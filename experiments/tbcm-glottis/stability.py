"""Stability and F0 control over vowels, pressures, adduction and TA (1440 conditions)."""
from map import *
K='../../speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-0.speaker'
for v in 'aiueoM':
    cs=[f'.6 {f} {P} {a} {b} 0 .2 {t} 25 | {FEM}' for f in (150,250,400,600,800) for P in (3000,6000,10000,16000) for a,b in((.4,.4),(.57,.4),(.8,.8)) for t in (.05,.17,.4,.8)]
    r=probe(cs,K,v); err=[abs(val(x,'F0')/float(c.split()[1])-1) for c,x in zip(cs,r) if 'F0' in x]
    print(v,len(r),'DIV',sum('DIV' in x for x in r),'no voice',sum('NOV' in x for x in r),'F0 err>2%',sum(e>.02 for e in err),'of',len(err))
