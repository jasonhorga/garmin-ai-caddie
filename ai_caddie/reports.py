from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from ai_caddie.history import HistoryData
from ai_caddie.llm_providers import LLMMessage, TextProvider, redact_secret_text


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
_STRATEGY_SUPPORT_TERMS = {
    "strategy",
    "decision",
    "caddie",
    "plan",
    "route",
    "target",
    "option",
    "avoid",
}
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
_CAUSAL_SUPPORT_TERMS = {"issue", "issues", "diagnosis", "audit", "cause", "strokeslost", "estimatedstrokeslost"}
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
        missing_data.append({"label": "round_reference", "reason": f"{round_id} not present in drillDown.roundIds"})
    if history_data is not None and not round_row:
        missing_data.append({"label": "round_scorecard", "reason": f"{round_id} not present in normalized history data"})
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


def _round_scorecard_fact(round_row: dict[str, Any]) -> dict[str, Any]:
    score = round_row.get("strokes")
    par = round_row.get("par")
    return {
        "roundRef": str(round_row.get("id")),
        "date": round_row.get("date"),
        "course": round_row.get("course"),
        "courseKey": round_row.get("courseKey"),
        "holesCompleted": round_row.get("holesCompleted"),
        "score": score,
        "par": par,
        "toPar": int(score) - int(par) if isinstance(score, int) and isinstance(par, int) else None,
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


def _compact_decision_audit_row(row: dict[str, Any]) -> dict[str, Any]:
    compact_keys = [
        "classification",
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
    return {key: row[key] for key in compact_keys if key in row}


def _decision_audit_trends_fact(history_stats: dict[str, Any]) -> dict[str, Any] | None:
    trends = _decision_audit_trends(history_stats)
    if not trends:
        return None
    classification_counts = [
        _compact_decision_audit_row(row)
        for row in trends.get("classificationCounts", [])
        if isinstance(row, dict)
    ]
    recent_drivers = [
        _compact_decision_audit_row(row)
        for row in trends.get("recentCostDrivers", [])
        if isinstance(row, dict)
    ]
    return {
        "totalAudits": trends.get("totalAudits", 0),
        "auditedRoundRefs": _as_string_list(trends.get("auditedRoundRefs")),
        "classificationCounts": classification_counts[:5],
        "recentCostDrivers": recent_drivers[:5],
    }


def _decision_audit_fact_source_refs(value: dict[str, Any]) -> list[str]:
    classification_counts = value.get("classificationCounts") if isinstance(value.get("classificationCounts"), list) else []
    recent_drivers = value.get("recentCostDrivers") if isinstance(value.get("recentCostDrivers"), list) else []
    rows = [row for row in [*classification_counts, *recent_drivers] if isinstance(row, dict)]
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
    for row in trends.get("classificationCounts", []) if isinstance(trends.get("classificationCounts"), list) else []:
        if not isinstance(row, dict):
            continue
        refs = _row_refs_match_round(row, round_id)
        if refs:
            compact = _compact_decision_audit_row(row)
            compact["refs"] = refs
            rows.append(compact)
    return rows[:8]


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
        missing_data.append({"label": "period", "reason": f"{period} not present in history time aggregates"})
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
) -> dict[str, Any]:
    record = {
        "id": uuid4().hex,
        "storedAt": _stored_at(),
        "kind": kind,
        "subjectId": redact_private_text(subject_id),
        "report": _redact_value(report),
    }
    path = report_store_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return record


def list_report_records(*, root: Path | str | None = None) -> list[dict[str, Any]]:
    path = report_store_file(root)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def latest_report_record(kind: str, subject_id: str, *, root: Path | str | None = None) -> dict[str, Any] | None:
    safe_subject_id = redact_private_text(subject_id)
    matches = [
        record
        for record in list_report_records(root=root)
        if record.get("kind") == kind and str(record.get("subjectId")) == safe_subject_id
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda record: str(record.get("storedAt") or ""))[-1]


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
                claim = f"Recent review is based on {round_count} rounds." if label == "summary_trend" else f"Report is based on {round_count} rounds."
                _append_inference(rows, _inference(claim, fact, default_confidence=confidence, missing_data=missing_data))
                continue
        if label in {"top_issue", "top_issues", "round_issues"}:
            issue = _first_issue(value)
            if issue:
                _append_inference(rows, _inference(f"Primary scoring-loss signal is {issue}.", fact, default_confidence=confidence, missing_data=missing_data))
                continue
        if label in {"decision_audit_trends", "round_decision_audits"}:
            classification = _first_audit_classification(value)
            if classification:
                _append_inference(
                    rows,
                    _inference(
                        f"Caddie audit loop highlights {classification} as a decision issue.",
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
                course_text = f" at {course}" if course else ""
                _append_inference(rows, _inference(f"Round score was {score}{course_text}.", fact, default_confidence=confidence, missing_data=missing_data))

    if not rows and facts_used:
        synthetic_fact = {
            "label": "facts_used",
            "sourceRefs": report_source_refs({"factsUsed": facts_used}),
        }
        rows.append(
            _inference(
                f"Narrative is constrained to {len(facts_used)} structured facts.",
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
        claims = [f"Review is constrained to {len(facts_used)} structured facts."]

    title = "Round review" if kind == "round" else "Trend review"
    parts = [f"{title}: {' '.join(claims[:5])}"]
    missing_labels = _missing_labels(missing_data)
    if missing_labels:
        parts.append(f"Missing data: {', '.join(missing_labels[:8])}.")
    parts.append("Every statement is bound to the structured facts and source references in this report.")
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
                        "reason": f"Narrative references {category} without a supporting structured fact.",
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
    if category in {"practice_advice", "strategy_advice", "causal_claim"}:
        return {category}
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
            normalized_label_source = label_source.replace("_", "").replace("-", "")
            if any(term in normalized_label_source for term in _PRACTICE_SUPPORT_TERMS):
                support["practice_advice"].add("practice_advice")
            if any(term in normalized_label_source for term in _STRATEGY_SUPPORT_TERMS):
                support["strategy_advice"].add("strategy_advice")
            if any(term in normalized_label_source for term in _CAUSAL_SUPPORT_TERMS):
                support["causal_claim"].add("causal_claim")
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
    if normalized_key in _PENALTY_FACT_KEYS:
        support["penalty"].update(_tokens_from_terms(text, _PENALTY_VALUE_TOKENS) or {"penalty"})
    if normalized_key in _CLUB_FACT_KEYS:
        support["club"].update(_club_tokens(value))
    if any(term in normalized_key for term in _PRACTICE_SUPPORT_TERMS):
        support["practice_advice"].add("practice_advice")
    if any(term in normalized_key for term in _STRATEGY_SUPPORT_TERMS):
        support["strategy_advice"].add("strategy_advice")
    if any(term in normalized_key for term in _CAUSAL_SUPPORT_TERMS):
        support["causal_claim"].add("causal_claim")
    if _term_in_text("strategy", text) or _term_in_text("execution", text):
        support["causal_claim"].add("causal_claim")


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
        "Write an evidence-bound golf review. Use only factsUsed. "
        "Do not invent weather, lie, intent, club, penalties, or private data. "
        "Call out missingData explicitly.\n\n"
        f"{json.dumps(safe_facts, ensure_ascii=False, indent=2)}"
    )
    narrative = provider.chat(
        [
            LLMMessage(role="system", content="You are AI Caddie. Facts are authoritative; uncertainty must be visible."),
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
