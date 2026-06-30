from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ai_caddie.caddie.caddie_context import build_caddie_context
from ai_caddie.history.history import OWNER_ID
from ai_caddie.caddie.decision import (
    audit_decision,
    latest_decision_audit,
    latest_decision_record,
    normalize_decision_audit_id,
    store_decision,
    store_decision_audit,
)
from ai_caddie.caddie.decision_api import build_decision_from_request

from .annotations import ANNOTATION_ROOT
from .data_source import load_history_data_for_mode
from .models import (
    CaddieContextResponse,
    CaddieDecisionAuditLatestResponse,
    CaddieDecisionAuditRecord,
    CaddieDecisionAuditRequest,
    CaddieDecisionAuditStoreResponse,
    CaddieDecisionRequest,
    CaddieDecisionResponse,
)


DECISION_AUDIT_ROOT = Path(".")
DECISION_LEDGER_ROOT = Path(".")
VISION_ROOT = Path(".")
WEATHER_ROOT = Path(".")


def build_caddie_decision_response(
    request: CaddieDecisionRequest, *, player_id: str = OWNER_ID
) -> CaddieDecisionResponse:
    decision = build_decision_from_request(request.model_dump())
    # Member-scoped: the decision lands in the caller's evidence partition (evidence_root(player_id));
    # the owner stays flat / byte-identical.
    store_decision(decision, root=DECISION_LEDGER_ROOT, player_id=player_id)
    return CaddieDecisionResponse(**decision)


def build_caddie_context_response(
    *,
    source_ref: str,
    shot_type: str,
    distance_to_pin_m: float | None = None,
    lie: str | None = None,
    current_latitude: float | None = None,
    current_longitude: float | None = None,
    target_latitude: float | None = None,
    target_longitude: float | None = None,
    strategy_mode: str | None = None,
    start_x: float | None = None,
    start_y: float | None = None,
    target_x: float | None = None,
    target_y: float | None = None,
    landing_radius_m: float = 18.0,
    captured_at: str | None = None,
    player_id: str = OWNER_ID,
) -> CaddieContextResponse:
    data, mode = load_history_data_for_mode(player_id=player_id)
    return CaddieContextResponse(
        **build_caddie_context(
            data,
            source_ref=source_ref,
            shot_type=shot_type,
            distance_to_pin_m=distance_to_pin_m,
            lie=lie,
            data_mode=mode,
            annotations_root=ANNOTATION_ROOT,
            vision_root=VISION_ROOT,
            weather_root=WEATHER_ROOT,
            current_location=_location(current_latitude, current_longitude),
            target_location=_location(target_latitude, target_longitude),
            strategy_mode=strategy_mode,
            route_start=_local_point(start_x, start_y),
            route_target=_local_point(target_x, target_y),
            landing_radius_m=landing_radius_m,
            captured_at=captured_at,
            player_id=player_id,
        )
    )


def _location(latitude: float | None, longitude: float | None) -> dict[str, float | str] | None:
    if latitude is None or longitude is None:
        return None
    return {"latitude": float(latitude), "longitude": float(longitude), "source": "live_input"}


def _local_point(x: float | None, y: float | None) -> dict[str, float] | None:
    if x is None or y is None:
        return None
    return {"x": float(x), "y": float(y)}


def _audit_record(row: dict[str, object] | None) -> CaddieDecisionAuditRecord | None:
    return CaddieDecisionAuditRecord(**row) if row else None


def _actual_audit_input(request: CaddieDecisionAuditRequest) -> dict[str, object] | None:
    if request.actualShots is None and request.actualScoreToPar is None and request.penalty is None:
        return request.actualShot
    payload: dict[str, object] = {}
    if request.actualShots is not None:
        payload["actualShots"] = request.actualShots
    elif request.actualShot is not None:
        payload["actualShots"] = [request.actualShot]
    if request.actualScoreToPar is not None:
        payload["actualScoreToPar"] = request.actualScoreToPar
    if request.penalty is not None:
        payload["penalty"] = request.penalty
    return payload


def _decision_for_audit(
    decision_id: str, request: CaddieDecisionAuditRequest, *, player_id: str = OWNER_ID
) -> dict[str, object]:
    if request.decision is not None:
        return request.decision
    # Re-read the stored decision from the CALLER's partition only: a member resolves their own
    # stored decision (never the owner's — a guessed owner decision_id 404s, no cross-read).
    record = latest_decision_record(decision_id, root=DECISION_LEDGER_ROOT, player_id=player_id)
    if not record or not isinstance(record.get("decision"), dict):
        raise HTTPException(status_code=404, detail="stored decision not found")
    return record["decision"]


def create_decision_audit_response(
    decision_id: str, request: CaddieDecisionAuditRequest, *, player_id: str = OWNER_ID
) -> CaddieDecisionAuditStoreResponse:
    audit = audit_decision(_decision_for_audit(decision_id, request, player_id=player_id), _actual_audit_input(request))
    # Member-scoped: the audit lands in the caller's evidence partition; the owner stays flat.
    record = store_decision_audit(audit, decision_id=decision_id, root=DECISION_AUDIT_ROOT, player_id=player_id)
    return CaddieDecisionAuditStoreResponse(
        schema="ai-caddie-decision-audit-store-v1",
        record=CaddieDecisionAuditRecord(**record),
    )


def latest_decision_audit_response(decision_id: str) -> CaddieDecisionAuditLatestResponse:
    record = latest_decision_audit(decision_id, root=DECISION_AUDIT_ROOT)
    return CaddieDecisionAuditLatestResponse(
        schema="ai-caddie-decision-audit-latest-v1",
        decisionId=normalize_decision_audit_id(decision_id),
        record=_audit_record(record),
    )
