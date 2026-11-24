"""Vary the modal shape, static parameters, F0 and larynx height and print the features for two sentences."""
import os, re, sys, json, subprocess, concurrent.futures as cf, numpy as np
import make_speaker as ms
G = '../../speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-0.speaker'
TTS = '../japanese-accent/results/%s.seg'
os.makedirs('build/ex', exist_ok=True)


def transform_seg(src, dst, shift_st=0.0, rng=1.0, rate=1.0):
    """Shift the F0 of a seg file, scale its range (in semitones around the median) and its durations."""
    t = open(src).read(); f = [float(v) for v in re.findall(r'Hz = ([\d.]+)', t)]; f = [v for v in f if v > 0]
    med = np.median(np.log2(f))
    def sub(m):
        v = float(m.group(1))
        return 'Hz = %.2f' % (0 if v == 0 else 2**(med + shift_st/12 + rng*(np.log2(v) - med)))
    t = re.sub(r'Hz = ([\d.]+)', sub, t)
    t = re.sub(r'duration_s = ([\d.]+)', lambda m: 'duration_s = %.6f' % (float(m.group(1))/rate), t)
    open(dst, 'w').write(t)


def make(path, modal=None, static=None, hy=0.0, source=G, shapes=None):
    """modal: (LCA, IA, PCA, CT, TA, flutter). hy: cm added to the larynx height of all tract shapes."""
    sh = dict(ms.SHAPES)
    if modal: sh['modal'] = sh['default'] = modal
    if shapes: sh.update(shapes)
    ms.convert(source, path, static=static, shapes=sh)
    if hy:
        t = open(path, newline='').read(); i = t.index('<glottis_models>')
        lo, hi = (float(v) for v in re.search(r'name="HY"\s+min="([^"]+)"\s+max="([^"]+)"', t).groups())
        head = re.sub(r'(<param name="HY" value=")([^"]+)', lambda m: m.group(1) + '%.4f' % min(hi, max(lo, float(m.group(2)) + hy)), t[:i])
        open(path, 'w', newline='').write(head + t[i:])


def run(job):
    """job: name, seg transform (shift, range, rate), speaker keywords"""
    name, tr, kw = job; kw = dict(kw); p = kw.pop('pressure', 1.0); ad = kw.pop('advance', 0.0); spk = f'build/ex/{name}.speaker'
    if kw.get('geo'): spk = G
    else: make(spk, **kw)
    r = {}
    for s in ('ame', 'tenki'):
        seg = f'build/ex/{name}_{s}.seg'; transform_seg(TTS % s, seg, *tr)
        out = subprocess.run([sys.executable, '-c', f'''
import json
from synth import *; from features import features
fs,x=synth("{seg}","{spk}","build/ex/{name}_{s}",pressure={p},advance={ad}); np.save("build/ex/{name}_{s}.npy",x)
print("JSON"+json.dumps({{k:float(v) for k,v in features(x,fs,"{seg}").items()}}))'''], capture_output=True, text=True)
        js = [l for l in out.stdout.split('\n') if l.startswith('JSON')]
        if not js: return name, out.stderr[-300:]
        r[s] = json.loads(js[0][4:])
    return name, {k: np.mean([r[s][k] for s in r]) for k in r['ame']}


def table(jobs, workers=8):
    res = []
    print(f'{"":26} F0   F0sd centr tilt  H1H3 power aper voiced')
    with cf.ThreadPoolExecutor(workers) as ex:
        for n, r in ex.map(run, jobs):
            res.append((n, r))
            if isinstance(r, str): print(n, r); continue
            print(f'{n:26} {r["F0"]:4.0f} {r["F0sd"]:5.1f} {r["centroid"]:5.0f} {r["tilt"]:5.1f} {r["H1H3"]:5.1f} {r["power"]:6.1f} {r["aper"]:.2f} {r["voiced"]:.2f}', flush=True)
    return res
