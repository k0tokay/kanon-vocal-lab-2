"""v1.1.1 -> v1.1.2: taps that leak at the sides, voiced fricatives with a narrower glottis.

Taps: TS3 (tongue sides at the tip) to TAP_TS3. Between -0.2 and -0.35 VTL gives the tip region a
lateral channel of 0 to 0.15 cm2, so the tap does not close completely (real taps rarely do).
Without it the area jumps from 0 to 0.15 cm2 within 2 % of the movement and cannot be controlled.

Voiced fricatives: x_bottom, x_top, chink, relative amplitude. v1.1.0/1 (.133, .133, .025, .594)
is as open as /h/; it doubles the flow after the release (breathy onset).
"""
from build import *

V112 = ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-2.speaker"
TAP_TS3 = -.28
VOICED_FRICATIVE = (.12, .13, .015, .8)

if __name__ == "__main__":
    tr = ctune.vm.Tract(NEW)
    for n in tr.shape_names():
        if n.startswith("tt-tap-"):
            x = tr.shape(n).copy()
            x[tr.index("TS3")] = TAP_TS3
            tr.set_shape(n, x)
    tr.write_speaker(V112, NEW)
    edit_glottis(V112, "voiced-fricative", dict(zip(INDEX, VOICED_FRICATIVE)), V112)
