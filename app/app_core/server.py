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
    POST /api/save      {speaker, path?}
    POST /api/compute   {speaker, shape | params, what?: [tube, formants, spectrum, contours]}

WebSocket /ws
    server -> client: {"type": "hello", "project": ...} first, then every event
    client -> server: {"id": ..., "kind": "op" | "drag_end" | "undo" | "redo" | "compute", ...}
                      answered by {"type": "reply", "id": ..., "result" | "error": ...}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import traceback
from pathlib import Path

from aiohttp import WSMsgType, web

from .names import APP_NAME
from .project import Project
from .vtl import backend

COMPUTE_ALL = ("tube", "formants", "contours")


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
        out["spectrum"] = {"freq": f.tolist(), "magnitude": mag.tolist()}
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
        return str(project.save_speaker(msg["speaker"], msg.get("path")))
    if kind == "compute":
        return compute(project, msg)
    if kind == "project":
        return project.to_json()
    raise KeyError(f"unknown request kind {kind!r}")


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
        try:
            async for m in ws:
                if m.type != WSMsgType.TEXT:
                    continue
                try:
                    msg = json.loads(m.data)
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
    app.router.add_get("/ws", ws_handler)
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
