from __future__ import annotations

import logging
import threading
from pathlib import Path

from ai_caddie.history import OWNER_ID
from ai_caddie.stats_cache import cached_build_history_stats, cached_load_history_data

from .data_source import load_history_data_for_mode
from .models import HistoryStatsResponse, HistoryStatsSummaryResponse

DECISION_AUDIT_ROOT = Path(".")

logger = logging.getLogger(__name__)


def load_history_stats_response(window: str = "all", *, player_id: str = OWNER_ID) -> HistoryStatsResponse:
    data, mode = load_history_data_for_mode(player_id=player_id)
    return HistoryStatsResponse(
        **cached_build_history_stats(
            data, data_mode=mode, player_id=player_id, decision_audit_root=DECISION_AUDIT_ROOT, window=window
        )
    )


def load_history_summary_response(*, player_id: str = OWNER_ID) -> HistoryStatsSummaryResponse:
    """Slim the full (window=all) stats build down to the 概览 landing needs.

    Reuses the same cached build as ``load_history_stats_response`` (so it is a
    cache hit after warm), then returns only ``summary`` + the top issue label —
    a ~15KB payload instead of the ~20MB full response.
    """
    stats = load_history_stats_response(window="all", player_id=player_id)
    top_issue: str | None = None
    if stats.issues:
        candidate = stats.issues[0].get("issue")
        if isinstance(candidate, str):
            top_issue = candidate
    return HistoryStatsSummaryResponse(schema="ai-caddie-history-summary-v1", summary=stats.summary, topIssue=top_issue)


def warm_stats_cache() -> None:
    """Pre-populate the stats cache so the first request after a sync or boot is a hit.

    Calls the same cached accessors the request path uses: ``cached_load_history_data``
    (the ~2s read) and ``load_history_stats_response`` (the ~10s build, via
    ``cached_build_history_stats``). Exactly THREE windows are pre-warmed:

    * ``all``   — default for /history/stats, /caddie/context, and the mobile packages
    * ``last10`` — 趋势总览's default range; windowed build sees only 10 rounds (~0.1s extra)
    * ``12m``   — used by the 12-month trend view (~1.7s extra on real data)

    After this runs, all three warmed windows and the other consumers of the stats cache
    return instantly until the inputs change again.

    This is purely a pre-population: it never changes the data or the response any
    endpoint would produce. Any failure is swallowed -- a warm must NEVER break the sync
    response or crash the background thread it runs on.
    """
    try:
        cached_load_history_data()
        load_history_stats_response()
        load_history_stats_response(window="last10")
        load_history_stats_response(window="12m")
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
