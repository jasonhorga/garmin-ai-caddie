from __future__ import annotations

from pathlib import Path

from ai_caddie.llm_providers import StaticProvider, build_text_provider
from ai_caddie.reports import (
    build_round_report_facts,
    build_trend_report_facts,
    generate_report,
    latest_report_record,
    redact_private_text,
    report_source_refs,
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


def _report_response(report: dict[str, object], *, kind: str, subject_id: str) -> ReviewReportResponse:
    payload = dict(report)
    payload.setdefault("kind", kind)
    payload.setdefault("subjectId", redact_private_text(subject_id))
    payload.setdefault(
        "sourceRefs",
        report_source_refs(
            {
                "sourceRefs": payload.get("sourceRefs"),
                "factsUsed": payload.get("factsUsed"),
                "missingData": payload.get("missingData"),
            }
        ),
    )
    return ReviewReportResponse(**payload)


def load_round_report_response(round_id: str) -> ReviewReportResponse:
    stored = latest_report_record("round", round_id, root=REPORT_ROOT)
    if stored and isinstance(stored.get("report"), dict):
        return _report_response(stored["report"], kind="round", subject_id=round_id)
    facts = build_round_report_facts(_history_stats_dict(), round_id, history_data=_history_data())
    report = generate_report(facts, StaticProvider("No generated report stored yet."))
    return _report_response(report, kind="round", subject_id=round_id)


def generate_round_report_response(round_id: str) -> ReviewReportResponse:
    facts = build_round_report_facts(_history_stats_dict(), round_id, history_data=_history_data())
    report = generate_report(facts, build_text_provider())
    store_report(report, kind="round", subject_id=round_id, root=REPORT_ROOT)
    return _report_response(report, kind="round", subject_id=round_id)


def load_trend_report_response(period: str) -> ReviewReportResponse:
    stored = latest_report_record("trend", period, root=REPORT_ROOT)
    if stored and isinstance(stored.get("report"), dict):
        return _report_response(stored["report"], kind="trend", subject_id=period)
    facts = build_trend_report_facts(_history_stats_dict(), period)
    report = generate_report(facts, StaticProvider("No generated trend report stored yet."))
    return _report_response(report, kind="trend", subject_id=period)


def generate_trend_report_response(period: str) -> ReviewReportResponse:
    facts = build_trend_report_facts(_history_stats_dict(), period)
    report = generate_report(facts, build_text_provider())
    store_report(report, kind="trend", subject_id=period, root=REPORT_ROOT)
    return _report_response(report, kind="trend", subject_id=period)
