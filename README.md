# 独立开发情报 · daily-radar

零依赖、零费用的**自动日报引擎**，当前赛道：**跨境 / 独立开发者**（新品发布、SaaS 融资、工具与开源、Show HN）。

采集 → 去重 → 加权打分 → 输出网页 + Markdown。**GitHub Actions 免费每天跑，GitHub Pages 免费托管，没有服务器、没有月费、随时能停。**

## 快速开始

```bash
cd ~/Desktop/daily-radar
python3 -m radar
```

约 5 秒出报，只依赖 Python 3.9+ 标准库，**不用 pip install 任何东西**。

产物在 `output/`：

| 文件 | 用途 |
| --- | --- |
| `latest.html` | 网页版，双击打开或部署 |
| `latest.md` | 文字版，发公众号 / 邮件 / 群里 |
| `YYYY-MM-DD.html` / `.md` | 当期归档 |
| `data/YYYY-MM-DD.json` | 结构化数据，可单独卖给需要 API 的人 |
| `index.html` | 历史归档页 |

## 当前数据源

| 频道 | 来源 | 说明 |
| --- | --- | --- |
| 🆕 新品发布 | `producthunt.com/feed` | 每日新品（Atom） |
| 💰 融资动态 | TechCrunch Startups + Crunchbase News | 融资、估值、并购（RSS） |
| 🛠️ Show HN | `hnrss.org/show` | 独立开发者发布作品（RSS） |
| 🚀 工具与开源 | GitHub Search API | 近 7 天新建且涨星快的仓库 |
| 🔥 技术热点 | Hacker News 首页 | 热度信号 |

全部免费、无需 API key。单个源挂掉只会在文末出现一行告警，不会影响整期出报。

## 改配置就行，不用改代码

`config.json` 是唯一的业务开关：

- **`keywords`** — 赛道关键词和权重。英文词按“词首边界”匹配：`launch` 能命中 `launches`，但 `api` 不会误命中 `capital`。
- **`scoring`** — 打分参数。想要更看重新内容就把 `half_life_hours` 调小（如 12）。
- **`sources.<名字>`** — 每个频道一条：
  - `type` 选适配器（`feed` / `github` / `hackernews` / `arxiv`）
  - `label` 决定频道在日报里的名字
  - `weight` 频道基础权重
  - `max` 该频道最多取几条
  - `max_age_days` 超过几天直接丢弃，防止旧闻混进日报
  - `trim_markers` / `summary_drop_patterns` 清理 RSS 里的站内噪音
- **`output.pick_diversity`** — 今日精选里单个频道最多占几条（默认 2，避免整屏都是融资新闻）

打分公式（白盒，可解释）：

```
总分 = 频道权重
     + 标题关键词命中 × 倍数 + 摘要关键词命中
     + 时效奖励 × 0.5^(已过小时数 / 半衰期)
     + 热度信号 × ln(1 + 星标数或点赞数)
```

## 加一个新频道（不用写代码）

任何有 RSS / Atom 的站点，在 `config.json` 的 `sources` 里加一段即可：

```json
"microns": {
  "enabled": true,
  "type": "feed",
  "label": "微型创业",
  "url": "https://example.com/feed.xml",
  "weight": 1.0,
  "max": 6,
  "max_age_days": 3
}
```

一个频道可以合并多个源，用 `"urls": ["...", "..."]` 代替 `"url"`。

## 加一个需要自定义逻辑的源

在 `radar/sources.py` 里加函数：

```python
@register("mysource")
def fetch_mysource(settings, now):
    data = http_json("https://example.com/api")
    return [{"title": x["name"], "url": x["link"], "summary": x.get("desc", ""),
             "published": parse_time(x.get("time")), "metrics": {}, "tags": []}]
```

然后在 `config.json` 里用 `"type": "mysource"` 引用它。

## 部署成免费自动日报

1. GitHub 建一个仓库，把 `~/Desktop/daily-radar` 推上去（`main` 分支）。
2. 仓库 **Settings → Actions → General → Workflow permissions** 选 **Read and write**。
3. 仓库 **Settings → Pages → Source** 选 **GitHub Actions**。
4. 完成。`.github/workflows/daily.yml` 每天北京时间 09:00 自动出报并部署；也能在 Actions 页面点 **Run workflow** 手动跑。

上线后订阅地址：`https://<用户名>.github.io/<仓库名>/`，归档在 `index.html`。

> 如果你在仓库里配置了 `GITHUB_TOKEN` 环境变量，GitHub 数据源的限额会从 10 次/分提升到 30 次/分，CI 更稳。工作流已经自动传入。

## 变现思路（针对这个赛道）

1. **卖订阅** — 免费版发公开页，付费版给完整版（更多频道、附中文点评、每周复盘）。9.9–39/月，走知识星球 / 小报童 / 邮件。
2. **卖数据** — `data/*.json` 是结构化情报，适合投研、选品、招聘方按年买接口。
3. **做流量入口** — 日报免费，导流到你的付费社群、课程或工具。
4. **企业定制** — 同一套引擎给公司跑「竞品动态 / 新工具监控」内部日报，收实施费 + 维护费。

技术已经解决，真正的门槛是**每天坚持发**和**选对一个有人愿意付钱的切入角度**。

## 目录结构

```
daily-radar/
├── config.json              # 唯一的业务配置
├── radar/
│   ├── __main__.py          # python3 -m radar
│   ├── cli.py               # 命令行入口
│   ├── config.py            # 配置加载 / 默认值
│   ├── pipeline.py          # 采集→去重→打分→排序→精选
│   ├── render.py            # Markdown / HTML / 归档页
│   ├── sources.py           # 数据源适配器（含通用 RSS/Atom）
│   └── util.py              # HTTP / 时间 / 文本工具
├── output/                  # 产物（会被 Actions 提交并部署）
└── .github/workflows/daily.yml
```
