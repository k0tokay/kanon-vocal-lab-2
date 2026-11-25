"""Render accent test sentences with and without accent commands.

Run from the repository root:
    python3 experiments/japanese-accent/run.py
Needs pyopenjtalk, numpy, scipy, matplotlib and the macOS API build
(set VTL_LIB to point at libVocalTractLabApi.dylib if it is elsewhere).
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from accent import Mora, render

OUT = Path(__file__).resolve().parent / "results"
SENTENCES = {
    "hashi-chopsticks": "箸がある。",
    "hashi-bridge": "橋がある。",
    "hashi-edge": "端がある。",
    "tenki": "今日はいい天気ですね。",
    "ame": "雨が降っていますが、私は傘を持っていません。",
}


def main():
    summary = {}
    fig, axes = plt.subplots(len(SENTENCES), 1, figsize=(9, 2.2 * len(SENTENCES)))
    for ax, (key, text) in zip(axes, SENTENCES.items()):
        r = render(text, OUT / key, f0_model=None)
        flat = render(text, OUT / f"{key}-monotone", accent=False)
        ax.plot(r["t"], r["f0"], label="accent")
        ax.plot(flat["t"], flat["f0"], "--", lw=.8, label="phrase only")
        for s in r["segments"]:
            if s.name:
                ax.text(s.t0 + s.duration / 2, ax.get_ylim()[0] if False else 150, s.name,
                        ha="center", fontsize=7)
        ax.set_ylim(140, 330)
        ax.set_title(key, fontsize=9)
        ax.set_ylabel("F0 Hz")
        summary[key] = dict(
            text=text,
            moras=[f"{u.consonant}{u.vowel}:{u.accent_type}/{u.position}" for u in r["units"] if isinstance(u, Mora)],
            segments=[[s.name, round(s.duration, 4)] for s in r["segments"]],
            phrase_commands=r["phrases"], accent_commands=r["accents"])
    axes[0].legend(fontsize=7)
    axes[-1].set_xlabel("time s")
    fig.tight_layout()
    fig.savefig(OUT / "f0.png", dpi=120)
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
