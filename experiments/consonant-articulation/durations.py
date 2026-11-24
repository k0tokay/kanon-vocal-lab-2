"""Consonant share of CV moras: JVS women (align.pkl) against the rule (accent.py).

Prints per consonant the JVS median consonant and vowel durations (no phrase-final moras), the
ratio c/(c+v), the mean mora, and the rule values. Needs out/align.pkl.
"""
from compare import *


def final(seq, i):
    return i + 1 >= len(seq) or seq[i + 1][1] - seq[i][2] > .03


def rows():
    al = pickle.load(open(OUT / "align.pkl", "rb"))["align"]
    d = {}
    for (n, u), sp in al.items():
        seq = [s for s in sp if s[0] != "sil"]
        for i in range(len(seq) - 1):
            p, a, b = seq[i]; q, c, e = seq[i + 1]
            if p in VOWELS or p in ("N", "cl") or q not in "aiueo" or final(seq, i + 1) or (i and seq[i - 1][0] == "cl"):
                continue
            d.setdefault(p, []).append((b - a, e - c, n))
    return d


if __name__ == "__main__":
    d = rows()
    allc = [x[0] + x[1] for v in d.values() for x in v]
    print(f"JVS mora (CV, non-final) median {1e3*np.median(allc):.0f} ms")
    for p, v in sorted(d.items(), key=lambda q: np.median([x[0] for x in q[1]])):
        c, w = np.array([x[:2] for x in v]).T
        seg = accent.onset(p, "a", True)
        print(f"{p:3s} n={len(v):4d}  JVS c {1e3*np.median(c):4.0f} (p25 {1e3*np.percentile(c,25):.0f} p75 {1e3*np.percentile(c,75):.0f}) v {1e3*np.median(w):4.0f}  share {np.median(c/(c+w)):.2f}"
              f"   rule {1e3*sum(s.duration for s in seg):4.0f}  share {sum(s.duration for s in seg)/.135:.2f}")
