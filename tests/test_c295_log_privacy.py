"""J7.3: runtime log exits exclude identities, including structured errors.

Discovered once with the J7 product tests; assertions exercise rendered output.
"""
from collections import namedtuple
from decimal import Decimal
import hashlib
import io
import logging.config
import logging
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from uvicorn.config import LOGGING_CONFIG

from starlette.responses import PlainTextResponse
from starlette.routing import Route

from ai_caddie.caddie.mobile_event_store import FileEventStore
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

    def capture_production(self):
        # J7.3: model uvicorn's real topology: no root handler, independent
        # service exits and a dynamic-stderr lastResort for ordinary children.
        logging.config.dictConfig(LOGGING_CONFIG)
        logging.getLogger().handlers[:] = []
        logging.getLogger().setLevel(logging.WARNING)
        streams = {}
        for name in (*main.SERVICE_INFO_LOGGERS, "uvicorn"):
            streams[name] = io.StringIO()
            handler = logging.StreamHandler(streams[name])
            handler.setFormatter(_FullFormatter("%(levelname)s:%(name)s:%(message)s"))
            logging.getLogger(name).handlers[:] = [handler]
        streams["lastResort"] = io.StringIO()
        self.enterContext(patch("sys.stderr", streams["lastResort"]))
        self.enterContext(patch.object(logging, "lastResort", logging._StderrHandler(logging.WARNING)))
        logging.lastResort.setFormatter(_FullFormatter("%(levelname)s:%(name)s:%(message)s"))
        main.configure_request_timing_logging()
        main.configure_request_timing_logging()
        return streams

    def capture_service(self):
        streams = self.capture_production()
        class Combined:
            def getvalue(self):
                return "\n".join(stream.getvalue() for stream in streams.values())
        return Combined()

    def test_J73_each_production_exit_redacts_identity_and_preserves_diagnostics(self):
        # J7.3 + RUNBOOK migration diagnostics: these literal codes are public;
        # player/round/token values and local paths must disappear at every exit.
        streams = self.capture_production()
        targets = {name: name for name in main.SERVICE_INFO_LOGGERS}
        targets["lastResort"] = "server_v2.privacy_future"
        for exit_name, logger_name in targets.items():
            with self.subTest(exit=exit_name):
                target = logging.getLogger(logger_name)
                target.error("mobile_event_migration_intent_unrecoverable partition=%s reason=%s",
                             "main:0123456789ab", "log_and_backup_mismatch")
                target.warning("geometry_derivatives failed gid=%s hole=%d stage=distances error_type=%s",
                               "public-course-42", 7, "ValueError")
                target.info("course_install gid=%s", "public-course-42")
                try:
                    raise OSError(28, "No space left on device (quota)", "data/players/PRIVATEPLAYER/events")
                except OSError as exc:
                    target.warning("storage failed: %r player_id=%s round_id=%s token=%s",
                                   exc, "PRIVATEPLAYER", "PRIVATEROUND", "PRIVATETOKEN", exc_info=True)
                output = streams[exit_name].getvalue()
                for public in ("log_and_backup_mismatch", "ValueError", "OSError", "28",
                               "No space left on device (quota)", "main:0123456789ab"):
                    with self.subTest(diagnostic=public):
                        self.assertIn(public, output)
                self.assertEqual(output.count("public-course-42"), 1 if exit_name == "lastResort" else 2)
                for private in ("PRIVATEPLAYER", "PRIVATEROUND", "PRIVATETOKEN", "data/players"):
                    self.assertNotIn(private, output)

    def test_J73_mapping_arguments_and_serialized_identity_fields_are_private(self):
        streams = self.capture_production()
        target = logging.getLogger(main.SERVICE_INFO_LOGGERS[0])
        target.warning("details=%s status=200", {"player_id": "PRIVATEPLAYER", "reason": "intent_unreadable"})
        target.warning('details={"round_id":"PRIVATEROUND","reason":"intent_unreadable"} status=200')
        output = streams[main.SERVICE_INFO_LOGGERS[0]].getvalue()
        for private in ("PRIVATEPLAYER", "PRIVATEROUND"):
            with self.subTest(private=private):
                self.assertNotIn(private, output)
        self.assertIn('"round_id":"[redacted]","reason":"intent_unreadable"', output)
        self.assertIn("'player_id': '[redacted]'", output)
        self.assertEqual(output.count("intent_unreadable"), 2)
        self.assertEqual(output.count("status=200"), 2)

    def test_J73_filter_failure_never_escapes_business_logging(self):
        streams = self.capture_production()
        target = logging.getLogger(main.SERVICE_INFO_LOGGERS[0])
        Point = namedtuple("Point", "x y")
        cases = (("numpy=%d", (np.int64(7),)), ("decimal=%d", (Decimal(8),)),
                 ("point=%s", (Point(1, 2),)), ("mismatch=%s %s", ("PRIVATEPLAYER",)))
        for message, args in cases:
            with self.subTest(message=message):
                try:
                    target.warning(message, *args)
                except Exception as exc:
                    self.fail("business logging raised " + type(exc).__name__)
        output = streams[main.SERVICE_INFO_LOGGERS[0]].getvalue()
        for public in ("numpy=7", "decimal=8", "point=", "log record redaction failed"):
            self.assertIn(public, output)
        self.assertNotIn("PRIVATEPLAYER", output)

    def test_J73_sensitive_values_do_not_swallow_neighboring_timing_fields(self):
        streams = self.capture_production()
        target = logging.getLogger(main.SERVICE_INFO_LOGGERS[0])
        for path in ("/api/v2/share/PRIVATETOKEN", "https://example.invalid/p/PRIVATETOKEN",
                     "https://example.invalid/api?token=PRIVATETOKEN"):
            target.info("path=%s player_id=%s status=200 total_ms=12 stages=geometry:3 holes=3/18 active round event",
                        path, "PRIVATEPLAYER")
        output = streams[main.SERVICE_INFO_LOGGERS[0]].getvalue()
        for public in ("status=200", "total_ms=12", "stages=geometry:3", "holes=3/18", "active round event"):
            self.assertEqual(output.count(public), 3, output)
        for private in ("PRIVATETOKEN", "PRIVATEPLAYER"):
            self.assertNotIn(private, output)

    def test_J73_uvicorn_unhandled_exception_and_stack_keep_only_frame_locations(self):
        streams = self.capture_production()
        try:
            raise ValueError("data/players/PRIVATEPLAYER/PRIVATEROUND")
        except ValueError:
            logging.getLogger("uvicorn.error").error("Exception in ASGI application", exc_info=True)
        logging.getLogger(main.SERVICE_INFO_LOGGERS[0]).warning("stack diagnostic", stack_info=True)
        output = streams["uvicorn"].getvalue()
        self.assertIn("ValueError", output)
        self.assertIn("test_c295_log_privacy.py", output)
        self.assertNotIn("PRIVATEPLAYER", output)
        stack = streams[main.SERVICE_INFO_LOGGERS[0]].getvalue()
        self.assertIn("test_c295_log_privacy.py", stack)
        self.assertIn("test_J73_uvicorn_unhandled_exception_and_stack_keep_only_frame_locations", stack)
        self.assertRegex(stack, r"line \d+")
        for rendered in (output, stack):
            self.assertNotIn(str(Path(__file__).parent), rendered)
            self.assertNotIn('raise ValueError(', rendered)

    def test_J73_handlers_added_after_startup_are_protected(self):
        self.capture_production()
        for name in ("ai_caddie.privacy_late", ""):
            with self.subTest(exit=name or "root"):
                stream = io.StringIO()
                exit_logger = logging.getLogger(name)
                exit_logger.propagate = False
                exit_logger.addHandler(logging.StreamHandler(stream))
                target = exit_logger if name else logging.getLogger("server_v2.privacy_late_root")
                target.warning("player_id=%s status=200", "PRIVATEPLAYER")
                self.assertNotIn("PRIVATEPLAYER", stream.getvalue())
                self.assertIn("status=200", stream.getvalue())

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

    def test_J73_syntax_error_payload_is_private_but_stack_survives(self):
        from ai_caddie.history import stats_cache

        stream = self.capture_service()
        failure = SyntaxError("SENTINELSYNTAX", ("data/players/SENTINELSYNTAX", 1, 1, "SENTINELSYNTAX"))
        failure.add_note("SENTINELNOTE")
        with patch.object(stats_cache, "cached_load_history_data", side_effect=failure):
            main._prepare_recent_work("SENTINELPLAYER")
        output = stream.getvalue()
        self.assertNotIn("SENTINELSYNTAX", output)
        self.assertNotIn("SENTINELNOTE", output)
        self.assertIn("SyntaxError", output)
        self.assertIn("Traceback", output)

    def test_J73_cached_exception_text_does_not_bypass_privacy(self):
        stream = self.capture_service()
        try:
            raise RuntimeError("SENTINELCACHEDTEXT")
        except RuntimeError:
            record = logging.getLogger("server_v2.future").makeRecord(
                "server_v2.future", logging.ERROR, __file__, 1, "cached failure", (), None)
            record.exc_text = logging.Formatter().formatException(sys.exc_info())
        logging.getLogger("server_v2.future").handle(record)
        self.assertNotIn("SENTINELCACHEDTEXT", stream.getvalue())
        self.assertIn("cached failure", stream.getvalue())

    def test_J73_mobile_index_warning_uses_partition_without_service_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "data/players/SENTINELSTORE/mobile_events"
            store = FileEventStore(root)
            event = {"eventId": "one", "roundId": "privacy-round", "clientId": "ios",
                     "kind": "score", "hole": 1, "payload": {"strokes": 4}}
            with patch.object(store, "_record_round_index_after_append", side_effect=OSError("unavailable")), \
                 self.assertLogs("ai_caddie.caddie.mobile_event_store", level="WARNING") as captured:
                store.append_batch("privacy-round", [event], request_key="privacy-append")
            output = "\n".join(captured.output)
            self.assertNotIn("SENTINELSTORE", output)
            self.assertRegex(output, r"partition=player:[0-9a-f]{12}")
            self.assertIn("OSError", output)
            self.assertEqual(len(store.read_rows()), 1)

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
        expected = hashlib.sha256(str(directory.resolve()).encode("utf-8")).hexdigest()[:12]
        self.assertIn("partition=player:" + expected, output)

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
