"""Inside the synthesis around one consonant (cdiag.so): intraoral pressure, glottis, flow, area.

    internal.py <speaker> aba,ada,aga [--every 5] [--rate 1.0]

Prints, every few ms around the segment, t (ms from the segment's beginning), x_bottom/x_top (mm),
relative amplitude, intraoral pressure (% of the lung pressure, 5 ms mean), glottal area min and
max over 5 ms (mm2), mouth flow (5 ms mean, cm3/s) and the oral minimum area (cm2).
"""
import ctypes as C
import sys

from compare import *

_lib = C.CDLL(str(HERE.parents[1] / "build-mac/cdiag.so"))
_lib.cd_run.argtypes = [C.c_char_p, C.c_char_p, C.c_int, np.ctypeslib.ndpointer(np.float64), C.c_int]
KANA = {"aba": "あば", "ada": "あだ", "aga": "あが", "aza": "あざ", "aja": "あじゃ", "ara": "あら", "apa": "あぱ", "ata": "あた", "aka": "あか",
        "igi": "いぎ", "iri": "いり", "uru": "うる", "ere": "えれ", "oro": "おろ"}


def run(speaker, text, rate=1.0, step=24):
    """Rows of cdiag for a short text, and its segments."""
    stem = OUT / f"internal/{accent.os.getpid()}"
    r = accent.render(KANA.get(text, text), stem, speaker=Path(speaker), rate=rate)
    R = np.zeros((20000, 11))
    n = _lib.cd_run(str(speaker).encode(), str(stem.with_suffix(".ges")).encode(), step, R, 20000)
    assert n > 0, n
    return R[:n], r


def smooth(x, n):
    return np.convolve(x, np.ones(n) / n, "same")


if __name__ == "__main__":
    a = sys.argv[1:]
    opt = lambda k, d: float(a[a.index(k) + 1]) if k in a else d
    spk, names = a[0], a[1].split(",")
    every = int(opt("--every", 5))
    for name in names:
        R, r = run(spk, name, opt("--rate", 1.0))
        seg = [s for s in r["segments"] if s.name][1]
        dt = R[1, 0] - R[0, 0]
        w = max(1, round(.005 / dt))
        P, F = smooth(R[:, 7], w) / 80, smooth(R[:, 6], w)
        print(f"== {name}: {seg.name} {1e3 * seg.t0:.0f} + {1e3 * seg.duration:.0f} ms")
        print("    t    xb   xt  amp  Pio%  gmin  gmax  flow   Amin")
        for t in range(-60, int(1e3 * seg.duration) + 60, every):
            k = int((seg.t0 + t / 1e3) / dt)
            q = slice(max(0, k - w // 2), k + w // 2 + 1)
            print(f"{t:5d}  {10 * R[k, 2]:4.2f} {10 * R[k, 3]:4.2f} {R[k, 4]:4.2f} {P[k]:5.0f} {100 * R[q, 5].min():5.1f} {100 * R[q, 5].max():5.1f} {F[k]:6.0f} {R[k, 8]:6.3f}")
