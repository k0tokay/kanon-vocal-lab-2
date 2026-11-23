"""How much of the lost formant height can larynx raising buy back?

Start from the end of a `compensate.py --scale --raise pharynx_length` run
(target anatomy, Kanon's vowels up to a common formant scale k < 1). Hold
the anatomy and drive k back towards 1 while the articulation of /a i u/
and the pharynx shortening are free; the shortening is made cheap in the
step metric, so the path uses it before it bends the articulation. The
curve k(shortening) says how far a raised larynx alone can lift the vowels.

    python3 experiments/anatomy-compensation/raise_scale.py F15 W02
Writes results/<target>-scaled-raised/raise_scale.json and raise_scale.png.
"""
import argparse
import json

import numpy as np

import compensate as cp
from compensate import vm

DEPTH = 3.0          # cm: allow more than compensate.RAISE_DEPTH to see the whole curve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="*", default=["F15", "W02"])
    ap.add_argument("--weight", type=float, default=0.1, help="metric weight of the shortening")
    args = ap.parse_args()
    vm.set_reference(None)
    old_depth = cp.RAISE_DEPTH
    cp.RAISE_DEPTH = DEPTH
    problem = cp.Problem(["a", "i", "u"], scale=True, raise_params=["pharynx_length"])
    y0 = problem(problem.join(problem.theta0, problem.q0))
    for name in args.targets:
        folder = cp.OUT / f"{name}-scaled-raised"
        rec = json.loads((folder / "path.json").read_text())
        z = np.array(rec["path"][-1]["z"])
        k0 = problem.na + len(problem.vowels) * problem.nq
        d = old_depth * (1 - z[k0])                 # shortening in cm, re-expressed for DEPTH
        z[k0] = 1 - d / DEPTH
        driven = np.r_[np.arange(problem.na), len(z) - 1]
        target = z[driven].copy()
        target[-1] = (0.0 - cp.LOG_SCALE[0]) / (cp.LOG_SCALE[1] - cp.LOG_SCALE[0])   # k = 1
        nfree = len(z) - len(driven)
        weights = np.ones(nfree)
        weights[k0 - problem.na] = args.weight

        def accept(z, y):
            return min(problem.min_areas(z).values()) >= cp.MIN_AREA

        rows = []

        def log(step):
            row = dict(s=step.s, k=float(np.exp(problem.log_k(step.z))),
                       shortening=float(problem.shortening(step.z)[0]),
                       pharynx=float(problem.split(step.z)[0][8]),
                       min_area={v: round(a, 3) for v, a in problem.min_areas(step.z).items()},
                       formants=problem.formants_hz(step.y, problem.log_k(step.z)))
            rows.append(row)
            print(f"{name} s={step.s:.3f} k={row['k']:.3f} shortening={row['shortening']:.3f} cm "
                  f"pharynx={row['pharynx']:.2f} areas={row['min_area']}", flush=True)

        path = vm.follow(problem, z, driven, target, np.zeros(nfree), np.ones(nfree), cp.H,
                         y_target=y0, ds=0.05, ds_max=0.1, ds_min=1e-3, tol=cp.TOL,
                         accept=accept, on_step=log, scheme="minmod", weights=weights)
        stopped = path[-1].info.get("stopped")
        (folder / "raise_scale.json").write_text(json.dumps(dict(
            target=name, weight=args.weight, depth=DEPTH, stopped=stopped, rows=rows,
            z_end=path[-1].z.tolist()), indent=1))
        print(name, "reached k=1" if path[-1].s >= 1 - 1e-9 else f"stopped at k={rows[-1]['k']:.3f}: {stopped}")

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(4.5, 3.2), constrained_layout=True)
        ax.plot([r["shortening"] for r in rows], [r["k"] for r in rows], "o-")
        ax.set(xlabel="pharynx shortening (cm)", ylabel="common formant scale k",
               title=f"{name}: raising the larynx at the target anatomy")
        fig.savefig(folder / "raise_scale.png", dpi=150)


if __name__ == "__main__":
    main()
