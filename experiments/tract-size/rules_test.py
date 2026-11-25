"""compare.py with the absolute areas of the rules (velic openings, tap contact) scaled by k^2.

    rules_test.py <k> <label>=<speaker> [v] [c] [l]     v: velum of nasals, l: velic leak of b d g, c: tap contact area
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "consonant-articulation"))
import compare as C
k, spec, *w = sys.argv[1:]
k2 = float(k) ** 2
a = C.accent
if "v" in w:
    a.VELIC *= k2
if "l" in w:
    for s, v in (("b", .04), ("d", .04), ("g", .02)):
        a.TIMING[s] = {**a.TIMING.get(s, {}), "velic_cm2": v * k2}
if "c" in w:
    a.TIMING["4"] = {**a.TIMING["4"], "contact_cm2": .13 * k2}
C.main([spec])
