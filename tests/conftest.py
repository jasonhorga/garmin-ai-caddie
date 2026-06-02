"""Shared pytest fixtures."""

import pytest

from ai_caddie import stats_cache


@pytest.fixture(autouse=True)
def _isolate_stats_cache():
    """The history-stats cache (ai_caddie.stats_cache) is process-global. Clear it
    around every test so a result cached by one test can't leak into another.

    Tests inject in-memory HistoryData that the on-disk fingerprint cannot tell apart
    (same data_mode/roots/size + same disk state -> same cache key). In production the
    data is always loaded from disk and therefore matches the fingerprint, so this
    isolation only matters for tests.
    """
    stats_cache.clear()
    yield
    stats_cache.clear()
