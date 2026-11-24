"""Acoustic features of Hayashi & Morise (acting voices of age and gender), computed
on the vowels of a seg file. The spectral envelope is a pitch-synchronous power
spectrum smoothed over F0 instead of WORLD's CheapTrick, so compare only values
from this script with each other, not with the paper's table."""
import re, numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import butter, sosfiltfilt
from synth import f0_track
VOW = set('aeioM') | {'@'}


def segments(path):
    out, t = [], 0
    for l in open(path):
        m = re.match(r'name = ([^;]*);.*?duration_s = ([\d.]+)', l)
        if m:
            out.append((m.group(1).strip(), t, t + float(m.group(2)))); t += float(m.group(2))
    return out


def mel(f): return 1127.01048*np.log(f/700 + 1)


def features(x, fs, seg, nfft=2048):
    f0 = f0_track(x, fs); t = np.arange(len(f0))*.005 + .03    # centre of the 60 ms spans
    inv = np.zeros(len(f0), bool)
    for n, a, b in segments(seg):
        if n in VOW: inv |= (t > a) & (t < b)
    total = inv.sum(); ok = inv & (f0 > 0); ok &= f0 < 2*np.median(f0[ok])
    fr = np.fft.rfftfreq(nfft, 1/fs); C, S, H, P = [], [], [], []
    band = sosfiltfilt(butter(4, [2000, 6000], 'band', fs=fs, output='sos'), x); A = []
    for k in np.where(ok)[0]:
        T = fs/f0[k]; c = int(t[k]*fs); L = int(3*T/2); s = x[c-L:c+L]
        if len(s) < 2*L: continue
        p = np.abs(np.fft.rfft(s*np.hanning(2*L), nfft))**2
        w = max(1, int(round(f0[k]/(fs/nfft)))); env = np.maximum(uniform_filter1d(p, w), 0) + 1e-14
        amp = np.sqrt(env); C.append((fr*amp)[fr <= 12000].sum()/amp[fr <= 12000].sum())
        hi = (fr >= 1000) & (fr <= 12000); S.append(np.polyfit(np.log2(fr[hi]), 10*np.log10(env[hi]), 1)[0])
        e = lambda h: 10*np.log10(np.interp(h*f0[k], fr, env)); H.append(e(1) - e(3)); P.append(10*np.log10(env.mean()))
        l = int(round(T)); a = band[c-L:c+L-l]; b = band[c-L+l:c+L]
        A.append(1 - max(0, np.dot(a, b)/np.sqrt(np.dot(a, a)*np.dot(b, b) + 1e-20)))
    f = f0[ok]
    return dict(F0=np.median(f), F0mel=np.median(mel(f)), F0sd=np.std(mel(f)), centroid=np.median(C), tilt=np.median(S),
                H1H3=np.median(H), power=np.median(P), aper=np.median(A), voiced=ok.sum()/total)
