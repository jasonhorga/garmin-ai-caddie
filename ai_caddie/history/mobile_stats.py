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
    "nineBreakdown",
    "loopKeys",
    "nineOnlyRounds",
    "rounds",
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
_TIME_KEYS = ("byYear", "byQuarter", "byMonth", "byDay", "improvement", "playFrequency")
_SCORING_KEYS = (
    "scoreBands", "outcomes", "outcomeDistribution", "difficultyAdjusted", "byPar", "phaseStats", "putting",
    "approachMiss", "teeDirection",
    # B0 new statistics fields
    "penalties", "scrambling", "roundSequences", "loops", "nineCombos", "nineOnlyRounds", "hardestHoles",
)
_DIAGNOSIS_KEYS = ("topIssue", "issueTrends", "windowSize")
_PROFILE_KEYS = ("topStrength", "topWeakness", "strengths", "weaknesses", "caddieBiases")
_QUALITY_KEYS = ("label", "state", "ready", "total")


# Heavy evidence arrays that balloon the payload but the compact 统计 screens never render: the
# real bulk on live data is the per-row ``*Refs`` arrays (``holeRefs`` ~50KB on putting,
# ``bogeyOrWorseRefs`` ~21KB per par row, …) plus a few named deltas/histograms. We strip every
# key ending in ``Refs`` (plural) wherever it is nested — but KEEP the small singular drill ids
# (``bestRoundRef``/``worstRoundRef`` don't end in "Refs", and ``roundIds`` is kept) so a stat can
# still open its round.
_DROP_KEYS = {"roundOverRoundDeltas", "outcomeRows", "scoreHistogram", "decisionAuditTrends"}

# B5 payload budget (IMPLEMENTATION_PLAN "B0 新统计字段", 体积): ``scoring.roundSequences`` is one
# per-hole row per round (~298 KB raw on real history). The mobile screens only show recent rounds'
# hole strips, so the compact payload keeps the newest rounds; the full series stays on
# ``/api/v2/history/stats``.
MOBILE_ROUND_SEQUENCE_LIMIT = 20


def _strip_refs(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_refs(v) for k, v in value.items() if not k.endswith("Refs") and k not in _DROP_KEYS}
    if isinstance(value, list):
        return [_strip_refs(item) for item in value]
    return value


def _pick(row: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    return {key: row[key] for key in keys if key in row}


# B5 表现分析 "和之前比": each narrow window compares with the comparable period right before it
# (10 vs the 10 before, 20 vs the 20 before, the last year vs the year before); ``all`` has none.
PREVIOUS_WINDOW = {"last10": "prev10", "last20": "prev20", "12m": "prev12m"}
_PREVIOUS_SCORING_KEYS = ("teeDirection", "approachMiss", "scrambling", "putting", "phaseStats")


# A count window compares only with a COMPLETE previous sample: "和前 10 场比" against 5 rounds would
# be a different comparison under the same label. ``prev12m`` is a date range, so any rounds count.
PREVIOUS_REQUIRED_ROUNDS = {"prev10": 10, "prev20": 20}


def build_mobile_previous(stats: dict[str, Any], window: str) -> dict[str, Any] | None:
    """The compact comparison block for ``window``'s previous period, or None when it has no
    rounds (a delta against nothing would be invented). A count window whose previous period is
    short of its full sample carries ``requiredRounds`` and no ``scoring``, so the phone says how
    many rounds there are instead of comparing."""
    summary = stats.get("summary") if isinstance(stats.get("summary"), dict) else {}
    rounds = summary.get("totalRounds")
    if not rounds:
        return None
    block: dict[str, Any] = {"window": window, "roundCount": rounds}
    required = PREVIOUS_REQUIRED_ROUNDS.get(window)
    if required is not None:
        block["requiredRounds"] = required
        if rounds < required:
            return block
    scoring = stats.get("scoring") if isinstance(stats.get("scoring"), dict) else {}
    return _strip_refs({**block, "scoring": _pick(scoring, _PREVIOUS_SCORING_KEYS)})


def _cap_round_sequences(scoring: dict[str, Any]) -> dict[str, Any]:
    """Keep the newest ``MOBILE_ROUND_SEQUENCE_LIMIT`` rows (the server lists them newest first)."""
    sequences = scoring.get("roundSequences")
    if isinstance(sequences, list) and len(sequences) > MOBILE_ROUND_SEQUENCE_LIMIT:
        return {**scoring, "roundSequences": sequences[:MOBILE_ROUND_SEQUENCE_LIMIT]}
    return scoring


def build_mobile_stats(stats: dict[str, Any]) -> dict[str, Any]:
    """Slice the full history-stats dict down to the compact mobile 统计 payload."""
    time = stats.get("time") if isinstance(stats.get("time"), dict) else {}
    scoring = stats.get("scoring") if isinstance(stats.get("scoring"), dict) else {}
    diagnosis = stats.get("diagnosis") if isinstance(stats.get("diagnosis"), dict) else {}
    profile = stats.get("playerProfile") if isinstance(stats.get("playerProfile"), dict) else {}
    courses = stats.get("courses") if isinstance(stats.get("courses"), list) else []
    clubs = stats.get("clubs") if isinstance(stats.get("clubs"), list) else []
    quality = stats.get("dataQuality") if isinstance(stats.get("dataQuality"), list) else []
    payload = {
        "schema": SCHEMA,
        "dataMode": stats.get("dataMode"),
        "summary": stats.get("summary") if isinstance(stats.get("summary"), dict) else {},
        "time": _pick(time, _TIME_KEYS),
        "trend": stats.get("trend") if isinstance(stats.get("trend"), dict) else {},
        "scoring": _cap_round_sequences(_pick(scoring, _SCORING_KEYS)),
        "records": stats.get("records") if isinstance(stats.get("records"), dict) else {},
        "courses": [_pick(course, _COURSE_KEYS) for course in courses],
        "clubs": [_pick(club, _CLUB_KEYS) for club in clubs],
        "diagnosis": _pick(diagnosis, _DIAGNOSIS_KEYS),
        "playerProfile": _pick(profile, _PROFILE_KEYS),
        "dataQuality": [_pick(row, _QUALITY_KEYS) for row in quality],
    }
    # Drop the heavy per-row evidence arrays nested anywhere (holeRefs/*Refs/outcomeRows/…) — on real
    # data these are ~90% of the bytes and the compact screens never use them; roundIds + the singular
    # bestRoundRef/recentRoundId survive for drill-down.
    return _strip_refs(payload)
