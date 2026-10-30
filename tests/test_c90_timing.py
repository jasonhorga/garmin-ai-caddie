from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime
import io
import json
import logging
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse
from starlette.routing import Match, Route

from ai_caddie.core import request_timing
from server_v2 import main as server_main
from server_v2.main import app
from server_v2.timing_api import sanitize_client_record


@contextmanager
def _routes_prepended(*routes):
    """Put extra routes in front of the real route table for one test."""
    app.router.routes[0:0] = routes
    try:
        yield
    finally:
        for route in routes:
            app.router.routes.remove(route)


class _RecordingRoute:
    """Matches nothing; records each route-table walk that reaches it."""

    path = "/recording-route"

    def __init__(self) -> None:
        self.walked: list[str] = []

    def matches(self, scope):
        self.walked.append(scope["path"])
        return Match.NONE, {}


class _BrokenRoute:
    path = "/broken-route/{value}"

    def matches(self, scope):
        raise RuntimeError("broken convertor")


def _access_record(method: str, path: str, status: int) -> logging.LogRecord:
    # uvicorn 0.48 h11/httptools: access_logger.info('%s - "%s %s HTTP/%s" %d', client, method,
    # get_path_with_query_string(scope), http_version, status).
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0,
        '%s - "%s %s HTTP/%s" %d',
        ("testclient:50000", method, path, "1.1", status), None,
    )


class C90TimingPersistenceTests(unittest.TestCase):
    def test_uvicorn_access_filter_uses_method_route_templates_and_unmatched_marker(self) -> None:
        """J7.3: access diagnostics retain method/status but never retain opaque URL segments."""
        cases = [
            ("GET", "/api/v2/players/p_1a2b3c4d/clubs/bag?token=secret", 200, "/api/v2/players/{player_id}/clubs/bag"),
            ("PUT", "/api/v2/players/p_1a2b3c4d/clubs/bag", 204, "/api/v2/players/{player_id}/clubs/bag"),
            ("GET", "/api/v2/history/rounds/900001", 404, "/api/v2/history/rounds/{round_ref}"),
            ("GET", "/api/v2/history/rounds/r_ab12cd", 500, "/api/v2/history/rounds/{round_ref}"),
            ("GET", "/api/v2/history/rounds/r_ab12cd/removed", 404, "<unmatched>"),
        ]
        for method, path, status, expected_path in cases:
            record = logging.LogRecord(
                "uvicorn.access", logging.INFO, __file__, 0,
                '%s "%s %s %s" %s',
                ("127.0.0.1", method, path, "HTTP/1.1", status), None,
            )
            self.assertTrue(request_timing.URLRedactionFilter().filter(record))
            output = record.getMessage()
            self.assertIn(f'"{method} ', output)
            self.assertIn(f'" {status}', output)
            self.assertIn(expected_path, output)
            self.assertNotIn("p_1a2b3c4d", output)
            self.assertNotIn("900001", output)
            self.assertNotIn("r_ab12cd", output)
            self.assertNotIn("token=secret", output)

    def test_uvicorn_access_filter_exception_uses_unmatched_marker(self) -> None:
        """J7.3: a route matcher failure still emits a safe access record."""
        path = "/api/v2/history/rounds/r_ab12cd"
        record = logging.LogRecord(
            "uvicorn.access", logging.INFO, __file__, 0,
            '%s "%s %s %s" %s',
            ("127.0.0.1", "GET", path, "HTTP/1.1", 503), None,
        )
        with patch.object(request_timing, "route_template", side_effect=RuntimeError("matcher"), create=True):
            self.assertTrue(request_timing.URLRedactionFilter().filter(record))
        output = record.getMessage()
        self.assertIn("<unmatched>", output)
        self.assertIn('"GET ', output)
        self.assertIn('" 503', output)
        self.assertNotIn("r_ab12cd", output)

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
                timing.finish(
                    method="GET",
                    path="/api/v2/mobile/courses/3881/package?render=false",
                    status=200,
                    route_path="/api/v2/mobile/courses/{course_id}/package",
                )
                request_timing.flush_timing_writes()
            rows = [json.loads(line) for line in (root / "timing/2026-10-27.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["path"], "/api/v2/mobile/courses/{course_id}/package")
            self.assertEqual(rows[0]["request_id"], "phone:package-1")
            self.assertEqual(rows[0]["status"], 200)
            self.assertIn("facts_package", rows[0]["stages"])
            self.assertTrue(rows[0]["ts"].startswith("2026-10-27T16:00:00.000+08:00"))

    def test_finish_logs_the_route_template_without_resource_ids(self) -> None:
        timing = request_timing.RequestTiming("timing-log")
        with self.assertLogs("server_v2.timing", level="INFO") as captured:
            timing.finish(
                method="GET",
                path="/api/v2/history/rounds/secret-round",
                status=200,
                route_path="/api/v2/history/rounds/{round_ref}",
            )
        output = "\n".join(captured.output)
        self.assertIn("path=/api/v2/history/rounds/{round_ref}", output)
        self.assertNotIn("secret-round", output)

    def test_server_timing_uses_fastapi_route_templates_for_non_numeric_ids_and_404(self) -> None:
        with tempfile.TemporaryDirectory() as raw, patch.object(request_timing, "TIMING_ROOT", Path(raw)), patch.object(
            request_timing, "TIMING_CLOCK", lambda: datetime(2026, 10, 27, 16, 0, tzinfo=request_timing._BEIJING)
        ):
            client = TestClient(app)
            requests = (
                ("numeric-round", "/api/v2/history/rounds/900001"),
                ("text-round", "/api/v2/history/rounds/round-secret"),
                ("player", "/api/v2/players/player-secret/clubs/bag"),
                ("unmatched", "/missing/round/secret"),
            )
            responses = [
                client.get(path, headers={"X-AI-Caddie-Request-ID": request_id})
                for request_id, path in requests
            ]
            request_timing.flush_timing_writes()
            self.assertEqual(responses[-1].status_code, 404)
            rows = [
                json.loads(line)
                for line in (Path(raw) / "timing/2026-10-27.jsonl").read_text().splitlines()
            ]
            by_request = {row["request_id"]: row for row in rows}
            self.assertEqual(by_request["numeric-round"]["path"], "/api/v2/history/rounds/{round_ref}")
            self.assertEqual(by_request["text-round"]["path"], "/api/v2/history/rounds/{round_ref}")
            self.assertEqual(by_request["player"]["path"], "/api/v2/players/{player_id}/clubs/bag")
            self.assertEqual(by_request["unmatched"]["path"], "<unmatched>")
            serialized = json.dumps(rows, ensure_ascii=False)
            self.assertNotIn("round-secret", serialized)
            self.assertNotIn("player-secret", serialized)

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
    def test_client_timing_templates_non_numeric_route_ids(self) -> None:
        """J7.3: client timing uses the server route template for opaque identifiers."""
        records = [
            {
                "request_id": "client-player",
                "path": "/api/v2/players/p_1a2b3c4d/clubs/bag",
                "client_total_ms": 12,
                "status": 200,
                "started_at": "2026-10-27T08:00:00Z",
            },
            {
                "request_id": "client-round",
                "path": "/api/v2/history/rounds/r_ab12cd",
                "client_total_ms": 13,
                "status": 200,
                "started_at": "2026-10-27T08:00:00Z",
            },
        ]
        sanitized = [sanitize_client_record(record) for record in records]
        self.assertEqual(
            [row["path"] for row in sanitized if row is not None],
            ["/api/v2/players/{player_id}/clubs/bag", "/api/v2/history/rounds/{round_ref}"],
        )
        serialized = json.dumps(sanitized)
        self.assertNotIn("p_1a2b3c4d", serialized)
        self.assertNotIn("r_ab12cd", serialized)

    def test_client_timing_unmatched_route_records_marker_not_opaque_ids(self) -> None:
        """J7.3: a client path the route table cannot match never persists its segments."""
        paths = [
            "/api/v2/players/p_1a2b3c4d/clubs/bag/",
            "/api/v2/players/p_1a2b3c4d/removed-endpoint",
            "/api/v2/history/rounds/r_ab12cd/",
        ]
        sanitized = [
            sanitize_client_record({
                "request_id": f"client-unmatched-{index}",
                "path": path,
                "client_total_ms": 12,
                "status": 404,
                "started_at": "2026-10-27T08:00:00Z",
            })
            for index, path in enumerate(paths)
        ]
        self.assertEqual([row["path"] for row in sanitized if row is not None], ["<unmatched>"] * len(paths))
        serialized = json.dumps(sanitized)
        self.assertNotIn("p_1a2b3c4d", serialized)
        self.assertNotIn("r_ab12cd", serialized)

    def test_exception_timing_keeps_matched_route_template(self) -> None:
        """J7.3: a 500 timing record keeps the matched route for diagnosis."""
        from server_v2 import main
        from starlette.requests import Request

        request = Request({
            "type": "http",
            "method": "GET",
            "path": "/api/v2/history/rounds/r_ab12cd",
            "headers": [],
        })
        request.scope["route"] = SimpleNamespace(path="/api/v2/history/rounds/{round_ref}")

        async def call_next(_request):
            raise RuntimeError("fixture failure")

        with self.assertLogs("server_v2.timing", level="INFO") as captured:
            with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                asyncio.run(main.request_timing_middleware(request, call_next))
        output = "\n".join(captured.output)
        self.assertIn("path=/api/v2/history/rounds/{round_ref}", output)
        self.assertNotIn("r_ab12cd", output)

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


class UvicornLogExitTests(unittest.TestCase):
    def _log_after_startup(self, logger_name: str, formatter: logging.Formatter, msg: str, args: tuple) -> str:
        """Log one line the way uvicorn does, through the loggers the app configures at startup."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        target = logging.getLogger(logger_name)
        loggers = [target, *(logging.getLogger(name) for name in server_main.SERVICE_INFO_LOGGERS)]
        saved = [(lg, lg.level, lg.propagate, list(lg.handlers), list(lg.filters), lg.disabled) for lg in loggers]

        def restore() -> None:
            for lg, level, propagate, handlers, filters, disabled in saved:
                lg.setLevel(level)
                lg.propagate = propagate
                lg.handlers[:] = handlers
                lg.filters[:] = filters
                lg.disabled = disabled

        self.addCleanup(restore)
        # uvicorn's dictConfig leaves its loggers at INFO with their own handler and no filters;
        # the lifespan then runs configure_request_timing_logging().
        target.setLevel(logging.INFO)
        target.propagate = False
        target.disabled = False
        target.handlers[:] = [handler]
        target.filters[:] = []
        server_main.configure_request_timing_logging()
        target.info(msg, *args)
        return stream.getvalue()

    def test_startup_access_logger_writes_route_template_without_ids_or_query(self) -> None:
        """J7.3: the uvicorn.access exit configured at startup carries no opaque id or token."""
        from uvicorn.logging import AccessFormatter

        output = self._log_after_startup(
            "uvicorn.access",
            AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False),
            '%s - "%s %s HTTP/%s" %d',
            ("testclient:50000", "GET", "/api/v2/players/p_ACCESSSECRET/clubs/bag?token=ACCESSTOKEN", "1.1", 200),
        )
        # Expected: the bag route template from server_v2/main.py in uvicorn's request-line shape.
        self.assertIn('testclient:50000 - "GET /api/v2/players/{player_id}/clubs/bag HTTP/1.1" 200', output)
        self.assertNotIn("ACCESSSECRET", output)
        self.assertNotIn("ACCESSTOKEN", output)
        self.assertNotIn("?", output)

    def test_startup_error_logger_drops_websocket_handshake_target(self) -> None:
        """J7.3: a hand-crafted WebSocket upgrade cannot write ids or tokens to uvicorn.error."""
        target = "/api/v2/players/p_WSSECRET/clubs/bag?token=WSTOKEN"
        # The handshake lines uvicorn 0.48's websockets/wsproto protocols log on uvicorn.error; the
        # API serves no WebSocket route, so every handshake target is unmatched.
        cases = (
            ('%s - "WebSocket %s" 403', ("testclient:50000", target), 'testclient:50000 - "WebSocket <unmatched>" 403'),
            ('%s - "WebSocket %s" [accepted]', ("testclient:50000", target), 'testclient:50000 - "WebSocket <unmatched>" [accepted]'),
            ('%s - "WebSocket %s" %d', ("testclient:50000", target, 404), 'testclient:50000 - "WebSocket <unmatched>" 404'),
        )
        for msg, args, expected in cases:
            with self.subTest(msg=msg):
                output = self._log_after_startup("uvicorn.error", logging.Formatter("%(message)s"), msg, args)
                self.assertEqual(output.strip(), expected)

    def test_route_cache_ignores_query_and_keeps_no_raw_path(self) -> None:
        """J7.3: route resolution caches one entry per path and retains no token or opaque id."""
        recorder = _RecordingRoute()
        with _routes_prepended(recorder):
            for token in ("CACHETOKEN1", "CACHETOKEN2", "CACHETOKEN3"):
                self.assertEqual(
                    request_timing.route_template(f"/api/v2/players/p_CACHESECRET/clubs/bag?token={token}", "GET"),
                    "/api/v2/players/{player_id}/clubs/bag",
                )
        # One route-table walk (one cache entry); routing never reads the query, so the rest are hits.
        self.assertEqual(recorder.walked, ["/api/v2/players/p_CACHESECRET/clubs/bag"])
        cached = repr(list(request_timing._ROUTE_TEMPLATE_CACHE.items()))
        self.assertNotIn("CACHETOKEN", cached)
        self.assertNotIn("CACHESECRET", cached)

    def test_access_template_follows_starlette_method_dispatch(self) -> None:
        """J7.3: access diagnostics name the route Starlette dispatches to, including its 405."""
        item = Route("/dispatch-route/{item}", lambda request: PlainTextResponse("item"), methods=["GET"])
        fixed = Route("/dispatch-route/fixed", lambda request: PlainTextResponse("fixed"), methods=["POST"])
        # Starlette's Router: the first route matching path and method handles the request; with
        # none, the first route matching the path answers 405 with its Allow header.
        cases = (
            ("GET", 200, "item", "/dispatch-route/{item}"),
            ("POST", 200, "fixed", "/dispatch-route/fixed"),
            ("DELETE", 405, {"GET", "HEAD"}, "/dispatch-route/{item}"),
        )
        with _routes_prepended(item, fixed):
            client = TestClient(app.router)
            for method, status, answer, template in cases:
                with self.subTest(method=method):
                    response = client.request(method, "/dispatch-route/fixed")
                    self.assertEqual(response.status_code, status)
                    if status == 200:
                        self.assertEqual(response.text, answer)
                    else:
                        self.assertEqual(set(response.headers["allow"].split(", ")), answer)
                    record = _access_record(method, "/dispatch-route/fixed", status)
                    request_timing.URLRedactionFilter().filter(record)
                    self.assertEqual(record.getMessage(), f'testclient:50000 - "{method} {template} HTTP/1.1" {status}')
        record = _access_record("DELETE", "/api/v2/history/rounds/r_DISPATCHSECRET", 405)
        request_timing.URLRedactionFilter().filter(record)
        self.assertEqual(record.getMessage(), 'testclient:50000 - "DELETE /api/v2/history/rounds/{round_ref} HTTP/1.1" 405')

    def test_broken_route_matcher_skips_only_that_route(self) -> None:
        """J7.3: one route whose matcher raises does not hide the routes after it."""
        with _routes_prepended(_BrokenRoute()):
            record = _access_record("GET", "/api/v2/players/p_BROKENSECRET/clubs/bag", 200)
            request_timing.URLRedactionFilter().filter(record)
            client = sanitize_client_record({
                "request_id": "broken-route",
                "path": "/api/v2/history/rounds/r_BROKENSECRET",
                "client_total_ms": 12,
                "status": 200,
                "started_at": "2026-10-27T08:00:00Z",
            })
        self.assertEqual(record.getMessage(), 'testclient:50000 - "GET /api/v2/players/{player_id}/clubs/bag HTTP/1.1" 200')
        self.assertEqual(client["path"], "/api/v2/history/rounds/{round_ref}")


if __name__ == "__main__":
    unittest.main()
