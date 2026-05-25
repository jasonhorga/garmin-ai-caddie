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
    "tee_miss": {
        "phase": "Tee",
        "reason": "tee miss",
        "confidence": "medium",
    },
    "three_putt": {
        "phase": "Putting",
        "reason": "three putt",
        "confidence": "medium",
    },
    "club_uncertainty": {
        "phase": "Club Confidence",
        "reason": "club uncertainty",
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


def issue_record(
    issue: str,
    refs: list[str],
    *,
    source: str = "deterministic",
) -> dict[str, Any]:
    key = str(issue or "").strip().lower()
    classification = classify_issue(key)
    return {
        "issue": key,
        "count": len(refs),
        "refs": refs,
        "source": source,
        **classification,
    }
