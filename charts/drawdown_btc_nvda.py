# /// script
# dependencies = ["matplotlib"]
# ///
"""d1 配图：BTC 2017–18 与 NVDA 2021–22 从高点的回撤（周线收盘，Yahoo Finance）。

用法：uv run charts/drawdown_btc_nvda.py <BTC-USD.json> <NVDA.json> <out.png>
"""
import datetime as dt
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

font_manager.fontManager.addfont("/System/Library/Fonts/Hiragino Sans GB.ttc")
plt.rcParams["font.family"] = "Hiragino Sans GB"


def series(path, start, end):
    r = json.load(open(path))["chart"]["result"][0]
    pts = [(dt.datetime.fromtimestamp(t, dt.UTC).replace(tzinfo=None), c) for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]
    return [(d, c) for d, c in pts if start <= d <= end]


def drawdown(pts):
    peak_i = max(range(len(pts)), key=lambda i: pts[i][1])
    after = pts[peak_i:]
    peak = after[0][1]
    return [(i, (c / peak - 1) * 100) for i, (_, c) in enumerate(after)], peak, after


btc_file, nvda_file, out = sys.argv[1:4]
btc = series(btc_file, dt.datetime(2017, 1, 1), dt.datetime(2019, 3, 31))
nvda = series(nvda_file, dt.datetime(2021, 1, 1), dt.datetime(2023, 3, 31))

fig, ax = plt.subplots(figsize=(12, 6.75), dpi=100)
fig.patch.set_facecolor("#0f1115")
ax.set_facecolor("#0f1115")

for pts, color, label in ((btc, "#f7931a", "比特币  2017.12 高点之后"), (nvda, "#76b900", "英伟达  2021.11 高点之后")):
    dd, peak, after = drawdown(pts)
    xs, ys = [i for i, _ in dd], [y for _, y in dd]
    ax.plot(xs, ys, color=color, lw=3, label=label)
    lo = min(range(len(ys)), key=lambda i: ys[i])
    ax.scatter([xs[lo]], [ys[lo]], color=color, s=80, zorder=5)
    off = (-130, -42) if color == "#f7931a" else (10, -28)
    ax.annotate(f"{ys[lo]:.0f}%", (xs[lo], ys[lo]), xytext=off, textcoords="offset points",
                color=color, fontsize=30, fontweight="bold")
    print(label, "peak", after[0][0].date(), round(peak, 2), "trough", after[lo][0].date(), round(after[lo][1], 2), f"{ys[lo]:.1f}%")

ax.axhline(0, color="#555", lw=1)
ax.axhline(-50, color="#444", lw=1, ls="--")
ax.text(1, -48, "腰斩线", color="#888", fontsize=14)
ax.set_ylim(-100, 8)
ax.set_xlim(0, 70)
ax.set_xlabel("见顶后的周数", color="#aaa", fontsize=14)
ax.set_ylabel("距高点", color="#aaa", fontsize=14)
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
ax.tick_params(colors="#aaa", labelsize=12)
for s in ax.spines.values():
    s.set_visible(False)
ax.grid(axis="y", color="#222")
ax.set_title("17 年的比特币和 20 年的英伟达，上车之后长这样", color="#eee", fontsize=24, pad=18, loc="left")
leg = ax.legend(loc="upper center", fontsize=15, frameon=False)
for t in leg.get_texts():
    t.set_color("#ddd")
fig.text(0.99, 0.015, "数据：Yahoo Finance 周线收盘", color="#666", fontsize=11, ha="right")
fig.tight_layout()
fig.savefig(out, facecolor=fig.get_facecolor())
print(out)
