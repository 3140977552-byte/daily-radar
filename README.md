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

## AI 中文点评（这是付费理由所在）

精选的 8 条会多一句中文点评，告诉你“这条值不值得点开”。没有这句，日报就只是搬运；有了这句，才是替读者做判断。

- 一次请求搞定全部精选，**约 1000 tokens/期**，DeepSeek 按这个量一个月不到 1 块钱。
- 没配 key、网络失败、模型乱输出，都只记一条告警，日报照常生成——**AI 挂了不会导致停更**。
- 想关掉：`config.json` 里把 `ai.enabled` 设为 `false`。
- 想换模型：改 `ai.base_url` / `ai.model`（任何 OpenAI 兼容接口都行）。

**API key 绝对不要写进 `config.json`**，仓库是公开的。正确做法：

- 本地：`export RADAR_API_KEY=sk-xxx`（或写进 `~/.config/daily-radar/env`）
- 线上：仓库 **Settings → Secrets and variables → Actions → New repository secret**，名字填 `RADAR_API_KEY`

工作流里已经用 `${{ secrets.RADAR_API_KEY }}` 注入，key 不会出现在日志里。

## 相关性闸门

泛资讯源（如 Hacker News 首页）默认开启 `require_keyword`：**没命中任何赛道关键词的条目直接丢弃**，不管它热度多高。否则「某学校禁手机提高成绩」这种高赞但无关的内容会挤进精选。

如果你希望某个源不做过滤，去掉它配置里的 `require_keyword` 即可。

## 双层产出：免费版公开、付费版只在本机

| 层 | 位置 | 内容 |
| --- | --- | --- |
| 免费 | `output/`（会推到公开仓库） | 5 条精选 · 其中 2 条带点评 · 每频道 3 条 |
| 付费 | `paid/`（**已 git 忽略，永不上传**） | 9–10 条精选全带点评 · 每频道最多 10 条 · 周报 |

关键设计：**付费内容永远不会进公开仓库**。`paid/` 写在 `.gitignore` 里，公开的归档 JSON 也会被自动剥掉 `take` 字段（点评是付费资产，不能跟着数据一起漏出去）。CI 只跑 `--tier free`，所以线上永远只有免费版。

```bash
python3 -m radar                 # 免费版 + 付费版
python3 -m radar --tier free     # 只出公开版（CI 用这个）
python3 -m radar --weekly        # 额外生成周报到 paid/
```

## 小红书发布包

```bash
python3 -m radar --publish-only    # 只出小红书稿，不动网站
python3 -m radar --publish         # 出稿 + 更新网站/归档
```

产物只有一个文件：`发布包/YYYY-MM-DD/小红书.md`（已 git 忽略），含标题、300–450 字正文、5 个标签、封面文案。一次调用约 1200 tokens。

### 每天自动出稿

已安装 launchd 定时任务 `com.libokai.dailyradar.xhs`，每天 **09:30** 生成到 `发布包/<日期>/`。

```bash
launchctl list | grep dailyradar                      # 查看是否在跑
launchctl kickstart -k gui/$(id -u)/com.libokai.dailyradar.xhs  # 立刻跑一次
tail -f 发布包/run.log                                # 看日志
```

注意：电脑睡眠时任务不会跑，唤醒后会补跑；API key 从 `~/.config/daily-radar/env` 读取，不经过仓库。

## 每天 30 秒的发布流程

1. 本机跑 `python3 -m radar --weekly`
2. 打开 `paid/latest.md`，全选复制，粘进你的付费渠道（小报童 / 知识星球 / 邮件）
3. 周日下午再发一次 `paid/latest-weekly.md`

免费版网页由 GitHub Actions 每天自动更新，你不用管。**你每天唯一的人工动作，是把付费版粘出去**——这也是目前唯一必须由你亲自做的事。

周报里的「本周观察」是 LLM 根据一周的条目自己写的趋势判断，不是拼凑标题。单日情报谁都能抄，一周的判断力抄不走，这就是付费层的护城河。

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
├── config.json              # 唯一的业务配置（含 tiers / ai）
├── radar/
│   ├── __main__.py          # python3 -m radar
│   ├── cli.py               # 命令行入口（--tier / --weekly）
│   ├── config.py            # 配置加载 / 默认值
│   ├── pipeline.py          # 采集→去重→打分→排序→精选
│   ├── commentary.py        # LLM 中文点评
│   ├── weekly.py            # 周报汇总 + 趋势观察
│   ├── publish.py           # 小红书发布包
│   ├── render.py            # Markdown / HTML / 归档页（支持分层）
│   ├── sources.py           # 数据源适配器（含通用 RSS/Atom）
│   └── util.py              # HTTP / 时间 / 文本工具
├── output/                  # 免费版产物（会被 Actions 提交并部署）
├── paid/                    # 付费版产物（git 忽略，只在本机）
├── 发布包/                  # 小红书成稿（git 忽略，只在本机）
├── scripts/daily-xhs.sh     # launchd 调用的出稿脚本
└── .github/workflows/daily.yml
```
