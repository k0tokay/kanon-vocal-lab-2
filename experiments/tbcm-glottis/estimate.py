"""Estimate the body-cover glottis (F0 control off) from a recorded steady /a/.

    python3 estimate.py recording.wav [test]     (mono, any rate; results in build/est, not committed)

The vocal tract of the recording is not that of the speaker file, so the levels of the glottal flow
harmonics (synthesized with Kanon's tract) are multiplied with an all-pole tract whose first formants
are fitted at the same time. The search (CMA-ES) is over the muscles and the pressure alone, or with the
static parameters, with a prior around Kanon's values. 'test' recovers known parameters instead."""
import sys, os, json, re, numpy as np
from scipy.io import wavfile
from scipy.optimize import least_squares
import natural as N
from map import val
OUT = 'build/est'; K = 22
# ------------------------------------------------------------------ measurement of the recording
def measure(path, t0=.5, t1=8.0, hop=.05, guess=None):
    fs, x = wavfile.read(path); x = x.astype(float)/(np.iinfo(x.dtype).max if x.dtype.kind == 'i' else 1)
    if x.ndim > 1: x = x.mean(1)
    if guess is None:
        s = x[len(x)//2:len(x)//2 + fs//5]; n = fs//10; a = s - s.mean()
        r = [np.dot(a[:n], a[l:l+n])/np.sqrt(np.dot(a[:n], a[:n])*np.dot(a[l:l+n], a[l:l+n])) for l in range(fs//500, fs//70)]
        r = np.array(r); k = next(i for i in range(1, len(r)-1) if r[i] > .93*r.max() and r[i] >= r[i-1] and r[i] >= r[i+1]); guess = fs/(k + fs//500)
    L = int(2.5*fs/guess); n = np.arange(-L, L)/fs; w = np.hanning(2*L); F, D, Nn = [], [], []
    def basis(f, ks): A = np.exp(2j*np.pi*f*np.outer(n, ks)); return np.c_[A.real, A.imag]*w[:, None]
    for c in range(int(t0*fs), min(int(t1*fs), len(x)-L), int(hop*fs)):
        s = x[c-L:c+L]*w; ks = np.arange(1, K+1)
        def err(f): M = basis(f, ks); return np.sum((s - M@np.linalg.lstsq(M, s, rcond=None)[0])**2)
        g = np.linspace(guess*.985, guess*1.015, 31); f = g[np.argmin([err(v) for v in g])]
        g = np.linspace(f*.999, f*1.001, 11); f = g[np.argmin([err(v) for v in g])]
        M = basis(f, ks); co = np.linalg.lstsq(M, s, rcond=None)[0]; res = s - M@co
        H = basis(f, ks + .5); ch = np.linalg.lstsq(H, res, rcond=None)[0]
        F.append(f); D.append(np.hypot(co[:K], co[K:])); Nn.append(np.hypot(ch[:K], ch[K:]))
    D = 20*np.log10(np.array(D)); Nn = 20*np.log10(np.array(Nn)); d = np.median(D, 0); no = np.median(Nn, 0)
    no = np.r_[no[0], .5*(no[1:] + no[:-1])]; ref = d[:6].max()
    return dict(f0=float(np.median(F)), f0sd=float(np.std(F)), R=(d - ref).tolist(), noise=(no - ref).tolist(), iqr=np.subtract(*np.percentile(D, [75, 25], 0)).tolist())
# ------------------------------------------------------------------ all-pole tract of the recording
POLES = [(3500, 200), (4150, 250)] + [(f, 350) for f in range(5200, 20000, 1000)]
def pole(f, F, B): return -10*np.log10((1 - (f/F)**2)**2 + (f*B/F**2)**2)
def tract(f, q): return pole(f, q[0], np.exp(q[3])) + pole(f, q[1], np.exp(q[4])) + pole(f, q[2], 120.) + sum(pole(f, *p) for p in POLES)
FLOW = (220., .35)     # prior of the peak-to-peak glottal flow (cm^3/s) and its sd (log): the recording has no absolute level
SIG = np.array([1, 1, 1, 1, 1e3, 2.5, 3, 3, 4])     # h5 (1010 Hz) is ignored: 25 dB below its neighbours in the recording, no all-pole tract does that
QP = np.array([690, 1210, 2600, np.log(80), np.log(80)]); QS = np.array([80, 80, 250, .35, .35])
def inner(T, dU, f0):
    """Best tract for the flow harmonics dU (dB); returns (cost, q, gain, fitted levels)."""
    f = f0*np.arange(1, K+1); R = np.array(T['R']); no = 10**(np.array(T['noise'])/10); dU = np.array(dU[:K])
    def pred(p): return 10*np.log10(10**((dU + tract(f, QP + QS*p[:5]) + p[5])/10) + no)
    def res(p):
        e = (pred(p) - R); soft = lambda r: np.sign(r)*np.sqrt(2*(np.sqrt(1 + r*r) - 1))
        return np.r_[soft(e[:9]/SIG), np.mean(e[13:22])/6, p[:5]]
    p0 = np.r_[np.zeros(5), np.mean((R - dU - tract(f, QP))[:4])]; s = least_squares(res, p0, method='lm', max_nfev=200)
    return 2*s.cost, QP + QS*s.x[:5], s.x[5], pred(s.x)
def parse(r):
    m = re.search(r' dU ([-\d. ]+?) P ', r); return np.array(m.group(1).split(), float) if m else None
os.environ['PROBE_HARM'] = '1'
MUS = ['LCA', 'IA', 'CT', 'TA', 'pressure']
STA = ['rest_length', 'rest_thickness', 'mucosa_depth', 'ligament_depth', 'muscle_depth', 'cover_shear', 'body_shear', 'convergence', 'posterior_scale']
PRIOR = {'LCA': .25, 'IA': .25, 'CT': .25, 'TA': .25, 'pressure': .30, 'convergence': .3}      # sd; static ones .15 (log)
CENTER = {'LCA': .55, 'IA': .45, 'CT': .2, 'TA': .2}
class Problem:
    def __init__(s, T, names, hold=None):
        s.T, s.names = T, names; s.i = np.array([N.NAMES.index(n) for n in names]); s.z0 = N.Z0.copy()
        for n, v in {**CENTER, **(hold or {})}.items(): s.z0[N.NAMES.index(n)] = v
        s.z0[N.NAMES.index('PCA')] = 0; s.sd = np.array([PRIOR.get(n, .15) for n in names])
    def z(s, u): z = s.z0.copy(); z[s.i] += s.sd*u; return z
    def cost(s, U):
        zs = [s.z(u) for u in U]; rs = N.batch(zs, dur=.4); out = []
        for z, u, r in zip(zs, U, rs):
            dU = parse(r); over = np.sum((np.maximum(0, N.LO - z) + np.maximum(0, z - N.HI))**2)*1e3
            if dU is None: out.append((1e3 + u@u + over, None, r)); continue
            f0 = val(r, 'F0'); c, q, g, p = inner(s.T, dU, s.T['f0'])
            ac = val(r, 'Umax') - val(r, 'Umin'); per = float(re.search(r' r ([\d.]+)', r).group(1))     # AC flow, periodicity
            out.append((c + (np.log(f0/s.T['f0'])/.004)**2 + u@u + over + 200*max(0, .97 - per) + (np.log(max(ac, 1)/FLOW[0])/FLOW[1])**2, dict(q=q.tolist(), g=g, p=p.tolist(), f0=f0, c=c), r))
        return out
def cma(P, gens, seed, pop=20, s0=.5, m0=None):
    rng = np.random.default_rng(seed); n = len(P.names); m = rng.normal(0, .7, n) if m0 is None else m0.copy(); sg = s0; C = np.eye(n); pc = np.zeros(n); ps = np.zeros(n)
    mu = pop//2; w = np.log(mu + .5) - np.log(np.arange(1, mu+1)); w /= w.sum(); me = 1/np.sum(w**2)
    cc = (4 + me/n)/(n + 4 + 2*me/n); cs = (me + 2)/(n + me + 5); c1 = 2/((n + 1.3)**2 + me); cm = min(1 - c1, 2*(me - 2 + 1/me)/((n + 2)**2 + me))
    ds = 1 + 2*max(0, np.sqrt((me - 1)/(n + 1)) - 1) + cs; chi = np.sqrt(n)*(1 - 1/(4*n) + 1/(21*n*n)); best = (1e9,); arch = []
    for g in range(gens):
        d, B = np.linalg.eigh(C); d = np.sqrt(np.maximum(d, 1e-14)); Y = rng.normal(size=(pop, n))*d@B.T; X = m + sg*Y; res = P.cost(X); c = np.array([r[0] for r in res]); o = np.argsort(c)
        for k in range(pop): arch.append((c[k], X[k].copy()))
        if c[o[0]] < best[0]: best = (c[o[0]], X[o[0]].copy(), res[o[0]][1], res[o[0]][2])
        yw = w@Y[o[:mu]]; m = m + sg*yw; ps = (1 - cs)*ps + np.sqrt(cs*(2 - cs)*me)*(B@((B.T@yw)/d))
        h = np.linalg.norm(ps)/np.sqrt(1 - (1 - cs)**(2*(g+1))) < (1.4 + 2/(n+1))*chi; pc = (1 - cc)*pc + h*np.sqrt(cc*(2 - cc)*me)*yw
        C = (1 - c1 - cm)*C + c1*np.outer(pc, pc) + cm*(Y[o[:mu]].T*w)@Y[o[:mu]]; sg *= np.exp(cs/ds*(np.linalg.norm(ps)/chi - 1))
        if sg*d.max() < .01: break
    return best, arch
def solve(T, names, gens, seeds, hold=None):
    P = Problem(T, names, hold); sols = []
    for s in seeds:
        b, arch = cma(P, gens, s); x = N.dec(P.z(b[1])); sols.append((b, x))
        print(f'  seed {s} cost {b[0]:.2f} (spectrum {b[2]["c"] if b[2] else -1:.2f}) ' + ' '.join(f'{n}={x[N.NAMES.index(n)]:.3g}' for n in names) + ' |' + re.sub(r' dU.*? P [-\d. ]+', ' ', b[3]), flush=True)
    sols.sort(key=lambda t: t[0][0]); return P, sols
def dump(T, sols, name):
    b, x = sols[0]; f = T['f0']*np.arange(1, K+1); print('  tract F1 %.0f F2 %.0f F3 %.0f B1 %.0f B2 %.0f' % (*b[2]['q'][:3], np.exp(b[2]['q'][3]), np.exp(b[2]['q'][4])))
    print('  h  rec ', ' '.join(f'{v:6.1f}' for v in T['R'][:13])); print('  h  fit ', ' '.join(f'{v:6.1f}' for v in b[2]['p'][:13]))
    json.dump([dict(cost=s[0][0], par=dict(zip(N.NAMES, s[1].tolist())), **(s[0][2] or {}), probe=s[0][3]) for s in sols], open(f'{OUT}/{name}.json', 'w'), indent=1)
if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    if sys.argv[-1] == 'test':     # recovery of known parameters through another tract, with the noise floor of the recording
        T0 = json.load(open(f'{OUT}/target.json')); truth = [dict(LCA=.58, IA=.5, CT=.12, TA=.17, pressure=7000), dict(LCA=.53, IA=.42, CT=.2, TA=.2, pressure=9500, rest_length=1.15, rest_thickness=.23)]
        for k, tr in enumerate(truth):
            z = N.Z0.copy()
            for n, v in tr.items(): i = N.NAMES.index(n); z[i] = np.log(v) if N.LOG[i] else v
            r = N.batch([z])[0]; dU = parse(r); f0 = val(r, 'F0'); f = f0*np.arange(1, K+1); R = dU[:K] + tract(f, np.array([650, 1180, 2500, np.log(60), np.log(95)])); R -= R.max()
            R = 10*np.log10(10**(R/10) + 10**(np.array(T0['noise'])/10)) + np.random.default_rng(k).normal(0, .5, K)
            T = dict(f0=f0, R=R.tolist(), noise=T0['noise']); print('TRUTH', tr, re.sub(r' dU.*? P [-\d. ]+', '', r))
            for nm, names in (('A', MUS), ('B', MUS + STA)):
                print(' stage', nm); P, s = solve(T, names, 60 if nm == 'A' else 110, range(1)); dump(T, s, f'test{k}{nm}')
        sys.exit()
    T = measure(sys.argv[1]); json.dump(T, open(f'{OUT}/target.json', 'w')); print('F0 %.1f sd %.2f' % (T['f0'], T['f0sd'])); print(' R    ', np.round(T['R'], 1)); print(' noise', np.round(T['noise'], 1))
    for nm, names in (('A', MUS), ('B', MUS + STA)):
        print('stage', nm); P, s = solve(T, names, 80 if nm == 'A' else 160, range(5)); dump(T, s, nm)
