"""Consonant measures of synthesised sentences against 51 JVS women, token by token.

    compare.py [--old-rules | --v111-rules] <label>=<speaker file> ...      e.g.  v110=../../speakers/.../v1-1-0.speaker

Each consonant token of the five sentences is measured (measure.py) in every JVS recording
(boundaries: align.py) and in the rule synthesis (boundaries: the segment file). The same
token has the same context in both. Each measure becomes a z-score against the 51 women;
tokens are then averaged per consonant class. Writes results/compare-<label>.json and prints
the table.
"""
import json
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor

from align import *
import measure as M

VOWELS = set("aiueoAIUEO")


def tokens(spans):
    """(index among non-pause phones, phone, start, end, end of next vowel, previous phone, next phone)."""
    out = []
    seq = [s for s in spans if s[0] != "sil"]
    for i, (p, a, b) in enumerate(seq):
        if p in VOWELS or p in ("cl", "sil"):
            continue
        n = seq[i + 1] if i + 1 < len(seq) else None
        if n is None or n[0] not in "aiueo":
            continue                    # before devoiced vowels the reference level is undefined
        prev = seq[i - 1] if i else None
        if prev and abs(prev[2] - a) > .03:
            prev = None                 # after a pause
        out.append((i, p, a, b, n[2], prev[0] if prev else "#", n[0]))
    return out


def measure_one(job):
    x, spans = job
    sp = M.Spec(x)
    return {(i, p + n): M.token(sp, a, b, v1, p) | {"prev": q} for i, p, a, b, v1, q, n in tokens(spans)}


def jvs():
    path = OUT / "jvs-measures.pkl"
    if path.exists():
        return pickle.load(open(path, "rb"))
    al = pickle.load(open(OUT / "align.pkl", "rb"))["align"]
    keys, jobs = [], []
    for n in women():
        for u, x in load_jvs(n, list(SENTENCES)).items():
            keys.append((n, u)); jobs.append((x, al[(n, u)]))
    with ProcessPoolExecutor(8) as ex:
        res = dict(zip(keys, ex.map(measure_one, jobs, chunksize=4)))
    pickle.dump(res, open(path, "wb"))
    return res


def synth(speaker, label, rate=1.0):
    """Rule synthesis of the five sentences: audio at 16 kHz and phone spans, as in align.rule_sentences but with pauses."""
    out = {}
    for u, text in SENTENCES.items():
        stem = OUT / f"sent/{label}/{u}"
        r = accent.render(text, stem, speaker=Path(speaker), rate=rate)
        sr, x = wavfile.read(stem.with_suffix(".wav"))
        b = []
        for q, (s, e) in zip(r["units"], r["spans"]):
            if isinstance(q, accent.Pause):
                continue
            if q.consonant:
                own = [g for g in r["segments"] if s - 1e-6 <= g.t0 < e - 1e-6]
                k = own[-1]
                b += [(q.consonant, s, k.t0), (q.vowel, k.t0, e)]
            else:
                b.append((q.vowel, s, e))
        out[u] = (level(to16(x / 32768.0, sr)), b)
    return out


CLASSES = {
    "無声破裂 k t": ["k", "t", "ky"], "有声破裂 b d g": ["b", "d", "g", "by", "gy"],
    "s": ["s"], "ɕ (sh)": ["sh"], "tɕ (ch)": ["ch"], "ts": ["ts"], "z": ["z"], "dʑ (j)": ["j"],
    "ɸ h ç": ["f", "h", "hy"], "m n": ["m", "n", "my", "ny"], "ɾ": ["r", "ry"], "w j": ["w", "y"],
}
KEYS = ["dur_ms", "closure_ms", "closure_mid", "closure_low", "burst_mid", "burst_1k", "burst_2k", "burst_4k", "burst_cog",
        "vot_ms", "fric_ms", "fric_level", "fric_cog", "fb_1k", "fb_2k", "fb_3k", "fb_4k", "fb_5k", "fb_6k", "fric_voice", "dip_mid", "dip_full",
        "dip_500_4k", "voice_min", "peak_hi", "nb_0.08k", "nb_0.5k", "nb_1k", "nb_2k", "nb_3k"]


def collect_jvs():
    """{(utterance, token): {measure: array over speakers}}"""
    pop = {}
    for (n, u), toks in jvs().items():
        for t, o in toks.items():
            for k, v in o.items():
                if k != "prev":
                    pop.setdefault((u, t), {}).setdefault(k, []).append(v)
    return pop


def table(S, pop):
    """S: {utterance: {token: measures}}. Per class and measure: JVS mean, SD, synthesis mean, mean z, n tokens."""
    rows = {}
    for cname, phs in CLASSES.items():
        acc = {}
        for u, toks in S.items():
            for t, o in toks.items():
                if not any(t[1][:-1] == p for p in phs):
                    continue
                for k, v in o.items():
                    q = pop.get((u, t), {}).get(k) if k != "prev" else None
                    if q is None or len(q) < 15:
                        continue
                    q = np.array(q)
                    m, s = np.median(q), 1.4826 * np.median(np.abs(q - np.median(q))) + 1e-6
                    acc.setdefault(k, []).append((m, s, v))
        rows[cname] = {k: dict(jvs=float(np.mean([a[0] for a in v])), sd=float(np.mean([a[1] for a in v])),
                               syn=float(np.mean([a[2] for a in v])), z=float((np.mean([a[2] for a in v]) - np.mean([a[0] for a in v])) / np.mean([a[1] for a in v])),
                               n=len(v)) for k, v in acc.items()}
    return rows


def old_rules():
    """The rules of 2de4607 (before this experiment). VTL_LIB must be a library of that commit, too."""
    accent.BASE = {"p": .055, "b": .045, "t": .055, "d": .045, "k": .06, "g": .045, "s": .085, "z": .06, "S": .09,
                   "C": .08, "h": .065, "f": .07, "v": .05, "ts": .08, "tS": .085, "dZ": .065, "m": .05, "n": .045,
                   "N": .05, "4": .022, "j": .06, "u": .05, "M": .04, "s\\": .09, "z\\": .06, "ts\\": .085, "dz\\": .065}
    accent.GLIDE, accent.VELIC, accent.JA_TIMING, accent.TIMING = .025, 1.0, set(), {}
    new = accent.onset
    accent.onset = lambda *a, after_vowel=False, **k: new(*a, **k)


def v111_rules():
    """The rules of a86f77e (label "stop = ja"). VTL_LIB must be a library of that commit, too."""
    accent.JA_TIMING, accent.TIMING = set(), {}
    new = accent.write_seg

    def write_seg(segments, path):
        new(segments, path)
        lines = path.read_text().splitlines()
        for i, s in enumerate(segments):
            if s.name in ("p", "t", "k", "b", "d", "g"):
                lines[i] += " stop = ja;"
        path.write_text("\n".join(lines) + "\n")
    accent.write_seg = write_seg


def main(args):
    if "--v111-rules" in args:
        args.remove("--v111-rules")
        v111_rules()
    if "--old-rules" in args:
        args.remove("--old-rules")
        old_rules()
    pop = collect_jvs()
    res = {}
    for a in args:
        label, spk = a.split("=")
        sy = synth(spk, label)
        res[label] = table({u: measure_one(j) for u, j in sy.items()}, pop)
        (HERE / "results").mkdir(exist_ok=True)
        (HERE / f"results/compare-{label}.json").write_text(json.dumps(res[label], ensure_ascii=False, indent=1))
    for c in CLASSES:
        print(f"== {c}")
        for k in KEYS:
            r = [res[l][c].get(k) for l in res]
            if r[0]:
                print(f"   {k:12s} JVS {r[0]['jvs']:8.1f} ±{r[0]['sd']:6.1f}  n={r[0]['n']:2d} | " +
                      " | ".join(f"{l} {q['syn']:8.1f} z={q['z']:+5.1f}" for l, q in zip(res, r) if q))


if __name__ == "__main__":
    main(sys.argv[1:])
