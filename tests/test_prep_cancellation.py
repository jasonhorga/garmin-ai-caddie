import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
from unittest.mock import patch

import httpx
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from ai_caddie.courses import course_prep, course_reference, prep_cache
from ai_caddie.courses.prep_work import checkpoint, cancellation, PrepCancelled
from server_v2.main import app
from server_v2.prep_work import run_prep


class Request:
    async def receive(self):
        await asyncio.Future()  # Connected client; cancelled when the request worker finishes.


class NonCancellableReceive:
    """Model BaseHTTPMiddleware's receive proxy while its outer response is still open."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.allow_build = threading.Event()
        self.release = asyncio.Event()
        self.finished = asyncio.Event()

    async def receive(self):
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            # The proxy does not finish cancellation until the response owner closes it.
            await self.release.wait()
            raise
        finally:
            self.finished.set()


class PrepCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_after_worker_done_is_not_reported_as_cancellation(self):
        built = threading.Event()

        class CompletedThenDisconnected:
            async def receive(self):
                await asyncio.to_thread(built.wait)
                await asyncio.sleep(0)
                return {"type": "http.disconnect"}

        with patch("server_v2.prep_work.mark") as mark:
            def build():
                built.set()
                return Response(status_code=200)

            response = await asyncio.wait_for(run_prep(CompletedThenDisconnected(), build), 1)

        self.assertEqual(response.status_code, 200)
        mark.assert_not_called()

    async def test_completed_prep_does_not_wait_for_receive_proxy_cancellation(self):
        request = NonCancellableReceive()

        def build():
            self.assertTrue(request.allow_build.wait(2))
            return Response(status_code=200)

        task = asyncio.create_task(run_prep(request, build))
        self.assertTrue(await asyncio.to_thread(request.started.wait, 2))
        request.allow_build.set()
        try:
            response = await asyncio.wait_for(asyncio.shield(task), 1)
            self.assertEqual(response.status_code, 200)
        finally:
            request.release.set()
            await asyncio.wait_for(request.finished.wait(), 1)
            await task

    async def test_concurrent_http_requests_and_cache_hit_build_once(self):
        prep_cache.clear()
        self.addCleanup(prep_cache.clear)
        entered, release = threading.Event(), threading.Event()

        def build(*args, **kwargs):
            entered.set()
            if not release.wait(2):
                raise AssertionError("test did not release builder")
            return [dict(hole=1, par=4)]

        with (patch.object(course_reference, "courseview_release_info", return_value=None),
              patch.object(course_prep, "effective_club_ladder", return_value=[]),
              patch.object(course_prep, "club_ladder_with_provenance", return_value=[]),
              patch.object(course_prep, "prep_nine", side_effect=build) as nine):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
                url = "/api/v2/courses/31795/prep?holes=1&render=false"
                first = asyncio.create_task(client.get(url))
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                second = asyncio.create_task(client.get(url))
                await asyncio.sleep(.1)
                release.set()
                results = await asyncio.wait_for(asyncio.gather(first, second), 3)
                third = await client.get(url)
            self.assertEqual([r.status_code for r in [*results, third]], [200, 200, 200])
            self.assertEqual(results[0].json(), third.json())
            self.assertEqual(nine.call_count, 1)

    async def test_disconnect_stops_before_next_hole(self):
        disconnected = asyncio.Event()

        async def receive():
            await disconnected.wait()
            return {"type": "http.disconnect"}

        request = StarletteRequest({"type": "http", "headers": []}, receive=receive)
        entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
        holes = []

        def build():
            try:
                for hole in (1, 2, 3):
                    checkpoint()
                    holes.append(hole)
                    entered.set()
                    release.wait(2)
            finally:
                stopped.set()

        task = asyncio.create_task(run_prep(request, build))
        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
        disconnected.set()
        response = await asyncio.wait_for(task, 1)
        self.assertEqual(response.status_code, 499)
        release.set()
        self.assertTrue(await asyncio.to_thread(stopped.wait, 2))
        self.assertEqual(holes, [1])

    async def test_client_timeout_signals_builder(self):
        entered, stopped = threading.Event(), threading.Event()

        def build():
            try:
                entered.set()
                while True:
                    checkpoint()
                    stopped.wait(.01)
            finally:
                stopped.set()

        task = asyncio.create_task(run_prep(Request(), build))
        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(task, .05)
        self.assertTrue(await asyncio.to_thread(stopped.wait, 2))

    async def test_cancelled_singleflight_waiter_leaves_leader_usable(self):
        prep_cache.clear()
        self.addCleanup(prep_cache.clear)
        entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
        cancelled = threading.Event()
        args = dict(global_id=31795, requested=[1], render=False, include_shots=False, player_id="me")

        def build():
            entered.set()
            release.wait(2)
            return {"ready": True}

        def waiter():
            with cancellation(cancelled):
                waiting.set()
                return prep_cache.cached_course_prep(build=build, **args)

        with ThreadPoolExecutor(2) as pool:
            leader = pool.submit(prep_cache.cached_course_prep, build=build, **args)
            self.assertTrue(entered.wait(2))
            follower = pool.submit(waiter)
            self.assertTrue(waiting.wait(2))
            cancelled.set()
            try:
                with self.assertRaises(PrepCancelled):
                    follower.result(timeout=1)
            finally:
                release.set()
            self.assertEqual(leader.result(timeout=2), {"ready": True})
        self.assertEqual(prep_cache.cached_course_prep(build=lambda: self.fail("cache miss"), **args), {"ready": True})
