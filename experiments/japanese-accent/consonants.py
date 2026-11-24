"""Measure the Japanese consonant and devoicing edits.

Run from the repository root:
    python3 experiments/japanese-accent/consonants.py
Writes results/consonants/*.wav and results/consonants/summary.json.
"""
import json
from pathlib import Path

import numpy as np
from scipy.io.wavfile import read

from accent import render

OUT = Path(__file__).resolve().parent / "results/consonants"


def frames(x, sr, t0, t1, keep=.6):
    """Middle `keep` fraction of [t0, t1)."""
    pad = (1 - keep) / 2 * (t1 - t0)
    return x[int((t0 + pad) * sr):int((t1 - pad) * sr)]


def low_band_db(x, sr):
    """Energy in 70-500 Hz (fundamental and first harmonics), in dB.

    Aspiration and frication noise carry little energy there, so this
    separates voicing from noise better than an autocorrelation peak,
    which narrow-band (formant-filtered) noise also produces.
    """
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), 8192)) ** 2
    f = np.fft.rfftfreq(8192, 1 / sr)
    band = (f > 70) & (f < 500)
    return float(10 * np.log10(spec[band].sum() / len(x) + 1e-20))


def spectrum_stats(x, sr):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), 8192)) ** 2
    f = np.fft.rfftfreq(8192, 1 / sr)
    band = (f > 1000) & (f < 11000)
    cog = float((f[band] * spec[band]).sum() / spec[band].sum())
    smooth = np.convolve(spec, np.ones(25) / 25, "same")
    peak = float(f[band][np.argmax(smooth[band])])
    return cog, peak


def rms_db(x):
    return float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12))


def main():
    summary = {}

    # Devoicing: vowels between voiceless consonants.
    text = "私は菊が少し好きです。"
    dev = {}
    variants = {"drop": dict(devoice="drop"), "keep": dict(devoice="keep"),
                "drop-palatal": dict(devoice="drop", palatal_i=True),
                "keep-palatal": dict(devoice="keep", palatal_i=True)}
    for name, kw in variants.items():
        r = render(text, OUT / f"devoicing-{name}", f0_model=None, **kw)
        sr, x = read(OUT / f"devoicing-{name}.wav")
        x = x / 32767
        voiced = [s for s in r["segments"] if s.name in ("a", "e", "o")]
        ref = np.mean([low_band_db(frames(x, sr, s.t0, s.t0 + s.duration), sr) for s in voiced])
        # Devoiced moras: onset start to the end of the (possibly dropped) vowel.
        rows, mora = [], None
        for u, span in zip(r["units"], r["spans"]):
            if getattr(u, "vowel", "").isupper():
                seg = frames(x, sr, *span, keep=.8)
                rows.append(dict(mora=u.consonant + u.vowel.lower(), t=round(span[0], 3),
                                 low_band_re_vowel_db=round(low_band_db(seg, sr) - ref, 1),
                                 rms_db=round(rms_db(seg), 1)))
        dev[name] = dict(segments=[[s.name, round(s.duration, 3), s.tag] for s in r["segments"]],
                         devoiced_moras=rows)
    summary["devoicing"] = dict(text=text, **dev)

    # Fricatives in /a_a/ frames, VTL default versus Japanese edits.
    fric = {}
    for word, label in [("アシア", "shi"), ("アシャア", "sha"), ("アシュア", "shu"),
                        ("アチア", "chi"), ("アフア", "fu"), ("アヒア", "hi"),
                        ("アサア", "sa"), ("アスア", "su")]:
        variants = [("vtl", dict(japanese=False)), ("japanese", dict(japanese=True))]
        fric[label] = {}
        for name, kw in variants:
            r = render(word, OUT / f"{label}-{name}", f0_model=None, **kw)
            sr, x = read(OUT / f"{label}-{name}.wav")
            x = x / 32767
            seg = next(s for s in r["segments"]
                       if s.name in ("S", "C", "f", "s", "h", "s\\", "tS", "ts\\"))
            # Affricates: measure only the fricative part (after the 33% closure).
            start = seg.t0 + (.33 * seg.duration if seg.name in ("tS", "ts\\") else 0)
            part = frames(x, sr, start, seg.t0 + seg.duration)
            cog, peak = spectrum_stats(part, sr)
            vowel = next(s for s in r["segments"] if s.name == "a")
            fric[label][name] = dict(
                segment=seg.name, cog_hz=round(cog), peak_hz=round(peak),
                level_re_vowel_db=round(rms_db(part) - rms_db(frames(x, sr, vowel.t0, vowel.t0 + vowel.duration)), 1),
                low_band_re_vowel_db=round(low_band_db(part, sr) - low_band_db(
                    frames(x, sr, vowel.t0, vowel.t0 + vowel.duration), sr), 1))
    summary["fricatives"] = fric

    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
