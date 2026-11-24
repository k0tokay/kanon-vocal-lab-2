"""Try glottal shapes for the obstruents: small sentences of C V, measured like the corpus tokens.

    glottis_scan.py <speaker> <shape name> "x_bottom,x_top,chink,rel_amp" ...   ("=" keeps the speaker's)
"""
import sys

from compare import *
from build import INDEX, edit_glottis as edit

TEXT = {"voiced-plosive": ["あばばば", "あだだだ", "あががが", "ぐぎげご"],
        "voiceless-plosive": ["あぱぱぱ", "あたたた", "あかかか", "くきけこ"],
        "voiceless-fricative": ["あささ", "すせそ", "あししゃ", "しゅしょ", "はへほ", "ひふ"],
        "voiced-fricative": ["あざざ", "ずぜぞ", "あじじゃ", "じゅじょ"], "modal": ["あだだだ"], "h": ["ははは", "あへほ"]}


def run(speaker, shape):
    rows = []
    for j, t in enumerate(TEXT[shape]):
        stem = OUT / f"scan/{shape}-{j}-{accent.os.getpid()}"
        r = accent.render(t, stem, speaker=Path(speaker))
        sr, x = wavfile.read(stem.with_suffix(".wav"))
        b = []
        for q, (s, e) in zip(r["units"], r["spans"]):
            if isinstance(q, accent.Pause):
                continue
            if q.consonant:
                k = [g for g in r["segments"] if s - 1e-6 <= g.t0 < e - 1e-6][-1]
                b += [(q.consonant, s, k.t0), (q.vowel, k.t0, e)]
            else:
                b.append((q.vowel, s, e))
        rows += list(measure_one((level(to16(x / 32768.0, sr)), b)).values())
    return rows


if __name__ == "__main__":
    spk, shape = sys.argv[1:3]
    keys = ["closure_ms", "closure_low", "closure_mid", "voice_min", "burst_mid", "burst_1k", "burst_4k", "vot_ms",
            "fric_ms", "fric_level", "fric_cog", "fb_2k", "fb_4k", "fb_6k", "fric_voice", "dip_mid"]
    for a in sys.argv[3:]:
        f = spk
        if a != "=":
            f = edit(spk, shape, dict(zip(INDEX, map(float, a.split(",")))), OUT / f"scan-{shape}-{abs(hash(a)) % 10**6}-{accent.os.getpid()}.speaker")
        rows = run(f, shape)
        m = lambda k: np.median([r[k] for r in rows if k in r]) if any(k in r for r in rows) else np.nan
        print(f"{a:28s}", " ".join(f"{k} {m(k):.1f}" for k in keys if m(k) == m(k)), flush=True)
