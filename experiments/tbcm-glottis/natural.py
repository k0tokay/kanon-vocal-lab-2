"""Natural F0 of the body-cover glottis (F0 control off): Jacobian of the source measures with
respect to muscles, pressure and static parameters, and the direction that lowers F0 only.

    python3 natural.py [target_Hz]

Steady /a/ of Kanon, no aspiration. Uses experiments/vtlmap (jacobian, bounded_step)."""
import sys, numpy as np
sys.path.insert(0, '../vtlmap')
import vtlmap as vm
from map import probe, val
SPK = '../../speakers/fulkhisa-kanon/fulkhisa-kanon-v1-2-0.speaker'
# name, probe key (c = control, s = static index), baseline (v1.2.0), lower, upper, logarithmic, Jacobian step
PAR = [('LCA', 'c2', .51, 0, 1, 0, .02), ('IA', 'c3', .36, 0, 1, 0, .02), ('PCA', 'c4', 0, 0, 1, 0, .02), ('CT', 'c5', .115, 0, 1, 0, .02),
       ('TA', 'c6', .10, 0, 1, 0, .02), ('pressure', 'c1', 8000, 3000, 25000, 1, .05),
       ('rest_length', 's0', 1.0, .5, 1.8, 1, .05), ('rest_thickness', 's1', .2, .08, .5, 1, .05), ('mucosa_depth', 's2', .15, .05, .35, 1, .05),
       ('ligament_depth', 's3', .15, .05, .35, 1, .05), ('muscle_depth', 's4', .3, .1, .7, 1, .05), ('cover_shear', 's5', 3000, 800, 20000, 1, .05),
       ('body_shear', 's6', 6000, 1000, 40000, 1, .05), ('convergence', 's7', 0, 0, 2, 0, .1), ('posterior_scale', 's8', 1, .1, 2, 1, .05)]
NAMES = [p[0] for p in PAR]
LOG = np.array([p[5] for p in PAR], bool); H = np.array([p[6] for p in PAR])
def enc(x): x = np.array(x, float); x[LOG] = np.log(x[LOG]); return x
def dec(z): x = np.array(z, float); x[LOG] = np.exp(x[LOG]); return x
Z0, LO, HI = (enc([p[i] for p in PAR]) for i in (2, 3, 4))
def line(z, dur=.5, f0control=0, f0=203, extra='14=-60'):
    x = dec(np.clip(z, LO, HI)); c = [f0] + [0]*6 + [0]; s = []
    for v, p in zip(x, PAR):
        k = int(p[1][1:])
        if p[1][0] == 'c': c[k] = v
        else: s.append(f'{k}={v:.6g}')
    return f'{dur} ' + ' '.join(f'{v:.6g}' for v in c) + ' | ' + ' '.join(s) + f' 9=.5 10=.06 11=12 12={f0control} 13=.3 {extra}'
OBS = ['logF0', 'H1H2', 'H1H2k', 'CQ', 'lev']
def obs(r):
    if 'F0' not in r: raise vm.Invalid(r[:40])
    v = np.array([np.log(val(r, 'F0')*1.0)] + [val(r, k) for k in OBS[1:]]); return v
def batch(zs, **kw): return probe([line(z, **kw) for z in zs], SPK)
def f(z): return obs(batch([z])[0])
def jac(z):
    """vm.jacobian with the simulations of all columns done in parallel beforehand."""
    pts = [z] + [np.clip(z + s*H[j]*np.eye(len(z))[j], LO, HI) for j in range(len(z)) for s in (1, -1)]
    table = {np.clip(p, LO, HI).tobytes(): r for p, r in zip(pts, batch(pts))}
    return vm.jacobian(lambda q: obs(table[np.clip(q, LO, HI).tobytes()]), z, H, LO, HI)
if __name__ == '__main__':
    target = float(sys.argv[1]) if len(sys.argv) > 1 else 203.0
    J, y = jac(Z0); print('baseline', dict(zip(OBS, y.round(3))), 'F0 %.1f' % np.exp(y[0]))
    print('effect of +0.1 (muscles, convergence) or +10 % (pressure, static): F0 %, H1-H2 dB, H1-2k dB, CQ, level dB')
    u = np.where(LOG, np.log(1.1), .1)
    for j, n in enumerate(NAMES): print(f'{n:16}', ' '.join(f'{v:8.2f}' for v in np.r_[100*J[0, j]*u[j], J[1:, j]*u[j]]))
    np.save('build/ex/natural_J.npy', J)
    for label, free in (('muscles + pressure', range(6)), ('muscles + pressure + static', range(len(PAR)))):
        free = np.array(list(free)); W = np.ones(len(free)); z = Z0.copy()
        W = np.where(LOG[free], 1/.2, 1/.2)         # 20 % or .2 activation is one unit of change
        for mode in ('F0 only', 'F0, others fixed'):
            z = Z0.copy(); y0 = f(z)
            for it in range(8):
                J, y = jac(z)
                A = J[:, free]; b = np.r_[np.log(target) - y[0], y0[1:] - y[1:]]
                sc = np.array([1/.005, 1/1., 1/3., 1/.03, 1/2.])          # one unit of misfit
                if mode == 'F0 only': sc[1:] = 0
                d = vm.bounded_step(A*sc[:, None], b*sc, LO[free] - z[free], HI[free] - z[free], .5, W)
                d *= min(1, .15/np.abs(d).max())
                z[free] += d
                if abs(np.log(target) - f(z)[0]) < .003 and mode == 'F0 only': break
            y = f(z); print('\n', label, '/', mode, ' F0 %.1f' % np.exp(y[0]), dict(zip(OBS[1:], (y - y0)[1:].round(2))))
            print('  ', ' '.join(f'{n}={a:.3g}' for n, a, b0 in zip(NAMES, dec(z), dec(Z0)) if abs(a - b0) > 1e-3*max(1, abs(b0))))
