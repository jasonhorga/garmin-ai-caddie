from __future__ import annotations

from pathlib import Path

from ai_caddie.history.history import OWNER_ID
from ai_caddie.llm.llm_providers import build_text_provider
from ai_caddie.reports.reports import (
    audit_report_narrative,
    build_club_report_facts,
    build_course_report_facts,
    build_hole_report_facts,
    build_report_inferences,
    build_round_report_facts,
    build_trend_report_facts,
    generate_deterministic_report,
    generate_report,
    iter_report_records,
    latest_report_record,
    redact_private_text,
    report_source_refs,
    store_report,
)

from .data_source import load_history_data_for_mode
from .history_stats import load_history_stats_response
from .models import ReviewReportIndexResponse, ReviewReportResponse


REPORT_ROOT = Path(".")
MEDIA_ROOT = Path(".")


def _history_stats_dict(player_id: str = OWNER_ID) -> dict[str, object]:
    return load_history_stats_response(player_id=player_id).model_dump(by_alias=True)


def _history_data(player_id: str = OWNER_ID):
    data, _mode = load_history_data_for_mode(player_id=player_id)
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


def _facts_with_provider_failure(facts: dict[str, object], exc: Exception) -> dict[str, object]:
    payload = dict(facts)
    missing_data = payload.get("missingData")
    rows = [row for row in missing_data if isinstance(row, dict)] if isinstance(missing_data, list) else []
    rows.append(
        {
            "label": "report_provider",
            "state": "missing",
            "reason": redact_private_text(exc),
        }
    )
    payload["missingData"] = rows
    return payload


def _generate_provider_report_or_fallback(facts: dict[str, object]) -> dict[str, object]:
    try:
        return generate_report(facts, build_text_provider())
    except Exception as exc:
        report = generate_deterministic_report(_facts_with_provider_failure(facts, exc))
        report["confidence"] = "low"
        return report


def load_report_index_response(*, player_id: str = OWNER_ID) -> ReviewReportIndexResponse:
    # The report store is now per-player partitioned (evidence_root): the owner reads the flat store,
    # a member reads ONLY their own partition. A member therefore sees the reports THEY generated and
    # never the owner's (or another member's) index/round ids; a member with none gets an empty index.
    # Owner (OWNER_ID) → the flat store, byte-identical.
    items = [
        _report_index_item(record, sequence)
        for sequence, record in enumerate(iter_report_records(root=REPORT_ROOT, player_id=player_id))
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


def load_round_report_response(round_id: str, *, player_id: str = OWNER_ID) -> ReviewReportResponse:
    # Per-player partitioned: a member reads back ONLY the report THEY generated (their partition);
    # the owner reads the flat store (byte-identical). No stored report → deterministic facts.
    stored = latest_report_record("round", round_id, root=REPORT_ROOT, player_id=player_id)
    if stored and isinstance(stored.get("report"), dict):
        return _report_response(stored["report"], kind="round", subject_id=round_id)
    facts = build_round_report_facts(
        _history_stats_dict(player_id), round_id, history_data=_history_data(player_id)
    )
    report = generate_deterministic_report(facts)
    return _report_response(report, kind="round", subject_id=round_id)


def generate_round_report_response(round_id: str, *, player_id: str = OWNER_ID) -> ReviewReportResponse:
    # Member-scoped: facts are built from the caller's OWN history and the report lands in their
    # evidence partition (evidence_root(player_id)); the owner stays flat / byte-identical.
    facts = build_round_report_facts(_history_stats_dict(player_id), round_id, history_data=_history_data(player_id))
    report = _generate_provider_report_or_fallback(facts)
    store_report(report, kind="round", subject_id=round_id, root=REPORT_ROOT, player_id=player_id)
    return _report_response(report, kind="round", subject_id=round_id)


def _hole_subject_id(course_key: str, hole: int) -> str:
    return f"{course_key}:{hole}"


def load_hole_report_response(course_key: str, hole: int, *, player_id: str = OWNER_ID) -> ReviewReportResponse:
    subject_id = _hole_subject_id(course_key, hole)
    stored = latest_report_record("hole", subject_id, root=REPORT_ROOT, player_id=player_id)
    if stored and isinstance(stored.get("report"), dict):
        return _report_response(stored["report"], kind="hole", subject_id=subject_id)
    facts = build_hole_report_facts(
        _history_stats_dict(player_id),
        course_key,
        hole,
        history_data=_history_data(player_id),
        vision_root=MEDIA_ROOT,
        player_id=player_id,
    )
    report = generate_deterministic_report(facts)
    return _report_response(report, kind="hole", subject_id=subject_id)


def generate_hole_report_response(course_key: str, hole: int, *, player_id: str = OWNER_ID) -> ReviewReportResponse:
    subject_id = _hole_subject_id(course_key, hole)
    facts = build_hole_report_facts(
        _history_stats_dict(player_id),
        course_key,
        hole,
        history_data=_history_data(player_id),
        vision_root=MEDIA_ROOT,
        player_id=player_id,
    )
    report = _generate_provider_report_or_fallback(facts)
    store_report(report, kind="hole", subject_id=subject_id, root=REPORT_ROOT, player_id=player_id)
    return _report_response(report, kind="hole", subject_id=subject_id)


def load_course_report_response(course_key: str, *, player_id: str = OWNER_ID) -> ReviewReportResponse:
    stored = latest_report_record("course", course_key, root=REPORT_ROOT, player_id=player_id)
    if stored and isinstance(stored.get("report"), dict):
        return _report_response(stored["report"], kind="course", subject_id=course_key)
    facts = build_course_report_facts(_history_stats_dict(player_id), course_key)
    report = generate_deterministic_report(facts)
    return _report_response(report, kind="course", subject_id=course_key)


def generate_course_report_response(course_key: str, *, player_id: str = OWNER_ID) -> ReviewReportResponse:
    facts = build_course_report_facts(_history_stats_dict(player_id), course_key)
    report = _generate_provider_report_or_fallback(facts)
    store_report(report, kind="course", subject_id=course_key, root=REPORT_ROOT, player_id=player_id)
    return _report_response(report, kind="course", subject_id=course_key)


def load_club_report_response(club_name: str, *, player_id: str = OWNER_ID) -> ReviewReportResponse:
    stored = latest_report_record("club", club_name, root=REPORT_ROOT, player_id=player_id)
    if stored and isinstance(stored.get("report"), dict):
        return _report_response(stored["report"], kind="club", subject_id=club_name)
    facts = build_club_report_facts(_history_stats_dict(player_id), club_name)
    report = generate_deterministic_report(facts)
    return _report_response(report, kind="club", subject_id=club_name)


def generate_club_report_response(club_name: str, *, player_id: str = OWNER_ID) -> ReviewReportResponse:
    facts = build_club_report_facts(_history_stats_dict(player_id), club_name)
    report = _generate_provider_report_or_fallback(facts)
    store_report(report, kind="club", subject_id=club_name, root=REPORT_ROOT, player_id=player_id)
    return _report_response(report, kind="club", subject_id=club_name)


def load_trend_report_response(period: str, *, player_id: str = OWNER_ID) -> ReviewReportResponse:
    stored = latest_report_record("trend", period, root=REPORT_ROOT, player_id=player_id)
    if stored and isinstance(stored.get("report"), dict):
        return _report_response(stored["report"], kind="trend", subject_id=period)
    facts = build_trend_report_facts(_history_stats_dict(player_id), period)
    report = generate_deterministic_report(facts)
    return _report_response(report, kind="trend", subject_id=period)


def generate_trend_report_response(period: str, *, player_id: str = OWNER_ID) -> ReviewReportResponse:
    facts = build_trend_report_facts(_history_stats_dict(player_id), period)
    report = _generate_provider_report_or_fallback(facts)
    store_report(report, kind="trend", subject_id=period, root=REPORT_ROOT, player_id=player_id)
    return _report_response(report, kind="trend", subject_id=period)
