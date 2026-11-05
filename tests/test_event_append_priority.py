"""J4.2/J5.9: saving a stroke gets the same CPU priority as opening a round."""
import asyncio
import threading
import unittest
from unittest.mock import patch

from ai_caddie.core import priority_work
from server_v2.package_admission import PackageAdmissionMiddleware


class EventAppendPriorityTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_receipt_precedes_new_background_cpu_work(self):
        await self._assert_foreground_response("POST", "/api/v2/mobile/rounds/fixture/events")

    async def test_history_replay_precedes_new_background_cpu_work(self):
        await self._assert_foreground_response("GET", "/api/v2/mobile/rounds/fixture/events/replay")

    async def _assert_foreground_response(self, method, path):
        gate = priority_work.ForegroundGate()
        decided, completed = threading.Event(), threading.Event()
        real_wait = gate._condition.wait
        worker = None
        order = []

        def wait(timeout=None):
            decided.set()
            return real_wait(timeout)

        def background():
            with priority_work.background_work(unit_type="fixture"):
                order.append("background")
                decided.set()
            completed.set()

        async def app(scope, receive, send):
            nonlocal worker
            worker = asyncio.create_task(asyncio.to_thread(background))
            self.assertTrue(await asyncio.to_thread(decided.wait, 5), "background made no admission decision")
            self.assertFalse(completed.is_set(), "background CPU ran before the durable receipt")
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"receipt"})

        async def receive():
            await asyncio.Event().wait()

        async def send(message):
            if message["type"] == "http.response.body":
                order.append("receipt")

        with patch.object(priority_work, "FOREGROUND_GATE", gate), patch.object(gate._condition, "wait", wait):
            try:
                await PackageAdmissionMiddleware(app)(
                    {"type": "http", "method": method, "path": path}, receive, send)
            finally:
                if worker is not None:
                    await asyncio.wait_for(worker, 5)
        self.assertEqual(order, ["receipt", "background"])
        self.assertEqual(gate.foreground_count, 0)
