"""Third estimate: Kanon's tract kept as it is (no recording-side tract). The harmonics of the radiated sound are compared with the recording.

    TARGET=full2 python3 estimate3.py seed harm|band

harm: levels of the single harmonics (Kanon's formants are then errors the glottis cannot remove; robust loss).
band: h1, h2 alone and the energies of wider bands, so that the formants may sit elsewhere within a band."""
import json, re, os, sys, numpy as np, natural as N, estimate as E, estimate2 as E2
from map import val
T, TG, R, NO = E2.T, E2.TG, E2.R, E2.NO; K = E2.K; NAMES = E2.NAMES
SIG = np.r_[[1, 1, 1, 1, 3, 2.5, 3, 3, 4], [5]*13]
if TG in ('target', 'full1'): SIG[4] = 1e3          # the deep dip of the recording at h5
BANDS = [(0, 1), (1, 2), (2, 4), (4, 8), (8, 13), (13, 20), (20, 22)]; BSIG = np.array([1, 1, 1.5, 1.5, 3, 3, 4.])
soft = lambda e: 2*(np.sqrt(1 + e*e) - 1)
def radiated(r):
    m = re.search(r' P ([-\d. ]+)', r); return np.array(m.group(1).split(), float)[:K]
bands = lambda L: np.array([10*np.log10(np.sum(10**(L[a:b]/10))) for a, b in BANDS])
def misfit(P, mode):
    """Cost and fitted levels; the gain is the only free parameter."""
    best = None
    for g in np.arange(-20, 20.01, .25) + (np.mean(R[:4] - P[:4])):
        L = 10*np.log10(10**((P + g)/10) + NO)
        if mode == 'harm': c = np.sum(soft((L - R)/SIG)[:9]) + soft(np.mean((L - R)[9:13])/3) + soft(np.mean((L - R)[13:18])/4) + soft(np.mean((L - R)[18:22])/5)
        else: c = np.sum(soft((bands(L) - bands(R))/BSIG))
        if best is None or c < best[0]: best = (c, g, L)
    return best
def cost(U, mode, f0s=.004, dur=.45):
    zs = [E2.z(u) for u in U]; out = []
    for v, u, r in zip(zs, U, N.batch(zs, dur=dur)):
        over = np.sum((np.maximum(0, N.LO - v) + np.maximum(0, v - N.HI))**2)*1e3 + 1e3*max(0, -v[N.NAMES.index('PCA')])**2
        if E.parse(r) is None: out.append((1e3 + u@u + over, None, r)); continue
        c, g, L = misfit(radiated(r), mode); f0 = val(r, 'F0'); ac = val(r, 'Umax') - val(r, 'Umin'); per = float(re.search(r' r ([\d.]+)', r).group(1))
        out.append((c + (np.log(f0/T['f0'])/f0s)**2 + u@u + over + 200*max(0, .97 - per) + (np.log(max(ac, 1)/E.FLOW[0])/E.FLOW[1])**2, dict(g=g, p=L.tolist(), f0=f0, c=c), r))
    return out
if __name__ == '__main__':
    mode = sys.argv[2]; rng = np.random.default_rng(int(sys.argv[1])); U = []
    for _ in range(1000):
        u = rng.normal(0, 1.1, len(NAMES)); u[NAMES.index('PCA')] = abs(u[NAMES.index('PCA')]); U.append(u)
    res = []
    for k in range(0, len(U), 300): res += cost(U[k:k+300], mode, f0s=.06)
    o = np.argsort([r[0] for r in res]); picks = []
    for i in o:
        if res[i][1] is not None and all(np.linalg.norm(U[i] - U[j]) > 1.2 for j in picks): picks.append(i)
        if len(picks) == 3: break
    sols = []
    for k, i in enumerate(picks):
        class Q:
            names = NAMES; u0 = U[i]
            def cost(s, V): return cost([s.u0 + v for v in V], mode)
        b, _ = E.cma(Q(), 120, 10 + k, pop=18, s0=.2, m0=np.zeros(len(NAMES))); x = N.dec(E2.z(Q.u0 + b[1])); sols.append((b, x))
        print(f'start {res[i][0]:.1f} -> cost {b[0]:.2f} fit {b[2]["c"]:.2f} ' + ' '.join(f'{n}={x[N.NAMES.index(n)]:.3g}' for n in NAMES) + ' |' + re.sub(r' dU.*? P [-\d. ]+', ' ', b[3]), flush=True); print('   fit', np.round(b[2]['p'][:14], 1)); print('   rec', np.round(R[:14], 1), flush=True)
    sols.sort(key=lambda t: t[0][0]); json.dump([dict(cost=s[0][0], par=dict(zip(N.NAMES, s[1].tolist())), **s[0][2], probe=s[0][3]) for s in sols], open(f'build/est/{TG}_K{mode}.json', 'w'), indent=1)
