"""发布包：把当天情报变成可以直接粘贴到各平台的内容。

产出四种东西：
- 小红书：标题 + 正文 + 标签（口语、分点、无 markdown）
- 公众号：标题 + 摘要 + 长文（有小标题，可附原文链接）
- 朋友圈：两三行的短文案
- 封面文案：做图用的主标题和副标题

一次 LLM 调用产出全部，控制在 ~2500 tokens。
"""
import json
import os

from .commentary import _post
from .util import clean

SYSTEM = (
    "你是中文科技自媒体作者，读者是中国的独立开发者和小团队创始人。"
    "你写东西具体、直接、有判断，讨厌空话。禁止使用「赋能」「生态」「引领」「颠覆」这类词，"
    "禁止夸张开头（如「震惊」「必看」「炸裂」），禁止编造事实。"
)

INSTRUCTION = """根据下面的今日情报，产出三个平台的发布内容。

【小红书】
- 标题：不超过 20 字，要有具体信息或反常识判断，不要标题党
- 正文：300-450 字，口语化，分 3-4 点，每点给一句判断（不是复述标题）
- 结尾：一句提问，引导评论
- 标签：5 个，不带 #
- 正文里不要用 markdown 符号，不要放链接

【公众号】
- 标题：不超过 26 字
- 摘要：不超过 60 字
- 正文：700-900 字，开头用一个具体场景或反常识判断引入，中间 2-3 个小标题（用「一、」「二、」这种），结尾落到一个可执行的动作
- 可以用 markdown 的小标题，正文中不要堆砌链接

【朋友圈】
- 2-3 行，不超过 100 字，像人随手发的，不要 emoji 堆叠，不要标签

严格要求：只输出 JSON，不要任何解释或代码块标记，格式如下
{"xiaohongshu":{"title":"","body":"","tags":["","","","",""]},
 "wechat":{"title":"","digest":"","body":""},
 "moments":""}

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
    rows = []
    for item in items:
        rows.append(
            {
                "来源": item.get("label") or item.get("source"),
                "标题": item["title"],
                "摘要": clean(item.get("summary") or "")[:120],
                "点评": item.get("take") or "",
            }
        )
    return rows


def build_bundle(report, config, api_key=None, limit=6):
    ai = config.get("ai") or {}
    picks = (report.get("picks") or report["items"])[:limit]
    if not ai.get("enabled") or not api_key:
        return None

    payload = {
        "model": ai.get("model") or "deepseek-chat",
        "temperature": 0.7,
        "max_tokens": 3000,
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

    # 模型偶尔漏标签，用配置兜底，避免发布时那一栏是空的
    xhs = bundle.setdefault("xiaohongshu", {})
    tags = [str(t).strip().lstrip("#") for t in (xhs.get("tags") or []) if str(t).strip()]
    if not tags:
        tags = list((config.get("publish") or {}).get("default_tags") or [])
    xhs["tags"] = tags[:5]
    return bundle


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content.rstrip() + "\n")


def write_bundle(bundle, report, out_dir):
    """把一个 bundle 落成可以直接打开复制的一组文件。"""
    date = report["date"]
    xhs = bundle.get("xiaohongshu") or {}
    wechat = bundle.get("wechat") or {}
    moments = bundle.get("moments") or ""

    paths = []

    xhs_text = []
    xhs_text.append("# 小红书\n")
    xhs_text.append("## 标题")
    xhs_text.append(xhs.get("title", ""))
    xhs_text.append("\n## 正文")
    xhs_text.append(xhs.get("body", ""))
    xhs_text.append("\n## 标签")
    xhs_text.append(" ".join("#%s" % t.strip("#") for t in (xhs.get("tags") or [])))
    xhs_text.append("\n## 封面文案（做图用）")
    xhs_text.append("主标题：%s" % xhs.get("title", ""))
    xhs_text.append("副标题：%s" % (wechat.get("digest") or ""))
    path = os.path.join(out_dir, "小红书.md")
    _write(path, "\n".join(xhs_text))
    paths.append(path)

    wechat_text = [
        "# 公众号\n",
        "## 标题",
        wechat.get("title", ""),
        "\n## 摘要",
        wechat.get("digest", ""),
        "\n## 正文",
        wechat.get("body", ""),
        "\n## 原文清单（附在文末，也可不加）",
    ]
    for item in (report.get("picks") or [])[:8]:
        wechat_text.append("- %s  %s" % (item["title"], item["url"]))
    path = os.path.join(out_dir, "公众号.md")
    _write(path, "\n".join(wechat_text))
    paths.append(path)

    path = os.path.join(out_dir, "朋友圈.txt")
    _write(path, moments)
    paths.append(path)

    guide = [
        "# 发布指引 · %s" % date,
        "",
        "1. 先发朋友圈（30 秒），测试有没有人回你",
        "2. 小红书：标题 + 正文复制，封面用「封面文案」做一张纯文字图",
        "3. 公众号：标题、摘要、正文分别复制；原文清单按需加在文末",
        "4. 小红书不发链接，引导「评论区/私信」；公众号可以放链接",
        "",
        "## 今天的素材（给做图用）",
    ]
    for item in (report.get("picks") or [])[:3]:
        guide.append("- %s" % item["title"])
    path = os.path.join(out_dir, "发布指引.md")
    _write(path, "\n".join(guide))
    paths.append(path)

    return paths
