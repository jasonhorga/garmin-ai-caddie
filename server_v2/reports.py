from __future__ import annotations

from pathlib import Path

from ai_caddie.llm_providers import StaticProvider, build_text_provider
from ai_caddie.reports import (
    audit_report_narrative,
    build_report_inferences,
    build_round_report_facts,
    build_trend_report_facts,
    generate_report,
    latest_report_record,
    list_report_records,
    redact_private_text,
    report_source_refs,
    store_report,
)

from .data_source import load_history_data_for_mode
from .history_stats import load_history_stats_response
from .models import ReviewReportIndexResponse, ReviewReportResponse


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
                "inferencesMade": payload.get("inferencesMade"),
            }
        ),
    )
    facts_used = payload.get("factsUsed") if isinstance(payload.get("factsUsed"), list) else []
    missing_data = payload.get("missingData") if isinstance(payload.get("missingData"), list) else []
    payload.setdefault(
        "inferencesMade",
        build_report_inferences(
            [row for row in facts_used if isinstance(row, dict)],
            [row for row in missing_data if isinstance(row, dict)],
            default_confidence=str(payload.get("confidence") or "low"),
        ),
    )
    unsupported_claims = payload.get("unsupportedClaims")
    if not isinstance(unsupported_claims, list):
        unsupported_claims = audit_report_narrative(
            str(payload.get("narrative") or ""),
            [row for row in facts_used if isinstance(row, dict)],
            [row for row in missing_data if isinstance(row, dict)],
        )
        payload["unsupportedClaims"] = unsupported_claims
    payload["factBinding"] = {
        "state": "needs_review" if unsupported_claims else "bound",
        "unsupportedClaimCount": len(unsupported_claims),
    }
    if unsupported_claims:
        payload["confidence"] = "low"
    return ReviewReportResponse(**payload)


def _report_index_item(record: dict[str, object], sequence: int) -> dict[str, object]:
    report = record.get("report")
    report_payload = report if isinstance(report, dict) else {}
    kind = str(report_payload.get("kind") or record.get("kind") or "round")
    subject_id = redact_private_text(report_payload.get("subjectId") or record.get("subjectId") or "")
    source_refs = report_source_refs(
        {
            "sourceRefs": report_payload.get("sourceRefs"),
            "factsUsed": report_payload.get("factsUsed"),
            "missingData": report_payload.get("missingData"),
        }
    )
    return {
        "id": str(record.get("id") or ""),
        "storedAt": str(record.get("storedAt") or ""),
        "sequence": sequence,
        "kind": kind,
        "subjectId": subject_id,
        "confidence": str(report_payload.get("confidence") or "low"),
        "provider": str(report_payload.get("provider") or "unknown"),
        "model": str(report_payload.get("model") or "unknown"),
        "sourceRefs": source_refs,
    }


def load_report_index_response() -> ReviewReportIndexResponse:
    items = [
        _report_index_item(record, sequence)
        for sequence, record in enumerate(list_report_records(root=REPORT_ROOT))
        if isinstance(record, dict)
    ]
    items.sort(key=lambda item: (str(item.get("storedAt") or ""), int(item.get("sequence") or 0)), reverse=True)
    for item in items:
        item.pop("sequence", None)
    return ReviewReportIndexResponse(
        schema="ai-caddie-review-report-index-v1",
        total=len(items),
        reports=items,
    )


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
