from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ai_caddie.caddie.mobile_live import (
    ack_event_cursor,
    append_event_batch,
    build_live_round_package,
    build_live_round_package_for_course,
    build_mobile_course_options,
    build_round_state,
    first_hole_lightweight_course_prep,
    replay_event_log,
    round_events,
)
from ai_caddie.history.history import OWNER_ID
from ai_caddie.rounds import round_ingest
from ai_caddie.caddie.mobile_reconciliation import apply_mobile_reconciliation_suggestions, reconcile_mobile_round_events
from ai_caddie.llm.weather_context import WeatherTransport

from .data_source import load_history_data_for_mode
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


def _refresh_course_release_authority(global_ids: list[int]) -> None:
    """Refresh each physical loop's small Garmin release before package coverage is evaluated."""
    from ai_caddie.courses.course_reference import courseview_release_info

    for selected_global_id in dict.fromkeys(int(value) for value in global_ids if int(value) > 0):
        try:
            # Geometry files and release documents live under the canonical repository data root;
            # MOBILE_ROOT only scopes player/event fixtures and may be redirected independently.
            courseview_release_info(selected_global_id, allow_fetch=True)
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
    _refresh_course_release_authority(_round_release_global_ids(data, round_id))
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
            client_id=client_id,
            ensure_geometry=ensure_geometry,
        )
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
    # Refresh every selected physical loop before historical `ready` or cached precise files are
    # evaluated. This applies equally to played and never-played catalogue courses.
    _refresh_course_release_authority(
        [int(global_id), *([int(back_global_id)] if back_global_id is not None else [])]
    )
    data, mode = load_history_data_for_mode(player_id=player_id)
    package = build_live_round_package_for_course(
        global_id,
        round_id=round_id,
        tee_box=tee_box,
        data=data,
        data_mode=mode,
        player_id=player_id,
        root=MOBILE_ROOT,
        annotations_root=ANNOTATION_ROOT,
        captured_at=captured_at,
        weather_transport=OPEN_METEO_TRANSPORT,
        client_id=client_id,
        ensure_geometry=ensure_geometry,
        nine=nine,
        back_global_id=back_global_id,
        # Live start must be fast: skip the heavy all-hole course_prep build (per-hole route /
        # hazard point-in-polygon over big meshes).  One forced-lightweight first-hole seed is
        # attached below so the live screen is factual before precise background work begins.
        include_course_prep=False,
        include_event_cursor=include_event_cursor,
        ensure_lightweight=True,
    )
    package["coursePrep"] = first_hole_lightweight_course_prep(
        package,
        player_id=player_id,
    )
    return LiveRoundPackageResponse(
        **package
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
    return LiveRoundEventBatchResponse(**result)


def finish_mobile_round_response(
    round_id: str,
    request: MobileRoundFinishRequest,
    *,
    player_id: str = OWNER_ID,
) -> RoundIngestResponse:
    try:
        summary = round_ingest.ingest_round(
            player_id,
            round_events(round_id, root=MOBILE_ROOT, player_id=player_id),
            request.meta,
            idempotency_key=f"mobile-finish:{round_id}",
            root=MOBILE_ROOT,
        )
    except round_ingest.RoundIngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
