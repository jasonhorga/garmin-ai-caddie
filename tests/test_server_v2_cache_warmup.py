"""Tests for proactively warming the stats cache after a Garmin sync.

After ``/api/v2/sync/garmin`` lands new scorecards/shots on disk, the stats-cache
fingerprint changes, so the FIRST user request after a sync would otherwise pay the
~10s cold ``build_history_stats`` recompute. We warm the cache on a background thread
right after a successful sync so that first request is already a cache hit.

These are unittest.TestCase tests on purpose: CI runs ``python -m unittest discover``,
which ignores pytest fixtures/conftest/monkeypatch. We test the plain warm function
(``warm_stats_cache``) directly rather than poking at raw threads, and we spy on the
underlying build with ``unittest.mock`` so we can assert a subsequent request is a hit.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ai_caddie import stats_cache
from server_v2.history_stats import (
    load_history_stats_response,
    warm_stats_cache,
    warm_stats_cache_in_background,
)


class CacheWarmupTests(unittest.TestCase):
    def setUp(self) -> None:
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        # Fixture mode keeps the warm fast and deterministic and avoids depending on
        # whatever local data happens to be on disk in CI.
        self._env = patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"})
        self._env.start()
        self.addCleanup(self._env.stop)
        from ai_caddie.config import get_settings

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
            self.assertGreaterEqual(warmed_calls, 1, "warm should have done a cold build")

            # The real user path after a warm must NOT recompute.
            load_history_stats_response()
            self.assertEqual(
                build_spy.call_count,
                warmed_calls,
                "request after warm should be a cache hit (no extra build)",
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


if __name__ == "__main__":
    unittest.main()
