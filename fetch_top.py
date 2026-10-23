#!/usr/bin/env python3
"""抓取过去 N 小时 X 中文区（美股/财经/AI/财富自由/个人成长）浏览量 Top10 和互动量 Top10。

用法：python3 fetch_top.py [--date YYYY-MM-DD] [--dry-run]
产出：data/<date>/raw.json, data/<date>/top.json, data/<date>/top.md
依赖：opencli + 本目录 opencli-plugin（命令 `opencli xhot search`），Chrome 里 X 已登录。
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = dict(os.environ, PATH=f"{Path.home()}/.local/node/bin:{Path.home()}/.local/bin:" + os.environ.get("PATH", ""))


def chunks(items, n):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def run_search(query, limit):
    cmd = ["opencli", "xhot", "search", query, "--limit", str(limit), "-f", "json"]
    for attempt in range(2):
        proc = subprocess.run(cmd, capture_output=True, text=True, env=ENV, timeout=240)
        out = proc.stdout.strip()
        if proc.returncode == 0 and out.startswith("["):
            return json.loads(out)
        err = (proc.stderr or out)[-400:]
        print(f"  ! 第{attempt + 1}次失败: {err.strip()}", file=sys.stderr)
        time.sleep(8)
    return []


def engagement(t):
    # 指令包口径：点赞 + 回复 + 转发（收藏、引用另列）
    return t["likes"] + t["replies"] + t["retweets"]


def top_by(rows, key, n, per_author):
    picked, count = [], {}
    for t in sorted(rows, key=key, reverse=True):
        a = t["author"].lower()
        if count.get(a, 0) >= per_author:
            continue
        count[a] = count.get(a, 0) + 1
        picked.append(t)
        if len(picked) == n:
            break
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true", help="只打印查询，不抓取")
    ap.add_argument("--reuse-raw", action="store_true", help="不重新抓取，用 raw.json 重新过滤排名")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text())
    out_dir = ROOT / "data" / args.date
    out_dir.mkdir(parents=True, exist_ok=True)

    since = int(time.time()) - cfg["window_hours"] * 3600
    suffix = f'{cfg["query_suffix"]} min_faves:{cfg["min_faves"]} since_time:{since}'
    queries = []
    for group, terms in cfg["groups"].items():
        for part in chunks(terms, cfg["terms_per_query"]):
            queries.append((group, f'({" OR ".join(part)}) {suffix}'))

    if args.dry_run:
        for g, q in queries:
            print(g, "|", q)
        return

    raw_path = out_dir / "raw.json"
    if args.reuse_raw:
        fetched = json.loads(raw_path.read_text())
        since = int(fetched[0].get("_since", 0)) if fetched else 0
    else:
        fetched = {}
        for i, (group, q) in enumerate(queries, 1):
            print(f"[{i}/{len(queries)}] {group}: {q[:60]}…", file=sys.stderr)
            for t in run_search(q, cfg["per_query_limit"]):
                if t["id"] in fetched:
                    fetched[t["id"]]["groups"] = sorted(set(fetched[t["id"]]["groups"]) | {group})
                else:
                    t["groups"], t["_since"] = [group], since
                    fetched[t["id"]] = t
            time.sleep(3)
        fetched = list(fetched.values())
        raw_path.write_text(json.dumps(fetched, ensure_ascii=False, indent=1))

    excluded = {a.lower() for a in cfg["exclude_authors"]}
    terms = [w.lower() for ws in cfg["groups"].values() for w in ws]
    blocked = cfg.get("blocklist", [])
    pool = {}
    for t in fetched:
        if t.get("lang") not in ("zh", "") or t["author"].lower() in excluded:
            continue
        if not any(w in t["text"].lower() for w in terms) or any(b in t["text"] for b in blocked):
            continue
        created = dt.datetime.strptime(t["created_at"], "%a %b %d %H:%M:%S %z %Y").timestamp()
        if created < since:
            continue
        t["views"] = int(t.get("views") or 0)
        t["engagement"] = engagement(t)
        t["url"] = f'https://x.com/{t["author"]}/status/{t["id"]}'
        pool[t["id"]] = t

    rows = list(pool.values())

    # 粗筛后多留候选，最终 Top10 由写稿环节剔除跑题/敏感帖后确定
    n, per = cfg["candidates_n"], cfg["max_per_author"]
    by_views = top_by(rows, lambda t: t["views"], n, per)
    by_eng = top_by(rows, lambda t: t["engagement"], n, per)
    result = {
        "date": args.date,
        "window_hours": cfg["window_hours"],
        "pool_size": len(rows),
        "queries": len(queries),
        "final_n": cfg["top_n"],
        "candidates_views": by_views,
        "candidates_engagement": by_eng,
    }
    (out_dir / "top.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))

    lines = [f"# X 中文区 Top 帖 {args.date}（过去 {cfg['window_hours']}h，候选池 {len(rows)} 条）", ""]
    for title, items in (("浏览量候选", by_views), ("互动量候选（赞+评+转）", by_eng)):
        lines += [f"## {title}", ""]
        for k, t in enumerate(items, 1):
            lines.append(f"{k}. @{t['author']} | 浏览 {t['views']:,} | 互动 {t['engagement']:,} "
                         f"(赞{t['likes']} 转{t['retweets']} 评{t['replies']} 引{t['quotes']} 藏{t['bookmarks']}) | {'/'.join(t['groups'])}")
            lines.append(f"   {t['url']}")
            lines.append("   " + t["text"].replace("\n", " ")[:160])
        lines.append("")
    (out_dir / "top.md").write_text("\n".join(lines))
    print(out_dir / "top.md")


if __name__ == "__main__":
    main()
