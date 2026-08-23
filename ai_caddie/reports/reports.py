from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

from ai_caddie.history.history import HistoryData
from ai_caddie.llm.llm_providers import LLMMessage, TextProvider, redact_secret_text
from ai_caddie.core.data import OWNER_ID, evidence_root
from ai_caddie.reports.report_labels_zh import (
    audit_class_zh,
    audit_status_zh,
    data_label_zh,
    form_direction_zh,
    issue_label_zh,
    trend_dimension_zh,
)
from ai_caddie.llm.vision_context import list_findings_for_target


def redact_private_text(text: object) -> str:
    return redact_secret_text(text)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_private_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_value(item) for key, item in value.items()}
    return value


def _fact(
    label: str,
    value: Any,
    source: str,
    *,
    source_refs: list[str] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "label": label,
        "value": value,
        "source": source,
    }
    refs = _unique_strings([*(source_refs or []), *_metadata_source_refs(value)])
    if refs:
        row["sourceRefs"] = refs
    coverage = _metadata_coverage(value)
    if coverage:
        row["coverage"] = coverage
    confidence = _metadata_confidence(value)
    if confidence:
        row["confidence"] = confidence
    provenance_summary = _provenance_summary(provenance)
    if provenance_summary:
        row["provenance"] = provenance_summary
    return row


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _source_refs_from_provenance(provenance: Any) -> list[str]:
    if not isinstance(provenance, dict):
        return []
    refs = provenance.get("sourceRefs")
    if isinstance(refs, list):
        return _unique_strings(refs)
    return []


def _provenance_summary(provenance: Any) -> dict[str, Any] | None:
    if not isinstance(provenance, dict):
        return None
    keys = [
        "sourceConnector",
        "snapshotId",
        "sourceRecordType",
        "sourceRecordId",
        "sourceRecordIds",
        "parentRecordId",
        "sourceFiles",
        "sourceRefs",
        "confidence",
        "status",
        "normalizedAt",
    ]
    summary = {key: provenance[key] for key in keys if key in provenance}
    return summary or None


def _source_refs_from_fact_values(values: list[dict[str, Any]]) -> list[str]:
    return _unique_strings(
        [
            source_ref
            for value in values
            for source_ref in _as_string_list(value.get("sourceRefs"))
        ]
    )


def _metadata_source_refs(value: Any) -> list[str]:
    if isinstance(value, dict):
        for key in ("sourceRefs", "roundRefs", "roundIds", "holeRefs", "shotRefs", "refs"):
            refs = value.get(key)
            if isinstance(refs, list):
                return _unique_strings(refs)
        return []
    if isinstance(value, list):
        return _unique_strings(
            [
                source_ref
                for item in value
                for source_ref in _metadata_source_refs(item)
            ]
        )
    return []


_SOURCE_REF_KEYS = {
    "sourceRef",
    "sourceRefs",
    "refs",
    "roundRef",
    "roundRefs",
    "roundIds",
    "auditedRoundRefs",
    "holeRef",
    "holeRefs",
    "shotRef",
    "shotRefs",
    "actualShotRefs",
    "evidenceRefs",
    "missingDataRef",
    "missingDataRefs",
    "baselineRefs",
    "recentRefs",
}

_UNSUPPORTED_CLAIM_RULES = {
    "weather": {
        "keywords": ("weather", "wind", "rain", "temperature", "precipitation", "gust"),
    },
    "lie": {
        "keywords": ("lie", "stance", "slope", "blocked view", "rough", "fairway", "bunker"),
    },
    "penalty": {
        "keywords": ("penalty", "penalties", "ob", "out of bounds", "water"),
    },
    "club": {
        "keywords": ("club", "driver", "wood", "iron", "wedge", "putter", "hybrid"),
    },
    "practice_advice": {
        "keywords": ("practice", "drill", "train", "lesson", "work on"),
    },
    "strategy_advice": {
        "keywords": ("should", "recommend", "aim", "lay up", "attack", "safe", "conservative", "aggressive"),
    },
    "causal_claim": {
        "keywords": ("cause", "because", "due to", "reason", "costing strokes", "led to"),
    },
}

_CLUB_TOKEN_PATTERN = re.compile(r"\b(?:[1-9]i|[1-9]w|[1-9]h|pw|gw|sw|lw|1d)\b", re.IGNORECASE)
_CLAIM_FRAGMENT_SPLIT_PATTERN = re.compile(r"\s*(?:;|\bbut\b|\bhowever\b|\byet\b)\s*", re.IGNORECASE)
_CATEGORY_MENTION_PATTERNS = {
    "weather": re.compile(r"\b(weather|wind|rain|temperature|precipitation|gusts?)\b", re.IGNORECASE),
    "lie": re.compile(r"\b(lie|stance|slope|blocked view|rough|fairway|bunker)\b", re.IGNORECASE),
    "penalty": re.compile(r"\b(penalt(?:y|ies)|ob|out of bounds|water)\b", re.IGNORECASE),
    "club": re.compile(r"\b(club|driver|wood|iron|wedge|putter|hybrid)\b", re.IGNORECASE),
    "practice_advice": re.compile(
        r"\b(practice|drills?|training|train|lesson|work on|range session)\b",
        re.IGNORECASE,
    ),
    "strategy_advice": re.compile(
        r"\b(should|recommend(?:ed|ation)?|aim|lay up|layup|attack|safe|safer|conservative|aggressive|"
        r"play away|play short|play long|take less|take more|target)\b",
        re.IGNORECASE,
    ),
    "causal_claim": re.compile(
        r"\b(cause[sd]?|because|due to|reason|cost(?:ing)? strokes?|strokes? lost|led to|leads to)\b",
        re.IGNORECASE,
    ),
}
_WEATHER_FACT_KEYS = {
    "weather",
    "weathersnapshot",
    "windspeedmps",
    "winddirectiondeg",
    "temperaturec",
    "precipitationmm",
    "rain",
    "gust",
}
_LIE_FACT_KEYS = {"lie", "surface", "stance", "slope", "blockedview", "endlie", "resultlie"}
_PENALTY_FACT_KEYS = {"penalty", "penalties", "hazard", "hazards", "nearrisks", "avoidzones", "forbiddenzones"}
_CLUB_FACT_KEYS = {"club", "clubname", "recommendedclub", "actualclub", "selectedclub"}
_LIE_VALUE_TOKENS = {"rough", "fairway", "bunker", "green", "fringe", "tee", "sand", "blocked", "slope"}
_PENALTY_VALUE_TOKENS = {"penalty", "penalties", "water", "ob", "hazard", "bunker"}
_WEATHER_VALUE_TOKENS = {"weather", "wind", "rain", "temperature", "precipitation", "gust"}
_CLUB_WORD_TOKENS = {"driver", "wood", "iron", "wedge", "putter", "hybrid", "club"}
_PRACTICE_SUPPORT_TERMS = {"practice", "drill", "training", "lesson"}
_STRATEGY_ACTION_TERMS = {
    "recommend",
    "aim",
    "lay up",
    "layup",
    "attack",
    "safe",
    "safer",
    "conservative",
    "aggressive",
    "play away",
    "play short",
    "play long",
    "take less",
    "take more",
    "target",
}
_STRATEGY_MODAL_TOKENS = {"should", "recommend", "recommended", "recommendation"}
_CAUSAL_CUE_TOKENS = {"cause", "caused", "because", "due_to", "reason", "costing_strokes", "strokes_lost", "led_to", "leads_to"}
_CAUSAL_CLASSIFICATION_TOKENS = {"strategy", "execution", "information_gap", "info_gap"}
_MISSING_CALLOUT_TERMS = (
    "missing",
    "unavailable",
    "not recorded",
    "not cached",
    "no data",
    "unknown",
    "uncertain",
    "lack",
    "lacking",
    # Chinese equivalents
    "缺失",
    "不可用",
    "未记录",
    "无数据",
    "未知",
    "不确定",
    "缺少",
)


def report_source_refs(value: Any) -> list[str]:
    refs: list[Any] = []

    def walk(current: Any, key_hint: str = "") -> None:
        if isinstance(current, list):
            if key_hint in _SOURCE_REF_KEYS:
                refs.extend(current)
                return
            for item in current:
                walk(item)
            return

        if isinstance(current, str) and key_hint in _SOURCE_REF_KEYS:
            refs.append(current)
            return

        if not isinstance(current, dict):
            return

        for key, item in current.items():
            if key in _SOURCE_REF_KEYS:
                if isinstance(item, list):
                    refs.extend(item)
                else:
                    refs.append(item)
            else:
                walk(item, key)

    walk(value)
    return _unique_strings(refs)


def _metadata_coverage(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and isinstance(value.get("coverage"), dict):
        return dict(value["coverage"])
    return None


def _metadata_confidence(value: Any) -> str | None:
    if isinstance(value, dict) and value.get("confidence") is not None:
        return str(value["confidence"])
    return None


def _with_stat_metadata(value: dict[str, Any], source: Any) -> dict[str, Any]:
    if not isinstance(source, dict):
        return value
    for key in ("sourceRefs", "coverage", "confidence"):
        if key in source:
            value[key] = source[key]
    return value


def build_round_report_facts(
    history_stats: dict[str, Any],
    round_id: str,
    *,
    history_data: HistoryData | None = None,
) -> dict[str, Any]:
    summary = history_stats.get("summary") if isinstance(history_stats.get("summary"), dict) else {}
    scoring = history_stats.get("scoring") if isinstance(history_stats.get("scoring"), dict) else {}
    data_quality = history_stats.get("dataQuality") if isinstance(history_stats.get("dataQuality"), list) else []
    drill_down = history_stats.get("drillDown") if isinstance(history_stats.get("drillDown"), dict) else {}
    all_round_ids = [str(item) for item in drill_down.get("roundIds", [])] if isinstance(drill_down.get("roundIds"), list) else []

    facts_used = [
        _fact("total_rounds", summary.get("totalRounds"), "summary.totalRounds"),
        _fact("average_18", summary.get("average18"), "summary.average18"),
        _fact("best_score", summary.get("bestScore"), "summary.bestScore"),
    ]
    round_row = _find_round(history_data, round_id)
    if round_row:
        round_provenance = round_row.get("provenance")
        round_source_refs = _source_refs_from_provenance(round_provenance)
        facts_used.append(
            _fact(
                "round_scorecard",
                _round_scorecard_fact(round_row),
                "history.rounds",
                source_refs=round_source_refs,
                provenance=round_provenance if isinstance(round_provenance, dict) else None,
            )
        )
        facts_used.append(
            _fact(
                "round_hole_outcomes",
                _round_hole_outcomes(round_row),
                "history.rounds.holes",
                source_refs=round_source_refs,
                provenance=round_provenance if isinstance(round_provenance, dict) else None,
            )
        )
        round_shots = _round_shot_facts(history_data, round_id)
        if round_shots:
            facts_used.append(
                _fact(
                    "round_shots",
                    round_shots,
                    "history.shots",
                    source_refs=_source_refs_from_fact_values(round_shots),
                )
            )

    putting = scoring.get("putting") if isinstance(scoring.get("putting"), dict) else {}
    if putting:
        facts_used.append(
            _fact(
                "putting",
                {
                    "totalPutts": putting.get("totalPutts"),
                    "threePutts": putting.get("threePutts"),
                    "threePuttRefs": putting.get("threePuttRefs", []),
                },
                "scoring.putting",
            )
        )
    for phase in scoring.get("phaseStats", []) if isinstance(scoring.get("phaseStats"), list) else []:
        if isinstance(phase, dict) and phase.get("phase"):
            facts_used.append(_fact(f"phase_{phase.get('phase')}", phase, "scoring.phaseStats"))
    course_distribution = history_stats.get("courseDistribution")
    if isinstance(course_distribution, list) and course_distribution:
        facts_used.append(_fact("course_distribution", course_distribution[:5], "courseDistribution"))
    records = history_stats.get("records")
    if isinstance(records, dict) and records:
        facts_used.append(_fact("record_book", _record_book_fact(records), "records"))
    issues = history_stats.get("issues")
    if isinstance(issues, list) and issues:
        top_issue = sorted(
            [issue for issue in issues if isinstance(issue, dict)],
            key=lambda issue: int(issue.get("count") or 0),
            reverse=True,
        )[:1]
        if top_issue:
            facts_used.append(_fact("top_issue", top_issue[0], "issues"))
        round_issues = _round_issue_facts(issues, round_id)
        if round_issues:
            facts_used.append(_fact("round_issues", round_issues, "issues"))

    round_issue_trends = _round_diagnosis_issue_trends(history_stats, round_id)
    if round_issue_trends:
        facts_used.append(
            _fact(
                "round_diagnosis_issue_trends",
                round_issue_trends,
                "diagnosis.issueTrends",
                source_refs=report_source_refs(round_issue_trends),
            )
        )

    round_decision_audits = _round_decision_audit_facts(history_stats, round_id)
    if round_decision_audits:
        facts_used.append(
            _fact(
                "round_decision_audits",
                round_decision_audits,
                "diagnosis.decisionAuditTrends",
                source_refs=report_source_refs(round_decision_audits),
            )
        )

    for band in scoring.get("scoreBands", []) if isinstance(scoring.get("scoreBands"), list) else []:
        if not isinstance(band, dict):
            continue
        round_ids = _as_string_list(band.get("roundRefs") or band.get("roundIds") or band.get("refs"))
        if str(round_id) in round_ids:
            facts_used.append(
                _fact(
                    "round_score_band",
                    {"label": band.get("label"), "count": band.get("count"), "roundRefs": round_ids},
                    "scoring.scoreBands",
                )
            )

    missing_data: list[dict[str, Any]] = []
    if str(round_id) not in all_round_ids:
        missing_data.append({"label": "round_reference", "reason": f"{round_id} 不在 drillDown.roundIds 中"})
    if history_data is not None and not round_row:
        missing_data.append({"label": "round_scorecard", "reason": f"{round_id} 不在标准化历史数据中"})
    missing_data.extend(_missing_data_quality_rows(data_quality))

    return {
        "schema": "ai-caddie-report-facts-v1",
        "kind": "round",
        "subjectId": str(round_id),
        "factsUsed": facts_used,
        "missingData": missing_data,
    }


def _find_round(history_data: HistoryData | None, round_id: str) -> dict[str, Any] | None:
    if history_data is None:
        return None
    requested = str(round_id)
    for row in history_data.rounds:
        ids = {str(row.get("id") or ""), *(str(item) for item in (row.get("ids") or []))}
        if requested in ids:
            return row
    return None


def _round_numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric


def _round_differential_value(score: Any, rating: Any, slope: Any) -> float | None:
    score_value = _round_numeric(score)
    rating_value = _round_numeric(rating)
    slope_value = _round_numeric(slope)
    if score_value is None or rating_value is None or slope_value is None or slope_value <= 0:
        return None
    return round((score_value - rating_value) * 113.0 / slope_value, 1)


def _round_scorecard_fact(round_row: dict[str, Any]) -> dict[str, Any]:
    score = round_row.get("strokes")
    par = round_row.get("par")
    rating = _round_numeric(round_row.get("rating"))
    slope = _round_numeric(round_row.get("slope"))
    return {
        "roundRef": str(round_row.get("id")),
        "date": round_row.get("date"),
        "course": round_row.get("course"),
        "courseKey": round_row.get("courseKey"),
        "holesCompleted": round_row.get("holesCompleted"),
        "score": score,
        "par": par,
        "toPar": int(score) - int(par) if isinstance(score, int) and isinstance(par, int) else None,
        "rating": rating,
        "slope": slope,
        "differential": _round_differential_value(score, rating, slope),
        "putts": round_row.get("putts"),
        "hasShots": round_row.get("hasShots"),
        "shotStatus": round_row.get("shotStatus"),
    }


def _round_hole_outcomes(round_row: dict[str, Any]) -> list[dict[str, Any]]:
    round_ref = str(round_row.get("id"))
    hole_pars = str(round_row.get("holePars") or "")
    outcomes: list[dict[str, Any]] = []
    for index, hole in enumerate(round_row.get("holes") or [], start=1):
        if not isinstance(hole, dict):
            continue
        number = int(hole.get("number") or index)
        par = hole.get("par")
        if not isinstance(par, int) and 1 <= number <= len(hole_pars):
            try:
                par = int(hole_pars[number - 1])
            except ValueError:
                par = None
        score = hole.get("strokes")
        outcomes.append(
            {
                "holeRef": f"{round_ref}:{number}",
                "hole": number,
                "strokes": score,
                "par": par,
                "toPar": int(score) - int(par) if isinstance(score, int) and isinstance(par, int) else None,
                "putts": hole.get("putts"),
                "fairway": hole.get("fairway"),
                "gir": hole.get("gir"),
            }
        )
    return outcomes


def _round_shot_facts(history_data: HistoryData | None, round_id: str) -> list[dict[str, Any]]:
    if history_data is None:
        return []
    requested = str(round_id)
    rows: list[dict[str, Any]] = []
    for index, shot in enumerate(history_data.shots):
        shot_round_id = shot.get("roundId")
        if shot_round_id is None:
            shot_round_id = shot.get("scorecardId")
        if str(shot_round_id) != requested:
            continue
        rows.append(
            _with_row_provenance(
                {
                    "shotRef": f"{shot_round_id}:{shot.get('hole')}:{index}",
                    "hole": shot.get("hole"),
                    "club": shot.get("club") or shot.get("clubName"),
                    "distance": shot.get("distance") or shot.get("meters"),
                    "surface": shot.get("surface") or shot.get("endLie"),
                },
                shot.get("provenance"),
            )
        )
    return rows


def _with_row_provenance(row: dict[str, Any], provenance: Any) -> dict[str, Any]:
    source_refs = _source_refs_from_provenance(provenance)
    if source_refs:
        row["sourceRefs"] = source_refs
    provenance_summary = _provenance_summary(provenance)
    if provenance_summary:
        row["provenance"] = provenance_summary
    return row


def _round_issue_facts(issues: list[Any], round_id: str) -> list[dict[str, Any]]:
    requested = str(round_id)
    rows: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        refs = _as_string_list(issue.get("sourceRefs") or issue.get("refs"))
        round_refs = [ref for ref in refs if ref == requested or ref.startswith(f"{requested}:")]
        if not round_refs:
            continue
        rows.append(
            {
                "issue": issue.get("issue"),
                "phase": issue.get("phase"),
                "reason": issue.get("reason"),
                "confidence": issue.get("confidence"),
                "source": issue.get("source"),
                "count": len(round_refs),
                "refs": round_refs,
            }
        )
    return sorted(rows, key=lambda row: (-int(row.get("count") or 0), str(row.get("issue") or "")))[:8]


def _decision_audit_trends(history_stats: dict[str, Any]) -> dict[str, Any]:
    diagnosis = history_stats.get("diagnosis") if isinstance(history_stats.get("diagnosis"), dict) else {}
    trends = diagnosis.get("decisionAuditTrends") if isinstance(diagnosis.get("decisionAuditTrends"), dict) else {}
    return trends if isinstance(trends, dict) else {}


def _compact_decision_audit_row(row: dict[str, Any], row_kind: str | None = None) -> dict[str, Any]:
    compact_keys = [
        "kind",
        "classification",
        "label",
        "status",
        "selectedOptionId",
        "actualOptionId",
        "phase",
        "phases",
        "count",
        "pct",
        "baselineCount",
        "recentCount",
        "deltaCount",
        "estimatedStrokesLost",
        "direction",
        "sourceRefs",
        "baselineRefs",
        "recentRefs",
        "decisionIds",
        "actualShotRefs",
        "evidenceRefs",
        "modelUpdateSuggestions",
        "confidence",
        "coverage",
    ]
    compact = {key: row[key] for key in compact_keys if key in row}
    if row_kind:
        compact["kind"] = row_kind
    return compact


def _decision_audit_trends_fact(history_stats: dict[str, Any]) -> dict[str, Any] | None:
    trends = _decision_audit_trends(history_stats)
    if not trends:
        return None
    classification_counts = [
        _compact_decision_audit_row(row, "classification")
        for row in trends.get("classificationCounts", [])
        if isinstance(row, dict)
    ]
    recent_drivers = [
        _compact_decision_audit_row(row, "cost_driver")
        for row in trends.get("recentCostDrivers", [])
        if isinstance(row, dict)
    ]
    criteria_breakdown = [
        _compact_decision_audit_row(row, "criterion")
        for row in trends.get("criteriaBreakdown", [])
        if isinstance(row, dict)
    ]
    option_outcomes = [
        _compact_decision_audit_row(row, "option_outcome")
        for row in trends.get("optionOutcomes", [])
        if isinstance(row, dict)
    ]
    return {
        "totalAudits": trends.get("totalAudits", 0),
        "auditedRoundRefs": _as_string_list(trends.get("auditedRoundRefs")),
        "classificationCounts": classification_counts[:5],
        "recentCostDrivers": recent_drivers[:5],
        "criteriaBreakdown": criteria_breakdown[:8],
        "optionOutcomes": option_outcomes[:8],
    }


def _decision_audit_fact_source_refs(value: dict[str, Any]) -> list[str]:
    classification_counts = value.get("classificationCounts") if isinstance(value.get("classificationCounts"), list) else []
    recent_drivers = value.get("recentCostDrivers") if isinstance(value.get("recentCostDrivers"), list) else []
    criteria_breakdown = value.get("criteriaBreakdown") if isinstance(value.get("criteriaBreakdown"), list) else []
    option_outcomes = value.get("optionOutcomes") if isinstance(value.get("optionOutcomes"), list) else []
    rows = [row for row in [*classification_counts, *recent_drivers, *criteria_breakdown, *option_outcomes] if isinstance(row, dict)]
    return _unique_strings(
        [
            *_as_string_list(value.get("auditedRoundRefs")),
            *[
                ref
                for row in rows
                for ref in _as_string_list(row.get("sourceRefs") or row.get("recentRefs") or row.get("refs"))
            ],
            *[
                ref
                for row in rows
                for ref in _as_string_list(row.get("actualShotRefs"))
            ],
            *[
                ref
                for row in rows
                for ref in _as_string_list(row.get("evidenceRefs"))
            ],
        ]
    )


def _row_refs_match_round(row: dict[str, Any], round_id: str) -> list[str]:
    requested = str(round_id)
    refs = report_source_refs(row)
    return [ref for ref in refs if ref == requested or ref.startswith(f"{requested}:")]


def _round_decision_audit_facts(history_stats: dict[str, Any], round_id: str) -> list[dict[str, Any]]:
    trends = _decision_audit_trends(history_stats)
    rows: list[dict[str, Any]] = []
    audit_groups = [
        ("classificationCounts", "classification"),
        ("recentCostDrivers", "cost_driver"),
        ("criteriaBreakdown", "criterion"),
        ("optionOutcomes", "option_outcome"),
    ]
    for key, row_kind in audit_groups:
        group_rows = trends.get(key, []) if isinstance(trends.get(key), list) else []
        for row in group_rows:
            if not isinstance(row, dict):
                continue
            refs = _row_refs_match_round(row, round_id)
            if refs:
                compact = _compact_decision_audit_row(row, row_kind)
                compact["refs"] = refs
                rows.append(compact)
    return rows[:8]


def _compact_issue_trend_row(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "issue",
        "phase",
        "direction",
        "baselineCount",
        "recentCount",
        "deltaCount",
        "estimatedStrokesLost",
        "actualStrokesLost",
        "actualToParImpact",
        "actualImpactCoverage",
        "sourceRefs",
        "baselineRefs",
        "recentRefs",
        "confidence",
        "coverage",
    ]
    return {key: row[key] for key in keys if key in row}


def _diagnosis_issue_trends_fact(history_stats: dict[str, Any]) -> list[dict[str, Any]]:
    diagnosis = history_stats.get("diagnosis") if isinstance(history_stats.get("diagnosis"), dict) else {}
    trends = diagnosis.get("issueTrends") if isinstance(diagnosis.get("issueTrends"), list) else []
    rows = [_compact_issue_trend_row(row) for row in trends if isinstance(row, dict)]
    return rows[:8]


def _round_diagnosis_issue_trends(history_stats: dict[str, Any], round_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _diagnosis_issue_trends_fact(history_stats):
        refs = _row_refs_match_round(row, round_id)
        if refs:
            compact = dict(row)
            compact["refs"] = refs
            rows.append(compact)
    return rows[:8]


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric


def _has_change(value: Any) -> bool:
    numeric = _number_or_none(value)
    return numeric is not None and abs(numeric) > 0


def _baseline_recent_refs(row: dict[str, Any], baseline_key: str, recent_key: str) -> tuple[list[str], list[str], list[str]]:
    baseline_refs = _as_string_list(row.get(baseline_key))
    recent_refs = _as_string_list(row.get(recent_key))
    source_refs = _unique_strings([*baseline_refs, *recent_refs, *report_source_refs(row)])
    return baseline_refs, recent_refs, source_refs


def _with_optional_change_metadata(change: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    for key in ("confidence", "coverage"):
        if key in source:
            change[key] = source[key]
    return change


def _trend_changes_fact(history_stats: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    time_stats = history_stats.get("time") if isinstance(history_stats.get("time"), dict) else {}
    improvement = time_stats.get("improvement") if isinstance(time_stats.get("improvement"), dict) else {}
    if improvement and _has_change(improvement.get("deltaAverage18")):
        baseline_refs, recent_refs, source_refs = _baseline_recent_refs(improvement, "baselineRoundRefs", "recentRoundRefs")
        rows.append(
            _with_optional_change_metadata(
                {
                    "dimension": "overall",
                    "key": "scoring",
                    "metric": "average18",
                    "baseline": improvement.get("baselineAverage18"),
                    "recent": improvement.get("recentAverage18"),
                    "delta": improvement.get("deltaAverage18"),
                    "direction": improvement.get("direction"),
                    "baselineRefs": baseline_refs,
                    "recentRefs": recent_refs,
                    "sourceRefs": source_refs,
                },
                improvement,
            )
        )
    if improvement and _has_change(improvement.get("deltaAverageDifferential")):
        baseline_refs, recent_refs, source_refs = _baseline_recent_refs(
            improvement,
            "baselineDifferentialRoundRefs",
            "recentDifferentialRoundRefs",
        )
        if not source_refs:
            baseline_refs, recent_refs, source_refs = _baseline_recent_refs(improvement, "baselineRoundRefs", "recentRoundRefs")
        rows.append(
            _with_optional_change_metadata(
                {
                    "dimension": "overall",
                    "key": "difficulty_adjusted",
                    "metric": "differential",
                    "baseline": improvement.get("baselineAverageDifferential"),
                    "recent": improvement.get("recentAverageDifferential"),
                    "delta": improvement.get("deltaAverageDifferential"),
                    "direction": improvement.get("differentialDirection"),
                    "baselineRefs": baseline_refs,
                    "recentRefs": recent_refs,
                    "sourceRefs": source_refs,
                    "coverage": improvement.get("difficultyAdjustedCoverage"),
                },
                improvement,
            )
        )

    for course in history_stats.get("courses", []) if isinstance(history_stats.get("courses"), list) else []:
        if not isinstance(course, dict):
            continue
        recent_form = course.get("recentForm") if isinstance(course.get("recentForm"), dict) else {}
        if recent_form and _has_change(recent_form.get("deltaAverage18")):
            baseline_refs, recent_refs, source_refs = _baseline_recent_refs(recent_form, "baselineRoundRefs", "recentRoundRefs")
            rows.append(
                _with_optional_change_metadata(
                    {
                        "dimension": "course",
                        "key": course.get("courseKey"),
                        "label": course.get("courseName") or course.get("courseKey"),
                        "metric": "average18",
                        "baseline": recent_form.get("baselineAverage18"),
                        "recent": recent_form.get("recentAverage18"),
                        "delta": recent_form.get("deltaAverage18"),
                        "direction": recent_form.get("direction"),
                        "baselineRefs": baseline_refs,
                        "recentRefs": recent_refs,
                        "sourceRefs": source_refs,
                    },
                    recent_form,
                )
            )
        if recent_form and _has_change(recent_form.get("deltaAverageDifferential")):
            baseline_refs, recent_refs, source_refs = _baseline_recent_refs(recent_form, "baselineRoundRefs", "recentRoundRefs")
            rows.append(
                _with_optional_change_metadata(
                    {
                        "dimension": "course",
                        "key": course.get("courseKey"),
                        "label": course.get("courseName") or course.get("courseKey"),
                        "metric": "differential",
                        "baseline": recent_form.get("baselineAverageDifferential"),
                        "recent": recent_form.get("recentAverageDifferential"),
                        "delta": recent_form.get("deltaAverageDifferential"),
                        "direction": recent_form.get("differentialDirection") or recent_form.get("direction"),
                        "baselineRefs": baseline_refs,
                        "recentRefs": recent_refs,
                        "sourceRefs": source_refs,
                    },
                    recent_form,
                )
            )

    for club in history_stats.get("clubs", []) if isinstance(history_stats.get("clubs"), list) else []:
        if not isinstance(club, dict):
            continue
        trend = club.get("distanceTrend") if isinstance(club.get("distanceTrend"), dict) else {}
        if not trend or not _has_change(trend.get("deltaMedian")):
            continue
        baseline_refs, recent_refs, source_refs = _baseline_recent_refs(trend, "baselineShotRefs", "recentShotRefs")
        rows.append(
            _with_optional_change_metadata(
                {
                    "dimension": "club",
                    "key": club.get("club"),
                    "metric": "median_distance",
                    "baseline": trend.get("baselineMedian"),
                    "recent": trend.get("recentMedian"),
                    "delta": trend.get("deltaMedian"),
                    "direction": trend.get("direction"),
                    "baselineRefs": baseline_refs,
                    "recentRefs": recent_refs,
                    "sourceRefs": source_refs,
                },
                trend,
            )
        )

    diagnosis = history_stats.get("diagnosis") if isinstance(history_stats.get("diagnosis"), dict) else {}
    for issue in diagnosis.get("issueTrends", []) if isinstance(diagnosis.get("issueTrends"), list) else []:
        if not isinstance(issue, dict):
            continue
        if not (_has_change(issue.get("deltaCount")) or _has_change(issue.get("actualToParImpact"))):
            continue
        baseline_refs, recent_refs, source_refs = _baseline_recent_refs(issue, "baselineRefs", "recentRefs")
        rows.append(
            _with_optional_change_metadata(
                {
                    "dimension": "issue",
                    "key": issue.get("issue"),
                    "phase": issue.get("phase"),
                    "metric": "occurrences",
                    "baseline": issue.get("baselineCount"),
                    "recent": issue.get("recentCount"),
                    "delta": issue.get("deltaCount"),
                    "direction": issue.get("direction"),
                    "estimatedStrokesLost": issue.get("estimatedStrokesLost"),
                    "actualToParImpact": issue.get("actualToParImpact"),
                    "baselineRefs": baseline_refs,
                    "recentRefs": recent_refs,
                    "sourceRefs": source_refs,
                },
                issue,
            )
        )

    rows = [row for row in rows if row.get("sourceRefs")]
    rows.sort(key=_trend_change_sort_key)
    return rows[:12]


def _trend_change_sort_key(row: dict[str, Any]) -> tuple[float, float, float, str]:
    impact = abs(_number_or_none(row.get("actualToParImpact")) or 0.0)
    estimated = abs(_number_or_none(row.get("estimatedStrokesLost")) or 0.0)
    delta = abs(_number_or_none(row.get("delta")) or 0.0)
    return (-impact, -estimated, -delta, str(row.get("dimension") or ""))


def _find_hole_stat(history_stats: dict[str, Any], course_key: str, local_hole: int) -> dict[str, Any] | None:
    holes = history_stats.get("holes") if isinstance(history_stats.get("holes"), list) else []
    for row in holes:
        if not isinstance(row, dict):
            continue
        if str(row.get("courseKey") or "") != str(course_key):
            continue
        try:
            hole = int(row.get("hole") or 0)
        except (TypeError, ValueError):
            continue
        if hole == local_hole:
            return row
    return None


def _find_course_stat(history_stats: dict[str, Any], course_key: str) -> dict[str, Any] | None:
    courses = history_stats.get("courses") if isinstance(history_stats.get("courses"), list) else []
    distribution = history_stats.get("courseDistribution") if isinstance(history_stats.get("courseDistribution"), list) else []
    for row in [*courses, *distribution]:
        if isinstance(row, dict) and str(row.get("courseKey") or "") == str(course_key):
            return row
    return None


def _find_club_stat(history_stats: dict[str, Any], club_name: str) -> dict[str, Any] | None:
    clubs = history_stats.get("clubs") if isinstance(history_stats.get("clubs"), list) else []
    requested = str(club_name).strip().lower()
    for row in clubs:
        if isinstance(row, dict) and str(row.get("club") or "").strip().lower() == requested:
            return row
    return None


def _hole_subject_id(course_key: str, local_hole: int) -> str:
    return f"{course_key}:{local_hole}"


def _hole_report_source_refs(hole_stat: dict[str, Any] | None) -> dict[str, list[str]]:
    if not isinstance(hole_stat, dict):
        return {"holeRefs": [], "shotRefs": [], "roundRefs": []}
    hole_refs = _as_string_list(hole_stat.get("holeRefs") or hole_stat.get("refs") or hole_stat.get("sourceRefs"))
    shot_refs = _as_string_list(hole_stat.get("shotRefs"))
    round_refs = _unique_strings([ref.split(":", 1)[0] for ref in hole_refs if ref])
    return {"holeRefs": hole_refs, "shotRefs": shot_refs, "roundRefs": round_refs}


def _compact_hole_history(hole_stat: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "courseKey",
        "hole",
        "sampleCount",
        "averageToPar",
        "worstToPar",
        "scoreDistribution",
        "geometryCoverage",
        "holeRefs",
        "shotRefs",
        "sourceRefs",
        "coverage",
        "confidence",
    ]
    return {key: hole_stat[key] for key in keys if key in hole_stat}


def _hole_repeated_issues(hole_stat: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(hole_stat, dict):
        return []
    rows = [row for row in hole_stat.get("repeatedIssues", []) if isinstance(row, dict)]
    return sorted(rows, key=lambda row: (-int(row.get("count") or 0), str(row.get("issue") or "")))[:8]


def _hole_shot_facts(
    history_data: HistoryData | None,
    *,
    local_hole: int,
    hole_refs: list[str],
    shot_refs: list[str],
) -> list[dict[str, Any]]:
    if history_data is None:
        return []
    hole_ref_set = set(hole_refs)
    shot_ref_set = set(shot_refs)
    rows: list[dict[str, Any]] = []
    for index, shot in enumerate(history_data.shots):
        shot_round_id = shot.get("roundId")
        if shot_round_id is None:
            shot_round_id = shot.get("scorecardId")
        shot_ref = f"{shot_round_id}:{shot.get('hole')}:{index}"
        hole_ref = f"{shot_round_id}:{shot.get('hole')}"
        try:
            shot_hole = int(shot.get("hole") or 0)
        except (TypeError, ValueError):
            shot_hole = 0
        if shot_ref not in shot_ref_set and not (hole_ref in hole_ref_set and shot_hole == local_hole):
            continue
        rows.append(
            _with_row_provenance(
                {
                    "shotRef": shot_ref,
                    "holeRef": hole_ref,
                    "hole": shot.get("hole"),
                    "club": shot.get("club") or shot.get("clubName"),
                    "distance": shot.get("distance") or shot.get("meters"),
                    "surface": shot.get("surface") or shot.get("endLie"),
                },
                shot.get("provenance"),
            )
        )
    return rows[:40]


def _confirmed_vision_findings_for_refs(
    *,
    hole_refs: list[str],
    shot_refs: list[str],
    vision_root: Path | str | None,
    player_id: str = OWNER_ID,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    targets = [*[(("hole", ref)) for ref in hole_refs], *[(("shot", ref)) for ref in shot_refs]]
    for target_type, target_id in targets:
        for finding in list_findings_for_target(target_type, target_id, root=vision_root, player_id=player_id):
            if finding.get("confirmationState") != "manual_confirmed":
                continue
            finding_id = str(finding.get("id") or f"{target_type}:{target_id}:{finding.get('findingType')}")
            if finding_id in seen:
                continue
            seen.add(finding_id)
            rows.append(
                {
                    "id": finding_id,
                    "targetType": finding.get("targetType") or target_type,
                    "targetId": finding.get("targetId") or target_id,
                    "mediaId": finding.get("mediaId"),
                    "mediaKind": finding.get("mediaKind"),
                    "findingType": finding.get("findingType"),
                    "evidenceText": redact_private_text(finding.get("evidenceText") or ""),
                    "confidence": finding.get("confidence"),
                    "confirmationState": finding.get("confirmationState"),
                    "sourceRefs": [str(finding.get("targetId") or target_id)],
                }
            )
    return rows


def _hole_quality_missing_rows(
    data_quality: Any,
    *,
    hole_refs: list[str],
    shot_refs: list[str],
    round_refs: list[str],
) -> list[dict[str, Any]]:
    related = set([*hole_refs, *shot_refs, *round_refs])
    rows = []
    for row in _missing_data_quality_rows(data_quality):
        refs = set(report_source_refs(row))
        if refs and not (refs & related):
            continue
        if not refs and row.get("label") not in {"reports", "weather", "geometry"}:
            continue
        rows.append(row)
    return rows


def build_hole_report_facts(
    history_stats: dict[str, Any],
    course_key: str,
    local_hole: int,
    *,
    history_data: HistoryData | None = None,
    vision_root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> dict[str, Any]:
    subject_id = _hole_subject_id(course_key, local_hole)
    hole_stat = _find_hole_stat(history_stats, course_key, local_hole)
    course_stat = _find_course_stat(history_stats, course_key)
    refs = _hole_report_source_refs(hole_stat)
    hole_refs = refs["holeRefs"]
    shot_refs = refs["shotRefs"]
    round_refs = refs["roundRefs"]
    facts_used: list[dict[str, Any]] = []

    if hole_stat:
        hole_history = _compact_hole_history(hole_stat)
        facts_used.append(
            _fact(
                "hole_history",
                hole_history,
                "holes",
                source_refs=report_source_refs(hole_history),
            )
        )
        repeated_issues = _hole_repeated_issues(hole_stat)
        if repeated_issues:
            facts_used.append(
                _fact(
                    "hole_repeated_issues",
                    repeated_issues,
                    "holes.repeatedIssues",
                    source_refs=report_source_refs(repeated_issues),
                )
            )
        geometry_coverage = hole_stat.get("geometryCoverage")
        if geometry_coverage is not None:
            facts_used.append(
                _fact(
                    "hole_geometry_coverage",
                    {
                        "courseKey": course_key,
                        "hole": local_hole,
                        "geometryCoverage": geometry_coverage,
                        "holeRefs": hole_refs,
                    },
                    "holes.geometryCoverage",
                    source_refs=hole_refs,
                )
            )

    if course_stat:
        facts_used.append(
            _fact(
                "course_context",
                {
                    "courseKey": course_stat.get("courseKey"),
                    "courseName": course_stat.get("courseName") or course_stat.get("label"),
                    "roundCount": course_stat.get("roundCount"),
                    "average18": course_stat.get("average18"),
                    "recentForm": course_stat.get("recentForm"),
                    "issueProfile": course_stat.get("issueProfile", [])[:5] if isinstance(course_stat.get("issueProfile"), list) else [],
                    "sourceRefs": _as_string_list(course_stat.get("sourceRefs") or course_stat.get("roundRefs") or course_stat.get("roundIds")),
                    "coverage": course_stat.get("coverage"),
                    "confidence": course_stat.get("confidence"),
                },
                "courses",
            )
        )

    hole_shots = _hole_shot_facts(history_data, local_hole=local_hole, hole_refs=hole_refs, shot_refs=shot_refs)
    if hole_shots:
        facts_used.append(
            _fact(
                "hole_shots",
                hole_shots,
                "history.shots",
                source_refs=report_source_refs(hole_shots),
            )
        )

    vision_findings = _confirmed_vision_findings_for_refs(
        hole_refs=hole_refs,
        shot_refs=shot_refs,
        vision_root=vision_root,
        player_id=player_id,
    )
    if vision_findings:
        facts_used.append(
            _fact(
                "confirmed_vision_findings",
                vision_findings,
                "vision.findings",
                source_refs=report_source_refs(vision_findings),
            )
        )

    missing_data: list[dict[str, Any]] = []
    if hole_stat is None:
        missing_data.append({"label": "hole_reference", "reason": f"{subject_id} 不在历史球洞汇总中"})
    elif str(hole_stat.get("geometryCoverage") or "").lower() != "ready":
        missing_data.append(
            {
                "label": "geometry",
                "state": str(hole_stat.get("geometryCoverage") or "missing"),
                "reason": f"{subject_id} 的几何覆盖率为 {hole_stat.get('geometryCoverage') or '缺失'}",
                "sourceRefs": hole_refs,
            }
        )
    missing_data.extend(
        _hole_quality_missing_rows(
            history_stats.get("dataQuality") if isinstance(history_stats.get("dataQuality"), list) else [],
            hole_refs=hole_refs,
            shot_refs=shot_refs,
            round_refs=round_refs,
        )
    )

    return {
        "schema": "ai-caddie-report-facts-v1",
        "kind": "hole",
        "subjectId": subject_id,
        "factsUsed": facts_used,
        "missingData": missing_data,
    }


def _compact_course_history(course_stat: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "courseKey",
        "courseName",
        "roundCount",
        "average18",
        "bestScore",
        "worstScore",
        "averageDifferential",
        "bestDifferential",
        "difficultyAdjusted",
        "recentForm",
        "teeDirection",
        "parScoring",
        "approachMiss",
        "geometryCoverage",
        "roundRefs",
        "roundIds",
        "sourceRefs",
        "coverage",
        "confidence",
    ]
    return {key: course_stat[key] for key in keys if key in course_stat}


def _course_hole_rows(history_stats: dict[str, Any], course_key: str) -> list[dict[str, Any]]:
    holes = history_stats.get("holes") if isinstance(history_stats.get("holes"), list) else []
    rows = [
        row
        for row in holes
        if isinstance(row, dict) and str(row.get("courseKey") or "") == str(course_key)
    ]
    rows.sort(key=lambda row: (-float(row.get("averageToPar") or 0), int(row.get("hole") or 0)))
    return rows[:18]


def _missing_rows_for_related_refs(data_quality: Any, related_refs: list[str], *, generic_labels: set[str]) -> list[dict[str, Any]]:
    related = set(related_refs)
    rows = []
    for row in _missing_data_quality_rows(data_quality):
        refs = set(report_source_refs(row))
        if refs and not (refs & related):
            continue
        if not refs and row.get("label") not in generic_labels:
            continue
        rows.append(row)
    return rows


def build_course_report_facts(history_stats: dict[str, Any], course_key: str) -> dict[str, Any]:
    subject_id = str(course_key)
    course_stat = _find_course_stat(history_stats, course_key)
    facts_used: list[dict[str, Any]] = []
    related_refs: list[str] = []

    if course_stat:
        course_history = _compact_course_history(course_stat)
        related_refs.extend(report_source_refs(course_history))
        facts_used.append(
            _fact(
                "course_history",
                course_history,
                "courses",
                source_refs=report_source_refs(course_history),
            )
        )
        issue_profile = [row for row in course_stat.get("issueProfile", []) if isinstance(row, dict)]
        if issue_profile:
            facts_used.append(
                _fact(
                    "course_issue_profile",
                    issue_profile[:8],
                    "courses.issueProfile",
                    source_refs=report_source_refs(issue_profile),
                )
            )
            related_refs.extend(report_source_refs(issue_profile))
        toughest_holes = [row for row in course_stat.get("toughestHoles", []) if isinstance(row, dict)]
        if toughest_holes:
            facts_used.append(
                _fact(
                    "course_toughest_holes",
                    toughest_holes[:8],
                    "courses.toughestHoles",
                    source_refs=report_source_refs(toughest_holes),
                )
            )
            related_refs.extend(report_source_refs(toughest_holes))
        geometry_coverage = course_stat.get("geometryCoverage")
        if geometry_coverage is not None:
            facts_used.append(
                _fact(
                    "course_geometry_coverage",
                    {
                        "courseKey": course_key,
                        "geometryCoverage": geometry_coverage,
                        "sourceRefs": _as_string_list(course_stat.get("sourceRefs") or course_stat.get("roundRefs") or course_stat.get("roundIds")),
                    },
                    "courses.geometryCoverage",
                )
            )

    course_holes = _course_hole_rows(history_stats, course_key)
    if course_holes:
        facts_used.append(
            _fact(
                "course_holes",
                course_holes,
                "holes",
                source_refs=report_source_refs(course_holes),
            )
        )
        related_refs.extend(report_source_refs(course_holes))

    missing_data: list[dict[str, Any]] = []
    if course_stat is None:
        missing_data.append({"label": "course_reference", "reason": f"{course_key} 不在球场汇总中"})
    elif str(course_stat.get("geometryCoverage") or "").lower() != "ready":
        missing_data.append(
            {
                "label": "geometry",
                "state": str(course_stat.get("geometryCoverage") or "missing"),
                "reason": f"{course_key} 的几何覆盖率为 {course_stat.get('geometryCoverage') or '缺失'}",
                "sourceRefs": _as_string_list(course_stat.get("sourceRefs") or course_stat.get("roundRefs") or course_stat.get("roundIds")),
            }
        )
    missing_data.extend(
        _missing_rows_for_related_refs(
            history_stats.get("dataQuality") if isinstance(history_stats.get("dataQuality"), list) else [],
            _unique_strings(related_refs),
            generic_labels={"reports", "weather", "geometry"},
        )
    )

    return {
        "schema": "ai-caddie-report-facts-v1",
        "kind": "course",
        "subjectId": subject_id,
        "factsUsed": facts_used,
        "missingData": missing_data,
    }


def _compact_club_profile(club_stat: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "club",
        "sampleCount",
        "rawSampleCount",
        "validSampleCount",
        "invalidSampleCount",
        "outlierCount",
        "median",
        "p10",
        "p90",
        "dispersionRange",
        "consistency",
        "max",
        "roundIds",
        "shotRefs",
        "validShotRefs",
        "invalidShotRefs",
        "outlierShotRefs",
        "correctedRefs",
        "correctionCount",
        "coverage",
        "confidence",
    ]
    return {key: club_stat[key] for key in keys if key in club_stat}


def _compact_club_surface_risk(club_stat: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "club",
        "topSurface",
        "hazardRate",
        "riskRate",
        "usableRate",
        "surfaceDistribution",
        "riskShotRefs",
        "usableShotRefs",
        "sourceRefs",
        "coverage",
        "confidence",
    ]
    return {key: club_stat[key] for key in keys if key in club_stat}


def build_club_report_facts(history_stats: dict[str, Any], club_name: str) -> dict[str, Any]:
    subject_id = str(club_name)
    club_stat = _find_club_stat(history_stats, club_name)
    facts_used: list[dict[str, Any]] = []
    related_refs: list[str] = []

    if club_stat:
        profile = _compact_club_profile(club_stat)
        related_refs.extend(report_source_refs(profile))
        facts_used.append(
            _fact(
                "club_profile",
                profile,
                "clubs",
                source_refs=report_source_refs(profile),
            )
        )
        distance_trend = club_stat.get("distanceTrend") if isinstance(club_stat.get("distanceTrend"), dict) else None
        if distance_trend:
            facts_used.append(
                _fact(
                    "club_distance_trend",
                    {"club": club_stat.get("club"), **distance_trend},
                    "clubs.distanceTrend",
                    source_refs=report_source_refs(distance_trend),
                )
            )
            related_refs.extend(report_source_refs(distance_trend))
        sample_quality = club_stat.get("sampleQuality") if isinstance(club_stat.get("sampleQuality"), dict) else None
        if sample_quality:
            facts_used.append(
                _fact(
                    "club_sample_quality",
                    {"club": club_stat.get("club"), **sample_quality},
                    "clubs.sampleQuality",
                    source_refs=report_source_refs(sample_quality),
                )
            )
            related_refs.extend(report_source_refs(sample_quality))
        surface_risk = _compact_club_surface_risk(club_stat)
        if surface_risk:
            facts_used.append(
                _fact(
                    "club_surface_risk",
                    surface_risk,
                    "clubs.surfaceRisk",
                    source_refs=report_source_refs(surface_risk),
                )
            )
            related_refs.extend(report_source_refs(surface_risk))

    missing_data: list[dict[str, Any]] = []
    if club_stat is None:
        missing_data.append({"label": "club_reference", "reason": f"{club_name} 不在球杆汇总中"})
    else:
        sample_quality = club_stat.get("sampleQuality") if isinstance(club_stat.get("sampleQuality"), dict) else {}
        if str(sample_quality.get("confidence") or club_stat.get("confidence") or "").lower() in {"low", "insufficient"}:
            missing_data.append(
                {
                    "label": "club_samples",
                    "state": "partial",
                    "reason": f"球杆 {club_stat.get('club')} 样本置信度为 {sample_quality.get('confidence') or club_stat.get('confidence')}",
                    "sourceRefs": _as_string_list(club_stat.get("shotRefs")),
                }
            )
    missing_data.extend(
        _missing_rows_for_related_refs(
            history_stats.get("dataQuality") if isinstance(history_stats.get("dataQuality"), list) else [],
            _unique_strings(related_refs),
            generic_labels={"club_samples", "shot_rows"},
        )
    )

    return {
        "schema": "ai-caddie-report-facts-v1",
        "kind": "club",
        "subjectId": subject_id,
        "factsUsed": facts_used,
        "missingData": missing_data,
    }


def _course_issue_profiles_fact(history_stats: dict[str, Any]) -> list[dict[str, Any]]:
    courses = history_stats.get("courses") if isinstance(history_stats.get("courses"), list) else []
    rows: list[dict[str, Any]] = []
    for course in courses:
        if not isinstance(course, dict):
            continue
        issue_profile = [row for row in course.get("issueProfile", []) if isinstance(row, dict)]
        toughest_holes = [row for row in course.get("toughestHoles", []) if isinstance(row, dict)]
        if not issue_profile and not toughest_holes:
            continue
        rows.append(
            {
                "courseKey": course.get("courseKey"),
                "courseName": course.get("courseName"),
                "roundCount": course.get("roundCount"),
                "average18": course.get("average18"),
                "sourceRefs": _as_string_list(course.get("sourceRefs") or course.get("roundRefs") or course.get("roundIds")),
                "issueProfile": issue_profile[:5],
                "toughestHoles": toughest_holes[:5],
                "coverage": course.get("coverage"),
                "confidence": course.get("confidence"),
            }
        )
    return sorted(rows, key=lambda row: -sum(int(issue.get("count") or 0) for issue in row.get("issueProfile", [])))[:6]


def _club_risk_profiles_fact(history_stats: dict[str, Any]) -> list[dict[str, Any]]:
    clubs = history_stats.get("clubs") if isinstance(history_stats.get("clubs"), list) else []
    rows: list[dict[str, Any]] = []
    for club in clubs:
        if not isinstance(club, dict):
            continue
        if club.get("riskRate") is None and club.get("hazardRate") is None and not club.get("surfaceDistribution"):
            continue
        surface_distribution = [
            row for row in club.get("surfaceDistribution", [])
            if isinstance(row, dict)
        ]
        rows.append(
            {
                "club": club.get("club"),
                "sampleCount": club.get("sampleCount"),
                "median": club.get("median"),
                "p10": club.get("p10"),
                "p90": club.get("p90"),
                "dispersionRange": club.get("dispersionRange"),
                "topSurface": club.get("topSurface"),
                "hazardRate": club.get("hazardRate"),
                "riskRate": club.get("riskRate"),
                "usableRate": club.get("usableRate"),
                "surfaceDistribution": surface_distribution[:5],
                "riskShotRefs": _as_string_list(club.get("riskShotRefs")),
                "usableShotRefs": _as_string_list(club.get("usableShotRefs")),
                "sourceRefs": _as_string_list(club.get("sourceRefs") or club.get("shotRefs")),
                "coverage": club.get("coverage"),
                "confidence": club.get("confidence"),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -float(row.get("riskRate") or row.get("hazardRate") or 0),
            -int(row.get("sampleCount") or 0),
            str(row.get("club") or ""),
        ),
    )[:8]


def build_trend_report_facts(history_stats: dict[str, Any], period: str) -> dict[str, Any]:
    summary = history_stats.get("summary") if isinstance(history_stats.get("summary"), dict) else {}
    time_stats = history_stats.get("time") if isinstance(history_stats.get("time"), dict) else {}
    scoring = history_stats.get("scoring") if isinstance(history_stats.get("scoring"), dict) else {}
    data_quality = history_stats.get("dataQuality") if isinstance(history_stats.get("dataQuality"), list) else []
    drill_down = history_stats.get("drillDown") if isinstance(history_stats.get("drillDown"), dict) else {}

    facts_used = [
        _fact(
            "summary_trend",
            _with_stat_metadata(
                {
                    "totalRounds": summary.get("totalRounds"),
                    "average18": summary.get("average18"),
                    "median18": summary.get("median18"),
                    "recent5Average": summary.get("recent5Average"),
                    "recent10Average": summary.get("recent10Average"),
                    "recent20Average": summary.get("recent20Average"),
                    "bestScore": summary.get("bestScore"),
                },
                summary,
            ),
            "summary",
        )
    ]

    period_row = _find_period_row(time_stats, period)
    if period_row is not None:
        facts_used.append(_fact("time_period", period_row, "time"))
    elif period == "recent_10":
        facts_used.append(
            _fact(
                "time_period",
                {
                    "key": "recent_10",
                    "average18": summary.get("recent10Average"),
                    "roundRefs": _as_string_list(drill_down.get("roundRefs") or drill_down.get("roundIds"))[:10],
                },
                "summary.recent10Average",
            )
        )

    for phase in scoring.get("phaseStats", []) if isinstance(scoring.get("phaseStats"), list) else []:
        if isinstance(phase, dict) and phase.get("phase"):
            facts_used.append(_fact(f"phase_{phase.get('phase')}", phase, "scoring.phaseStats"))

    score_bands = scoring.get("scoreBands")
    if isinstance(score_bands, list):
        facts_used.append(_fact("score_distribution", score_bands, "scoring.scoreBands"))

    course_distribution = history_stats.get("courseDistribution")
    if isinstance(course_distribution, list) and course_distribution:
        facts_used.append(_fact("course_distribution", course_distribution[:8], "courseDistribution"))

    records = history_stats.get("records")
    if isinstance(records, dict) and records:
        facts_used.append(_fact("record_book", _record_book_fact(records), "records"))

    issues = history_stats.get("issues")
    if isinstance(issues, list) and issues:
        top_issues = sorted(
            [issue for issue in issues if isinstance(issue, dict)],
            key=lambda issue: int(issue.get("count") or 0),
            reverse=True,
        )[:5]
        facts_used.append(_fact("top_issues", top_issues, "issues"))

    diagnosis_issue_trends = _diagnosis_issue_trends_fact(history_stats)
    if diagnosis_issue_trends:
        facts_used.append(
            _fact(
                "diagnosis_issue_trends",
                diagnosis_issue_trends,
                "diagnosis.issueTrends",
                source_refs=report_source_refs(diagnosis_issue_trends),
            )
        )

    course_issue_profiles = _course_issue_profiles_fact(history_stats)
    if course_issue_profiles:
        facts_used.append(
            _fact(
                "course_issue_profiles",
                course_issue_profiles,
                "courses.issueProfile",
                source_refs=report_source_refs(course_issue_profiles),
            )
        )

    club_risk_profiles = _club_risk_profiles_fact(history_stats)
    if club_risk_profiles:
        facts_used.append(
            _fact(
                "club_risk_profiles",
                club_risk_profiles,
                "clubs.surfaceRisk",
                source_refs=report_source_refs(club_risk_profiles),
            )
        )

    trend_changes = _trend_changes_fact(history_stats)
    if trend_changes:
        facts_used.append(
            _fact(
                "trend_changes",
                trend_changes,
                "time.improvement|courses.recentForm|clubs.distanceTrend|diagnosis.issueTrends",
                source_refs=report_source_refs(trend_changes),
            )
        )

    decision_audits = _decision_audit_trends_fact(history_stats)
    if decision_audits and int(decision_audits.get("totalAudits") or 0):
        facts_used.append(
            _fact(
                "decision_audit_trends",
                decision_audits,
                "diagnosis.decisionAuditTrends",
                source_refs=_decision_audit_fact_source_refs(decision_audits),
            )
        )

    facts_used.append(
        _fact(
            "drilldown_refs",
            {
                "roundRefs": _as_string_list(drill_down.get("roundRefs") or drill_down.get("roundIds"))[:20],
                "holeRefs": _as_string_list(drill_down.get("holeRefs"))[:40],
                "shotRefs": _as_string_list(drill_down.get("shotRefs"))[:40],
            },
            "drillDown",
        )
    )

    missing_data: list[dict[str, Any]] = []
    if period_row is None and period != "recent_10":
        missing_data.append({"label": "period", "reason": f"{period} 不在历史时间汇总中"})
    missing_data.extend(_missing_data_quality_rows(data_quality))

    return {
        "schema": "ai-caddie-report-facts-v1",
        "kind": "trend",
        "subjectId": str(period),
        "factsUsed": facts_used,
        "missingData": missing_data,
    }


def _find_period_row(time_stats: dict[str, Any], period: str) -> dict[str, Any] | None:
    if period.startswith("year:"):
        key = period.removeprefix("year:")
        return _find_time_row(time_stats.get("byYear"), key)
    if period.startswith("quarter:"):
        key = period.removeprefix("quarter:")
        return _find_time_row(time_stats.get("byQuarter"), key)
    if period.startswith("month:"):
        key = period.removeprefix("month:")
        return _find_time_row(time_stats.get("byMonth"), key)
    return None


def _record_book_fact(records: dict[str, Any]) -> dict[str, Any]:
    return {
        "best18": records.get("best18"),
        "bestNine": records.get("bestNine"),
        "mostPlayedCourse": records.get("mostPlayedCourse"),
        "longestShots": records.get("longestShots", [])[:3] if isinstance(records.get("longestShots"), list) else [],
        "bestHoleOutcomes": records.get("bestHoleOutcomes", [])[:3] if isinstance(records.get("bestHoleOutcomes"), list) else [],
    }


def _find_time_row(rows: Any, key: str) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("key") or row.get("year") or row.get("period") or "") == key:
            return row
    return None


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _missing_data_quality_rows(data_quality: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(data_quality, list):
        return rows
    for finding in data_quality:
        if not isinstance(finding, dict) or finding.get("state") == "good":
            continue
        row = {
            "label": finding.get("label", "unknown"),
            "state": finding.get("state", "unknown"),
            "ready": finding.get("ready"),
            "total": finding.get("total"),
        }
        refs = _as_string_list(finding.get("sourceRefs") or finding.get("refs") or finding.get("roundRefs") or finding.get("roundIds"))
        if refs:
            row["refs"] = refs
            row["sourceRefs"] = refs
        if isinstance(finding.get("coverage"), dict):
            row["coverage"] = dict(finding["coverage"])
        if finding.get("confidence") is not None:
            row["confidence"] = finding.get("confidence")
        rows.append(row)
    return rows


def _stored_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def report_store_file(root: Path | str | None = None) -> Path:
    return Path(root or ".") / "data" / "reports" / "reports.jsonl"


def store_report(
    report: dict[str, Any],
    *,
    kind: str,
    subject_id: str,
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> dict[str, Any]:
    record = {
        "id": uuid4().hex,
        "storedAt": _stored_at(),
        "kind": kind,
        "subjectId": redact_private_text(subject_id),
        "report": _redact_value(report),
    }
    path = report_store_file(evidence_root(player_id, root=root))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return record


def iter_report_records(
    *,
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> Iterator[Any]:
    """Yield the append-only report authority one record at a time.

    Callers that only need an index, one matching report, or aggregate metadata must not retain the
    complete fact trees for every historical report.  A malformed/torn final append remains ignored,
    matching the original lossless list reader.
    """
    evidence = evidence_root(player_id, root=root)
    if evidence is None:
        return
    path = report_store_file(evidence)
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue  # tolerate a torn final append; never 500 the read path


def list_report_records(*, root: Path | str | None = None, player_id: str = OWNER_ID) -> list[dict[str, Any]]:
    """Return every full stored report for callers that explicitly need the whole ledger."""
    return list(iter_report_records(root=root, player_id=player_id))


_STATS_ISSUE_KEYS = (
    "issue",
    "suggestedIssue",
    "tag",
    "sourceRefs",
    "refs",
    "targetRefs",
    "targetRef",
    "targetId",
)


def _stats_issue_projection(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    projected = {key: value[key] for key in _STATS_ISSUE_KEYS if key in value}
    return projected or None


def _stats_report_projection(record: Any) -> dict[str, Any] | None:
    """Keep exactly the report fields consumed by ``history_stats``.

    Stored reports retain their complete fact and inference provenance for review/report APIs.  The
    statistics builder only needs report coverage plus explicitly suggested issue labels and refs;
    retaining every report's multi-megabyte ``factsUsed`` tree during each stats build made a normal
    owner process exceed the production 1 GiB memory limit.  This projection is deliberately private
    to the stats read path; ``list_report_records`` remains the lossless authority for every other
    consumer.
    """
    if not isinstance(record, dict):
        return None
    projected = {
        key: record[key]
        for key in ("kind", "subjectId", "sourceRefs")
        if key in record
    }
    report = record.get("report")
    if not isinstance(report, dict):
        return projected

    report_projection: dict[str, Any] = {}
    if "sourceRefs" in report:
        report_projection["sourceRefs"] = report["sourceRefs"]
    for key in ("aiSuggestedIssues", "suggestedIssues"):
        rows = report.get(key)
        if isinstance(rows, list):
            report_projection[key] = [
                projected_row
                for row in rows
                if (projected_row := _stats_issue_projection(row)) is not None
            ]

    inferences: list[dict[str, Any]] = []
    raw_inferences = report.get("inferencesMade")
    if isinstance(raw_inferences, list):
        for inference in raw_inferences:
            projected_inference = _stats_issue_projection(inference)
            if not isinstance(inference, dict):
                continue
            nested = inference.get("suggestedIssues")
            if isinstance(nested, list):
                nested_projection = [
                    projected_row
                    for row in nested
                    if (projected_row := _stats_issue_projection(row)) is not None
                ]
                if nested_projection:
                    projected_inference = dict(projected_inference or {})
                    projected_inference["suggestedIssues"] = nested_projection
            if projected_inference:
                inferences.append(projected_inference)
    if inferences:
        report_projection["inferencesMade"] = inferences
    if report_projection:
        projected["report"] = report_projection
    return projected


def list_report_stats_records(
    *,
    root: Path | str | None = None,
    player_id: str = OWNER_ID,
) -> list[dict[str, Any]]:
    """Stream a compact report projection for aggregate history statistics."""
    records: list[dict[str, Any]] = []
    for record in iter_report_records(root=root, player_id=player_id):
        projected = _stats_report_projection(record)
        if projected is not None:
            records.append(projected)
    return records


def latest_report_record(kind: str, subject_id: str, *, root: Path | str | None = None, player_id: str = OWNER_ID) -> dict[str, Any] | None:
    safe_subject_id = redact_private_text(subject_id)
    latest: dict[str, Any] | None = None
    latest_key: tuple[str, int] | None = None
    for sequence, record in enumerate(iter_report_records(root=root, player_id=player_id)):
        if not isinstance(record, dict):
            continue
        if record.get("kind") != kind or str(record.get("subjectId")) != safe_subject_id:
            continue
        key = (str(record.get("storedAt") or ""), sequence)
        if latest_key is None or key >= latest_key:
            latest = record
            latest_key = key
    return latest


def _confidence(facts_used: list[dict[str, Any]], missing_data: list[dict[str, Any]]) -> str:
    if not facts_used:
        return "low"
    if missing_data:
        return "medium"
    return "high"


def _fact_label(fact: dict[str, Any]) -> str:
    return str(fact.get("label") or "fact")


def _fact_confidence(fact: dict[str, Any], default: str) -> str:
    confidence = str(fact.get("confidence") or default)
    return confidence if confidence in {"low", "medium", "high"} else default


def _missing_labels(missing_data: list[dict[str, Any]]) -> list[str]:
    return _unique_strings([row.get("label") for row in missing_data if isinstance(row, dict)])


def _missing_refs(missing_data: list[dict[str, Any]]) -> list[str]:
    return report_source_refs({"missingData": missing_data})


def _inference(
    claim: str,
    fact: dict[str, Any],
    *,
    default_confidence: str,
    missing_data: list[dict[str, Any]],
) -> dict[str, Any]:
    source_refs = report_source_refs(fact)
    return {
        "claim": claim,
        "factLabels": [_fact_label(fact)],
        "sourceRefs": source_refs,
        "confidence": _fact_confidence(fact, default_confidence),
        "missingDataRefs": _missing_refs(missing_data),
        "missingDataLabels": _missing_labels(missing_data),
    }


def _append_inference(rows: list[dict[str, Any]], row: dict[str, Any]) -> None:
    if row.get("sourceRefs"):
        rows.append(row)


def _first_issue(value: Any) -> str | None:
    if isinstance(value, dict):
        issue = value.get("issue")
        return str(issue) if issue is not None else None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("issue") is not None:
                return str(item["issue"])
    return None


def _first_audit_classification(value: Any) -> str | None:
    rows: list[Any] = []
    if isinstance(value, dict):
        recent = value.get("recentCostDrivers")
        counts = value.get("classificationCounts")
        rows.extend(recent if isinstance(recent, list) else [])
        rows.extend(counts if isinstance(counts, list) else [])
    elif isinstance(value, list):
        rows.extend(value)
    for item in rows:
        if isinstance(item, dict) and item.get("classification") is not None:
            return str(item["classification"])
    return None


def _first_audit_signal(value: Any) -> str | None:
    rows: list[Any] = []
    if isinstance(value, dict):
        for key in ("criteriaBreakdown", "optionOutcomes", "recentCostDrivers", "classificationCounts"):
            group = value.get(key)
            rows.extend(group if isinstance(group, list) else [])
    elif isinstance(value, list):
        rows.extend(value)

    for item in rows:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        status = str(item.get("status") or "").strip()
        if label and status and status.lower() in {"fail", "review", "missing"}:
            return f"判据 {label} {audit_status_zh(status)}"

    for item in rows:
        if not isinstance(item, dict):
            continue
        selected = str(item.get("selectedOptionId") or "").strip()
        actual = str(item.get("actualOptionId") or "").strip()
        classification = str(item.get("classification") or "").strip()
        if selected and actual and selected != actual:
            suffix = f"，分类为 {audit_class_zh(classification)}" if classification else ""
            return f"选项 {selected}->{actual}{suffix}"

    classification = _first_audit_classification(value)
    return f"{audit_class_zh(classification)} 决策问题" if classification else None


def _first_risky_club(value: Any) -> tuple[str, float | None] | None:
    rows = value if isinstance(value, list) else []
    for item in rows:
        if not isinstance(item, dict) or item.get("club") is None:
            continue
        rate = item.get("riskRate")
        try:
            numeric_rate = float(rate) if rate is not None else None
        except (TypeError, ValueError):
            numeric_rate = None
        return str(item["club"]), numeric_rate
    return None


def _first_course_issue(value: Any) -> tuple[str, str] | None:
    rows = value if isinstance(value, list) else []
    for item in rows:
        if not isinstance(item, dict):
            continue
        course = str(item.get("courseName") or item.get("courseKey") or "").strip()
        issues = item.get("issueProfile") if isinstance(item.get("issueProfile"), list) else []
        for issue in issues:
            if isinstance(issue, dict) and issue.get("issue") is not None and course:
                return course, str(issue["issue"])
    return None


def _top_trend_change_summary(value: Any) -> tuple[str, str, Any, str | None] | None:
    rows = value if isinstance(value, list) else []
    for item in rows:
        if not isinstance(item, dict):
            continue
        dimension = str(item.get("dimension") or "trend")
        key = str(item.get("label") or item.get("key") or "").strip()
        metric = str(item.get("metric") or "change")
        if not key:
            key = dimension
        direction = str(item.get("direction")) if item.get("direction") is not None else None
        return dimension, key, item.get("delta"), direction or metric
    return None


def _hole_history_summary(value: Any) -> tuple[int | None, Any, Any] | None:
    if not isinstance(value, dict):
        return None
    hole = value.get("hole")
    try:
        hole_number = int(hole) if hole is not None else None
    except (TypeError, ValueError):
        hole_number = None
    return hole_number, value.get("averageToPar"), value.get("sampleCount")


def _first_vision_finding(value: Any) -> str | None:
    rows = value if isinstance(value, list) else []
    for row in rows:
        if isinstance(row, dict) and row.get("findingType") is not None:
            return str(row["findingType"])
    return None


def _course_history_summary(value: Any) -> tuple[str, Any] | None:
    if not isinstance(value, dict):
        return None
    course = str(value.get("courseName") or value.get("courseKey") or "").strip()
    if not course:
        return None
    return course, value.get("roundCount")


def _club_profile_summary(value: Any) -> tuple[str, Any, Any] | None:
    if not isinstance(value, dict):
        return None
    club = str(value.get("club") or "").strip()
    if not club:
        return None
    return club, value.get("median"), value.get("sampleCount")


def _club_surface_risk_summary(value: Any) -> tuple[str, Any] | None:
    if not isinstance(value, dict):
        return None
    club = str(value.get("club") or "").strip()
    if not club:
        return None
    return club, value.get("riskRate") if value.get("riskRate") is not None else value.get("hazardRate")


def _summary_round_count(value: Any) -> int | None:
    if isinstance(value, dict):
        count = value.get("totalRounds") or value.get("roundCount")
        try:
            return int(count)
        except (TypeError, ValueError):
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_report_inferences(
    facts_used: list[dict[str, Any]],
    missing_data: list[dict[str, Any]],
    *,
    default_confidence: str | None = None,
) -> list[dict[str, Any]]:
    confidence = default_confidence or _confidence(facts_used, missing_data)
    rows: list[dict[str, Any]] = []
    for fact in facts_used:
        if not isinstance(fact, dict):
            continue
        label = _fact_label(fact)
        value = fact.get("value")
        if label in {"summary_trend", "total_rounds"}:
            round_count = _summary_round_count(value)
            if round_count is not None:
                claim = f"近期回顾基于 {round_count} 场球。" if label == "summary_trend" else f"本报告基于 {round_count} 场球。"
                _append_inference(rows, _inference(claim, fact, default_confidence=confidence, missing_data=missing_data))
                continue
        if label in {"top_issue", "top_issues", "round_issues", "diagnosis_issue_trends", "round_diagnosis_issue_trends"}:
            issue = _first_issue(value)
            if issue:
                _append_inference(rows, _inference(f"主要失分信号为 {issue_label_zh(issue)}。", fact, default_confidence=confidence, missing_data=missing_data))
                continue
        if label == "hole_history":
            summary = _hole_history_summary(value)
            if summary:
                hole, average_to_par, sample_count = summary
                hole_text = f"第 {hole} 洞" if hole is not None else "本洞"
                sample_text = f"，共 {sample_count} 个样本" if sample_count is not None else ""
                _append_inference(
                    rows,
                    _inference(
                        f"{hole_text}平均相对标准杆 {average_to_par}{sample_text}。",
                        fact,
                        default_confidence=confidence,
                        missing_data=missing_data,
                    ),
                )
                continue
        if label == "hole_repeated_issues":
            issue = _first_issue(value)
            if issue:
                _append_inference(rows, _inference(f"本洞反复出现的问题为 {issue_label_zh(issue)}。", fact, default_confidence=confidence, missing_data=missing_data))
                continue
        if label == "confirmed_vision_findings":
            finding_type = _first_vision_finding(value)
            if finding_type:
                _append_inference(
                    rows,
                    _inference(
                        f"已确认的视觉证据包含 {finding_type}。",
                        fact,
                        default_confidence=confidence,
                        missing_data=missing_data,
                    ),
                )
                continue
        if label == "course_history":
            summary = _course_history_summary(value)
            if summary:
                course, round_count = summary
                count_text = f"共有 {round_count} 场球记录" if round_count is not None else "已在历史记录中"
                _append_inference(rows, _inference(f"球场 {course}{count_text}。", fact, default_confidence=confidence, missing_data=missing_data))
                continue
        if label == "course_issue_profile":
            issue = _first_issue(value)
            if issue:
                _append_inference(rows, _inference(f"球场专项问题分布突出 {issue_label_zh(issue)}。", fact, default_confidence=confidence, missing_data=missing_data))
                continue
        if label == "club_profile":
            summary = _club_profile_summary(value)
            if summary:
                club, median_value, sample_count = summary
                sample_text = f"，共 {sample_count} 个样本" if sample_count is not None else ""
                _append_inference(
                    rows,
                    _inference(
                        f"球杆 {club} 中位距离为 {median_value}{sample_text}。",
                        fact,
                        default_confidence=confidence,
                        missing_data=missing_data,
                    ),
                )
                continue
        if label == "club_distance_trend" and isinstance(value, dict) and value.get("direction"):
            club = value.get("club") or "club"
            _append_inference(
                rows,
                _inference(
                    f"球杆 {club} 距离趋势为 {value.get('direction')}。",
                    fact,
                    default_confidence=confidence,
                    missing_data=missing_data,
                ),
            )
            continue
        if label == "club_surface_risk":
            summary = _club_surface_risk_summary(value)
            if summary:
                club, risk_rate = summary
                rate_text = f"，风险率 {risk_rate:g}%" if isinstance(risk_rate, (int, float)) else ""
                _append_inference(rows, _inference(f"球杆落点模型标记 {club}{rate_text}。", fact, default_confidence=confidence, missing_data=missing_data))
                continue
        if label == "club_risk_profiles":
            club_risk = _first_risky_club(value)
            if club_risk:
                club, risk_rate = club_risk
                rate_text = f"，风险率 {risk_rate:g}%" if risk_rate is not None else ""
                _append_inference(rows, _inference(f"球杆风险模型标记 {club}{rate_text}。", fact, default_confidence=confidence, missing_data=missing_data))
                continue
        if label == "trend_changes":
            summary = _top_trend_change_summary(value)
            if summary:
                dimension, key, delta, direction = summary
                dim_zh = trend_dimension_zh(dimension)
                # The key is an issue token only when the dimension is "issue";
                # for club/course it is a name/key that stays as-is.
                key_zh = issue_label_zh(key) if dimension == "issue" else key
                dir_zh = form_direction_zh(direction) if direction is not None else ""
                delta_text = f"，变化量 {delta}" if delta is not None else ""
                _append_inference(
                    rows,
                    _inference(
                        f"最大趋势变化：{dim_zh} {key_zh} {dir_zh}{delta_text}。",
                        fact,
                        default_confidence=confidence,
                        missing_data=missing_data,
                    ),
                )
                continue
        if label == "course_issue_profiles":
            course_issue = _first_course_issue(value)
            if course_issue:
                course, issue = course_issue
                _append_inference(rows, _inference(f"球场 {course} 问题分布突出 {issue_label_zh(issue)}。", fact, default_confidence=confidence, missing_data=missing_data))
                continue
        if label in {"decision_audit_trends", "round_decision_audits"}:
            signal = _first_audit_signal(value)
            if signal:
                _append_inference(
                    rows,
                    _inference(
                        f"球童审计循环标记 {signal}。",
                        fact,
                        default_confidence=confidence,
                        missing_data=missing_data,
                    ),
                )
                continue
        if label == "round_scorecard" and isinstance(value, dict):
            score = value.get("score")
            course = value.get("course")
            if score is not None:
                course_text = f"，球场 {course}" if course else ""
                _append_inference(rows, _inference(f"本场成绩 {score}{course_text}。", fact, default_confidence=confidence, missing_data=missing_data))

    if not rows and facts_used:
        synthetic_fact = {
            "label": "facts_used",
            "sourceRefs": report_source_refs({"factsUsed": facts_used}),
        }
        rows.append(
            _inference(
                f"叙述受限于 {len(facts_used)} 条结构化事实。",
                synthetic_fact,
                default_confidence=confidence,
                missing_data=missing_data,
            )
        )
    return rows


def _sentence(text: object) -> str:
    value = str(text).strip()
    if not value:
        return ""
    if value[-1] in ".!?。！？":
        return value
    return f"{value}."


def _deterministic_report_narrative(
    *,
    kind: str,
    facts_used: list[dict[str, Any]],
    missing_data: list[dict[str, Any]],
) -> str:
    inferences = build_report_inferences(facts_used, missing_data)
    claims = [_sentence(row.get("claim")) for row in inferences if isinstance(row, dict) and row.get("claim")]
    if not claims:
        claims = [f"回顾受限于 {len(facts_used)} 条结构化事实。"]

    title = {
        "round": "球局回顾",
        "trend": "趋势回顾",
        "hole": "球洞回顾",
        "course": "球场回顾",
        "club": "球杆回顾",
    }.get(kind, "回顾")
    parts = [f"{title}：{' '.join(claims[:5])}"]
    missing_labels = _missing_labels(missing_data)
    if missing_labels:
        parts.append(f"数据缺失：{', '.join(data_label_zh(label) for label in missing_labels[:8])}。")
    parts.append("每项陈述均受本报告结构化事实及来源引用约束。")
    return redact_private_text(" ".join(parts))


def _report_payload(
    safe_facts: dict[str, Any],
    *,
    provider: str,
    model: str,
    narrative: str,
) -> dict[str, Any]:
    facts_used = safe_facts.get("factsUsed", []) if isinstance(safe_facts.get("factsUsed"), list) else []
    missing_data = safe_facts.get("missingData", []) if isinstance(safe_facts.get("missingData"), list) else []
    kind = str(safe_facts.get("kind", "round"))
    subject_id = redact_private_text(safe_facts.get("subjectId", ""))
    source_refs = report_source_refs({"factsUsed": facts_used, "missingData": missing_data})
    safe_narrative = redact_private_text(narrative)
    unsupported_claims = audit_report_narrative(safe_narrative, facts_used, missing_data)
    confidence = "low" if unsupported_claims else _confidence(facts_used, missing_data)
    return {
        "schema": "ai-caddie-review-report-v1",
        "kind": kind,
        "subjectId": subject_id,
        "sourceRefs": source_refs,
        "provider": provider,
        "model": model,
        "factsUsed": facts_used,
        "missingData": missing_data,
        "inferencesMade": build_report_inferences(facts_used, missing_data),
        "unsupportedClaims": unsupported_claims,
        "factBinding": {
            "state": "needs_review" if unsupported_claims else "bound",
            "unsupportedClaimCount": len(unsupported_claims),
        },
        "narrative": safe_narrative,
        "confidence": confidence,
    }


def audit_report_narrative(
    narrative: str,
    facts_used: list[dict[str, Any]],
    missing_data: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    support = _fact_support_index(facts_used)
    missing_labels = _missing_labels(missing_data)
    missing_refs = _missing_refs(missing_data)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for sentence in _narrative_sentences(narrative):
        for fragment in _claim_fragments(sentence):
            fragment_text = fragment.strip(" ,")
            if not fragment_text:
                continue
            for category, rule in _UNSUPPORTED_CLAIM_RULES.items():
                mentioned = _mentioned_support_tokens(fragment_text, category, rule)
                if not mentioned:
                    continue
                if _claim_supported_by_facts(category, mentioned, support):
                    continue
                if _missing_data_callout_allowed(fragment_text, category, missing_labels):
                    continue
                key = (category, fragment_text)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "category": category,
                        "claim": fragment_text[:240],
                        "reason": f"叙述引用了 {category}，但缺乏对应的结构化事实支撑。",
                        "confidence": "low",
                        "sourceRefs": [],
                        "missingDataRefs": missing_refs,
                        "missingDataLabels": missing_labels,
                    }
                )
    return rows


def _narrative_sentences(narrative: str) -> list[str]:
    text = redact_private_text(narrative).replace("\n", " ").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", text) if part.strip()]


def _claim_fragments(sentence: str) -> list[str]:
    return [fragment.strip() for fragment in _CLAIM_FRAGMENT_SPLIT_PATTERN.split(sentence) if fragment.strip()]


def _mentioned_support_tokens(sentence: str, category: str, rule: dict[str, tuple[str, ...]]) -> set[str]:
    lowered = sentence.lower()
    pattern = _CATEGORY_MENTION_PATTERNS[category]
    if not pattern.search(sentence) and not (category == "club" and _CLUB_TOKEN_PATTERN.search(sentence)):
        return set()
    if category == "club":
        tokens = _club_tokens(sentence)
        if tokens:
            return tokens
        return {"club"}
    if category == "weather":
        return _tokens_from_terms(lowered, _WEATHER_VALUE_TOKENS)
    if category == "lie":
        return _tokens_from_terms(lowered, _LIE_VALUE_TOKENS) or {"lie"}
    if category == "penalty":
        tokens = _tokens_from_terms(lowered, _PENALTY_VALUE_TOKENS)
        if re.search(r"\bout of bounds\b", lowered):
            tokens.add("ob")
        if re.search(r"\bpenalt(?:y|ies)\b", lowered):
            tokens.add("penalty")
        return tokens or {"penalty"}
    if category == "practice_advice":
        return _tokens_from_terms(lowered, _PRACTICE_SUPPORT_TERMS) or {"practice_advice"}
    if category == "strategy_advice":
        return _strategy_claim_tokens(lowered) or {"strategy_advice"}
    if category == "causal_claim":
        return _causal_claim_tokens(lowered) or {"causal_claim"}
    return set(rule["keywords"])


def _tokens_from_terms(text: str, terms: set[str]) -> set[str]:
    tokens = set()
    for term in terms:
        if _term_in_text(term, text):
            tokens.add(_normalize_support_token(term))
    return tokens


def _term_in_text(term: str, text: str) -> bool:
    if " " in term:
        return term in text
    return bool(re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE))


def _normalize_support_token(value: str) -> str:
    token = value.strip().lower().replace(" ", "_")
    if token == "penalties":
        return "penalty"
    if token == "out_of_bounds":
        return "ob"
    if token == "gusts":
        return "gust"
    return token


def _strategy_claim_tokens(text: str) -> set[str]:
    tokens = _tokens_from_terms(text, _STRATEGY_ACTION_TERMS)
    if _term_in_text("should", text):
        tokens.add("should")
    return tokens


def _causal_claim_tokens(text: str) -> set[str]:
    tokens = {token for token in _text_identity_tokens(text) if token in _CAUSAL_CLASSIFICATION_TOKENS}
    tokens.update(re.findall(r"\b[a-z]+_[a-z0-9_]+\b", text))
    if _term_in_text("three putt", text):
        tokens.add("three_putt")
    if _term_in_text("approach short", text):
        tokens.add("approach_short")
    if not tokens and any(_term_in_text(term.replace("_", " "), text) for term in _CAUSAL_CUE_TOKENS):
        tokens.add("causal_claim")
    return tokens


def _text_identity_tokens(value: Any) -> set[str]:
    text = str(value).lower()
    words = [word for word in re.findall(r"[a-z0-9]+", text) if len(word) > 1]
    tokens = set(words)
    tokens.update(f"{left}_{right}" for left, right in zip(words, words[1:]))
    return tokens


def _club_tokens(value: Any) -> set[str]:
    text = str(value)
    tokens = {match.group(0).lower() for match in _CLUB_TOKEN_PATTERN.finditer(text)}
    lowered = text.lower()
    for word in _CLUB_WORD_TOKENS:
        if _term_in_text(word, lowered):
            tokens.add(word)
    return tokens


def _claim_supported_by_facts(category: str, mentioned: set[str], support: dict[str, set[str]]) -> bool:
    supported = support.get(category, set())
    if category == "club":
        exact_tokens = {token for token in mentioned if token not in _CLUB_WORD_TOKENS and token != "club"}
        return exact_tokens.issubset(supported) if exact_tokens else bool(supported)
    if category == "weather":
        exact_tokens = {token for token in mentioned if token != "weather"}
        return exact_tokens.issubset(supported) if exact_tokens else bool(supported)
    if category == "lie":
        exact_tokens = {token for token in mentioned if token != "lie"}
        return exact_tokens.issubset(supported) if exact_tokens else bool(supported)
    if category == "penalty":
        if "water" in mentioned and ("water" in supported or "hazard" in supported):
            return True
        return mentioned.issubset(supported)
    if category == "practice_advice":
        exact_tokens = {token for token in mentioned if token != "practice_advice"}
        return bool(exact_tokens) and exact_tokens.issubset(supported)
    if category == "strategy_advice":
        exact_tokens = {
            token
            for token in mentioned
            if token not in _STRATEGY_MODAL_TOKENS and token != "strategy_advice"
        }
        return bool(exact_tokens) and exact_tokens.issubset(supported)
    if category == "causal_claim":
        exact_tokens = {token for token in mentioned if token not in _CAUSAL_CUE_TOKENS and token != "causal_claim"}
        return bool(exact_tokens) and exact_tokens.issubset(supported)
    return bool(supported)


def _fact_support_index(facts_used: list[dict[str, Any]]) -> dict[str, set[str]]:
    support = {
        "weather": set(),
        "lie": set(),
        "penalty": set(),
        "club": set(),
        "practice_advice": set(),
        "strategy_advice": set(),
        "causal_claim": set(),
    }
    for fact in facts_used:
        if not isinstance(fact, dict):
            continue
        fact_value = fact.get("value")
        if _meaningful_fact_value(fact_value):
            label_source = f"{fact.get('label', '')} {fact.get('source', '')}".lower()
            if any(_term_in_text(term, label_source) for term in _WEATHER_VALUE_TOKENS):
                support["weather"].add("weather")
            if any(_term_in_text(term, label_source) for term in _PENALTY_VALUE_TOKENS):
                support["penalty"].add("penalty")
        _collect_fact_support(fact_value, support)
    return support


def _collect_fact_support(value: Any, support: dict[str, set[str]], key_hint: str = "") -> None:
    normalized_key = key_hint.lower().replace("_", "")
    if isinstance(value, dict):
        for key, item in value.items():
            if key_hint.lower() in {"clubprofiles", "club_profiles"}:
                support["club"].update(_club_tokens(key))
            if _meaningful_fact_value(item):
                _add_keyed_support(str(key), item, support)
            _collect_fact_support(item, support, str(key))
        return
    if isinstance(value, list):
        for item in value:
            _collect_fact_support(item, support, key_hint)
        return
    if not _meaningful_fact_value(value):
        return
    text = str(value).lower()
    if normalized_key in _CLUB_FACT_KEYS:
        support["club"].update(_club_tokens(value))
    if normalized_key in _LIE_FACT_KEYS:
        support["lie"].update(_tokens_from_terms(text, _LIE_VALUE_TOKENS) or {"lie"})
    if normalized_key in {"findingtype", "evidencetext"}:
        support["lie"].update(_tokens_from_terms(text, _LIE_VALUE_TOKENS))
    if normalized_key in _WEATHER_FACT_KEYS:
        support["weather"].update(_weather_tokens_for_key(normalized_key))
    if normalized_key in _PENALTY_FACT_KEYS:
        support["penalty"].update(_tokens_from_terms(text, _PENALTY_VALUE_TOKENS) or {"penalty"})


def _add_keyed_support(key: str, value: Any, support: dict[str, set[str]]) -> None:
    normalized_key = key.lower().replace("_", "")
    text = str(value).lower()
    if normalized_key in _WEATHER_FACT_KEYS:
        support["weather"].update(_weather_tokens_for_key(normalized_key))
    if normalized_key in _LIE_FACT_KEYS:
        support["lie"].update(_tokens_from_terms(text, _LIE_VALUE_TOKENS) or {"lie"})
    if normalized_key in {"findingtype", "evidencetext"}:
        support["lie"].update(_tokens_from_terms(text, _LIE_VALUE_TOKENS))
    if normalized_key in _PENALTY_FACT_KEYS:
        support["penalty"].update(_tokens_from_terms(text, _PENALTY_VALUE_TOKENS) or {"penalty"})
    if normalized_key in _CLUB_FACT_KEYS:
        support["club"].update(_club_tokens(value))
    if any(term in normalized_key for term in _PRACTICE_SUPPORT_TERMS):
        support["practice_advice"].update(_tokens_from_terms(text, _PRACTICE_SUPPORT_TERMS) or {"practice"})
    if normalized_key in {"target", "targetnote", "strategy", "strategynote", "route", "option", "avoidzones", "forbiddenzones"}:
        support["strategy_advice"].update(_strategy_claim_tokens(text))
    if normalized_key in {"issue", "classification", "phase", "modelupdatesuggestion"}:
        support["causal_claim"].update(_text_identity_tokens(value))


def _weather_tokens_for_key(normalized_key: str) -> set[str]:
    tokens = {"weather"}
    if "wind" in normalized_key:
        tokens.add("wind")
    if "temperature" in normalized_key:
        tokens.add("temperature")
    if "precipitation" in normalized_key or "rain" in normalized_key:
        tokens.update({"precipitation", "rain"})
    if "gust" in normalized_key:
        tokens.add("gust")
    return tokens


def _meaningful_fact_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float, bool)):
        return True
    if isinstance(value, list):
        return any(_meaningful_fact_value(item) for item in value)
    if isinstance(value, dict):
        return any(_meaningful_fact_value(item) for item in value.values())
    return True


def _missing_data_callout_allowed(sentence: str, category: str, missing_labels: list[str]) -> bool:
    lowered = sentence.lower()
    if not any(term in lowered for term in _MISSING_CALLOUT_TERMS):
        return False
    if category == "strategy_advice" and _strategy_uncertainty_callout(lowered):
        return True
    if category in {label.lower() for label in missing_labels}:
        return True
    if category == "weather" and any(label.lower() in {"wind", "weather"} for label in missing_labels):
        return True
    return False


def _strategy_uncertainty_callout(lowered_sentence: str) -> bool:
    if "should" not in lowered_sentence:
        return False
    if not any(term in lowered_sentence for term in ("uncertain", "unknown", "missing", "unavailable", "no data")):
        return False
    return not any(_term_in_text(term, lowered_sentence) for term in _STRATEGY_ACTION_TERMS)


def generate_report(facts: dict[str, Any], provider: TextProvider) -> dict[str, Any]:
    safe_facts = _redact_value(facts)

    prompt = (
        "用简体中文撰写基于证据的高尔夫复盘。仅使用 factsUsed 中的事实。"
        "不得编造天气、谎言、意图、球杆、罚杆或私人数据。"
        "明确指出 missingData 中的缺失数据。\n\n"
        f"{json.dumps(safe_facts, ensure_ascii=False, indent=2)}"
    )
    narrative = provider.chat(
        [
            LLMMessage(role="system", content="你是AI球童。事实是权威的；不确定性必须明确呈现。"),
            LLMMessage(role="user", content=prompt),
        ],
        max_tokens=1200,
    )
    return _report_payload(
        safe_facts,
        provider=provider.__class__.__name__,
        model=provider.model,
        narrative=narrative,
    )


def generate_deterministic_report(facts: dict[str, Any]) -> dict[str, Any]:
    safe_facts = _redact_value(facts)
    facts_used = safe_facts.get("factsUsed", []) if isinstance(safe_facts.get("factsUsed"), list) else []
    missing_data = safe_facts.get("missingData", []) if isinstance(safe_facts.get("missingData"), list) else []
    kind = str(safe_facts.get("kind", "round"))
    return _report_payload(
        safe_facts,
        provider="DeterministicReportProvider",
        model="deterministic-facts-v1",
        narrative=_deterministic_report_narrative(kind=kind, facts_used=facts_used, missing_data=missing_data),
    )
