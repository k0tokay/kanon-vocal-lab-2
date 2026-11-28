"""The local server: operations in, change notifications out.

    python -m app_core.server --speaker ../speakers/JD2.speaker [--score foo.ges] [--port 8765]

The data lives here only. A screen (or any client) sends operations and
receives every change as a notification over the WebSocket, so several
windows stay in sync. Listens on 127.0.0.1 only.

HTTP
    GET  /api/project                      the whole project (speakers, history, operations)
    POST /api/op        {op, args, drag?}  run an operation -> {result}
    POST /api/drag_end  {drag}             close the undo step of a drag
    POST /api/undo, /api/redo
    POST /api/save      {speaker | score, path?, overwrite?}
                        -> {result: {ok: true, path}} or {result: {ok: false, reason, path}}
                           reason: protected | versioned | exists (see project.save_refusal)
    POST /api/open_score {path, discard?}  open a `.ges` in place of the open score
    POST /api/score_sound {score, speaker} -> the score synthesized: {key, duration,
                        sampling_rate, envelope, spectrogram} (one synthesis at a time;
                        an older request still waiting gives up: "superseded")
    GET  /api/score_wav?key=...            that sound as audio/wav
    POST /api/score_tract {score, speaker, time} -> the vocal tract at `time`:
                        {params, tube, contours} (from the score's tract parameters)
    POST /api/sustained {speaker, shape | params, glottis_shape?, duration?}  -> audio/wav (a held vowel)
    POST /api/glottis_wave {speaker, tract_shape, glottis_shape, duration?}
                        -> a few periods of glottal area, glottal flow and output, and f0
    POST /api/compute   {speaker, shape | params, what?: [tube, formants, spectrum, contours]}

WebSocket /ws
    server -> client: {"type": "hello", "project": ...} first, then every event
    client -> server: {"id": ..., "kind": "op" | "drag_end" | "undo" | "redo" | "compute", ...}
                      answered by {"type": "reply", "id": ..., "result" | "error": ...}
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import threading
import traceback
from collections import OrderedDict
from pathlib import Path

import numpy as np
from aiohttp import WSMsgType, web

from .names import APP_NAME
from .project import Project, SaveRefused
from .vtl import Backend, backend, glottis_vector, wav_bytes

COMPUTE_ALL = ("tube", "formants", "contours")
PLAY_GAIN = 8.0  # VTL's output peaks near 0.1; one fixed gain keeps shapes comparable


def compute(project: Project, req: dict) -> dict:
    sp = project.speakers[req["speaker"]]
    params = req.get("params") or req["shape"]
    what = req.get("what") or COMPUTE_ALL
    b = backend()
    out: dict = {}
    if "tube" in what:
        out["tube"] = b.tube(sp, params).to_json()
    if "formants" in what:
        out["formants"] = b.formants(sp, params)
    if "spectrum" in what:
        f, mag, _ = b.spectrum(sp, params, int(req.get("n", 2048)))
        keep = f <= float(req.get("fmax", f[-1]))
        out["spectrum"] = {"freq": f[keep].tolist(), "magnitude": mag[keep].tolist()}
    if "contours" in what:
        out["contours"] = {k: v.tolist() for k, v in b.contours(sp, params).items()}
    return out


def glottis_wave(project: Project, req: dict) -> dict:
    sp = project.speakers[req["speaker"]]
    w = backend().glottis_wave(sp, req["tract_shape"], req.get("glottis_shape") or "modal",
                               min(max(float(req.get("duration", 0.3)), 0.1), 1.0))
    return {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in w.items()}


def handle(project: Project, msg: dict):
    """One request, shared by HTTP and WebSocket."""
    kind = msg["kind"]
    if kind == "op":
        return project.call(msg["op"], msg.get("args") or {}, drag=msg.get("drag"))
    if kind == "drag_end":
        return project.end_drag(msg["drag"])
    if kind == "undo":
        return project.undo()
    if kind == "redo":
        return project.redo()
    if kind == "open_score":
        return project.open_score(Path(msg["path"]).expanduser(), discard=bool(msg.get("discard")))
    if kind == "save":
        try:
            doc = msg.get("score") or msg["speaker"]
            out = project.save_speaker(doc, msg.get("path"), overwrite=bool(msg.get("overwrite")))
        except SaveRefused as e:
            return {"ok": False, "reason": e.reason, "path": str(e.path)}
        return {"ok": True, "path": str(out)}
    if kind == "compute":
        return compute(project, msg)
    if kind == "glottis_wave":
        return glottis_wave(project, msg)
    if kind == "score_sound":
        return SCORE.sound(project, msg)[1]
    if kind == "score_tract":
        return SCORE.tract(project, msg)
    if kind == "project":
        return project.to_json()
    raise KeyError(f"unknown request kind {kind!r}")


class SoundCache:
    """Synthesized sounds by what they depend on: the speaker's anatomy and glottis
    models, the tract parameters, the glottis shape and the duration. View data:
    never part of the history."""

    def __init__(self, size: int = 32):
        self.size = size
        self.items: OrderedDict[str, bytes] = OrderedDict()

    @staticmethod
    def key(project: Project, req: dict) -> str:
        sp = project.speakers[req["speaker"]]
        params = req.get("params") or sp.tract_shape(req["shape"])
        h = hashlib.sha256(Backend._key_of(sp).encode())
        g = req.get("glottis_shape") or "modal"
        h.update(json.dumps([list(map(float, params)), g, glottis_vector(sp, g),
                             float(req.get("duration", 1.0))]).encode())
        return h.hexdigest()

    def get(self, k: str) -> bytes | None:
        if k in self.items:
            self.items.move_to_end(k)
        return self.items.get(k)

    def put(self, k: str, v: bytes) -> None:
        self.items[k] = v
        while len(self.items) > self.size:
            self.items.popitem(last=False)


def sustained_wav(project: Project, req: dict) -> bytes:
    sp = project.speakers[req["speaker"]]
    params = req.get("params") or req["shape"]
    duration = min(max(float(req.get("duration", 1.0)), 0.1), 5.0)
    x, sr = backend().sustained(sp, params, duration, req.get("glottis_shape") or "modal")
    return wav_bytes(x * PLAY_GAIN, sr)


class Superseded(Exception):
    """A synthesis that gave up because a newer one was asked for."""


class ScoreWork:
    """Sounds and tract parameter sequences of gestural scores, cached by what they
    depend on (the whole speaker text and the score text). View data: never part
    of the history. Synthesis runs one at a time; a request still waiting when a
    newer one for the same score arrives gives up."""

    def __init__(self, size: int = 8):
        self.size = size
        self.sounds: OrderedDict[str, tuple[bytes, dict]] = OrderedDict()
        self.params: OrderedDict[str, np.ndarray] = OrderedDict()
        self.synth = threading.Lock()
        self.latest: dict[str, int] = {}
        self.counter = 0
        self.guard = threading.Lock()

    @staticmethod
    def key(project: Project, req: dict) -> str:
        sp = project.speakers[req["speaker"]]
        sc = project.scores[req["score"]]
        return hashlib.sha256((sp.text() + "\0" + sc.text()).encode()).hexdigest()

    def _put(self, cache: OrderedDict, k: str, v) -> None:
        cache[k] = v
        cache.move_to_end(k)
        while len(cache) > self.size:
            cache.popitem(last=False)

    def sound(self, project: Project, req: dict) -> tuple[bytes, dict]:
        k = self.key(project, req)
        if k in self.sounds:
            self.sounds.move_to_end(k)
            return self.sounds[k]
        with self.guard:
            self.counter += 1
            me = self.latest[req["score"]] = self.counter
        with self.synth:
            if k in self.sounds:
                return self.sounds[k]
            if self.latest.get(req["score"]) != me:
                raise Superseded("superseded")
            sp = project.speakers[req["speaker"]]
            sc = project.scores[req["score"]]
            x, sr = backend().score_audio(sp, sc.text(), sc.duration())
            out = (wav_bytes(x * SCORE_GAIN, sr), sound_view(x, sr) | {"key": k})
            self._put(self.sounds, k, out)
            return out

    def wav(self, k: str) -> bytes | None:
        v = self.sounds.get(k)
        return v[0] if v else None

    def tract(self, project: Project, req: dict) -> dict:
        k = self.key(project, req)
        sp = project.speakers[req["speaker"]]
        if k not in self.params:
            self._put(self.params, k, backend().score_tract_params(sp, project.scores[req["score"]].text(),
                                                                  TRACT_RATE))
        seq = self.params[k]
        # between two frames: linear (the frames are 5 ms apart)
        x = min(max(float(req["time"]), 0.0), (len(seq) - 1) / TRACT_RATE) * TRACT_RATE
        i = min(int(x), len(seq) - 2) if len(seq) > 1 else 0
        a = x - i
        params = seq[i] * (1 - a) + seq[min(i + 1, len(seq) - 1)] * a
        out = compute(project, {"speaker": req["speaker"], "params": params.tolist(),
                                "what": ["tube", "contours"]})
        return out | {"params": params.tolist(), "time": x / TRACT_RATE}


TRACT_RATE = 200.0  # frames per second of the tract parameter sequence
SCORE_GAIN = 2.0  # speech from a score peaks near 0.3; wav_bytes scales down what would clip


def sound_view(x: np.ndarray, sr: int, fmax: float = 8000.0) -> dict:
    """What the screen draws of a sound: the envelope (min and max per 2 ms, int8)
    and a spectrogram (5 ms hop, 20 ms Hann window, 0-fmax in 96 bands, 70 dB in uint8),
    both base64."""
    b = int(sr * 0.002)
    n = len(x) // b
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    scale = 127 / peak if peak > 0 else 0.0
    e = x[: n * b].reshape(n, b) if n else np.zeros((0, b))
    env = np.stack([e.min(1), e.max(1)], 1) * scale if n else np.zeros((0, 2))
    env = np.clip(np.round(env), -127, 127).astype(np.int8)
    hop, win, nfft, bands = int(sr * 0.005), int(sr * 0.02), 4096, 96
    w = np.hanning(win)
    top = int(fmax / sr * nfft)
    top -= top % bands
    frames = []
    for i in range(0, max(0, len(x) - win), hop):
        S = np.abs(np.fft.rfft(x[i:i + win] * w, nfft))[:top].reshape(bands, -1).mean(1)
        frames.append(20 * np.log10(S + 1e-12))
    spec = np.array(frames) if frames else np.zeros((0, bands))
    hi = spec.max() if spec.size else 0.0
    spec = np.clip((spec - (hi - 70)) / 70 * 255, 0, 255).astype(np.uint8)
    enc = lambda a: base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()  # noqa: E731
    return {
        "sampling_rate": sr, "duration": len(x) / sr,
        "envelope": {"data": enc(env), "count": int(n), "step": b / sr},
        "spectrogram": {"data": enc(spec), "frames": len(spec), "bands": bands, "step": hop / sr,
                        "start": win / 2 / sr, "fmax": top * sr / nfft},
    }


SCORE = ScoreWork()


def _error(e: Exception) -> dict:
    return {"error": f"{type(e).__name__}: {e}"}


def make_app(project: Project) -> web.Application:
    app = web.Application()
    clients: set[asyncio.Queue] = set()

    def broadcast(event: dict) -> None:
        for q in clients:
            q.put_nowait(event)

    project.subscribe(broadcast)

    def route(kind: str):
        async def h(request: web.Request) -> web.Response:
            body = await request.json() if request.can_read_body else {}
            try:
                result = handle(project, {**body, "kind": kind})
            except Exception as e:  # noqa: BLE001  (reported to the client)
                return web.json_response(_error(e), status=400)
            return web.json_response({"result": result})
        return h

    async def get_project(request: web.Request) -> web.Response:
        return web.json_response(project.to_json())

    sounds = SoundCache()

    async def sustained(request: web.Request) -> web.Response:
        try:
            req = await request.json()
            k = SoundCache.key(project, req)
            data = sounds.get(k)
            if data is None:
                # VTL takes about as long as the sound; keep the WebSocket answering meanwhile
                data = await asyncio.get_running_loop().run_in_executor(None, sustained_wav, project, req)
                sounds.put(k, data)
        except Exception as e:  # noqa: BLE001
            return web.json_response(_error(e), status=400)
        return web.Response(body=data, content_type="audio/wav", headers={"X-Sound-Key": k})

    async def ws_handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        q: asyncio.Queue = asyncio.Queue()
        q.put_nowait({"type": "hello", "app": APP_NAME, "project": project.to_json()})
        clients.add(q)

        async def sender():
            while True:
                await ws.send_json(await q.get())

        task = asyncio.create_task(sender())
        tasks: set[asyncio.Task] = set()

        async def compute_reply(msg: dict) -> None:
            try:
                r = await asyncio.get_running_loop().run_in_executor(None, handle, project, msg)
                q.put_nowait({"type": "reply", "id": msg.get("id"), "result": r})
            except Exception as e:  # noqa: BLE001
                q.put_nowait({"type": "reply", "id": msg.get("id"), **_error(e)})
        try:
            async for m in ws:
                if m.type != WSMsgType.TEXT:
                    continue
                try:
                    msg = json.loads(m.data)
                    if msg.get("kind") in ("compute", "glottis_wave", "score_sound", "score_tract"):
                        # off the event loop: a synthesis may hold VTL for a second
                        tasks.add(t := asyncio.create_task(compute_reply(msg)))
                        t.add_done_callback(tasks.discard)
                        continue
                    reply = {"type": "reply", "id": msg.get("id"), "result": handle(project, msg)}
                except Exception as e:  # noqa: BLE001
                    reply = {"type": "reply", "id": msg.get("id") if isinstance(msg, dict) else None,
                             **_error(e)}
                    if not isinstance(e, (KeyError, ValueError, TypeError)):
                        traceback.print_exc()
                q.put_nowait(reply)  # after the events this request caused
        finally:
            clients.discard(q)
            task.cancel()
        return ws

    app.router.add_get("/api/project", get_project)
    for kind in ("op", "drag_end", "undo", "redo", "save", "open_score", "compute", "glottis_wave",
                 "score_sound", "score_tract"):
        app.router.add_post(f"/api/{kind}", route(kind))
    app.router.add_post("/api/sustained", sustained)

    async def score_wav(request: web.Request) -> web.Response:
        data = SCORE.wav(request.query.get("key", ""))
        if data is None:
            return web.json_response({"error": "no such sound (synthesize it first)"}, status=404)
        return web.Response(body=data, content_type="audio/wav")
    app.router.add_get("/api/score_wav", score_wav)
    app.router.add_get("/ws", ws_handler)

    # The built screen (`npm run build` in app/web). In development Vite serves
    # it instead and forwards /api and /ws here.
    dist = Path(__file__).resolve().parents[1] / "web" / "dist"
    if (dist / "index.html").exists():
        async def index(request: web.Request) -> web.FileResponse:
            return web.FileResponse(dist / "index.html")
        app.router.add_get("/", index)
        app.router.add_static("/assets", dist / "assets")
    return app


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=f"{APP_NAME}: local server")
    ap.add_argument("--speaker", action="append", default=[], metavar="[ID=]PATH",
                    help="open a .speaker file (repeatable)")
    ap.add_argument("--score", metavar="PATH", help="open a gestural score (.ges)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    project = Project()
    for s in a.speaker:
        sid, _, path = s.rpartition("=")
        print("opened", project.open_speaker(Path(path), sid or None))
    if a.score:
        print("opened", project.open_score(Path(a.score)))
    web.run_app(make_app(project), host=a.host, port=a.port)


if __name__ == "__main__":
    main()
