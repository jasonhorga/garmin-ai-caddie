from __future__ import annotations

from ai_caddie.llm_providers import StaticProvider, build_text_provider
from ai_caddie.reports import build_round_report_facts, generate_report

from .history_stats import load_history_stats_response
from .models import ReviewReportResponse


def _history_stats_dict() -> dict[str, object]:
    return load_history_stats_response().model_dump(by_alias=True)


def load_round_report_response(round_id: str) -> ReviewReportResponse:
    facts = build_round_report_facts(_history_stats_dict(), round_id)
    report = generate_report(facts, StaticProvider("No generated report stored yet."))
    return ReviewReportResponse(**report)


def generate_round_report_response(round_id: str) -> ReviewReportResponse:
    facts = build_round_report_facts(_history_stats_dict(), round_id)
    report = generate_report(facts, build_text_provider())
    return ReviewReportResponse(**report)
