"""Figure of the WORLD statistics: JVS women (mean and 5-95 % range) against v1.1.0."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common import HERE, MEL_F

plt.rcParams.update({"font.family": ["Hiragino Sans", "sans-serif"], "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#c3c2b7", "axes.labelcolor": "#52514e", "xtick.color": "#52514e", "ytick.color": "#52514e"})
D = json.loads((HERE / "out/stats.json").read_text())
Q = np.arange(33) * 200 / 64


def panel(ax, key, x, title, xl, yl, sl=slice(None), log=False):
    P = np.array([p[key] for p in D["pop"].values()])[:, sl]; x = np.asarray(x)[sl]
    ax.fill_between(x, *np.nanpercentile(P, [5, 95], 0), color="#d9d8d1", lw=0, label="JVS女性51名（5〜95%）")
    ax.plot(x, np.nanmean(P, 0), color="#52514e", lw=1.5, label="JVS女性の平均")
    C = np.mean([v[key] for k, v in D["vtl"].items() if k != "rule"], 0)[sl]
    ax.plot(x, C, color="#2a78d6", lw=2, label="v1.1.0（実声の時間・F0を写す）")
    ax.plot(x, np.array(D["vtl"]["rule"][key])[sl], color="#eb6834", lw=2, label="v1.1.0（ルール韻律）")
    ax.set_title(title, fontsize=11, loc="left", color="#0b0b0b"); ax.set_xlabel(xl); ax.set_ylabel(yl)
    ax.grid(axis="y", color="#e1e0d9", lw=.6); ax.set_axisbelow(True)
    if log:
        ax.set_xscale("log"); ax.set_xticks([125, 250, 500, 1000, 2000, 4000, 7000]); ax.set_xticklabels(["125", "250", "500", "1k", "2k", "4k", "7k"]); ax.minorticks_off()


fig, ax = plt.subplots(2, 3, figsize=(15, 8.2))
panel(ax[0, 0], "ltas", MEL_F, "有声区間の平均スペクトル", "周波数 (Hz)", "200–1000 Hz比 (dB)", log=True)
panel(ax[0, 1], "uv", MEL_F, "無声区間の平均スペクトル", "周波数 (Hz)", "有声200–1000 Hz比 (dB)", log=True)
panel(ax[0, 2], "msd", MEL_F, "スペクトル形状の時間変動（有声区間）", "周波数 (Hz)", "標準偏差 (dB)", log=True)
panel(ax[1, 0], "nhr_hist", np.arange(-39, 21, 2), "3 kHz帯の雑音/調波比の分布（有声区間）", "雑音/調波比 (dB)", "密度")
panel(ax[1, 1], "am", Q, "雑音/調波比の変動スペクトル（3 kHz帯）", "変動の速さ (Hz)", "dB", slice(1, 25))
panel(ax[1, 2], "fm", Q, "F0の変動スペクトル", "変動の速さ (Hz)", "dB re 1 cent²/Hz", slice(1, 25))
h, l = ax[0, 0].get_legend_handles_labels()
fig.legend(h, l, loc="upper center", ncol=4, frameon=False)
fig.tight_layout(rect=(0, 0, 1, .95)); fig.savefig(HERE / "results/stats.png", dpi=110, facecolor="white")
