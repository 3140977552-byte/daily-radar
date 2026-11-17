"""零依赖小工具：HTTP、时间、文本清洗。"""
import gzip
import html as html_module
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) DailyRadar/1.0"


def http_get(url, headers=None, timeout=25, retries=2):
    """带重试的 GET，返回 bytes。全流程只用标准库，免装依赖。"""
    hdr = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        hdr.update(headers)
    last_err = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except Exception as exc:  # noqa: BLE001 - 单源失败不应拖垮整条流水线
            last_err = exc
    raise RuntimeError("请求失败: %s (%s)" % (url[:80], last_err))


def http_json(url, headers=None, timeout=25, retries=2):
    hdr = {"Accept": "application/json"}
    if headers:
        hdr.update(headers)
    return json.loads(http_get(url, headers=hdr, timeout=timeout, retries=retries).decode("utf-8", "replace"))


def parse_time(value):
    """把各种 ISO 时间字符串转成 UTC datetime，失败返回 None。"""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        cleaned = re.sub(r"\.\d+", "", text)  # 处理超过 6 位的小数秒
        try:
            dt = datetime.fromisoformat(cleaned)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean(text):
    """解实体 + 去标签 + 压缩空白。RSS 内容常被双重转义，所以跑两轮。"""
    if not text:
        return ""
    text = str(text)
    for _ in range(2):
        text = _TAG_RE.sub(" ", html_module.unescape(text))
    return _WS_RE.sub(" ", text).strip()


def norm_title(text):
    """用于去重的标题指纹：只保留字母、数字、汉字。"""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (text or "").lower())


def canonical_url(url):
    """去掉追踪参数和末尾斜杠，方便判断是否同一条。"""
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url.strip())
    query = urllib.parse.urlencode(
        [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query) if not k.lower().startswith("utm_")]
    )
    path = parsed.path.rstrip("/") or "/"
    host = parsed.netloc.lower().replace("www.", "")
    return urllib.parse.urlunsplit((parsed.scheme or "https", host, path, query, ""))


def truncate(text, limit):
    text = clean(text)
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text
