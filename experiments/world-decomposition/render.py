"""Render all Kanon audio used below into out/<version>/audio (git-ignored).

    KANON=v1-1-3 VTL_LIB=... python render.py jvs0xx jvs0yy ...
"""
import sys
import json
from copysynth import *

OUT = OUT / "audio"

if __name__ == "__main__":
    info = {}
    for u, text in SENTENCES.items():
        x, r = rule(text, OUT / f"vtl/{u}")
        for spk in sys.argv[1:]:
            real = load_jvs(spk, [u]).get(u)
            if real is None:
                continue
            P = analyse(real)
            y, segs, score = copy(text, OUT / f"{spk}/{u}", real, P)
            info[f"{spk}/{u}"] = dict(score=float(score), real_s=len(real) / RS, vtl_s=len(y) / RS)
            print(spk, u, info[f"{spk}/{u}"], flush=True)
    (OUT / "info.json").write_text(json.dumps(info, indent=1))
