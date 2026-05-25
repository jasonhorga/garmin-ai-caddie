from __future__ import annotations

from pathlib import Path

from ai_caddie.caddie_context import build_caddie_context
from ai_caddie.decision import audit_decision, latest_decision_audit, store_decision_audit
from ai_caddie.decision_api import build_decision_from_request

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


def build_caddie_decision_response(request: CaddieDecisionRequest) -> CaddieDecisionResponse:
    decision = build_decision_from_request(request.model_dump())
    return CaddieDecisionResponse(**decision)


def build_caddie_context_response(
    *,
    source_ref: str,
    shot_type: str,
    distance_to_pin_m: float | None = None,
    lie: str | None = None,
) -> CaddieContextResponse:
    data, _mode = load_history_data_for_mode()
    return CaddieContextResponse(
        **build_caddie_context(
            data,
            source_ref=source_ref,
            shot_type=shot_type,
            distance_to_pin_m=distance_to_pin_m,
            lie=lie,
        )
    )


def _audit_record(row: dict[str, object] | None) -> CaddieDecisionAuditRecord | None:
    return CaddieDecisionAuditRecord(**row) if row else None


def create_decision_audit_response(decision_id: str, request: CaddieDecisionAuditRequest) -> CaddieDecisionAuditStoreResponse:
    audit = audit_decision(request.decision, request.actualShot)
    record = store_decision_audit(audit, decision_id=decision_id, root=DECISION_AUDIT_ROOT)
    return CaddieDecisionAuditStoreResponse(
        schema="ai-caddie-decision-audit-store-v1",
        record=CaddieDecisionAuditRecord(**record),
    )


def latest_decision_audit_response(decision_id: str) -> CaddieDecisionAuditLatestResponse:
    record = latest_decision_audit(decision_id, root=DECISION_AUDIT_ROOT)
    return CaddieDecisionAuditLatestResponse(
        schema="ai-caddie-decision-audit-latest-v1",
        decisionId=decision_id,
        record=_audit_record(record),
    )
