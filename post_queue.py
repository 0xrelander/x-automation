#!/usr/bin/env python3
"""按间隔依次发帖，每条发前查重、发后去主页核实，结果追加到 published.json。

用法：python3 post_queue.py --account ElioCUIsg --gap-min 30 --first-delay-min 30 file1.txt file2.txt ...
只发用户在对话里确认过的稿子；任何一条失败或核实不到就停，不重试（避免重复发帖）。
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
ENV = dict(os.environ, PATH=f"{Path.home()}/.local/node/bin:" + os.environ.get("PATH", ""))


def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def opencli(*args, timeout=300):
    p = subprocess.run(["opencli", *args, "-f", "json"], capture_output=True, text=True, env=ENV, timeout=timeout)
    out = p.stdout.strip()
    starts = [i for i in (out.find("["), out.find("{")) if i >= 0]
    if not starts:
        return []
    data = json.loads(out[min(starts):])
    return data if isinstance(data, list) else [data]


def recent(account):
    return opencli("twitter", "tweets", account, "--limit", "5")


def norm(s):
    return "".join(s.split())[:60]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--gap-min", type=float, default=30)
    ap.add_argument("--first-delay-min", type=float, default=0)
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()

    if a.first_delay_min:
        log(f"等待 {a.first_delay_min} 分钟后发第一条")
        time.sleep(a.first_delay_min * 60)
    for i, f in enumerate(a.files):
        if i:
            log(f"等待 {a.gap_min} 分钟")
            time.sleep(a.gap_min * 60)
        text = Path(f).read_text()
        who = opencli("twitter", "whoami")
        if not who or who[0].get("username") != a.account:
            log(f"STOP 当前登录账号不是 {a.account}：{who}")
            sys.exit(1)
        if any(norm(t["text"]) == norm(text) for t in recent(a.account)):
            log(f"SKIP {f} 主页上已经有这条，不重复发")
            continue
        res = opencli("twitter", "post", text)
        r = res[0] if res else {}
        log(f"POST {f} -> {r.get('status')} {r.get('message')} {r.get('url', '')}")
        time.sleep(20)
        found = [t for t in recent(a.account) if norm(t["text"]) == norm(text)]
        if not found:
            log(f"STOP {f} 主页上核实不到，停止后续发布（不重试，避免重复）")
            sys.exit(2)
        t = found[0]
        url = f"https://x.com/{a.account}/status/{t['id']}"
        log(f"VERIFIED {f} {url} copies={len(found)}")
        p = ROOT / "published.json"
        logs = json.loads(p.read_text()) if p.exists() else []
        logs.append({"date": dt.date.today().isoformat(), "posted_at_utc": t["created_at"], "account": a.account,
                     "tweet_id": t["id"], "url": url, "file": f, "publisher": "post_queue.py", "verified_on_profile": True})
        p.write_text(json.dumps(logs, ensure_ascii=False, indent=1))
    log("DONE")


if __name__ == "__main__":
    main()
