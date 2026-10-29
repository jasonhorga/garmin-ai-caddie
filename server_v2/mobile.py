from __future__ import annotations

from contextlib import contextmanager
import copy
from datetime import UTC, datetime
import fcntl
from concurrent.futures import Future, TimeoutError, wait as wait_futures
import logging
import hashlib
from pathlib import Path
import threading
import time
from typing import Any, Callable, Iterator

from fastapi import HTTPException

from ai_caddie.caddie.mobile_live import (
    InvalidEventError,
    ack_event_cursor,
    append_event_batch,
    build_live_round_package,
    apply_past_round_loop_identity,
    build_live_round_package_for_loops,
    round_loop_key,
    build_mobile_course_options,
    build_round_state,
    _event_cursor,
    attach_canonical_prep_plan_to_caddie_seeds,
    first_hole_lightweight_course_prep,
    _manual_notes_for_seed,
    replay_event_log,
    round_events,
)
from ai_caddie.caddie.mobile_event_store import EventPayloadTooLargeError
from ai_caddie.caddie.round_loops import RoundLoopFactsMissingError
from ai_caddie.history.history import OWNER_ID, HistoryData
from ai_caddie.history.corrected_history import corrected_history_data
from ai_caddie.rounds import round_ingest, score_invariant
from ai_caddie.rounds.correction_audit import CorrectionConflict, IdentityUnavailable
from ai_caddie.caddie.mobile_reconciliation import apply_mobile_reconciliation_suggestions, reconcile_mobile_round_events
from ai_caddie.caddie.mobile_round_identity import MobileRoundIdentityError, save_mobile_round_identity
from ai_caddie.llm.weather_context import WeatherTransport, weather_snapshot_for_time

from .data_source import load_history_data_for_mode
from .history_stats import warm_stats_cache_in_background
from .timing import mark as mark_request_stage
from .models import (
    LiveRoundEventBatchRequest,
    LiveRoundEventBatchResponse,
    LiveRoundEventAckRequest,
    LiveRoundEventAckResponse,
    LiveRoundEventReplayResponse,
    LiveRoundPackageResponse,
    MobileRoundFinishRequest,
    MobileCourseOptionsResponse,
    RoundIngestResponse,
    RoundStateResponse,
    MobileReconciliationApplyRequest,
    MobileReconciliationApplyResponse,
    MobileReconciliationResponse,
)


MOBILE_ROOT = Path(".")
ANNOTATION_ROOT = Path(".")
DECISION_AUDIT_ROOT = Path(".")
DECISION_LEDGER_ROOT = Path(".")
OPEN_METEO_TRANSPORT: WeatherTransport | None = None
logger = logging.getLogger(__name__)


# Phone and Watch commonly request the same course package at the same time. The package is a
# read-only projection for the duration of a request, so followers can share the leader's result
# without introducing a persistent/stale response cache. This protects the single API worker from
# duplicate stats/strategy CPU while retaining the existing complete-package contract.
PACKAGE_FOLLOWER_WAIT_SECONDS = 1.0
_PACKAGE_SINGLEFLIGHT_LOCK = threading.Lock()
_PACKAGE_SINGLEFLIGHT: dict[tuple[Any, ...], Future[Any]] = {}

# A never-installed course has no cached Garmin release, and the loop resolver needs that release's
# hole count. The release and its courseData are two small documents (a few hundred ms from
# Garmin), so a cold start fetches them in the foreground. 8 s bounds a slow provider while leaving
# the iPhone's 30 s start deadline (SyncClient.roundStartTimeoutInterval) for the package build
# itself; geometry, rasters and topo remain the background job's work.
COLD_RELEASE_FETCH_TIMEOUT_SECONDS = 8.0
COLD_RELEASE_RETRY_AFTER_SECONDS = 2
_COLD_RELEASE_LOCK = threading.Lock()
_COLD_RELEASE_FETCHES: dict[int, Future[bool]] = {}


def _package_time_bucket(captured_at: str | None) -> str:
    """Use a short bucket for concurrent requests without making weather permanently stale."""
    value = str(captured_at or "").strip()
    if value:
        return value[:16]
    return datetime.now(UTC).replace(second=0, microsecond=0).isoformat()


def _history_package_signature(data: object) -> tuple[Any, ...]:
    rounds = getattr(data, "rounds", None) or []
    shots = getattr(data, "shots", None) or []
    round_ids = tuple(str(row.get("id") or "") for row in rounds if isinstance(row, dict))
    stable_ids = hashlib.blake2b("\x00".join(round_ids).encode("utf-8"), digest_size=16).hexdigest()
    return (
        len(rounds), len(shots), stable_ids,
        getattr(data, "source_fingerprint", None),
        getattr(data, "correction_fingerprint", None),
    )


def _package_singleflight(key: tuple[Any, ...], builder: Callable[[], Any], *,
                          fallback: Callable[[], Any] | None = None) -> Any:
    with _PACKAGE_SINGLEFLIGHT_LOCK:
        future = _PACKAGE_SINGLEFLIGHT.get(key)
        if future is None:
            future = Future()
            _PACKAGE_SINGLEFLIGHT[key] = future
            leader = True
        else:
            leader = False
    if not leader:
        # Share the leader's result when it is available promptly. A slow leader continues
        # independently while the follower reads a cached map/pending projection.
        mark_request_stage("singleflight_wait")
        try:
            return future.result(timeout=PACKAGE_FOLLOWER_WAIT_SECONDS)
        except TimeoutError:
            if fallback is None:
                raise
            mark_request_stage("singleflight_pending")
            value = fallback()
            value.sourceCoverage = {**value.sourceCoverage, "state": "degraded"}
            value.offlinePackageStatus = {**value.offlinePackageStatus, "state": "degraded",
                                          "cacheable": False, "degradationReason": "singleflight_timeout"}
            return value

    try:
        value = builder()
    except BaseException as exc:
        future.set_exception(exc)
        raise
    else:
        future.set_result(value)
        return value
    finally:
        with _PACKAGE_SINGLEFLIGHT_LOCK:
            if _PACKAGE_SINGLEFLIGHT.get(key) is future:
                del _PACKAGE_SINGLEFLIGHT[key]


def _bind_package_event_cursor(
    package: LiveRoundPackageResponse,
    *,
    round_id: str,
    client_id: str | None,
    player_id: str,
    include_event_cursor: bool,
) -> LiveRoundPackageResponse:
    if not include_event_cursor:
        return package
    # The expensive package body is shared across phone/Watch callers, but the cursor is explicitly
    # client-scoped. Bind it after single-flight so one device can never receive another device's ACK
    # state while still sharing the CPU-heavy 18-hole projection.
    return package.model_copy(
        update={
            "eventCursor": _event_cursor(
                round_id,
                root=MOBILE_ROOT,
                client_id=client_id,
                player_id=player_id,
            )
        }
    )


def _rebind_course_package_round_identity(
    package: LiveRoundPackageResponse,
    round_id: str | None,
    *,
    captured_at: str | None = None,
    player_id: str = OWNER_ID,
) -> LiveRoundPackageResponse:
    """Attach a caller's round identity after sharing the course-fact projection.

    Course packages contain reusable map/club/history facts, while ``roundId`` and seed
    ``sourceRef`` values are runtime identities. Keeping those layers separate lets two devices or
    two rounds share one CPU-heavy build without leaking event cursors or writing a seed under the
    wrong round. The event cursor itself is rebound separately by ``_bind_package_event_cursor``.
    """
    requested = str(round_id or "").strip()
    if not requested or requested == str(package.roundId):
        return package
    payload = copy.deepcopy(package.model_dump(by_alias=True))
    previous = str(payload.get("roundId") or "")
    payload["roundId"] = requested
    source_coverage = payload.get("sourceCoverage")
    if isinstance(source_coverage, dict):
        source_coverage["requestedRoundId"] = requested

    def replace_runtime_ref(value: Any) -> Any:
        text = str(value or "")
        if previous and text == previous:
            return requested
        if previous and text.startswith(f"{previous}:"):
            return f"{requested}{text[len(previous):]}"
        return value

    def rebind_seed(value: Any, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return {
                child_key: rebind_seed(child_value, child_key)
                for child_key, child_value in value.items()
            }
        if isinstance(value, list):
            return [rebind_seed(item, key) for item in value]
        if key in {"roundId", "sourceRef"} and isinstance(value, str):
            return replace_runtime_ref(value)
        return value

    seeds = payload.get("caddieContextSeeds")
    if isinstance(seeds, list):
        rebound_seeds = [rebind_seed(seed) for seed in seeds]
        # The shared course projection intentionally has no caller round identity. Rehydrate only
        # the small player/round evidence layer after single-flight: this keeps map/stats/geometry
        # CPU shared while preserving owner/member isolation for annotations and cached weather.
        weather_by_hole: dict[int, dict[str, Any]] = {}
        for seed in rebound_seeds:
            if not isinstance(seed, dict):
                continue
            try:
                hole = int(seed.get("hole") or 0)
            except (TypeError, ValueError):
                hole = 0
            if hole <= 0:
                continue
            context = dict(seed.get("context") or {})
            notes = _manual_notes_for_seed(
                annotations_root=ANNOTATION_ROOT,
                round_id=requested,
                hole_ref=f"{requested}:{hole}",
                player_id=player_id,
            )
            if notes:
                context["manualNotes"] = notes
            else:
                context.pop("manualNotes", None)
            snapshot = weather_snapshot_for_time(
                requested,
                hole,
                captured_at=captured_at,
                root=MOBILE_ROOT,
                exact_hole=True,
                player_id=player_id,
            )
            if snapshot is not None:
                weather_by_hole[hole] = snapshot
                seed["weatherSnapshot"] = snapshot
                context["weatherSnapshot"] = snapshot
            seed["context"] = context
        payload["caddieContextSeeds"] = rebound_seeds

        top_snapshot = weather_snapshot_for_time(
            requested,
            captured_at=captured_at,
            root=MOBILE_ROOT,
            exact_hole=False,
            player_id=player_id,
        )
        if top_snapshot is not None:
            holes = [
                int(row.get("number") or 0)
                for row in payload.get("holes") or []
                if isinstance(row, dict) and int(row.get("number") or 0) > 0
            ]
            coverage_rows = []
            for hole in holes:
                snapshot = weather_by_hole.get(hole)
                row: dict[str, Any] = {
                    "hole": hole,
                    "sourceRef": f"{requested}:{hole}",
                    "state": "ready" if snapshot else "missing",
                }
                if snapshot:
                    row["capturedAt"] = snapshot.get("capturedAt")
                    row["source"] = snapshot.get("source")
                coverage_rows.append(row)
            ready = sum(1 for row in coverage_rows if row["state"] == "ready")
            total = len(coverage_rows)
            payload["weatherSnapshot"] = {
                **top_snapshot,
                "coverage": {
                    "ready": ready,
                    "total": total,
                    "pct": round((ready / total) * 100.0, 1) if total else 0.0,
                },
                "holeCoverage": coverage_rows,
            }
    return LiveRoundPackageResponse(**payload)


@contextmanager
def _mobile_materialization_lock(player_id: str) -> Iterator[None]:
    """Serialize a player's event snapshots and shared history index across workers."""
    directory = (
        Path(MOBILE_ROOT)
        / "data"
        / "players"
        / player_id
        / "mobile_events"
    )
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "materialization.lock").open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _refresh_course_release_authority(
    global_ids: list[int],
    *,
    allow_fetch: bool = True,
) -> list[int]:
    """Refresh each physical loop's small Garmin release before package coverage is evaluated.

    Returns the ids that have no release afterwards (for a cache-only read: not cached).
    """
    from ai_caddie.courses.course_reference import courseview_release_info

    missing: list[int] = []
    for selected_global_id in dict.fromkeys(int(value) for value in global_ids if int(value) > 0):
        try:
            # Geometry files and release documents live under the canonical repository data root;
            # MOBILE_ROOT only scopes player/event fixtures and may be redirected independently.
            if not courseview_release_info(selected_global_id, allow_fetch=allow_fetch):
                missing.append(selected_global_id)
        except Exception:
            # Offline/provider failure keeps the last complete release and precise map usable. A
            # later package request retries without making course start depend on Garmin uptime.
            missing.append(selected_global_id)
    return missing


def _fetch_cold_course_release(global_id: int) -> bool:
    """Fetch one uncached release and its courseData; True when Garmin was unavailable."""
    from ai_caddie.courses.course_reference import (
        courseview_release_fetch_failed,
        courseview_release_info,
    )
    from server_v2.map_startup import ensure_startup_course_data

    started = time.perf_counter()
    try:
        # The release fetch shares the refresh lock with the background vector bootstrap; whichever
        # runs second re-reads the cache instead of issuing another Garmin request.
        if courseview_release_info(global_id, allow_fetch=True):
            ensure_startup_course_data(global_id)
            failed = False
        else:
            # No release: either Garmin has no such layout (a fact) or the provider failed.
            failed = courseview_release_fetch_failed(global_id)
    except Exception:
        logger.warning("course_package cold_release_failed gid=%s", global_id, exc_info=True)
        failed = True
    logger.info("course_package cold_release gid=%s duration_ms=%.1f provider_failed=%s",
                global_id, (time.perf_counter() - started) * 1000, failed)
    return failed


def _uncached_release_ids(global_ids: list[int]) -> list[int]:
    from ai_caddie.courses.course_reference import courseview_release_info

    return [
        gid
        for gid in dict.fromkeys(int(value) for value in global_ids if int(value) > 0)
        if not courseview_release_info(gid, allow_fetch=False)
    ]


def _ensure_cold_course_releases(global_ids: list[int]) -> list[int]:
    """Fetch the missing release (and its courseData) of each given course within one deadline.

    A course whose release is already cached is read from disk only: no refresh and no provider
    request is added. Returns the ids that are worth retrying: their release missed the deadline
    (the fetch continues in the background so a retried start finds the cache) or Garmin failed.
    A course Garmin answered as unknown is not returned; its loops stay a 422.
    """
    missing = _uncached_release_ids(global_ids)
    if not missing:
        return []
    futures: dict[int, Future[bool]] = {}
    for gid in missing:
        with _COLD_RELEASE_LOCK:
            future = _COLD_RELEASE_FETCHES.get(gid)
            leader = future is None
            if leader:
                future = Future()
                _COLD_RELEASE_FETCHES[gid] = future
        if leader:
            # A plain daemon thread, not the geometry pool: a cold release must never queue behind
            # geometry work, and the thread outlives a timed-out request to finish filling the cache.
            def run(gid: int = gid, future: Future[bool] = future) -> None:
                failed = True
                try:
                    failed = _fetch_cold_course_release(gid)
                finally:
                    with _COLD_RELEASE_LOCK:
                        if _COLD_RELEASE_FETCHES.get(gid) is future:
                            del _COLD_RELEASE_FETCHES[gid]
                    future.set_result(failed)

            try:
                threading.Thread(target=run, name=f"cold-release-{gid}", daemon=True).start()
            except Exception as exc:
                # Without this the future never completes and every later start of the course
                # would wait on it; a failed start is an outage of this attempt, retryable.
                with _COLD_RELEASE_LOCK:
                    if _COLD_RELEASE_FETCHES.get(gid) is future:
                        del _COLD_RELEASE_FETCHES[gid]
                future.set_exception(exc)
                logger.warning("course_package cold_release_thread_failed gid=%s", gid, exc_info=True)
        futures[gid] = future
    wait_futures(list(futures.values()), timeout=COLD_RELEASE_FETCH_TIMEOUT_SECONDS)
    retryable = [
        gid
        for gid in _uncached_release_ids(missing)
        if not futures[gid].done() or futures[gid].exception() is not None or futures[gid].result()
    ]
    if retryable:
        logger.warning("course_package release_pending gids=%s budget_s=%s",
                       retryable, COLD_RELEASE_FETCH_TIMEOUT_SECONDS)
    return retryable


def _build_course_package_with_cold_releases(
    build: Callable[[], LiveRoundPackageResponse],
) -> LiveRoundPackageResponse:
    """Build from cached facts; a never-installed loop gets its release once, then a rebuild.

    The package build reads releases from cache only. Since the vector bootstrap runs in the
    background, a course seen for the first time has no release to prove its loops and the build
    reports missing facts. Only that case waits for the release: a cached or history-proven course
    keeps its cache-only start with no added provider request, and a request that contradicts a
    known shape (``:all`` on an 18-hole course) is never a reason to call Garmin. The uncached
    ids come from inside the single-flight build, so concurrent phone/Watch starts still share one
    build and observe one snapshot.
    """
    try:
        return build()
    except RoundLoopFactsMissingError as exc:
        cold = list(getattr(exc, "uncached_release_ids", ()))
        if not cold:
            raise
    pending = _ensure_cold_course_releases(cold)
    mark_request_stage("cold_release")
    try:
        return build()
    except RoundLoopFactsMissingError as exc:
        if not pending:
            raise
        # The loops are unproven only because Garmin has not delivered a release yet. Its fetch
        # keeps running, so this is a retryable start rather than an invalid request. The iPhone
        # start shows "暂时无法开始,稍后重试" for any HTTP error (no automatic start retry);
        # the Watch retries its package request on its own.
        raise HTTPException(
            status_code=503,
            detail=f"course_release_pending: Garmin release for {pending} is still loading; retry",
            headers={"Retry-After": str(COLD_RELEASE_RETRY_AFTER_SECONDS)},
        ) from exc


def _round_release_global_ids(data: object, round_id: str) -> list[int]:
    rows = getattr(data, "rounds", []) or []
    requested = str(round_id)
    row = next(
        (
            candidate
            for candidate in rows
            if requested
            in {
                str(candidate.get("id") or ""),
                *(str(value) for value in (candidate.get("ids") or [])),
            }
        ),
        None,
    )
    if not isinstance(row, dict):
        return []
    values = [
        row.get("frontNineGlobalCourseId"),
        row.get("backNineGlobalCourseId"),
        row.get("globalId") or row.get("courseGlobalId") or row.get("courseId"),
    ]
    result: list[int] = []
    for value in values:
        try:
            global_id = int(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if global_id > 0 and global_id not in result:
            result.append(global_id)
    return result


def build_mobile_round_package_response(
    round_id: str,
    *,
    captured_at: str | None = None,
    client_id: str | None = None,
    ensure_geometry: bool = False,
    player_id: str = OWNER_ID,
) -> LiveRoundPackageResponse:
    data, mode = load_history_data_for_mode(player_id=player_id)
    data = corrected_history_data(data, player_id=player_id, annotations_root=ANNOTATION_ROOT)
    mark_request_stage("history_load")
    key = (
        "round",
        player_id,
        str(round_id),
        bool(ensure_geometry),
        _package_time_bucket(captured_at),
        _history_package_signature(data),
    )

    def build(*, cache_only: bool = False) -> LiveRoundPackageResponse:
        # The round package is on the first-screen path. Use only already-cached
        # release bytes here; Tee/course-install workers own any zh_CHS refresh
        # so Garmin latency cannot hold the playable package hostage.
        _refresh_course_release_authority(
            _round_release_global_ids(data, round_id),
            allow_fetch=False,
        )
        mark_request_stage("release_lookup")
        package = build_live_round_package(
            round_id,
            data=data,
            data_mode=mode,
            player_id=player_id,
            root=MOBILE_ROOT,
            annotations_root=ANNOTATION_ROOT,
            captured_at=captured_at,
            weather_transport=OPEN_METEO_TRANSPORT,
            client_id=None,
            ensure_geometry=ensure_geometry and not cache_only,
            include_event_cursor=False,
            # The first-screen contract needs recent player carry evidence, not the complete
            # history/geometry quality report. The all-history projection is warmed by the
            # background stats path and remains available to history/review routes.
            stats_window="last20",
            **({"map_only": True} if cache_only else {}),
        )
        # A past round names its loops only from durable facts (v2 contract); an unprovable
        # order is an explicit degraded package, never a guess from cache availability.
        package = apply_past_round_loop_identity(package)
        # Resuming an existing round used to omit CoursePrep entirely. The phone then had to
        # request one hole at a time after every swipe, so holes 2+ rendered a base bitmap with
        # no factual centreline until the request completed. Keep the same cheap, release-bound
        # route seeds as a new-course start; precise topo/hazard installation remains asynchronous.
        package["coursePrep"] = first_hole_lightweight_course_prep(
            package,
            player_id=player_id,
            **({"map_only": True} if cache_only else {}),
        )
        if package.get("coursePrep"):
            package["caddieContextSeeds"] = attach_canonical_prep_plan_to_caddie_seeds(
                package.get("caddieContextSeeds"),
                package.get("coursePrep"),
            )
        mark_request_stage("caddie_seed")
        return LiveRoundPackageResponse(**package)

    package = _package_singleflight(key, build, fallback=lambda: build(cache_only=True))
    _persist_mobile_package_identity(package, player_id=player_id)
    mark_request_stage("serialization")
    return _bind_package_event_cursor(
        package,
        round_id=str(round_id),
        client_id=client_id,
        player_id=player_id,
        include_event_cursor=True,
    )


def build_mobile_course_package_response(
    global_id: int,
    *,
    round_id: str | None = None,
    tee_box: str | None = None,
    captured_at: str | None = None,
    client_id: str | None = None,
    ensure_geometry: bool = False,
    loops: list[tuple[int, str]],
    include_event_cursor: bool = True,
    player_id: str = OWNER_ID,
    prepare_map: bool = False,
    priority_hole: int = 1,
    map_only: bool = False,
) -> LiveRoundPackageResponse:
    if prepare_map:
        from server_v2.map_startup import prepare_priority_hole

        prepare_priority_hole(loops, priority_hole=priority_hole, tee_box=tee_box, wait=False)
        mark_request_stage("priority_vector")
    if map_only:
        from ai_caddie.core.config import get_settings

        data = HistoryData(raw_rounds=[], rounds=[], shots=[])
        mode = "fixture" if get_settings().data_mode == "fixture" else "local"
    else:
        data, mode = load_history_data_for_mode(player_id=player_id)
        if isinstance(data, HistoryData) and not data.corrected:
            data = corrected_history_data(data, player_id=player_id, annotations_root=ANNOTATION_ROOT)
    mark_request_stage("history_load")
    key = (
        "course",
        player_id,
        int(global_id),
        str(tee_box or ""),
        # The ordered loop identity: 前→前 / 前→后 / 后→前 / 后→后 never share a result.
        round_loop_key(loops),
        bool(ensure_geometry),
        bool(map_only),
        int(priority_hole),
        _package_time_bucket(captured_at),
        ("deferred",) if map_only else _history_package_signature(data),
    )

    def build(*, cache_only: bool = False) -> LiveRoundPackageResponse:
        # Refresh every selected physical loop before historical `ready` or cached precise files are
        # evaluated. This applies equally to played and never-played catalogue courses. The
        # uncached ids are observed here, before the template reads the cache: a release that lands
        # mid-build still counts as cold for this attempt.
        uncached = _refresh_course_release_authority(
            list(dict.fromkeys(int(gid) for gid, _ in loops)),
            allow_fetch=False,
        )
        mark_request_stage("release_lookup")
        try:
            package = build_live_round_package_for_loops(
                loops,
                # The shared projection deliberately has no caller-specific round identity. It is
                # rebound after the single-flight result is obtained below.
                round_id=None,
                tee_box=tee_box,
                data=data,
                data_mode=mode,
                player_id=player_id,
                root=MOBILE_ROOT,
                annotations_root=ANNOTATION_ROOT,
                captured_at=captured_at,
                weather_transport=OPEN_METEO_TRANSPORT,
                client_id=None,
                ensure_geometry=ensure_geometry and not cache_only,
                # The package contract is always a complete 18-hole fact set.  Expensive precise
                # geometry installation remains a separate durable job queued by the route below.
                include_course_prep=False,
                include_event_cursor=False,
                ensure_lightweight=True,
                allow_lightweight_fetch=False,
                # Bound startup CPU to the recent history window. This keeps a cold round from
                # waiting on the full historical per-hole geometry audit; the package records the
                # scope under sourceCoverage.playerStatsWindow.
                stats_window="last20",
                defer_non_priority_enrichment=True,
                map_only=map_only or cache_only,
            )
        except RoundLoopFactsMissingError as exc:
            # Single-flight followers receive this same exception object, snapshot included.
            exc.uncached_release_ids = tuple(uncached)
            raise
        mark_request_stage("facts_package")
        # Keep immediately drawable factual CourseView seeds for every playable hole while the
        # durable install job prepares precise assets. This is an enrichment detail, never a
        # second package mode; it prevents later holes from showing a blank route while batches
        # are still downloading.
        package["coursePrep"] = first_hole_lightweight_course_prep(
            package,
            player_id=player_id,
            **({"map_only": True} if map_only or cache_only else {}),
        )
        if package.get("coursePrep"):
            package["caddieContextSeeds"] = attach_canonical_prep_plan_to_caddie_seeds(
                package.get("caddieContextSeeds"),
                package.get("coursePrep"),
            )
        mark_request_stage("caddie_seed")
        return LiveRoundPackageResponse(**package)

    package = _build_course_package_with_cold_releases(
        lambda: _package_singleflight(key, build, fallback=lambda: build(cache_only=True)),
    )
    mark_request_stage("rebind")
    package = _rebind_course_package_round_identity(
        package,
        round_id,
        captured_at=captured_at,
        player_id=player_id,
    )
    # Course downloads without a caller round id are templates, not live round starts.
    if round_id:
        _persist_mobile_package_identity(package, player_id=player_id)
    mark_request_stage("serialization")
    return _bind_package_event_cursor(
        package,
        round_id=str(package.roundId),
        client_id=client_id,
        player_id=player_id,
        include_event_cursor=include_event_cursor,
    )


def _persist_mobile_package_identity(package: LiveRoundPackageResponse, *, player_id: str) -> None:
    if not package.roundLoops:
        return
    try:
        @contextmanager
        def _timed_lock() -> Iterator[None]:
            mark_request_stage("persist_lock")
            with _mobile_materialization_lock(player_id):
                mark_request_stage("persist_write")
                yield

        save_mobile_round_identity(
            str(package.roundId), [row.model_dump() for row in package.roundLoops],
            package.loopKey, package.holes, root=MOBILE_ROOT, player_id=player_id,
            event_lock=_timed_lock,
        )
    except MobileRoundIdentityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def build_mobile_course_options_response(player_id: str = OWNER_ID) -> MobileCourseOptionsResponse:
    data, mode = load_history_data_for_mode(player_id=player_id)
    return MobileCourseOptionsResponse(**build_mobile_course_options(data, data_mode=mode))


def append_mobile_events_response(
    round_id: str,
    request: LiveRoundEventBatchRequest,
    *,
    idempotency_key: str,
    player_id: str = OWNER_ID,
) -> LiveRoundEventBatchResponse:
    from ai_caddie.core.request_timing import mark

    mark("event_request")
    if request.roundId != round_id:
        logger.warning("mobile_events validation_failed status=422 path=body.roundId type=path_mismatch")
        raise HTTPException(status_code=422, detail="roundId does not match path")
    events = [event.model_dump(by_alias=True) for event in request.events]
    with _mobile_materialization_lock(player_id):
        mark("event_materialization_lock_wait")
        try:
            result = append_event_batch(
                round_id,
                events,
                idempotency_key=idempotency_key,
                root=MOBILE_ROOT,
                player_id=player_id,
                # Spec 5.7: every hole this append scores must stay possible, checked inside the
                # store's lock on its own deduplicated rows; otherwise nothing of the batch is stored.
                validate_append=score_invariant.require_possible_appended_scores,
            )
        except InvalidEventError as exc:
            # A round-envelope mismatch is batch-wide even if a record also has bad content.
            if any(event.roundId != round_id for event in request.events):
                raise HTTPException(status_code=422, detail="event roundId does not match path") from exc
            logger.warning("mobile_events validation_failed status=422 path=body.events type=event_invalid")
            raise HTTPException(status_code=422, detail={"code": "event_invalid", "message": str(exc)}) from exc
        except score_invariant.ScoreInvariantError as exc:
            # A score invariant violation belongs to one event's content. The locked append
            # validator has rejected the whole request before any row or reservation is written;
            # the client may bisect the request and quarantine this singleton.
            logger.warning("mobile_events validation_failed status=422 path=body.events type=event_invalid")
            raise HTTPException(status_code=422, detail={"code": "event_invalid", "message": str(exc)}) from exc
        except EventPayloadTooLargeError as exc:
            logger.warning("mobile_events validation_failed status=422 path=body.events type=event_payload_too_large")
            raise HTTPException(
                status_code=422,
                detail={"code": "event_payload_too_large", "message": str(exc)},
            ) from exc
        except ValueError as exc:
            logger.warning("mobile_events validation_failed status=422 path=body.events type=event_batch_invalid")
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # If another device already finished this round, the append itself is the earliest reliable
        # moment to refresh history. This also covers an upgraded legacy Watch queue that relays
        # through the phone and never owns the newer standalone model's explicit finish retry.
        try:
            refreshed = round_ingest.refresh_ingested_round_if_exists(
                player_id,
                load_events=lambda: round_events(
                    round_id,
                    root=MOBILE_ROOT,
                    player_id=player_id,
                ),
                idempotency_key=f"mobile-finish:{round_id}",
                root=MOBILE_ROOT,
            )
            if isinstance(refreshed, dict) and not refreshed.get("idempotent", False):
                warm_stats_cache_in_background(player_id=player_id)
        except Exception:
            # append_event_batch already committed and fsynced. Never lie to the client that its
            # accepted event failed merely because the derived history view needs a later retry.
            logger.exception("late-event history refresh failed for round %s", round_id)
    return LiveRoundEventBatchResponse(**result)


def finish_mobile_round_response(
    round_id: str,
    request: MobileRoundFinishRequest,
    *,
    player_id: str = OWNER_ID,
) -> RoundIngestResponse:
    with _mobile_materialization_lock(player_id):
        try:
            summary = round_ingest.ingest_round(
                player_id,
                round_events(round_id, root=MOBILE_ROOT, player_id=player_id),
                request.meta,
                idempotency_key=f"mobile-finish:{round_id}",
                root=MOBILE_ROOT,
                # A phone may finish before an offline Watch uploads its last facts. Repeated finish
                # is still a no-op for the same event revision, but a larger append-only stream must
                # refresh the existing history row instead of acknowledging a permanently stale one.
                refresh_existing_events=True,
            )
        except round_ingest.RoundIngestError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not summary.get("idempotent", False):
        # A completed live round changes the player's stats fingerprint. Start the same bounded
        # background warm used by Garmin sync so the next round does not pay the cold rebuild.
        warm_stats_cache_in_background(player_id=player_id)
    return RoundIngestResponse(**summary)


def replay_mobile_events_response(
    round_id: str,
    *,
    client_id: str | None = None,
    after_sequence: int | None = None,
    limit: int = 100,
    player_id: str = OWNER_ID,
) -> LiveRoundEventReplayResponse:
    return LiveRoundEventReplayResponse(
        **replay_event_log(
            round_id,
            client_id=client_id,
            after_sequence=after_sequence,
            limit=limit,
            root=MOBILE_ROOT,
            player_id=player_id,
        )
    )


def round_state_response(round_id: str, *, player_id: str = OWNER_ID) -> RoundStateResponse:
    return RoundStateResponse(**build_round_state(round_id, root=MOBILE_ROOT, player_id=player_id))


def ack_mobile_events_response(round_id: str, request: LiveRoundEventAckRequest, *, player_id: str = OWNER_ID) -> LiveRoundEventAckResponse:
    try:
        result = ack_event_cursor(
            round_id,
            client_id=request.clientId,
            server_sequence=request.serverSequence,
            root=MOBILE_ROOT,
            player_id=player_id,
        )
    except ValueError as exc:
        status_code = 409 if str(exc) == "consumer_ack_ahead_of_stream" else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LiveRoundEventAckResponse(**result)


def reconcile_mobile_round_response(round_id: str, player_id: str = OWNER_ID) -> MobileReconciliationResponse:
    data, _mode = load_history_data_for_mode(player_id=player_id)
    try:
        return MobileReconciliationResponse(
            **reconcile_mobile_round_events(round_id, data, root=MOBILE_ROOT, player_id=player_id)
        )
    except MobileRoundIdentityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def apply_mobile_round_reconciliation_response(
    round_id: str,
    request: MobileReconciliationApplyRequest,
    *,
    player_id: str = OWNER_ID,
) -> MobileReconciliationApplyResponse:
    # Concurrency: the batch is ordered, and already applied sourceSuggestionIds skipped, outside the
    # player's audit lock; each annotation write then re-checks its hole under the lock. A concurrent
    # edit of the same hole can therefore leave the first rows written and fail a later one (422, or
    # 503 if the state cannot be read); every written row kept its hole possible. A retry with the same
    # suggestionIds skips the written rows by sourceSuggestionId and orders the rest on the current
    # card, so it ends with each fix written once, or the same 422 while the card still forbids it.
    # Racing applies use the same clientMutationId: the locked writer returns the stored annotation
    # for identical content and rejects different content with 409. Only the creating writer emits
    # a caddie decision audit.
    data, _mode = load_history_data_for_mode(player_id=player_id)
    try:
        applied = apply_mobile_reconciliation_suggestions(
            round_id,
            data,
            suggestion_ids=request.suggestionIds,
            root=MOBILE_ROOT,
            annotations_root=ANNOTATION_ROOT,
            decision_audit_root=DECISION_AUDIT_ROOT,
            decision_ledger_root=DECISION_LEDGER_ROOT,
            player_id=player_id,
            data_loader=lambda: load_history_data_for_mode(player_id=player_id)[0],
        )
    except (CorrectionConflict, MobileRoundIdentityError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except score_invariant.ScoreInvariantError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        # A selected suggestion the annotation store refuses; checked before any write.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IdentityUnavailable as exc:
        # Nothing was written; the client retries the same selection later.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return MobileReconciliationApplyResponse(**applied)
