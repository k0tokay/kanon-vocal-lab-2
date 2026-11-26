"""Adduction and abduction at another register: LCA, IA, PCA that give a consonant's glottal
opening (vocal process position VP, posterior opening PGO) when TA and CT are those of modal.

    ./run.sh invert.py [speaker]     -> prints the shapes and writes build/inverted.json

The opening of a shape is computed with build/posture_map at 220 Hz and 8000 dPa (static
posture under F0 control, no vibration). TA changes the strain that the F0 control chooses,
and with it the posterior opening, so the old muscle values do not give the old opening.
"""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
import variants

HERE = Path(__file__).resolve().parent


class Posture:
    def __init__(self, speaker):
        self.p = subprocess.Popen([str(HERE / "build/posture_map"), str(speaker)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True, bufsize=1)

    def __call__(self, lca, ia, pca, ct, ta, f0=220.0, pressure=8000.0):
        self.p.stdin.write(f"{f0} {pressure} {lca} {ia} {pca} {ct} {ta}\n")
        s, vp, pgo, nf0, op = map(float, self.p.stdout.readline().split())
        return vp, pgo


def invert(post, target, ct, ta, start):
    vp0, pgo0 = target

    def cost(x):
        x = np.clip(x, 0, 1)
        vp, pgo = post(*x, ct, ta)
        # 0.05 mm and 0.1 mm^2; a weak pull towards the old values and towards PCA = 0
        return ((vp - vp0) / .05) ** 2 + ((pgo - pgo0) / .1) ** 2 + .1 * np.sum((x - start) ** 2) + x[2] ** 2

    best = None
    for s in (start, start + [0, 0, .1], start * [.7, .7, 1], start * [1.2, 1.2, 1]):
        r = minimize(cost, np.clip(s, 0, 1), method="Nelder-Mead", options=dict(xatol=1e-4, fatol=1e-4, maxiter=600))
        if best is None or r.fun < best.fun:
            best = r
    x = np.clip(best.x, 0, 1)
    return x, post(*x, ct, ta)


def main(speaker=variants.BASE):
    post = Posture(speaker)
    sh = variants.shapes(speaker)
    I = variants.IDX
    modal = sh["modal"]
    ct, ta = modal[I["ct"]], modal[I["ta"]]
    out = {}
    print(f"{'shape':20} {'old LCA IA PCA':>18} {'VP':>6} {'PGO':>6} | {'new LCA IA PCA':>18} {'VP':>6} {'PGO':>6}  (TA {ta:.3f}, CT {ct:.3f})")
    for name in variants.CONSONANT_SHAPES:
        v = sh[name]
        old = np.array([v[I["lca"]], v[I["ia"]], v[I["pca"]]])
        target = post(*old, v[I["ct"]], v[I["ta"]])
        x, got = invert(post, target, ct, ta, old)
        out[name] = dict(lca=float(x[0]), ia=float(x[1]), pca=float(x[2]), ct=ct, ta=ta,
                         flutter=modal[I["flutter"]], target=target, got=got)
        print(f"{name:20} {old[0]:6.3f}{old[1]:6.3f}{old[2]:6.3f} {target[0]:6.3f} {target[1]:6.2f} | "
              f"{x[0]:6.3f}{x[1]:6.3f}{x[2]:6.3f} {got[0]:6.3f} {got[1]:6.2f}")
    (HERE / "build/inverted.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    main(*sys.argv[1:])
