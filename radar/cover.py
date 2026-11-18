"""生成小红书封面图（3:4，1080×1440）。

为什么不用文生图模型：中文字形会被画错，标题又是封面最关键的信息。
这里用 SVG 排版（真字体、锐利、零成本），再经 QuickLook 转 PNG、裁成 3:4。

流程：
  1440×1440 画布排版（内容留在中间 960px 安全区）
  → qlmanage 转 PNG
  → sips 居中裁成 1080×1440（两侧各裁 180px）
"""
import os
import re
import shutil
import subprocess
import tempfile

FONT = "PingFang SC, Hiragino Sans GB, Microsoft YaHei, sans-serif"

CANVAS = 1440          # 画布边长
MARGIN = 240           # 左右安全边距（裁剪后剩 60px）
CONTENT_W = CANVAS - MARGIN * 2

BG_TOP = "#0b1220"
BG_BOTTOM = "#17203a"
ACCENT = "#3b82f6"
TITLE_COLOR = "#f8fafc"
SUB_COLOR = "#93a3b8"
MUTED = "#5b6b82"


def _esc(text):
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _char_width(ch, size):
    code = ord(ch)
    if code > 0x2E80:          # 汉字、全角标点
        return size * 1.0
    if ch.isupper():
        return size * 0.66
    if ch.isdigit():
        return size * 0.58
    if ch == " ":
        return size * 0.28
    return size * 0.55


def wrap(text, size, max_width, max_lines=4):
    """按估算宽度手工折行——SVG 不会自动换行。"""
    lines, current, width = [], "", 0.0
    for ch in text.strip():
        w = _char_width(ch, size)
        if width + w > max_width and current:
            lines.append(current)
            current, width = ch, w
        else:
            current += ch
            width += w
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(len(lines[-1]) - 1, 1)] + "…"
    return lines or [""]


def build_svg(title, subtitle, date_label, brand="独立开发情报", footer="每天 09:30 更新"):
    title_lines = wrap(title, 82, CONTENT_W, max_lines=4)
    sub_lines = wrap(subtitle, 40, CONTENT_W, max_lines=2) if subtitle else []

    # 竖向居中：标题块整体压在画面中上部
    title_size, line_height = 82, 108
    block_height = len(title_lines) * line_height
    start_y = 520 - block_height // 2 + title_size

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (CANVAS, CANVAS, CANVAS, CANVAS),
        "<defs>",
        '<linearGradient id="bg" x1="0" y1="0" x2="0.3" y2="1">',
        '<stop offset="0%%" stop-color="%s"/>' % BG_TOP,
        '<stop offset="100%%" stop-color="%s"/>' % BG_BOTTOM,
        "</linearGradient>",
        '<radialGradient id="glow" cx="0.85" cy="0.15" r="0.55">',
        '<stop offset="0%%" stop-color="%s" stop-opacity="0.35"/>' % ACCENT,
        '<stop offset="100%%" stop-color="%s" stop-opacity="0"/>' % ACCENT,
        "</radialGradient>",
        "</defs>",
        '<rect width="100%" height="100%" fill="url(#bg)"/>',
        '<rect width="100%" height="100%" fill="url(#glow)"/>',
    ]

    # 顶部品牌行
    parts.append(
        '<text x="%d" y="300" font-family="%s" font-size="34" font-weight="600" '
        'letter-spacing="4" fill="%s">%s</text>' % (MARGIN, FONT, MUTED, _esc(brand))
    )
    parts.append('<rect x="%d" y="342" width="88" height="6" rx="3" fill="%s"/>' % (MARGIN, ACCENT))

    # 主标题
    y = start_y
    for line in title_lines:
        parts.append(
            '<text x="%d" y="%d" font-family="%s" font-size="%d" font-weight="700" fill="%s">%s</text>'
            % (MARGIN, y, FONT, title_size, TITLE_COLOR, _esc(line))
        )
        y += line_height

    # 副标题
    y += 34
    for line in sub_lines:
        parts.append(
            '<text x="%d" y="%d" font-family="%s" font-size="40" fill="%s">%s</text>'
            % (MARGIN, y, FONT, SUB_COLOR, _esc(line))
        )
        y += 60

    # 底部信息
    parts.append(
        '<line x1="%d" y1="1160" x2="%d" y2="1160" stroke="#243049" stroke-width="2"/>'
        % (MARGIN, CANVAS - MARGIN)
    )
    parts.append(
        '<text x="%d" y="1220" font-family="%s" font-size="30" fill="%s">%s</text>'
        % (MARGIN, FONT, MUTED, _esc(date_label))
    )
    parts.append(
        '<text x="%d" y="1220" text-anchor="end" font-family="%s" font-size="30" fill="%s">%s</text>'
        % (CANVAS - MARGIN, FONT, MUTED, _esc(footer))
    )
    parts.append("</svg>")
    return "\n".join(parts)


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def render(title, subtitle, date_label, out_png, **kwargs):
    """生成 PNG，返回路径；失败时抛异常，由调用方降级处理。"""
    if not shutil.which("qlmanage") or not shutil.which("sips"):
        raise RuntimeError("缺少 qlmanage 或 sips，无法生成封面")

    svg_text = build_svg(title, subtitle, date_label, **kwargs)
    workdir = tempfile.mkdtemp(prefix="radar-cover-")
    try:
        svg_path = os.path.join(workdir, "cover.svg")
        with open(svg_path, "w", encoding="utf-8") as handle:
            handle.write(svg_text)

        result = _run(["qlmanage", "-t", "-s", str(CANVAS), "-o", workdir, svg_path])
        raw = os.path.join(workdir, "cover.svg.png")
        if not os.path.exists(raw):
            raise RuntimeError("QuickLook 转图失败：%s" % (result.stderr or result.stdout)[:200])

        # 居中裁成 3:4：高 1440、宽 1080
        os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
        out_height, out_width = CANVAS, int(CANVAS * 0.75)
        crop = _run(["sips", "-c", str(out_height), str(out_width), raw, "--out", out_png])
        if not os.path.exists(out_png):
            raise RuntimeError("sips 裁剪失败：%s" % (crop.stderr or crop.stdout)[:200])
        return out_png
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def safe_filename(text):
    return re.sub(r"[^\w\u4e00-\u9fff-]+", "_", str(text))[:40].strip("_") or "cover"
