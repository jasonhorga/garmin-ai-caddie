from __future__ import annotations

from ai_caddie.decision_api import build_decision_from_request

from .models import CaddieDecisionRequest, CaddieDecisionResponse


def build_caddie_decision_response(request: CaddieDecisionRequest) -> CaddieDecisionResponse:
    decision = build_decision_from_request(request.model_dump())
    return CaddieDecisionResponse(**decision)
