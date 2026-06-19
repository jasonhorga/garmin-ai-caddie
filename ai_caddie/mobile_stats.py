"""Compact mobile slice of ``build_history_stats``.

The full ``/api/v2/history/stats`` payload is ~11MB on real data — too big to download and
parse on a phone. The 统计 screens only need the aggregate NUMBERS (basic / deep / periodic /
per-course / per-club) plus the small drill-down round ids, not the giant per-hole table
(``holes[]`` is ~1275 rows) or the heavy per-row evidence refs.

``build_mobile_stats`` keeps the metric sections and the *small* drill refs (``scoreBands[].roundIds``,
``courses[].recentRoundId/roundIds``) so a stat can still open the round it came from, and drops:

- ``holes[]`` entirely (per-hole aggregate is fetched per course on demand if/when needed),
- the heavy per-row ref arrays (``sourceRefs``/``shotRefs``/``holeRefs``/``roundRefs``) everywhere.

It is a pure transform of the already-built stats dict, so it is a cache hit after warm and adds
no compute. The single-round 复盘 stays on ``/api/v2/history/rounds/{ref}`` (already compact).
"""

from __future__ import annotations

from typing import Any

SCHEMA = "ai-caddie-mobile-stats-v1"

# Metric numbers to keep per course (drop roundRefs/sourceRefs/coverage detail — keep small drill ids).
_COURSE_KEYS = (
    "courseKey",
    "courseName",
    "roundCount",
    "average18",
    "bestScore",
    "worstScore",
    "averageDifferential",
    "bestDifferential",
    "recentForm",
    "recentRoundId",
    "roundIds",
    "location",
)
# Club distance model fields (按码 conversion happens on the client); drop roundIds-heavy evidence.
_CLUB_KEYS = (
    "club",
    "sampleCount",
    "validSampleCount",
    "median",
    "p10",
    "p90",
    "max",
    "dispersionRange",
    "consistency",
    "distanceTrend",
    "confidence",
)
_TIME_KEYS = ("byYear", "byQuarter", "byMonth", "improvement", "playFrequency")
_SCORING_KEYS = ("scoreBands", "outcomes", "difficultyAdjusted", "byPar", "phaseStats", "putting", "approachMiss", "teeDirection")
_DIAGNOSIS_KEYS = ("topIssue", "issueTrends", "windowSize")
_PROFILE_KEYS = ("topStrength", "topWeakness", "strengths", "weaknesses", "caddieBiases")
_QUALITY_KEYS = ("label", "state", "ready", "total")


def _pick(row: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    return {key: row[key] for key in keys if key in row}


def build_mobile_stats(stats: dict[str, Any]) -> dict[str, Any]:
    """Slice the full history-stats dict down to the compact mobile 统计 payload."""
    time = stats.get("time") if isinstance(stats.get("time"), dict) else {}
    scoring = stats.get("scoring") if isinstance(stats.get("scoring"), dict) else {}
    diagnosis = stats.get("diagnosis") if isinstance(stats.get("diagnosis"), dict) else {}
    profile = stats.get("playerProfile") if isinstance(stats.get("playerProfile"), dict) else {}
    courses = stats.get("courses") if isinstance(stats.get("courses"), list) else []
    clubs = stats.get("clubs") if isinstance(stats.get("clubs"), list) else []
    quality = stats.get("dataQuality") if isinstance(stats.get("dataQuality"), list) else []
    return {
        "schema": SCHEMA,
        "dataMode": stats.get("dataMode"),
        "summary": stats.get("summary") if isinstance(stats.get("summary"), dict) else {},
        "time": _pick(time, _TIME_KEYS),
        "scoring": _pick(scoring, _SCORING_KEYS),
        "records": stats.get("records") if isinstance(stats.get("records"), dict) else {},
        "courses": [_pick(course, _COURSE_KEYS) for course in courses],
        "clubs": [_pick(club, _CLUB_KEYS) for club in clubs],
        "diagnosis": _pick(diagnosis, _DIAGNOSIS_KEYS),
        "playerProfile": _pick(profile, _PROFILE_KEYS),
        "dataQuality": [_pick(row, _QUALITY_KEYS) for row in quality],
    }
