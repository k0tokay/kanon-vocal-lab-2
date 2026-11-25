"""For comparison: Kanon's shapes moved by VTL's own adaptation to the anatomy of a 15-year-old female (s = 0..1 on the way)."""
import sys
from scale import *
sys.path.insert(0, str(HERE.parent / "vtlmap"))
import vtlmap as vm
for s in (.5, 1.0):
    t = vm.Tract(BASE); th0 = t.anatomy()
    th = vm.restrict_anatomy(th0 + s * (vm.anatomy_from_age(180, False) - th0))
    sh = {n: t.shape(n) for n in t.shape_names()}
    t.set_anatomy(th)
    for n, x in sh.items():
        t.set_shape(n, vm.adapt(th, vm.unadapt(th0, x)))
    t.write_speaker(HERE / f"out/f15-{s:g}.speaker", BASE)
