"""Stage 4: saving (with the files the server refuses to overwrite) and the held vowel."""

import difflib
import io
import json
import shutil
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np
from aiohttp.test_utils import AioHTTPTestCase

from app_core.project import Project, SaveRefused, meta_path
from app_core.server import make_app
from app_core.speaker import Speaker
from app_core.vtl import backend

from .common import KANON, needs_vtl, read_text

SET = {"speaker": "kanon", "shape": "a", "param": "TCX", "value": 0.5}


class Save(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def open_copy(self, name: str) -> tuple[Project, Path]:
        f = self.dir / name
        shutil.copyfile(KANON, f)
        p = Project()
        p.open_speaker(f, "kanon")
        return p, f

    def test_save_changes_exactly_one_value_and_is_not_an_undo_step(self):
        p, f = self.open_copy("work.speaker")
        p.call("tract.set_param", SET)
        steps = len(p.history.done)
        out = p.save_speaker("kanon")
        self.assertEqual(out, f)
        self.assertEqual(len(p.history.done), steps)
        self.assertEqual(p.edited("kanon"), {})
        self.assertFalse(p.is_modified("kanon"))
        diff = [l for l in difflib.unified_diff(read_text(KANON).splitlines(), read_text(f).splitlines(),
                                                lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
        self.assertEqual(diff, ['-        <param name="TCX" value="-0.8236"/>',
                                '+        <param name="TCX" value="0.5000"/>'])
        meta = json.loads(meta_path(f).read_text())
        self.assertEqual(meta["saves"][-1]["operations"][0]["calls"][0]["op"], "tract.set_param")

    @needs_vtl
    def test_vtl_reads_the_saved_file_back(self):
        p, f = self.open_copy("work.speaker")
        p.call("tract.set_param", SET)
        p.save_speaker("kanon")
        x = backend().tract_params_of_shape(Speaker.load(f), "a")
        names = Speaker.load(f).tract_param_names
        self.assertAlmostEqual(x[names.index("TCX")], 0.5)

    def test_protected_files_are_refused(self):
        for i, name in enumerate(("kanon-v1-3-1-manual-edit2.speaker", "kanon-intuition-001.speaker", "kanon-v1-2-0-rec-a.speaker")):
            with self.subTest(name):
                p, f = self.open_copy(name)
                before = f.read_bytes()
                p.call("tract.set_param", SET)
                with self.assertRaises(SaveRefused) as e:
                    p.save_speaker("kanon")
                self.assertEqual(e.exception.reason, "protected")
                with self.assertRaises(SaveRefused):  # not even with overwrite, nor by its path
                    p.save_speaker("kanon", f, overwrite=True)
                self.assertEqual(f.read_bytes(), before)
                self.assertFalse(meta_path(f).exists())
                self.assertTrue(p.edited("kanon"))  # still unsaved
                # save as: a new name works
                out = p.save_speaker("kanon", f"copy{i}")
                self.assertEqual(out, self.dir / f"copy{i}.speaker")
                self.assertEqual(p.edited("kanon"), {})

    def test_released_versions_are_refused(self):
        d = self.dir / "speakers" / "x"
        d.mkdir(parents=True)
        f = d / "kanon-v9-9-9.speaker"
        shutil.copyfile(KANON, f)
        p = Project()
        p.open_speaker(f, "kanon")
        p.call("tract.set_param", SET)
        with self.assertRaises(SaveRefused) as e:
            p.save_speaker("kanon", overwrite=True)
        self.assertEqual(e.exception.reason, "versioned")
        out = p.save_speaker("kanon", "kanon-v9-9-10")  # a new version is fine
        self.assertTrue(out.exists())
        self.assertEqual(Speaker.load(out).path, out)

    def test_another_existing_file_needs_overwrite(self):
        p, f = self.open_copy("work.speaker")
        other = self.dir / "other.speaker"
        other.write_text("x")
        with self.assertRaises(SaveRefused) as e:
            p.save_speaker("kanon", "other.speaker")
        self.assertEqual(e.exception.reason, "exists")
        self.assertEqual(other.read_text(), "x")
        self.assertEqual(p.save_speaker("kanon", "other.speaker", overwrite=True), other)
        # the speaker now lives there: saving again needs no confirmation
        self.assertEqual(p.save_speaker("kanon"), other)


@needs_vtl
class Sustained(unittest.TestCase):
    def test_a_held_vowel_is_one_second_and_not_silent(self):
        sp = Speaker.load(KANON)
        x, sr = backend().sustained(sp, "a", 1.0)
        self.assertLessEqual(abs(len(x) - sr), 96)
        rms = np.sqrt(np.mean(x[sr // 4: 3 * sr // 4] ** 2))
        self.assertGreater(rms, 1e-3)
        self.assertLess(np.abs(x[:10]).max(), rms)  # faded in
        self.assertLess(np.abs(x[-10:]).max(), rms)  # faded out

    def test_another_shape_sounds_different(self):
        sp = Speaker.load(KANON)
        a, _ = backend().sustained(sp, "a", 0.3)
        i, _ = backend().sustained(sp, "i", 0.3)
        self.assertGreater(np.abs(a - i).max(), 1e-3)


class Http(AioHTTPTestCase):
    async def get_application(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.file = self.dir / "kanon-manual-edit.speaker"
        shutil.copyfile(KANON, self.file)
        self.project = Project()
        self.project.open_speaker(self.file, "kanon")
        return make_app(self.project)

    async def test_save_refusal_and_save_as(self):
        r = await (await self.client.post("/api/save", json={"speaker": "kanon"})).json()
        self.assertEqual(r["result"], {"ok": False, "reason": "protected", "path": str(self.file)})
        r = await (await self.client.post("/api/save", json={"speaker": "kanon", "path": "new"})).json()
        self.assertEqual(r["result"], {"ok": True, "path": str(self.dir / "new.speaker")})

    @needs_vtl
    async def test_sustained_wav_and_cache(self):
        body = {"speaker": "kanon", "shape": "a", "duration": 0.5}
        r = await self.client.post("/api/sustained", json=body)
        self.assertEqual(r.status, 200)
        self.assertEqual(r.content_type, "audio/wav")
        data = await r.read()
        with wave.open(io.BytesIO(data)) as w:
            self.assertEqual(w.getnchannels(), 1)
            self.assertAlmostEqual(w.getnframes() / w.getframerate(), 0.5, delta=0.003)
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        self.assertGreater(np.sqrt(np.mean(pcm.astype(float) ** 2)), 100)
        r2 = await self.client.post("/api/sustained", json=body)
        self.assertEqual(r2.headers["X-Sound-Key"], r.headers["X-Sound-Key"])
        # an edit changes the key; undo brings the cached sound back
        await self.client.post("/api/op", json={"op": "tract.set_param", "args": SET})
        r3 = await self.client.post("/api/sustained", json=body)
        self.assertNotEqual(r3.headers["X-Sound-Key"], r.headers["X-Sound-Key"])
        self.assertEqual(len(self.project.history.done), 1)  # sounds are not history


if __name__ == "__main__":
    unittest.main()
