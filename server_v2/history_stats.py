from __future__ import annotations

import logging
import threading
from pathlib import Path

from ai_caddie.stats_cache import cached_build_history_stats, cached_load_history_data

from .data_source import load_history_data_for_mode
from .models import HistoryStatsResponse

DECISION_AUDIT_ROOT = Path(".")

logger = logging.getLogger(__name__)


def load_history_stats_response(window: str = "all") -> HistoryStatsResponse:
    data, mode = load_history_data_for_mode()
    return HistoryStatsResponse(
        **cached_build_history_stats(data, data_mode=mode, decision_audit_root=DECISION_AUDIT_ROOT, window=window)
    )


def warm_stats_cache() -> None:
    """Pre-populate the stats cache so the first request after a sync is a hit.

    Calls the same cached accessors the request path uses: ``cached_load_history_data``
    (the ~2s read) and ``load_history_stats_response`` (the ~10s build, via
    ``cached_build_history_stats``). After this runs, ``/api/v2/history/stats`` and the
    other consumers of the stats cache return instantly until the inputs change again.

    This is purely a pre-population: it never changes the data or the response any
    endpoint would produce. Any failure is swallowed -- a warm must NEVER break the sync
    response or crash the background thread it runs on.
    """
    try:
        cached_load_history_data()
        load_history_stats_response()
    except Exception:  # noqa: BLE001 - warming is best-effort and must not propagate
        logger.exception("stats cache warm failed")


def warm_stats_cache_in_background() -> threading.Thread:
    """Run :func:`warm_stats_cache` on a daemon thread and return it.

    Used after a successful sync so the ~10s recompute happens off the request path and
    does NOT block the ``/api/v2/sync/garmin`` response.
    """
    thread = threading.Thread(target=warm_stats_cache, name="stats-cache-warm", daemon=True)
    thread.start()
    return thread
