#!/usr/bin/env python3
"""从 OpenBit 公开页抓一只标的或一个人物的可引用事实（研究摘要、驱动、来源说法、持有人申报、资料时间），存成 JSON，顺手打印一份给写评论的人看。

用法：python3 ob_facts.py NVDA TSLA pelosi [--date 2026-10-24] [--en]
输出：data/<日期>/ob/<key>.json
只读。回复里引用的每个数都要能在这里找到原句。
"""
import argparse
import datetime as dt
import json
import re
from pathlib import Path

from daily_targets import LINK, PEOPLE, fetch, visible_lines
from post_queue import ROOT, log

BIAS = re.compile(r"^(偏多|偏空|分歧|中性|偏中性)\s*·\s*(.+?)\s*·\s*资料更新：$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def section(lines, start, ends):
    try:
        i = lines.index(start) + 1
    except ValueError:
        return []
    j = len(lines)
    for e in ends:
        if e in lines[i:]:
            j = min(j, lines.index(e, i))
    return lines[i:j]


def after(lines, label, k=1):
    try:
        i = lines.index(label)
        return lines[i + k]
    except (ValueError, IndexError):
        return None


def parse_stock(lines, ticker):
    title = next((l for l in lines if "为什么涨跌" in l and "·" not in l), "")
    out = {"kind": "stock", "key": ticker, "url": f"{LINK}/stocks/{ticker}", "title": title,
           "summary": {"headline": after(lines, "研究摘要"), "why": after(lines, "为什么关注"),
                       "next_check": after(lines, "下一验证点"), "next_check_note": after(lines, "下一验证点", 2),
                       "falsifier": after(lines, "什么情况会推翻判断")},
           "drivers": [], "sources": [], "holders": [], "dates": {}}
    sec = section(lines, "研究驱动", ["来源说法", "代币化版本", "相关板块", "持有人申报", "资料时间与使用范围"])
    i = 0
    while i < len(sec) - 3:
        m = BIAS.match(sec[i + 1])
        if m and DATE.match(sec[i + 2]):
            out["drivers"].append({"name": sec[i], "bias": m.group(1), "status": m.group(2), "date": sec[i + 2], "text": sec[i + 3]})
            i += 4
        else:
            i += 1
    sec = section(lines, "来源说法", ["代币化版本", "相关板块", "持有人申报", "资料时间与使用范围"])
    for i, l in enumerate(sec):
        m = re.match(r"^(来源标识|转述来源)：(.+?)\s*·\s*资料所记事件日：$", l)
        if m and i >= 1 and i + 1 < len(sec):
            out["sources"].append({"text": sec[i - 1], "source": m.group(2), "date": sec[i + 1]})
    sec = section(lines, "持有人申报", ["资料时间与使用范围"])
    i = 0
    while i < len(sec) - 3:
        if sec[i + 1].startswith("·") and "申报变动：" in sec[i + 2] and DATE.match(sec[i + 3]):
            d = sec[i + 2]
            out["holders"].append({"name": sec[i], "org": sec[i + 1].lstrip("· ").strip(), "kind": d.split(" · ")[0],
                                   "flags": [p for p in d.split(" · ")[1:] if "：" not in p],
                                   "change": (re.search(r"申报变动：(\S+)", d) or [None, None])[1],
                                   "pct": (re.search(r"占比：([\d.]+%)", d) or [None, None])[1], "asof": sec[i + 3]})
            i += 4
        else:
            i += 1
    sec = section(lines, "资料时间与使用范围", ["查看档案目录"])
    for i in range(0, len(sec) - 1, 2):
        if sec[i].endswith("："):
            out["dates"][sec[i].rstrip("：")] = sec[i + 1]
    return out


def parse_person(lines, slug):
    title = next((l for l in lines if "申报" in l and "截至" in l and len(l) < 60), lines[0] if lines else "").replace(" · OpenBit", "")
    out = {"kind": "person", "key": slug, "url": f"{LINK}/people/{slug}", "title": title,
           "asof": (re.search(r"截至\s*(\d{4}-\d{2}-\d{2})", title) or [None, None])[1],
           "filed": next((lines[i + 1] for i, l in enumerate(lines[:-1]) if l.endswith("提交日：")), None),
           "subject": after(lines, "申报主体"), "securities": [], "transactions": []}
    sec = section(lines, "申报动作", ["证券链接进入对应股票研究页；其引擎观点可能更新于另一个时点，不能当作申报人的观点。", "已披露交易记录"])
    i = 0
    while i + 2 < len(sec):
        m = re.search(r"（([A-Z][A-Z0-9.\-]{0,6})）$", sec[i])
        if m:
            out["securities"].append({"name": sec[i], "ticker": m.group(1), "pct": sec[i + 1], "action": sec[i + 2]})
            i += 3
        else:
            i += 1
    sec = section(lines, "已披露交易记录", ["×"])
    cur = None
    for l in sec[1:]:
        m = re.search(r"（([A-Z][A-Z0-9.\-]{0,6})）$", l)
        if m:
            cur = {"ticker": m.group(1), "rows": []}
            out["transactions"].append(cur)
        elif cur is not None and len(cur["rows"]) < 12:
            cur["rows"].append(l)
    return out


def brief(d):
    if d["kind"] == "stock":
        s = d["summary"]
        lines = [f"## {d['title']}  {d['url']}", f"摘要：{s['headline']} ｜ 为什么关注：{s['why']}", f"下一验证点：{s['next_check']} ｜ 推翻条件：{s['falsifier']}",
                 f"驱动 {len(d['drivers'])} 条（偏多 {sum(x['bias']=='偏多' for x in d['drivers'])} / 偏空 {sum(x['bias']=='偏空' for x in d['drivers'])} / 分歧 {sum(x['bias']=='分歧' for x in d['drivers'])}）："]
        lines += [f"  - [{x['bias']}·{x['status']}·{x['date']}] {x['name']}：{x['text']}" for x in d["drivers"]]
        lines += [f"来源说法 {len(d['sources'])} 条："] + [f"  - ({x['source']} {x['date']}) {x['text']}" for x in d["sources"][:6]]
        lines += [f"持有人申报 {len(d['holders'])} 条："] + [f"  - {x['name']}（{x['org']}）{x['kind']} {' '.join(x['flags'])} {x['change']} {x['pct'] or ''} 截至 {x['asof']}" for x in d["holders"]]
        lines += ["资料时间：" + "；".join(f"{k} {v}" for k, v in d["dates"].items())]
    else:
        lines = [f"## {d['title']}  {d['url']}", f"主体：{d['subject']} ｜ 资料截至 {d['asof']} ｜ 提交日 {d['filed']}", f"申报涉及 {len(d['securities'])} 只："]
        lines += [f"  - {x['name']} {x['action']} {x['pct'] if x['pct'] != '—' else ''}" for x in d["securities"]]
        for t in d["transactions"][:8]:
            lines.append(f"  交易 {t['ticker']}: " + " / ".join(t["rows"][:6]))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="+", help="标的代码（大写）或人物 slug")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    a = ap.parse_args()
    outdir = ROOT / "data" / a.date / "ob"
    outdir.mkdir(parents=True, exist_ok=True)
    for k in a.keys:
        if k.lower() in PEOPLE:
            d = parse_person(visible_lines(fetch(f"{LINK}/people/{k.lower()}")), k.lower())
        else:
            d = parse_stock(visible_lines(fetch(f"{LINK}/stocks/{k.upper()}")), k.upper())
        d["fetched"] = dt.datetime.now().isoformat(timespec="minutes")
        (outdir / f"{d['key']}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1))
        print(brief(d))
        print()


if __name__ == "__main__":
    main()
