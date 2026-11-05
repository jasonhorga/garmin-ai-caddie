"""Promise: a saved bag remains readable while unrelated startup workers are busy."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import anyio
import httpx

from ai_caddie.core import data
from server_v2.main import app


class ClubBagLatencyTests(unittest.TestCase):
    def test_saved_bags_finish_before_unrelated_worker_is_released(self):
        for path in ("/api/v2/history/clubs/bag", "/api/v2/players/me/clubs/bag"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                bag_file = root / "club_bag.json"
                bag_file.write_text(json.dumps({"clubs": [
                    {"id": 1, "clubTypeId": 1, "customName": "Fixture driver"},
                ]}))
                with patch.object(data, "DATA_DIR", root), patch.object(data, "CLUBS_BAG_FILE", bag_file), patch.dict(
                    os.environ, {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin", "AI_CADDIE_SECURITY_PROFILE": "private"},
                ):
                    asyncio.run(self._read_while_busy(path))

    async def _read_while_busy(self, path):
        limiter = anyio.to_thread.current_default_thread_limiter()
        limiter.total_tokens = 1
        entered, outcome = anyio.Event(), anyio.Event()
        release = threading.Event()
        request_done = False
        response = None

        def unrelated_startup_work():
            anyio.from_thread.run_sync(entered.set)
            if not release.wait(10):  # watchdog only; correctness uses the events below
                raise AssertionError("test did not release unrelated worker")

        original_acquire = limiter.acquire

        async def observed_acquire():
            if limiter.borrowed_tokens == limiter.total_tokens:
                outcome.set()
            await original_acquire()

        async def read():
            nonlocal request_done, response
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
                response = await client.get(path, headers={"X-AI-Caddie-Admin-Token": "fixture-admin"})
            request_done = True
            outcome.set()

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(anyio.to_thread.run_sync, unrelated_startup_work)
            await entered.wait()
            try:
                with patch.object(limiter, "acquire", observed_acquire):
                    tasks.start_soon(read)
                    with anyio.fail_after(10):
                        await outcome.wait()
                    completed_before_release = request_done
            finally:
                release.set()
        self.assertTrue(completed_before_release, "saved bag queued behind unrelated startup worker")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["found"])
        self.assertEqual(response.json()["clubs"][0]["customName"], "Fixture driver")
