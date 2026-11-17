"""命令行入口：python3 -m radar [--config config.json]"""
import argparse
import json
import os
import sys

from . import config as config_module
from .pipeline import build
from .render import render_html, render_index, render_markdown


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def load_archive(data_dir):
    entries = []
    if not os.path.isdir(data_dir):
        return entries
    for name in sorted(os.listdir(data_dir), reverse=True):
        if not name.endswith(".json"):
            continue
        path = os.path.join(data_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            entries.append((payload.get("date") or name[:-5], len(payload.get("items") or []), "%s.html" % name[:-5]))
        except Exception:  # noqa: BLE001 - 归档损坏不影响当天产出
            continue
    return entries


def main(argv=None):
    parser = argparse.ArgumentParser(prog="radar", description="生成每日情报日报")
    parser.add_argument("--config", default="config.json", help="配置文件路径（默认 config.json）")
    parser.add_argument("--quiet", action="store_true", help="只输出结果路径")
    args = parser.parse_args(argv)

    config = config_module.load(args.config)
    report = build(config)

    if not report["items"]:
        print("没有采集到任何条目，检查网络或数据源配置。", file=sys.stderr)
        for err in report["errors"]:
            print("  - " + err, file=sys.stderr)
        return 1

    out = config_module.output_dir(config)
    data_dir = os.path.join(out, "data")
    date = report["date"]
    markdown_path = os.path.join(out, "latest.md")
    html_path = os.path.join(out, "latest.html")
    dated_md = os.path.join(out, "%s.md" % date)
    dated_html = os.path.join(out, "%s.html" % date)
    json_path = os.path.join(data_dir, "%s.json" % date)

    markdown = render_markdown(report, config)
    page = render_html(report, config)
    write(markdown_path, markdown)
    write(dated_md, markdown)
    write(html_path, page)
    write(dated_html, page)
    write(json_path, json.dumps(report, ensure_ascii=False, indent=2, default=str))
    write(os.path.join(out, "index.html"), render_index(load_archive(data_dir), config))

    if args.quiet:
        print(html_path)
        return 0

    print("日期: %s" % date)
    print("采集: " + " · ".join("%s %d 条" % (k, v) for k, v in report["stats"].items()))
    print("收录: %d 条（去重后）" % len(report["items"]))
    if report["errors"]:
        print("告警:")
        for err in report["errors"]:
            print("  - " + err)
    print("生成:")
    for path in (html_path, markdown_path, json_path, os.path.join(out, "index.html")):
        print("  " + os.path.relpath(path, config_module.ROOT))
    print("")
    print("今日精选:")
    for item in report.get("picks") or report["items"][: int(config["output"]["top_n"])]:
        print("  %.1f  %s" % (item["score"], item["title"][:70]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
