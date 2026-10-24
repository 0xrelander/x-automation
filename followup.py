#!/usr/bin/env python3
"""回访：逐条读自己评论所在的楼，统计博主是否回复、评论获赞、其他人回复数，写入 followup.json。

用法：python3 followup.py
"""
import datetime as dt
import json
import time
from pathlib import Path

from post_queue import ROOT, log, opencli

LOCAL = json.loads((ROOT / "config.local.json").read_text()) if (ROOT / "config.local.json").exists() else {}
ACCOUNT = LOCAL.get("account", "")


def main():
    eng = json.loads((ROOT / "engagement.json").read_text())
    out = []
    for i, e in enumerate(eng, 1):
        target_author = e["target"].split("/")[3]
        rid = e.get("reply_url", "").rstrip("/").split("/")[-1]
        rec = {"target": e["target"], "author": target_author, "reply_url": e.get("reply_url"), "date": e["date"],
               "reply": e["reply"], "found": False, "my_likes": None, "author_replied": False,
               "author_reply_text": None, "other_replies": 0}
        if rid:
            rows = opencli("twitter", "thread", rid, "--limit", "100")
            idx = next((k for k, r in enumerate(rows) if r.get("id") == rid), None)
            if idx is not None:
                rec["found"] = True
                rec["my_likes"] = rows[idx].get("likes", 0)
                below = rows[idx + 1:]
                mine_author = [r for r in below if r.get("author", "").lower() == target_author.lower()]
                rec["author_replied"] = bool(mine_author)
                rec["author_reply_text"] = mine_author[0]["text"][:200] if mine_author else None
                rec["other_replies"] = sum(1 for r in below if r.get("author", "").lower() not in (target_author.lower(), ACCOUNT.lower()))
        out.append(rec)
        log(f"[{i}/{len(eng)}] @{target_author} found={rec['found']} likes={rec['my_likes']} author_replied={rec['author_replied']} others={rec['other_replies']}")
        time.sleep(3)
    (ROOT / "followup.json").write_text(json.dumps({"checked_at": dt.datetime.now().isoformat(timespec="minutes"), "items": out}, ensure_ascii=False, indent=1))
    log("DONE")


if __name__ == "__main__":
    main()
