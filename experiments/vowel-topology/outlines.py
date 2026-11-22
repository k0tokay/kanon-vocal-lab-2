"""Draw VTL midsagittal outlines of sampled shapes next to the speaker's shapes.

For each speaker shape given, the nearest sampled point of the band is drawn
over it; a second figure shows a spread of the band picked by farthest-point
sampling, each over the static vowel.
"""
import argparse
import ctypes
import re
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import sample
from sample import active, high, low


def outline(lib, x):
    """Polylines of the VTL SVG export as a list of (k, 2) arrays."""
    with tempfile.NamedTemporaryFile(suffix=".svg") as f:
        assert lib.vtlExportTractSvg(np.ascontiguousarray(x).ctypes.data_as(ctypes.POINTER(ctypes.c_double)), f.name.encode()) == 0
        text = Path(f.name).read_text()
    return [np.array(p.split(), float).reshape(-1, 2) for p in re.findall(r'points="([^"]*)"', text)]


def full(z, base):
    x = base.copy()
    x[active] = low[active] + z*(high-low)[active]
    return x


def draw(ax, lines, label=None, **kw):
    for k, p in enumerate(lines):
        ax.plot(p[:, 0], -p[:, 1], **kw, label=label if k == 0 else None)


def frame(ax, title):
    ax.set_title(title, fontsize=8)
    ax.set_aspect("equal")
    ax.set_xlim(-110, 175)
    ax.set_ylim(-225, 65)
    ax.axis("off")


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("samples", type=Path)
    parser.add_argument("--shapes", nargs="*", default=[], help="speaker shapes to match, e.g. a-compare")
    parser.add_argument("--eps", type=float, default=.01)
    parser.add_argument("--spread", type=int, default=12)
    args = parser.parse_args()
    data = np.load(args.samples)
    vowel = str(data["vowel"]) if "vowel" in data else "a"
    X, E = data["points"][data["errors"] <= args.eps], data["errors"][data["errors"] <= args.eps]
    base = sample.shape(vowel)
    lib = ctypes.CDLL(str(sample.root / "build-mac/gui/libVocalTractLabApi.dylib"))
    assert lib.vtlInitialize(str(sample.speaker).encode()) == 0
    static = outline(lib, base)
    out = args.samples.parent

    if args.shapes:
        fig, axes = plt.subplots(1, len(args.shapes), figsize=(4*len(args.shapes), 4.4), squeeze=False, constrained_layout=True)
        for ax, name in zip(axes[0], args.shapes):
            x = sample.shape(name)
            z = (x[active]-low[active])/(high-low)[active]
            d = np.linalg.norm(X-z, axis=1)
            j = d.argmin()
            draw(ax, static, color="0.75", lw=1, label=f"/{vowel}/ static")
            draw(ax, outline(lib, x), color="tab:red", lw=1.2, label=name)
            draw(ax, outline(lib, full(X[j], base)), color="tab:blue", lw=1.2, ls="--", label=f"nearest sample (error {E[j]:.4f})")
            frame(ax, f"{name}: distance to nearest sample {d[j]:.2f}\n(to /{vowel}/ static {np.linalg.norm(z-(base[active]-low[active])/(high-low)[active]):.2f})")
            ax.legend(fontsize=7, loc="lower left")
        fig.savefig(out / f"outlines-compare-{args.eps}.png", dpi=150)

    rng = np.random.default_rng(0)
    pick = [int(rng.integers(len(X)))]
    gap = np.linalg.norm(X-X[pick[0]], axis=1)
    while len(pick) < args.spread:
        pick.append(int(gap.argmax()))
        gap = np.minimum(gap, np.linalg.norm(X-X[pick[-1]], axis=1))
    cols = 6
    fig, axes = plt.subplots(int(np.ceil(len(pick)/cols)), cols, figsize=(2.6*cols, 2.8*np.ceil(len(pick)/cols)), constrained_layout=True)
    for ax, j in zip(axes.flat, pick):
        draw(ax, static, color="0.75", lw=.8)
        draw(ax, outline(lib, full(X[j], base)), color="tab:blue", lw=1)
        frame(ax, f"#{j} error {E[j]:.4f}")
    for ax in axes.flat[len(pick):]:
        ax.axis("off")
    fig.suptitle(f"/{vowel}/: {len(pick)} spread-out samples with error ≤ {args.eps} (grey: static /{vowel}/)")
    fig.savefig(out / f"outlines-spread-{args.eps}.png", dpi=130)
