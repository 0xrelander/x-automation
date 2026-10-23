#!/usr/bin/env python3
"""把 data/<date>/{top.json, final_top.json, pack.json} 排成「今日审阅包」纯文本，并做字数、相似度、AI 味检查。

用法：python3 render_pack.py [--date YYYY-MM-DD]
产出：review/审阅包-<date>.txt；有 fatal 时退出码为 2
"""
import argparse
import datetime as dt
import html
import json
import sys
from pathlib import Path

from render_review import AI_SMELL, CSS, RED_LINES, SIM_FATAL, similarity

ROOT = Path(__file__).resolve().parent
MIN_CHARS, MAX_CHARS = 120, 280
SPEC_BANNED = ["首先", "其次", "总的来说", "值得注意的是", "在当今社会"]


def body_len(text):
    lines = [l for l in text.splitlines() if not l.startswith("#") and "不构成投资建议" not in l]
    return len("".join(lines).replace(" ", ""))


def check(text, source, long_form=False):
    out = []
    n = body_len(text)
    if long_form:
        out.append(("ok", f"长文 {n} 字"))
    elif not MIN_CHARS <= n <= MAX_CHARS:
        out.append(("warn", f"正文 {n} 字，不在 {MIN_CHARS}–{MAX_CHARS}"))
    for w in SPEC_BANNED + RED_LINES:
        if w in text:
            out.append(("fatal", f"禁用词「{w}」"))
    for w in AI_SMELL:
        if w in text and w not in SPEC_BANNED:
            out.append(("warn", f"AI 味词「{w}」"))
    if "**" in text:
        out.append(("fatal", "Markdown 残留"))
    if "「" in text or "」" in text:
        out.append(("fatal", "正文用了「」（用户判定 AI 味）"))
    r = similarity(text, source)
    out.append(("fatal" if r >= SIM_FATAL else "ok", f"与原帖相似度 {r:.2f}"))
    return out


def fmt_post(t):
    return (f"@{t['author']} · {t['created_at'][4:16]} UTC\n"
            f"   曝光 {t['views']:,} · 点赞 {t['likes']:,} · 回复 {t['replies']:,} · 转发 {t['retweets']:,} · 收藏 {t['bookmarks']:,}")


PACK_CSS = CSS + """
h2{display:flex;align-items:baseline;gap:8px}h2 small{font-size:13px;font-weight:400;color:var(--mut)}
.rank{display:inline-block;min-width:22px;height:22px;line-height:22px;text-align:center;border-radius:6px;background:var(--acc);color:#fff;font-size:12px;font-weight:600;margin-right:8px}
.stats{color:var(--mut);font-size:12px;margin:2px 0 8px}.src{color:var(--mut);font-size:13px;border-left:3px solid var(--line);padding-left:10px;margin:8px 0}
.ver{border:1px solid var(--line);border-radius:8px;padding:12px;margin:10px 0}.ver-h{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px}
.ver-h b{font-size:14px}.body{white-space:pre-wrap;font-size:15px;line-height:1.75}.chk{font-size:12px;margin-top:8px}
details{margin:8px 0}summary{cursor:pointer;color:var(--acc);font-size:13px}.why{background:color-mix(in srgb,var(--acc) 8%,transparent);border-radius:8px;padding:8px 12px;font-size:13px;margin:6px 0 10px}
.prompt{font-family:ui-monospace,Menlo,monospace;font-size:12px;background:color-mix(in srgb,var(--fg) 5%,transparent);border-radius:6px;padding:8px;margin:6px 0;white-space:pre-wrap}
nav{position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:2;display:flex;gap:14px;flex-wrap:wrap;font-size:13px;border-bottom:1px solid var(--line)}
button.copied{color:var(--ok);border-color:var(--ok)}button{white-space:nowrap;flex-shrink:0}
"""


def render_html(date, top, final, pack, by_id, full, skipped):
    e = html.escape
    ver_n = sum(len(p["versions"]) for p in pack["posts"])

    def chk_html(text, src, long_form=False):
        items = check(text, src, long_form)
        return "".join(f"<span class={lvl}>{e(m)}</span>　" for lvl, m in items if lvl != "ok" or "相似度" in m)

    def ver_html(pid, ver, highlight=False):
        t = by_id[pid]
        vid = f"v{pid[-6:]}{ver['label'][0]}"
        style = " style='border-color:var(--acc)'" if highlight else ""
        return (f"<div class=ver{style}><div class=ver-h><b>版本 {e(ver['label'])}</b>"
                f"<button onclick=copyText('{vid}',this)>复制</button></div>"
                f"<div class=body id={vid}>{e(ver['text'])}</div><div class=chk>{chk_html(ver['text'], t['text'], '长文' in ver['label'])}</div></div>")

    def img_html(img):
        s = f"<div class=meta>配图：<b>{'需要' if img['need'] else '不需要，纯文字'}</b>。{e(img['note'])}</div>"
        for i, pr in enumerate(img["prompts"], 1):
            s += f"<div class=prompt>提示词 {i}：{e(pr)}</div>"
        return s

    def src_html(t):
        return (f"<div class=src><a href='{e(t['url'])}' target=_blank>@{e(t['author'])}</a> 的原帖 · "
                f"曝光 {t['views']:,} · 赞 {t['likes']:,} · 评 {t['replies']:,} · 转 {t['retweets']:,} · 藏 {t['bookmarks']:,}"
                f"<div>{e(t['text'][:160])}</div></div>")

    def breakdown_html(p):
        rows = []
        for k, v in p["breakdown"].items():
            if k == "模板":
                rows.append("<li>可复用句式：<ul>" + "".join(f"<li>{e(x)}</li>" for x in v) + "</ul></li>")
            else:
                rows.append(f"<li><b>{e(k)}</b>：{e(v)}</li>")
        return f"<details><summary>爆点拆解</summary><ul>{''.join(rows)}</ul></details>"

    P = [f"<!doctype html><html lang=zh><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>X 仿写审阅包 {date}</title><style>{PACK_CSS}</style></head><body><main>",
         f"<h1>X 中文爆款仿写审阅包 · {date}</h1>",
         f"<div class=meta>@ElioCUIsg · X 搜索最近 24h 中文帖 {top['pool_size']} 条，剔除 {len(final['dropped'])} 条 · "
         f"仿写 {len(pack['posts'])} 篇原帖、{ver_n} 个版本 · 互动量 = 赞 + 评 + 转 · <b>未发布</b></div>",
         "<nav><a href='#rec'>推荐发布</a><a href='#all'>全部仿写</a><a href='#q'>待确认</a><a href='#rank'>榜单</a></nav>"]

    P.append(f"<h2 id=rec>今日推荐发布 <small>按潜力排序</small></h2>")
    for i, r in enumerate(pack["recommend"], 1):
        p, t = full[r["id"]], by_id[r["id"]]
        ver = next((v for v in p["versions"] if v["label"].startswith(r["label"])), p["versions"][0])
        inner = breakdown_html(p).replace("<details><summary>爆点拆解</summary>", "").replace("</details>", "")
        P.append(f"<div class=card><div><span class=rank>{i}</span><b>仿 @{e(t['author'])} · 版本 {e(r['label'])}</b></div>"
                 f"<div class=why>{e(r['why'])}</div>{ver_html(r['id'], ver, True)}{img_html(p['image'])}"
                 f"<details><summary>原帖和爆点拆解</summary>{src_html(t)}{inner}</details></div>")

    P.append("<h2 id=q>需要你确认</h2><div class=card><ol>" + "".join(f"<li>{e(q)}</li>" for q in pack["questions"]) + "</ol></div>")

    P.append(f"<h2 id=all>全部仿写 <small>{len(pack['posts'])} 篇原帖 × A/B</small></h2>")
    for p in pack["posts"]:
        t = by_id[p["id"]]
        P.append(f"<div class=card><b>仿 @{e(t['author'])}</b>{src_html(t)}{breakdown_html(p)}"
                 + "".join(ver_html(p["id"], v) for v in p["versions"]) + img_html(p["image"]) + "</div>")

    P.append("<h2 id=rank>榜单 Top10</h2><div class=grid>")
    for title, ids in (("浏览量", final["top_views"]), ("互动量（赞+评+转）", final["top_engagement"])):
        rows = ""
        for i, pid in enumerate(ids, 1):
            t = by_id[pid]
            tag = "<span class=ok>已仿写</span>" if pid in full else f"<span class=sub>{e(skipped.get(pid, '与人设关联弱')[:24])}</span>"
            rows += (f"<tr><td class=n>{i}</td><td><a href='{e(t['url'])}' target=_blank>@{e(t['author'])}</a>"
                     f"<div class=tx>{e(t['text'][:60])}</div><div style='font-size:12px'>{tag}</div></td>"
                     f"<td class=num>{t['views']:,}</td><td class=num>{t['likes'] + t['replies'] + t['retweets']:,}</td></tr>")
        P.append(f"<div class=card><b>{title}</b><table><tr><th></th><th>帖子</th><th class=num>曝光</th><th class=num>互动</th></tr>{rows}</table></div>")
    P.append("</div>")
    P.append("<details class=card><summary>剔除的 " + str(len(final["dropped"])) + " 条</summary><ul>" + "".join(
        f"<li>@{e(by_id.get(x['id'], {}).get('author', x['id']))}：{e(x['reason'])}</li>" for x in final["dropped"]) + "</ul></details>")
    P.append("""</main><script>
function copyText(id,btn){const t=document.getElementById(id).innerText;
(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).catch(()=>{const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();document.execCommand('copy');a.remove()})
.finally(()=>{btn.textContent='已复制';btn.classList.add('copied');setTimeout(()=>{btn.textContent='复制';btn.classList.remove('copied')},1500)})}
</script></body></html>""")
    return "".join(P)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()
    d = ROOT / "data" / args.date
    top, final, pack = (json.loads((d / f).read_text()) for f in ("top.json", "final_top.json", "pack.json"))
    by_id = {t["id"]: t for k in ("candidates_views", "candidates_engagement") for t in top[k]}
    full = {p["id"]: p for p in pack["posts"]}
    skipped = {s["id"]: s["reason"] for s in pack["skipped"]}
    done, fatal = set(), 0
    L = [f"【今日X中文爆款仿写审阅包 - {args.date}】", "",
         f"数据：X 搜索，最近 24 小时，中文；候选 {top['pool_size']} 条，剔除 {len(final['dropped'])} 条（政治、八卦、低俗、猎奇、跑题）",
         "互动量 = 点赞 + 回复 + 转发；账号人设：@ElioCUIsg（BIT 美股业务负责人）", ""]

    def section(title, ids):
        nonlocal fatal
        L.extend([title, ""])
        for i, pid in enumerate(ids, 1):
            t = by_id[pid]
            L.append(f"{i}. 原帖链接：{t['url']}")
            L.append(f"   {fmt_post(t)}")
            L.append("   原帖摘要：" + t["text"].replace("\n", " ")[:120])
            if pid in done:
                L.extend(["   （拆解和仿写见上文同一篇）", ""])
                continue
            done.add(pid)
            p = full.get(pid)
            if not p:
                L.extend([f"   不仿写：{skipped.get(pid, '与人设关联弱')}", ""])
                continue
            L.append("   爆点拆解：")
            for k, v in p["breakdown"].items():
                if k == "模板":
                    L.append("     可复用句式：")
                    L.extend(f"       · {x}" for x in v)
                else:
                    L.append(f"     {k}：{v}")
            for ver in p["versions"]:
                L.append(f"   仿写版本{ver['label']}：")
                L.extend("     " + line if line else "" for line in ver["text"].splitlines())
                res = check(ver["text"], t["text"], "长文" in ver["label"])
                fatal += sum(1 for lvl, _ in res if lvl == "fatal")
                L.append("     ［自检］" + "；".join(m for _, m in res))
            img = p["image"]
            L.append(f"   配图建议：{'是' if img['need'] else '否，建议纯文字'}。{img['note']}")
            for j, pr in enumerate(img["prompts"], 1):
                L.append(f"     提示词{j}：{pr}")
            L.append("")

    section("一、浏览量 Top 相关", final["top_views"])
    section("二、互动量 Top 相关", final["top_engagement"])
    L.extend(["三、今日推荐优先发布的 3-5 条", ""])
    for i, r in enumerate(pack["recommend"], 1):
        L.append(f"{i}. @{by_id[r['id']]['author']} 那篇的仿写版本{r['label']}：{r['why']}")
    L.extend(["", "四、需要用户确认的问题", ""])
    L.extend(f"{i}. {q}" for i, q in enumerate(pack["questions"], 1))
    out = ROOT / "review" / f"审阅包-{args.date}.txt"
    out.write_text("\n".join(L) + "\n")
    html_out = ROOT / "review" / f"审阅包-{args.date}.html"
    html_out.write_text(render_html(args.date, top, final, pack, by_id, full, skipped))
    print(out)
    print(html_out)
    print(f"fatal={fatal}")
    sys.exit(2 if fatal else 0)


if __name__ == "__main__":
    main()
