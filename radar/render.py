"""渲染：Markdown（邮件/公众号/小报童）与 HTML（网页订阅）。

同一份 report 可以渲染成不同层级（free / paid），差别只在数量和点评的露出范围。
"""
import html
from datetime import datetime, timezone

from .sources import label

SOURCE_ICON = {
    "arxiv": "📄",
    "github": "🚀",
    "hackernews": "🔥",
    "producthunt": "🆕",
    "funding": "💰",
    "showhn": "🛠️",
}


def _item_label(item):
    return item.get("label") or label(item["source"])


def _section_label(rows):
    return rows[0].get("label") if rows else ""


def _age(published):
    if not published:
        return ""
    hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600.0
    if hours < 1:
        return "刚刚"
    if hours < 24:
        return "%d 小时前" % int(hours)
    return "%d 天前" % int(hours // 24)


def _compact(number):
    number = int(number)
    if number >= 1000:
        return "%.1fk" % (number / 1000.0)
    return str(number)


def _signal(item):
    stars = item["metrics"].get("stars")
    if stars:
        return "★ %s" % _compact(stars)
    points = item["metrics"].get("points")
    if points:
        return "%s 分" % points
    return ""


def _truncate(text, limit):
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _esc(text):
    return html.escape(str(text or ""))


# --------------------------------------------------------------------------- #
# 层级配置：free 与 paid 的差异全部来自 config.json 的 tiers
# --------------------------------------------------------------------------- #
def tier_options(config, name):
    preset = (config.get("tiers") or {}).get(name) or {}
    out = config.get("output") or {}
    return {
        "name": name,
        "title": preset.get("title") or config["title"],
        "subtitle": preset.get("subtitle") or config.get("subtitle") or "",
        "top_n": int(preset.get("top_n", out.get("top_n", 8))),
        "per_section": int(preset.get("per_section", out.get("per_section", 6))),
        "show_takes": int(preset.get("show_takes", 10 ** 6)),
        "sections": preset.get("sections", "all"),
        "promo": preset.get("promo") or "",
    }


def _sections(report, config, tier):
    grouped = []
    for name in config.get("sources", {}):
        rows = [item for item in report["items"] if item["source"] == name]
        if rows:
            grouped.append((name, rows[: tier["per_section"]]))
    limit = tier["sections"]
    if isinstance(limit, int):
        grouped = grouped[:limit]
    return grouped


def _takes_enabled(tier, index):
    return index <= tier["show_takes"]


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def render_markdown(report, config, tier_name="paid"):
    tier = tier_options(config, tier_name)
    limit = int(config["output"]["max_summary_chars"])
    picks = (report.get("picks") or report["items"])[: tier["top_n"]]

    lines = ["# %s · %s" % (tier["title"], report["date"]), ""]
    if tier["subtitle"]:
        lines.append("> %s" % tier["subtitle"])
    lines += ["> 本期收录 %d 条 · 生成于 %s" % (len(report["items"]), report["generated_at"]), ""]
    lines += ["## 🔥 今日精选", ""]

    for index, item in enumerate(picks, 1):
        meta = " · ".join(x for x in [_item_label(item), _age(item["published"]), _signal(item)] if x)
        lines.append("%d. **[%s](%s)**" % (index, item["title"], item["url"]))
        if item["summary"]:
            lines.append("   %s" % _truncate(item["summary"], limit))
        if item.get("take") and _takes_enabled(tier, index):
            lines.append("   > 💬 %s" % item["take"])
        lines.append("   `%.1f` · %s" % (item["score"], meta))
        lines.append("")

    for name, rows in _sections(report, config, tier):
        lines += ["## %s %s" % (SOURCE_ICON.get(name, "•"), _section_label(rows)), ""]
        for item in rows:
            meta = " · ".join(x for x in [_age(item["published"]), _signal(item)] if x)
            lines.append(
                "- **[%s](%s)**  `%.1f`%s"
                % (item["title"], item["url"], item["score"], (" · " + meta) if meta else "")
            )
            if item["summary"]:
                lines.append("  %s" % _truncate(item["summary"], limit))
        lines.append("")

    if tier["promo"]:
        lines += ["---", "", tier["promo"], ""]

    if report["errors"]:
        lines += ["---", "", "运行告警：", ""]
        lines += ["- %s" % err for err in report["errors"]]
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
CSS = """
:root{--fg:#14161a;--muted:#6b7280;--line:#e6e8ec;--bg:#fff;--accent:#2563eb;--chip:#f3f4f6}
@media (prefers-color-scheme:dark){:root{--fg:#e6e8ec;--muted:#9aa3af;--line:#262a31;--bg:#0e1116;--accent:#60a5fa;--chip:#1a1f27}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.wrap{max-width:780px;margin:0 auto;padding:40px 20px 64px}
header{border-bottom:2px solid var(--fg);padding-bottom:18px;margin-bottom:28px}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:14px;margin:0}
h2{font-size:15px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:38px 0 14px;font-weight:600}
ol.picks{list-style:none;padding:0;margin:0;counter-reset:p}
ol.picks li{counter-increment:p;position:relative;padding:14px 0 14px 44px;border-bottom:1px solid var(--line)}
ol.picks li::before{content:counter(p);position:absolute;left:0;top:14px;width:28px;height:28px;border-radius:8px;background:var(--chip);color:var(--accent);font-size:13px;font-weight:700;display:flex;align-items:center;justify-content:center}
.item{padding:13px 0;border-bottom:1px solid var(--line)}
.item:last-child{border-bottom:0}
a{color:inherit;text-decoration:none}
a:hover{color:var(--accent)}
.t{font-weight:600}
.d{color:var(--muted);font-size:14px;margin:5px 0 0}
.meta{color:var(--muted);font-size:12px;margin-top:6px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.score{background:var(--chip);border-radius:999px;padding:1px 8px;font-variant-numeric:tabular-nums;font-weight:600}
.tag{color:var(--muted);font-size:12px}
.take{margin:9px 0 0;padding:8px 12px;background:var(--chip);border-left:3px solid var(--accent);border-radius:0 8px 8px 0;font-size:14px;line-height:1.6}
.take-label{display:inline-block;margin-right:8px;color:var(--accent);font-size:11px;font-weight:700;letter-spacing:.08em;vertical-align:1px}
.promo{margin-top:44px;padding:16px 18px;border:1px dashed var(--line);border-radius:10px;color:var(--muted);font-size:14px;line-height:1.7}
footer{margin-top:48px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}
nav a{color:var(--accent);font-size:14px}
table{width:100%;border-collapse:collapse;font-size:15px}
td{padding:10px 0;border-bottom:1px solid var(--line)}
td.r{text-align:right;color:var(--muted);font-size:13px}
"""


def _page(title, body):
    return (
        '<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        "<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n<div class=\"wrap\">\n%s\n</div>\n</body>\n</html>\n"
        % (_esc(title), CSS, body)
    )


def _take_html(item):
    if not item.get("take"):
        return ""
    return '<p class="take"><span class="take-label">点评</span>%s</p>' % _esc(item["take"])


def _item_html(item, limit):
    meta = [
        '<span class="score">%.1f</span>' % item["score"],
        '<span class="tag">%s</span>' % _esc(_item_label(item)),
    ]
    age = _age(item["published"])
    if age:
        meta.append('<span class="tag">%s</span>' % _esc(age))
    signal = _signal(item)
    if signal:
        meta.append('<span class="tag">%s</span>' % _esc(signal))
    for tag in item.get("tags", [])[:2]:
        meta.append('<span class="tag">#%s</span>' % _esc(tag))
    summary = '<p class="d">%s</p>' % _esc(_truncate(item["summary"], limit)) if item["summary"] else ""
    return (
        '<div class="item"><a href="%s" target="_blank" rel="noopener"><div class="t">%s</div></a>%s%s'
        '<div class="meta">%s</div></div>'
        % (_esc(item["url"]), _esc(item["title"]), summary, _take_html(item), "".join(meta))
    )


def render_html(report, config, tier_name="paid", with_archive=True):
    tier = tier_options(config, tier_name)
    limit = int(config["output"]["max_summary_chars"])
    picks = (report.get("picks") or report["items"])[: tier["top_n"]]

    parts = [
        '<header><h1>%s</h1><p class="sub">%s · %d 条 · %s</p></header>'
        % (_esc(tier["title"]), _esc(report["date"]), len(report["items"]), _esc(report["generated_at"]))
    ]

    rows = []
    for index, item in enumerate(picks, 1):
        meta = [
            '<span class="score">%.1f</span>' % item["score"],
            '<span class="tag">%s</span>' % _esc(_item_label(item)),
        ]
        age = _age(item["published"])
        if age:
            meta.append('<span class="tag">%s</span>' % _esc(age))
        signal = _signal(item)
        if signal:
            meta.append('<span class="tag">%s</span>' % _esc(signal))
        summary = '<p class="d">%s</p>' % _esc(_truncate(item["summary"], limit)) if item["summary"] else ""
        take = _take_html(item) if _takes_enabled(tier, index) else ""
        rows.append(
            '<li><a href="%s" target="_blank" rel="noopener"><span class="t">%s</span></a>%s%s'
            '<div class="meta">%s</div></li>'
            % (_esc(item["url"]), _esc(item["title"]), summary, take, "".join(meta))
        )
    parts.append('<h2>今日精选</h2><ol class="picks">%s</ol>' % "".join(rows))

    for name, items in _sections(report, config, tier):
        parts.append(
            '<h2>%s %s</h2>%s'
            % (SOURCE_ICON.get(name, "•"), _esc(_section_label(items)), "".join(_item_html(i, limit) for i in items))
        )

    if tier["promo"]:
        parts.append('<div class="promo">%s</div>' % _esc(tier["promo"]))

    footer = "由 daily-radar 自动生成 · 采集 %d 条 / 收录 %d 条" % (sum(report["stats"].values()), len(report["items"]))
    if report["errors"]:
        footer += " · 告警 %d 项" % len(report["errors"])
    nav = '<br><nav><a href="index.html">历史归档</a></nav>' if with_archive else ""
    parts.append("<footer>%s%s</footer>" % (_esc(footer), nav))

    return _page("%s · %s" % (tier["title"], report["date"]), "\n".join(parts))


def render_index(entries, config):
    """entries: [(date, count, filename)] 按日期倒序。"""
    rows = "".join(
        '<tr><td><a href="%s">%s</a></td><td class="r">%d 条</td></tr>' % (_esc(name), _esc(date), count)
        for date, count, name in entries
    )
    body = '<header><h1>%s</h1><p class="sub">%s · 历史归档</p></header><table>%s</table>' % (
        _esc(config["title"]),
        _esc(config.get("subtitle") or ""),
        rows or "<tr><td>暂无归档</td></tr>",
    )
    return _page("%s · 归档" % config["title"], body)
