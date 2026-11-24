"""v1.1.3 -> v1.1.4: the adducted glottis of b d g vibrates with less amplitude.

In v1.1.3 voiced-plosive is 5-8 dB louder than the leaky modal voice, and the glottis is still there
while the mouth is open (70 ms before the closure to about 40 ms after the release), so the vowels
next to b d g stuck out. The adduction is needed (it keeps the voice going in the closure), so the
relative amplitude changes, 1 -> 0.4; slightly tighter folds keep the burst above 2 kHz. The numbers
depend on how loud modal is: choose them again (stop_scan.py) if modal or the glottis model changes.
"""
from build import *
from build113 import V113

V114 = ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-4.speaker"
VOICED_PLOSIVE = dict(x_bottom=.018, x_top=.03, rel_amp=.4)       # v1.1.3: .025, .055, 1

if __name__ == "__main__":
    edit_glottis(V113, "voiced-plosive", VOICED_PLOSIVE, V114)
