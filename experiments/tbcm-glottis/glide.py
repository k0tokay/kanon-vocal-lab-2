"""Sustained sounds with control trajectories through vtlSynthesisAddTract."""
from synth import *
def hold(speaker, vowel, points, dur, names=('f0','pressure','act_lca','act_ia','act_pca','act_ct','act_ta','flutter')):
    """points: list of (t, value per control parameter); linear interpolation."""
    assert lib.vtlInitialize(speaker.encode()) == 0
    c=[ct.c_int() for _ in range(4)]; lib.vtlGetConstants(*map(ct.byref,c)); fs=c[0].value; NT=c[2].value; NG=c[3].value
    sh=(ct.c_double*NT)(); assert lib.vtlGetTractParams(vowel.encode(), sh)==0
    step=48*2; n=int(dur*fs/step); t=np.arange(n)*step/fs
    T=np.array([p[0] for p in points]); V=np.array([p[1] for p in points],float)
    g=np.stack([np.interp(t,T,V[:,k]) for k in range(V.shape[1])],1); assert g.shape[1]==NG,(g.shape,NG)
    lib.vtlResetTractSynthesis(); out=[]; a=(ct.c_double*step)()
    for k in range(n):
        gp=(ct.c_double*NG)(*g[k])
        lib.vtlSynthesisAddTract(0 if k==0 else step, a, sh, gp)
        if k: out.append(np.array(a[:]))
    lib.vtlClose(); return fs, np.concatenate(out)
O='../../speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-0-tbcm.speaker'
GEO='../../speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-0.speaker'
if __name__=='__main__':
    M=(.57,.40,0,.2)
    def P(t,f,p=8000,ta=.17,a=M): return (t,[f,p,*a,ta,20])
    for ta in (.1,.17,.3):
        fs,x=hold(O,'a',[P(0,180,0,ta),P(.05,180,8000,ta),P(.4,180,8000,ta),P(3.4,620,10000,ta),P(3.8,620,10000,ta),P(3.9,620,0,ta)],4.0)
        f=f0_track(x,fs); tt=np.arange(len(f))*.005+.015; tgt=np.interp(tt,[0,.4,3.4,4],[180,180,620,620]); ok=f>0
        e=12*np.log2(f[ok]/tgt[ok]); print('TA',ta,'voiced %.2f'%ok[:740].mean(),'mean %.2f  |err| %.2f  max %.2f st'%(e.mean(),np.abs(e).mean(),np.abs(e).max()), [(round(tt[k],1),round(f[k])) for k in range(60,760,70)])
        save(f'build/glide_{ta}.wav',x,fs)
