"""周报：聚合最近 N 天的归档，选出本周最值得看的条目，并让 LLM 写一段趋势观察。

周报是付费层的主力交付物——单日情报谁都能抄，一周的判断力抄不走。
"""
import json
import os
from datetime import date, datetime, timedelta, timezone

from .commentary import SYSTEM, _extract_json, _post
from .render import CSS, SOURCE_ICON, _esc, _item_label, _page, _signal, _take_html, _truncate
from .util import parse_time

WEEKLY_SYSTEM = (
    "你是中文科技情报编辑，读者是中国的独立开发者和小团队创始人。"
    "你擅长从一周的零散信息里看出趋势，说话直接，不堆术语，不用「赋能」「生态」「引领」这类词。"
)


def load_recent(data_dir, days):
    if not os.path.isdir(data_dir):
        return []
    names = sorted(n for n in os.listdir(data_dir) if n.endswith(".json"))
    reports = []
    for name in names[-days:]:
        try:
            with open(os.path.join(data_dir, name), "r", encoding="utf-8") as handle:
                reports.append(json.load(handle))
        except Exception:  # noqa: BLE001 - 单份归档损坏不影响周报
            continue
    return reports


def merge_items(reports):
    merged = {}
    for report in reports:
        for raw in report.get("items") or []:
            item = dict(raw)
            item["published"] = parse_time(item.get("published"))
            key = item.get("id") or item.get("url")
            if not key:
                continue
            if key not in merged or item.get("score", 0) > merged[key].get("score", 0):
                merged[key] = item
    items = list(merged.values())
    items.sort(key=lambda x: x.get("score", 0), reverse=True)
    return items


def _week_label(days):
    today = date.today()
    start = today - timedelta(days=max(days - 1, 0))
    return "%s ~ %s" % (start.isoformat(), today.isoformat()), today.isocalendar()


def _summarize(items, config, api_key):
    ai = config.get("ai") or {}
    if not ai.get("enabled") or not api_key or not items:
        return ""
    titles = [{"标题": i["title"], "来源": _item_label(i)} for i in items[:40]]
    payload = {
        "model": ai.get("model") or "deepseek-chat",
        "temperature": 0.5,
        "max_tokens": 700,
        "messages": [
            {"role": "system", "content": WEEKLY_SYSTEM},
            {
                "role": "user",
                "content": (
                    "根据下面这周的科技情报标题，写一段 150-200 字的中文周度观察。\n"
                    "要求：点出 2-3 个真正值得跟进的趋势，说清对独立开发者的影响；"
                    "不要逐条复述；不要用列表；直接输出段落文字，不要任何前缀或标题。\n\n"
                    + json.dumps(titles, ensure_ascii=False, indent=1)
                ),
            },
        ],
    }
    base_url = (ai.get("base_url") or "https://api.deepseek.com").rstrip("/")
    response = _post(
        base_url + "/chat/completions",
        {"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
        payload,
        int(ai.get("timeout", 90)),
    )
    return (response["choices"][0]["message"]["content"] or "").strip()


def build(config, data_dir, days=7, api_key=None):
    reports = load_recent(data_dir, days)
    items = merge_items(reports)
    dates = sorted(str(r.get("date")) for r in reports if r.get("date"))
    label = "%s ~ %s" % (dates[0], dates[-1]) if dates else "暂无归档"
    iso = date.today().isocalendar()

    grouped = []
    for name in config.get("sources", {}):
        rows = [i for i in items if i["source"] == name][:3]
        if rows:
            grouped.append((name, rows))

    observation, error = "", ""
    try:
        observation = _summarize(items, config, api_key)
    except Exception as exc:  # noqa: BLE001 - 周报没有 AI 段落也要能发
        error = "周报观察生成失败：%s" % exc

    return {
        "range": label,
        "week": "W%02d" % iso[1],
        "days": len(reports),
        "items": items,
        "top": items[:10],
        "sections": grouped,
        "observation": observation,
        "error": error,
    }


# --------------------------------------------------------------------------- #
# 渲染
# --------------------------------------------------------------------------- #
def render_markdown(weekly, config):
    lines = ["# %s · 周报 %s" % (config["title"], weekly["week"]), ""]
    lines.append("> %s · 覆盖 %d 天 / %d 条" % (weekly["range"], weekly["days"], len(weekly["items"])))
    lines.append("")
    if weekly["observation"]:
        lines += ["## 本周观察", "", weekly["observation"], ""]
    lines += ["## 本周最值得看的 10 条", ""]
    for index, item in enumerate(weekly["top"], 1):
        lines.append("%d. **[%s](%s)**" % (index, item["title"], item["url"]))
        if item.get("summary"):
            lines.append("   %s" % _truncate(item["summary"], 140))
        if item.get("take"):
            lines.append("   > 💬 %s" % item["take"])
        lines.append("")
    for name, rows in weekly["sections"]:
        lines += ["## %s %s" % (SOURCE_ICON.get(name, "•"), rows[0].get("label") or name), ""]
        for item in rows:
            lines.append("- [%s](%s)  `%.1f`" % (item["title"], item["url"], item.get("score", 0)))
        lines.append("")
    if weekly["error"]:
        lines += ["---", "", weekly["error"], ""]
    return "\n".join(lines).rstrip() + "\n"


def render_html(weekly, config):
    limit = int(config["output"]["max_summary_chars"])
    parts = [
        "<header><h1>%s · 周报</h1><p class=\"sub\">%s · 覆盖 %d 天 / %d 条</p></header>"
        % (_esc(config["title"]), _esc(weekly["range"]), weekly["days"], len(weekly["items"]))
    ]

    if weekly["observation"]:
        parts.append('<h2>本周观察</h2><p class="d">%s</p>' % _esc(weekly["observation"]))

    rows = []
    for index, item in enumerate(weekly["top"], 1):
        meta = ['<span class="score">%.1f</span>' % item.get("score", 0)]
        meta.append('<span class="tag">%s</span>' % _esc(_item_label(item)))
        signal = _signal(item)
        if signal:
            meta.append('<span class="tag">%s</span>' % _esc(signal))
        summary = '<p class="d">%s</p>' % _esc(_truncate(item["summary"], limit)) if item.get("summary") else ""
        rows.append(
            '<li><a href="%s" target="_blank" rel="noopener"><span class="t">%s</span></a>%s%s'
            '<div class="meta">%s</div></li>'
            % (_esc(item["url"]), _esc(item["title"]), summary, _take_html(item), "".join(meta))
        )
    parts.append('<h2>本周最值得看的 10 条</h2><ol class="picks">%s</ol>' % "".join(rows))

    for name, items in weekly["sections"]:
        inner = "".join(
            '<div class="item"><a href="%s" target="_blank" rel="noopener"><div class="t">%s</div></a>'
            '<div class="meta"><span class="score">%.1f</span></div></div>'
            % (_esc(i["url"]), _esc(i["title"]), i.get("score", 0))
            for i in items
        )
        parts.append(
            '<h2>%s %s</h2>%s'
            % (SOURCE_ICON.get(name, "•"), _esc(items[0].get("label") or name), inner)
        )

    if weekly["error"]:
        parts.append('<div class="promo">%s</div>' % _esc(weekly["error"]))
    parts.append("<footer>周报由 daily-radar 自动汇总 · %s</footer>" % _esc(weekly["range"]))
    return _page("%s · 周报 %s" % (config["title"], weekly["week"]), "\n".join(parts))
