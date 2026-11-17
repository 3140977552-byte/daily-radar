"""流水线：采集 -> 归一化 -> 去重 -> 打分 -> 排序。"""
import hashlib
import math
import re
from datetime import datetime, timedelta, timezone

from .sources import SOURCES, label
from .util import canonical_url, clean, norm_title

CJK_RE = re.compile(r"[\u4e00-\u9fff]")


# --------------------------------------------------------------------------- #
# 关键词匹配：英文词按“词首边界”匹配（launch 能命中 launches，但 api 不会命中 capital）
# --------------------------------------------------------------------------- #
def compile_keywords(keywords):
    matchers = []
    for keyword, weight in (keywords or {}).items():
        key = str(keyword).lower().strip()
        if not key:
            continue
        if CJK_RE.search(key):
            matchers.append((key, float(weight), None))
        else:
            pattern = re.compile(r"(?<![a-z0-9])" + re.escape(key))
            matchers.append((key, float(weight), pattern))
    return matchers


def keyword_points(text, matchers):
    if not text:
        return 0.0
    lowered = text.lower()
    total = 0.0
    for key, weight, pattern in matchers:
        if pattern is None:
            if key in lowered:
                total += weight
        elif pattern.search(lowered):
            total += weight
    return total


def normalize(raw, source_name, now, settings=None):
    settings = settings or {}
    title = clean(raw.get("title"))
    url = (raw.get("url") or "").strip()
    if not title or not url:
        return None
    digest = hashlib.sha1((source_name + "|" + canonical_url(url)).encode("utf-8")).hexdigest()[:12]
    return {
        "id": digest,
        "title": title,
        "url": url,
        "summary": clean(raw.get("summary")),
        "source": source_name,
        "label": label(source_name, settings),
        "published": raw.get("published"),
        "metrics": raw.get("metrics") or {},
        "tags": [t for t in (raw.get("tags") or []) if t][:4],
        "score": 0.0,
    }


def dedupe(items):
    """同一条内容可能在多个源出现：先按 URL 指纹，再按标题指纹。"""
    seen_url, seen_title, kept = set(), set(), []
    for item in items:
        url_key = canonical_url(item["url"])
        title_key = norm_title(item["title"])
        if url_key in seen_url or (title_key and title_key in seen_title):
            continue
        seen_url.add(url_key)
        if title_key:
            seen_title.add(title_key)
        kept.append(item)
    return kept


def score(item, config, kw_points, now):
    """可解释的加权打分：源权重 + 关键词命中 + 时效衰减 + 热度信号。"""
    rules = config["scoring"]
    total = float(config["sources"].get(item["source"], {}).get("weight", 1.0)) + kw_points

    published = item.get("published")
    half_life = float(rules["half_life_hours"])
    age_hours = (now - published).total_seconds() / 3600.0 if published else half_life
    age_hours = max(age_hours, 0.0)
    total += float(rules["freshness_bonus"]) * (0.5 ** (age_hours / half_life))

    signal = item["metrics"].get("stars") or item["metrics"].get("points") or 0
    if signal:
        total += float(rules["signal_weight"]) * math.log1p(float(signal))

    return round(total, 3)


def select_picks(items, config):
    """今日精选：按分数取，但限制单个频道的占比，避免整屏都是融资新闻。"""
    top_n = int(config["output"].get("top_n", 8))
    cap = int(config["output"].get("pick_diversity", 2))
    counts, picks = {}, []
    for item in items:
        source = item["source"]
        if counts.get(source, 0) >= cap:
            continue
        picks.append(item)
        counts[source] = counts.get(source, 0) + 1
        if len(picks) >= top_n:
            break
    return picks


def build(config, now=None):
    now = now or datetime.now(timezone.utc)
    matchers = compile_keywords(config.get("keywords"))
    items, errors, stats = [], [], {}

    for name, settings in config.get("sources", {}).items():
        if not settings.get("enabled"):
            continue
        adapter = settings.get("type") or name
        fetcher = SOURCES.get(adapter)
        if fetcher is None:
            errors.append("%s: 未注册的适配器 %s" % (name, adapter))
            continue
        try:
            raw_items = fetcher(settings, now)
        except Exception as exc:  # noqa: BLE001 - 单源故障降级，不影响整期日报
            errors.append("%s: %s" % (settings.get("label") or name, exc))
            stats[name] = 0
            continue

        limit = settings.get("max")
        if limit:
            raw_items = raw_items[: int(limit)]
        normalized = [normalize(raw, name, now, settings) for raw in raw_items]
        normalized = [item for item in normalized if item]
        max_age = settings.get("max_age_days")
        if max_age:
            cutoff = timedelta(days=float(max_age))
            normalized = [i for i in normalized if not i["published"] or (now - i["published"]) <= cutoff]
        stats[name] = len(normalized)
        items.extend(normalized)

    items = dedupe(items)
    multiplier = float(config["scoring"]["keyword_title_multiplier"])
    for item in items:
        kw_points = keyword_points(item["title"], matchers) * multiplier + keyword_points(item["summary"], matchers)
        item["score"] = score(item, config, kw_points, now)
        item["_kw"] = kw_points

    # 相关性闸门：对泛资讯源（如 HN 首页），没有命中任何赛道关键词的直接丢弃，
    # 避免“热度高但和读者无关”的内容挤进精选。
    items = [
        item
        for item in items
        if not (config["sources"].get(item["source"], {}).get("require_keyword") and item["_kw"] <= 0)
    ]
    for item in items:
        item.pop("_kw", None)
    items.sort(key=lambda x: x["score"], reverse=True)

    return {
        "date": now.strftime("%Y-%m-%d"),
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "items": items,
        "picks": select_picks(items, config),
        "errors": errors,
        "stats": stats,
    }
