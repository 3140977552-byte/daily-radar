"""用 LLM 给精选条目写一句中文点评。

设计原则：
1. 可选。没配 key、网络挂了、模型乱输出，都只记一条告警，日报照常产出。
2. 省 token。所有精选条目打成一个请求，一次调用，不让成本随条数线性涨。
3. 只点评精选。全量条目靠规则排序，点评是稀缺资源，用在最该用的地方。
"""
import json
import os
import re
import urllib.request

SYSTEM = (
    "你是中文科技情报编辑，读者是中国的独立开发者和小团队创始人。"
    "你的任务不是复述信息，而是帮读者判断：这条值不值得点开、对他意味着什么。"
    "风格：口语、具体、不吹不黑。禁止使用「赋能」「生态」「引领」这类词。"
)

INSTRUCTION = """给下面每条情报写一句中文点评。

规则：
1. 每条不超过 45 个字，一句话说完。
2. 必须给出判断（例如「值得看，因为…」「可以先跳过」「这类玩法国内还没人做」），不要只复述标题。
3. 不要以「这条」「该」「此」开头。
4. 只输出 JSON 数组，不要任何解释文字，格式：
[{"id": "条目 id", "take": "点评"}]

情报列表：
"""


def _post(url, headers, payload, timeout):
    request = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    start, end = text.find("["), text.rfind("]")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def _payload(items, model):
    brief = [
        {
            "id": item["id"],
            "来源": item.get("label") or item["source"],
            "标题": item["title"],
            "摘要": (item["summary"] or "")[:150],
        }
        for item in items
    ]
    return {
        "model": model,
        "temperature": 0.4,
        "max_tokens": 1200,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": INSTRUCTION + json.dumps(brief, ensure_ascii=False, indent=1)},
        ],
    }


def enrich(report, config):
    """给 report['picks'] 里的每一条挂上 item['take']。就地修改并返回 report。"""
    ai = config.get("ai") or {}
    if not ai.get("enabled"):
        return report

    env_name = ai.get("api_key_env") or "RADAR_API_KEY"
    api_key = os.environ.get(env_name)
    if not api_key:
        report["errors"].append("AI 点评已跳过：环境变量 %s 未设置" % env_name)
        return report

    picks = report.get("picks") or []
    limit = int(ai.get("max_items", 8))
    targets = picks[:limit]
    if not targets:
        return report

    base_url = (ai.get("base_url") or "https://api.deepseek.com").rstrip("/")
    timeout = int(ai.get("timeout", 90))
    try:
        response = _post(
            base_url + "/chat/completions",
            {"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
            _payload(targets, ai.get("model") or "deepseek-chat"),
            timeout,
        )
        content = response["choices"][0]["message"]["content"]
        entries = _extract_json(content)
    except Exception as exc:  # noqa: BLE001 - 点评失败不能影响出报
        report["errors"].append("AI 点评失败：%s" % exc)
        return report

    takes = {}
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and entry.get("id") and entry.get("take"):
            takes[str(entry["id"])] = str(entry["take"]).strip()

    applied = 0
    for item in report["items"]:
        take = takes.get(item["id"])
        if take:
            item["take"] = take
            applied += 1

    report["ai"] = {"model": response.get("model"), "applied": applied, "usage": response.get("usage") or {}}
    if applied < len(targets):
        report["errors"].append("AI 点评只覆盖了 %d/%d 条" % (applied, len(targets)))
    return report
