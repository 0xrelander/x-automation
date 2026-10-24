# x-automation（OpenBit 版）

fork 自 Lina 的 elio-x-daily。给一个 X 账号做日更和赞评的半自动工作流：每一步发布前都要人工审阅确认，脚本只执行确认过的计划。账号写在 `config.local.json`（不进仓库）：`{"account": "<用户名>"}`。

赞评线现在是 OpenBit 的打法：在美股 / 聪明钱话题的高流量帖下面，补一个原帖没有的数（来自 openbit.trade 的个股页 / 人物页），末行带那一页的链接。写法见 `style/openbit_reply.md`。

依赖 [opencli](https://github.com/jackwener/opencli) 和本机 Chrome 里已经登录的 X 会话。

## 目录

| 文件 | 作用 |
|---|---|
| `RUNBOOK.md` | 每日抓热帖、拆爆点、写稿、审阅的执行手册 |
| `fetch_top.py` | 按 `config.json` 的关键词组抓取过去 24 小时中文区高浏览、高互动帖子 |
| `render_pack.py` / `render_review.py` | 生成审阅包和审阅页，检查相似度、Markdown 残留、红线词 |
| `post_queue.py` | 按间隔发布确认过的帖子：先核对登录账号、查重，发后去主页核实 |
| `daily_targets.py` | **每天选账号**：按关键词组搜最近 N 小时中英文高流量帖，识别帖里提到的、OpenBit 有页面的标的 / 人物，按 浏览增速 × 新鲜 × 能补数 打分，每位作者留一条，出 `data/<日期>/候选.md` |
| `ob_facts.py` | 抓 openbit.trade 个股页 / 人物页上可引用的事实（研究摘要、驱动、来源说法、持有人申报、国会交易），存 `data/<日期>/ob/`；回复里每个数都要能在这里找到原句 |
| `find_engage_targets.py` | Lina 原版找目标脚本（中文、不识别标的），留作对照 |
| `engage_queue.py` | 按计划点赞并评论：每条之间随机等待，发前核对账号，发后核实评论挂在原帖下面；发成独立帖或核实不到就停。四道门：日顶 `reply_daily_cap`、同博主冷却 `author_cooldown_days`、作息门 `active_hours`、跨批间隔 `batch_gap_min` |
| `followup.py` / `analyze_followup.py` | 回访评论所在的楼，统计浏览和互动 |
| `opencli-plugin/` | 自建 opencli 插件 `xhot search`，返回带浏览量、收藏等完整互动数据的搜索结果 |
| `style/` | 写作规范：`openbit_reply.md`（回复写法 v2，在 Lina 版上改，带【留 / 改 / 新】标记）、`elio_voice.md`（Lina 原版，当对照）、`humanizer_zh.md`（去 AI 味清单） |
| `charts/` | 配图脚本 |

## 常用命令

```bash
# 1 每天选账号：最近 30 小时的候选，出 data/<日期>/候选.md
python3 daily_targets.py --hours 30

# 2 抓要引用的数（标的代码 / 人物 slug）
python3 ob_facts.py NVDA TSLA pelosi

# 3 按 style/openbit_reply.md 写 data/<日期>/plan.json（≤ reply_daily_cap 条），人工勾过再发

# 4 执行确认过的赞评计划，每条之间随机等 1–20 分钟
python3 engage_queue.py data/<日期>/plan.json

# 5 回访（+2h、+24h 各一次）
python3 followup.py && python3 analyze_followup.py

# 日更线（Lina 原流程，RUNBOOK.md）
python3 post_queue.py --account <用户名> --first-delay-min 0 --gap-min 31 data/<日期>/q1.txt
```

赞评计划格式：`[{"url": "https://x.com/<user>/status/<id>", "reply": "评论正文", ...第 9 节的标签}]`

## 不进仓库的内容

`data/`、`history/`、`review/` 和各类运行记录（`engagement.json`、`published.json` 等）都在 `.gitignore` 里，只保存在本机。
