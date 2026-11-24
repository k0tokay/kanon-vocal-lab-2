"""Peak of the first 60 ms of a vowel after b d g (and, for reference, after other onsets)
against the rest of the voice: 20 log10(peak / utterance active rms), above 60 Hz.

    ALIGN=<align.pkl> python onset_peaks.py v1-1-0 v1-1-3 ...
"""
import pickle
import sys

from scipy.signal import butter, sosfiltfilt

from common import *
from copysynth import read_wav
from stats import SPK
from vowels import VOW, seg_spans

SETS = {"b d g": {"b", "d", "g"}, "other": {"k", "t", "s", "n", "m", "sh", "h", "4", "r", "s\\", "ts\\", "ch", "y", "j", "z"}}
HP = butter(2, 60, "hp", fs=RS, output="sos")


def peaks(x, sp):
    x = level(sosfiltfilt(HP, x)); out = {k: [] for k in SETS}
    for (c, *_), (v, a, b) in zip(sp, sp[1:]):
        if v in VOW:
            for k, s in SETS.items():
                if c in s:
                    w = x[max(0, int((a - .02) * RS)):int((a + .06) * RS)]
                    if len(w): out[k].append(20 * np.log10(np.abs(w).max() / RMS))
    return out


def show(name, items):
    r = [peaks(x, sp) for x, sp in items]
    print(f"{name:22s} " + "  ".join(f"{k}: n {len(q):4d} median {np.median(q):5.1f} p95 {np.percentile(q, 95):5.1f} max {max(q):5.1f}"
                                      for k in SETS for q in [np.array(sum((z[k] for z in r), []))]))


if __name__ == "__main__":
    al = pickle.load(open(os.environ["ALIGN"], "rb"))["align"]
    show("JVS women", [(x, al[n, u]) for n in sorted({n for n, _ in al}) for u, x in load_jvs(n, SENTENCES).items() if (n, u) in al])
    for s in SPK:
        show(f"JVS {s}", [(x, al[s, u]) for u, x in load_jvs(s, SENTENCES).items() if (s, u) in al])
    for ver in sys.argv[1:]:
        A = HERE / "out" / ver / "audio"
        for tag, subs in (("rule", ["vtl"]), ("copy", SPK)):
            show(f"{ver} {tag}", [(read_wav(A / f"{b}/{u}.wav"), seg_spans(A / f"{b}/{u}.seg")) for b in subs for u in SENTENCES])
