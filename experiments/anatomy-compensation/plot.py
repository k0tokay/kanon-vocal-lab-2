"""Figures for compensate.py results.

Run from the repository root:
    python3 experiments/anatomy-compensation/plot.py W02 F15
Writes results/<target>/{outlines,areas,path,params}.png.
"""
import ctypes as ct
import json
import re
import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "vtlmap"))
import vtlmap as vm  # noqa: E402
from compensate import API, OUT, SPEAKER  # noqa: E402

STYLE = {"Kanon": dict(color="0.55", lw=1.2), "naive": dict(color="tab:blue", lw=1, ls="--"),
         "compensated": dict(color="tab:red", lw=1.2)}


def outlines(speaker, shapes):
    """VTL midsagittal outlines (SVG export) of the given parameter vectors."""
    api = ct.CDLL(str(API))
    assert api.vtlInitialize(str(speaker).encode()) == 0
    out = []
    try:
        for x in shapes:
            with tempfile.NamedTemporaryFile(suffix=".svg") as f:
                x = np.ascontiguousarray(x, float)
                assert api.vtlExportTractSvg(x.ctypes.data_as(ct.POINTER(ct.c_double)), f.name.encode()) == 0
                text = Path(f.name).read_text()
            out.append([np.array(p.split(), float).reshape(-1, 2)
                        for p in re.findall(r'points="([^"]*)"', text)])
    finally:
        api.vtlClose()
    return out


def main(names):
    vm.set_reference(None)
    kanon = vm.Tract(SPEAKER)
    for name in names:
        folder = OUT / name
        rec = json.loads((folder / "path.json").read_text())
        vowels = list(rec["end_shapes"])
        orig = {v: kanon.shape(v) for v in vowels}
        naive = {v: np.array(x) for v, x in rec["naive_shapes"].items()}
        comp = {v: np.array(x) for v, x in rec["end_shapes"].items()}
        sets = {"Kanon": (SPEAKER, orig), "naive": (folder / f"kanon-{name}-naive.speaker", naive),
                "compensated": (folder / f"kanon-{name}.speaker", comp)}
        title = f"Kanon → {rec['label']}" + ("" if rec["reached"] else f" (stopped at s = {rec['s_end']:.2f})")

        # Midsagittal outlines.
        fig, axes = plt.subplots(1, len(vowels), figsize=(4 * len(vowels), 4.2))
        for label, (spk, shapes) in sets.items():
            for ax, lines in zip(axes, outlines(spk, [shapes[v] for v in vowels])):
                for k, p in enumerate(lines):
                    ax.plot(p[:, 0], -p[:, 1], **STYLE[label], label=label if k == 0 else None)
        for ax, v in zip(axes, vowels):
            ax.set_title(f"/{v}/")
            ax.set_aspect("equal")
            ax.axis("off")
        axes[0].legend(fontsize=8, loc="lower left")
        fig.suptitle(title, fontsize=10)
        fig.tight_layout()
        fig.savefig(folder / "outlines.png", dpi=130)
        plt.close(fig)

        # Area functions.
        fig, axes = plt.subplots(1, len(vowels), figsize=(4 * len(vowels), 3), sharey=True)
        for label, (spk, shapes) in sets.items():
            t = vm.Tract(spk)
            for ax, v in zip(axes, vowels):
                pos, area = t.area_function(shapes[v])
                ax.step(pos, area, where="post", **STYLE[label], label=label)
        for ax, v in zip(axes, vowels):
            ax.set_title(f"/{v}/")
            ax.set_xlabel("distance from glottis [cm]")
        axes[0].set_ylabel("area [cm²]")
        axes[0].legend(fontsize=8)
        fig.suptitle(title, fontsize=10)
        fig.tight_layout()
        fig.savefig(folder / "areas.png", dpi=130)
        plt.close(fig)

        # Along the path: formant error without compensation, size of the compensation.
        path = rec["path"]
        s = np.array([p["s"] for p in path])
        target = {v: np.array(f) for v, f in rec["kanon_formants"].items()}
        fig, axes = plt.subplots(1, 2, figsize=(10, 3.2))
        for k, v in enumerate(vowels):
            for j in range(3):
                err = [100 * (p["naive_formants"][v][j] / target[v][j] - 1) if p["naive_formants"] else np.nan
                       for p in path]
                axes[0].plot(s, err, color=f"C{k}", ls=["-", "--", ":"][j], label=f"/{v}/ F{j + 1}")
        axes[0].set_xlabel("s (0 = Kanon, 1 = target anatomy)")
        axes[0].set_ylabel("formant change without compensation [%]")
        axes[0].legend(fontsize=7, ncol=3)
        na = len(rec["anatomy"]["names"])
        nq = len(rec["free"])
        z = np.array([p["z"] for p in path])
        for k, v in enumerate(vowels):
            dq = z[:, na + k * nq:na + (k + 1) * nq] - z[0, na + k * nq:na + (k + 1) * nq]
            axes[1].plot(s, np.linalg.norm(dq, axis=1), color=f"C{k}", label=f"/{v}/")
        axes[1].set_xlabel("s")
        axes[1].set_ylabel("|Δ articulation| (reference chart, range units)")
        axes[1].legend(fontsize=8)
        fig.suptitle(title, fontsize=10)
        fig.tight_layout()
        fig.savefig(folder / "path.png", dpi=130)
        plt.close(fig)

        # Per-parameter compensation at the end.
        fig, ax = plt.subplots(figsize=(10, 3.2))
        width = 0.8 / len(vowels)
        for k, v in enumerate(vowels):
            dq = z[-1, na + k * nq:na + (k + 1) * nq] - z[0, na + k * nq:na + (k + 1) * nq]
            ax.bar(np.arange(nq) + (k - (len(vowels) - 1) / 2) * width, dq, width, label=f"/{v}/")
        ax.axhline(0, color="0.3", lw=.6)
        ax.set_xticks(np.arange(nq), rec["free"], fontsize=8)
        ax.set_ylabel("compensation (fraction of range)")
        ax.legend(fontsize=8)
        ax.set_title(title, fontsize=10)
        fig.tight_layout()
        fig.savefig(folder / "params.png", dpi=130)
        plt.close(fig)
        print("wrote", folder)


if __name__ == "__main__":
    main(sys.argv[1:] or ["W02", "F15"])
