#!/usr/bin/env python3
"""按间隔对一组帖子依次点赞 + 评论，每条前核对登录账号、查是否已评论过，发后核实，结果写进 engagement.json。

用法：python3 engage_queue.py [--account <用户名>] plan.json
账号默认读 config.local.json 的 account（不进仓库）。
每两条之间随机等 1–20 分钟（10-21 用户定的规矩，不要连续操作）；--gap-lo/--gap-hi 可调。
plan.json: [{"url": "...", "reply": "...", 其余标签见 style/openbit_reply.md 第 9 节}]
只执行用户在对话里确认过的计划；评论失败或核实不到就停，不重试（避免重复评论）。
发前四道门（config.json）：reply_daily_cap 日顶（含今天已发的）、author_cooldown_days 同博主冷却、active_hours 作息门、batch_gap_min 跨批最小间隔。
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

CFG = json.loads((ROOT / "config.json").read_text())
LOCAL = json.loads((ROOT / "config.local.json").read_text()) if (ROOT / "config.local.json").exists() else {}


def my_reply_exists(account, tweet_url, text):
    tid = tweet_url.rstrip("/").split("/")[-1]
    rows = opencli("twitter", "thread", tid)
    strip = lambda s: re.sub(r"^(@\w+\s*)+", "", s or "")
    return [r for r in rows if r.get("author", "").lower() == account.lower() and norm(strip(r.get("text"))) == norm(text)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default=LOCAL.get("account"))
    ap.add_argument("--dry-run", action="store_true", help="只过四道门和账号核对，逐条打印要发什么，不点赞不评论")
    ap.add_argument("--gap-lo", type=float, default=1)
    ap.add_argument("--gap-hi", type=float, default=20)
    ap.add_argument("plan")
    a = ap.parse_args()
    if not a.account:
        log("STOP 没有账号：传 --account 或在 config.local.json 写 account")
        sys.exit(1)
    plan = json.loads(Path(a.plan).read_text())
    out_p = ROOT / "engagement.json"
    done = json.loads(out_p.read_text()) if out_p.exists() else []
    today = dt.date.today().isoformat()
    cap = CFG.get("reply_daily_cap", 5)
    sent_today = [e for e in done if e["date"] == today and e.get("account") == a.account]
    if len(sent_today) + len(plan) > cap:
        log(f"STOP 今天已发 {len(sent_today)} 条，计划 {len(plan)} 条，超过日顶 {cap}。砍计划再来")
        sys.exit(4)
    lo, hi = CFG.get("active_hours", [6, 23])
    if not lo <= dt.datetime.now().hour < hi:
        log(f"STOP 现在 {dt.datetime.now():%H:%M}，不在作息时段 {lo:02d}:00–{hi:02d}:00")
        sys.exit(5)
    if sent_today:
        last = dt.datetime.strptime(f"{today} {sent_today[-1]['time']}", "%Y-%m-%d %H:%M")
        gap = CFG.get("batch_gap_min", 15)
        if dt.datetime.now() - last < dt.timedelta(minutes=gap):
            log(f"STOP 上一批 {sent_today[-1]['time']} 刚发过，跨批至少隔 {gap} 分钟")
            sys.exit(6)
    cool = CFG.get("author_cooldown_days", 7)
    recent_authors = {e["target"].split("/")[3].lower() for e in done
                      if (dt.date.today() - dt.date.fromisoformat(e["date"])).days < cool}

    if a.dry_run:
        who = opencli("twitter", "whoami")
        log(f"DRY-RUN 登录账号 {who[0].get('username') if who else '?'}（要求 {a.account}）；今天已发 {len(sent_today)}，日顶 {cap}，计划 {len(plan)} 条")
        for item in plan:
            au = item["url"].split("/")[3]
            log(f"  {'SKIP 冷却' if au.lower() in recent_authors else 'WOULD'} like+reply → @{au}  {item['reply'].splitlines()[0][:50]}… + {item.get('link', '')}")
        log("DRY-RUN 结束，没有发任何东西")
        return
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
        if url.split("/")[3].lower() in recent_authors:
            log(f"SKIP {url} 这位博主 {cool} 天内评过")
            continue
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
        tags = {k: v for k, v in item.items() if k not in ("url", "reply")}
        done.append({"date": dt.date.today().isoformat(), "time": dt.datetime.now().strftime("%H:%M"), "account": a.account,
                     "target": url, "liked": bool(like and like[0].get("status") == "success"), "reply": text,
                     "reply_url": r.get("url", ""), "verified_in_thread": verified, "standalone": standalone, **tags})
        recent_authors.add(url.split("/")[3].lower())
        out_p.write_text(json.dumps(done, ensure_ascii=False, indent=1))
        if not verified:
            log(f"STOP {url} {'评论被发成了独立帖 ' + r.get('url', '') if standalone else '核实不到评论'}，停止后续，等人工处理")
            sys.exit(3)
    log("DONE")


if __name__ == "__main__":
    main()
