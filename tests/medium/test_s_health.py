"""Deploy health, readiness warming, abandoned-request logging, and missing weather.

Entry points are the real HTTP routes of ``server_v2.main:app`` (TestClient, or the raw ASGI
callable when a client must vanish mid-body).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.core import request_timing
from ai_caddie.history import stats_cache
from ai_caddie.llm import weather_context
from server_v2 import history_stats, readiness
from server_v2 import weather as weather_api
from server_v2.main import app

DEPLOYED_SHA = "3f9c2b7e8d41a6c05b9e7f12d4a8c6e0b1f2a3d4"
JOIN_GUARD_S = 20.0

_STATS_DICTS = (
    "_cache",
    "_aux_cache",
    "_cache_source_revisions",
    "_CORRECTED_CACHE",
    "_load_cache",
    "_load_inflight",
    "_inflight",
)


def _pop_env(case: unittest.TestCase, *names: str) -> None:
    patcher = mock.patch.dict(os.environ)
    patcher.start()
    case.addCleanup(patcher.stop)
    for name in names:
        os.environ.pop(name, None)


def _ready_sync_status(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(
        connector=SimpleNamespace(name="garmin_cn", state="ready"),
        snapshot=SimpleNamespace(
            scorecardCount=1,
            shotFileCount=1,
            lastSuccessfulSyncAt=None,
            geometryReadyCount=1,
            geometryDependencyCount=1,
            geometryMissingCount=0,
        ),
        lastRun=None,
    )


def _check(payload: dict[str, Any], label: str) -> dict[str, Any]:
    matches = [check for check in payload["checks"] if check["label"] == label]
    if len(matches) != 1:
        raise AssertionError(f"expected one {label!r} check, got {payload['checks']!r}")
    return matches[0]


class Health(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        _pop_env(
            self,
            "AI_CADDIE_ADMIN_TOKEN",
            "AI_CADDIE_SECURITY_PROFILE",
            "AI_CADDIE_READINESS_TRACE",
            "AI_CADDIE_STATS_CACHE_DIR",
            "AI_CADDIE_PRIVATE_ROOT",
            "AI_CADDIE_BUILD_REVISION",
        )
        dict_targets = [(stats_cache, name) for name in _STATS_DICTS] + [
            (history_stats, "_WARM_THREADS"),
            (history_stats, "_WARM_FAILURES"),
            (history_stats, "_WARM_FAILURE_TIME"),
            (readiness, "_MOBILE_READINESS"),
            (readiness, "_MOBILE_READINESS_THREADS"),
        ]
        for module, name in dict_targets:
            patcher = mock.patch.dict(getattr(module, name), clear=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        for patcher in (
            mock.patch.object(readiness, "load_sync_status_response", side_effect=_ready_sync_status),
            mock.patch.object(readiness, "course_reference_coverage", return_value={"total": 2, "ready": 2}),
            # The owner package warm is a separate concern; keep it offline and cheap.
            mock.patch.object(
                readiness, "build_mobile_round_package_response", side_effect=RuntimeError("offline test")
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        # Registered last so it runs first: background workers finish before patches unwind.
        self.addCleanup(self._join_workers)

    def _join_workers(self) -> None:
        threads = list(history_stats._WARM_THREADS.values()) + list(readiness._MOBILE_READINESS_THREADS.values())
        for thread in threads:
            thread.join(JOIN_GUARD_S)
            self.assertFalse(thread.is_alive(), f"background worker {thread.name} did not finish")

    def _readiness(self) -> dict[str, Any]:
        response = self.client.get("/api/v2/readiness")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["authenticated"])
        return payload

    def test_revision_readiness(self) -> None:
        """S-24 [main]: after a deploy, health reports the deployed commit and a cold stats cache reads as warming, not failed"""
        with mock.patch.dict(os.environ, {"AI_CADDIE_BUILD_REVISION": DEPLOYED_SHA}):
            health = self.client.get("/api/v2/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["revision"], DEPLOYED_SHA)
        self.assertEqual(health.json()["status"], "ok")

        payload = self._readiness()
        history = _check(payload, "history")
        self.assertEqual(history["state"], "warming")
        # Warming is an accepted state: the runtime verdict stays ready.
        self.assertEqual(payload["runtimeStatus"], "ready")
        self.assertNotIn("history", [c["label"] for c in payload["checks"] if c["state"] in {"failed", "degraded"}])

    def test_readiness_returns_while_history_build_is_blocked(self) -> None:
        """S-24: readiness answers warming while the history statistics build is still running"""
        release = threading.Event()
        real_build = stats_cache._build_history_stats

        def blocked_build(*args: Any, **kwargs: Any) -> Any:
            release.wait()
            return real_build(*args, **kwargs)

        patcher = mock.patch.object(stats_cache, "_build_history_stats", side_effect=blocked_build)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Runs before the join cleanup registered in setUp, so the worker can exit.
        self.addCleanup(release.set)

        result: dict[str, Any] = {}

        def call() -> None:
            try:
                result["payload"] = self.client.get("/api/v2/readiness").json()
            except BaseException as exc:  # surfaced to the test thread below
                result["error"] = exc

        caller = threading.Thread(target=call, name="readiness-caller", daemon=True)
        caller.start()
        caller.join(JOIN_GUARD_S)
        self.assertFalse(caller.is_alive(), "readiness request did not return while the stats build was blocked")
        self.assertNotIn("error", result)
        self.assertEqual(_check(result["payload"], "history")["state"], "warming")
        self.assertEqual(result["payload"]["runtimeStatus"], "ready")

    def test_revision_classes(self) -> None:
        """S-24: health revision is the deploy value verbatim, trimmed, or unknown when unset or blank"""
        rows = (
            ("deployed sha", DEPLOYED_SHA, DEPLOYED_SHA),
            ("unset", None, "unknown"),
            ("empty", "", "unknown"),
            ("whitespace only", "  \n", "unknown"),
            ("padded sha", f"  {DEPLOYED_SHA}\n", DEPLOYED_SHA),
        )
        for label, value, expected in rows:
            with self.subTest(label):
                env = {} if value is None else {"AI_CADDIE_BUILD_REVISION": value}
                with mock.patch.dict(os.environ, env):
                    if value is None:
                        os.environ.pop("AI_CADDIE_BUILD_REVISION", None)
                    response = self.client.get("/api/v2/health")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["revision"], expected)

    def test_warm_cache_reads_ready(self) -> None:
        """S-24: once the history statistics are built, readiness reports history ready and fresh"""
        history_stats.load_history_stats_response("all")
        history_stats.load_history_stats_response("last20")
        payload = self._readiness()
        history = _check(payload, "history")
        self.assertEqual(history["state"], "ready", history)
        self.assertEqual(payload["runtimeStatus"], "ready")

    def test_readiness_without_owner_is_liveness_only(self) -> None:
        """S-24: a caller who is not the owner gets liveness only, with no owner evidence"""
        with mock.patch.dict(os.environ, {"AI_CADDIE_ADMIN_TOKEN": "owner-secret-for-test"}):
            response = self.client.get("/api/v2/readiness")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["authenticated"])
        self.assertEqual(payload["checks"], [])
        self.assertEqual(payload["serviceStatus"], "ready")


def _drive_abandoned_post(path: str, partial_body: bytes) -> list[dict[str, Any]]:
    """Send part of a JSON body through the raw ASGI app, then report the client gone."""
    messages = [
        {"type": "http.request", "body": partial_body, "more_body": True},
        {"type": "http.disconnect"},
    ]
    sent: list[dict[str, Any]] = []
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(partial_body) + 4096).encode()),
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    async def receive() -> dict[str, Any]:
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def run() -> None:
        await app(scope, receive, send)

    asyncio.run(run())
    return sent


class Timing(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        _pop_env(self, "AI_CADDIE_ADMIN_TOKEN", "AI_CADDIE_SECURITY_PROFILE", "AI_CADDIE_PRIVATE_ROOT")
        self.server_records: list[dict[str, Any]] = []
        self.client_records: list[dict[str, Any]] = []
        for patcher in (
            mock.patch.object(request_timing, "TIMING_ROOT", None),
            mock.patch.object(
                request_timing, "_enqueue_timing", side_effect=lambda record, **_kw: self.server_records.append(record)
            ),
            mock.patch.object(request_timing, "append_client_timing", side_effect=self.client_records.append),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_disconnect_499(self) -> None:
        """S-28 [main]: a client that disconnects mid-body is logged and recorded as 499, never 400"""
        cases = (
            ("/api/v2/mobile/client-timing", b'[{"request_id": "abc'),
            ("/api/v2/caddie/decision", b'{"roundId": "r'),
        )
        for path, partial in cases:
            with self.subTest(path):
                self.server_records.clear()
                with self.assertLogs("server_v2.timing", "INFO") as logs:
                    sent = _drive_abandoned_post(path, partial)
                timing_lines = [line for line in logs.output if "request_timing" in line and f"path={path} " in line]
                self.assertEqual(len(timing_lines), 1, logs.output)
                self.assertIn("status=499", timing_lines[0])
                self.assertNotIn("status=400", timing_lines[0])
                self.assertEqual([record["status"] for record in self.server_records], [499])
                self.assertEqual(self.server_records[0]["path"], path)
                started = [message["status"] for message in sent if message["type"] == "http.response.start"]
                self.assertNotIn(400, started)
                self.assertTrue(all(status == 499 for status in started), started)
                self.assertEqual(self.client_records, [])

    def test_client_timing_accepted_and_bounded(self) -> None:
        """S-28: complete client timing diagnostics are accepted, invalid ones rejected, oversized batches refused"""
        good = {
            "request_id": "ios-req-1",
            "path": "/api/v2/mobile/rounds/123/package",
            "client_total_ms": 812.5,
            "started_at": "2026-11-10T08:00:00+08:00",
            "status": 200,
            "network_type": "wifi",
        }
        bad = dict(good, unexpected_field="x")
        response = self.client.post("/api/v2/mobile/client-timing", json=[good, bad])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"accepted": 1, "rejected": 1})
        self.assertEqual(len(self.client_records), 1)
        self.assertEqual(self.client_records[0]["request_id"], "ios-req-1")
        self.assertEqual(self.server_records[-1]["status"], 200)

        self.client_records.clear()
        too_many = self.client.post("/api/v2/mobile/client-timing", json=[good] * 51)
        self.assertEqual(too_many.status_code, 413)
        self.assertEqual(self.client_records, [])
        at_limit = self.client.post("/api/v2/mobile/client-timing", json=[good] * 50)
        self.assertEqual(at_limit.status_code, 200)
        self.assertEqual(at_limit.json(), {"accepted": 50, "rejected": 0})


class Weather(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        _pop_env(self, "AI_CADDIE_ADMIN_TOKEN", "AI_CADDIE_SECURITY_PROFILE")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.transport_calls = 0

        def offline(*_args: Any, **_kwargs: Any) -> Any:
            self.transport_calls += 1
            raise OSError("weather provider offline (test)")

        for patcher in (
            mock.patch.object(weather_api, "WEATHER_ROOT", self.root),
            mock.patch.object(weather_api, "OPEN_METEO_TRANSPORT", None),
            mock.patch.object(weather_context, "_default_open_meteo_transport", side_effect=offline),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_weather_unavailable_is_not_invented(self) -> None:
        """S-29 [main]: when the weather provider fails the snapshot says missing and invents no temperature or wind"""
        response = self.client.get(
            "/api/v2/weather/snapshot",
            params={
                "source": "open_meteo",
                "latitude": 31.2,
                "longitude": 121.5,
                "captured_at": "2026-11-10T08:00:00+08:00",
                "persist": "true",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertGreaterEqual(self.transport_calls, 1)
        self.assertEqual(payload["state"], "missing")
        for field in ("windSpeedMps", "windDirectionDeg", "temperatureC", "precipitationMm"):
            self.assertIsNone(payload[field], field)
        labels = [item["label"] if isinstance(item, dict) else item for item in payload["missingData"]]
        self.assertIn("weather_provider", labels)
        # A missing snapshot is never persisted as evidence.
        self.assertEqual([p for p in self.root.rglob("*") if p.is_file()], [])

    def test_product_settings_readable(self) -> None:
        """S-29: product settings expose the documented sources, AI providers, apps, privacy and endpoints"""
        response = self.client.get("/api/v2/settings/product")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-product-settings-v1")
        for key in ("dataSources", "aiProviders", "liveApps", "privacy", "endpoints"):
            self.assertIn(key, payload)
        sources = {source["id"]: source for source in payload["dataSources"]}
        self.assertEqual(sources["garmin_cn_web_session"]["track"], "primary")
        self.assertEqual(sources["garmin_cn_web_session"]["credentialPolicy"], "session_material_only")
        self.assertEqual(sources["garmin_oauth"]["state"], "not_syncable")
        self.assertTrue(payload["liveApps"]["ios"]["offlineFirst"])
        self.assertTrue(payload["liveApps"]["watch"]["requiresIphoneBridge"])
        self.assertTrue(payload["aiProviders"]["factBindingRequired"])
        self.assertTrue(payload["privacy"]["noGarminPasswordStorage"])
        self.assertEqual(payload["endpoints"]["syncStatus"], "/api/v2/sync/status")


if __name__ == "__main__":
    unittest.main()
