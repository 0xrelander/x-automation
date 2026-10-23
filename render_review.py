#!/usr/bin/env python3
"""把 data/<date>/{top.json, final_top.json, analysis.json, drafts.json} 渲染成审阅页，并做自动检查。

用法：python3 render_review.py [--date YYYY-MM-DD]
产出：review/elio_x_review_<date>.html；同时把 drafts 复制到 history/<date>.json 供去重
退出码：有 fatal 时为 2
"""
import argparse
import datetime as dt
import difflib
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DISCLAIMER = "不构成投资建议"
SIM_FATAL = 0.45
MAX_CHARS = 600
AI_SMELL = ["在这个", "让我们", "值得注意的是", "总而言之", "综上所述", "底层逻辑", "赋能", "不禁", "毋庸置疑", "深度剖析",
            "闭环", "抓手", "本质", "维度", "说白了", "真正的", "从来不是", "随着", "折射", "值得深思", "未来可期", "希望对你有帮助",
            "牌桌", "子弹", "裸泳", "称重机", "投票机", "慢就是快", "进行了", "进行一"]
RED_LINES = ["中共", "台独", "习近平", "必涨", "稳赚", "无风险", "抄底就对"]
HYPE_WORDS = ["梭哈", "满仓", "all in", "冲就完了"]  # 劝诫语境常见，只做提醒
RISKY_TOOLS = ["杠杆", "期权", "融券", "融资", "合约"]


def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def similarity(a, b):
    norm = lambda s: re.sub(r"https?://\S+|\s+", "", s)
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def check(draft, sources):
    issues = []  # (level, msg)
    body = "\n".join(draft["tweets"])
    for i, tw in enumerate(draft["tweets"], 1):
        if len(tw) > MAX_CHARS:
            issues.append(("warn", f"第{i}条 {len(tw)} 字，超过 {MAX_CHARS}"))
    if "「" in body or "」" in body:
        issues.append(("fatal", "正文用了「」（用户判定 AI 味）"))
    if re.search(r"\*\*|^#{1,3} |^\s*[-*] ", body, re.M):
        issues.append(("fatal", "有 Markdown 残留（X 不渲染）"))
    if draft.get("needs_disclaimer") and DISCLAIMER not in draft["tweets"][-1]:
        issues.append(("fatal", "needs_disclaimer=true，但最后一条没有免责声明"))
    if any(w in body for w in RISKY_TOOLS) and "风险" not in body:
        issues.append(("warn", "提到杠杆/期权/融资类工具，但没有风险提示"))
    for w in AI_SMELL:
        if w in body:
            issues.append(("warn", f"AI 味词：「{w}」"))
    if re.search(r"不是[^。\n]{0,20}(而是|，是)", body):
        issues.append(("warn", "假对比句式「不是…而是/是…」"))
    if body.count("——") >= 2:
        issues.append(("warn", "破折号偏多"))
    for w in HYPE_WORDS:
        if w in body:
            issues.append(("warn", f"喊单类词「{w}」，确认是劝诫语境"))
    for w in RED_LINES:
        if w in body:
            issues.append(("fatal", f"红线词：「{w}」"))
    best = (0.0, None)
    for s in sources:
        r = similarity(body, s["text"])
        if r > best[0]:
            best = (r, s)
    if best[1] is not None:
        level = "fatal" if best[0] >= SIM_FATAL else ("warn" if best[0] >= 0.3 else "ok")
        issues.append((level, f"与来源 @{best[1]['author']} 相似度 {best[0]:.2f}"))
    return issues


def esc(s):
    return html.escape(str(s))


def tweet_row(t, rank):
    return (f"<tr><td class=n>{rank}</td><td><a href='{esc(t['url'])}' target=_blank>@{esc(t['author'])}</a>"
            f"<div class=tx>{esc(t['text'][:180])}</div></td>"
            f"<td class=num>{t['views']:,}</td><td class=num>{t['engagement']:,}</td>"
            f"<td class=sub>赞{t['likes']} 转{t['retweets']} 评{t['replies']} 引{t['quotes']} 藏{t['bookmarks']}</td></tr>")


CSS = """
:root{--bg:#fafaf8;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#e4e3de;--acc:#1d6fd8;--bad:#c4361f;--warn:#b07400;--ok:#2f7d3b}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--mut:#9a9993;--card:#1f1f1d;--line:#33322f;--acc:#6aa8ff;--bad:#ff7a63;--warn:#f0b34a;--ok:#6cc47a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.65 -apple-system,"PingFang SC","Hiragino Sans GB",sans-serif}
main{max-width:1080px;margin:0 auto;padding:24px 16px 80px}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:36px 0 12px}
.meta{color:var(--mut);font-size:13px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:12px 0;overflow-x:auto;min-width:0}a{word-break:break-all}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.n{color:var(--mut);width:24px}.sub{color:var(--mut);white-space:nowrap}
.tx{color:var(--mut);margin-top:2px}a{color:var(--acc);text-decoration:none}
.tweet{white-space:pre-wrap;border-left:3px solid var(--line);padding:4px 0 4px 12px;margin:10px 0}
.tag{display:inline-block;font-size:12px;padding:1px 8px;border-radius:99px;border:1px solid var(--line);margin:0 6px 6px 0;color:var(--mut)}
.fatal{color:var(--bad)}.warn{color:var(--warn)}.ok{color:var(--ok)}ul{margin:6px 0;padding-left:20px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media (max-width:760px){.grid{grid-template-columns:1fr}.sub{display:none}}
button{font:inherit;font-size:12px;border:1px solid var(--line);background:transparent;color:var(--fg);border-radius:6px;padding:2px 10px;cursor:pointer}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()
    d = ROOT / "data" / args.date
    top = load(d / "top.json", {})
    final = load(d / "final_top.json", {})
    analysis = load(d / "analysis.json", {})
    drafts = load(d / "drafts.json", [])

    by_id = {t["id"]: t for k in ("candidates_views", "candidates_engagement") for t in top.get(k, [])}
    tv = [by_id[i] for i in final.get("top_views", []) if i in by_id] or top.get("candidates_views", [])[:10]
    te = [by_id[i] for i in final.get("top_engagement", []) if i in by_id] or top.get("candidates_engagement", [])[:10]
    ana = {a["id"]: a for a in analysis.get("items", [])}

    parts = [f"<!doctype html><html lang=zh><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>Elio X 日更 {args.date}</title><style>{CSS}</style></head><body><main>",
             f"<h1>Elio X 日更审阅 · {args.date}</h1>",
             f"<div class=meta>候选池 {top.get('pool_size', 0)} 条 · 过去 {top.get('window_hours', 24)}h · 剔除 {len(final.get('dropped', []))} 条跑题或敏感帖 · 稿件 {len(drafts)} 篇 · 未发布，等待确认</div>"]

    fatal_total = 0
    parts.append("<h2>今日稿件</h2>")
    for dr in drafts:
        srcs = [by_id[i] for i in dr.get("source_ids", []) if i in by_id]
        issues = check(dr, srcs)
        fatal_total += sum(1 for lvl, _ in issues if lvl == "fatal")
        tags = "".join(f"<span class=tag>{esc(x)}</span>" for x in [dr.get("format", "single"), dr.get("hot_hook", "")] + dr.get("hashtags", []))
        tweets = "".join(f"<div class=tweet>{esc(t)}</div>" for t in dr["tweets"])
        if dr.get("hashtags"):
            tweets += f"<div class=meta>发布时附：{esc(' '.join(dr['hashtags']))}</div>"
        src_links = " ".join(f"<a href='{esc(s['url'])}' target=_blank>@{esc(s['author'])}</a>" for s in srcs)
        chk = "".join(f"<li class={lvl}>{esc(m)}</li>" for lvl, m in issues)
        parts.append(f"<div class=card id='{esc(dr['slug'])}'><b>{esc(dr['slug'])} · {esc(dr['angle'])}</b> "
                     f"<button onclick=\"navigator.clipboard.writeText(document.querySelectorAll('#{esc(dr['slug'])} .tweet')[0].innerText)\">复制主帖</button>"
                     f"<div style='margin-top:6px'>{tags}</div>{tweets}"
                     f"<div class=meta>借鉴：{esc(dr.get('borrowed', ''))} · 来源 {src_links}</div>"
                     f"<div class=meta>备注：{esc(dr.get('notes', ''))}</div><ul>{chk}</ul></div>")

    if analysis.get("patterns"):
        parts.append("<h2>今日爆点规律</h2><div class=card><ul>" + "".join(f"<li>{esc(p)}</li>" for p in analysis["patterns"]) + "</ul></div>")

    parts.append("<h2>Top 10</h2><div class=grid>")
    for title, items in (("浏览量", tv), ("互动量（赞+转+评+引+藏）", te)):
        parts.append(f"<div class=card><b>{title}</b><table><tr><th></th><th>帖子</th><th class=num>浏览</th><th class=num>互动</th><th class=sub>明细</th></tr>"
                     + "".join(tweet_row(t, i) for i, t in enumerate(items, 1)) + "</table></div>")
    parts.append("</div>")

    if ana:
        parts.append("<h2>逐条拆解</h2>")
        for i in dict.fromkeys([t["id"] for t in tv + te]):
            a, t = ana.get(i), by_id.get(i)
            if not a or not t:
                continue
            parts.append(f"<div class=card><a href='{esc(t['url'])}' target=_blank>@{esc(t['author'])}</a> "
                         f"<span class=tag>{esc(a.get('hook', ''))}</span><div class=tx>{esc(t['text'][:220])}</div>"
                         f"<ul><li>骨架：{esc(a.get('structure', ''))}</li><li>为什么能爆：{esc(a.get('why_it_works', ''))}</li>"
                         f"<li>Elio 可借：{esc(a.get('borrowable', ''))}</li></ul></div>")

    if final.get("dropped"):
        parts.append("<h2>剔除记录</h2><div class=card><ul>" + "".join(
            f"<li>{esc(by_id.get(x['id'], {}).get('author', x['id']))}：{esc(x['reason'])}</li>" for x in final["dropped"]) + "</ul></div>")

    parts.append("</main></body></html>")
    out = ROOT / "review" / f"elio_x_review_{args.date}.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text("".join(parts))
    if drafts:
        (ROOT / "history").mkdir(exist_ok=True)
        shutil.copy(d / "drafts.json", ROOT / "history" / f"{args.date}.json")
    print(out)
    print(f"fatal={fatal_total}")
    sys.exit(2 if fatal_total else 0)


if __name__ == "__main__":
    main()
