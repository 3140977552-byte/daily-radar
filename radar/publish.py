"""小红书发布包：把当天情报写成可以直接粘贴的笔记。

只产出一个文件：发布包/YYYY-MM-DD/小红书.md
一次 LLM 调用，约 1200 tokens。
"""
import json
import os

from . import cover as cover_module
from .commentary import _post
from .util import clean

SYSTEM = (
    "你是小红书上的中文科技博主，读者是中国的独立开发者和小团队创始人。"
    "你说话具体、直接、有判断，讨厌空话。禁止使用「赋能」「生态」「引领」「颠覆」这类词，"
    "禁止标题党（如「震惊」「必看」「炸裂」），禁止编造事实。"
)

INSTRUCTION = """根据下面的今日情报，写一篇小红书笔记。

要求：
- 标题：不超过 20 字，要有具体信息或反常识判断，不要夸张
- 正文：300-450 字，口语化，分 3-4 段，每段一个判断（不是复述标题），段与段之间空一行
- 结尾：一句提问，引导评论
- 正文里不要用任何 markdown 符号（不要 #、*、-），不要放链接和网址
- 标签：5 个，不带 # 号
- 封面：主标题（可用标题本身）+ 副标题（一句钩子，20 字内）

只输出 JSON，不要解释、不要代码块标记：
{"title":"","body":"","tags":["","","","",""],"cover":{"title":"","subtitle":""}}

今日情报：
"""


def _json_block(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def _brief(items):
    return [
        {
            "来源": item.get("label") or item.get("source"),
            "标题": item["title"],
            "摘要": clean(item.get("summary") or "")[:120],
            "点评": item.get("take") or "",
        }
        for item in items
    ]


def build_bundle(report, config, api_key=None, limit=6):
    ai = config.get("ai") or {}
    if not ai.get("enabled") or not api_key:
        return None

    picks = (report.get("picks") or report["items"])[:limit]
    payload = {
        "model": ai.get("model") or "deepseek-chat",
        "temperature": 0.7,
        "max_tokens": 1600,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": INSTRUCTION + json.dumps(_brief(picks), ensure_ascii=False, indent=1)},
        ],
    }
    base_url = (ai.get("base_url") or "https://api.deepseek.com").rstrip("/")
    response = _post(
        base_url + "/chat/completions",
        {"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
        payload,
        int(ai.get("timeout", 120)),
    )
    bundle = _json_block(response["choices"][0]["message"]["content"])
    bundle["_usage"] = (response.get("usage") or {}).get("total_tokens")

    tags = [str(t).strip().lstrip("#") for t in (bundle.get("tags") or []) if str(t).strip()]
    if not tags:
        tags = list((config.get("publish") or {}).get("default_tags") or [])
    bundle["tags"] = tags[:5]
    bundle.setdefault("cover", {})
    return bundle


def render_markdown(bundle):
    cover = bundle.get("cover") or {}
    lines = ["# 小红书", "", "## 标题", bundle.get("title", ""), "", "## 正文", bundle.get("body", ""), ""]
    lines += ["## 标签", " ".join("#%s" % t for t in bundle.get("tags") or []), ""]
    lines += ["## 封面文案（做图用）"]
    lines += ["主标题：%s" % (cover.get("title") or bundle.get("title", ""))]
    lines += ["副标题：%s" % (cover.get("subtitle") or ""), ""]
    return "\n".join(lines).rstrip() + "\n"


def write_bundle(bundle, report, out_dir):
    """落盘小红书稿 + 3:4 封面图，返回 (文件列表, 封面错误信息)。"""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    cover_error = ""
    cover_path = ""

    cover_cfg = (bundle.get("cover") or {})
    pub_cfg = config.get("publish") or {}
    try:
        cover_path = os.path.join(out_dir, "封面.png")
        cover_module.render(
            cover_cfg.get("title") or bundle.get("title", ""),
            cover_cfg.get("subtitle") or "",
            report["date"],
            cover_path,
            footer=pub_cfg.get("cover_footer", "每日更新"),
            show_date=bool(pub_cfg.get("cover_show_date", True)),
        )
        paths.append(cover_path)
    except Exception as exc:  # noqa: BLE001 - 封面失败不影响文字稿
        cover_error = "封面生成失败：%s" % exc
        cover_path = ""

    path = os.path.join(out_dir, "小红书.md")
    markdown = render_markdown(bundle)
    if cover_path:
        markdown = markdown.rstrip() + "\n\n## 封面\n封面.png（1080×1440，直接上传）\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(markdown)
    paths.insert(0, path)
    return paths, cover_error
