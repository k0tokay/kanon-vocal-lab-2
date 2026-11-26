"""Time course of the TBCM in a sentence: muscle activity, F0, leak and AC flow.

    ./run.sh plot.py out.png variant:sentence [variant:sentence ...]
"""
import re, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import diag

plt.rcParams["font.family"] = ["Hiragino Sans", "sans-serif"]


def segs(path):
    out, t = [], 0
    for l in open(path):
        m = re.match(r"name = ([^;]*); duration_s = ([\d.]+);", l)
        out.append((m.group(1), t, t + float(m.group(2))))
        t += float(m.group(2))
    return out


def smooth(x, n):
    return np.convolve(x, np.ones(n) / n, "same")


def main(out, items):
    fig, axes = plt.subplots(4, len(items), figsize=(7 * len(items), 9), sharex="col", squeeze=False)
    for c, item in enumerate(items):
        v, s = item.split(":")
        L = diag.load(diag.OUT / v / f"{s}.f32")
        t = np.arange(len(L["flow"])) / diag.FS
        k = slice(None, None, 48)
        ax = axes[0, c]
        for m, col in (("lca", "C0"), ("ia", "C1"), ("pca", "C2"), ("ct", "C3"), ("ta", "C4")):
            ax.plot(t[k], L[m][k], col, label=m.upper())
        ax.set_ylabel("活動")
        ax.legend(ncol=5, fontsize=8, loc="upper right")
        ax.set_title(item)
        ax = axes[1, c]
        mf = L["measured_f0"].copy()
        mf[mf <= 0] = np.nan
        ax.plot(t[k], L["f0"][k], "k", lw=.8, label="目標")
        ax.plot(t[k], mf[k], "C3", lw=.8, label="測定")
        ax.set_ylabel("F0 (Hz)")
        ax.set_ylim(120, 340)
        ax.legend(fontsize=8)
        ax = axes[2, c]
        n = int(diag.FS / 200)
        mn = np.array([L["flow"][max(0, i - n):i + n].min() for i in range(0, len(t), 48)])
        mx = np.array([L["flow"][max(0, i - n):i + n].max() for i in range(0, len(t), 48)])
        ax.plot(t[k], mn, "C0", label="流れの最小(漏れ)")
        ax.plot(t[k], mx - mn, "C1", label="流れの振幅")
        ax.set_ylabel("cm³/s")
        ax.set_ylim(0, 400)
        ax.legend(fontsize=8)
        ax = axes[3, c]
        ax.plot(t[k], 100 * L["area_post"][k], "C2", label="後部の開口 (mm²)")
        ax.plot(t[k], 10 * L["vp"][k], "C5", label="声帯突起の位置 (mm)")
        ax.set_ylim(-.5, 6)
        ax.legend(fontsize=8)
        ax.set_xlabel("時間 (s)")
        for n_, a, b in segs(diag.OUT / v / f"{s}.seg"):
            for r in range(4):
                axes[r, c].axvline(a, color="0.85", lw=.5)
            axes[0, c].text((a + b) / 2, 1.02, n_, ha="center", fontsize=8)
        axes[0, c].set_ylim(0, 1.1)
    fig.tight_layout()
    fig.savefig(out, dpi=110)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
