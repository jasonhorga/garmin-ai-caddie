"""J7.3: runtime log exits exclude identities, including structured errors.

Discovered once with the J7 product tests; assertions exercise rendered output.
"""
from collections import namedtuple
from decimal import Decimal
import base64
import hashlib
import io
import logging.config
import logging
import sys
import subprocess
import textwrap
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
from ai_caddie.courses import course_prep
from ai_caddie.ops import retention
from server_v2 import main, pin_sheet, render_backfill
from server_v2.models import PinSheetImageIn, PinSheetRequest
from fastapi import HTTPException
from ai_caddie.llm.llm_providers import ProviderConfigurationError
from ai_caddie.llm.pin_sheet_vision import PinSheetReadError
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

    def test_J73_future_handler_guard_has_one_reversible_lifetime(self):
        """J7.3: privacy guards must end with the service that owns their exits."""
        from server_v2.log_privacy import protect_future_handlers

        before = (logging.Logger.addHandler, logging.Logger.callHandlers)
        target = logging.getLogger("ai_caddie.guard_lifetime")
        target.setLevel(logging.WARNING)
        target.propagate = False
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handle = protect_future_handlers()
        self.addCleanup(handle.close)
        installed = (logging.Logger.addHandler, logging.Logger.callHandlers)
        self.assertIs(protect_future_handlers(), handle)
        self.assertEqual(installed, (logging.Logger.addHandler, logging.Logger.callHandlers))
        # Direct list mutation must be covered until the service ends.
        target.handlers[:] = [handler]
        target.warning("player_id=PRIVATEPLAYER")
        self.assertNotIn("PRIVATEPLAYER", stream.getvalue())
        self.assertTrue(handler.filters)
        handle.close()
        handle.close()
        self.assertEqual((logging.Logger.addHandler, logging.Logger.callHandlers), before)
        self.assertEqual(handler.filters, [])
        target.warning("library diagnostic: mesh unreadable")
        self.assertIn("library diagnostic: mesh unreadable", stream.getvalue())
        # Closing an installation must permit a fresh service to start later.
        with protect_future_handlers():
            stream.seek(0)
            stream.truncate()
            target.warning("player_id=PRIVATEPLAYER")
            self.assertNotIn("PRIVATEPLAYER", stream.getvalue())
        self.assertEqual((logging.Logger.addHandler, logging.Logger.callHandlers), before)

    def test_J73_player_partition_hash_survives_service_exit(self):
        """J7.3: the documented 12-hex partition is public, player ids are private."""
        streams = self.capture_production()
        target = logging.getLogger(main.SERVICE_INFO_LOGGERS[0])
        target.warning("partition=player:0123456789ab player_id=PRIVATEPLAYER status=200")
        target.warning("player:0123456789ab partition=player:0123456789abc")
        output = streams[main.SERVICE_INFO_LOGGERS[0]].getvalue()
        self.assertIn("partition=player:0123456789ab player_id=[redacted] status=200", output)
        self.assertNotIn("PRIVATEPLAYER", output)
        self.assertNotIn("partition=player:0123456789abc", output)
        self.assertNotIn("\nWARNING:" + target.name + ":player:0123456789ab", output)

    def test_J73_bearer_credentials_are_private_in_every_spelling(self):
        """J7.3: key/value, serialized dictionaries and bare Bearer all hide tokens."""
        streams = self.capture_production()
        target = logging.getLogger(main.SERVICE_INFO_LOGGERS[0])
        for value in ("Authorization: Bearer PRIVATEBEARER",
                      "authorization=Bearer PRIVATEBEARER",
                      "api_key: Bearer PRIVATEBEARER",
                      {"Authorization": "Bearer PRIVATEBEARER"},
                      "Bearer PRIVATEBEARER"):
            with self.subTest(value=value):
                streams[target.name].seek(0)
                streams[target.name].truncate()
                target.warning("credential=%s status=200", value)
                output = streams[target.name].getvalue()
                self.assertNotIn("PRIVATEBEARER", output)
                self.assertIn("status=200", output)

    def test_J73_cron_other_loggers_redact_root_and_last_resort(self):
        """J7.3: cron protects every ai_caddie exit, including fallback logging."""
        from ai_caddie import pipeline

        root = logging.getLogger()
        root.handlers[:] = []
        target = logging.getLogger("ai_caddie.connectors.privacy_cron")
        target.handlers[:] = []
        target.setLevel(logging.WARNING)
        target.propagate = True
        for parent in (logging.getLogger("ai_caddie.connectors"), logging.getLogger("ai_caddie")):
            parent.handlers[:] = []
            parent.propagate = True
        stream = io.StringIO()
        with patch.object(logging, "lastResort", logging.StreamHandler(stream)):
            pipeline._configure_sync_logging()
            for exit_name in ("lastResort", "root"):
                with self.subTest(exit=exit_name):
                    if exit_name == "root":
                        root.handlers[:] = [logging.StreamHandler(stream)]
                    stream.seek(0)
                    stream.truncate()
                    third_party = logging.getLogger("privacy_cron_vendor")
                    third_party.handlers[:] = []
                    third_party.setLevel(logging.WARNING)
                    third_party.propagate = True
                    sources = [target, third_party]
                    if exit_name == "root":
                        sources.append(root)
                    for source in sources:
                        source.warning("cron failed p_0123456789abcdef token=PRIVATECRON status=200")
                    output = stream.getvalue()
                    self.assertEqual(output.count("cron failed"), len(sources))
                    self.assertEqual(output.count("status=200"), len(sources))
                    self.assertNotIn("p_0123456789abcdef", output)
                    self.assertNotIn("PRIVATECRON", output)

    def test_J73_unhashable_and_nonweak_handlers_remain_safe_and_reversible(self):
        """J7.3: unusual handler identities cannot break or bypass log exits."""
        from server_v2.log_privacy import protect_future_handlers

        class UnhashableHandler(logging.StreamHandler):
            def __eq__(self, other):
                return self is other

            # Handler's fork lock registry also hashes handlers; keep this
            # fixture focused on the privacy guard, not that unrelated registry.
            def createLock(self):
                self.lock = None

        class NonweakHandler:
            __slots__ = ("delegate", "filters", "level")

            def __init__(self, stream):
                self.delegate = logging.StreamHandler(stream)
                self.filters = self.delegate.filters
                self.level = logging.NOTSET

            def addFilter(self, value):
                self.delegate.addFilter(value)

            def removeFilter(self, value):
                self.delegate.removeFilter(value)

            def handle(self, record):
                return self.delegate.handle(record)

        target = logging.getLogger("ai_caddie.unusual_handler")
        target.setLevel(logging.WARNING)
        target.propagate = False
        for handler_type in (UnhashableHandler, NonweakHandler):
            for attachment in ("addHandler", "direct"):
                with self.subTest(handler=handler_type.__name__, attachment=attachment):
                    stream = io.StringIO()
                    handler = handler_type(stream)
                    target.handlers[:] = []
                    with protect_future_handlers():
                        try:
                            if attachment == "addHandler":
                                target.addHandler(handler)
                            else:
                                target.handlers[:] = [handler]
                            target.warning("player_id=PRIVATEHANDLER status=200")
                            target.warning("token=PRIVATEHANDLER status=201")
                        except TypeError as exc:
                            self.fail("privacy guard rejected handler: " + str(exc))
                        self.assertNotIn("PRIVATEHANDLER", stream.getvalue())
                        self.assertIn("status=200", stream.getvalue())
                        self.assertIn("status=201", stream.getvalue())
                    self.assertEqual(handler.filters, [])
                    target.handlers[:] = []

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

    def test_J73_real_course_prep_failure_redacts_bare_player_id(self):
        """J7.3: the production course-prep warning never emits a member id."""
        streams = self.capture_production()
        for player_id in ("p_deadbeef", "p_0123456789abcdef"):
            with self.subTest(player_id=player_id), patch(
                "ai_caddie.history.stats_cache.cached_load_history_data",
                side_effect=RuntimeError("history unavailable"),
            ):
                self.assertIsNone(course_prep._corrected_profile_history(player_id))
        output = streams["lastResort"].getvalue()
        self.assertIn("failed to load corrected profile history", output)
        for player_id in ("p_deadbeef", "p_0123456789abcdef"):
            self.assertNotIn(player_id, output)
        self.assertIn("RuntimeError", output)

    def test_J73_cron_warning_redacts_bare_player_id(self):
        """J7.3: invoke cron main in a fresh interpreter without API startup."""
        script = textwrap.dedent('''
            from contextlib import nullcontext
            from unittest.mock import patch
            import logging
            from ai_caddie import pipeline
            def sync(**kwargs):
                logging.getLogger("ai_caddie.garmin.fetch").warning(
                    "cron failed for p_0123456789abcdef")
                return pipeline.SyncResult(auth_ok=True)
            with patch.object(pipeline, "sync", side_effect=sync), \\
                 patch.object(pipeline, "_persist_sync_observability"), \\
                 patch("ai_caddie.connectors.sync_lock.acquire_sync_lock", return_value=nullcontext()), \\
                 patch("ai_caddie.connectors.snapshot.write_connector_status"):
                raise SystemExit(pipeline.main([]))
        ''')
        result = subprocess.run([sys.executable, "-c", script],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stderr
        self.assertNotIn("p_0123456789abcdef", output)
        self.assertIn("cron failed for [redacted]", output)

    def test_J73_relative_player_path_is_redacted_without_swallowing_fields(self):
        """J7.3: relative player partitions are private while adjacent fields survive."""
        streams = self.capture_production()
        logging.getLogger(main.SERVICE_INFO_LOGGERS[0]).warning(
            "storage path=data/players/p_deadbeef/events status=503 reason=quota")
        output = streams[main.SERVICE_INFO_LOGGERS[0]].getvalue()
        self.assertNotIn("data/players/p_deadbeef/events", output)
        self.assertNotIn("data/players", output)
        self.assertNotIn("p_deadbeef", output)
        self.assertIn("status=503", output)
        self.assertIn("reason=quota", output)

    def test_J73_player_path_without_data_prefix_has_clean_shape(self):
        """J7.3: a relative player path keeps its separators after redaction."""
        streams = self.capture_production()
        logging.getLogger(main.SERVICE_INFO_LOGGERS[0]).warning(
            "storage path=players/p_deadbeef/events status=503 reason=quota")
        output = streams[main.SERVICE_INFO_LOGGERS[0]].getvalue()
        self.assertIn("path=players/[redacted]/events", output)
        self.assertNotIn("p_deadbeef", output)
        self.assertIn("status=503", output)

    def test_J73_oserror_strerror_redacts_private_payload(self):
        """J7.3: retained OSError diagnostics still pass through text redaction."""
        streams = self.capture_production()
        try:
            raise OSError(28, "quota data/players/p_deadbeef token=tok_deadbeef")
        except OSError:
            logging.getLogger(main.SERVICE_INFO_LOGGERS[0]).warning(
                "storage failed", exc_info=True)
        output = streams[main.SERVICE_INFO_LOGGERS[0]].getvalue()
        self.assertIn("[Errno 28]", output)
        self.assertIn("quota", output)
        self.assertNotIn("p_deadbeef", output)
        self.assertNotIn("tok_deadbeef", output)

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

    def test_J73_direct_handlers_list_mutation_is_protected(self):
        """J7.3: appending directly to handlers cannot bypass the exit filter."""
        self.capture_production()
        for name in ("server_v2.direct_handlers", "ai_caddie.direct_handlers", ""):
            for mode in ("append", "extend", "replace", "slice"):
                with self.subTest(logger=name, mode=mode):
                    stream = io.StringIO()
                    target = logging.getLogger(name)
                    target.propagate = False
                    handler = logging.StreamHandler(stream)
                    if mode == "append":
                        target.handlers.append(handler)
                    elif mode == "extend":
                        target.handlers.extend([handler])
                    elif mode == "replace":
                        target.handlers = [handler]
                    else:
                        target.handlers[:] = [handler]
                    source = target if name else logging.getLogger("server_v2.direct_root_child")
                    source.warning("player_id=%s status=200", "PRIVATEPLAYER")
                    self.assertNotIn("PRIVATEPLAYER", stream.getvalue())
                    self.assertIn("status=200", stream.getvalue())

    def test_J73_pin_sheet_failure_keeps_exception_payload_private(self):
        """J7.3: real failure branches retain types, never arbitrary exception text."""
        request = PinSheetRequest(images=[PinSheetImageIn(
            contentBase64=base64.b64encode(b"\xff\xd8\xff\xe0" + b"\0" * 64).decode())])
        for error, status in ((ProviderConfigurationError("PRIVATEPAYLOAD"), 503),
                              (RuntimeError("PRIVATEPAYLOAD"), 502),
                              (PinSheetReadError("PRIVATEPAYLOAD"), 422)):
            with self.subTest(error=type(error).__name__):
                streams = self.capture_production()
                with patch.object(pin_sheet, "build_media_vision_provider", side_effect=error):
                    with self.assertRaises(HTTPException) as caught:
                        pin_sheet.read_pin_sheet_response(request)
                self.assertEqual(caught.exception.status_code, status)
                output = streams["lastResort"].getvalue()
                self.assertNotIn("PRIVATEPAYLOAD", output)
                self.assertIn(type(error).__name__, output)

    def test_J73_backfill_failure_keeps_exception_payload_private(self):
        """J7.3: terminal retries and ordinary render errors reach privacy as exceptions."""
        for retry in (False, True):
            with self.subTest(retry=retry), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                meshes = root / "meshes"
                meshes.mkdir()
                (meshes / "gid1_h01_meshes.json").write_text("{}")
                failure = (render_backfill._RetryRender("PRIVATEPAYLOAD") if retry
                           else RuntimeError("PRIVATEPAYLOAD"))
                def draw(*args):
                    raise failure
                streams = self.capture_production()
                worker = render_backfill.RenderBackfill(
                    state_path=root / "state.json", mesh_root=meshes,
                    topo_ready=lambda *args: False, raster_version=lambda *args: None,
                    render_topo=draw)
                try:
                    with patch.object(worker, "_wait_for_foreground"), \
                         patch.object(render_backfill.time, "sleep"):
                        worker.enqueue_all(recent=set(), downloaded=set())
                        for _ in range(3 if retry else 1):
                            self.assertTrue(worker.run_once())
                    self.assertEqual(worker.status()["failed"], 1)
                finally:
                    worker.close()
                output = streams["lastResort"].getvalue()
                self.assertIn("asset=failed", output)
                self.assertIn(type(failure).__name__, output)
                self.assertIn("gid=1 hole=1", output)
                self.assertNotIn("PRIVATEPAYLOAD", output)

    def test_J73_extras_strings_use_shape_redaction_without_sensitive_key(self):
        """J7.3: non-sensitive extra keys still redact player-shaped values."""
        streams = self.capture_production()
        logging.getLogger(main.SERVICE_INFO_LOGGERS[0]).warning(
            "diagnostic reason=%s", "prep_deadbeef", extra={
                "context": "p_deadbeef",
                "operation": "op_deadbeef",
                "cache": "p_cache",
                "request": "req-0123456789abcdef0123456789abcdef",
                "partition": "main:0123456789ab",
                "job": "garmin-sync-0123456789abcdef",
                "reason": "log_and_backup_mismatch",
                "error_type": "TimeoutError",
                "gid": "public-course-42",
                "hole": 7,
            })
        output = streams[main.SERVICE_INFO_LOGGERS[0]].getvalue()
        self.assertNotIn("'context': 'p_deadbeef'", output)
        for public in ("prep_deadbeef", "op_deadbeef", "p_cache", "req-0123456789abcdef0123456789abcdef",
                       "main:0123456789ab", "garmin-sync-0123456789abcdef",
                       "log_and_backup_mismatch", "TimeoutError", "public-course-42", "'hole': 7"):
            self.assertIn(public, output)

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
