"""v1.1.4 + the body-cover glottis of v1.3.0 -> v1.3.1.

The vocal tract (shapes, also tt-tap-M), the three older glottis models and the timing rules are those
of v1.1.4; the block "Triangular body-cover glottis" is copied from v1.3.0 as it is, and selected. v1.3.0
itself is v1.1.0 plus this block, so nothing else of it is needed. The glottal shapes of the obstruents
tuned for Geometric glottis 2025 (voiced-plosive, voiced- and voiceless-fricative) stay in their block and
have no effect while the body-cover glottis is selected: that one has its own shapes of these names.
"""
import re

from build import ROOT, Path

KANON = ROOT / "speakers/fulkhisa-kanon"
V114, V130, V131 = (KANON / f"fulkhisa-kanon-v{v}.speaker" for v in ("1-1-4", "1-3-0", "1-3-1"))
BLOCK = re.compile(r'[ \t]*<glottis_model type="Triangular body-cover glottis".*?</glottis_model>\r?\n', re.S)

if __name__ == "__main__":
    s, b = V114.read_text(), BLOCK.search(V130.read_text())[0]
    s = re.sub(r'(<glottis_model type="[^"]+" selected=")1"', r'\g<1>0"', BLOCK.sub("", s))
    i = s.index("  </glottis_models>")
    V131.write_text(s[:i] + b + s[i:])
