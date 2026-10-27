from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.core import request_timing
from server_v2.main import app
from server_v2.timing_api import sanitize_client_record


class C90TimingPersistenceTests(unittest.TestCase):
    def test_template_path_keeps_double_slash_prefix_without_url_parsing(self) -> None:
        self.assertEqual(request_timing.template_path("//api/v2/courses/3881?x=1"), "//api/v2/courses/{id}")
        self.assertEqual(request_timing.template_path("//[x"), "//[x")

    def test_finish_writes_templated_jsonl_record(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with patch.object(request_timing, "TIMING_ROOT", root), patch.object(
                request_timing, "TIMING_CLOCK", lambda: datetime(2026, 10, 27, 16, 0, tzinfo=request_timing._BEIJING)
            ):
                timing = request_timing.RequestTiming("phone:package-1")
                timing.mark("facts package")
                timing.finish(method="GET", path="/api/v2/mobile/courses/3881/package?render=false", status=200)
                request_timing.flush_timing_writes()
            rows = [json.loads(line) for line in (root / "timing/2026-10-27.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["path"], "/api/v2/mobile/courses/{id}/package")
            self.assertEqual(rows[0]["request_id"], "phone:package-1")
            self.assertEqual(rows[0]["status"], 200)
            self.assertIn("facts_package", rows[0]["stages"])
            self.assertTrue(rows[0]["ts"].startswith("2026-10-27T16:00:00.000+08:00"))

    def test_startup_cleanup_keeps_fourteen_beijing_dates(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "private"
            timing_dir = root / "timing"
            timing_dir.mkdir(parents=True)
            for name in ("2026-10-13.jsonl", "2026-10-14.jsonl", "client-2026-10-13.jsonl", "client-2026-10-14.jsonl"):
                (timing_dir / name).write_text("{}\n")
            with patch.object(request_timing, "TIMING_ROOT", root), patch.object(
                request_timing, "TIMING_CLOCK", lambda: datetime(2026, 10, 27, tzinfo=request_timing._BEIJING)
            ):
                request_timing.initialize_timing_storage()
            self.assertFalse((timing_dir / "2026-10-13.jsonl").exists())
            self.assertFalse((timing_dir / "client-2026-10-13.jsonl").exists())
            self.assertTrue((timing_dir / "2026-10-14.jsonl").exists())
            self.assertTrue((timing_dir / "client-2026-10-14.jsonl").exists())

    def test_writer_failure_does_not_stop_the_next_record(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original_open = Path.open
            failed = False

            def flaky_open(path: Path, *args, **kwargs):
                nonlocal failed
                if path.parent == root / "timing" and not failed:
                    failed = True
                    raise OSError("injected timing write failure")
                return original_open(path, *args, **kwargs)

            with patch.object(request_timing, "TIMING_ROOT", root), patch.object(
                request_timing, "TIMING_CLOCK", lambda: datetime(2026, 10, 27, 16, 0, tzinfo=request_timing._BEIJING)
            ), patch.object(Path, "open", flaky_open):
                request_timing.RequestTiming("first").finish(method="GET", path="/x", status=200)
                request_timing.RequestTiming("second").finish(method="GET", path="/x", status=200)
                request_timing.flush_timing_writes()
            rows = [json.loads(line) for line in (root / "timing" / "2026-10-27.jsonl").read_text().splitlines()]
            self.assertEqual([row["request_id"] for row in rows], ["second"])


class C90TimingEndpointTests(unittest.TestCase):
    def test_admin_timing_requires_configured_token(self) -> None:
        with tempfile.TemporaryDirectory() as raw, patch.object(request_timing, "TIMING_ROOT", Path(raw)), patch.dict(
            "os.environ", {"AI_CADDIE_ADMIN_TOKEN": "secret-c90"}, clear=False
        ):
            path = Path(raw) / "timing/2026-10-27.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"ts": "2026-10-27T08:00:00+08:00", "request_id": "r1", "path": "/api/v2/mobile/courses/{id}/package", "total_ms": 42.0}) + "\n")
            client = TestClient(app)
            self.assertEqual(client.get("/api/v2/admin/timing").status_code, 401)
            response = client.get("/api/v2/admin/timing?path=/api/v2/mobile&min_ms=40", headers={"X-AI-Caddie-Admin-Token": "secret-c90"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()[0]["request_id"], "r1")
            request_timing.flush_timing_writes()

    def test_client_timing_drops_invalid_entries_and_caps_batch(self) -> None:
        with tempfile.TemporaryDirectory() as raw, patch.object(request_timing, "TIMING_ROOT", Path(raw)), patch.object(
            request_timing, "TIMING_CLOCK", lambda: datetime(2026, 10, 27, 16, 0, tzinfo=request_timing._BEIJING)
        ):
            client = TestClient(app)
            valid = {"request_id": "r-client", "path": "/api/v2/mobile/courses/3881/package", "client_total_ms": 123.4, "status": 200, "started_at": "2026-10-27T08:00:00Z", "network_type": "wifi"}
            response = client.post("/api/v2/mobile/client-timing", json=[valid, {"request_id": "bad value", "path": "/x", "client_total_ms": 1, "status": 200, "started_at": "2026-10-27T08:00:00Z"}])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"accepted": 1, "rejected": 1})
            request_timing.flush_timing_writes()
            self.assertIn('"request_id":"r-client"', (Path(raw) / "timing/client-2026-10-27.jsonl").read_text())
            self.assertEqual(client.post("/api/v2/mobile/client-timing", json=[valid] * 51).status_code, 413)
            self.assertEqual(
                client.post("/api/v2/mobile/client-timing", content=b"[]", headers={"Content-Length": str(64 * 1024 + 1)}).status_code,
                413,
            )
            request_timing.flush_timing_writes()

    def test_client_timing_drops_bad_template_and_invalid_error_field(self) -> None:
        valid = {"request_id": "r-client", "path": "/api/v2/mobile/courses/3881/package", "client_total_ms": 12, "status": 200, "started_at": "2026-10-27T08:00:00Z", "error": "bad?key=secret"}
        with patch.object(request_timing, "template_path", side_effect=ValueError("bad path")):
            self.assertIsNone(sanitize_client_record(valid))
        sanitized = sanitize_client_record(valid)
        self.assertEqual(sanitized["status"], 200)
        self.assertNotIn("error", sanitized)

    def test_client_timing_requires_player_auth_when_admin_token_is_configured(self) -> None:
        with patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "secret-c90"}, clear=False):
            response = TestClient(app).post("/api/v2/mobile/client-timing", json=[])
        self.assertEqual(response.status_code, 401)

    def test_malformed_path_request_stays_a_404(self) -> None:
        response = TestClient(app).request("GET", "http://testserver//[x")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
