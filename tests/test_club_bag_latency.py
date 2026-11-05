"""Promise: a saved bag remains readable while unrelated startup workers are busy."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import anyio
import httpx
from fastapi.testclient import TestClient

from ai_caddie.core import data
from ai_caddie.core import request_timing
from server_v2 import club_bag_api, main, timing_api
from server_v2.main import app
from starlette.requests import Request


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


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

    def test_worker_wait_and_execution_have_distinct_durations(self):
        async def exercise():
            clock = Clock()
            timing = request_timing.RequestTiming("fixture-queued", started=clock(), clock=clock)
            limiter = anyio.CapacityLimiter(1)
            await limiter.acquire()
            waiting = anyio.Event()
            acquire = limiter.acquire
            result = None

            async def observed_acquire():
                waiting.set()
                await acquire()

            def project(value):
                self.assertIs(request_timing.current(), timing)
                clock.advance(0.013)
                return value

            async def read():
                nonlocal result
                result = await club_bag_api.run_bag_read("bag_read_projection", project, "clubs")

            with patch.object(club_bag_api, "_read_limiter", return_value=limiter), patch.object(
                limiter, "acquire", observed_acquire,
            ), request_timing.bind(timing):
                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(read)
                    with anyio.fail_after(10):
                        await waiting.wait()
                    clock.advance(0.250)
                    limiter.release()
            self.assertEqual(result, "clubs")
            self.assertAlmostEqual(timing.marks["bag_read_projection_worker_queue"], 250)
            self.assertAlmostEqual(timing.marks["bag_read_projection"], 13)
            self.assertAlmostEqual(timing.total_ms, 263)

        asyncio.run(exercise())

    def test_bag_headers_and_records_include_authentication_and_projection(self):
        async def exercise(path, authorized):
            clock = Clock()
            records = []
            original_gate = main._enforce_request_authorization
            original_player = club_bag_api.current_player_id

            def gate(request):
                clock.advance(0.007)
                return original_gate(request)

            def player(request):
                clock.advance(0.011)
                return original_player(request)

            def project(*args, **kwargs):
                clock.advance(0.013)
                return None

            def timing(request_id):
                return request_timing.RequestTiming(request_id, started=clock(), clock=clock)

            with patch.object(main, "RequestTiming", timing), patch.object(
                main, "_enforce_request_authorization", gate,
            ), patch.object(club_bag_api, "current_player_id", player), patch.object(
                data, "load_club_bag", project,
            ), patch("ai_caddie.caddie.club_bag.load_club_bag", project), patch.object(
                data, "load_manual_club_bag", return_value=None,
            ), patch("ai_caddie.caddie.club_bag.load_manual_club_bag", return_value=None), patch.object(
                request_timing, "_enqueue_timing", records.append,
            ), patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin", "AI_CADDIE_SECURITY_PROFILE": "private"}):
                headers = {"X-AI-Caddie-Request-ID": "fixture-stages"}
                if authorized:
                    headers["X-AI-Caddie-Admin-Token"] = "fixture-admin"
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
                    response = await client.get(path, headers=headers)
            self.assertEqual(response.status_code, 200 if authorized else 401)
            self.assertEqual(response.headers["X-AI-Caddie-Request-ID"], "fixture-stages")
            self.assertEqual(len(records), 1)
            row = records[0]
            self.assertEqual(row["request_id"], "fixture-stages")
            self.assertEqual(row["stages"]["auth_gate"], 7)
            if authorized:
                self.assertEqual(row["stages"]["auth_player"], 11)
                self.assertEqual(row["stages"]["bag_read_projection"], 13)
                self.assertEqual(row["total_ms"], 31)
                self.assertIn("auth_gate;dur=7.0", response.headers["Server-Timing"])
                self.assertIn("bag_read_projection;dur=13.0", response.headers["Server-Timing"])
                for stage in ("auth_gate", "auth_player", "bag_read_projection"):
                    self.assertEqual(row["stages"][f"{stage}_worker_queue"], 0)
            else:
                self.assertNotIn("bag_read_projection", row["stages"])
                self.assertEqual(row["total_ms"], 7 if "history" in path else 18)

        for path in ("/api/v2/history/clubs/bag", "/api/v2/players/me/clubs/bag"):
            for authorized in (True, False):
                with self.subTest(path=path, authorized=authorized):
                    asyncio.run(exercise(path, authorized))

    def test_cancelled_request_is_logged_as_cancelled_not_server_failure(self):
        records = []
        request = Request({"type": "http", "method": "GET", "path": "/api/v2/players/me/clubs/bag", "headers": []})
        request.scope["route"] = SimpleNamespace(path="/api/v2/players/{player_id}/clubs/bag")

        async def cancelled(_request):
            raise asyncio.CancelledError()

        with patch.object(request_timing, "_enqueue_timing", records.append):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(main.request_timing_middleware(request, cancelled))
        self.assertEqual(records[0]["status"], 499)
        self.assertIn("cancelled", records[0]["stages"])
        self.assertNotIn("error", records[0]["stages"])


class TimingComparisonTests(unittest.TestCase):
    """Promise: request-ID pairing preserves timing boundaries and separates cancellations."""

    def test_admin_can_read_persisted_client_pair_without_changing_default_query_shape(self):
        server = {"ts": "2026-11-05T00:00:00Z", "request_id": "fixture-disk-pair", "path": "/api/v2/history/clubs/bag", "status": 200, "total_ms": 20}
        client = {**server, "client_total_ms": 120}
        with tempfile.TemporaryDirectory() as raw, patch.object(request_timing, "TIMING_ROOT", Path(raw)), patch.dict(
            os.environ, {"AI_CADDIE_ADMIN_TOKEN": "fixture-admin", "AI_CADDIE_SECURITY_PROFILE": "private"},
        ):
            directory = Path(raw) / "timing"
            directory.mkdir()
            (directory / "2026-11-05.jsonl").write_text(json.dumps(server) + "\n")
            (directory / "client-2026-11-05.jsonl").write_text(json.dumps(client) + "\n")
            api = TestClient(app)
            url = "/api/v2/admin/timing?request_id=fixture-disk-pair"
            headers = {"X-AI-Caddie-Admin-Token": "fixture-admin"}
            self.assertEqual(api.get(url).status_code, 401)
            self.assertEqual(api.get(url, headers=headers).json(), [server])
            result = api.get(url + "&include_client=true", headers=headers)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()[0]["client_timing"], {
                "outcome": "response", "client_total_ms": 120, "outside_server_timing_ms": 100,
            })
            request_timing.flush_timing_writes()

    def test_client_total_is_paired_by_id_and_route_with_signed_boundary_difference(self):
        server = {"ts": "2026-11-05T00:00:00Z", "request_id": "fixture-pair", "path": "/bag", "status": 200, "total_ms": 457.7}
        client = {**server, "client_total_ms": 5105.2}
        for error in (None, "cancelled", "url_-999", "url_-1001"):
            with self.subTest(error=error):
                row = {**client, **({"error": error} if error else {})}
                with patch.object(request_timing, "read_timing_rows", side_effect=lambda **kw: [row] if kw.get("client") else [server]):
                    result = timing_api.query_server_records(request_id="fixture-pair", include_client=True)[0]
                comparison = result["client_timing"]
                self.assertEqual(comparison["client_total_ms"], 5105.2)
                self.assertEqual(comparison["outcome"], "cancelled" if error in ("cancelled", "url_-999") else "error" if error else "response")
                if error:
                    self.assertNotIn("outside_server_timing_ms", comparison)
                else:
                    self.assertEqual(comparison["outside_server_timing_ms"], 4647.5)
                self.assertFalse(any("network" in key for key in comparison))
        negative = timing_api._client_comparison(server, [{**client, "client_total_ms": 100}])
        self.assertEqual(negative["outside_server_timing_ms"], -357.7)
        cancelled_server = timing_api._client_comparison({**server, "status": 499}, [client])
        self.assertEqual(cancelled_server["outcome"], "cancelled")
        self.assertNotIn("outside_server_timing_ms", cancelled_server)

    def test_missing_wrong_route_and_duplicate_ids_are_not_guessed(self):
        server = {"ts": "2026-11-05T00:00:00Z", "request_id": "fixture-pair", "path": "/bag", "status": 200, "total_ms": 10}
        client = {**server, "client_total_ms": 20}
        for clients, servers, outcome in (([], [server], "missing"), ([{**client, "path": "/other"}], [server], "missing"),
                                          ([client, client], [server], "ambiguous"), ([client], [server, server], "ambiguous")):
            with self.subTest(outcome=outcome), patch.object(
                request_timing, "read_timing_rows", side_effect=lambda **kw: clients if kw.get("client") else servers,
            ):
                result = timing_api.query_server_records(include_client=True)[0]
                self.assertEqual(result["client_timing"], {"outcome": outcome})
