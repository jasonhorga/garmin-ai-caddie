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
    replay_event_log,
)
from ai_caddie.history.history import OWNER_ID
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
    MobileCourseOptionsResponse,
    RoundStateResponse,
    MobileReconciliationApplyRequest,
    MobileReconciliationApplyResponse,
    MobileReconciliationResponse,
)


MOBILE_ROOT = Path(".")
ANNOTATION_ROOT = Path(".")
DECISION_AUDIT_ROOT = Path(".")
OPEN_METEO_TRANSPORT: WeatherTransport | None = None


def build_mobile_round_package_response(
    round_id: str,
    *,
    captured_at: str | None = None,
    client_id: str | None = None,
    ensure_geometry: bool = False,
    player_id: str = OWNER_ID,
) -> LiveRoundPackageResponse:
    data, mode = load_history_data_for_mode(player_id=player_id)
    return LiveRoundPackageResponse(
        **build_live_round_package(
            round_id,
            data=data,
            data_mode=mode,
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
    player_id: str = OWNER_ID,
) -> LiveRoundPackageResponse:
    data, mode = load_history_data_for_mode(player_id=player_id)
    return LiveRoundPackageResponse(
        **build_live_round_package_for_course(
            global_id,
            round_id=round_id,
            tee_box=tee_box,
            data=data,
            data_mode=mode,
            root=MOBILE_ROOT,
            annotations_root=ANNOTATION_ROOT,
            captured_at=captured_at,
            weather_transport=OPEN_METEO_TRANSPORT,
            client_id=client_id,
            ensure_geometry=ensure_geometry,
            nine=nine,
            back_global_id=back_global_id,
            # Live start must be fast: skip the heavy all-hole course_prep build (per-hole route /
            # hazard point-in-polygon over big meshes). The app fetches per-hole prep on demand
            # (the 2D map + hazards), so the round opens immediately.
            include_course_prep=False,
        )
    )


def build_mobile_course_options_response(player_id: str = OWNER_ID) -> MobileCourseOptionsResponse:
    data, mode = load_history_data_for_mode(player_id=player_id)
    return MobileCourseOptionsResponse(**build_mobile_course_options(data, data_mode=mode))


def append_mobile_events_response(
    round_id: str,
    request: LiveRoundEventBatchRequest,
    *,
    idempotency_key: str,
) -> LiveRoundEventBatchResponse:
    if request.roundId != round_id:
        raise HTTPException(status_code=422, detail="roundId does not match path")
    try:
        result = append_event_batch(
            round_id,
            [event.model_dump(by_alias=True) for event in request.events],
            idempotency_key=idempotency_key,
            root=MOBILE_ROOT,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LiveRoundEventBatchResponse(**result)


def replay_mobile_events_response(
    round_id: str,
    *,
    client_id: str | None = None,
    after_sequence: int | None = None,
    limit: int = 100,
) -> LiveRoundEventReplayResponse:
    return LiveRoundEventReplayResponse(
        **replay_event_log(
            round_id,
            client_id=client_id,
            after_sequence=after_sequence,
            limit=limit,
            root=MOBILE_ROOT,
        )
    )


def round_state_response(round_id: str) -> RoundStateResponse:
    return RoundStateResponse(**build_round_state(round_id, root=MOBILE_ROOT))


def ack_mobile_events_response(round_id: str, request: LiveRoundEventAckRequest) -> LiveRoundEventAckResponse:
    try:
        result = ack_event_cursor(
            round_id,
            client_id=request.clientId,
            server_sequence=request.serverSequence,
            root=MOBILE_ROOT,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LiveRoundEventAckResponse(**result)


def reconcile_mobile_round_response(round_id: str) -> MobileReconciliationResponse:
    data, _mode = load_history_data_for_mode()
    return MobileReconciliationResponse(**reconcile_mobile_round_events(round_id, data, root=MOBILE_ROOT))


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
        )
    )
