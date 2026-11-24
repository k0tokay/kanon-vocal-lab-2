"""voiceactress100 texts with a comma where more than half of the JVS women pause for 100 ms.

    VA100=<dir> python prosody_text.py <out/prosody-jvs.pkl> <out.json>
"""
import json
import os
import pickle
import re
import sys
from pathlib import Path

import pyopenjtalk

VA = Path(os.environ["VA100"])
PH = [l.split() for l in (VA / "voiceactoress100_phoneme_openjtalk.txt").read_text().splitlines()]
TX = [l.split("\t")[1] for l in (VA / "balance_sentences.txt").read_text().splitlines()[1:]]
VOWEL = set("aiueoAIUEON") | {"cl"}


def phones(text):
    return [re.search(r"-(.+?)\+", l).group(1) for l in pyopenjtalk.extract_fullcontext(text)]


def aligned(a, b):
    """Levenshtein map: for every index of a, the index of b it corresponds to."""
    n, m = len(a), len(b)
    D = [[i + j if i * j == 0 else 0 for j in range(m + 1)] for i in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i][j] = min(D[i - 1][j] + 1, D[i][j - 1] + 1, D[i - 1][j - 1] + (a[i - 1].lower() != b[j - 1].lower()))
    i, j, out = n, m, [None] * n
    while i and j:
        if D[i][j] == D[i - 1][j - 1] + (a[i - 1].lower() != b[j - 1].lower()):
            out[i - 1] = j - 1; i, j = i - 1, j - 1
        elif D[i][j] == D[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    return out, D[n][m]


def with_commas(text, ph):
    """Put a comma after the word that ends at each 'pau' of the reading."""
    words, ends, n = [], [], 0
    for w in pyopenjtalk.run_frontend(text):
        k = len([p for p in phones_of(w)])
        words.append(w["string"]); n += k; ends.append(n)
    mine = [p for w in pyopenjtalk.run_frontend(text) for p in phones_of(w)]
    core, breaks = [], []
    for p in ph:
        if p == "pau": breaks.append(len(core))
        elif p != "sil": core.append(p)
    back, dist = aligned(core, mine)
    out, cut = [], set()
    for b in breaks:
        i = b - 1
        while i >= 0 and back[i] is None: i -= 1
        e = (back[i] + 1) if i >= 0 else 0
        cut.add(min(range(len(ends)), key=lambda q: abs(ends[q] - e)))
    for q, w in enumerate(words):
        out.append(w)
        if q in cut and q + 1 < len(words): out.append("、")
    return "".join(out) + "。"


def phones_of(w):
    return [] if w["pos"] == "記号" else [p for p in pyopenjtalk.g2p(w["pron"].replace("’", "")).split() if p != "pau"]


def heard(D, u, ph):
    """The reading with 'pau' only where more than half of the women are silent for 100 ms."""
    core = [p for p in ph if p not in ("sil", "pau")]
    cnt, n = [0] * (len(core) + 1), 0
    for r in D["jvs"].values():
        if u not in r: continue
        k = 0; n += 1
        for name, a, b in r[u]["spans"]:
            if name == "sil": cnt[k] += b - a >= .1
            else: k += 1
    out = ["sil"]
    for i, p in enumerate(core):
        if i and cnt[i] > n / 2: out.append("pau")
        out.append(p)
    return out + ["sil"]


if __name__ == "__main__":
    D = pickle.load(open(sys.argv[1], "rb")); res = {}
    for i, (t, p) in enumerate(zip(TX, PH)):
        p = heard(D, f"{i + 1:03d}", p)
        res[f"{i + 1:03d}"] = dict(text=with_commas(t, p), reading=p)
    Path(sys.argv[2]).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    for u in ("001", "009", "012", "013", "017", "025"): print(u, res[u]["text"])
