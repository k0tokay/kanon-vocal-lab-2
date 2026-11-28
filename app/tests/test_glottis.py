"""Stage 5: glottis operations, switching the model, saving, and the glottis waveform."""

import shutil
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import AioHTTPTestCase

from app_core.project import Project
from app_core.server import make_app
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


class Ops(Base):
    def test_shape_param_one_step_and_undo(self):
        self.assertEqual(self.sp.selected_glottis.type, TBCM)
        v = self.p.ops.glottis.set_param(speaker="kanon", shape="modal", param="f0", value=250)
        self.assertEqual(v, 250.0)
        self.assertEqual(self.sp.get(("glottis_shape", TBCM, "modal", 0)), 250.0)
        self.assertEqual(len(self.p.history.done), 1)
        self.assertEqual(list(self.p.edited("kanon")), [("glottis_shape", TBCM, "modal", 0)])
        self.p.undo()
        self.assertEqual(self.sp.text(), self.text)
        self.assertEqual(self.p.edited("kanon"), {})

    def test_drag_is_one_step(self):
        for v in (200, 210, 230):
            self.p.call("glottis.set_param", {"speaker": "kanon", "shape": "modal", "param": "act_ct", "value": v / 1000},
                        drag="d")
        self.p.end_drag("d")
        self.assertEqual(len(self.p.history.done), 1)
        self.p.undo()
        self.assertEqual(self.sp.text(), self.text)

    def test_values_are_clamped_to_the_range(self):
        info = self.sp.selected_glottis.control[self.sp.selected_glottis.control_index("f0")]
        self.assertEqual(self.p.ops.glottis.set_param(speaker="kanon", shape="modal", param="f0", value=1e9), info.max)

    def test_static_param_and_undo(self):
        v = self.p.ops.glottis.set_static(speaker="kanon", param="rest_length", value=1.1)
        self.assertAlmostEqual(v, 1.1)
        self.assertEqual(list(self.p.edited("kanon")), [("glottis_static", TBCM, "rest_length")])
        self.p.undo()
        self.assertEqual(self.sp.text(), self.text)

    def test_another_models_shape(self):
        self.p.ops.glottis.set_param(speaker="kanon", model=G2025, shape="modal", param="f0", value=150)
        self.assertEqual(self.sp.glottis_models[G2025].shape_values("modal")[0], 150.0)
        self.assertEqual(self.sp.selected_glottis.type, TBCM)  # selection unchanged

    def test_select_model_is_one_step_and_undoes(self):
        events = []
        self.p.subscribe(events.append)
        self.p.ops.glottis.select_model(speaker="kanon", model=G2025)
        self.assertEqual(self.sp.selected_glottis.type, G2025)
        self.assertEqual(self.p.to_json()["speakers"]["kanon"]["glottis"]["selected"], G2025)
        self.assertEqual(events[-1]["changes"][0]["address"], ["glottis_selected"])
        self.assertEqual(len(self.p.history.done), 1)
        self.assertEqual(list(self.p.edited("kanon")), [("glottis_selected",)])
        self.p.undo()
        self.assertEqual(self.sp.text(), self.text)
        self.p.redo()
        self.assertEqual(self.sp.selected_glottis.type, G2025)

    def test_unknown_model_changes_nothing(self):
        p = Project()
        p.open_speaker(JD2, "jd2")  # JD2 has no body-cover model
        with self.assertRaises(KeyError):
            p.ops.glottis.select_model(speaker="jd2", model=TBCM)
        self.assertEqual(p.speakers["jd2"].text(), read_text(JD2))
        self.assertEqual(p.history.done, [])


@needs_vtl
class SavedFile(Base):
    def test_vtl_reads_the_saved_glottis_back(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "g.speaker"
            shutil.copyfile(KANON, f)
            p = Project()
            p.open_speaker(f, "k")
            p.ops.glottis.select_model(speaker="k", model=G2025)
            p.ops.glottis.set_param(speaker="k", shape="modal", param="f0", value=180)
            p.ops.glottis.set_static(speaker="k", param=0, value=1.0)
            p.save_speaker("k")
            sp = Speaker.load(f)
            self.assertEqual(sp.selected_glottis.type, G2025)
            b = backend()
            b.load_all(sp)  # vtlInitialize reads the file as written
            self.assertEqual(b.num_glottis_params, len(sp.glottis_models[G2025].control))
            w = b.glottis_wave(sp, "a", "modal", 0.3)
            self.assertAlmostEqual(w["f0_measured"], 180, delta=180 * 0.03)


@needs_vtl
class Wave(Base):
    def test_every_model_gives_a_periodic_wave_at_the_shapes_f0(self):
        for model in self.sp.glottis_models:
            with self.subTest(model):
                self.sp.set(("glottis_selected",), model)
                w = backend().glottis_wave(self.sp, "a", "modal", 0.3)
                n = len(w["flow_cm3_s"])
                self.assertEqual(len(w["area_cm2"]), n)
                self.assertEqual(len(w["output"]), n)
                self.assertAlmostEqual(n, 4 * w["sampling_rate"] / w["f0_target"], delta=2)
                self.assertGreaterEqual(min(w["area_cm2"]), 0)
                self.assertGreater(max(w["flow_cm3_s"]) - min(w["flow_cm3_s"]), 10)
                self.assertAlmostEqual(w["f0_measured"], w["f0_target"], delta=w["f0_target"] * 0.05)

    def test_edits_reach_the_wave(self):
        self.p.ops.glottis.set_param(speaker="kanon", shape="modal", param="f0", value=300)
        w = backend().glottis_wave(self.sp, "a", "modal", 0.3)
        self.assertEqual(w["f0_target"], 300)
        self.assertAlmostEqual(w["f0_measured"], 300, delta=9)


class Server(AioHTTPTestCase):
    async def get_application(self):
        self.project = Project()
        self.project.open_speaker(KANON, "kanon")
        return make_app(self.project)

    @needs_vtl
    async def test_glottis_wave_over_websocket(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()  # hello
        await ws.send_json({"id": 1, "kind": "glottis_wave", "speaker": "kanon", "tract_shape": "a",
                            "glottis_shape": "modal"})
        r = (await ws.receive_json())["result"]
        self.assertEqual(r["f0_target"], 220.0)
        self.assertEqual(len(r["flow_cm3_s"]), len(r["area_cm2"]))
        await ws.close()

    @needs_vtl
    async def test_sustained_with_another_glottis_shape(self):
        a = await self.client.post("/api/sustained", json={"speaker": "kanon", "shape": "a", "duration": 0.2})
        b = await self.client.post("/api/sustained", json={"speaker": "kanon", "shape": "a", "duration": 0.2,
                                                           "glottis_shape": "falsetto"})
        self.assertEqual((a.status, b.status), (200, 200))
        self.assertNotEqual(a.headers["X-Sound-Key"], b.headers["X-Sound-Key"])
        self.assertNotEqual(await a.read(), await b.read())


if __name__ == "__main__":
    unittest.main()
