"""Build candidate alveolo-palatal fricative shapes [ɕ] for the Kanon speaker.

Each candidate starts from VTL's postalveolar fricative S(v) for the vowel
contexts v = a, i, u and moves the tongue body (TCX TCY TBX TBY) a fraction
w of the way to the palatal fricative C(v). Optionally the tongue tip is
lowered (laminal articulation) and the lips are spread. Every candidate is
written into a copy of the speaker file as tt-alveolopalatal-fricative(v),
rendered in /a_a/, /a_i/ and /a_ɯ/, and measured.

Run from the repository root:
    python3 experiments/japanese-accent/alveolopalatal.py [--install NAME]
--install writes the named candidate into the speaker file itself.
"""
import argparse
import ctypes as ct
import itertools
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from scipy.io.wavfile import read

import accent
from accent import SPEAKER, render
from consonants import frames, low_band_db, rms_db, spectrum_stats

OUT = Path(__file__).resolve().parent / "results/alveolopalatal"
BODY = ["TCX", "TCY", "TBX", "TBY"]
CONTEXTS = {"a": "アシャア", "i": "アシア", "u": "アシュア"}


def shapes_of(root):
    vt = root.find(".//vocal_tract_model")
    return vt.find("shapes"), {s.get("name"): s for s in vt.find("shapes")}


def values(shape):
    return {p.get("name"): float(p.get("value")) for p in shape}


def candidate(base, palatal, w, tip_drop, spread):
    out = dict(base)
    for k in BODY:
        out[k] = (1 - w) * base[k] + w * palatal[k]
    out["TTY"] = base["TTY"] - tip_drop
    if spread:
        out["LP"] = min(base["LP"], -0.5)
    return out


def make_shape(name, params, template):
    shape = ET.Element("shape", name=name)
    for p in template:
        ET.SubElement(shape, "param", name=p.get("name"), value=f"{params[p.get('name')]:.4f}")
    return shape


def write_speaker(src, dst, new_shapes):
    tree = ET.parse(src)
    container, existing = shapes_of(tree.getroot())
    for name, params in new_shapes.items():
        if name in existing:
            container.remove(existing[name])
        container.append(make_shape(name, params, existing["tt-postalveolar-fricative(a)"]))
    ET.indent(tree, "  ")
    tree.write(dst, encoding="utf-8", xml_declaration=True)


def install(speaker, new_shapes, order):
    """Insert the shapes as text after tt-postalveolar-fricative(u), keeping
    the rest of the speaker file byte-for-byte."""
    with open(speaker, newline="") as f:
        text = f.read()
    nl = "\r\n" if "\r\n" in text else "\n"
    anchor = '<shape name="tt-postalveolar-fricative(u)">'
    start = text.index(anchor)
    indent = text[text.rindex("\n", 0, start) + 1:start]
    end = text.index("</shape>", start) + len("</shape>")
    block = ""
    for name, params in new_shapes.items():
        if f'<shape name="{name}">' in text:
            raise SystemExit(f"{name} already in {speaker}")
        block += f"{nl}{indent}<shape name=\"{name}\">"
        for k in order:
            block += f"{nl}{indent}  <param name=\"{k}\" value=\"{params[k]:.4f}\"/>"
        block += f"{nl}{indent}</shape>"
    with open(speaker, "w", newline="") as f:
        f.write(text[:end] + block + text[end:])


def constriction(params_order, lib):
    """Minimum area (cm²) and front-cavity length (cm) of the static shape."""
    n = lib.tube_sections
    lengths, areas = np.empty(n), np.empty(n)
    arts = (ct.c_int * n)()
    scalars = [ct.c_double() for _ in range(3)]
    x = np.array(params_order)
    assert lib.vtlTractToTube(x.ctypes.data_as(ct.POINTER(ct.c_double)),
                              lengths.ctypes.data_as(ct.POINTER(ct.c_double)),
                              areas.ctypes.data_as(ct.POINTER(ct.c_double)),
                              arts, *map(ct.byref, scalars)) == 0
    k = int(np.argmin(areas[5:])) + 5        # skip the glottal end
    return float(areas[k]), float(lengths[k + 1:].sum())


def candidates(shapes):
    grid = itertools.product([0.0, 0.33, 0.67, 1.0], [0.0, 0.4], [False, True])
    for w, tip, spread in grid:
        name = f"w{w:.2f}-tip{tip:.1f}-{'spread' if spread else 'keep'}"
        yield name, {f"tt-alveolopalatal-fricative({v})": candidate(
            values(shapes[f"tt-postalveolar-fricative({v})"]),
            values(shapes[f"tb-palatal-fricative({v})"]), w, tip, spread) for v in "aiu"}


def measure(name, speaker, order):
    rows = {}
    for v, word in CONTEXTS.items():
        stem = OUT / name / v
        r = render(word, stem, speaker=speaker, f0_model=None)
        sr, x = read(stem.with_suffix(".wav"))
        x = x / 32767
        seg = next(s for s in r["segments"] if s.name == "s\\")
        part = frames(x, sr, seg.t0, seg.t0 + seg.duration)
        vowel = next(s for s in r["segments"] if s.name == "a")
        vx = frames(x, sr, vowel.t0, vowel.t0 + vowel.duration)
        cog, peak = spectrum_stats(part, sr)
        rows[v] = dict(cog_hz=round(cog), peak_hz=round(peak),
                       level_re_vowel_db=round(rms_db(part) - rms_db(vx), 1),
                       low_band_re_vowel_db=round(low_band_db(part, sr) - low_band_db(vx, sr), 1))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", help="write this candidate into the speaker file")
    args = ap.parse_args()
    tree = ET.parse(SPEAKER)
    _, shapes = shapes_of(tree.getroot())
    order = [p.get("name") for p in shapes["a"]]
    all_candidates = dict(candidates(shapes))
    if args.install:
        install(SPEAKER, all_candidates[args.install], order)
        print("installed", args.install, "into", SPEAKER)
        return

    summary = {}
    tmp = Path(tempfile.mkdtemp())
    for name, new in all_candidates.items():
        speaker = tmp / f"{name}.speaker"
        write_speaker(SPEAKER, speaker, new)
        lib = accent.use_speaker(speaker)
        area, front = constriction([new["tt-alveolopalatal-fricative(i)"][k] for k in order], lib)
        summary[name] = dict(min_area_cm2_i=round(area, 3), front_cavity_cm_i=round(front, 2),
                             **measure(name, speaker, order))
        print(name, summary[name])
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
