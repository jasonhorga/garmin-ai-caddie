from __future__ import annotations

from pathlib import Path

from ai_caddie.llm_providers import StaticProvider, build_text_provider
from ai_caddie.reports import (
    build_round_report_facts,
    build_trend_report_facts,
    generate_report,
    latest_report_record,
    store_report,
)

from .data_source import load_history_data_for_mode
from .history_stats import load_history_stats_response
from .models import ReviewReportResponse


REPORT_ROOT = Path(".")


def _history_stats_dict() -> dict[str, object]:
    return load_history_stats_response().model_dump(by_alias=True)


def _history_data():
    data, _mode = load_history_data_for_mode()
    return data


def load_round_report_response(round_id: str) -> ReviewReportResponse:
    stored = latest_report_record("round", round_id, root=REPORT_ROOT)
    if stored and isinstance(stored.get("report"), dict):
        return ReviewReportResponse(**stored["report"])
    facts = build_round_report_facts(_history_stats_dict(), round_id, history_data=_history_data())
    report = generate_report(facts, StaticProvider("No generated report stored yet."))
    return ReviewReportResponse(**report)


def generate_round_report_response(round_id: str) -> ReviewReportResponse:
    facts = build_round_report_facts(_history_stats_dict(), round_id, history_data=_history_data())
    report = generate_report(facts, build_text_provider())
    store_report(report, kind="round", subject_id=round_id, root=REPORT_ROOT)
    return ReviewReportResponse(**report)


def load_trend_report_response(period: str) -> ReviewReportResponse:
    stored = latest_report_record("trend", period, root=REPORT_ROOT)
    if stored and isinstance(stored.get("report"), dict):
        return ReviewReportResponse(**stored["report"])
    facts = build_trend_report_facts(_history_stats_dict(), period)
    report = generate_report(facts, StaticProvider("No generated trend report stored yet."))
    return ReviewReportResponse(**report)


def generate_trend_report_response(period: str) -> ReviewReportResponse:
    facts = build_trend_report_facts(_history_stats_dict(), period)
    report = generate_report(facts, build_text_provider())
    store_report(report, kind="trend", subject_id=period, root=REPORT_ROOT)
    return ReviewReportResponse(**report)
