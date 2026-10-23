#!/usr/bin/env python3
"""搜过去 N 小时美股/AI/港股/财富自由的中文高流量帖，排除自家账号和已互动过的作者，按浏览排序输出候选。

用法：python3 find_engage_targets.py --hours 15 --out <cands.json>
"""
import argparse
import datetime as dt
import json
import time
from pathlib import Path

from post_queue import ROOT, log, opencli

GROUPS = {
    "美股": "(美股 OR 纳指 OR 标普 OR 英伟达 OR 特斯拉 OR 财报 OR 美联储 OR 降息 OR NVDA OR TSLA OR 巴菲特)",
    "AI": "(AI OR OpenAI OR Claude OR 大模型 OR 算力 OR 黄仁勋 OR Anthropic)",
    "港股": "(港股 OR 恒指 OR 恒生 OR 腾讯 OR 阿里 OR 小米 OR 港交所)",
    "财富自由": "(财富自由 OR 被动收入 OR 存款 OR 理财 OR 复利 OR 退休 OR 资产配置)",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=15)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    since = int(time.time() - a.hours * 3600)
    suffix = f"lang:zh -filter:replies -filter:nativeretweets min_faves:30 since_time:{since}"
    eng = ROOT / "engagement.json"
    done_authors = {e["target"].split("/")[3].lower() for e in json.loads(eng.read_text())} if eng.exists() else set()
    rows, limited = {}, []
    for g, q in GROUPS.items():
        res = opencli("xhot", "search", f"{q} {suffix}", "--limit", "60")
        if not res or "id" not in res[0]:
            limited.append(g)
        for t in res:
            if "id" in t:
                t.setdefault("groups", []).append(g)
                rows.setdefault(t["id"], t)
        time.sleep(4)
    out = []
    for t in rows.values():
        ts = dt.datetime.strptime(t["created_at"], "%a %b %d %H:%M:%S %z %Y").timestamp()
        if ts < since or t["author"] in ("ElioCUIsg", "BITstocks_CN", "BITstocks"):
            continue
        t["views"] = int(t.get("views") or 0)
        t["engaged_before"] = t["author"].lower() in done_authors
        out.append(t)
    out.sort(key=lambda t: -t["views"])
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    log(f"候选 {len(out)} 条；限流/失败的组：{limited or '无'}")


if __name__ == "__main__":
    main()
