import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app_core.project import Project, meta_path

from .common import KANON, read_text

TCX = ("tract_shape", "a", "TCX")
F0 = ("glottis_shape", "Triangular body-cover glottis", "modal", 0)


class Base(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.sid = self.p.open_speaker(KANON, "kanon")
        self.sp = self.p.speakers["kanon"]
        self.events = []
        self.p.subscribe(self.events.append)
        self.original = self.sp.text()

    def tcx(self):
        return self.sp.get(TCX)


class Single(Base):
    def test_set_undo_redo(self):
        r = self.p.ops.tract.set_param(speaker="kanon", shape="a", param="TCX", value=0.5)
        self.assertEqual(r, 0.5)
        self.assertEqual(self.tcx(), 0.5)
        self.assertTrue(self.p.undo())
        self.assertEqual(self.sp.text(), self.original)  # byte for byte
        self.assertTrue(self.p.redo())
        self.assertEqual(self.tcx(), 0.5)
        self.assertFalse(self.p.redo())

    def test_each_call_is_one_step(self):
        for v in (0.1, 0.2, 0.3):
            self.p.call("tract.set_param", {"speaker": "kanon", "shape": "a", "param": "TCX", "value": v})
        self.assertEqual(len(self.p.history.done), 3)
        self.p.undo()
        self.assertEqual(self.tcx(), 0.2)

    def test_clamped_to_the_range(self):
        self.p.ops.tract.set_param(speaker="kanon", shape="a", param="TCX", value=99)
        self.assertEqual(self.tcx(), 2.979)

    def test_glottis(self):
        r = self.p.ops.glottis.set_param(speaker="kanon", shape="modal", param="f0", value=250.123456789)
        self.assertEqual(r, 250.123457)
        self.assertEqual(self.sp.get(F0), 250.123457)
        self.p.undo()
        self.assertEqual(self.sp.text(), self.original)

    def test_glottis_other_model(self):
        self.p.ops.glottis.set_param(speaker="kanon", model="Geometric glottis 2025",
                                     shape="default", param=1, value=9000)
        self.assertEqual(self.sp.get(("glottis_shape", "Geometric glottis 2025", "default", 1)), 9000)

    def test_error_changes_nothing(self):
        with self.assertRaises(KeyError):
            self.p.ops.tract.set_param(speaker="kanon", shape="no-such-shape", param="TCX", value=0)
        self.assertEqual(self.p.history.done, [])
        self.assertEqual(self.events, [])


class Grouping(Base):
    def test_drag_is_one_step(self):
        for v in (0.1, 0.2, 0.3, 0.4):
            self.p.call("tract.set_param", {"speaker": "kanon", "shape": "a", "param": "TCX", "value": v},
                        drag="slider-1")
        self.assertEqual(len([e for e in self.events if e["type"] == "changed"]), 4)  # live updates
        self.p.end_drag("slider-1")
        self.assertEqual(len(self.p.history.done), 1)
        self.p.undo()
        self.assertEqual(self.sp.text(), self.original)

    def test_another_edit_ends_a_drag(self):
        self.p.call("tract.set_param", {"speaker": "kanon", "shape": "a", "param": "TCX", "value": 0.1}, drag=1)
        self.p.ops.tract.set_param(speaker="kanon", shape="a", param="TCY", value=0.0)
        self.assertEqual(len(self.p.history.done), 2)

    def test_group_is_one_step(self):
        with self.p.group("script"):
            for prm in ("TCX", "TCY", "TTX"):
                self.p.ops.tract.set_param(speaker="kanon", shape="a", param=prm, value=0.5)
            self.p.ops.glottis.set_param(speaker="kanon", shape="modal", param="f0", value=200)
            with self.p.group("inner"):  # nested groups join the outer one
                self.p.ops.tract.set_param(speaker="kanon", shape="i", param="JA", value=-3)
        self.assertEqual(len(self.p.history.done), 1)
        self.assertEqual(self.p.history.done[0].label, "script")
        self.assertEqual(len(self.p.history.done[0].changes), 5)
        self.p.undo()
        self.assertEqual(self.sp.text(), self.original)
        self.p.redo()
        self.assertEqual(self.tcx(), 0.5)

    def test_new_edit_clears_redo(self):
        self.p.ops.tract.set_param(speaker="kanon", shape="a", param="TCX", value=0.1)
        self.p.undo()
        self.p.ops.tract.set_param(speaker="kanon", shape="a", param="TCX", value=0.2)
        self.assertFalse(self.p.history.state()["can_redo"])


class Notifications(Base):
    def test_events(self):
        self.p.ops.tract.set_param(speaker="kanon", shape="a", param="TCX", value=0.5)
        self.p.undo()
        do, undo = self.events
        self.assertEqual(do["source"], "do")
        self.assertEqual(do["changes"], [{"speaker": "kanon", "address": list(TCX), "value": 0.5}])
        self.assertEqual(undo["source"], "undo")
        self.assertEqual(undo["changes"][0]["value"], -0.8236)
        self.assertTrue(undo["history"]["can_redo"])
        json.dumps(self.events)  # events go over the wire as JSON


class Save(Base):
    def test_save_writes_meta_with_the_operations(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.speaker"
            shutil.copy(KANON, path)
            self.p.ops.tract.set_param(speaker="kanon", shape="a", param="TCX", value=0.5)
            self.p.ops.tract.set_param(speaker="kanon", shape="a", param="TCX", value=0.6)
            self.p.undo()
            self.assertTrue(self.p.is_modified("kanon"))
            self.p.save_speaker("kanon", path)
            self.assertFalse(self.p.is_modified("kanon"))
            meta = json.loads(meta_path(path).read_text())
            ops = meta["saves"][0]["operations"]
            self.assertEqual([o["action"] for o in ops], ["do", "do", "undo"])
            self.assertEqual(ops[0]["calls"][0]["args"]["value"], 0.5)
            self.assertIn('name="TCX" value="0.5000"', read_text(path))
            self.p.save_speaker("kanon", path)  # a second save appends
            self.assertEqual(len(json.loads(meta_path(path).read_text())["saves"]), 2)


if __name__ == "__main__":
    unittest.main()
