"""The local server: operations in, change notifications out.

    python -m app_core.server --speaker ../speakers/JD2.speaker [--port 8765]

The data lives here only. A screen (or any client) sends operations and
receives every change as a notification over the WebSocket, so several
windows stay in sync. Listens on 127.0.0.1 only.

HTTP
    GET  /api/project                      the whole project (speakers, history, operations)
    POST /api/op        {op, args, drag?}  run an operation -> {result}
    POST /api/drag_end  {drag}             close the undo step of a drag
    POST /api/undo, /api/redo
    POST /api/save      {speaker, path?, overwrite?}
                        -> {result: {ok: true, path}} or {result: {ok: false, reason, path}}
                           reason: protected | versioned | exists (see project.save_refusal)
    POST /api/sustained {speaker, shape | params, duration?}  -> audio/wav (a held vowel)
    POST /api/compute   {speaker, shape | params, what?: [tube, formants, spectrum, contours]}

WebSocket /ws
    server -> client: {"type": "hello", "project": ...} first, then every event
    client -> server: {"id": ..., "kind": "op" | "drag_end" | "undo" | "redo" | "compute", ...}
                      answered by {"type": "reply", "id": ..., "result" | "error": ...}
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import traceback
from collections import OrderedDict
from pathlib import Path

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
    if kind == "save":
        try:
            out = project.save_speaker(msg["speaker"], msg.get("path"), overwrite=bool(msg.get("overwrite")))
        except SaveRefused as e:
            return {"ok": False, "reason": e.reason, "path": str(e.path)}
        return {"ok": True, "path": str(out)}
    if kind == "compute":
        return compute(project, msg)
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
        h.update(json.dumps([list(map(float, params)), glottis_vector(sp), float(req.get("duration", 1.0))]).encode())
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
    x, sr = backend().sustained(sp, params, duration)
    return wav_bytes(x * PLAY_GAIN, sr)


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
                r = await asyncio.get_running_loop().run_in_executor(None, compute, project, msg)
                q.put_nowait({"type": "reply", "id": msg.get("id"), "result": r})
            except Exception as e:  # noqa: BLE001
                q.put_nowait({"type": "reply", "id": msg.get("id"), **_error(e)})
        try:
            async for m in ws:
                if m.type != WSMsgType.TEXT:
                    continue
                try:
                    msg = json.loads(m.data)
                    if msg.get("kind") == "compute":
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
    for kind in ("op", "drag_end", "undo", "redo", "save", "compute"):
        app.router.add_post(f"/api/{kind}", route(kind))
    app.router.add_post("/api/sustained", sustained)
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
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    project = Project()
    for s in a.speaker:
        sid, _, path = s.rpartition("=")
        print("opened", project.open_speaker(Path(path), sid or None))
    web.run_app(make_app(project), host=a.host, port=a.port)


if __name__ == "__main__":
    main()
