import unittest

from aiohttp.test_utils import AioHTTPTestCase

from app_core.project import Project
from app_core.server import make_app

from .common import KANON, library_path

OP = {"op": "tract.set_param", "args": {"speaker": "kanon", "shape": "a", "param": "TCX", "value": 0.5}}


class Server(AioHTTPTestCase):
    async def get_application(self):
        self.project = Project()
        self.project.open_speaker(KANON, "kanon")
        return make_app(self.project)

    async def test_http_op_is_broadcast_to_every_window(self):
        a = await self.client.ws_connect("/ws")
        b = await self.client.ws_connect("/ws")
        for ws in (a, b):
            hello = await ws.receive_json()
            self.assertEqual(hello["type"], "hello")
            self.assertIn("kanon", hello["project"]["speakers"])
        r = await self.client.post("/api/op", json=OP)
        self.assertEqual((await r.json())["result"], 0.5)
        for ws in (a, b):
            ev = await ws.receive_json()
            self.assertEqual(ev["type"], "changed")
            self.assertEqual(ev["changes"][0]["value"], 0.5)
        await a.close()
        await b.close()

    async def test_websocket_requests(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()  # hello
        for v in (0.1, 0.2):
            await ws.send_json({"id": v, "kind": "op", "drag": "s", **{**OP, "args": {**OP["args"], "value": v}}})
            self.assertEqual((await ws.receive_json())["type"], "changed")
            self.assertEqual((await ws.receive_json())["result"], v)
        await ws.send_json({"id": "e", "kind": "drag_end", "drag": "s"})
        self.assertEqual((await ws.receive_json())["type"], "history")
        await ws.receive_json()
        await ws.send_json({"id": "u", "kind": "undo"})
        ev = await ws.receive_json()
        self.assertEqual((ev["source"], ev["changes"][0]["value"]), ("undo", -0.8236))
        self.assertEqual(await ws.receive_json(), {"type": "reply", "id": "u", "result": True})
        await ws.send_json({"id": "x", "kind": "op", "op": "no.such"})
        self.assertIn("error", await ws.receive_json())
        await ws.close()

    async def test_errors_are_400(self):
        r = await self.client.post("/api/op", json={**OP, "args": {**OP["args"], "shape": "zz"}})
        self.assertEqual(r.status, 400)
        self.assertIn("zz", (await r.json())["error"])

    @unittest.skipUnless(library_path().exists(), "VTL is not built")
    async def test_compute(self):
        r = await self.client.post("/api/compute", json={"speaker": "kanon", "shape": "a"})
        out = (await r.json())["result"]
        self.assertEqual(set(out), {"tube", "formants", "contours"})
        self.assertEqual(len(out["formants"]), 4)


if __name__ == "__main__":
    unittest.main()
