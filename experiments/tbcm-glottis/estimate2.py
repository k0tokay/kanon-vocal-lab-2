"""Second estimate: harmonic 5 included (a zero of the glottal flow can make its dip), PCA free, formants 1-5 free,
starts from a random scan. python3 estimate2.py  (needs build/est/target.json of estimate.py)"""
import json, re, sys, numpy as np, natural as N, estimate as E
from map import val
from scipy.optimize import least_squares
import os; TG = os.environ.get('TARGET', 'target'); T = json.load(open(f'build/est/{TG}.json')); K = E.K; FR = T['f0']*np.arange(1, K+1); R = np.array(T['R']); NO = 10**(np.array(T['noise'])/10)
NZ = '--notch' in sys.argv      # zero of the recording side near 1010 Hz (nasal branch or room) and a first-order high pass of the microphone
QP = np.r_[[690, 1210, 2950, 3700, 4200], np.log([80, 80, 130, 200, 200])]; QS = np.r_[[80, 80, 200, 150, 100], [.4]*5]
if NZ: QP = np.r_[QP, 1010, np.log(60), np.log(160), np.log(60)]; QS = np.r_[QS, 20, .7, .5, .8]
M = len(QP)
REST = [(f, 350) for f in range(5200, 20000, 1000)]
SIG = np.r_[[1, 1, 1, 1, 3, 2.5, 3, 3, 4], [5]*13]
def tract(f, q):
    y = sum(E.pole(f, q[i], np.exp(q[5+i])) for i in range(5)) + sum(E.pole(f, *p) for p in REST)
    if NZ: y = y - E.pole(f, q[10], np.exp(q[11])) + E.pole(f, q[10], np.exp(q[12])) - 10*np.log10(1 + (np.exp(q[13])/f)**2)
    return y
def inner(dU):
    dU = np.array(dU[:K])
    def pred(p): return 10*np.log10(10**((dU + tract(FR, QP + QS*p[:M]) + p[M])/10) + NO)
    def res(p):
        e = (pred(p) - R)/SIG; return np.r_[np.sign(e)*np.sqrt(2*(np.sqrt(1 + e*e) - 1)), p[:M]]
    best = None
    for f3 in (0,):
        p0 = np.zeros(M + 1); p0[2] = f3; p0[M] = np.mean((R - dU - tract(FR, QP + QS*p0[:M]))[:4]); s = least_squares(res, p0, method='trf', max_nfev=60)
        if best is None or s.cost < best[0]: best = (s.cost, s.x)
        if f3 == 0 and s.cost > 40: break
    p = best[1]; return 2*best[0], QP + QS*p[:M], p[M], pred(p)
NAMES = ['LCA', 'IA', 'PCA', 'CT', 'TA', 'pressure', 'rest_length', 'rest_thickness', 'mucosa_depth', 'ligament_depth', 'muscle_depth', 'cover_shear', 'body_shear', 'convergence', 'posterior_scale']
I = np.array([N.NAMES.index(n) for n in NAMES]); SD = np.array([{'LCA': .25, 'IA': .25, 'PCA': .08, 'CT': .25, 'TA': .25, 'pressure': .3, 'convergence': .3, 'rest_length': .25, 'rest_thickness': .25}.get(n, .15) for n in NAMES])
C0 = N.Z0.copy(); C0[N.NAMES.index('LCA')] = .5; C0[N.NAMES.index('IA')] = .5; C0[N.NAMES.index('CT')] = .2; C0[N.NAMES.index('TA')] = .25
def z(u): v = C0.copy(); v[I] += SD*u; return v
def cost(U, f0s=.004, dur=.45):
    zs = [z(u) for u in U]; out = []
    for v, u, r in zip(zs, U, N.batch(zs, dur=dur)):
        dU = E.parse(r); over = np.sum((np.maximum(0, N.LO - v) + np.maximum(0, v - N.HI))**2)*1e3 + 1e3*max(0, -v[N.NAMES.index('PCA')])**2
        if dU is None: out.append((1e3 + u@u + over, None, r)); continue
        c, q, g, p = inner(dU); f0 = val(r, 'F0'); ac = val(r, 'Umax') - val(r, 'Umin'); per = float(re.search(r' r ([\d.]+)', r).group(1))
        out.append((c + (np.log(f0/T['f0'])/f0s)**2 + u@u + over + 200*max(0, .97 - per) + (np.log(max(ac, 1)/E.FLOW[0])/E.FLOW[1])**2, dict(q=q.tolist(), g=g, p=p.tolist(), f0=f0, c=c), r))
    return out
class P:
    names = NAMES
    def cost(s, U): return cost(U)
if __name__ == '__main__':
    rng = np.random.default_rng(int(sys.argv[1])); U = []
    for _ in range(1000):
        u = rng.normal(0, 1.1, len(NAMES)); u[NAMES.index('PCA')] = abs(u[NAMES.index('PCA')]); U.append(u)
    res = []
    for k in range(0, len(U), 300): res += cost(U[k:k+300], f0s=.06)
    o = np.argsort([r[0] for r in res]); print('scan best', [round(res[i][0], 1) for i in o[:8]], flush=True); picks = []
    for i in o:
        if res[i][1] is None: continue
        if all(np.linalg.norm(U[i] - U[j]) > 1.2 for j in picks): picks.append(i)
        if len(picks) == 3: break
    sols = []
    for k, i in enumerate(picks):
        class Q(P):
            u0 = U[i]
            def cost(s, V): return cost([s.u0 + v for v in V])
        b, _ = E.cma(Q(), 120, 10 + k, pop=18, s0=.2, m0=np.zeros(len(NAMES))); x = N.dec(z(Q.u0 + b[1])); sols.append((b, x))
        print(f'start {res[i][0]:.1f} -> cost {b[0]:.2f} spectrum {b[2]["c"]:.2f} ' + ' '.join(f'{n}={x[N.NAMES.index(n)]:.3g}' for n in NAMES) + ' |' + re.sub(r' dU.*? P [-\d. ]+', ' ', b[3]), flush=True); print('   tract', np.round(b[2]['q'][:5]), np.round(np.exp(b[2]['q'][5:10])), (np.round(b[2]['q'][10]), np.round(np.exp(b[2]['q'][11:]))) if NZ else ''); print('   fit', np.round(b[2]['p'][:14], 1)); print('   rec', np.round(R[:14], 1), flush=True)
    sols.sort(key=lambda t: t[0][0]); json.dump([dict(cost=s[0][0], par=dict(zip(N.NAMES, s[1].tolist())), **s[0][2], probe=s[0][3]) for s in sols], open('build/est/' + (TG + '_' if TG != 'target' else '') + ('D' if NZ else 'C') + '.json', 'w'), indent=1)
