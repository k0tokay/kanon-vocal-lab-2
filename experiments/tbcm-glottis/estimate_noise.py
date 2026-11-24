"""Aspiration of an estimate in Kanon's tract: the floor between the harmonics is matched with a recording.
The tone follows the F0 and the level of the recording, because jitter leaks into the floor as well.

    python3 estimate_noise.py estimate.json recording.wav start_s

The room noise of the recording is part of the floor, so the result is an upper bound."""
import sys, os, json, numpy as np, subprocess
from scipy.io import wavfile
from concurrent.futures import ThreadPoolExecutor
import natural as N, estimate as E
fs = 48000; DUR = 2.5
def track(x, hop=.02):
    """F0 and level of the recording every hop seconds (strongest peak of the autocorrelation, then a fine search)."""
    out = []
    for c in np.arange(.06, len(x)/fs - .06, hop):
        i = int(c*fs); W = int(.03*fs); a = x[i-W:i+W]; r = np.correlate(a - a.mean(), a - a.mean(), 'full')[2*W-1:]; r = r/r[0]/(1 - np.arange(len(r))/len(r)*.999); lo, hi = fs//420, fs//110
        f = fs/(lo + int(r[lo:hi].argmax())); L = int(2.5*fs/f); n = np.arange(-L, L)/fs; w = np.hanning(2*L); s = x[max(0, i-L):i+L]*w if i >= L and i+L <= len(x) else None
        if s is None: continue
        best = None
        for step in (np.linspace(.97, 1.03, 31), np.linspace(.999, 1.001, 11)):
            base = f if best is None else best[1]
            for v in base*step:
                A = np.exp(2j*np.pi*v*np.outer(n, np.arange(1, 7))); M = np.c_[A.real, A.imag]*w[:, None]; e = np.sum((s - M@np.linalg.lstsq(M, s, rcond=None)[0])**2)
                if best is None or e < best[0]: best = (e, v)
        out.append((c, best[1], 20*np.log10(a.std() + 1e-9)))
    T, F, L = np.array(out).T; t = np.arange(len(x))/fs; return np.interp(t, T, np.convolve(np.pad(F, 2, 'edge'), np.ones(5)/5, 'valid')), np.interp(t, T, L)
def render(par, n, tag, asp, cut):
    z = N.enc([par[k] for k in N.NAMES]); env = {k: v for k, v in os.environ.items() if k != 'PROBE_HARM'}
    subprocess.run(['./build/glottis_probe', N.SPK, 'a', 'bcg', 'build/' + tag], input=N.line(z, dur=n/fs + .6, extra=f'14={asp} 15={cut}') + '\n', capture_output=True, text=True, env=env); return np.fromfile(f'build/{tag}00.f64')[int(.2*fs):]
def follow(y, f0, lev, base): return np.interp(np.cumsum(f0/base)/fs, np.arange(len(y))/fs, y)*10**((lev - np.median(lev))/20)
def floor(y, tag):
    p = f'build/{tag}.wav'; wavfile.write(p, fs, (y*.5/np.abs(y).max()*32767).astype(np.int16)); t = E.measure(p, t0=.15, t1=DUR - .9, hop=.08, guess=203); os.remove(p); return np.array(t['noise'])
if __name__ == '__main__':
    src, rec, t0 = sys.argv[1], sys.argv[2], float(sys.argv[3]); s = json.load(open(src))[0]; par, base = s['par'], s['f0']
    f, x = wavfile.read(rec); x = x.astype(float)/(np.iinfo(x.dtype).max if x.dtype.kind == 'i' else 1); x = x if f == fs else np.interp(np.arange(int(len(x)*fs/f))*f/fs, np.arange(len(x)), x)
    x = x[int(t0*fs):int((t0 + DUR)*fs)]; f0, lev = track(x); target = floor(x, 'en_rec'); grid = [(a, c) for a in (-60, -48, -42, -36, -30, -24, -18) for c in (1000, 3000, 8000)]
    def one(k): y = follow(render(par, len(x), f'en{k}', *grid[k]), f0, lev, base); return np.mean(np.abs((floor(y, f'en{k}') - target)[4:22]))
    with ThreadPoolExecutor(3) as ex: e = list(ex.map(one, range(len(grid))))
    for k in np.argsort(e)[:6]: print('aspiration %d dB cutoff %d Hz: mean floor error %.1f dB' % (*grid[k], e[k]))
