#!/usr/bin/env python3
"""每天选账号：按 config.json 的关键词组搜最近 N 小时的中英文高流量帖，识别帖里提到的、OpenBit 有页面的标的 / 人物，
按「浏览增速 × 新鲜 × 能补数」打分，每个作者只留最好的一条，输出候选 JSON 和给人看的 Markdown。

用法：python3 daily_targets.py [--hours 30] [--date 2026-10-24] [--products top,live]
输出：data/<日期>/cands.json、data/<日期>/候选.md
只读不发。账号从 config.local.json 读（不进仓库）。
"""
import argparse
import datetime as dt
import html
import json
import re
import time
import urllib.request
from pathlib import Path

from post_queue import ROOT, log, opencli

CFG = json.loads((ROOT / "config.json").read_text())
LOCAL = json.loads((ROOT / "config.local.json").read_text()) if (ROOT / "config.local.json").exists() else {}
LINK = CFG.get("link_base", "https://openbit.trade")

# 人物页：中英文叫法 → OpenBit people slug
PEOPLE = {
    "buffett": ["巴菲特", "Buffett", "Berkshire", "伯克希尔"],
    "burry": ["伯里", "Burry", "大空头"],
    "pelosi": ["佩洛西", "Pelosi"],
    "dalio": ["达利欧", "Dalio", "桥水", "Bridgewater"],
    "soros": ["索罗斯", "Soros"],
    "tepper": ["泰珀", "Tepper", "Appaloosa"],
    "icahn": ["伊坎", "Icahn"],
    "druckenmiller": ["德鲁肯米勒", "Druckenmiller"],
    "ackman": ["阿克曼", "Ackman", "Pershing"],
    "wood": ["木头姐", "凯茜·伍德", "Cathie Wood", "ARK Invest", "ARKK"],
    "justinsun": ["孙宇晨", "Justin Sun"],
    "klarman": ["卡拉曼", "Klarman", "Baupost"],
    "coleman": ["蔡斯·科尔曼", "Chase Coleman", "Tiger Global", "老虎环球"],
    "gottheimer": ["戈特海默", "Gottheimer"],
    "greene": ["泰勒·格林", "Marjorie Taylor Greene", "MTG"],
}
# 站上目录没有的常用叫法
EXTRA_ALIAS = {
    "NVDA": ["英伟达", "老黄", "Nvidia", "NVIDIA", "Jensen"], "TSLA": ["特斯拉", "Tesla", "马斯克"], "AAPL": ["苹果", "Apple"],
    "MSFT": ["微软", "Microsoft"], "GOOGL": ["谷歌", "Google", "Alphabet"], "AMZN": ["亚马逊", "Amazon"], "META": ["Meta", "脸书"],
    "AMD": ["AMD", "超微"], "AVGO": ["博通", "Broadcom"], "INTC": ["英特尔", "Intel"], "MU": ["美光", "Micron"], "TSM": ["台积电", "TSMC"],
    "ORCL": ["甲骨文", "Oracle"], "MSTR": ["微策略", "Strategy", "MicroStrategy"], "COIN": ["Coinbase"], "PLTR": ["Palantir"],
    "NFLX": ["奈飞", "Netflix"], "BABA": ["阿里巴巴"], "PDD": ["拼多多"], "NIO": ["蔚来"], "XPEV": ["小鹏"], "LI": ["理想汽车"],
    "SPCX": ["SpaceX"], "IREN": ["IREN"], "CRWV": ["CoreWeave"], "SMCI": ["超微电脑"], "ASML": ["阿斯麦", "ASML"], "ARM": ["Arm 控股"],
}
# 大写裸词里容易误判的英文单词，不当代码
TICKER_STOP = {"AI", "ARM", "AIR", "BE", "ON", "ALL", "NOW", "OPEN", "FAST", "HOOD", "PATH", "PLAY", "SNOW", "TEAM", "GOOD",
               "LOVE", "CAN", "E", "SSL", "MX", "NC", "INR", "EC", "LI", "MU", "BA", "GM", "IT", "US", "CEO", "ETF", "IPO", "GDP",
               "CPI", "FED", "PE", "EPS", "ATH", "ATHS", "RIOT", "HUT", "TEM", "VST", "DIS", "AB", "NET", "RUN", "BILL", "LIFE"}


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 x-automation daily_targets"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def visible_lines(page):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    return [l.strip() for l in t.splitlines() if l.strip()]


def inventory():
    """OpenBit 目前有页面的标的清单 + 中文名，缓存一天。"""
    p = ROOT / "data" / "ob_inventory.json"
    if p.exists() and time.time() - p.stat().st_mtime < 86400:
        return json.loads(p.read_text())
    locs = re.findall(r"<loc>([^<]+)", fetch(f"{LINK}/sitemap-stocks.xml"))
    tickers = sorted({re.sub(r".*/stocks/", "", l) for l in locs})
    alias = {}
    for name, tk in re.findall(r"([^\n（）]{1,40})（([A-Z][A-Z0-9.\-]{0,6})）", "\n".join(visible_lines(fetch(f"{LINK}/stocks")))):
        if tk in tickers:
            alias.setdefault(tk, []).append(name.strip())
    inv = {"fetched": dt.datetime.now().isoformat(timespec="minutes"), "tickers": tickers, "alias": alias}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(inv, ensure_ascii=False, indent=1))
    log(f"OpenBit 目录：{len(tickers)} 只标的")
    return inv


def detect(text, inv):
    tickers, people = [], []
    tset = set(inv["tickers"])
    for tk in re.findall(r"\$([A-Za-z]{1,6})\b", text):
        if tk.upper() in tset:
            tickers.append(tk.upper())
    for tk in re.findall(r"\b([A-Z]{3,5})\b", text):
        if tk in tset and tk not in TICKER_STOP:
            tickers.append(tk)
    for tk, names in {**inv["alias"], **{k: inv["alias"].get(k, []) + v for k, v in EXTRA_ALIAS.items()}}.items():
        if tk in tset and any(n and n in text for n in names):
            tickers.append(tk)
    for slug, names in PEOPLE.items():
        if any(n in text for n in names):
            people.append(slug)
    return sorted(set(tickers)), sorted(set(people))


def matched_words(text, groups):
    low = text.lower()
    return [w for terms in groups.values() for w in terms if w.strip('"$').lower() in low]


def chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def canonical(t):
    return f"https://x.com/{t['author']}/status/{t['id']}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=CFG.get("reply_window_hours", 30))
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--products", default=",".join(CFG.get("products", ["top"])))
    a = ap.parse_args()
    day = ROOT / "data" / a.date
    day.mkdir(parents=True, exist_ok=True)
    inv = inventory()
    since = int(time.time() - a.hours * 3600)
    me = LOCAL.get("account", "")
    exclude = {x.lower() for x in CFG.get("exclude_authors", []) + ([me] if me else [])}
    eng_p = ROOT / "engagement.json"
    eng = json.loads(eng_p.read_text()) if eng_p.exists() else []
    cooldown_days = CFG.get("author_cooldown_days", 7)
    recent_authors = {e["target"].split("/")[3].lower() for e in eng
                      if (dt.date.today() - dt.date.fromisoformat(e["date"])).days < cooldown_days}
    all_authors = {e["target"].split("/")[3].lower() for e in eng}
    mf = CFG.get("reply_min_faves", {"zh": 30, "en": 150})
    plans = []
    for lang, groups, suffix in (("zh", CFG["groups"], CFG["query_suffix"]), ("en", CFG.get("groups_en", {}), CFG.get("query_suffix_en", ""))):
        for g, terms in groups.items():
            for ch in chunks(terms, CFG.get("terms_per_query", 6)):
                plans.append((lang, g, f"({' OR '.join(ch)}) {suffix} min_faves:{mf[lang]} since_time:{since}"))
    rows, failed = {}, []
    for prod in a.products.split(","):
        for lang, g, q in plans:
            res = opencli("twitter", "search", q, "--product", prod, "--limit", str(CFG.get("per_query_limit", 40)))
            if not res or "id" not in res[0]:
                failed.append(f"{g}/{prod}")
            for t in res:
                if "id" not in t:
                    continue
                t["lang"] = lang
                t.setdefault("groups", []).append(g)
                rows.setdefault(t["id"], t)
            log(f"{lang} {g} [{prod}] → {len(res)} 条，累计 {len(rows)}")
            time.sleep(3)
    now = time.time()
    out = []
    for t in rows.values():
        try:
            ts = dt.datetime.strptime(t["created_at"], "%a %b %d %H:%M:%S %z %Y").timestamp()
        except Exception:
            continue
        if ts < since or t["author"].lower() in exclude:
            continue
        if any(b in t["text"] for b in CFG.get("blocklist", [])):
            continue
        age = max(1.0, (now - ts) / 60)
        views = int(t.get("views") or 0)
        tickers, people = detect(t["text"], inv)
        fresh = 1.0 if age <= 360 else 0.6 if age <= 1440 else 0.25
        fill = 1.0 if (tickers or people) else 0.3
        velocity = views / max(age, 30)
        out.append({
            "id": t["id"], "url": canonical(t), "author": t["author"], "bio": (t.get("bio") or "")[:80], "text": t["text"],
            "created_at": t["created_at"], "age_min": round(age), "views": views, "likes": t.get("likes", 0), "lang": t["lang"],
            "groups": sorted(set(t["groups"])), "words": matched_words(t["text"], {**CFG["groups"], **CFG.get("groups_en", {})})[:6],
            "tickers": tickers, "people": people, "has_media": bool(t.get("has_media")),
            "links": [f"{LINK}{'/en' if t['lang'] == 'en' else ''}/stocks/{x}" for x in tickers] + [f"{LINK}{'/en' if t['lang'] == 'en' else ''}/people/{x}" for x in people],
            "score": round(velocity * fresh * fill, 1), "engaged_before": t["author"].lower() in all_authors,
            "cooldown": t["author"].lower() in recent_authors,
        })
    out.sort(key=lambda r: -r["score"])
    best, seen = [], {}
    for r in out:
        k = r["author"].lower()
        if k in seen:
            best[seen[k]]["others_by_author"] = best[seen[k]].get("others_by_author", 0) + 1
            continue
        seen[k] = len(best)
        best.append(r)
    (day / "cands.json").write_text(json.dumps(best, ensure_ascii=False, indent=1))
    n = CFG.get("candidates_n", 30)
    md = [f"# {a.date} 候选（最近 {a.hours:g} 小时，{len(rows)} 条原始 → {len(out)} 条合格 → {len(best)} 位作者）", "",
          f"分 = 浏览/分钟 × 新鲜（≤6h 1.0 / ≤24h 0.6 / 更久 0.25）× 能补数（帖里有 OpenBit 有页面的标的或人物 1.0，否则 0.3）。失败的查询：{failed or '无'}", "",
          "| # | 作者 | 浏览 | 发了多久 | 能补的页 | 帖子 | 分 |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(best[:n], 1):
        flag = " ⛔7天内评过" if r["cooldown"] else (" ·评过" if r["engaged_before"] else "")
        age = f"{r['age_min'] // 60}h{r['age_min'] % 60:02d}m"
        pages = ", ".join(r["tickers"] + [f"@{p}" for p in r["people"]]) or "—"
        txt = re.sub(r"\s+", " ", r["text"])[:70].replace("|", "｜")
        md.append(f"| {i} | [@{r['author']}]({r['url']}){flag}<br><sub>{r['bio'][:40]}</sub> | {r['views']:,} | {age} | {pages} | {txt} | {r['score']} |")
    (day / "候选.md").write_text("\n".join(md) + "\n")
    log(f"候选 {len(best)} 位作者（前 {min(n, len(best))} 写进 候选.md）；失败：{failed or '无'}")


if __name__ == "__main__":
    main()
