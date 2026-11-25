"""Enlarge a speaker's vocal tract as a whole: every length of the anatomy and every length-valued
articulatory parameter (targets and ranges) times k, angles and unitless parameters as they are.

The result is the same head and the same articulation, seen through a magnifier, so closures stay
closures and places of constriction stay where they are (relative to the tract). Not scaled:
  * TS1-TS3 (tongue sides): VTL reads them against absolute thresholds (0.2: friction, -0.2: lateral)
    and floors the area at absolute values, so the fricatives and taps keep their channel areas;
  * VO, VS, LP, HX (unitless, or an area);
  * the piriform fossa, the nasal cavity and the trachea, which in Kanon's file are already adult;
  * the glottis models.

    scale.py <k> <out.speaker> [base.speaker]
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / "speakers/fulkhisa-kanon/fulkhisa-kanon-v1-3-1.speaker"
LENGTHS = {
    r"p\d": ["x", "z", "teeth_height", "top_teeth_width", "bottom_teeth_width", "palate_height", "jaw_height"],
    "jaw": ["fulcrum_x", "fulcrum_y", "rest_pos_x", "rest_pos_y", "tooth_root_length"],
    "lips": ["width"], "tip": ["radius"], "body": ["radius_x", "radius_y"], "root": ["trx_intercept", "try_intercept"],
    "tonsil": ["length", "height"], "velum": ["uvula_width", "uvula_height", "uvula_depth"],
    "low|mid|high|narrow|wide": ["points"],
    "pharynx": ["fulcrum_x", "fulcrum_y", "top_rib_y", "upper_depth", "lower_depth", "back_side_width"],
    "larynx": ["upper_depth", "lower_depth", "epiglottis_width", "epiglottis_height", "epiglottis_depth"],
}
PARAMS = ["HY", "JX", "LD", "TCX", "TCY", "TTX", "TTY", "TBX", "TBY", "TRX", "TRY"]
LIP_OFFSET = .4            # VocalTract::calcLips uses width - 0.4 as a radius


def scale_text(s, k):
    e = s.index("</anatomy>")
    anat, rest = s[:e], s[e:]
    num = lambda m, f: m[1] + " ".join(f"{f(float(v)):.6g}" for v in m[2].split()) + m[3]

    def element(m):
        tag = m[0]
        name = re.match(r"<(\w+)", tag)[1]
        for pat, attrs in LENGTHS.items():
            if re.fullmatch(pat, name):
                for a in attrs:
                    f = (lambda v: k * (v - LIP_OFFSET) + LIP_OFFSET) if name == "lips" else (lambda v: k * v)
                    tag = re.sub(rf'(\s{a}=")([^"]*)(")', lambda q: num(q, f), tag)
        if name == "param" and re.search(r'name="(\w+)"', tag)[1] in PARAMS:
            tag = re.sub(r'(\s(?:min|max|neutral)=")([^"]*)(")', lambda q: num(q, lambda v: k * v), tag)
        return tag
    anat = re.sub(r"<[a-z]\w*[^>]*>", element, anat)
    t = rest.index("</vocal_tract_model>")
    rest = re.sub(rf'(<param name="(?:{"|".join(PARAMS)})"[^>]*value=")([^"]*)(")',
                  lambda q: num(q, lambda v: k * v), rest[:t]) + rest[t:]
    return anat + rest


def scaled(k, out, base=BASE):
    with open(base, newline="") as f:
        s = f.read()
    with open(out, "w", newline="") as f:
        f.write(scale_text(s, k))
    return Path(out)


if __name__ == "__main__":
    scaled(float(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else BASE)
