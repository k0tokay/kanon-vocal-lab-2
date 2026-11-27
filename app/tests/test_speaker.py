import difflib
import tempfile
import unittest
from pathlib import Path

import numpy as np

from app_core.speaker import Speaker, format_like

from .common import JD2, KANON, SPEAKERS, needs_vtl, read_text


class RoundTrip(unittest.TestCase):
    def test_every_speaker_in_the_repository_is_written_back_byte_for_byte(self):
        files = sorted(SPEAKERS.rglob("*.speaker"))
        self.assertIn(KANON, files)
        self.assertIn(JD2, files)
        for f in files:
            with self.subTest(f.name):
                self.assertEqual(Speaker.load(f).text(), read_text(f))

    def test_save_writes_the_same_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            out = Speaker.load(JD2).save(Path(d) / "x.speaker")  # JD2 has CRLF line ends
            self.assertEqual(out.read_bytes(), JD2.read_bytes())

    def test_a_change_touches_only_that_value(self):
        sp = Speaker.load(KANON)
        before = sp.text().splitlines()
        stored = sp.set(("tract_shape", "a", "TCX"), -0.123456)
        self.assertEqual(stored, -0.1235)  # the file keeps 4 decimals
        diff = [l for l in difflib.unified_diff(before, sp.text().splitlines(), lineterm="", n=0)
                if l[:1] in "+-" and l[:3] not in ("+++", "---")]
        self.assertEqual(diff, ['-        <param name="TCX" value="-0.8236"/>',
                                '+        <param name="TCX" value="-0.1235"/>'])


class Tree(unittest.TestCase):
    def test_parts(self):
        sp = Speaker.load(KANON)
        self.assertEqual(len(sp.tract_params), 19)
        self.assertEqual(sp.tract_param_names[:4], ["HX", "HY", "JX", "JA"])
        self.assertEqual(list(sp.glottis_models), [
            "Geometric glottis 2025", "Geometric glottis 2019",
            "Triangular glottis", "Triangular body-cover glottis"])
        self.assertEqual(sp.selected_glottis.type, "Triangular body-cover glottis")
        self.assertIn("modal", sp.glottis_models["Geometric glottis 2025"].shapes)
        self.assertEqual(sp.get(("anatomy", "palate", "p3", "x")), 1.3338)
        self.assertEqual(sp.get(("glottis_static", "Geometric glottis 2025", "rest_f0")), 170.0)
        self.assertEqual(sp.get(("glottis_shape", "Geometric glottis 2025", "default", "f0")), 225.92)
        j = sp.to_json()
        self.assertEqual(j["glottis"]["selected"], "Triangular body-cover glottis")
        self.assertEqual(len(j["tract"]["shapes"]["a"]), 19)

    def test_select_glottis(self):
        sp = Speaker.load(KANON)
        sp.set(("glottis_selected",), "Geometric glottis 2019")
        self.assertEqual(Speaker(sp.text()).selected_glottis.type, "Geometric glottis 2019")

    def test_format_like(self):
        self.assertEqual(format_like("0.7386", 1 / 3), "0.3333")
        self.assertEqual(format_like("225.920000", 200), "200.000000")
        self.assertEqual(format_like("1", 2.0), "2")


@needs_vtl
class ReadByVTL(unittest.TestCase):
    def test_tree_values_are_what_vtl_reads(self):
        from app_core.vtl import backend
        for f in (KANON, JD2):
            sp = Speaker.load(f)
            for name in sp.tract_shapes:
                with self.subTest(f.name, shape=name):
                    np.testing.assert_array_equal(backend().tract_params_of_shape(sp, name),
                                                  sp.tract_shape(name))

    def test_vtl_reads_an_edited_file_with_the_new_value(self):
        from app_core.vtl import backend
        sp = Speaker.load(KANON)
        stored = sp.set(("tract_shape", "i", "TBY"), 1.23456)
        sp2 = Speaker(sp.text())
        x = backend().tract_params_of_shape(sp2, "i")
        self.assertEqual(x[sp.tract_param_names.index("TBY")], stored)
        info = backend().tract_param_info(sp2)
        self.assertEqual(info["names"], sp.tract_param_names)
        np.testing.assert_allclose(info["min"], [p.min for p in sp.tract_params])


if __name__ == "__main__":
    unittest.main()
