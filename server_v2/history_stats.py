from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from ai_caddie.history.history import OWNER_ID
from ai_caddie.history.mobile_stats import PREVIOUS_WINDOW, build_mobile_previous, build_mobile_stats
from ai_caddie.history.stats_cache import (
    cached_build_history_stats,
    cached_history_stats_snapshot,
    cached_load_history_data,
    history_input_signature,
)
from ai_caddie.core.priority_work import background_work, yield_to_foreground

from .data_source import load_history_data_for_mode
from .models import HistoryStatsResponse, HistoryStatsSummaryResponse, MobileStatsResponse

ANNOTATION_ROOT = Path(".")
WEATHER_ROOT = Path(".")
REPORTS_ROOT = Path(".")
DECISION_AUDIT_ROOT = Path(".")

logger = logging.getLogger(__name__)
_WARM_LOCK = threading.Lock()
# Warming is player-scoped. A member sync must not attach to an owner's in-flight warm and then
# leave the member's first package cold. The per-player map still bounds duplicate work to one
# worker for each data partition.
_WARM_THREADS: dict[str, threading.Thread] = {}
_WARM_FAILURES: dict[str, str] = {}
_WARM_FAILURE_AT: dict[str, float] = {}
WARM_RETRY_DELAY_S = 0.1


def load_history_stats_response(window: str = "all", *, player_id: str = OWNER_ID) -> HistoryStatsResponse:
    data, mode = load_history_data_for_mode(player_id=player_id)
    return HistoryStatsResponse(
        **cached_build_history_stats(
            data,
            data_mode=mode,
            player_id=player_id,
            annotations_root=ANNOTATION_ROOT,
            weather_root=WEATHER_ROOT,
            reports_root=REPORTS_ROOT,
            decision_audit_root=DECISION_AUDIT_ROOT,
            window=window,
        )
    )


def load_history_stats_snapshot(*, player_id: str = OWNER_ID, window: str = "all") -> dict | None:
    """Return an already-built stats projection for liveness probes without doing source I/O."""
    return cached_history_stats_snapshot(player_id=player_id, window=window)


def load_history_summary_response(*, player_id: str = OWNER_ID) -> HistoryStatsSummaryResponse:
    """Slim the full (window=all) stats build down to the 概览 landing needs.

    Reuses the same cached build as ``load_history_stats_response`` (so it is a
    cache hit after warm), then returns only ``summary`` + the top issue label —
    a ~15KB payload instead of the ~20MB full response.
    """
    # Slice the raw cached dict: validating the whole ~20MB HistoryStatsResponse only to read two
    # fields made the home landing pay for the full stats model on every request.
    data, mode = load_history_data_for_mode(player_id=player_id)
    stats = cached_build_history_stats(
        data,
        data_mode=mode,
        player_id=player_id,
        annotations_root=ANNOTATION_ROOT,
        weather_root=WEATHER_ROOT,
        reports_root=REPORTS_ROOT,
        decision_audit_root=DECISION_AUDIT_ROOT,
        window="all",
    )
    top_issue: str | None = None
    issues = stats.get("issues") or []
    if issues and isinstance(issues[0], dict):
        candidate = issues[0].get("issue")
        if isinstance(candidate, str):
            top_issue = candidate
    return HistoryStatsSummaryResponse(
        schema="ai-caddie-history-summary-v1",
        summary=stats.get("summary"),
        topIssue=top_issue,
    )


def load_mobile_stats_response(window: str = "all", *, player_id: str = OWNER_ID) -> MobileStatsResponse:
    """Compact 统计 payload for the phone: the deep / periodic / per-course / per-club slices of the
    stats build, minus the giant per-hole table and heavy refs. ``window`` (all|12m|last20|last10) mirrors
    ``/history/stats`` so the GolfLive 统计 view keeps its windowed KPIs without the ~11MB payload;
    the warm cache pre-builds all four windows, so each stays a cache hit — ``cached_build_history_stats``
    returns the raw dict so ``build_mobile_stats`` slices it with no second Pydantic pass.
    """
    data, mode = load_history_data_for_mode(player_id=player_id)

    def build(selected: str) -> dict:
        return cached_build_history_stats(
            data,
            data_mode=mode,
            player_id=player_id,
            annotations_root=ANNOTATION_ROOT,
            weather_root=WEATHER_ROOT,
            reports_root=REPORTS_ROOT,
            decision_audit_root=DECISION_AUDIT_ROOT,
            window=selected,
        )

    payload = build_mobile_stats(build(window))
    # 表现分析 "和之前比": the previous comparable period rides in the same response (one RTT).
    previous_window = PREVIOUS_WINDOW.get(window)
    if previous_window is not None:
        payload["previous"] = build_mobile_previous(build(previous_window), previous_window)
    return MobileStatsResponse(**payload)


def warm_stats_cache(player_id: str = OWNER_ID) -> bool:
    """Pre-populate the stats cache so the first request after a sync or boot is a hit.

    Calls the same cached accessors the request path uses: ``cached_load_history_data``
    (the ~2s read) and ``load_history_stats_response`` (the ~10s build, via
    ``cached_build_history_stats``). Four windows are pre-warmed, plus the three previous-period
    windows (prev10 / prev20 / prev12m) the mobile 表现分析 response compares against:

    * ``all``   — default for /history/stats, /caddie/context, and the mobile packages
    * ``last10`` — 趋势总览's default range; windowed build sees only 10 rounds (~0.1s extra)
    * ``last20`` — the wider recent-form range; windowed build sees only 20 rounds
    * ``12m``   — used by the 12-month trend view (~1.7s extra on real data)

    After this runs, all four warmed windows and the other consumers of the stats cache
    return instantly until the inputs change again.

    Return True only after every projection succeeds, so a monitor never acknowledges a
    failed or merely scheduled rebuild.

    This is purely a pre-population: it never changes the data or the response any
    endpoint would produce. Any failure is swallowed -- a warm must NEVER break the sync
    response or crash the background thread it runs on.
    """
    # Each phase completes its own single-flight before the next starts; between phases a
    # background warm pauses while a package is live (no-op when not an admitted unit).
    phases = [
        lambda: cached_load_history_data(player_id=player_id),
        lambda: load_history_stats_response(player_id=player_id),
        lambda: load_history_stats_response(window="last10", player_id=player_id),
        lambda: load_history_stats_response(window="last20", player_id=player_id),
        lambda: load_history_stats_response(window="12m", player_id=player_id),
    ]
    # B5 表现分析: each narrow window's mobile response also carries its previous comparable
    # period (prev10 / prev20 / prev12m); build those too so the first analysis is a hit.
    phases += [lambda window=window: load_mobile_stats_response(window=window, player_id=player_id)
               for window in PREVIOUS_WINDOW]
    try:
        for phase in phases:
            yield_to_foreground()
            phase()
    except Exception:  # noqa: BLE001 - warming is best-effort and must not propagate
        logger.exception("stats cache warm failed")
        return False
    return True


def warm_stats_cache_in_background(player_id: str = OWNER_ID) -> threading.Thread | None:
    """Run :func:`warm_stats_cache` on a daemon thread and return it.

    Used after a successful sync so the ~10s recompute happens off the request path and
    does NOT block the ``/api/v2/sync/garmin`` response.
    """
    clean_player_id = str(player_id or OWNER_ID).strip() or OWNER_ID
    if os.getenv("AI_CADDIE_READINESS_TRACE") == "1":
        warm_stats_cache(player_id=clean_player_id)
        return None
    with _WARM_LOCK:
        existing = _WARM_THREADS.get(clean_player_id)
        if existing is not None and existing.is_alive():
            return existing
        retry_at = _WARM_FAILURE_AT.get(clean_player_id, 0.0)
        if clean_player_id in _WARM_FAILURES and time.monotonic() < retry_at:
            return None

        def run() -> None:
            try:
                with background_work(unit_type="stats"):
                    thread.history_signature = history_input_signature(clean_player_id)
                    thread.warm_succeeded = warm_stats_cache(player_id=clean_player_id) is True
                with _WARM_LOCK:
                    if not thread.warm_succeeded:
                        _WARM_FAILURES[clean_player_id] = "stats warm returned false"
                        _WARM_FAILURE_AT[clean_player_id] = time.monotonic() + WARM_RETRY_DELAY_S
                    else:
                        _WARM_FAILURES.pop(clean_player_id, None)
                        _WARM_FAILURE_AT.pop(clean_player_id, None)
            except Exception as exc:  # noqa: BLE001 - background warm must leave a retryable record
                with _WARM_LOCK:
                    _WARM_FAILURES[clean_player_id] = f"{exc.__class__.__name__}: {exc}"
                    _WARM_FAILURE_AT[clean_player_id] = time.monotonic() + WARM_RETRY_DELAY_S
            finally:
                with _WARM_LOCK:
                    if _WARM_THREADS.get(clean_player_id) is threading.current_thread():
                        _WARM_THREADS.pop(clean_player_id, None)

        thread = threading.Thread(
            target=run,
            name=f"stats-cache-warm-{clean_player_id}",
            daemon=True,
        )
        thread.history_signature = None
        thread.warm_succeeded = False
        _WARM_THREADS[clean_player_id] = thread
        thread.start()
        return thread


def history_warm_failure(player_id: str = OWNER_ID) -> str | None:
    """Return the last failed background warm reason until a later warm succeeds."""
    clean_player_id = str(player_id or OWNER_ID).strip() or OWNER_ID
    with _WARM_LOCK:
        return _WARM_FAILURES.get(clean_player_id)


def history_warm_failure_details(player_id: str = OWNER_ID) -> dict[str, object] | None:
    """Return the latest failed warm and timestamp while retries remain enabled."""
    clean_player_id = str(player_id or OWNER_ID).strip() or OWNER_ID
    with _WARM_LOCK:
        reason = _WARM_FAILURES.get(clean_player_id)
        failed_at = _WARM_FAILURE_AT.get(clean_player_id)
    if reason is None:
        return None
    return {"reason": reason, "failedAtMonotonic": failed_at}
