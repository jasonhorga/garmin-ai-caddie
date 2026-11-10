"""Light requests keep answering while heavy work holds the shared worker pool (test-plan 4.4)."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
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
from ai_caddie.courses.prep_work import checkpoint
from server_v2 import garmin_raster
from server_v2 import main as server_main
from server_v2.main import app

ADMIN = {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin", "AI_CADDIE_SECURITY_PROFILE": "private"}
BAG_PATHS = ("/api/v2/history/clubs/bag", "/api/v2/players/me/clubs/bag")


@contextmanager
def saved_bag():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        bag_file = root / "club_bag.json"
        bag_file.write_text(json.dumps({"clubs": [{"id": 1, "clubTypeId": 1, "customName": "Fixture driver"}]}))
        with patch.object(data, "DATA_DIR", root), patch.object(data, "CLUBS_BAG_FILE", bag_file), \
                patch.dict(os.environ, ADMIN):
            yield


class HeldPool:
    """Fill a limiter with workers parked on an event; report the first caller that would queue behind them."""

    def __init__(self, limiter, holders):
        self.limiter = limiter
        self.holders = holders
        self.entered = 0
        self.all_entered = anyio.Event()
        self.queued = anyio.Event()
        self.release = threading.Event()

    def _park(self):
        anyio.from_thread.run_sync(self._entered)
        if not self.release.wait(10):  # watchdog only; correctness waits on events
            raise AssertionError("test did not release the held pool")

    def _entered(self):
        self.entered += 1
        if self.entered == self.holders:
            self.all_entered.set()

    async def hold(self, tasks, run):
        for _ in range(self.holders):
            tasks.start_soon(run, self._park)
        with anyio.fail_after(10):
            await self.all_entered.wait()

    @contextmanager
    def watch_queueing(self):
        original = self.limiter.acquire

        async def observed():
            if self.limiter.borrowed_tokens >= self.limiter.total_tokens:
                self.queued.set()
            await original()

        with patch.object(self.limiter, "acquire", observed):
            yield


async def first_of(queued: anyio.Event, work):
    """Run ``work``; return (finished_first, result) where finished_first is False if it queued first."""
    outcome = anyio.Event()
    state = {"done": False, "result": None}

    async def run():
        state["result"] = await work()
        state["done"] = True
        outcome.set()

    async def relay():
        await queued.wait()
        outcome.set()

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(run)
        tasks.start_soon(relay)
        with anyio.fail_after(10):
            await outcome.wait()
        finished_first = state["done"]
        tasks.cancel_scope.cancel()
    return finished_first, state["result"]


async def bag_get(path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
        return await client.get(path, headers={"X-AI-Caddie-Admin-Token": "fixture-admin"})


async def cached_raster():
    return await garmin_raster._dispatch_raster(lambda: b"cached-hole", lambda: b"slow-render")


class LightRequests(unittest.TestCase):
    """S-31: saved-bag reads and cached hole images return while heavy work occupies the worker pool."""

    def _with_default_pool_held(self, probe):
        """Run ``probe`` while the shared pool is full; return what it observed for asserting outside the loop."""

        async def scenario():
            pool = HeldPool(anyio.to_thread.current_default_thread_limiter(), holders=1)
            pool.limiter.total_tokens = 1
            async with anyio.create_task_group() as tasks:
                await pool.hold(tasks, anyio.to_thread.run_sync)
                try:
                    with pool.watch_queueing():
                        return await probe(pool)
                finally:
                    pool.release.set()

        return asyncio.run(scenario())

    def test_light_routes_return_while_heavy_pool_held(self):
        """S-31 [main]: with the shared pool full, the saved bag and a cached hole image still return."""

        async def probe(pool):
            seen = {path: await first_of(pool.queued, lambda: bag_get(path)) for path in BAG_PATHS}
            seen["image"] = await first_of(pool.queued, cached_raster)
            return seen

        with saved_bag():
            seen = self._with_default_pool_held(probe)
        for path in BAG_PATHS:
            finished_first, response = seen[path]
            self.assertTrue(finished_first, f"{path} queued behind heavy work")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["clubs"][0]["customName"], "Fixture driver")
        finished_first, image = seen["image"]
        self.assertTrue(finished_first, "cached hole image queued behind heavy work")
        self.assertEqual(image, b"cached-hole")

    def test_concurrent_light_reads_all_return(self):
        """S-31: several saved-bag reads at once all return while the shared pool stays full."""
        responses = []

        async def append(path):
            responses.append(await bag_get(path))

        async def many():
            async with anyio.create_task_group() as tasks:
                for index in range(6):
                    tasks.start_soon(append, BAG_PATHS[index % 2])

        async def probe(pool):
            finished_first, _ = await first_of(pool.queued, many)
            return finished_first

        with saved_bag():
            finished_first = self._with_default_pool_held(probe)
        self.assertTrue(finished_first, "a concurrent bag read queued behind heavy work")
        self.assertEqual([r.status_code for r in responses], [200] * 6)

    def test_cached_image_returns_while_slow_renders_fill_their_lane(self):
        """S-31: cold hole renders filling their own lane do not hold back an image that is already cached."""

        async def scenario():
            _fast, slow = garmin_raster._http_limiters()
            pool = HeldPool(slow, holders=int(slow.total_tokens))

            async def slow_render(park):
                await anyio.to_thread.run_sync(park, limiter=slow)

            async with anyio.create_task_group() as tasks:
                await pool.hold(tasks, slow_render)
                try:
                    with pool.watch_queueing():
                        return await first_of(pool.queued, cached_raster)
                finally:
                    pool.release.set()

        finished_first, image = asyncio.run(scenario())
        self.assertTrue(finished_first, "cached hole image queued behind slow renders")
        self.assertEqual(image, b"cached-hole")

    def test_client_disconnect_cancels_heavy_work(self):
        """S-31: a client that goes away stops course prep and nearby search at the next hole, with 499."""
        routes = {
            "prep": ("/api/v2/courses/31870/prep", b"holes=1&holes=2&holes=3&render=false", "_build_course_prep_nine"),
            "nearby": ("/api/v2/courses/nearby", b"latitude=31.2&longitude=121.4", "course_nearby_endpoint"),
        }
        for name, (path, query, target) in routes.items():
            with self.subTest(name), patch.dict(os.environ, ADMIN):
                status, holes = asyncio.run(self._disconnect_during(path, query, target))
                self.assertEqual(status, 499)
                self.assertEqual(holes, [1], "heavy work kept running after the client left")

    async def _disconnect_during(self, path, query, target):
        entered, gone = asyncio.Event(), asyncio.Event()
        release, finished = threading.Event(), threading.Event()
        loop = asyncio.get_running_loop()
        holes, sent = [], []

        def build(*_args, **_kwargs):
            try:
                for hole in (1, 2, 3):
                    checkpoint()
                    holes.append(hole)
                    loop.call_soon_threadsafe(entered.set)
                    if not release.wait(10):  # watchdog only
                        raise AssertionError("test did not release the build")
                return {"holes": holes}
            finally:
                finished.set()

        requested = False

        async def receive():
            nonlocal requested
            if not requested:
                requested = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await gone.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
            "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": query,
            "root_path": "", "client": ("127.0.0.1", 50000), "server": ("localhost", 80),
            "headers": [(b"host", b"localhost"), (b"x-ai-caddie-admin-token", b"fixture-admin")],
        }
        with patch.object(server_main, target, build):
            call = asyncio.create_task(app(scope, receive, send))
            try:
                await asyncio.wait_for(entered.wait(), 10)
                gone.set()
                await asyncio.wait_for(call, 10)
            finally:
                release.set()
            await asyncio.to_thread(finished.wait, 10)
        status = next(m["status"] for m in sent if m["type"] == "http.response.start")
        return status, list(holes)


if __name__ == "__main__":
    unittest.main()
