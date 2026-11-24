"""Gentle and boyish settings: speaker files, features and listening set in results/gentle."""
import os, sys, json, numpy as np
from explore import *
from synth import synth, save
OUT = 'results/gentle'; SPK = '../../speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-0-tbcm%s.speaker'
S = lambda a: dict(aspiration_strength=a)
AD = .025      # s, see synth.advance_closing
SETTINGS = {   # (F0 shift st, F0 range, rate), modal (LCA, IA, PCA, CT, TA, flutter), aspiration dB, pressure factor
    '今のTBCM':          ((0, 1, 1), (.57, .40, 0, .2, .17, 25), -34, 1.0),
    'やさしい_弱':       ((0, 1, 1), (.54, .38, 0, .2, .11, 25), -32, 1.0),
    'やさしい_中':       ((0, 1, 1), (.51, .36, 0, .2, .10, 25), -30, 1.0),
    'やさしい_強':       ((0, 1, 1), (.49, .34, 0, .2, .08, 25), -29, .95),
    'やさしい_中_F0だけ下げる': ((-4, 1, 1), (.51, .36, 0, .2, .10, 25), -30, 1.0),
    '少年_息を少し残す': ((-4, 1.2, 1), (.54, .38, 0, .2, .14, 25), -31, 1.05),
    '少年_張り':         ((-4, 1.2, 1), (.55, .38, 0, .2, .18, 25), -32, 1.1),
}
JOBS = [(f'g{k}', tr, dict(modal=m, static=S(a), pressure=p, advance=AD)) for k, (tr, m, a, p) in enumerate(SETTINGS.values())]
if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    R = table(JOBS)
    json.dump({n: r for n, (_, r) in zip(SETTINGS, R)}, open(f'{OUT}/features.json', 'w'), ensure_ascii=False, indent=1)
    make(SPK % '-gentle', modal=SETTINGS['やさしい_中'][1], static=S(-30))
    make(SPK % '-gentle-boy', modal=SETTINGS['少年_息を少し残す'][1], static=S(-31))
    gap = np.zeros(24000); t = 0; k = 0; buf = []
    for s in ('ame', 'tenki'):
        for i, n in enumerate(SETTINGS):
            x = np.load(f'build/ex/g{i}_{s}.npy'); w = np.abs(x) > .05*np.abs(x).max()
            y = x*.07/np.sqrt(np.mean(x[w]**2)); y *= min(1, .9/np.abs(y).max()); k += 1
            save(f'{OUT}/{k:02d}_{s}_{n}.wav', y, 48000, peak=np.abs(y).max())
            print(k, s, n, f'{t:.1f} s'); buf += [y, gap]; t += len(y)/48000 + .5
    z = np.concatenate(buf); save(f'{OUT}/試聴_やさしい・少年.wav', z, 48000, peak=np.abs(z).max())
