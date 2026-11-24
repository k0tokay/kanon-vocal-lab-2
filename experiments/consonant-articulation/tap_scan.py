"""Scan of the tap: how fast the sound goes into and comes out of it, against the same JVS tokens.

    tap_scan.py <speaker> "key=value,..." ...

Keys: timing labels of "4" (onset_tau, offset_tau, contact, contact_cm2), dur, ts3 and other
tract parameters (added to the tap shapes except TS3, which is set).
Band levels relative to the vowels on both sides (line between -50..-40 and +40..+50 ms),
averaged over the 12 tokens of the five sentences; rms = difference to JVS in dB, -30..+30 ms.
"""
import multiprocessing
import sys
import zlib

import course
from build import ctune
from voiced_scan import *

BANDS = {"low": [0], "0.5-1": [1], "1-2": [2], "2-4": [3, 4], "4-8": [5, 6, 7]}
SHOW_R = list(range(-30, 36, 5))


def rel(c):
    out = []
    t = course.T
    for k in BANDS.values():
        y = 10 * np.log10((10 ** (c[k] / 10)).sum(0))
        a, b = np.median(y[(t >= -50) & (t <= -40)]), np.median(y[(t >= 40) & (t <= 50)])
        y = y - np.interp(t, [-45, 45], [a, b])
        out.append([y[int(np.flatnonzero(t == s)[0])] for s in SHOW_R])
    return np.array(out)


def edit_shapes(speaker, d, out):
    tr = ctune.vm.Tract(Path(speaker))
    for n in tr.shape_names():
        if n.startswith("tt-tap-"):
            x = tr.shape(n).copy()
            for k, v in d.items():
                i = tr.index(k)
                x[i] = v if k.startswith("TS") else x[i] + v
            tr.set_shape(n, x)
    tr.write_speaker(Path(out), Path(speaker))
    return out


def jobr(a):
    speaker, spec = a
    o = dict(kv.split("=") for kv in spec.split(",")) if spec != "=" else {}
    o = {k: float(v) for k, v in o.items()}
    tag = zlib.crc32(spec.encode())
    shape = {k: o.pop(k) for k in list(o) if k.isupper() or k[:2] == "TS"}
    if shape:
        speaker = edit_shapes(speaker, shape, OUT / f"scan/tap-{tag}.speaker")
    if "dur" in o:
        accent.BASE["4"] = o.pop("dur")
    accent.TIMING["4"] = {**accent.TIMING["4"], **{(k if k.endswith("_cm2") else k + "_s"): v for k, v in o.items()}}
    R = synth(str(speaker), f"tap{tag}")
    return spec, {(u, t): rel(c[1]) for u, j in R.items() for t, c in course.courses(j).items() if t[1][:-1] in ("r", "ry")}


if __name__ == "__main__":
    spk, *specs = sys.argv[1:]
    spk = str(Path(spk).resolve())
    J = {}
    for (n, u), d in course.jvs_courses().items():
        for t, o in d.items():
            if t[1][:-1] in ("r", "ry"):
                J.setdefault((u, t), []).append(rel(o[1]))
    J = {t: np.median(v, 0) for t, v in J.items() if len(v) > 20}
    (OUT / "scan").mkdir(exist_ok=True)
    print("ms              " + " ".join(f"{t:4d}" for t in SHOW_R))
    with multiprocessing.Pool(8, maxtasksperchild=1) as ex:
        for j, (s, S) in enumerate(ex.imap(jobr, [(spk, s) for s in specs], chunksize=1)):
            ks = [t for t in J if t in S]
            Jm, Sm = np.mean([J[t] for t in ks], 0), np.mean([S[t] for t in ks], 0)
            if j == 0:
                for b, r in zip(BANDS, Jm):
                    print(f"JVS {b:12s}" + " ".join(f"{x:4.0f}" for x in r))
            print(s, f"rms {np.sqrt(np.mean((Sm - Jm) ** 2)):.1f}", "per band", " ".join(f"{np.sqrt(np.mean((a - b) ** 2)):.1f}" for a, b in zip(Sm, Jm)))
            for b, r in zip(BANDS, Sm):
                print(f"    {b:12s}" + " ".join(f"{x:4.0f}" for x in r))
