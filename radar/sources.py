"""数据源适配器。新增一个源 = 写一个函数 + 加 @register("名字")。

每个适配器签名: fetch(settings, now) -> list[dict]
返回的 dict 至少包含 title / url，其余字段可选:
  summary(str) / published(datetime|None) / metrics(dict) / tags(list)

config.json 里可以用 "type" 指定适配器，这样同一个适配器能复用成多个频道。
"""
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime

from .util import clean, http_get, http_json, parse_time

SOURCES = {}

# 兜底显示名，config 里的 label 优先
LABELS = {
    "arxiv": "AI 论文",
    "github": "开源新星",
    "hackernews": "技术热点",
    "producthunt": "新品发布",
    "funding": "融资动态",
    "showhn": "Show HN",
    "feed": "资讯",
}


def register(name):
    def wrapper(func):
        SOURCES[name] = func
        return func

    return wrapper


def label(name, settings=None):
    if settings and settings.get("label"):
        return settings["label"]
    return LABELS.get(name, name)


# --------------------------------------------------------------------------- #
# 通用 RSS / Atom 解析：一个适配器打通所有订阅源
# --------------------------------------------------------------------------- #
def _parse_atom(root):
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall("atom:entry", ns):
        link = ""
        for node in entry.findall("atom:link", ns):
            if node.get("rel") in (None, "alternate"):
                link = node.get("href") or link
        items.append(
            {
                "title": clean(entry.findtext("atom:title", "", ns)),
                "url": link,
                "summary": clean(entry.findtext("atom:summary", "", ns) or entry.findtext("atom:content", "", ns)),
                "published": parse_time(entry.findtext("atom:published", "", ns) or entry.findtext("atom:updated", "", ns)),
                "metrics": {},
                "tags": [c.get("term") for c in entry.findall("atom:category", ns) if c.get("term")][:3],
            }
        )
    return items


def _parse_rss(root):
    channel = root.find("channel")
    if channel is None:
        return []
    items = []
    for entry in channel.findall("item"):
        published = None
        raw_date = entry.findtext("pubDate") or entry.findtext("{http://purl.org/dc/elements/1.1/}date")
        if raw_date:
            try:
                published = parsedate_to_datetime(raw_date).astimezone(__import__("datetime").timezone.utc)
            except (TypeError, ValueError):
                published = None
        items.append(
            {
                "title": clean(entry.findtext("title", "")),
                "url": (entry.findtext("link", "") or "").strip(),
                "summary": clean(entry.findtext("description", "")),
                "published": published,
                "metrics": {},
                "tags": [c.text for c in entry.findall("category") if c.text][:3],
            }
        )
    return items


def parse_feed(xml_text):
    root = ET.fromstring(xml_text)
    if root.tag.lower().endswith("feed"):
        return _parse_atom(root)
    return _parse_rss(root)


@register("feed")
def fetch_feed(settings, now):
    urls = settings.get("urls") or ([settings["url"]] if settings.get("url") else [])
    markers = settings.get("trim_markers") or []
    drop_patterns = [re.compile(p) for p in settings.get("summary_drop_patterns") or []]
    items = []
    for url in urls:
        items.extend(parse_feed(http_get(url, timeout=30).decode("utf-8", "replace")))
    for item in items:
        summary = item.get("summary") or ""
        for marker in markers:
            cut = summary.find(marker)
            if cut > 0:
                summary = summary[:cut]
        summary = summary.strip()
        if drop_patterns and any(p.search(summary) for p in drop_patterns):
            summary = ""
        item["summary"] = summary
    return items


# --------------------------------------------------------------------------- #
# arXiv：最新投稿论文
# --------------------------------------------------------------------------- #
@register("arxiv")
def fetch_arxiv(settings, now):
    categories = settings.get("categories") or ["cs.AI"]
    query = " OR ".join("cat:%s" % cat for cat in categories)
    url = (
        "https://export.arxiv.org/api/query?search_query=%s"
        "&sortBy=submittedDate&sortOrder=descending&max_results=%d"
        % (urllib.parse.quote(query, safe=":"), int(settings.get("max", 18)))
    )
    return _parse_atom(ET.fromstring(http_get(url, timeout=35).decode("utf-8", "replace")))


# --------------------------------------------------------------------------- #
# GitHub：近期新建且涨星快的仓库
# --------------------------------------------------------------------------- #
def _github_headers():
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        # 有 token 时限额从 10 次/分提到 30 次/分，CI 环境更稳
        headers["Authorization"] = "Bearer " + token
    return headers


@register("github")
def fetch_github(settings, now):
    since = (now - timedelta(days=int(settings.get("since_days", 7)))).strftime("%Y-%m-%d")
    query = "created:>%s stars:>%d" % (since, int(settings.get("min_stars", 80)))
    if settings.get("language"):
        query += " language:" + settings["language"]
    for topic in settings.get("topics") or []:
        query += " topic:" + topic
    url = "https://api.github.com/search/repositories?q=%s&sort=stars&order=desc&per_page=%d" % (
        urllib.parse.quote(query),
        int(settings.get("max", 15)),
    )
    data = http_json(url, headers=_github_headers())

    items = []
    for repo in data.get("items", []):
        full_name = repo.get("full_name") or ""
        if not full_name:
            continue
        tags = [repo.get("language")] if repo.get("language") else []
        tags += (repo.get("topics") or [])[:3]
        items.append(
            {
                "title": full_name,
                "url": repo.get("html_url") or "",
                "summary": clean(repo.get("description") or ""),
                "published": parse_time(repo.get("created_at")),
                "metrics": {"stars": repo.get("stargazers_count") or 0},
                "tags": [t for t in tags if t][:4],
            }
        )
    return items


# --------------------------------------------------------------------------- #
# Hacker News：首页热帖
# --------------------------------------------------------------------------- #
@register("hackernews")
def fetch_hackernews(settings, now):
    url = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=%d" % int(settings.get("max", 15))
    data = http_json(url)

    items = []
    for hit in data.get("hits", []):
        title = clean(hit.get("title") or hit.get("story_title") or "")
        if not title:
            continue
        link = hit.get("url") or "https://news.ycombinator.com/item?id=%s" % hit.get("objectID")
        items.append(
            {
                "title": title,
                "url": link,
                "summary": "",
                "published": parse_time(hit.get("created_at")),
                "metrics": {"points": hit.get("points") or 0},
                "tags": ["hn"],
            }
        )
    return items
