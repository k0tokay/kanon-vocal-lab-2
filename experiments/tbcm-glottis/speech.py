"""Voicing, F0 tracking, level and consonant noise of a seg file, TBCM against the speaker's own glottis."""
import sys, re, numpy as np
from synth import *
from scipy.signal import stft
def segs(p):
    out, t = [], 0
    for l in open(p):
        m = re.match(r'name = ([^;]*);.*?duration_s = ([\d.]+)', l)
        if not m: continue
        f = [float(x) for x in re.findall(r'Hz = ([\d.]+)', l)]
        out.append((m.group(1).strip(), t, t+float(m.group(2)), f)); t += float(m.group(2))
    return out
def report(seg, spk, stem):
    fs, x = synth(seg, spk, stem); save(stem+'.wav', x, fs)
    f0 = f0_track(x, fs); rows = []
    for n, a, b, f in segs(seg):
        if not n: continue
        s = x[int(a*fs):int(b*fs)]; mid = s[len(s)//5:-len(s)//5]
        i, j = int((a-.015)/.005), int((b-.015)/.005); seg0 = f0[max(0,i):j]
        v = seg0[seg0 > 0]; w = mid*np.hanning(len(mid)); P = abs(np.fft.rfft(w, 8192))**2; fr = np.fft.rfftfreq(8192, 1/fs)
        hp = 10*np.log10(P[(fr>2500)&(fr<12000)].sum()+1e-20); lp = 10*np.log10(P[(fr>80)&(fr<600)].sum()+1e-20)
        rows.append((n, a, 20*np.log10(np.sqrt(np.mean(mid**2))+1e-9), len(v)/max(1,len(seg0)), np.median(v) if len(v) else 0, np.mean(f) if f else 0, lp, hp))
    return rows
if __name__ == '__main__':
    a = [report(sys.argv[1], s, f'build/syl/r{i}') for i, s in enumerate(sys.argv[2:])]
    print('seg   t     target ' + ' | '.join('lev  voiced F0 lowdB highdB' for _ in a))
    for rs in zip(*a):
        print(f'{rs[0][0]:4} {rs[0][1]:5.2f} {rs[0][5]:5.0f}  ' + ' | '.join(f'{r[2]:6.1f} {r[3]:4.2f} {r[4]:5.0f} {r[6]:5.0f} {r[7]:5.0f}' for r in rs))
