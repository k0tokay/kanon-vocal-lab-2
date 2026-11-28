"""Gestural scores: reading and writing, the gesture operations and undo, the
saved file read back by VTL, and the tract parameters of a score."""

import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from app_core import xmltree
from app_core.project import Project, SaveRefused, meta_path
from app_core.score import SEQUENCES, Score, starts
from app_core.server import SCORE, make_app  # noqa: F401  (the server module loads)
from app_core.vtl import backend

from .common import JD2, REPO, needs_vtl, read_text

EXAMPLE = REPO / "GUI" / "example01.ges"  # VTL's example (JD2's shape names)
SMALL = REPO / "API" / "example2-input.ges"  # has empty sequences
V, L, TT, F0 = "vowel-gestures", "lip-gestures", "tongue-tip-gestures", "f0-gestures"


class Base(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.p.open_speaker(JD2, "jd2")
        self.sid = self.p.open_score(EXAMPLE)
        self.sc = self.p.scores[self.sid]
        self.text = read_text(EXAMPLE)

    def op(self, name, **args):
        return self.p.call(name, {"score": self.sid, **args})

    def undo_all(self):
        while self.p.undo():
            pass
        self.assertEqual(self.sc.text(), self.text)
        self.assertEqual(self.p.edited(self.sid), {})

    def ends(self, seq):
        gs = self.sc.sequences[seq]
        return [round(s + g[2], 6) for s, g in zip(starts(gs), gs)]


class ReadWrite(unittest.TestCase):
    def test_files_round_trip_byte_for_byte(self):
        for f in (EXAMPLE, SMALL, REPO / "API" / "example5-input.ges"):
            with self.subTest(f.name):
                self.assertEqual(Score.load(f).text(), read_text(f))

    def test_all_sequences_in_vtl_order(self):
        sc = Score.load(EXAMPLE)
        self.assertEqual([s["type"] for s in sc.to_json()["sequences"]], [s.type for s in SEQUENCES])
        self.assertAlmostEqual(sc.duration(), 2.263, places=2)

    def test_a_changed_sequence_is_written_like_vtl(self):
        sc = Score.load(EXAMPLE)
        gs = [list(g) for g in sc.sequences[L]]
        gs[0][2] += 0.01
        sc.set(("sequence", L), gs)
        lines = [ln for ln in sc.text().splitlines() if "ll-" in ln or 'value=""' in ln]
        self.assertTrue(all(ln.startswith("    <gesture value=") and ln.endswith(" />") for ln in lines))
        self.assertEqual(Score(xmltree.parse(sc.text())).sequences[L], sc.sequences[L])


class Operations(Base):
    def test_boundary_moves_only_the_two_gestures(self):
        before = self.ends(V)
        t = self.op("gesture.set_boundary", sequence=V, index=2, time=before[2] + 0.02)
        after = self.ends(V)
        self.assertAlmostEqual(after[2], t, places=6)
        self.assertEqual(after[3:], before[3:])  # the rest keeps its times
        self.assertEqual(after[:2], before[:2])
        self.undo_all()

    def test_a_drag_is_one_step(self):
        e = self.ends(V)[0]
        for k in range(5):
            self.p.call("gesture.set_boundary", {"score": self.sid, "sequence": V, "index": 0,
                                                  "time": e + 0.005 * k}, drag="d1")
        self.p.end_drag("d1")
        self.assertEqual(len(self.p.history.done), 1)
        self.assertAlmostEqual(self.ends(V)[0], e + 0.02, places=6)
        self.undo_all()

    def test_boundary_keeps_a_millisecond(self):
        before = self.ends(V)
        self.op("gesture.set_boundary", sequence=V, index=0, time=-1)
        self.assertAlmostEqual(self.ends(V)[0], 0.001, places=6)
        self.op("gesture.set_boundary", sequence=V, index=0, time=99)
        self.assertAlmostEqual(self.ends(V)[0], before[1] - 0.001, places=6)
        self.assertEqual(self.ends(V)[1:], before[1:])
        self.undo_all()

    def test_set_value_time_constant_and_neutral_clamped(self):
        g = self.op("gesture.set", sequence=F0, index=0, value=500, time_constant=1, slope=-999)
        self.assertEqual(g[0], "108.000000")
        self.assertEqual((g[1], g[3]), (-200.0, 0.04))
        g = self.op("gesture.set", sequence=V, index=1, value="i", neutral=True)
        self.assertEqual((g[0], g[4]), ("i", 1))
        with self.assertRaises(ValueError):
            self.op("gesture.set", sequence=V, index=1, value='a"b')
        self.undo_all()

    def test_split_delete_add_keep_the_other_times(self):
        before = self.ends(TT)
        n = len(self.sc.sequences[TT])
        mid = (before[0] + before[1]) / 2
        k = self.op("gesture.split", sequence=TT, time=mid)
        self.assertEqual(k, 2)
        self.assertEqual(len(self.sc.sequences[TT]), n + 1)
        self.op("gesture.delete", sequence=TT, index=2)
        self.assertEqual(self.ends(TT), before)  # the time went back to the one before
        i = self.op("gesture.add", sequence=TT, time=mid, duration=0.02)
        g = self.sc.sequences[TT][i]
        self.assertEqual((g[0], g[4]), ("", 1))  # a new shape gesture is neutral
        self.assertEqual(self.ends(TT)[-1], before[-1])
        self.assertEqual(len(self.p.history.done), 3)
        self.undo_all()

    def test_the_last_gesture_stays_and_adding_after_the_end(self):
        p = Project()
        sid = p.open_score(SMALL)
        sc = p.scores[sid]
        with self.assertRaises(ValueError):
            p.ops.gesture.delete(score=sid, sequence=V, index=0)
        p.ops.gesture.add(score=sid, sequence=L, time=0.2, duration=0.05, value="ll-labial-closure")
        self.assertEqual([g[4] for g in sc.sequences[L]], [1, 0])  # a pause, then the gesture
        self.assertAlmostEqual(starts(sc.sequences[L])[1], 0.2, places=6)
        while p.undo():
            pass
        self.assertEqual(sc.text(), read_text(SMALL))

    def test_marks_and_project_json(self):
        self.op("gesture.set", sequence=V, index=0, duration=0.3)
        j = self.p.to_json()["scores"][self.sid]
        self.assertTrue(j["modified"])
        self.assertEqual([e["address"] for e in j["edited"]], [["sequence", V]])
        self.assertEqual(len(j["sequences"]), 8)
        self.undo_all()


class Files(Base):
    def test_save_writes_the_score_and_its_log(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "s.ges"
            shutil.copyfile(EXAMPLE, f)
            p = Project()
            sid = p.open_score(f)
            p.ops.gesture.set(score=sid, sequence=V, index=0, value="a")
            out = p.save_score(sid)
            self.assertEqual(out, f)
            self.assertFalse(p.is_modified(sid))
            self.assertIn('value="a"', read_text(f))
            self.assertTrue(meta_path(f).name == "s.ges.meta.json" and meta_path(f).exists())
            # save as: .ges added, an existing file only with overwrite, protected names never
            self.assertEqual(p.save_score(sid, "t").name, "t.ges")
            with self.assertRaises(SaveRefused):
                p.save_score(sid, f)
            (Path(d) / "x-manual-edit.ges").write_text("x")
            with self.assertRaises(SaveRefused):
                p.save_score(sid, Path(d) / "x-manual-edit.ges", overwrite=True)

    def test_opening_another_score(self):
        self.op("gesture.set", sequence=V, index=0, duration=0.3)
        with self.assertRaises(ValueError):
            self.p.open_score(SMALL)
        sid = self.p.open_score(SMALL, discard=True)
        self.assertEqual(list(self.p.scores), [sid])
        self.assertEqual(self.p.history.done, [])  # the old score's steps are gone
        self.assertFalse(self.p.undo())


@needs_vtl
class WithVTL(Base):
    def test_vtl_reads_the_saved_score_back(self):
        self.op("gesture.split", sequence=V, time=0.5)
        self.op("gesture.set_boundary", sequence=TT, index=1, time=0.45)
        self.op("gesture.set", sequence=F0, index=3, value=90.5, slope=10)
        self.op("gesture.add", sequence=L, time=0.6, duration=0.05, value="ll-labial-closure")
        with tempfile.TemporaryDirectory() as d:
            f = self.p.save_score(self.sid, Path(d) / "edited.ges")
            sp = self.p.speakers["jd2"]
            b = backend()
            # VTL writes back what it read: the same gestures, so the same tract parameters
            again = Score.load(f)
            self.assertEqual(again.sequences, self.sc.sequences)
            p1 = b.score_tract_params(sp, read_text(f))
            p2 = b.score_tract_params(sp, self.sc.text())
            np.testing.assert_array_equal(p1, p2)
            x, sr = b.score_audio(sp, read_text(f), again.duration())
            self.assertAlmostEqual(len(x) / sr, again.duration(), delta=0.05)
            self.assertGreater(np.max(np.abs(x)), 0.01)

    def test_tract_params_are_those_of_the_synthesis(self):
        sp = self.p.speakers["jd2"]
        b = backend()
        seq = b.score_tract_params(sp, self.sc.text(), 200.0)
        self.assertEqual(seq.shape, (int(self.sc.duration() * 200) + 1, b.num_tract_params))
        # VTL's own tube sequence of the score (a state every 2.5 ms): the area function
        # of our parameters at the same time is the same
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "tubes.txt"
            self.assertEqual(b.L.vtlGesturalScoreToTubeSequence(str(b._score_file(self.sc.text())).encode(),
                                                                 str(f).encode()), 0)
            rows = [ln for ln in f.read_text().splitlines() if not ln.startswith("#")][4:]
        for k in (40, 150, 300, 420):
            vtl_area = np.array(rows[5 * (2 * k) + 2].split(), dtype=float)
            np.testing.assert_allclose(b.tube(sp, seq[k]).area_cm2, vtl_area, atol=1e-3)
        gs = self.sc.sequences[V]
        st = starts(gs)
        i = 3
        # the server's answer at a time: the parameters, the tube and the contours
        r = SCORE.tract(self.p, {"speaker": "jd2", "score": self.sid, "time": st[i] + gs[i][2] * 0.8})
        self.assertEqual(len(r["params"]), b.num_tract_params)
        self.assertIn("tongue", r["contours"])

    def test_sound_view_and_cache(self):
        req = {"speaker": "jd2", "score": self.sid}
        wav, view = SCORE.sound(self.p, req)
        self.assertEqual(wav[:4], b"RIFF")
        self.assertAlmostEqual(view["duration"], self.sc.duration(), delta=0.05)
        self.assertGreater(view["spectrogram"]["frames"], 100)
        self.assertIs(SCORE.sound(self.p, req)[0], wav)  # cached
        self.op("gesture.set", sequence=F0, index=0, value=80)
        self.assertNotEqual(SCORE.sound(self.p, req)[1]["key"], view["key"])  # an edit: a new sound
        self.undo_all()


if __name__ == "__main__":
    unittest.main()
