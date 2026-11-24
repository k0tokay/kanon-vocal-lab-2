"""Where the loud vowels next to b d g come from: the glottis at the loudest moment.

    onset_glottis.py <label>=<speaker> ...            tokens of the five sentences, then the medians
    onset_glottis.py --swap <speaker>                 the same scores with parts of the b d g gestures replaced
    onset_glottis.py --steady <speaker>               steady [a] along the way from modal to voiced-plosive

Peak: 20 log10(max |x| / active rms of the utterance), above 60 Hz (as in world-decomposition/
onset_peaks.py), in the vowel after (-20..+60 ms from its beginning) and in the last 60 ms of the
vowel before. k: how far the glottis is from modal (0) to voiced-plosive (1) at that moment.
"""
import ctypes as C
import re
import sys

from scipy.signal import butter, sosfiltfilt

from compare import *
import internal

HP = butter(2, 60, "hp", fs=RS, output="sos")
VOICED = {"b", "d", "g"}
OTHER = {"k", "t", "s", "n", "m", "s\\", "ts", "ts\\", "4", "j", "z", "h"}
VOW = set("aiueoM")


def seg_spans(r):
    return [(s.name, s.t0, s.t0 + s.duration) for s in r["segments"]]


def wav(path):
    sr, x = wavfile.read(path)
    return level(sosfiltfilt(HP, to16(x / 32768.0, sr)))


def peaks(x, sp, sets=(VOICED, OTHER)):
    """[(consonant, vowel, beginning, end, peak after, its time, peak before, its time)] per set."""
    out = [[] for _ in sets]
    db = lambda a, b: (lambda w, i0: (20 * np.log10(np.abs(w).max() / RMS), (i0 + int(np.abs(w).argmax())) / RS) if len(w) else (np.nan, np.nan))(
        x[max(0, int(a * RS)):int(b * RS)], max(0, int(a * RS)))
    for i in range(len(sp) - 1):
        (c, a, b), (v, _, _) = sp[i], sp[i + 1]
        for k, s in enumerate(sets):
            if c in s and v in VOW:
                q = db(a - .06, a) if i and sp[i - 1][0] in VOW else (np.nan, np.nan)
                out[k].append((c, v, a, b) + db(b - .02, b + .06) + q)
    return out


def summary(rows):
    p = np.array([r[4] for r in rows]); q = np.array([r[6] for r in rows])
    return (f"after: n {len(p):3d} median {np.median(p):5.1f} p95 {np.percentile(p, 95):5.1f} max {p.max():5.1f}   "
            f"before: median {np.nanmedian(q):5.1f} p95 {np.nanpercentile(q, 95):5.1f} max {np.nanmax(q):5.1f}")


def trace(speaker, ges, step=12, n=200000):
    R = np.zeros((n, 11))
    k = internal._lib.cd_run(str(Path(speaker).resolve()).encode(), str(ges).encode(), step, R, n)
    assert k > 0, k
    return R[:k]


def glottis(speaker, shape, model="Geometric glottis 2025"):
    s = Path(speaker).read_text()
    k = s.index(f'type="{model}"')
    m = re.search(rf'<shape name="{shape}">(.*?)</shape>', s[k:], re.S)[1]
    return np.array([float(v) for v in re.findall(r'value="([-\d.e]+)"', m)])


def tokens_table(label, speaker):
    M0, V0 = (glottis(speaker, n) for n in ("modal", "voiced-plosive"))
    allr, ot, K = [], [], []
    for u, text in SENTENCES.items():
        stem = OUT / f"onset/{label}/{u}"
        r = accent.render(text, stem, speaker=Path(speaker))
        x = wav(stem.with_suffix(".wav"))
        v, o = peaks(x, seg_spans(r))
        R = trace(speaker, stem.with_suffix(".ges"))
        t = R[:, 0]
        for q in v:
            row = []
            for tp in (q[5], q[7]):
                if tp != tp:
                    continue
                k = int(np.searchsorted(t, tp)); w = np.abs(t - tp) < .0025
                f = (M0[2] - R[k, 2]) / (M0[2] - V0[2])
                row.append(f"t {1e3 * (tp - q[3]):4.0f} from end: k {f:4.2f} x {10 * R[k, 2]:.2f}/{10 * R[k, 3]:.2f} Pio {R[w, 7].mean() / 80:3.0f}% flow {R[w, 6].mean():4.0f} Amin {R[w, 8].mean():.2f}")
                if len(row) == 1:
                    K.append((1e3 * (tp - q[3]), f, q[4]))
            print(f"{label} {u} {q[0]}{q[1]} after {q[4]:5.1f} before {q[6]:5.1f} | " + " || ".join(row))
        allr += v; ot += o
    print(f"{label} b d g   {summary(allr)}\n{label} others  {summary(ot)}")
    K = np.array(K)
    print(f"{label} at the peak: {np.median(K[:, 0]):.0f} ms from the segment's end, k {np.median(K[:, 1]):.2f};  "
          f"peaks > 14 dB: n {(K[:, 2] > 14).sum()}, k {np.median(K[K[:, 2] > 14, 1]) if (K[:, 2] > 14).any() else np.nan:.2f}")


def ges_swap(ges, out, fn):
    s = ges.read_text()
    def seq(m):
        return m[1] + fn(m[2]) + m[3]
    s = re.sub(r'(<gesture_sequence type="glottal-shape-gestures"[^>]*>)(.*?)(</gesture_sequence>)', seq, s, flags=re.S)
    out.write_text(s)


def render_ges(speaker, ges, out):
    """As accent.synthesize, from a gestural score."""
    accent.use_speaker(Path(speaker))
    n = C.c_int()
    assert accent._lib.vtlGesturalScoreToAudio(bytes(ges), b"", b"", None, C.byref(n), 0, 0) == 0
    buf = (C.c_double * n.value)()
    assert accent._lib.vtlGesturalScoreToAudio(bytes(ges), b"", b"", buf, C.byref(n), 0, 0) == 0
    x = np.frombuffer(buf, dtype=np.float64)
    accent.write(out, accent._lib.rate, (x / np.abs(x).max() * .8 * 32767).astype(np.int16))
    return x


def swap(speaker):
    cases = {"as is": lambda g: g, "modal": lambda g: g.replace('"voiced-plosive"', '"modal"'),
             "tau 3 ms": None, "tau 15 ms": None}
    def tau(ms):
        return lambda g: re.sub(r'(value="voiced-plosive"[^/]*time_constant_s=")[\d.]+', rf"\g<1>{ms / 1e3:.6f}", g)
    cases["tau 3 ms"], cases["tau 15 ms"] = tau(3), tau(15)
    for name, fn in cases.items():
        rows, ot = [], []
        for u, text in SENTENCES.items():
            stem = OUT / f"onset/swap/{u}"
            r = accent.render(text, stem, speaker=Path(speaker))
            g2 = stem.with_name(u + "-x.ges")
            ges_swap(stem.with_suffix(".ges"), g2, fn)
            render_ges(speaker, g2, g2.with_suffix(".wav"))
            v, o = peaks(wav(g2.with_suffix(".wav")), seg_spans(r))
            rows += v; ot += o
        print(f"{name:10s} {summary(rows)}")


def steady(speaker):
    """Long vowels with the glottis fixed part of the way: peak and rms re modal, dB; HNR."""
    M0, V0 = (glottis(speaker, n) for n in ("modal", "voiced-plosive"))
    from build import edit_glottis
    import voicing
    for text in ("ああああ", "ええええ", "おおおお"):
        ref = None
        for k in (0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0):
            g = M0 + k * (V0 - M0)
            spk = edit_glottis(speaker, "modal", dict(x_bottom=g[2], x_top=g[3], chink=g[4], rel_amp=g[6]), OUT / f"onset/steady-{round(100 * k)}.speaker")
            stem = OUT / f"onset/steady/{round(100 * k)}"
            accent.render(text, stem, speaker=Path(spk))
            x = to16(render_ges(spk, stem.with_suffix(".ges"), stem.with_suffix(".wav")), accent._lib.rate)
            x = sosfiltfilt(HP, x); n = len(x); y = x[int(.4 * n):int(.6 * n)]
            P, A = 20 * np.log10(np.abs(y).max()), 10 * np.log10((y ** 2).mean())
            ref = ref or (P, A)
            print(f"{text[0]} k {k:.1f} x {10 * g[2]:.2f}/{10 * g[3]:.2f} peak {P - ref[0]:+5.1f} rms {A - ref[1]:+5.1f} HNR {np.nanmedian(voicing.hnr_track(y)):.0f}")


def jvs_reference():
    al = pickle.load(open(OUT / "align.pkl", "rb"))["align"]
    rows, ot = [], []
    for n in women():
        for u, x in load_jvs(n, list(SENTENCES)).items():
            v, o = peaks(level(sosfiltfilt(HP, x)), [(("M" if p == "u" else p), a, b) for p, a, b in al[(n, u)]],
                         ({"b", "d", "g", "by", "gy"}, {"k", "t", "s", "n", "m", "sh", "ch", "ts", "r", "y", "z", "h", "j"}))
            rows += v; ot += o
    print(f"JVS b d g   {summary(rows)}\nJVS others  {summary(ot)}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "--steady":
        steady(str(Path(a[1]).resolve())); sys.exit()
    if a[0] == "--jvs":
        jvs_reference(); sys.exit()
    if a[0] == "--swap":
        swap(a[1])
    else:
        for q in a:
            tokens_table(*q.split("="))
