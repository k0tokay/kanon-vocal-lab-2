"""Synthesize seg files or single segments with a speaker through the API.
Needs the API library (VTL_LIB)."""
import ctypes as ct, os, sys, re
import numpy as np
from scipy.io import wavfile
LIB = os.environ.get('VTL_LIB', os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../build-mac/gui/libVocalTractLabApi.dylib'))
lib = ct.CDLL(LIB)


def synth(seg, speaker, stem, log=False):
    assert lib.vtlInitialize(speaker.encode()) == 0
    c = [ct.c_int() for _ in range(4)]
    assert lib.vtlGetConstants(*map(ct.byref, c)) == 0
    ges = stem + '.ges'
    assert lib.vtlSegmentSequenceToGesturalScore(seg.encode(), ges.encode()) == 0
    n = ct.c_int()
    lib.vtlGesturalScoreToAudio(ges.encode(), b'', b'', None, ct.byref(n), 0, 0)
    buf = (ct.c_double*n.value)()
    misc = (stem + '.csv').encode() if log else b''
    assert lib.vtlGesturalScoreToAudio(ges.encode(), b'', misc, buf, ct.byref(n), 0, 0) == 0
    lib.vtlClose()
    return c[0].value, np.frombuffer(buf, dtype=float).copy()


def f0_track(x, fs, step=.005, win=.03):
    """Autocorrelation F0 (Hz, 0 if unvoiced)."""
    N, out = int(win*fs), []
    for i in range(0, len(x) - 2*N, int(step*fs)):
        a = x[i:i+N] - x[i:i+N].mean()
        if np.sqrt(np.mean(a*a)) < .005*np.abs(x).max(): out.append(0); continue
        r = np.array([np.dot(a, x[i+l:i+l+N])/np.sqrt(np.dot(a, a)*np.dot(x[i+l:i+l+N], x[i+l:i+l+N]) + 1e-12) for l in range(fs//700, fs//70)])
        m = r.max()
        if m < .6: out.append(0); continue
        k = next(j for j in range(1, len(r)-1) if r[j] > .93*m and r[j] >= r[j-1] and r[j] >= r[j+1]) if np.argmax(r) not in (0, len(r)-1) else int(np.argmax(r))
        out.append(fs/(k + fs//700))
    return np.array(out)


def save(path, x, fs, peak=.8):
    wavfile.write(path, fs, (x/np.abs(x).max()*peak*32767).astype(np.int16))


if __name__ == '__main__':
    seg, speaker, stem = sys.argv[1:4]
    fs, x = synth(seg, speaker, stem)
    save(stem + '.wav', x, fs)
    print(len(x)/fs, 's, max', np.abs(x).max(), 'rms', np.sqrt(np.mean(x*x)))
