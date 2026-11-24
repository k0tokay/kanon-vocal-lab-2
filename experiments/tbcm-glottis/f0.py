from map import *
import sys
K='../../speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-0.speaker'
size=sys.argv[2] if len(sys.argv)>2 else FEM; add=sys.argv[1]
fs=[160,200,240,280,330,400,480,560]; tas=[.05,.1,.2,.3,.4,.6]; 
for P in (5000,8000,12000):
    r=probe([f'.8 {f} {P} {add} {add} 0 .2 {t} 0 | {size}' for f in fs for t in tas],K)
    print('P',P,'cells: F0err% / CQ / H1H2 ; cols TA',tas)
    for i,f in enumerate(fs):
        print(f,' | '.join((f"{100*(val(x,'F0')/f-1):5.1f} {val(x,'CQ'):.2f} {val(x,'H1H2'):5.1f}" if 'F0' in x else '   ('+('DIV' if 'DIV' in x else 'no')+')       ') for x in r[i*len(tas):(i+1)*len(tas)]))
