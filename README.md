# elio-x-daily

给 X 账号 @ElioCUIsg 做内容和互动的半自动工作流。每一步发布前都要人工审阅确认，脚本只执行确认过的计划。

依赖 [opencli](https://github.com/jackwener/opencli) 和本机 Chrome 里已经登录的 X 会话。

## 目录

| 文件 | 作用 |
|---|---|
| `RUNBOOK.md` | 每日抓热帖、拆爆点、写稿、审阅的执行手册 |
| `fetch_top.py` | 按 `config.json` 的关键词组抓取过去 24 小时中文区高浏览、高互动帖子 |
| `render_pack.py` / `render_review.py` | 生成审阅包和审阅页，检查相似度、Markdown 残留、红线词 |
| `post_queue.py` | 按间隔发布确认过的帖子：先核对登录账号、查重，发后去主页核实 |
| `find_engage_targets.py` | 找最近 N 小时适合赞评的帖子，排除自家号和已经互动过的作者 |
| `engage_queue.py` | 按计划点赞并评论：每条之间随机等待，发前核对账号，发后核实评论挂在原帖下面；发成独立帖或核实不到就停 |
| `followup.py` / `analyze_followup.py` | 回访评论所在的楼，统计浏览和互动 |
| `opencli-plugin/` | 自建 opencli 插件 `xhot search`，返回带浏览量、收藏等完整互动数据的搜索结果 |
| `style/` | 写作规范：`openbit_reply.md`（回复写法 v2，在 Lina 版上改，带【留 / 改 / 新】标记）、`elio_voice.md`（Lina 原版，当对照）、`humanizer_zh.md`（去 AI 味清单） |
| `charts/` | 配图脚本 |

## 常用命令

```bash
# 找赞评目标
python3 find_engage_targets.py --hours 6 --out data/<日期>-engage-cands.json

# 执行确认过的赞评计划，每条之间随机等 1–10 分钟
python3 engage_queue.py --account ElioCUIsg --gap-lo 1 --gap-hi 10 data/<日期>-engage-plan.json

# 发布确认过的帖子，每篇间隔 31 分钟
python3 post_queue.py --account ElioCUIsg --first-delay-min 0 --gap-min 31 data/<日期>/q1.txt
```

赞评计划格式：`[{"url": "https://x.com/<user>/status/<id>", "reply": "评论正文"}]`

## 不进仓库的内容

`data/`、`history/`、`review/` 和各类运行记录（`engagement.json`、`published.json` 等）都在 `.gitignore` 里，只保存在本机。
