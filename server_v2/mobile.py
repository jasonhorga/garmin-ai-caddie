from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ai_caddie.mobile_live import append_event_batch, build_live_round_package
from ai_caddie.mobile_reconciliation import apply_mobile_reconciliation_suggestions, reconcile_mobile_round_events

from .data_source import load_history_data_for_mode
from .models import (
    LiveRoundEventBatchRequest,
    LiveRoundEventBatchResponse,
    LiveRoundPackageResponse,
    MobileReconciliationApplyRequest,
    MobileReconciliationApplyResponse,
    MobileReconciliationResponse,
)


MOBILE_ROOT = Path(".")
ANNOTATION_ROOT = Path(".")


def build_mobile_round_package_response(round_id: str) -> LiveRoundPackageResponse:
    data, _mode = load_history_data_for_mode()
    return LiveRoundPackageResponse(**build_live_round_package(round_id, data=data, root=MOBILE_ROOT))


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
            [event.model_dump() for event in request.events],
            idempotency_key=idempotency_key,
            root=MOBILE_ROOT,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LiveRoundEventBatchResponse(**result)


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
        )
    )
