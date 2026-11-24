import numpy as np
from map import *
K='../../speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-0.speaker'
# posture via probe output? use python port of rules with posture values from a helper
import subprocess
open('build/pm.cpp','w').write('''
#include "LaryngealPosture.h"
#include <cstdio>
int main(){double a[5];while(scanf("%lf %lf %lf %lf %lf",a,a+1,a+2,a+3,a+4)==5){LaryngealPosture q;q.settle(a);printf("%g %g %g %g\\n",q.getStrain(),q.getStress(LaryngealPosture::LIGAMENT),q.getStress(LaryngealPosture::MUCOSA),q.getStress(LaryngealPosture::TA));}}''')
subprocess.run('clang++ -O2 -I../../backend build/pm.cpp build/LaryngealPosture.o -o build/pm',shell=True,check=True)
def eig(ta,pm,size=(.01,.002,.0015,.0015,.003),muc=300,mub=600):
    e,sl,sm,st=pm; L0,T0,Dm,Dl,Dt=size
    L=L0*(1+e);T=T0/(1+.8*e);z=(1+ta)/3;Db=(ta*Dt+.5*Dl)/(1+.2*e);Dc=(Dm+.5*Dl)/(1+.2*e)
    sb=(.5*sl*Dl+st*Dt)/Db;sc=(.5*sl*Dl+sm*Dm)/Dc
    sh=2*muc*L*T/Dc; s=np.pi**2*sc*Dc*T/L
    k1=(sh+s)*z;k2=(sh+s)*(1-z);kb=2*mub*L*T/Db+np.pi**2*sb*Db*T/L
    kc=max(0,(.5*muc*L*Dc/T/(1/3-z*(1-z))-sh)*z*(1-z))
    m=np.array([1040*L*T*Dc*z,1040*L*T*Dc*(1-z),1040*L*T*Db])
    Kk=np.array([[k1+kc,-kc,-k1],[-kc,k2+kc,-k2],[-k1,-k2,k1+k2+kb]])
    w=np.linalg.eigvalsh(Kk/np.sqrt(np.outer(m,m)));return np.sqrt(abs(w))/2/np.pi, np.sqrt((k1+k2)/(m[0]+m[1]))/2/np.pi
g=[(c,t) for c in (0,.1,.2,.3,.5,.8) for t in (.05,.1,.2,.3,.5,.8)]
pm=subprocess.run('build/pm',input='\n'.join(f'.5 .5 0 {c} {t}' for c,t in g),capture_output=True,text=True).stdout.split('\n')
for P in (5000,8000,14000):
    r=probe([f'.4 200 {P} .5 .5 0 {c} {t} 0 | {FEM} 10=.06' for c,t in g],K)
    print(P)
    for (c,t),q,l in zip(g,pm,r):
        f,fc=eig(t,list(map(float,q.split())))
        F=val(l,'F0'); print(f'CT {c} TA {t} F0 {F:6.1f} eig {f.round(0)} cover {fc:5.0f} ratio {F/f[0]:.2f} {F/f[1]:.2f}')
