"""Listening set: results/*.wav, joined in results/試聴.wav (0.5 s silence between items)."""
import os, numpy as np
from glide import hold, O, GEO
from synth import synth, save, f0_track
from speech import report
os.makedirs('results', exist_ok=True); items=[]
A=(.57,.40,0,.2)
def rms(x,r=.07):
    w=np.abs(x)>.05*np.abs(x).max(); y=x*r/np.sqrt(np.mean(x[w]**2)); return y*min(1,.9/np.abs(y).max())
def add(name,x,fs): items.append((name,rms(x),fs))
def tb(v,pts,dur,name): fs,x=hold(O,v,pts,dur); add(name,x,fs); f=f0_track(x,fs); print(name,'voiced %.2f'%(f>0).mean(),'F0',f[f>0].min().round(),f[f>0].max().round())
def ramp(pts):   # on/offset of the pressure
    t0,t1=pts[0][0],pts[-1][0]; first=list(pts[0][1]); last=list(pts[-1][1]); f0=list(first); f0[1]=0; l0=list(last); l0[1]=0
    return [(0,f0),(.06,first)]+[(t+.06,p) for t,p in pts[1:]]+[(t1+.14,l0)], t1+.25
def P(f,p=8000,ta=.17,a=A): return [f,p,*a,ta,25]
for seg in ('tenki','ame'):
    for n,s in (('v1.1.0',GEO),('TBCM',O)):
        fs,x=synth(f'../japanese-accent/results/{seg}.seg',s,f'build/{seg}'); add(f'文_{seg}_{n}',x,fs)
import ctypes
def geo(v,f,dur):
    g=[203.187335,8000,.08125,.1432,.008,.948733,1.0,.5,25]; a=list(g); a[0]=f; z=list(a); z[1]=0
    return hold(GEO,v,[(0,z),(.06,a),(dur-.1,a),(dur,z)],dur+.1)
fs,x=geo('a',262,1.3); add('母音_262Hz_v1.1.0',x,fs)
p,d=ramp([(0,P(262)),(1.2,P(262))]); tb('a',p,d,'母音_262Hz_TBCM_modal')
p,d=ramp([(0,P(330,8000,.06,(.57,.4,0,.2))),(.8,P(330,8000,.06)),(2.8,P(330,8000,.4)),(3.4,P(330,8000,.4))]); tb('a',p,d,'TA_裏声から地声へ_330Hz')
p,d=ramp([(0,P(262,8000,.17,(.46,.35,0,.2))),(.5,P(262,8000,.17,(.46,.35,0,.2))),(2.5,P(262,8000,.2,(.85,.85,0,.2))),(3.0,P(262,8000,.2,(.85,.85,0,.2)))]); tb('a',p,d,'内転_息混じりから強い閉鎖へ_262Hz')
p,d=ramp([(0,P(220)),(.3,P(220)),(3.3,P(620,10000)),(3.8,P(620,10000))]); tb('a',p,d,'グライド_220-620Hz_modal')
p,d=ramp([(0,P(220,9000,.40,(.62,.5,0,.2))),(.3,P(220,9000,.40,(.62,.5,0,.2))),(3.3,P(620,10000,.12)),(3.8,P(620,10000,.12))]); tb('a',p,d,'グライド_220-620Hz_TAを減らす')
p,d=ramp([(0,P(330,5000)),(.3,P(330,5000)),(2.3,P(330,14000)),(2.6,P(330,14000))]); tb('a',p,d,'声門下圧_500-1400Pa_330Hz')
gap=np.zeros(24000); buf=[]; t=0
for k,(n,x,fs) in enumerate(items,1):
    save(f'results/{k:02d}_{n}.wav',x,fs,peak=np.abs(x).max()); print(k,n,'%.1f s at %.1f'%(len(x)/fs,t)); buf+= [x,gap]; t+=len(x)/fs+.5
y=np.concatenate(buf); save('results/試聴.wav',y,fs,peak=np.abs(y).max())
