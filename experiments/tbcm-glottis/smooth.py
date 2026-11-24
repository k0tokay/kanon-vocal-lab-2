"""Smooth voices: same posture from different muscle combinations, harmonics and breath measured apart.
Harmonics: the same sentence without aspiration. Breath: 2-10 kHz power of (full - harmonics-only) relative
to the whole vowel level. Writes results/smooth."""
import os, sys, json, numpy as np
from explore import *
from features import features, segments, VOW
from synth import save
OUT = 'results/smooth'
def mk(lca, ia, pca, ta, asp, tr=(0, 1, 1), p=1.0): return dict(m=(lca, ia, pca, .115, ta, 25), asp=asp, tr=tr, p=p)
SET = {
    '前回のやさしい中':            mk(.51, .36, 0, .10, -30),
    '保存された手動設定':          mk(.62, .255, .057, .109, -30, p=1.016),
    'LCA100_PCA22':               mk(1, .255, .22, .109, -30, p=1.016),
    'LCA100_PCA23':               mk(1, .255, .23, .109, -30, p=1.016),
    'LCA80_PCA12_IA40':           mk(.80, .40, .12, .109, -30, p=1.016),
    'LCA55_IA50_PCA0':            mk(.55, .50, 0, .109, -30, p=1.016),
    'LCA55_IA50_息少なめ':        mk(.55, .50, 0, .109, -34, p=1.016),
    'LCA55_IA50_息ごく少し':      mk(.55, .50, 0, .109, -38, p=1.016),
    'LCA55_IA50_さらに滑らか':    mk(.54, .47, 0, .10, -33),
    'LCA51_IA36_息少なめ':        mk(.51, .36, 0, .10, -35),
    'LCA51_IA36_息ごく少し':      mk(.51, .36, 0, .10, -40),
    'LCA55_IA50_-3半音':          mk(.55, .50, 0, .109, -34, (-3, 1.1, 1), 1.016),
}
def voc(x, seg):
    t = np.arange(len(x))/48000; m = np.zeros(len(x), bool)
    for n, a, b in segments(seg):
        if n in VOW: m |= (t > a + .01) & (t < b - .01)
    return m
def band(x, m, lo, hi):
    w = 1024; f = np.fft.rfftfreq(w, 1/48000); out = []
    for i in range(0, len(x)-w, w//2):
        if m[i:i+w].all(): out.append(np.abs(np.fft.rfft(x[i:i+w]*np.hanning(w)))**2)
    P = np.mean(out, 0); return P[(f >= lo) & (f < hi)].sum()
if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True); jobs = []
    for k, (n, c) in enumerate(SET.items()):
        for tag, a in (('f', c['asp']), ('h', -60)):
            jobs.append((f's{k}{tag}', c['tr'], dict(modal=c['m'], static=dict(aspiration_strength=a), pressure=c['p'], advance=.025)))
    R = dict(table(jobs))
    print(f'{"":26} F0  H1H3(h) centr(h) tilt(h) level(h) breath(dB rel) voiced')
    J = {}
    for k, n in enumerate(SET):
        b = []
        for s in ('ame', 'tenki'):
            x, h = (np.load(f'build/ex/s{k}{t}_{s}.npy') for t in 'fh'); seg = f'build/ex/s{k}f_{s}.seg'; m = voc(x, seg)
            b.append(10*np.log10(max(1e-12, band(x, m, 3000, 10000) - band(h, m, 3000, 10000))/band(x, m, 80, 10000)))
        rh, rf = R[f's{k}h'], R[f's{k}f']
        J[n] = dict(F0=rf['F0'], H1H3=rh['H1H3'], centroid=rh['centroid'], tilt=rh['tilt'], power=rh['power'], breath=float(np.mean(b)), voiced=rf['voiced'])
        print(f'{n:26} {rf["F0"]:4.0f} {rh["H1H3"]:5.1f} {rh["centroid"]:6.0f} {rh["tilt"]:6.1f} {rh["power"]:6.1f} {np.mean(b):6.1f} {rf["voiced"]:.2f}')
    make('../../speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-0-tbcm-smooth.speaker', modal=(.54, .47, 0, .115, .10, 25), static=dict(aspiration_strength=-33))
    json.dump(J, open(f'{OUT}/features.json', 'w'), ensure_ascii=False, indent=1)
    gap = np.zeros(24000); k = 0; t = 0
    for s in ('ame', 'tenki'):
        buf = []; t = 0
        for i, n in enumerate(SET):
            x = np.load(f'build/ex/s{i}f_{s}.npy'); w = np.abs(x) > .05*np.abs(x).max()
            y = x*.07/np.sqrt(np.mean(x[w]**2)); y *= min(1, .9/np.abs(y).max()); k += 1
            save(f'{OUT}/{k:02d}_{s}_{n}.wav', y, 48000, peak=np.abs(y).max()); buf += [y, gap]
            print(k, s, n, f'{t:.1f}'); t += len(y)/48000 + .5
        z = np.concatenate(buf); save(f'{OUT}/試聴_滑らか_{s}.wav', z, 48000, peak=np.abs(z).max())
