import unittest

import numpy as np

from app_core.project import Project
from app_core.vtl import CONTOUR_NAMES

from .common import JD2, KANON, needs_vtl


@needs_vtl
class Compute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app_core.vtl import backend
        cls.b = backend()
        cls.p = Project()
        cls.p.open_speaker(KANON, "kanon")
        cls.p.open_speaker(JD2, "jd2")

    def test_formants_of_vowels(self):
        sp = self.p.speakers["kanon"]
        a, i, u = (self.b.formants(sp, v) for v in "aiu")
        self.assertGreater(a[0], i[0])  # /a/ is open
        self.assertGreater(i[1], 2 * u[1])  # /i/ front, /u/ back
        self.assertGreater(self.b.formants(sp, "a")[0], self.b.formants(self.p.speakers["jd2"], "a")[0])

    def test_tube(self):
        t = self.b.tube(self.p.speakers["kanon"], "a")
        self.assertEqual(len(t.area_cm2), self.b.num_tube_sections)
        self.assertTrue(np.all(t.length_cm > 0))
        self.assertTrue(12 < t.position_cm[-1] + t.length_cm[-1] < 20)

    def test_contours(self):
        c = self.b.contours(self.p.speakers["kanon"], "i")
        self.assertEqual(tuple(c), CONTOUR_NAMES)
        lips = c["upper_front"][-1]
        self.assertGreater(lips[0], 0)  # lips are in front (+x), larynx below (-y)
        self.assertLess(c["lower_cover_larynx"][:, 1].min(), -5)

    def test_an_operation_changes_the_result(self):
        sp = self.p.speakers["kanon"]
        f1 = self.b.formants(sp, "a")[0]
        self.p.ops.tract.set_param(speaker="kanon", shape="a", param="JA", value=-1.0)  # close the jaw
        self.assertLess(self.b.formants(sp, "a")[0], f1 - 50)
        self.p.undo()
        self.assertAlmostEqual(self.b.formants(sp, "a")[0], f1)

    def test_editing_shapes_does_not_reload(self):
        sp = self.p.speakers["kanon"]
        self.b.use(sp)
        key = self.b._key
        self.p.ops.tract.set_param(speaker="kanon", shape="a", param="TCX", value=0.1)
        self.b.use(sp)
        self.assertEqual(self.b._key, key)
        sp.set(("anatomy", "lips", "width"), 1.0)
        self.b.use(sp)
        self.assertNotEqual(self.b._key, key)
        self.p.undo()


if __name__ == "__main__":
    unittest.main()
