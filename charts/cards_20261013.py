# /// script
# dependencies = ["matplotlib"]
# ///
"""2026-10-13 配图：冠军股次年表现柱状图 + 五万存款算账卡。

用法：uv run charts/cards_20261013.py <out_dir>
数据：Yahoo Finance 月线收盘（年末对年末），见 data/2026-10-13/images/{NVDA,PLTR}.json
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

font_manager.fontManager.addfont("/System/Library/Fonts/Hiragino Sans GB.ttc")
plt.rcParams["font.family"] = "Hiragino Sans GB"
BG, FG, MUT = "#0f1115", "#eeeeee", "#8a8a8a"
out = sys.argv[1]

# 图 1：当年冠军 vs 第二年
fig, ax = plt.subplots(figsize=(12, 6.75), dpi=100)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
groups = [("英伟达", "2023", 239, "2024", 171, "#76b900"), ("Palantir", "2024", 340, "2025", 135, "#6aa8ff")]
x = 0
for name, y1, r1, y2, r2, color in groups:
    for dx, yr, val, alpha in ((0, y1, r1, 1.0), (1, y2, r2, 0.55)):
        ax.bar(x + dx, val, width=0.8, color=color, alpha=alpha)
        ax.text(x + dx, val + 8, f"+{val}%", ha="center", color=color, fontsize=26, fontweight="bold")
        ax.text(x + dx, -28, f"{yr} 年", ha="center", color=MUT, fontsize=15)
    ax.text(x + 0.5, -58, name, ha="center", color=FG, fontsize=18)
    x += 3
ax.set_ylim(-70, 400)
ax.set_xlim(-0.8, 5.8)
ax.axis("off")
ax.set_title("当年涨幅冠军，第二年还在涨", color=FG, fontsize=26, loc="left", pad=16)
fig.text(0.99, 0.02, "全年涨幅，年末对年末｜数据：Yahoo Finance", color="#666", fontsize=11, ha="right")
fig.tight_layout()
fig.savefig(f"{out}/champion_next_year.png", facecolor=BG)

# 图 2：五万存款算账卡
fig = plt.figure(figsize=(12, 6.75), dpi=100)
fig.patch.set_facecolor(BG)
rows = [("存款", "50,000"), ("× 年化收益（美债，约）", "4%"), ("= 一年利息", "2,000"), ("÷ 12 个月", "≈ 166 / 月")]
fig.text(0.07, 0.86, "存款五万，算一下财富自由", color=FG, fontsize=30)
for i, (k, v) in enumerate(rows):
    y = 0.66 - i * 0.13
    fig.text(0.09, y, k, color=MUT, fontsize=24)
    fig.text(0.91, y, v, color="#f0b34a" if i == 3 else FG, fontsize=30 if i == 3 else 26, ha="right", fontweight="bold" if i == 3 else "normal")
fig.add_artist(plt.Line2D([0.07, 0.93], [0.255, 0.255], color="#333", lw=1))
fig.text(0.07, 0.13, "够在海边喝两杯咖啡", color=FG, fontsize=22)
fig.text(0.93, 0.05, "单位：元｜利率为示意，非投资建议", color="#666", fontsize=11, ha="right")
fig.savefig(f"{out}/50k_math.png", facecolor=BG)
print(out)
