"""Steady vowels against the vowels of sentences, with the state of the TBCM.

    build-mac/py.sh experiments/tbcm-control/diag.py [variant ...]

Each variant is a way of making the gestural score or the speaker (see VARIANTS).
For every voiced vowel of the sentences, a steady vowel of the same identity at the
same target F0 is synthesized with the same variant, and both are measured in the
middle half of the vowel from the per-sample log of build/ges_probe.
"""
import json, os, re, subprocess, sys, shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments/japanese-accent"))
import accent                                     # noqa: E402
from gestures import Score                        # noqa: E402

SPEAKER = ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v1-4-1.speaker"
PROBE = HERE / "build/ges_probe"
OUT = HERE / "build/diag"
FS = 48000
COLS = ["audio", "flow", "f0", "pressure", "lca", "ia", "pca", "ct", "ta", "strain", "vp",
        "area_lo", "area_up", "area_post", "contact", "natural_f0", "measured_f0"]
SENTENCES = {
    "tenki": "今日はいい天気ですね。",
    "ame": "雨が降っていますが、私は傘を持っていません。",
    "kanon": "私の名前は嘉音です。よろしくお願いします。",
}
VOWELS = set("aieoM")


def load(path):
    x = np.fromfile(path, dtype=np.float32).reshape(-1, len(COLS))
    return {c: x[:, i].astype(float) for i, c in enumerate(COLS)}


def probe(ges, log, speaker, static=()):
    subprocess.run([str(PROBE), str(speaker), str(ges), str(log), *static], check=True,
                   stdout=subprocess.DEVNULL)
    return load(log)


# ---------------------------------------------------------------- measures

def harmonic(y, f, fs=FS):
    n = len(y)
    w = np.hanning(n)
    t = np.arange(n) / fs
    return 20 * np.log10(abs(np.sum(w * y * np.exp(-2j * np.pi * f * t))) + 1e-12)


def measure(L, a, b):
    """Voice measures in the samples [a, b) of a log."""
    i0, i1 = int(a * FS), int(b * FS)
    flow = L["flow"][i0:i1]
    f0t = np.mean(L["f0"][i0:i1])
    d = np.diff(flow) * FS                       # flow derivative ~ source of the radiated sound
    # F0 from upward crossings of the flow's mean
    y = flow - flow.mean()
    up = np.where((y[:-1] < 0) & (y[1:] >= 0))[0]
    if len(up) >= 3:
        f0m = FS / np.median(np.diff(up))
    else:
        f0m = 0.0
    lo, hi = np.percentile(flow, 1), np.percentile(flow, 99)
    cq = np.mean(flow < lo + .1 * (hi - lo)) if hi - lo > 1 else 1.0
    f = f0m if f0m > 0 else f0t
    h1, h2 = harmonic(d, f), harmonic(d, 2 * f)
    # energies, so that the length of the window does not matter
    spec = abs(np.fft.rfft(d * np.hanning(len(d)), 1 << 16)) ** 2
    fr = np.fft.rfftfreq(1 << 16, 1 / FS)
    band = 10 * np.log10(spec[(fr > 2000) & (fr < 5000)].sum() + 1e-20)
    hpk = 10 * np.log10(spec[(fr > .5 * f) & (fr < 1.5 * f)].sum() + 1e-20)
    aud = L["audio"][i0:i1]
    voiced = np.mean(L["measured_f0"][i0:i1] > 0)
    return dict(voiced=voiced, f0_target=f0t, f0=f0m, f0_err=12 * np.log2(f0m / f0t) if f0m > 0 else np.nan,
                cq=cq, h1h2=h1 - h2, drop=hpk - band, ac=hi - lo, dc=lo,
                level=20 * np.log10(np.sqrt(np.mean(aud ** 2)) + 1e-9),
                ta=np.mean(L["ta"][i0:i1]), lca=np.mean(L["lca"][i0:i1]), ia=np.mean(L["ia"][i0:i1]),
                pca=np.mean(L["pca"][i0:i1]), pressure=np.mean(L["pressure"][i0:i1]),
                strain=np.mean(L["strain"][i0:i1]), vp=10 * np.mean(L["vp"][i0:i1]),
                post=100 * np.mean(L["area_post"][i0:i1]))


def onset(L, c0, t0, t1):
    """Voice onset (ms) relative to the vowel start t0: the first time after the middle of
    the preceding consonant [c0, t0) at which the AC amplitude of the flow (the flow minus
    its mean over one period) reaches half of its value in the middle of the vowel.
    Negative if the voice goes on through the consonant."""
    f0 = max(80.0, np.mean(L["f0"][int(t0 * FS):int(t1 * FS)]))
    p = int(FS / f0)
    s = int((c0 + t0) / 2 * FS)
    flow = L["flow"][s - p:int(t1 * FS)]
    ac = (flow - np.convolve(flow, np.ones(p) / p, "same"))[p:]
    step = p // 4
    amp = np.array([np.ptp(ac[k:k + p]) for k in range(0, len(ac) - p, step)])
    v0 = int((t0 * FS - s) / step)
    mid = amp[v0 + (len(amp) - v0) // 3: v0 + 2 * (len(amp) - v0) // 3]
    if len(mid) < 2:
        return np.nan
    k = np.argmax(amp >= .5 * np.median(mid))
    return 1000 * (s + k * step + p / 2 - t0 * FS) / FS


# ---------------------------------------------------------------- material

def read_seg(path):
    seg, t = [], 0.0
    for l in Path(path).read_text().splitlines():
        m = re.match(r"name = ([^;]*); duration_s = ([\d.]+);", l)
        seg.append((m.group(1), t, t + float(m.group(2))))
        t += float(m.group(2))
    return seg


def sentence(key, variant, speaker):
    stem = OUT / variant["name"] / key
    accent.render(SENTENCES[key], stem, speaker=speaker, f0_model=None, accent=variant.get("accent", True))
    return stem.with_suffix(".ges"), read_seg(stem.with_suffix(".seg"))


def steady(vowel, f0, variant, speaker):
    stem = OUT / variant["name"] / f"steady-{vowel}-{f0:.0f}"
    seg = stem.with_suffix(".seg")
    seg.parent.mkdir(parents=True, exist_ok=True)
    seg.write_text(f"name = ; duration_s = 0.150000; f0_20%_Hz = 0; f0_50%_Hz = 0; f0_80%_Hz = 0;\n"
                   f"name = {vowel}; duration_s = 0.900000; f0_20%_Hz = {f0:.2f}; f0_50%_Hz = {f0:.2f}; f0_80%_Hz = {f0:.2f};\n"
                   f"name = ; duration_s = 0.150000; f0_20%_Hz = 0; f0_50%_Hz = 0; f0_80%_Hz = 0;\n")
    lib = accent.use_speaker(speaker)
    ges = stem.with_suffix(".ges")
    assert lib.vtlSegmentSequenceToGesturalScore(bytes(seg), bytes(ges)) == 0
    return ges


def run(variant, keys=tuple(SENTENCES), remeasure=False):
    """Returns rows: one per sentence vowel with the sentence and steady measures.
    remeasure: use the logs of an earlier run."""
    name = variant["name"]
    (OUT / name).mkdir(parents=True, exist_ok=True)
    speaker = variant.get("speaker", SPEAKER)
    static = variant.get("static", ())
    edit = variant.get("edit")
    jobs, rows = [], []
    for key in keys:
        if remeasure:
            ges, seg = OUT / name / f"{key}.ges", read_seg(OUT / name / f"{key}.seg")
        else:
            ges, seg = sentence(key, variant, speaker)
            if edit:
                edit(ges, seg)
        jobs.append((key, ges, seg))
    logs = {}
    with ThreadPoolExecutor(8) as ex:
        fut = {key: ex.submit(load, ges.with_suffix(".f32")) if remeasure else
               ex.submit(probe, ges, ges.with_suffix(".f32"), speaker, static) for key, ges, seg in jobs}
        for key in fut:
            logs[key] = fut[key].result()
    targets = {}
    for key, ges, seg in jobs:
        L = logs[key]
        for i, (n, t0, t1) in enumerate(seg):
            if n not in VOWELS or t1 - t0 < .06:
                continue
            prev = seg[i - 1][0] if i else ""
            a, b = t0 + .25 * (t1 - t0), t1 - .25 * (t1 - t0)
            m = measure(L, a, b)
            if m["voiced"] < .9 or m["dc"] > 50:       # devoiced vowel or no voice
                continue
            f0r = 5 * round(m["f0_target"] / 5)
            targets[(n, f0r)] = None
            rows.append(dict(key=key, vowel=n, prev=prev, t0=t0, t1=t1, f0r=f0r,
                             onset=onset(L, seg[i - 1][1], t0, t1) if i else np.nan, sent=m))
    # steady vowels, measured in a window of the same length
    for k in targets:
        targets[k] = OUT / name / f"steady-{k[0]}-{k[1]:.0f}.ges" if remeasure else steady(k[0], k[1], variant, speaker)
    if edit and not remeasure:
        for k, ges in targets.items():
            edit(ges, [("", 0, .15), (k[0], .15, 1.05), ("", 1.05, 1.2)])
    with ThreadPoolExecutor(8) as ex:
        fut = {k: ex.submit(load, g.with_suffix(".f32")) if remeasure else
               ex.submit(probe, g, g.with_suffix(".f32"), speaker, static) for k, g in targets.items()}
        res = {k: f.result() for k, f in fut.items()}
    for r in rows:
        w = (r["t1"] - r["t0"]) / 4
        r["steady"] = measure(res[(r["vowel"], r["f0r"])], .6 - w, .6 + w)
    return rows


# ---------------------------------------------------------------- reporting

KEYS = ["f0_err", "h1h2", "cq", "drop", "level", "ac", "dc", "ta", "lca", "ia", "pressure", "strain", "vp", "post"]


def summary(rows):
    s = {}
    for k in KEYS:
        a = np.array([r["sent"][k] for r in rows])
        b = np.array([r["steady"][k] for r in rows])
        s[k] = (np.nanmean(a), np.nanmean(b), np.nanmean(a - b), np.nanmean(abs(a - b)))
    s["onset"] = np.nanmedian([r["onset"] for r in rows if r["prev"] and r["prev"] not in VOWELS])
    s["f0_abs"] = float(np.nanmean([abs(r["sent"]["f0_err"]) for r in rows]))
    s["onset_voiceless"] = np.nanmedian([r["onset"] for r in rows if r["prev"] in VOICELESS])
    s["n"] = len(rows)
    for g, sel in GROUPS.items():
        rs = [r for r in rows if sel(r["prev"])]
        s["group_" + g] = {k: (len(rs), float(np.nanmean([r["sent"][k] - r["steady"][k] for r in rs]))) for k in ("h1h2", "cq", "drop", "dc", "ta", "ia", "f0_err")}
    return s


VOICELESS = ("k", "t", "s", "S", "ts", "tS", "p", "h", "C", "s\\", "ts\\", "f", "x")
GROUPS = {"after_vowel_or_pause": lambda p: p in VOWELS or p == "",
          "after_voiceless": lambda p: p in VOICELESS,
          "after_voiced_consonant": lambda p: not (p in VOWELS or p == "" or p in VOICELESS)}


def print_summary(name, s):
    print(f"\n== {name}  (n={s['n']}, onset after consonant {s['onset']:.1f} ms, after voiceless {s['onset_voiceless']:.1f} ms, |F0 err| {s['f0_abs']:.2f} st)")
    print(f"{'':9}{'sentence':>10}{'steady':>10}{'diff':>9}{'|diff|':>9}")
    for k in KEYS:
        a, b, d, ad = s[k]
        print(f"{k:9}{a:10.3f}{b:10.3f}{d:9.3f}{ad:9.3f}")
    for g in GROUPS:
        print(f"  {g:24}" + "  ".join(f"{k} {v[1]:+.3f}" for k, v in s["group_" + g].items()) + f"  (n={s['group_' + g]['h1h2'][0]})")


if __name__ == "__main__":
    import variants
    args = sys.argv[1:]
    remeasure = "--remeasure" in args
    names = [a for a in args if a != "--remeasure"] or ["base"]
    allres = {}
    for n in names:
        v = variants.VARIANTS[n]
        v["name"] = n
        rows = run(v, remeasure=remeasure)
        s = summary(rows)
        print_summary(n, s)
        allres[n] = dict(summary={k: (list(v) if isinstance(v, tuple) else v) for k, v in s.items()}, rows=rows)
        (OUT / n / "rows.json").write_text(json.dumps(rows, default=float, indent=0))
    (OUT / f"summary-{'-'.join(names)}.json").write_text(json.dumps({k: v["summary"] for k, v in allres.items()}, default=float, indent=1))
