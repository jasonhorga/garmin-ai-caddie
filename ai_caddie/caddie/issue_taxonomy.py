from __future__ import annotations

from typing import Any

IssuePhase = str
IssueConfidence = str


_TAXONOMY: dict[str, dict[str, str]] = {
    "missing_shots": {
        "phase": "Data Quality",
        "reason": "missing shot data",
        "confidence": "high",
    },
    "double_or_worse": {
        "phase": "Course Management",
        "reason": "double or worse",
        "confidence": "high",
    },
    "hazard_result": {
        "phase": "Penalty",
        "reason": "other hazard result",
        "confidence": "medium",
    },
    "ob": {
        "phase": "Penalty",
        "reason": "OB",
        "confidence": "high",
    },
    "water": {
        "phase": "Penalty",
        "reason": "water",
        "confidence": "high",
    },
    "bunker": {
        "phase": "Short Game",
        "reason": "bunker",
        "confidence": "medium",
    },
    "rough": {
        "phase": "Course Management",
        "reason": "rough",
        "confidence": "medium",
    },
    "approach_short": {
        "phase": "Approach",
        "reason": "approach short",
        "confidence": "medium",
    },
    "approach_long": {
        "phase": "Approach",
        "reason": "approach long",
        "confidence": "medium",
    },
    "approach_left": {
        "phase": "Approach",
        "reason": "approach left",
        "confidence": "medium",
    },
    "approach_right": {
        "phase": "Approach",
        "reason": "approach right",
        "confidence": "medium",
    },
    "wrong_club": {
        "phase": "Club Confidence",
        "reason": "wrong club",
        "confidence": "medium",
    },
    "poor_lie": {
        "phase": "Course Management",
        "reason": "poor lie",
        "confidence": "medium",
    },
    "wind": {
        "phase": "Course Management",
        "reason": "wind",
        "confidence": "medium",
    },
    "slope": {
        "phase": "Course Management",
        "reason": "slope",
        "confidence": "medium",
    },
    "blocked_view": {
        "phase": "Course Management",
        "reason": "blocked view",
        "confidence": "medium",
    },
    "recovery_failed": {
        "phase": "Course Management",
        "reason": "recovery failed",
        "confidence": "medium",
    },
    "tee_miss": {
        "phase": "Tee",
        "reason": "tee miss",
        "confidence": "medium",
    },
    "fairway_missed_left": {
        "phase": "Tee",
        "reason": "fairway missed left",
        "confidence": "medium",
    },
    "fairway_missed_right": {
        "phase": "Tee",
        "reason": "fairway missed right",
        "confidence": "medium",
    },
    "tee_position_bad": {
        "phase": "Tee",
        "reason": "tee position bad",
        "confidence": "medium",
    },
    "three_putt": {
        "phase": "Putting",
        "reason": "three putt",
        "confidence": "medium",
    },
    "too_aggressive": {
        "phase": "Course Management",
        "reason": "too aggressive",
        "confidence": "medium",
    },
    "too_conservative": {
        "phase": "Course Management",
        "reason": "too conservative",
        "confidence": "medium",
    },
    "club_uncertainty": {
        "phase": "Club Confidence",
        "reason": "club uncertainty",
        "confidence": "medium",
    },
    "low_confidence_club": {
        "phase": "Club Confidence",
        "reason": "low-confidence club",
        "confidence": "medium",
    },
    "missing_putt_data": {
        "phase": "Data Quality",
        "reason": "missing putt data",
        "confidence": "high",
    },
    "missing_geometry": {
        "phase": "Data Quality",
        "reason": "missing geometry",
        "confidence": "high",
    },
    "weak_sample_size": {
        "phase": "Data Quality",
        "reason": "weak sample size",
        "confidence": "medium",
    },
}


def _normalized_reason(issue: str) -> str:
    return issue.strip().replace("_", " ") or "unknown issue"


def classify_issue(issue: str) -> dict[str, str]:
    key = str(issue or "").strip().lower()
    if key in _TAXONOMY:
        return dict(_TAXONOMY[key])
    return {
        "phase": "Course Management",
        "reason": _normalized_reason(key),
        "confidence": "low",
    }


# On real data a single issue (e.g. bunker across 441 rounds) accumulates
# ~1300 source refs, stored twice per row (refs + sourceRefs) — this dominated
# the ~20MB /history/stats payload. The refs are only example drill-down links:
# the true sample size is the separate ``count`` field, and drill-down resolves
# via /api/v2/history/drilldown/{ref} (not these inline arrays). So cap the
# stored examples while keeping ``count`` the full, accurate total.
ISSUE_REFS_CAP = 100


def issue_record(
    issue: str,
    refs: list[str],
    *,
    source: str = "deterministic",
) -> dict[str, Any]:
    key = str(issue or "").strip().lower()
    classification = classify_issue(key)
    capped = refs[:ISSUE_REFS_CAP]
    return {
        "issue": key,
        "count": len(refs),
        "refs": capped,
        "sourceRefs": capped,
        "source": source,
        **classification,
    }
