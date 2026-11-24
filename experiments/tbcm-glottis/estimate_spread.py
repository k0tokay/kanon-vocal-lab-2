"""Local uncertainty of the estimate: Jacobian (vtlmap) of the misfit with respect to the muscles and the pressure.
python3 estimate_spread.py"""
import json, re, numpy as np, natural as N, estimate as E
from natural import vm, val
from scipy.optimize import least_squares
T = json.load(open('build/est/target.json')); s = json.load(open('build/est/A.json'))[0]; P = E.Problem(T, E.MUS)
u0 = (N.enc([s['par'][n] for n in N.NAMES])[P.i] - P.z0[P.i])/P.sd
def feat(r):
    dU = E.parse(r)
    if dU is None: raise vm.Invalid('no voice')
    c, q, g, p = E.inner(T, dU, T['f0']); R = np.array(T['R']); w = (p - R)[:9]/E.SIG
    return np.r_[w, np.log(val(r, 'F0')/T['f0'])/.004, np.log((val(r, 'Umax') - val(r, 'Umin'))/E.FLOW[0])/E.FLOW[1], (q - E.QP)/E.QS]
h = np.array([.1, .1, .1, .1, .15]); pts = [u0] + [u0 + k*h[j]*np.eye(5)[j] for j in range(5) for k in (1, -1)]
tab = {p.tobytes(): r for p, r in zip(pts, N.batch([P.z(p) for p in pts], dur=.5))}
J, y = vm.jacobian(lambda u: feat(tab[u.tobytes()]), u0, h)
for prior in (1, 0):
    C = np.linalg.inv(J.T@J + prior*np.eye(5) + 1e-6*np.eye(5)); sd = np.sqrt(np.diag(C))*P.sd
    print('with prior' if prior else 'data only', ' '.join(f'{n} sd {v:.3f}' for n, v in zip(E.MUS, sd)), '(pressure: relative)')
w, V = np.linalg.eigh(J.T@J)
for k in range(5): print('curvature %.2f' % w[k], ' '.join(f'{n} {v:+.3f}' for n, v in zip(E.MUS, V[:, k]*P.sd)))
print('probe', re.sub(r' dU.*? P [-\d. ]+', ' ', s['probe'].split(' : ')[-1]))
