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
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.history import stats_cache
from server_v2.history_stats import (
    load_history_stats_response,
    warm_stats_cache,
    warm_stats_cache_in_background,
)


_WARMER_THREAD_NAMES = ("stats-cache-warm", "prepare-recent-boot")


def _drain_background_warmers(timeout: float = 30.0) -> None:
    """Join any lingering lifespan-spawned warmer daemon threads so their ``_build_history_stats``
    calls can't race a build-count spy in these tests. A no-op when none are alive."""
    for thread in threading.enumerate():
        if thread is threading.current_thread():
            continue
        if thread.name in _WARMER_THREAD_NAMES and thread.is_alive():
            thread.join(timeout=timeout)


class CacheWarmupTests(unittest.TestCase):
    def setUp(self) -> None:
        # Any earlier test that used ``TestClient(app)`` as a context manager ran the FastAPI lifespan,
        # which fires REAL background daemon threads ("stats-cache-warm" + "prepare-recent-boot") that
        # call ``_build_history_stats`` and are never joined (production wants fire-and-forget). If one
        # is still building when this file's exact-count ``_build_history_stats`` spy is active, its call
        # inflates the count → the intermittent "4 != 3". Drain those threads first; unittest runs
        # serially, so nothing new starts mid-test and the spy then sees only this test's warm.
        _drain_background_warmers()
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
                warmed_calls, 3, "warm should cold-build ALL THREE pre-warmed windows (all + last10 + 12m)"
            )

            # The real user path after a warm must NOT recompute — for all three
            # pre-warmed windows: all (default), last10 (趋势总览 default), 12m.
            load_history_stats_response()
            load_history_stats_response(window="last10")
            load_history_stats_response(window="12m")
            self.assertEqual(
                build_spy.call_count,
                warmed_calls,
                "all/last10/12m requests after warm should be cache hits (no extra build)",
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


class AppStartupTests(unittest.TestCase):
    """Tests that server startup fires the background cache warmer."""

    def test_app_startup_triggers_background_warmer_once(self) -> None:
        """FastAPI lifespan fires warm_stats_cache_in_background exactly once at boot.

        Using TestClient as a context manager runs the lifespan (startup + shutdown);
        the patched warmer must be called exactly once so the first user request after
        a cold boot is already a cache hit without blocking the server from serving.
        """
        from server_v2.main import app

        with patch("server_v2.main.warm_stats_cache_in_background") as warm_mock:
            with TestClient(app) as client:
                client.get("/api/v2/health")
            warm_mock.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
