"""Articulatory compensation for an anatomy change.

Move Kanon's 13 VTL anatomy parameters in a straight line to a target
anatomy while the articulation of /a/, /i/, /u/ follows the iso-formant set
(F1-F3 of all three vowels held at Kanon's values), i.e. along the kernel of
the Jacobian of the 9 log formants with respect to anatomy + articulation.

Articulation is written in the reference speaker's coordinates, so that
"no compensation" is VTL's own adaptation (AnatomyParams::adaptArticulation,
what the GUI does when the anatomy is changed) and the compensation is the
deviation from it.

Run from the repository root (after building build-mac/vtlmap.so):
    python3 experiments/anatomy-compensation/compensate.py W02 F15
Writes results/<target>/: path.json, speaker files (compensated and naive)
and WAVs of /a i u/ for the original, naive and compensated speakers.
"""
import argparse
import ctypes as ct
import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "vtlmap"))
import vtlmap as vm  # noqa: E402

ROOT = vm.ROOT
SPEAKER = ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vtl24.speaker"
REFERENCE = ROOT / "speakers/JD2.speaker"     # only for the reference-chart ranges
FIXED = ("TRX", "TRY", "VO")                   # TRX/TRY are computed by VTL, VO closed
MIN_AREA = 0.12                                # cm^2 before the tongue-side floor (contact)
H = 0.01                                       # difference step, fraction of each range
TOL = 5e-3                                     # max |log F - log F_kanon| (0.5%)
OUT = HERE / "results"


def targets():
    return {
        "W02": dict(theta=vm.Tract(ROOT / "speakers/W02.speaker").anatomy(),
                    label="W02.speaker (adult female, MRI)"),
        "F15": dict(theta=vm.anatomy_from_age(15 * 12, male=False),
                    label="VTL age model, female 15 y"),
    }


LOG_SCALE = (np.log(0.6), np.log(1.2))         # range of the common formant scale k


class Problem:
    """z = [anatomy (13), articulation of each vowel (free params)], all
    normalised to [0, 1] by their ranges; y = log F1-F3 of each vowel.

    With scale=True a last coordinate c sets a common formant scale k
    (log k from LOG_SCALE) and y = log F - log k: the vowels are then held
    only up to a uniform scaling of all formants, as when the same vowels
    are spoken by a larger speaker."""

    def __init__(self, vowels, scale=False):
        self.scale = scale
        self.tract = vm.Tract(SPEAKER)
        self.vowels = vowels
        self.names = self.tract.names
        self.theta0 = self.tract.anatomy()
        self.alo, self.ahi = vm.anatomy_bounds()
        self.qlo, self.qhi, _ = vm.Tract(REFERENCE).bounds()
        self.free = np.array([j for j, n in enumerate(self.names) if n not in FIXED])
        # Kanon's shapes in reference coordinates (fixed params kept as they are).
        self.q0 = {v: vm.unadapt(self.theta0, self.tract.shape(v)) for v in vowels}
        for v, q in self.q0.items():
            outside = [self.names[j] for j in self.free if not self.qlo[j] - 1e-9 <= q[j] <= self.qhi[j] + 1e-9]
            if outside:
                print(f"warning: /{v}/ outside the reference ranges in {outside}")
        self.na, self.nq = len(self.theta0), len(self.free)
        self._memo = {}

    # coordinates ---------------------------------------------------------
    def split(self, z):
        theta = self.alo + z[:self.na] * (self.ahi - self.alo)
        qs = {}
        for k, v in enumerate(self.vowels):
            q = self.q0[v].copy()
            zq = z[self.na + k * self.nq:self.na + (k + 1) * self.nq]
            q[self.free] = self.qlo[self.free] + zq * (self.qhi - self.qlo)[self.free]
            qs[v] = q
        return theta, qs

    def join(self, theta, qs, log_k=0.0):
        parts = [(theta - self.alo) / (self.ahi - self.alo)]
        for v in self.vowels:
            parts.append(((qs[v] - self.qlo) / (self.qhi - self.qlo))[self.free])
        if self.scale:
            parts.append([(log_k - LOG_SCALE[0]) / (LOG_SCALE[1] - LOG_SCALE[0])])
        return np.concatenate(parts)

    def log_k(self, z):
        """Common log formant scale (0 without scale)."""
        return LOG_SCALE[0] + z[-1] * (LOG_SCALE[1] - LOG_SCALE[0]) if self.scale else 0.0

    def shapes(self, z):
        """Absolute VTL parameters at the anatomy of z."""
        theta, qs = self.split(z)
        return theta, {v: vm.adapt(theta, q) for v, q in qs.items()}

    # the map -------------------------------------------------------------
    def measure(self, theta, v, x):
        key = (theta.tobytes(), v, x.tobytes())
        if key not in self._memo:
            if len(self._memo) > 20000:
                self._memo.clear()
            self.tract.set_anatomy(theta)
            f, level, area, count = self.tract.peaks(x, 3)
            self._memo[key] = (f, area, count)
        return self._memo[key]

    def __call__(self, z):
        theta, xs = self.shapes(z)
        out = []
        for v in self.vowels:
            f, area, count = self.measure(theta, v, xs[v])
            if count < 3:
                raise vm.Invalid(f"/{v}/ lost a formant")
            out.append(np.log(f))
        return np.concatenate(out) - self.log_k(z)

    def min_areas(self, z):
        theta, xs = self.shapes(z)
        return {v: self.measure(theta, v, xs[v])[1] for v in self.vowels}

    def formants_hz(self, y, log_k=0.0):
        """Formants in Hz from y (pass log_k to undo the common scale)."""
        return {v: np.exp(y[3 * k:3 * k + 3] + log_k).round(1).tolist() for k, v in enumerate(self.vowels)}


def naive(problem, z0, theta):
    """VTL's own adaptation: Kanon's reference-chart articulation, new anatomy."""
    z = z0.copy()
    z[:problem.na] = (theta - problem.alo) / (problem.ahi - problem.alo)
    return z


def near_bounds(problem, z, margin=0.02):
    zq = z[problem.na:problem.na + len(problem.vowels) * problem.nq].reshape(len(problem.vowels), problem.nq)
    names = [problem.names[j] for j in problem.free]
    return {v: [n for n, a in zip(names, row) if min(a, 1 - a) < margin] for v, row in zip(problem.vowels, zq)}


def write_speakers(problem, z_end, theta, folder, name):
    """Compensated speaker (a, i, u from the path, the other shapes adapted by
    VTL's rule) and the naive speaker (every shape adapted by VTL's rule)."""
    tract = vm.Tract(SPEAKER)
    tract.set_anatomy(theta)
    shapes = {s: tract.shape(s) for s in tract.shape_names()}
    for s, x in shapes.items():
        tract.set_shape(s, vm.adapt(theta, vm.unadapt(problem.theta0, x)))
    naive_path = folder / f"{name}-naive.speaker"
    tract.write_speaker(naive_path, SPEAKER)
    _, xs = problem.shapes(z_end)
    for v, x in xs.items():
        tract.set_shape(v, x)
    comp_path = folder / f"{name}.speaker"
    tract.write_speaker(comp_path, SPEAKER)
    return naive_path, comp_path


# ---------------------------------------------------------------------------
# Audio through the VTL API (static vowels a i u).
# ---------------------------------------------------------------------------
API = Path(os.environ.get("VTL_LIB", ROOT / "build-mac/gui/libVocalTractLabApi.dylib"))


def render_vowels(speaker, wav, vowels):
    api = ct.CDLL(str(API))
    seg = wav.with_suffix(".seg")
    lines = ["name = ; duration_s = 0.15;"]
    for v in vowels:
        lines.append(f"name = {v}; duration_s = 0.45; f0_20%_Hz = 220; f0_50%_Hz = 220; f0_80%_Hz = 215;")
        lines.append("name = ; duration_s = 0.2;")
    seg.write_text("\n".join(lines) + "\n")
    ges = wav.with_suffix(".ges")
    assert api.vtlInitialize(str(speaker).encode()) == 0, speaker
    try:
        assert api.vtlSegmentSequenceToGesturalScore(str(seg).encode(), str(ges).encode()) == 0
        assert api.vtlGesturalScoreToAudio(str(ges).encode(), str(wav).encode(), b"", None, None, 1, 0) == 0
    finally:
        api.vtlClose()
    seg.unlink()
    ges.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="*", default=["W02", "F15"])
    ap.add_argument("--vowels", default="a,i,u")
    ap.add_argument("--scale", action="store_true",
                    help="hold the formants only up to a common scale factor")
    args = ap.parse_args()
    vowels = args.vowels.split(",")
    vm.set_reference(None)          # VTL's built-in template, which Kanon was made from
    problem = Problem(vowels, scale=args.scale)
    z0 = problem.join(problem.theta0, problem.q0)
    y0 = problem(z0)
    print("Kanon", problem.formants_hz(y0), "min areas", problem.min_areas(z0))
    OUT.mkdir(exist_ok=True)
    render_vowels(SPEAKER, OUT / "kanon.wav", vowels)

    n = len(z0)
    free_lower = np.zeros(n - problem.na)
    free_upper = np.ones(n - problem.na)
    anatomy_names = vm.anatomy_names()

    for name in args.targets:
        spec = targets()[name]
        theta_t = vm.restrict_anatomy(spec["theta"])
        folder = OUT / (f"{name}-scaled" if args.scale else name)
        folder.mkdir(exist_ok=True)
        zt = (theta_t - problem.alo) / (problem.ahi - problem.alo)

        def accept(z, y):
            return min(problem.min_areas(z).values()) >= MIN_AREA

        def log(step):
            theta, _ = problem.split(step.z)
            # The naive point at the same anatomy, for comparison.
            try:
                yn = problem(naive(problem, z0, theta))
                naive_err = float(np.max(np.abs(yn - y0)))
            except vm.Invalid:
                yn, naive_err = None, None
            step.info.update(naive_error=naive_err, formant_scale=float(np.exp(problem.log_k(step.z))),
                             naive_formants=problem.formants_hz(yn) if yn is not None else None,
                             min_area=problem.min_areas(step.z))
            print(f"{name} s={step.s:.3f} k={step.info['formant_scale']:.3f} ds={step.info.get('ds', 0):.4f} it={step.info.get('iterations')} residual={step.residual:.4f} naive={naive_err} "
                  f"areas={ {v: round(a, 3) for v, a in step.info['min_area'].items()} }", flush=True)

        path = vm.follow(problem, z0, np.arange(problem.na), zt, free_lower, free_upper, H,
                         y_target=y0, ds=0.05, ds_max=0.1, ds_min=1e-3, tol=TOL,
                         accept=accept, on_step=log, scheme="minmod")
        end = path[-1]
        theta_end, xs_end = problem.shapes(end.z)
        _, xs_naive = problem.shapes(naive(problem, z0, theta_end))
        record = dict(
            target=name, label=spec["label"] + (", formants up to a common scale" if args.scale else ""),
            scaled=args.scale, reached=end.s >= 1 - 1e-9, s_end=end.s,
            anatomy=dict(names=anatomy_names, kanon=problem.theta0.tolist(),
                         target=theta_t.tolist(), end=theta_end.tolist()),
            params=problem.names, free=[problem.names[j] for j in problem.free],
            kanon_formants=problem.formants_hz(y0),
            near_bounds=dict(start=near_bounds(problem, z0), end=near_bounds(problem, end.z)),
            end_shapes={v: x.tolist() for v, x in xs_end.items()},
            naive_shapes={v: x.tolist() for v, x in xs_naive.items()},
            path=[dict(s=st.s, residual=st.residual, z=st.z.tolist(),
                       formants=problem.formants_hz(st.y, problem.log_k(st.z)), **st.info) for st in path])
        (folder / "path.json").write_text(json.dumps(record, indent=1))
        naive_spk, comp_spk = write_speakers(problem, end.z, theta_end, folder, f"kanon-{folder.name}")
        render_vowels(naive_spk, folder / "naive.wav", vowels)
        render_vowels(comp_spk, folder / "compensated.wav", vowels)
        print(name, "reached" if record["reached"] else f"stopped at s={end.s:.3f}",
              "near bounds at end", record["near_bounds"]["end"])


if __name__ == "__main__":
    main()
