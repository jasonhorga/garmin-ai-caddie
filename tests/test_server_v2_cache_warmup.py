"""Tests for proactively warming the stats cache after a Garmin sync and at startup.

After ``/api/v2/sync/garmin`` lands new scorecards/shots on disk, the stats-cache
fingerprint changes, so the FIRST user request after a sync would otherwise pay the
~10s cold ``build_history_stats`` recompute. We warm the cache on a background thread
right after a successful sync so that first request is already a cache hit.

The same warm also fires at server startup (FastAPI lifespan) so the very first user
request after a cold boot is already a hit too.

These are unittest.TestCase tests on purpose: CI runs ``python -m unittest discover``,
which ignores pytest fixtures/conftest/monkeypatch. We test the plain warm function
(``warm_stats_cache``) directly rather than poking at raw threads, and we spy on the
underlying build with ``unittest.mock`` so we can assert a subsequent request is a hit.
"""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from unittest.mock import Mock, call, patch

from tests.service_logging import ServiceLoggingIsolationMixin

from fastapi.testclient import TestClient

from ai_caddie.history import stats_cache
from server_v2.history_stats import (
    load_history_stats_response,
    warm_stats_cache,
    warm_stats_cache_in_background,
)


class CacheWarmupTests(ServiceLoggingIsolationMixin, unittest.TestCase):
    def setUp(self) -> None:
        # Earlier tests (round ingest, sync) start best-effort ``prepare-recent-*`` threads that
        # also warm stats. If one is still running, its builds are counted by the spies below.
        # A boot-time warmer may be sleeping through its deferred prep warm; release it first.
        from server_v2 import main as server_main

        server_main._PREP_WARM_DELAY_EVENT.set()
        self.addCleanup(server_main._PREP_WARM_DELAY_EVENT.clear)
        for thread in threading.enumerate():
            if thread.name.startswith("prepare-recent") and thread is not threading.current_thread():
                thread.join(timeout=60)
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        # Fixture mode keeps the warm fast and deterministic and avoids depending on
        # whatever local data happens to be on disk in CI.
        self._env = patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"})
        self._env.start()
        self.addCleanup(self._env.stop)
        from ai_caddie.core.config import get_settings

        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)

    def test_warm_populates_stats_cache_so_next_request_is_a_hit(self) -> None:
        # wraps -> the REAL build runs and returns a valid result (load_history_stats_response
        # constructs HistoryStatsResponse(**...), so a fake dict would fail validation).
        with patch.object(
            stats_cache, "_build_history_stats", wraps=stats_cache._build_history_stats
        ) as build_spy:
            warm_stats_cache()
            warmed_calls = build_spy.call_count
            self.assertEqual(
                warmed_calls, 7,
                "warm should cold-build all + last10 + last20 + 12m + prev10 + prev20 + prev12m",
            )

            # The real user path after a warm must NOT recompute any supported window, including
            # the mobile 表现分析 requests that carry their previous comparable period.
            load_history_stats_response()
            load_history_stats_response(window="last10")
            load_history_stats_response(window="last20")
            load_history_stats_response(window="12m")
            from server_v2.main import app

            client = TestClient(app)
            for window in ("all", "last10", "last20", "12m"):
                self.assertEqual(client.get(f"/api/v2/history/stats/mobile?window={window}").status_code, 200)
            self.assertEqual(
                build_spy.call_count,
                warmed_calls,
                "stats and mobile-analysis requests after warm should be cache hits (no extra build)",
            )

    def test_warm_populates_load_history_data_cache(self) -> None:
        with patch.object(
            stats_cache, "_load_history_data", wraps=stats_cache._load_history_data
        ) as load_spy:
            warm_stats_cache()
            warmed_calls = load_spy.call_count
            self.assertGreaterEqual(warmed_calls, 1, "warm should have loaded history once")

            stats_cache.cached_load_history_data()
            self.assertEqual(
                load_spy.call_count,
                warmed_calls,
                "cached_load_history_data after warm should be a hit",
            )

    def test_warm_swallows_errors_and_never_raises(self) -> None:
        # A warm failure must NEVER break the sync response or crash the thread.
        with patch.object(
            stats_cache, "cached_load_history_data", side_effect=RuntimeError("boom")
        ):
            warm_stats_cache()  # must not raise

    def test_warm_swallows_errors_from_stats_build(self) -> None:
        with patch(
            "server_v2.history_stats.load_history_stats_response",
            side_effect=RuntimeError("boom"),
        ):
            warm_stats_cache()  # must not raise

    def test_background_warm_returns_started_daemon_thread_and_completes(self) -> None:
        with patch.object(
            stats_cache, "_build_history_stats", wraps=stats_cache._build_history_stats
        ) as build_spy:
            thread = warm_stats_cache_in_background()
            self.assertTrue(thread.daemon)
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive(), "warm thread should finish")
            self.assertGreaterEqual(build_spy.call_count, 1)

    def test_background_warm_singleflights_per_player(self) -> None:
        entered = threading.Event()
        release = threading.Event()

        def blocking_warm(*, player_id: str = "me") -> None:
            entered.set()
            self.assertTrue(release.wait(timeout=2))

        with patch("server_v2.history_stats.warm_stats_cache", side_effect=blocking_warm):
            first = warm_stats_cache_in_background(player_id="p-singleflight")
            self.assertTrue(entered.wait(timeout=1))
            second = warm_stats_cache_in_background(player_id="p-singleflight")
            self.assertIs(first, second)
            release.set()
            first.join(timeout=2)

        self.assertFalse(first.is_alive())

    def test_G7_stale_disk_snapshot_is_readable_without_rebuilding_stats(self) -> None:
        """G7: a completed warm remains a bounded readiness snapshot after source revision moves."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"AI_CADDIE_STATS_CACHE_DIR": tmp, "AI_CADDIE_DATA_MODE": "fixture"}):
                warm_stats_cache()
                self.assertTrue(stats_cache.flush_persistent_writes(timeout=10))
                stats_cache.clear()
                with patch.object(stats_cache, "history_source_revision", return_value="new-source-revision"):
                    snapshot = stats_cache.cached_history_stats_snapshot()
                self.assertIsNotNone(snapshot)
                self.assertEqual(snapshot["source"], "disk")
                self.assertTrue(snapshot["stale"])
                self.assertIn("summary", snapshot["value"])

    def test_C263_memory_snapshot_hit_does_not_read_persistent_snapshot_file(self) -> None:
        """C263: readiness's in-memory hit must not deserialize the large disk projection."""
        player_id = "c263-memory-hit"
        key = (player_id, "fixture", ".", ".", ".", ".", "all")
        stats_cache.clear(player_id)
        with stats_cache._lock:
            stats_cache._cache[key] = (("fingerprint",), {"summary": {"totalRounds": 1}})
            stats_cache._cache_source_revisions[key] = "revision-memory"
        try:
            with tempfile.TemporaryDirectory() as tmp, \
                 patch.dict("os.environ", {"AI_CADDIE_STATS_CACHE_DIR": tmp}):
                path = stats_cache._persistent_cache_path(key)
                assert path is not None
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
                with patch.object(stats_cache.Path, "read_text", side_effect=AssertionError("disk snapshot read")):
                    snapshot = stats_cache.cached_history_stats_snapshot(player_id=player_id)
        finally:
            stats_cache.clear(player_id)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["source"], "memory")

    def test_G7_mobile_readiness_does_not_invalidate_warmed_all_stats_with_weather(self) -> None:
        """G7: readiness package probes do not write weather and evict the all-history snapshot."""
        from server_v2.readiness import build_readiness_response

        with patch.object(
            stats_cache, "_build_history_stats", wraps=stats_cache._build_history_stats
        ) as build_spy:
            warm_stats_cache()
            warmed_calls = build_spy.call_count
            payload = build_readiness_response()
            self.assertIn(payload["status"], {"ready", "degraded", "warming"})
            load_history_stats_response()
            self.assertEqual(
                build_spy.call_count,
                warmed_calls,
                "mobile readiness probe must not rewrite weather and invalidate all-history stats",
            )

    def test_G7_history_source_revision_is_captured_before_stats_build(self) -> None:
        """G7: a source mutation during a build leaves the persisted snapshot stale."""
        with tempfile.TemporaryDirectory() as tmp:
            state = ["before-build"]
            original = stats_cache._build_history_stats

            def mutating_build(*args, **kwargs):
                result = original(*args, **kwargs)
                state[0] = "after-build"
                return result

            with patch.dict(os.environ, {"AI_CADDIE_STATS_CACHE_DIR": tmp, "AI_CADDIE_DATA_MODE": "fixture"}), \
                 patch.object(stats_cache, "history_source_revision", side_effect=lambda _player="me": state[0]), \
                 patch.object(stats_cache, "_build_history_stats", side_effect=mutating_build):
                load_history_stats_response()
                self.assertTrue(stats_cache.flush_persistent_writes(timeout=10))
                stats_cache.clear()
                snapshot = stats_cache.cached_history_stats_snapshot()
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot["revision"], "before-build")
            self.assertTrue(snapshot["stale"])


class AppStartupTests(ServiceLoggingIsolationMixin, unittest.TestCase):
    """Tests that server startup fires the background cache warmer."""

    def test_app_startup_triggers_background_warmer_once(self) -> None:
        """FastAPI lifespan invokes the shared background startup entry exactly once.

        Using TestClient as a context manager runs the lifespan (startup + shutdown);
        the patched entry must be called exactly once so the first user request after
        a cold boot is already a cache hit without blocking the server from serving.
        """
        from server_v2.main import app

        with (
            patch.dict(os.environ, {"AI_CADDIE_BOOT_BACKGROUND_WORK": "1"}),
            patch("server_v2.main._start_boot_background_work") as boot,
        ):
            with TestClient(app) as client:
                client.get("/api/v2/health")
            boot.assert_called_once_with()

    def test_background_entry_starts_all_four_workers(self) -> None:
        from server_v2 import main

        resume, prepare, monitor = Mock(), Mock(), Mock()
        with (
            patch.object(main, "warm_stats_cache_in_background") as warm_mock,
            patch.object(main._garmin_sync_jobs, "start") as sync_start,
            patch.object(main, "threading") as threads,
        ):
            threads.Thread.side_effect = [resume, prepare, monitor]
            main._start_boot_background_work()

        warm_mock.assert_called_once_with()
        sync_start.assert_called_once_with(main._run_garmin_sync_job)
        self.assertEqual(threads.Thread.call_args_list[:2], [
            call(target=main.course_install.resume_pending_jobs,
                 name="course-install-resume", daemon=True),
            call(target=main._prepare_recent_bg, args=(main.OWNER_ID,),
                 kwargs={"prep_warm_delay_s": main._boot_prep_warm_delay_s()},
                 name="prepare-recent-boot", daemon=True),
        ])
        self.assertEqual(threads.Thread.call_count, 3)
        resume.start.assert_called_once_with()
        prepare.start.assert_called_once_with()
        monitor.start.assert_called_once_with()

    def test_service_starts_background_work_by_default(self) -> None:
        from server_v2 import main

        with patch.dict(os.environ), patch.object(main, "_start_boot_background_work") as boot:
            os.environ.pop("AI_CADDIE_BOOT_BACKGROUND_WORK", None)
            with TestClient(main.app):
                pass
        boot.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
