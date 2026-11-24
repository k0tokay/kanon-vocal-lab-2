"""Acoustic measures of one consonant token, the same code for JVS and synthesis (16 kHz).

token(x, a, b, v1): x = audio, [a, b] = consonant span, v1 = end of the following vowel.
All levels are dB re the following vowel (median 1-8 kHz or 80-8000 Hz level of its middle half).
"""
import numpy as np

RS = 16000
HOP = 16                      # 1 ms
EPS = 1e-12

BANDS = [(80, 500), (500, 1000), (1000, 2000), (2000, 3000), (3000, 4000), (4000, 5000), (5000, 6000), (6000, 7800)]


class Spec:
    """Short-time power on a 1 ms grid: 6 ms window for the high bands, 20 ms for voicing."""

    def __init__(self, x):
        self.x = x
        self.n = max(1, len(x) // HOP)
        self.hi = self._stft(96, 256)
        self.lo = self._stft(320, 1024)

    def _stft(self, win, nfft):
        pad = np.pad(self.x, (win // 2, win))
        w = np.hanning(win)
        w = w / np.sqrt((w ** 2).sum())
        out = np.empty((self.n, nfft // 2 + 1), np.float32)
        for k in range(0, self.n, 4096):
            i = np.arange(k, min(self.n, k + 4096))[:, None] * HOP + np.arange(win)[None]
            out[k:k + 4096] = np.abs(np.fft.rfft(pad[i] * w, nfft)) ** 2
        return out, np.fft.rfftfreq(nfft, 1 / RS)

    def band(self, lo, hi, which="hi"):
        p, f = getattr(self, which)
        return 10 * np.log10(p[:, (f >= lo) & (f < hi)].sum(1) + EPS)


STOPS = {"p", "t", "k", "b", "d", "g", "py", "ty", "ky", "by", "dy", "gy"}
AFFR = {"ts", "ch", "j", "z"}
FRIC = {"s", "sh", "h", "hy", "f"}
NASAL = {"m", "n", "my", "ny", "N"}
APPROX = {"r", "ry", "w", "y"}


def token(sp, a, b, v1, phone):
    """a, b, v1 in seconds. Returns a dict of measures (missing ones are absent)."""
    o = {"dur_ms": 1000 * (b - a)}
    n = sp.n
    ms = lambda t: int(np.clip(round(t * 1000), 0, n - 1))
    v0, ve = b, min(v1, b + .14)
    q = slice(ms(v0 + .35 * (ve - v0)), max(ms(v0 + .8 * (ve - v0)), ms(v0 + .35 * (ve - v0)) + 3))
    hi, mid, full, low = sp.band(2000, 7800), sp.band(1000, 7800), sp.band(80, 7800), sp.band(80, 500, "lo")
    Rh, Rm, Rf, Rl = (np.median(y[q]) for y in (hi, mid, full, low))
    w0, w1 = ms(a - .02), ms(b + .03)
    if w1 - w0 < 10:
        return o
    win = slice(w0, w1)
    o["dip_full"] = float(full[win].min() - Rf)
    o["dip_mid"] = float(mid[win].min() - Rm)
    o["peak_hi"] = float(np.max(hi[ms(a):ms(b + .015)]) - Rh)
    o["voice_min"] = float(low[win].min() - Rl)
    if phone in STOPS or phone in AFFR:
        # closure = the longest run within 8 dB of the lowest 1-7.8 kHz level and >= 12 dB below the vowel
        # (deeper than any recording's noise floor counts as equally silent: in a geminate the synthesis
        # decays for tens of ms, and the run within 8 dB of its minimum would be only the end of it)
        y = np.maximum(mid[win], Rm - 60)
        thr = max(y.min() + 8, min(Rm - 25, y.min() + 14))
        low_run = y < min(thr, Rm - 10)
        e = np.flatnonzero(np.diff(np.r_[0, low_run.astype(int), 0])).reshape(-1, 2)
        if len(e):
            k = np.argmax(e[:, 1] - e[:, 0])
            c0, c1 = e[k] + w0
            o["closure_ms"] = float(c1 - c0)
            o["closure_mid"] = float(np.median(mid[c0:c1]) - Rm)
            o["closure_low"] = float(np.median(low[c0:c1]) - Rl)
            r = slice(c1 - 2, min(c1 + 14, n))
            o["burst_mid"] = float(mid[r].max() - Rm)
            p, f = sp.hi
            s = p[c1 - 2 + int(np.argmax(mid[r])) - 2:c1 - 2 + int(np.argmax(mid[r])) + 5].mean(0)
            g = (f >= 1000) & (f < 7800)
            o["burst_cog"] = float((f[g] * s[g]).sum() / s[g].sum())
            for lo_, hi_ in ((1000, 2000), (2000, 4000), (4000, 7800)):
                o[f"burst_{lo_ // 1000}k"] = float(10 * np.log10(s[(f >= lo_) & (f < hi_)].sum() + EPS) - Rm)
            up = np.flatnonzero(low[c1:min(c1 + 120, n)] > Rl - 8)
            if len(up):
                o["vot_ms"] = float(up[0])
            o["cv_ms"] = float(c1 - ms(b))
    if phone in FRIC or phone in AFFR:
        y = hi[ms(a):ms(b + .015)]
        k = np.flatnonzero(y > y.max() - 5)
        s0, s1 = ms(a) + k[0], ms(a) + k[-1] + 1
        pad = int(.15 * (s1 - s0)); s0, s1 = s0 + pad, max(s1 - pad, s0 + pad + 4)
        o["fric_ms"] = float(s1 - s0)
        p, f = sp.hi
        s = p[s0:s1].mean(0)
        g = (f >= 1000) & (f < 7800)
        o["fric_cog"] = float((f[g] * s[g]).sum() / s[g].sum())
        o["fric_level"] = float(10 * np.log10(s[g].sum()) - Rm)
        o["fric_full"] = float(10 * np.log10(s[f >= 80].sum()) - Rf)
        tot = 10 * np.log10(s[g].sum())
        for lo_, hi_ in BANDS[2:]:
            o[f"fb_{lo_ // 1000}k"] = float(10 * np.log10(s[(f >= lo_) & (f < hi_)].sum() + EPS) - tot)
        o["fric_voice"] = float(np.median(low[s0:s1]) - Rl)
    if phone in NASAL or phone in APPROX:
        c = slice(ms(a + .2 * (b - a)), max(ms(a + .8 * (b - a)), ms(a + .2 * (b - a)) + 3))
        p, f = sp.lo
        s = p[c].mean(0); v = p[q].mean(0)
        for lo_, hi_ in BANDS[:5]:
            g = (f >= lo_) & (f < hi_)
            o[f"nb_{lo_ / 1000:g}k"] = float(10 * np.log10(s[g].sum() / v[g].sum() + EPS))
        y = sp.band(500, 4000)[win]
        o["dip_500_4k"] = float(y.min() - np.median(sp.band(500, 4000)[q]))
    return o
