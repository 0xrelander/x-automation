#!/usr/bin/env python3
"""分析 followup.json：按评论类型、结尾形式、原帖大小、评论天数分组，看博主回复率和评论获赞。"""
import glob
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
fu = json.loads((ROOT / "followup.json").read_text())
items = [x for x in fu["items"] if x["found"]]

# 技术分析批次
ta_urls = {p["url"] for p in json.loads((ROOT / "data/2026-10-15-engage-plan-ta.json").read_text())}
ta_urls |= {p["url"] for p in json.loads((ROOT / "data/2026-10-16-engage-plan.json").read_text())[:4]}

# 原帖浏览量：从所有候选文件里查
views = {}
for f in glob.glob(str(ROOT / "data/*engage-cands*.json")):
    for t in json.loads(Path(f).read_text()):
        views[t["id"]] = max(views.get(t["id"], 0), int(t.get("views") or 0))


def bucket_views(v):
    if v >= 50000:
        return "原帖 ≥5 万浏览"
    if v >= 20000:
        return "原帖 2–5 万"
    return "原帖 <2 万"


groups = defaultdict(list)
for x in items:
    tid = x["target"].rstrip("/").split("/")[-1]
    x["ta"] = x["target"] in ta_urls
    x["question"] = x["reply"].rstrip().endswith(("？", "?"))
    x["views"] = views.get(tid, 0)
    groups["全部"].append(x)
    groups["技术分析" if x["ta"] else "普通话题"].append(x)
    groups["结尾提问" if x["question"] else "结尾不提问"].append(x)
    groups[bucket_views(x["views"])].append(x)
    groups[f"评论日期 {x['date']}"].append(x)


def stat(xs):
    n = len(xs)
    rep = sum(x["author_replied"] for x in xs)
    likes = sum(x["my_likes"] or 0 for x in xs)
    liked_any = sum(1 for x in xs if (x["my_likes"] or 0) > 0)
    others = sum(x["other_replies"] for x in xs)
    return n, rep, likes, liked_any, others


print(f"回访时间 {fu['checked_at']}，可读到的评论 {len(items)}/{len(fu['items'])}")
print(f"{'分组':<16}{'条数':>4}{'博主回复':>8}{'回复率':>8}{'评论总赞':>8}{'有赞的评论':>10}{'其他人回复':>10}")
order = ["全部", "技术分析", "普通话题", "结尾提问", "结尾不提问", "原帖 ≥5 万浏览", "原帖 2–5 万", "原帖 <2 万"] + sorted(k for k in groups if k.startswith("评论日期"))
for k in order:
    if k not in groups:
        continue
    n, rep, likes, liked_any, others = stat(groups[k])
    print(f"{k:<16}{n:>4}{rep:>8}{rep / n:>8.0%}{likes:>8}{liked_any:>10}{others:>10}")

print("\n博主回复了的：")
for x in items:
    if x["author_replied"]:
        print(f"- @{x['author']}（{'技术' if x['ta'] else '普通'}，原帖 {x['views']:,}）Elio 评论赞 {x['my_likes']}\n  Elio：{x['reply'][:60]}…\n  博主：{x['author_reply_text']}")

print("\n评论获赞最多的 8 条：")
for x in sorted(items, key=lambda x: -(x["my_likes"] or 0))[:8]:
    print(f"- {x['my_likes']} 赞 @{x['author']}（原帖 {x['views']:,}）{x['reply'][:50]}…")
