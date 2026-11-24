"""Time course in bands around one consonant class, synthesis against JVS women, token by token.

    course.py <class> <label>[=<speaker>] ...     class: z j r s sh ch

Tracks are aligned at the end of the consonant segment (r: at the lowest 1-4 kHz level) and
in dB re the 80-7800 Hz level of the following vowel. Prints JVS medians, then each label,
averaged over the tokens the label has. "label" alone reuses out/course/<label>.pkl.
"""
import sys

from compare import *

SETS = {"z": ["z"], "j": ["j"], "r": ["r", "ry"], "s": ["s"], "sh": ["sh"], "ch": ["ch"]}
CB = [(80, 500), (500, 1000), (1000, 2000), (2000, 3000), (3000, 4000), (4000, 5000), (5000, 6000), (6000, 7800)]
T = np.arange(-120, 81, 5)


def courses(job):
    x, spans = job
    sp = M.Spec(x)
    B = np.array([sp.band(a, b, "lo" if b <= 1000 else "hi") for a, b in CB])
    k5 = np.ones(5) / 5
    B = np.array([10 * np.log10(np.convolve(10 ** (b / 10), k5, "same") + 1e-12) for b in B])
    full = sp.band(80, 7800)
    ms = lambda t: int(np.clip(round(t * 1000), 0, sp.n - 1))
    out = {}
    for i, p, a, b, v1, q, n in tokens(spans):
        ve = min(v1, b + .14)
        s0 = ms(b + .35 * (ve - b)); s1 = max(ms(b + .8 * (ve - b)), s0 + 3)
        c = ms(b)
        if p in ("r", "ry"):
            mid = sp.band(1000, 4000)[ms(a - .01):ms(b + .02)]
            if len(mid) < 5:
                continue
            c = ms(a - .01) + int(mid.argmin())
        k = np.clip(c + T, 0, sp.n - 1)
        out[(i, p + n)] = (q, B[:, k] - np.median(full[s0:s1]))
    return out


def jvs_courses():
    path = OUT / "course-jvs.pkl"
    if not path.exists():
        al = pickle.load(open(OUT / "align.pkl", "rb"))["align"]
        keys, jobs = [], []
        for n in women():
            for u, x in load_jvs(n, list(SENTENCES)).items():
                keys.append((n, u)); jobs.append((x, al[(n, u)]))
        with ProcessPoolExecutor(8) as ex:
            pickle.dump(dict(zip(keys, ex.map(courses, jobs, chunksize=4))), open(path, "wb"))
    return pickle.load(open(path, "rb"))


def main(args):
    phs = SETS[args[0]]
    J = {}
    for (n, u), d in jvs_courses().items():
        for t, o in d.items():
            if t[1][:-1] in phs:
                J.setdefault((u, t), []).append(o[1])
    J = {t: np.median(v, 0) for t, v in J.items() if len(v) > 20}
    ix = range(0, len(T), 2)
    print("tokens", [f"{t[0]}:{t[1][1]}" for t in J])
    print("ms            " + " ".join(f"{T[k]:4d}" for k in ix))

    def show(tag, D):
        for (a, b), r in zip(CB, D):
            print(f"{tag:5s} {a / 1000:g}-{b / 1000:g}".ljust(14) + " ".join(f"{r[k]:4.0f}" for k in ix))
    for j, l in enumerate(args[1:]):
        label = l.split("=")[0]
        path = OUT / f"course/{label}.pkl"
        if "=" in l:
            path.parent.mkdir(exist_ok=True)
            pickle.dump({u: courses(q) for u, q in synth(l.split("=")[1], label).items()}, open(path, "wb"))
        S = {(u, t): o[1] for u, d in pickle.load(open(path, "rb")).items() for t, o in d.items()}
        ks = [t for t in J if t in S]
        if j == 0:
            show("JVS", np.mean([J[t] for t in ks], 0))
        print(label, "n =", len(ks))
        show(label, np.mean([S[t] for t in ks], 0))


if __name__ == "__main__":
    main(sys.argv[1:])
