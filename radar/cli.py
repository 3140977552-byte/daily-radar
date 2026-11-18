"""命令行入口。

用法：
  python3 -m radar                  # 免费版写 output/，付费版写 paid/
  python3 -m radar --tier free      # 只出公开版（CI 用这个）
  python3 -m radar --weekly         # 额外生成周报
"""
import argparse
import json
import os
import sys

from . import config as config_module
from . import publish as publish_module
from . import weekly as weekly_module
from .commentary import enrich
from .pipeline import build
from .render import render_html, render_index, render_markdown

PAID_DIRNAME = "paid"


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def sanitize(report):
    """公开归档里去掉点评：点评是付费内容，不能跟着 JSON 一起进公开仓库。"""
    payload = dict(report)
    for key in ("items", "picks"):
        payload[key] = [{k: v for k, v in item.items() if k != "take"} for item in report.get(key) or []]
    return payload


def load_archive(data_dir):
    entries = []
    if not os.path.isdir(data_dir):
        return entries
    for name in sorted(os.listdir(data_dir), reverse=True):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(data_dir, name), "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            entries.append((payload.get("date") or name[:-5], len(payload.get("items") or []), "%s.html" % name[:-5]))
        except Exception:  # noqa: BLE001 - 归档损坏不影响当天产出
            continue
    return entries


def write_free(report, config, out_dir):
    markdown = render_markdown(report, config, "free")
    page = render_html(report, config, "free")
    date = report["date"]
    paths = [
        os.path.join(out_dir, "latest.md"),
        os.path.join(out_dir, "%s.md" % date),
        os.path.join(out_dir, "latest.html"),
        os.path.join(out_dir, "%s.html" % date),
        os.path.join(out_dir, "data", "%s.json" % date),
    ]
    write(paths[0], markdown)
    write(paths[1], markdown)
    write(paths[2], page)
    write(paths[3], page)
    write(paths[4], json.dumps(sanitize(report), ensure_ascii=False, indent=2, default=str))
    index_path = os.path.join(out_dir, "index.html")
    write(index_path, render_index(load_archive(os.path.join(out_dir, "data")), config))
    return paths + [index_path]


def write_paid(report, config, paid_dir):
    markdown = render_markdown(report, config, "paid")
    page = render_html(report, config, "paid", with_archive=False)
    date = report["date"]
    paths = [
        os.path.join(paid_dir, "latest.md"),
        os.path.join(paid_dir, "latest.html"),
        os.path.join(paid_dir, "%s.md" % date),
        os.path.join(paid_dir, "%s.html" % date),
    ]
    write(paths[0], markdown)
    write(paths[1], page)
    write(paths[2], markdown)
    write(paths[3], page)
    return paths


def write_weekly(config, data_dir, paid_dir):
    ai = config.get("ai") or {}
    api_key = os.environ.get(ai.get("api_key_env") or "RADAR_API_KEY")
    weekly = weekly_module.build(config, data_dir, 7, api_key)
    name = "weekly-%s" % weekly["week"]
    paths = [
        os.path.join(paid_dir, "%s.md" % name),
        os.path.join(paid_dir, "%s.html" % name),
        os.path.join(paid_dir, "latest-weekly.md"),
        os.path.join(paid_dir, "latest-weekly.html"),
    ]
    write(paths[0], weekly_module.render_markdown(weekly, config))
    write(paths[1], weekly_module.render_html(weekly, config))
    write(paths[2], weekly_module.render_markdown(weekly, config))
    write(paths[3], weekly_module.render_html(weekly, config))
    return weekly, paths


def main(argv=None):
    parser = argparse.ArgumentParser(prog="radar", description="生成每日情报日报")
    parser.add_argument("--config", default="config.json", help="配置文件路径（默认 config.json）")
    parser.add_argument("--tier", choices=["free", "paid", "both"], default="both", help="产出哪一层（默认 both）")
    parser.add_argument("--weekly", action="store_true", help="额外生成周报（写入 paid/）")
    parser.add_argument("--publish", action="store_true", help="额外生成小红书发布包（写入 发布包/）")
    parser.add_argument("--publish-only", action="store_true", help="只生成小红书发布包，不写网站和归档")
    parser.add_argument("--quiet", action="store_true", help="只输出结果路径")
    args = parser.parse_args(argv)

    config = config_module.load(args.config)
    report = enrich(build(config), config)

    if not report["items"]:
        print("没有采集到任何条目，检查网络或数据源配置。", file=sys.stderr)
        for err in report["errors"]:
            print("  - " + err, file=sys.stderr)
        return 1

    out_dir = config_module.output_dir(config)
    paid_dir = os.path.join(config_module.ROOT, PAID_DIRNAME)
    written = []

    if not args.publish_only:
        if args.tier in ("free", "both"):
            written += write_free(report, config, out_dir)
        if args.tier in ("paid", "both"):
            written += write_paid(report, config, paid_dir)

    weekly = None
    if args.weekly and not args.publish_only:
        weekly, weekly_paths = write_weekly(config, os.path.join(out_dir, "data"), paid_dir)
        written += weekly_paths

    publish_error = ""
    if args.publish or args.publish_only:
        ai = config.get("ai") or {}
        api_key = os.environ.get(ai.get("api_key_env") or "RADAR_API_KEY")
        try:
            bundle = publish_module.build_bundle(report, config, api_key)
            if bundle:
                written += publish_module.write_bundle(
                    bundle, report, os.path.join(config_module.ROOT, "发布包", report["date"])
                )
            else:
                publish_error = "未配置 AI，跳过发布包"
        except Exception as exc:  # noqa: BLE001 - 发布包失败不影响日报
            publish_error = "发布包生成失败：%s" % exc

    if args.quiet:
        for path in written:
            print(path)
        return 0

    print("日期: %s" % report["date"])
    print("采集: " + " · ".join("%s %d 条" % (k, v) for k, v in report["stats"].items()))
    print("收录: %d 条（去重后）" % len(report["items"]))
    ai = report.get("ai")
    if ai:
        print(
            "AI 点评: %s · 覆盖 %d 条 · 用量 %s tokens"
            % (ai.get("model"), ai.get("applied", 0), (ai.get("usage") or {}).get("total_tokens", "-"))
        )
    if weekly:
        print("周报: %s · %d 天 / %d 条%s" % (weekly["range"], weekly["days"], len(weekly["items"]), "（含 AI 观察）" if weekly["observation"] else ""))
    if publish_error:
        print(publish_error)
    if report["errors"]:
        print("告警:")
        for err in report["errors"]:
            print("  - " + err)
    print("生成:")
    for path in written:
        print("  " + os.path.relpath(path, config_module.ROOT))
    print("")
    print("今日精选:")
    for item in (report.get("picks") or [])[:12]:
        print("  %.1f  %s" % (item["score"], item["title"][:68]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
