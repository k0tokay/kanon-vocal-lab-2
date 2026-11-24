import subprocess, sys, itertools, re
from concurrent.futures import ThreadPoolExecutor
def probe(conds, spk, vowel='a', model='bcg', prefix=None):
    def one(chunk):
        return subprocess.run(['./build/glottis_probe', spk, vowel, model], input='\n'.join(chunk)+'\n', capture_output=True, text=True).stdout.strip().split('\n')
    n=8; parts=[conds[i::n] for i in range(n)]; parts=[p for p in parts if p]
    with ThreadPoolExecutor(n) as ex: res=list(ex.map(one, parts))
    out=[None]*len(conds)
    for i,r in enumerate(res):
        for j,l in enumerate(r): out[i+j*n]=l.split(' : ')[1] if ' : ' in l else l.split(' :')[1]
    return out
def val(s,k):
    m=re.search(r'\b'+k+r' (-?[\d.]+|nan)',s); return float(m.group(1)) if m else float('nan')
MALE='0=1.6 1=.3 2=.2 3=.2 4=.4'
FEM='0=1.0 1=.2 2=.15 3=.15 4=.3'
if __name__=='__main__':
    size={'male':MALE,'fem':FEM,'kan':'0=0.8 1=.2 2=.13 3=.13 4=.26'}[sys.argv[1]]
    spk='../../speakers/JD2.speaker' if sys.argv[1]=='male' else '../../speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-0.speaker'
    P=sys.argv[2]; add=sys.argv[3]; extra=sys.argv[4] if len(sys.argv)>4 else ''; keys=(sys.argv[5] if len(sys.argv)>5 else 'F0,CQ,H1H2').split(',')
    cts=[0,.1,.2,.3,.4,.5,.6,.8,1]; tas=[0,.1,.2,.3,.4,.6,.8,1]
    cs=[f'0.4 200 {P} {add} {add} 0 {c} {t} 0 | {size} {extra}' for c in cts for t in tas]
    r=probe(cs,spk)
    for k in keys:
        print(k,'rows CT, cols TA',tas)
        for i,c in enumerate(cts): print(f'{c:4}',' '.join((f'{val(r[i*len(tas)+j],k):7.2f}' if 'F0' in r[i*len(tas)+j] and 'r ' in r[i*len(tas)+j] else ('   DIV ' if 'DIV' in r[i*len(tas)+j] else '    -  ')) for j in range(len(tas))))
