"""J7.3: runtime log exits exclude identities, including structured errors.

Imported by the J7 product suite; no assertions inspect implementation text.
"""
import hashlib
import io
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from starlette.responses import PlainTextResponse
from starlette.routing import Route

from ai_caddie.core import request_timing, revisions
from ai_caddie.ops import retention
from server_v2 import main
from tests.service_logging import preserve_service_logging
from tests.test_c90_timing import _routes_prepended


_STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class _FullFormatter(logging.Formatter):
    def format(self, record):
        rendered = super().format(record)
        extras = {key: value for key, value in record.__dict__.items() if key not in _STANDARD}
        return rendered + " extra=" + repr(extras)


class J7LogPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(preserve_service_logging())
        request_timing.clear_route_template_cache()
        self.addCleanup(request_timing.clear_route_template_cache)

    def capture_service(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(_FullFormatter("%(levelname)s:%(name)s:%(message)s"))
        # Exercise the production root exit and the separate non-propagating service exits.
        for name in ("", *main.SERVICE_INFO_LOGGERS):
            logging.getLogger(name).handlers[:] = [handler]
        main.configure_request_timing_logging()
        main.configure_request_timing_logging()  # startup is idempotent
        return stream

    def test_J73_real_failure_redacts_extras_arguments_and_chained_exceptions(self):
        from ai_caddie.history import stats_cache

        stream = self.capture_service()
        player, round_id, name = "SENTINELPLAYER", "SENTINELROUND", "哨兵球员名字"

        def broken_history(**kwargs):
            for logger_name in (*main.SERVICE_INFO_LOGGERS, "server_v2.future.child"):
                target = logging.getLogger(logger_name)
                target.warning("diagnostic player=%s", player, extra={
                    "player_id": player, "round_id": round_id, "player_name": name,
                    "context": {"display_name": name, "roundId": round_id},
                    "attempt": 3,
                })
            try:
                raise ValueError(name)
            except ValueError as cause:
                raise FileNotFoundError(f"data/players/{player}/{round_id}") from cause

        with patch.object(stats_cache, "cached_load_history_data", side_effect=broken_history):
            main._prepare_recent_work(player)
        output = stream.getvalue()
        for sentinel in (player, round_id, name):
            self.assertNotIn(sentinel, output)
        self.assertIn("prepare-recent failed", output)
        self.assertIn("FileNotFoundError", output)
        self.assertIn("ValueError", output)
        self.assertIn("Traceback", output)
        self.assertIn("broken_history", output)
        self.assertIn("'attempt': 3", output)
        self.assertIn("player_id", output)  # formatter really emits extra, not message-only
        for logger_name in (*main.SERVICE_INFO_LOGGERS, "server_v2.future.child"):
            self.assertIn("WARNING:" + logger_name, output)

    def test_J73_revision_scanner_omits_private_directory_without_service_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "data/players/SENTINELREVISION/scorecards"
            directory.mkdir(parents=True)
            def scanner():
                raise RuntimeError("scanner unavailable")
            entry = revisions._Entry(directory, "privacy", (), None, scanner,
                                     revisions._SCAN_ROUND, False)
            with patch.dict(revisions._ENTRIES, {(str(directory.resolve()), "privacy"): entry}, clear=True):
                with self.assertLogs(revisions._LOGGER, level="ERROR") as captured:
                    revisions.scan_revision_cache_once()
        output = "\n".join(captured.output)
        self.assertNotIn("SENTINELREVISION", output)
        self.assertIn("RuntimeError", output)

    def test_J73_retention_omits_private_root_without_service_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "SENTINELRETENTION"
            with patch.object(retention, "_clean_topo_cache", side_effect=OSError("unavailable")), \
                 patch.object(retention, "_clean_garmin_snapshots", side_effect=OSError("unavailable")), \
                 self.assertLogs(retention.logger, level="WARNING") as captured:
                retention.cleanup_private_volume(root=root)
        output = "\n".join(captured.output)
        self.assertNotIn("SENTINELRETENTION", output)
        self.assertIn("OSError", output)
        self.assertEqual(len(captured.records), 2)

    def test_J73_route_fixture_clears_cache_on_normal_and_exception_exit(self):
        route = Route("/privacy-fixture/{item}", lambda request: PlainTextResponse("ok"))
        for fail in (False, True):
            with self.subTest(exception_exit=fail):
                try:
                    with _routes_prepended(route):
                        self.assertEqual(request_timing.route_template("/privacy-fixture/fixed", "GET"),
                                         "/privacy-fixture/{item}")
                        if fail:
                            raise RuntimeError("fixture exit")
                except RuntimeError:
                    pass
                self.assertIsNone(request_timing.route_template("/privacy-fixture/fixed", "GET"))

    def test_J73_route_cache_hit_refreshes_recency(self):
        # The documented bound is 1024. Hitting 0 protects it; entry 1 is now the LRU.
        with patch.object(request_timing, "_match_route_template", return_value=None) as matcher:
            for index in range(1024):
                request_timing.route_template(f"/privacy-lru/{index}", "GET")
            request_timing.route_template("/privacy-lru/0", "GET")
            request_timing.route_template("/privacy-lru/1024", "GET")
            matcher.reset_mock()
            request_timing.route_template("/privacy-lru/0", "GET")
            matcher.assert_not_called()
            request_timing.route_template("/privacy-lru/1", "GET")
            matcher.assert_called_once_with("/privacy-lru/1", "GET")
            self.assertEqual(len(request_timing._ROUTE_TEMPLATE_CACHE), 1024)

    def test_J73_websocket_filter_preserves_actionable_warning_and_error(self):
        guard = request_timing.WebSocketHandshakeFilter()
        for level, message in ((logging.WARNING, "Unsupported upgrade request."),
                               (logging.ERROR, "Exception in ASGI application")):
            with self.subTest(message=message):
                record = logging.LogRecord("uvicorn.error", level, __file__, 1, message, (), None)
                self.assertTrue(guard.filter(record))
                self.assertEqual(record.getMessage(), message)
