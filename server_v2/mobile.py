from __future__ import annotations

from contextlib import contextmanager
import copy
from datetime import UTC, datetime
import fcntl
from concurrent.futures import Future
import logging
import hashlib
from pathlib import Path
import threading
from typing import Any, Callable, Iterator

from fastapi import HTTPException

from ai_caddie.caddie.mobile_live import (
    ack_event_cursor,
    append_event_batch,
    build_live_round_package,
    build_live_round_package_for_course,
    build_mobile_course_options,
    build_round_state,
    _event_cursor,
    attach_canonical_prep_plan_to_caddie_seeds,
    first_hole_lightweight_course_prep,
    _manual_notes_for_seed,
    replay_event_log,
    round_events,
)
from ai_caddie.history.history import OWNER_ID
from ai_caddie.rounds import round_ingest
from ai_caddie.caddie.mobile_reconciliation import apply_mobile_reconciliation_suggestions, reconcile_mobile_round_events
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
_PACKAGE_SINGLEFLIGHT_LOCK = threading.Lock()
_PACKAGE_SINGLEFLIGHT: dict[tuple[Any, ...], Future[Any]] = {}


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
    # ``cached_load_history_data`` returns the same object for an unchanged file manifest and a new
    # object after a sync/ingest. Include that identity so a package already being built cannot be
    # shared with a caller that observed a freshly materialized, same-id history revision.
    stable_ids = hashlib.blake2b("\x00".join(round_ids).encode("utf-8"), digest_size=16).hexdigest()
    return (id(data), len(rounds), len(shots), stable_ids)


def _package_singleflight(key: tuple[Any, ...], builder: Callable[[], Any]) -> Any:
    with _PACKAGE_SINGLEFLIGHT_LOCK:
        future = _PACKAGE_SINGLEFLIGHT.get(key)
        if future is None:
            future = Future()
            _PACKAGE_SINGLEFLIGHT[key] = future
            leader = True
        else:
            leader = False
    if not leader:
        # The leader owns exception publication too; every waiter receives the same failure and can
        # use its existing offline/error fallback rather than starting another expensive build.
        return future.result()

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
) -> None:
    """Refresh each physical loop's small Garmin release before package coverage is evaluated."""
    from ai_caddie.courses.course_reference import courseview_release_info

    for selected_global_id in dict.fromkeys(int(value) for value in global_ids if int(value) > 0):
        try:
            # Geometry files and release documents live under the canonical repository data root;
            # MOBILE_ROOT only scopes player/event fixtures and may be redirected independently.
            courseview_release_info(selected_global_id, allow_fetch=allow_fetch)
        except Exception:
            # Offline/provider failure keeps the last complete release and precise map usable. A
            # later package request retries without making course start depend on Garmin uptime.
            pass


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
    mark_request_stage("history_load")
    key = (
        "round",
        player_id,
        str(round_id),
        bool(ensure_geometry),
        _package_time_bucket(captured_at),
        _history_package_signature(data),
    )

    def build() -> LiveRoundPackageResponse:
        # The round package is on the first-screen path. Use only already-cached
        # release bytes here; Tee/course-install workers own any zh_CHS refresh
        # so Garmin latency cannot hold the playable package hostage.
        _refresh_course_release_authority(
            _round_release_global_ids(data, round_id),
            allow_fetch=False,
        )
        mark_request_stage("release_lookup")
        return LiveRoundPackageResponse(
            **build_live_round_package(
                round_id,
                data=data,
                data_mode=mode,
                player_id=player_id,
                root=MOBILE_ROOT,
                annotations_root=ANNOTATION_ROOT,
                captured_at=captured_at,
                weather_transport=OPEN_METEO_TRANSPORT,
                client_id=None,
                ensure_geometry=ensure_geometry,
                include_event_cursor=False,
                # The first-screen contract needs recent player carry evidence, not the complete
                # history/geometry quality report. The all-history projection is warmed by the
                # background stats path and remains available to history/review routes.
                stats_window="last20",
            )
        )

    package = _package_singleflight(key, build)
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
    nine: str = "all",
    back_global_id: int | None = None,
    include_event_cursor: bool = True,
    player_id: str = OWNER_ID,
) -> LiveRoundPackageResponse:
    data, mode = load_history_data_for_mode(player_id=player_id)
    mark_request_stage("history_load")
    key = (
        "course",
        player_id,
        int(global_id),
        str(tee_box or ""),
        str(nine),
        int(back_global_id) if back_global_id is not None else None,
        bool(ensure_geometry),
        _package_time_bucket(captured_at),
        _history_package_signature(data),
    )

    def build() -> LiveRoundPackageResponse:
        # Refresh every selected physical loop before historical `ready` or cached precise files are
        # evaluated. This applies equally to played and never-played catalogue courses.
        _refresh_course_release_authority(
            [int(global_id), *([int(back_global_id)] if back_global_id is not None else [])],
            allow_fetch=False,
        )
        mark_request_stage("release_lookup")
        package = build_live_round_package_for_course(
            global_id,
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
            ensure_geometry=ensure_geometry,
            nine=nine,
            back_global_id=back_global_id,
            # The package contract is always a complete 18-hole fact set.  Expensive precise
            # geometry installation remains a separate durable job queued by the route below.
            include_course_prep=False,
            include_event_cursor=False,
            ensure_lightweight=True,
            allow_lightweight_fetch=False,
            # Bound startup CPU to the recent history window. This keeps a cold round from waiting
            # on the full historical per-hole geometry audit; the package records the scope under
            # sourceCoverage.playerStatsWindow.
            stats_window="last20",
            priority_holes=[10] if str(nine).lower() == "back" else [1],
            defer_non_priority_enrichment=True,
        )
        mark_request_stage("facts_package")
        # Keep one immediately drawable factual seed for the first hole while the durable install
        # job prepares precise assets. This is an enrichment detail, never a second package mode.
        package["coursePrep"] = first_hole_lightweight_course_prep(
            package,
            player_id=player_id,
        )
        if package.get("coursePrep"):
            package["caddieContextSeeds"] = attach_canonical_prep_plan_to_caddie_seeds(
                package.get("caddieContextSeeds"),
                package.get("coursePrep"),
            )
        mark_request_stage("caddie_seed")
        return LiveRoundPackageResponse(**package)

    package = _package_singleflight(key, build)
    package = _rebind_course_package_round_identity(
        package,
        round_id,
        captured_at=captured_at,
        player_id=player_id,
    )
    mark_request_stage("serialization")
    return _bind_package_event_cursor(
        package,
        round_id=str(package.roundId),
        client_id=client_id,
        player_id=player_id,
        include_event_cursor=include_event_cursor,
    )


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
    if request.roundId != round_id:
        raise HTTPException(status_code=422, detail="roundId does not match path")
    with _mobile_materialization_lock(player_id):
        try:
            result = append_event_batch(
                round_id,
                [event.model_dump(by_alias=True) for event in request.events],
                idempotency_key=idempotency_key,
                root=MOBILE_ROOT,
                player_id=player_id,
            )
        except ValueError as exc:
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
    return MobileReconciliationResponse(
        **reconcile_mobile_round_events(round_id, data, root=MOBILE_ROOT, player_id=player_id)
    )


def apply_mobile_round_reconciliation_response(
    round_id: str,
    request: MobileReconciliationApplyRequest,
) -> MobileReconciliationApplyResponse:
    data, _mode = load_history_data_for_mode()
    return MobileReconciliationApplyResponse(
        **apply_mobile_reconciliation_suggestions(
            round_id,
            data,
            suggestion_ids=request.suggestionIds,
            root=MOBILE_ROOT,
            annotations_root=ANNOTATION_ROOT,
            decision_audit_root=DECISION_AUDIT_ROOT,
            decision_ledger_root=DECISION_LEDGER_ROOT,
        )
    )
