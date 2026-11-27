"""Calling operations from Python, the same way the screen will.

    cd app && ../build-mac/py.sh examples/edit_speaker.py [OUT_DIR]

Opens Kanon v1.4.1, edits /a/ and the modal glottis shape as one undo step,
prints the formants before and after, undoes, redoes, and saves a copy (with
its .meta.json) to OUT_DIR (default: a temporary folder). The speaker in the
repository is not touched.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_core.project import Project  # noqa: E402
from app_core.vtl import backend  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

project = Project()
sid = project.open_speaker(REPO / "speakers/fulkhisa-kanon/fulkhisa-kanon-v1-4-1.speaker", "kanon")
sp = project.speakers[sid]
project.subscribe(lambda e: print("  event:", e["type"], e.get("source", ""),
                                  [(c["address"], c["value"]) for c in e.get("changes", [])]))

vtl = backend()
print("/a/ formants:", [round(f) for f in vtl.formants(sp, "a")])

# A script is one undo step.
with project.group("open /a/ more"):
    project.ops.tract.set_param(speaker=sid, shape="a", param="JA", value=-6.0)
    project.ops.tract.set_param(speaker=sid, shape="a", param="TCY", value=-1.8)
    project.ops.glottis.set_param(speaker=sid, shape="modal", param="f0", value=240)
print("after the script:", [round(f) for f in vtl.formants(sp, "a")])

project.undo()
print("after undo:      ", [round(f) for f in vtl.formants(sp, "a")])
project.redo()

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
path = project.save_speaker(sid, out / "kanon-edited.speaker")
print("saved", path, "and", path.with_name(path.stem + ".meta.json"))
