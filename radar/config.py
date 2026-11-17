"""配置加载与默认值合并。"""
import copy
import json
import os

DEFAULTS = {
    "title": "每日情报雷达",
    "subtitle": "",
    "timezone_offset_hours": 8,
    "keywords": {},
    "scoring": {
        "keyword_title_multiplier": 2.0,
        "half_life_hours": 36,
        "freshness_bonus": 2.0,
        "signal_weight": 0.6,
    },
    "sources": {},
    "output": {
        "dir": "output",
        "top_n": 8,
        "per_section": 6,
        "max_summary_chars": 180,
    },
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def deep_merge(base, override):
    """override 覆盖 base，字典递归合并，列表整体替换。"""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load(path):
    if not os.path.isabs(path):
        path = os.path.join(ROOT, path)
    if not os.path.exists(path):
        return copy.deepcopy(DEFAULTS)
    with open(path, "r", encoding="utf-8") as handle:
        user_config = json.load(handle)
    return deep_merge(DEFAULTS, user_config)


def output_dir(config):
    out = config["output"]["dir"]
    if not os.path.isabs(out):
        out = os.path.join(ROOT, out)
    return out
