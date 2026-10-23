#!/usr/bin/env python3
"""按间隔对一组帖子依次点赞 + 评论，每条前核对登录账号、查是否已评论过，发后核实，结果写进 engagement.json。

用法：python3 engage_queue.py --account ElioCUIsg plan.json
每两条之间随机等 1–20 分钟（10-21 用户定的规矩，不要连续操作）；--gap-lo/--gap-hi 可调。
plan.json: [{"url": "...", "reply": "..."}]
只执行用户在对话里确认过的计划；评论失败或核实不到就停，不重试（避免重复评论）。
"""
import argparse
import datetime as dt
import json
import random
import re
import sys
import time
from pathlib import Path

from post_queue import ROOT, log, norm, opencli


def my_reply_exists(account, tweet_url, text):
    tid = tweet_url.rstrip("/").split("/")[-1]
    rows = opencli("twitter", "thread", tid)
    strip = lambda s: re.sub(r"^(@\w+\s*)+", "", s or "")
    return [r for r in rows if r.get("author", "").lower() == account.lower() and norm(strip(r.get("text"))) == norm(text)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--gap-lo", type=float, default=1)
    ap.add_argument("--gap-hi", type=float, default=20)
    ap.add_argument("plan")
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    out_p = ROOT / "engagement.json"
    done = json.loads(out_p.read_text()) if out_p.exists() else []

    for i, item in enumerate(plan):
        if i:
            wait = random.uniform(a.gap_lo * 60, a.gap_hi * 60)
            log(f"等待 {wait // 60:.0f} 分 {wait % 60:.0f} 秒")
            time.sleep(wait)
        who = opencli("twitter", "whoami")
        if not who or who[0].get("username") != a.account:
            log(f"STOP 当前登录账号不是 {a.account}：{who}")
            sys.exit(1)
        url, text = item["url"], item["reply"]
        if my_reply_exists(a.account, url, text):
            log(f"SKIP {url} 已经评论过")
            continue
        like = opencli("twitter", "like", url)
        log(f"LIKE {url} -> {like[0].get('status') if like else '?'} {like[0].get('message') if like else ''}")
        res = opencli("twitter", "reply", url, text)
        r = res[0] if res else {}
        log(f"REPLY {url} -> {r.get('status')} {r.get('message')} {r.get('url', '')}")
        time.sleep(15)
        found = my_reply_exists(a.account, url, text)
        if not found and r.get("status") != "success":
            log(f"STOP {url} 评论失败且核实不到，停止后续（不重试）")
            sys.exit(2)
        verified = bool(found)
        log(f"{'VERIFIED' if verified else 'UNVERIFIED(命令成功但楼里没读到)'} {url} copies={len(found)}")
        standalone = False
        if not verified and r.get("url"):
            # 10-20 出过事：reply 命令报成功，实际发成了独立帖。读评论自己的楼，第一条是自己就说明没有挂在原帖下
            rows = opencli("twitter", "thread", r["url"].rstrip("/").split("/")[-1])
            standalone = bool(rows) and rows[0].get("author", "").lower() == a.account.lower()
        done.append({"date": dt.date.today().isoformat(), "time": dt.datetime.now().strftime("%H:%M"), "account": a.account,
                     "target": url, "liked": bool(like and like[0].get("status") == "success"), "reply": text,
                     "reply_url": r.get("url", ""), "verified_in_thread": verified, "standalone": standalone})
        out_p.write_text(json.dumps(done, ensure_ascii=False, indent=1))
        if not verified:
            log(f"STOP {url} {'评论被发成了独立帖 ' + r.get('url', '') if standalone else '核实不到评论'}，停止后续，等人工处理")
            sys.exit(3)
    log("DONE")


if __name__ == "__main__":
    main()
