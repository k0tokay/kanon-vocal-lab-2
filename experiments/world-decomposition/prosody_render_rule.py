"""The current rules (plain pyopenjtalk env) for the sentences prosody_render.py chose."""
import contextlib
import io
import json
import sys
from pathlib import Path

from prosody_render import accent, build

texts = json.load(open(sys.argv[1])); od = Path(sys.argv[2])
for u in json.load(open(od / "utts.json")):
    segs = build(texts[u]["text"], "rule", None, None, None, u); seg = od / f"{u}-rule.seg"; accent.write_seg(segs, seg)
    with contextlib.redirect_stdout(io.StringIO()):
        accent.synthesize(seg, seg.with_suffix(".wav"), segs)
