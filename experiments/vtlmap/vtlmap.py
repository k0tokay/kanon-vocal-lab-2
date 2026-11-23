"""Maps out of VTL's anatomy and articulation spaces, and their Jacobians.

Two layers:

* `Tract` wraps the native library (vtlmap.cpp): anatomy parameters
  (AnatomyParams), VTL's articulation adaptation between anatomies,
  formants and area functions of static shapes, and writing speaker files.
* Generic numerics on any vector map `f(z) -> y` with box bounds on z:
  `jacobian` (central differences, one-sided at bounds), `null_space`,
  `bounded_step` (least squares with bounds and damping) and `follow`
  (predictor-corrector continuation that drives some coordinates along a
  path while the rest keep f constant).

Nothing in the numerics knows about VTL, so the same functions apply to
other acoustic features (more formants, consonant spectra, area functions).
"""
from __future__ import annotations

import ctypes as ct
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
from scipy.optimize import lsq_linear

ROOT = Path(__file__).resolve().parents[2]
LIB = Path(os.environ.get("VTLMAP_LIB", ROOT / "build-mac/vtlmap.so"))

_D = np.ctypeslib.ndpointer(np.float64, ndim=1, flags="C_CONTIGUOUS")
_lib = None


def lib():
    global _lib
    if _lib is None:
        if not LIB.exists():
            raise FileNotFoundError(
                f"{LIB} is missing; build it with\n  clang++ -shared -fPIC -std=c++14 -O2 -w -Ibackend "
                "experiments/vtlmap/vtlmap.cpp $(ls backend/*.cpp | grep -v SoundLib.cpp) -o build-mac/vtlmap.so")
        L = ct.CDLL(str(LIB))
        sig = {
            "vm_last_error": ([], ct.c_char_p), "vm_num_params": ([], ct.c_int),
            "vm_num_anatomy": ([], ct.c_int),
            "vm_param_names": ([ct.c_char_p, ct.c_int], None),
            "vm_anatomy_names": ([ct.c_char_p, ct.c_int], None),
            "vm_anatomy_bounds": ([_D, _D], None),
            "vm_set_reference": ([ct.c_char_p], ct.c_int),
            "vm_anatomy_from_age": ([ct.c_int, ct.c_int, _D], None),
            "vm_restrict_anatomy": ([_D], None),
            "vm_open": ([ct.c_char_p], ct.c_void_p), "vm_close": ([ct.c_void_p], None),
            "vm_get_anatomy": ([ct.c_void_p, _D], None),
            "vm_set_anatomy": ([ct.c_void_p, _D], None),
            "vm_param_bounds": ([ct.c_void_p, _D, _D, _D], None),
            "vm_get_shape": ([ct.c_void_p, ct.c_char_p, _D], ct.c_int),
            "vm_set_shape": ([ct.c_void_p, ct.c_char_p, _D], None),
            "vm_num_shapes": ([ct.c_void_p], ct.c_int),
            "vm_shape_name": ([ct.c_void_p, ct.c_int, ct.c_char_p, ct.c_int], None),
            "vm_adapt": ([_D, _D, _D], None), "vm_unadapt": ([_D, _D, _D], None),
            "vm_formants": ([ct.c_void_p, _D, ct.c_int, _D, _D, ct.POINTER(ct.c_double)], ct.c_int),
            "vm_peaks": ([ct.c_void_p, _D, ct.c_int, ct.c_int, ct.c_double, ct.c_double, _D, _D,
                          ct.POINTER(ct.c_double)], ct.c_int),
            "vm_area_function":([ct.c_void_p, _D, _D, _D, ct.c_int], ct.c_int),
            "vm_constriction": ([ct.c_void_p, _D, _D], None),
            "vm_write_tract":([ct.c_void_p, ct.c_char_p], ct.c_int),
        }
        for name, (args, res) in sig.items():
            fn = getattr(L, name)
            fn.argtypes, fn.restype = args, res
        _lib = L
    return _lib


def _names(fn):
    buf = ct.create_string_buffer(4096)
    fn(buf, len(buf))
    return buf.value.decode().split()


def param_names() -> list[str]:
    return _names(lib().vm_param_names)


def anatomy_names() -> list[str]:
    return _names(lib().vm_anatomy_names)


def anatomy_bounds():
    n = lib().vm_num_anatomy()
    lo, hi = np.empty(n), np.empty(n)
    lib().vm_anatomy_bounds(lo, hi)
    return lo, hi


def set_reference(path: str | Path | None):
    """Reference (template) speaker for anatomy changes; None keeps VTL's built-in one."""
    if lib().vm_set_reference(str(path or "").encode()):
        raise RuntimeError(lib().vm_last_error().decode())


def anatomy_from_age(months: int, male: bool) -> np.ndarray:
    theta = np.empty(lib().vm_num_anatomy())
    lib().vm_anatomy_from_age(months, int(male), theta)
    return theta


def restrict_anatomy(theta) -> np.ndarray:
    theta = np.array(theta, float)
    lib().vm_restrict_anatomy(theta)
    return theta


def adapt(theta, reference) -> np.ndarray:
    """VTL's articulation adaptation: reference-speaker coordinates -> anatomy theta."""
    x = np.empty(lib().vm_num_params())
    lib().vm_adapt(np.asarray(theta, float), np.asarray(reference, float), x)
    return x


def unadapt(theta, x) -> np.ndarray:
    ref = np.empty(lib().vm_num_params())
    lib().vm_unadapt(np.asarray(theta, float), np.asarray(x, float), ref)
    return ref


class Tract:
    """One speaker's vocal tract. Anatomy changes are cached, so evaluating
    many shapes at one anatomy rebuilds the geometry once."""

    def __init__(self, speaker: str | Path):
        self.speaker = Path(speaker)
        self._h = lib().vm_open(str(speaker).encode())
        if not self._h:
            raise RuntimeError(lib().vm_last_error().decode())
        self.names = param_names()
        self._theta = None          # None: the file's own anatomy

    # No __del__: destroying a VocalTract after setFor() aborts inside VTL, so
    # handles live until the process exits (each holds a few MB).

    def index(self, *names):
        return np.array([self.names.index(n) for n in names])

    # Anatomy -------------------------------------------------------------
    def anatomy(self) -> np.ndarray:
        theta = np.empty(lib().vm_num_anatomy())
        lib().vm_get_anatomy(self._h, theta)
        return theta

    def set_anatomy(self, theta):
        theta = np.ascontiguousarray(theta, float)
        if self._theta is not None and np.array_equal(theta, self._theta):
            return
        lib().vm_set_anatomy(self._h, theta)
        self._theta = theta.copy()

    def bounds(self):
        n = len(self.names)
        lo, hi, neutral = np.empty(n), np.empty(n), np.empty(n)
        lib().vm_param_bounds(self._h, lo, hi, neutral)
        return lo, hi, neutral

    # Shapes ----------------------------------------------------------------
    def shape(self, name: str) -> np.ndarray:
        x = np.empty(len(self.names))
        if lib().vm_get_shape(self._h, name.encode(), x):
            raise KeyError(name)
        return x

    def shape_names(self) -> list[str]:
        buf = ct.create_string_buffer(256)
        out = []
        for i in range(lib().vm_num_shapes(self._h)):
            lib().vm_shape_name(self._h, i, buf, len(buf))
            out.append(buf.value.decode())
        return out

    def set_shape(self, name: str, x):
        lib().vm_set_shape(self._h, name.encode(), np.ascontiguousarray(x, float))

    # Acoustics and geometry -------------------------------------------------
    def formants(self, x, n=3):
        """(frequencies, bandwidths, min area before the tongue-side floor, count)."""
        f, b, a = np.zeros(n), np.zeros(n), ct.c_double()
        count = lib().vm_formants(self._h, np.ascontiguousarray(x, float), n, f, b, ct.byref(a))
        return f, b, a.value, count

    def peaks(self, x, n=3, exponent=13, fmin=150.0, fmax=7000.0):
        """Transfer-function peaks on a 2^exponent spectrum (5.9 Hz at 13),
        smooth enough for finite differences.
        Returns (frequencies, levels in dB, min area before the tongue-side floor, count)."""
        f, l, a = np.zeros(n), np.zeros(n), ct.c_double()
        count = lib().vm_peaks(self._h, np.ascontiguousarray(x, float), n, exponent, fmin, fmax,
                               f, l, ct.byref(a))
        return f, l, a.value, count

    def area_function(self, x, size=64):
        pos, area = np.empty(size), np.empty(size)
        k = lib().vm_area_function(self._h, np.ascontiguousarray(x, float), pos, area, size)
        return pos[:k], area[:k]

    def constriction(self, x):
        """Narrowest cross-section before the tongue-side floor:
        dict(area, pos (cm along the centre line from the glottis), x, y (midsagittal cm), articulator)."""
        out = np.empty(5)
        lib().vm_constriction(self._h, np.ascontiguousarray(x, float), out)
        return dict(area=out[0], pos=out[1], x=out[2], y=out[3],
                    articulator=["vocal folds", "tongue", "lower incisors", "lower lip", "other"][int(out[4])])

    def write_speaker(self, path: str | Path, template: str | Path | None = None):
        """Write a speaker file: `template`'s glottis models with this tract's
        anatomy and shapes (CRLF/LF of the template kept)."""
        template = Path(template or self.speaker)
        tmp = Path(str(path) + ".tract")
        if lib().vm_write_tract(self._h, str(tmp).encode()):
            raise RuntimeError(lib().vm_last_error().decode())
        tract = tmp.read_text()
        tmp.unlink()
        with open(template, newline="") as f:
            text = f.read()
        nl = "\r\n" if "\r\n" in text else "\n"
        tract = tract.replace("\n", nl).rstrip()
        text = re.sub(r"[ \t]*<vocal_tract_model>.*?</vocal_tract_model>", lambda _: tract.lstrip("\r\n"),
                      text, count=1, flags=re.S)
        with open(path, "w", newline="") as f:
            f.write(text)


# ---------------------------------------------------------------------------
# Generic numerics on maps f: R^n -> R^m with box bounds.
# ---------------------------------------------------------------------------

class Invalid(Exception):
    """Raised by a map for inputs where it is undefined (lost formant, contact)."""


def jacobian(f: Callable[[np.ndarray], np.ndarray], z, h, lower=None, upper=None,
             columns: Sequence[int] | None = None, y0=None, scheme="central"):
    """Finite-difference Jacobian of f at z.

    h is a scalar or per-coordinate step. `scheme`:
      "central": (f(z+h) - f(z-h)) / 2h;
      "minmod":  forward and backward differences, entrywise the smaller in
                 magnitude when they agree in sign and 0 otherwise. A jump or
                 kink on one side (contact, a new spectral peak) then does not
                 leak into the derivative; on smooth stretches it equals the
                 one-sided differences.
    One-sided where z +- h would leave [lower, upper] or f raises Invalid.
    `columns` restricts the derivative to those coordinates (others are zero).
    Returns (J, f(z)).
    """
    z = np.asarray(z, float)
    n = len(z)
    h = np.broadcast_to(np.asarray(h, float), (n,))
    lower = np.broadcast_to(-np.inf if lower is None else np.asarray(lower, float), (n,))
    upper = np.broadcast_to(np.inf if upper is None else np.asarray(upper, float), (n,))
    y0 = f(z) if y0 is None else y0
    J = np.zeros((len(y0), n))
    for j in (range(n) if columns is None else columns):
        up, down = z[j] + h[j] <= upper[j], z[j] - h[j] >= lower[j]
        zp, zm = z.copy(), z.copy()
        if up:
            zp[j] += h[j]
        if down:
            zm[j] -= h[j]
        yp, ym = y0, y0
        if up:
            try:
                yp = f(zp)
            except Invalid:     # undefined on this side: one-sided difference
                zp[j] = z[j]
        if down:
            try:
                ym = f(zm)
            except Invalid:
                zm[j] = z[j]
        if zp[j] == zm[j]:
            continue
        if scheme == "minmod" and zp[j] != z[j] and zm[j] != z[j]:
            fwd, bwd = (yp - y0) / (zp[j] - z[j]), (y0 - ym) / (z[j] - zm[j])
            J[:, j] = np.where(fwd * bwd > 0, np.sign(fwd) * np.minimum(abs(fwd), abs(bwd)), 0.0)
        else:
            J[:, j] = (yp - ym) / (zp[j] - zm[j])
    return J, y0


def null_space(J, rtol=1e-8):
    """Orthonormal basis of ker J (columns) and the singular values of J."""
    _, s, vt = np.linalg.svd(J, full_matrices=True)
    rank = int(np.sum(s > rtol * s[0])) if len(s) else 0
    return vt[rank:].T, s


def bounded_step(A, b, lower, upper, damping=0.0, weights=None):
    """argmin_d |A d - b|^2 + damping^2 |W d|^2  subject to lower <= d <= upper.

    With small damping and an underdetermined A this is (close to) the
    minimum-norm solution, which keeps a continuation step on the shortest
    path in the metric W.
    """
    n = A.shape[1]
    W = np.ones(n) if weights is None else np.asarray(weights, float)
    M = np.vstack([A, damping * np.diag(W)]) if damping else A
    rhs = np.r_[b, np.zeros(n)] if damping else b
    lo, hi = np.minimum(lower, upper - 1e-12), np.maximum(upper, lower + 1e-12)
    return lsq_linear(M, rhs, bounds=(lo, hi), method="bvls").x


@dataclass
class Step:
    s: float
    z: np.ndarray
    y: np.ndarray
    residual: float
    info: dict = field(default_factory=dict)


def correct(f, z, free, y_target, free_lower, free_upper, jac_free, tol=1e-3, aim=None,
            iterations=12, damping=1e-2, accept=None, y=None, weights=None):
    """Levenberg-Marquardt on the free coordinates until max|f(z) - y_target| < aim (default tol);
    a point that only gets below tol is still accepted.

    The free Jacobian is recomputed at every accepted iterate (VTL's maps are
    only piecewise smooth, so a stale one points the wrong way across kinks).
    Trials that leave the domain or that `accept(z, y)` rejects count as
    failures and raise the damping. `weights` (one per free coordinate) is
    the metric of the damping term: a small weight makes that coordinate
    cheap to move. Returns (z, y, number of iterations);
    raises Invalid when it does not converge.
    """
    y = f(z) if y is None else y
    lam = damping
    for it in range(iterations):
        r = y - y_target
        if np.max(np.abs(r)) < (tol if aim is None else aim):
            return z, y, it
        J = jac_free(z, y)
        for _ in range(8):
            d = bounded_step(J, -r, free_lower - z[free], free_upper - z[free], lam, weights)
            trial = z.copy()
            trial[free] += d
            try:
                yt = f(trial)
                ok = accept is None or accept(trial, yt)
            except Invalid:
                ok = False
            if ok and np.sum((yt - y_target) ** 2) < np.sum(r ** 2):
                z, y = trial, yt
                lam = max(lam / 3, 1e-4)
                break
            lam *= 4
        else:
            break
    if np.max(np.abs(y - y_target)) < tol:
        return z, y, iterations
    raise Invalid(f"corrector stalled at {np.max(np.abs(y - y_target)):.4f}")


def follow(f, z0, driven, target, free_lower, free_upper, h, y_target=None,
           ds=0.05, ds_min=1e-3, ds_max=0.1, tol=1e-3, accept=None, damping=1e-2,
           corrector_iterations=12, on_step=None, scheme="central", weights=None):
    """Drive the coordinates `driven` of z from z0 straight to `target` while
    the free coordinates keep f(z) == y_target (continuation on the level set).

    Predictor: the free coordinates move by the bounded, damped minimum-norm
    solution of J_free dz = -J_driven dp, i.e. along the tangent of the level
    set (the kernel of the full Jacobian) whose driven part is the step dp.
    Corrector: `correct` (Levenberg-Marquardt) with the driven coordinates
    held. `weights` (one per free coordinate) sets the metric of the
    minimum-norm predictor and of the corrector's damping, so the path
    prefers moving coordinates with small weights. `accept(z, y)` can
    reject points (e.g. tongue contact). The step
    halves on failure and grows after easy steps. Returns the accepted
    `Step`s, ending at s = 1 or where the step fell below ds_min.
    """
    z = np.array(z0, float)
    driven = np.asarray(driven)
    free = np.setdiff1d(np.arange(len(z)), driven)
    p0, p1 = z[driven].copy(), np.asarray(target, float)
    y = f(z)
    y_target = y if y_target is None else np.asarray(y_target, float)
    lo, hi = np.full(len(z), -np.inf), np.full(len(z), np.inf)
    lo[free], hi[free] = free_lower, free_upper

    def jac_free(z, y):
        return jacobian(f, z, h, lo, hi, columns=free, y0=y, scheme=scheme)[0][:, free]

    def jac_driven(z, y):
        return jacobian(f, z, h, columns=driven, y0=y, scheme=scheme)[0][:, driven]

    def corr(z, y=None):
        return correct(f, z, free, y_target, free_lower, free_upper, jac_free, tol, tol / 4,
                       corrector_iterations, damping, accept, y, weights)

    z, y, _ = corr(z, y)
    s, path = 0.0, [Step(0.0, z.copy(), y.copy(), float(np.max(np.abs(y - y_target))))]
    if on_step:
        on_step(path[-1])
    Jd = Jf = None
    while s < 1 - 1e-12:
        ds = min(ds, 1 - s)
        if Jd is None:
            Jd, Jf = jac_driven(z, y), jac_free(z, y)
        try:
            pred = z.copy()
            pred[driven] = p0 + (s + ds) * (p1 - p0)
            pred[free] += bounded_step(Jf, -Jd @ (pred[driven] - z[driven]),
                                       free_lower - z[free], free_upper - z[free], damping, weights)
            zn, yn, iterations = corr(pred)
            if accept and not accept(zn, yn):
                raise Invalid("rejected by accept()")
        except Invalid as e:
            ds /= 2
            if ds < ds_min:
                path[-1].info["stopped"] = str(e)
                break
            continue
        s += ds
        z, y, Jd = zn, yn, None
        path.append(Step(s, z.copy(), y.copy(), float(np.max(np.abs(y - y_target))),
                         dict(iterations=iterations, ds=ds)))
        if on_step:
            on_step(path[-1])
        if iterations <= 3:
            ds = min(ds * 1.5, ds_max)
    return path
