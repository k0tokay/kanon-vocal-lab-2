"""v1.1.2 -> v1.1.3: taps with a fronted tongue body, voiced fricatives with a wider glottis.

Taps: in v1.1.2 the tap shapes are the vowels with a raised tip, so F2 falls towards the contact
(a: 1520 -> 1330 Hz, like a retroflex). In JVS it goes to about 2000 Hz around every tap. The tongue
body (and the jaw) goes BLEND of the way to tt-tap-i; the tip and the lateral leak stay. The new
shape tt-tap-M serves taps after [M] (VTL had taken tt-alveolar-closure there).

Voiced fricatives: x_bottom, x_top, chink, relative amplitude. Opens more than in v1.1.2, so that
there is noise and little voice; the rules close it before the release (GesturalScore.cpp).
"""
import re
import sys

from build import *
from build112 import V112

V113 = ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-3.speaker"
BLEND = dict(a=.4, e=.35, o=.4, u=.3, M=.3)
BODY = ("TCX", "TCY", "TBX", "TBY", "JA")
VOICED_FRICATIVE = (.15, .15, .025, .6)


def tap_shapes(src, out, blend=BLEND):
    s = Path(src).read_text()
    if 'name="tt-tap-M"' not in s:
        b = re.search(r'[ \t]*<shape name="tt-tap-u">.*?</shape>\n', s, re.S)
        s = s[:b.end()] + b[0].replace("tt-tap-u", "tt-tap-M") + s[b.end():]
    Path(out).write_text(s)
    tr = ctune.vm.Tract(Path(out))
    ix = lambda n: int(np.ravel(tr.index(n))[0])
    m, u, tu = (tr.shape(n).copy() for n in ("M", "u", "tt-tap-u"))
    if Path(src) != Path(out) and "tt-tap-M" not in ctune.vm.Tract(Path(src)).shape_names():
        for p in ("TTX", "TTY", "TS3"):          # the vowel with the tip of tt-tap-u, jaw as there
            m[ix(p)] = tu[ix(p)]
        m[ix("JA")], m[ix("LD")] = tu[ix("JA")], max(m[ix("LD")], tu[ix("LD")])
        tr.set_shape("tt-tap-M", m)
    y = tr.shape("tt-tap-i")
    for v, al in blend.items():
        x = tr.shape(f"tt-tap-{v}").copy()
        for p in BODY:
            x[ix(p)] += al * (y[ix(p)] - x[ix(p)])
        tr.set_shape(f"tt-tap-{v}", x)
    tr.write_speaker(Path(out), Path(out))
    return out


if __name__ == "__main__":
    tap_shapes(V112, V113)
    edit_glottis(V113, "voiced-fricative", dict(zip(INDEX, VOICED_FRICATIVE)), V113)
    tr = ctune.vm.Tract(V113)
    for v in "aeiouM":
        x = tr.shape(f"tt-tap-{v}")
        a = tr.area_function(x, 96)
        r = a[0] / a[0][-1]
        print(v, np.round(tr.formants(x, 3)[0]), f"tip {a[1][(r > .8) & (r < .97)].min():.2f} back {a[1][(r > .2) & (r < .8)].min():.2f}")
