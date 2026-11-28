"""Whole shapes (add, duplicate, rename, delete) and the status marks."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app_core.project import Project, meta_path
from app_core.speaker import Speaker
from app_core.vtl import backend

from .common import JD2, KANON, needs_vtl, read_text

TBCM = "Triangular body-cover glottis"
G2025 = "Geometric glottis 2025"


class Base(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.p.open_speaker(KANON, "kanon")
        self.sp = self.p.speakers["kanon"]
        self.text = read_text(KANON)

    def undo_all(self):
        while self.p.undo():
            pass
        self.assertEqual(self.sp.text(), self.text)
        self.assertEqual(self.p.edited("kanon"), {})


class TractShapes(Base):
    def test_add_is_neutral_one_step_and_undoes(self):
        self.p.ops.tract.add_shape(speaker="kanon", name="new")
        self.assertEqual(list(self.sp.tract_shapes)[-1], "new")
        self.assertEqual(self.sp.tract_shape("new"), [p.neutral for p in self.sp.tract_params])
        self.assertEqual(len(self.p.history.done), 1)
        self.assertIn(("tract_shape_def", "new"), self.p.edited("kanon"))
        self.assertIn("new", self.p.to_json()["speakers"]["kanon"]["tract"]["shapes"])
        self.undo_all()
        self.p.redo()
        self.assertIn("new", self.sp.tract_shapes)

    def test_duplicate_copies_the_values(self):
        self.p.ops.tract.duplicate_shape(speaker="kanon", shape="i", name="i2")
        self.assertEqual(self.sp.tract_shape("i2"), self.sp.tract_shape("i"))
        # the copy is a shape of its own
        self.p.ops.tract.set_param(speaker="kanon", shape="i2", param="TCX", value=0.1)
        self.assertNotEqual(self.sp.tract_shape("i2"), self.sp.tract_shape("i"))
        self.undo_all()

    def test_names_that_are_taken_or_empty_are_refused(self):
        for bad in ("a", "", " x", "x\n"):
            with self.subTest(repr(bad)):
                with self.assertRaises(ValueError):
                    self.p.ops.tract.duplicate_shape(speaker="kanon", shape="i", name=bad)
                with self.assertRaises(ValueError):
                    self.p.ops.tract.rename_shape(speaker="kanon", shape="i", name=bad)
        self.assertEqual(self.sp.text(), self.text)
        self.assertEqual(self.p.history.done, [])

    def test_rename_keeps_the_place_and_the_status(self):
        names = list(self.sp.tract_shapes)
        k = names.index("e")
        self.p.ops.status.set(speaker="kanon", what=["tract_shape", "e"], level="wip")
        self.p.ops.tract.rename_shape(speaker="kanon", shape="e", name="e-new")
        self.assertEqual(list(self.sp.tract_shapes)[k], "e-new")
        self.assertNotIn("e", self.sp.tract_shapes)
        self.assertEqual(self.sp.get(("status", "tract_shape", "e-new")), "wip")
        self.assertEqual(self.sp.get(("status", "tract_shape", "e")), "todo")
        self.assertEqual(len(self.p.history.done), 2)
        self.undo_all()

    def test_delete_with_edits_and_status_undoes_byte_for_byte(self):
        self.p.ops.tract.set_param(speaker="kanon", shape="o", param="TCX", value=0.2)
        self.p.ops.status.set(speaker="kanon", what=["tract_shape", "o"], level="done")
        first = list(self.sp.tract_shapes)[0]
        self.p.ops.tract.delete_shape(speaker="kanon", shape="o")
        self.p.ops.tract.delete_shape(speaker="kanon", shape=first)
        self.assertNotIn("o", self.sp.tract_shapes)
        self.assertEqual(self.sp.status, {})
        self.p.edited("kanon")  # values of the deleted shape do not break this
        self.undo_all()

    def test_the_last_shape_cannot_be_deleted(self):
        p = Project()
        p.open_speaker(JD2, "jd2")
        sp = p.speakers["jd2"]
        for n in list(sp.tract_shapes)[1:]:
            p.ops.tract.delete_shape(speaker="jd2", shape=n)
        with self.assertRaises(ValueError):
            p.ops.tract.delete_shape(speaker="jd2", shape=list(sp.tract_shapes)[0])
        while p.undo():
            pass
        self.assertEqual(sp.text(), read_text(JD2))


class GlottisShapes(Base):
    def test_add_uses_the_models_defaults(self):
        self.p.ops.glottis.add_shape(speaker="kanon", name="g")
        m = self.sp.selected_glottis
        self.assertEqual(m.shape_values("g"), [p.default for p in sorted(m.control, key=lambda p: p.index)])
        self.undo_all()

    def test_duplicate_rename_delete_in_another_model(self):
        self.p.ops.glottis.duplicate_shape(speaker="kanon", model=G2025, shape="modal", name="m2")
        m = self.sp.glottis_models[G2025]
        self.assertEqual(m.shape_values("m2"), m.shape_values("modal"))
        self.assertNotIn("m2", self.sp.selected_glottis.shapes)
        self.p.ops.glottis.rename_shape(speaker="kanon", model=G2025, shape="m2", name="m3")
        self.assertEqual(list(m.shapes)[-1], "m3")
        self.p.ops.glottis.delete_shape(speaker="kanon", model=G2025, shape="breathy")
        self.assertNotIn("breathy", m.shapes)
        with self.assertRaises(ValueError):
            self.p.ops.glottis.duplicate_shape(speaker="kanon", model=G2025, shape="modal", name="m3")
        self.undo_all()


class Status(Base):
    def test_status_is_an_operation_and_not_in_the_speaker_file(self):
        for what in (["tract_shape", "a"], ["glottis_shape", TBCM, "modal"], ["glottis_model", TBCM]):
            self.p.ops.status.set(speaker="kanon", what=what, level="wip")
        self.assertEqual(self.sp.text(), self.text)
        self.assertEqual(len(self.p.history.done), 3)
        self.assertEqual(len(self.p.edited("kanon")), 3)
        self.assertTrue(self.p.is_modified("kanon"))
        st = self.p.to_json()["speakers"]["kanon"]["status"]
        self.assertIn({"what": ["glottis_model", TBCM], "level": "wip"}, st)
        self.undo_all()

    def test_unknown_targets_and_levels_are_refused(self):
        for what, level in ((["tract_shape", "nope"], "wip"), (["glottis_model", "x"], "wip"),
                            (["tract_shape", "a"], "great"), (["speaker"], "wip")):
            with self.subTest(what=what, level=level):
                with self.assertRaises((KeyError, ValueError)):
                    self.p.ops.status.set(speaker="kanon", what=what, level=level)
        self.assertEqual(self.p.history.done, [])

    def test_saved_in_the_meta_file_and_read_back(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "s.speaker"
            shutil.copyfile(KANON, f)
            p = Project()
            p.open_speaker(f, "k")
            p.ops.status.set(speaker="k", what=["tract_shape", "a"], level="done")
            p.ops.status.set(speaker="k", what=["glottis_model", TBCM], level="wip")
            p.save_speaker("k")
            self.assertEqual(read_text(f), self.text)  # only the meta file changed
            meta = json.loads(meta_path(f).read_text())
            self.assertEqual(len(meta["status"]), 2)
            self.assertEqual(p.edited("k"), {})
            q = Project()
            q.open_speaker(f, "k")
            self.assertEqual(q.speakers["k"].get(("status", "tract_shape", "a")), "done")
            self.assertEqual(q.speakers["k"].get(("status", "glottis_model", TBCM)), "wip")
            self.assertEqual(q.speakers["k"].get(("status", "tract_shape", "i")), "todo")


@needs_vtl
class SavedFile(unittest.TestCase):
    def test_vtl_reads_added_renamed_and_deleted_shapes_back(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "s.speaker"
            shutil.copyfile(KANON, f)
            p = Project()
            p.open_speaker(f, "k")
            p.ops.tract.duplicate_shape(speaker="k", shape="i", name="i-copy")
            p.ops.tract.add_shape(speaker="k", name="neutral2")
            p.ops.tract.rename_shape(speaker="k", shape="u", name="u-renamed")
            p.ops.tract.delete_shape(speaker="k", shape="o")
            p.ops.glottis.duplicate_shape(speaker="k", shape="modal", name="modal-2")
            p.ops.glottis.set_param(speaker="k", shape="modal-2", param="f0", value=170)
            p.ops.glottis.delete_shape(speaker="k", shape="breathy")
            p.save_speaker("k")
            sp = Speaker.load(f)
            self.assertIn("i-copy", sp.tract_shapes)
            self.assertNotIn("o", sp.tract_shapes)
            b = backend()
            b.load_all(sp)
            orig = Speaker.load(KANON)
            for name, like in (("i-copy", "i"), ("u-renamed", "u")):
                self.assertEqual(list(b.tract_params_of_shape(sp, name)),
                                 list(b.tract_params_of_shape(orig, like)))
            self.assertEqual(list(b.tract_params_of_shape(sp, "neutral2")), [p.neutral for p in sp.tract_params])
            w = b.glottis_wave(sp, "i-copy", "modal-2", 0.3)
            self.assertAlmostEqual(w["f0_measured"], 170, delta=170 * 0.03)


if __name__ == "__main__":
    unittest.main()
