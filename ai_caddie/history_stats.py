from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Literal
import math

from ai_caddie.annotations import list_annotations
from ai_caddie.decision import list_decision_audits
from ai_caddie.geometry_evidence import geometry_coverage_for_course, geometry_coverage_for_hole
from ai_caddie.history import HistoryData, average, percentile
from ai_caddie.history_drilldown import build_drilldown_index
from ai_caddie.issue_taxonomy import issue_record
from ai_caddie.reports import list_report_records
from ai_caddie.weather_context import list_weather_snapshots

DataModeName = Literal["local", "fixture"]
CORRECTION_KINDS = {"club_correction", "lie_correction", "penalty_correction", "putt_correction", "score_correction"}


def _round_id(row: dict[str, Any]) -> str:
    return str(row.get("id"))


def _hole_ref(row: dict[str, Any], hole_number: int) -> str:
    return f"{_round_id(row)}:{hole_number}"


def _shot_ref(shot: dict[str, Any], index: int) -> str:
    return f"{_shot_round_id(shot)}:{shot.get('hole')}:{index}"


def _shot_round_id(shot: dict[str, Any]) -> str:
    return str(shot.get("roundId") or shot.get("scorecardId"))


def _shot_distance(shot: dict[str, Any]) -> Any:
    return shot.get("distance") if shot.get("distance") is not None else shot.get("meters")


def _shot_surface(shot: dict[str, Any]) -> Any:
    return shot.get("surface") if shot.get("surface") is not None else shot.get("endLie")


def _shot_club(shot: dict[str, Any]) -> str:
    return str(shot.get("club") or shot.get("clubName") or "Unknown")


def _normalized_shot(shot: dict[str, Any]) -> dict[str, Any]:
    row = dict(shot)
    row["roundId"] = _shot_round_id(row)
    if row.get("distance") is None and row.get("meters") is not None:
        row["distance"] = row.get("meters")
    if row.get("surface") is None and row.get("endLie") is not None:
        row["surface"] = row.get("endLie")
    if row.get("club") is None and row.get("clubName") is not None:
        row["club"] = row.get("clubName")
    return row


def _payload_value(record: dict[str, Any], *keys: str) -> Any:
    payload = record.get("payload") or {}
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return value
    return None


def _annotations_by_kind(annotations: list[dict[str, Any]] | None, kind: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for record in annotations or []:
        if record.get("kind") == kind:
            rows[str(record.get("targetId") or "")] = record
    return rows


def _corrected_putt_value(
    hole_ref: str,
    original: Any,
    corrections: dict[str, dict[str, Any]],
) -> int | None:
    value = original
    if hole_ref in corrections:
        value = _payload_value(corrections[hole_ref], "to", "putts", "correctedPutts")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _corrected_score_value(
    hole_ref: str,
    original: Any,
    corrections: dict[str, dict[str, Any]],
) -> int | None:
    value = original
    if hole_ref in corrections:
        value = _payload_value(corrections[hole_ref], "to", "score", "strokes", "correctedScore")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _effective_score_data(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> HistoryData:
    score_corrections = _annotations_by_kind(annotations, "score_correction")
    if not score_corrections:
        return data

    rounds: list[dict[str, Any]] = []
    for row in data.rounds:
        row_copy = dict(row)
        holes: list[dict[str, Any]] = []
        round_delta = 0
        corrected_refs: list[str] = []
        for hole in row.get("holes") or []:
            hole_copy = dict(hole)
            number = int(hole_copy.get("number") or 0)
            ref = _hole_ref(row, number) if number else ""
            if ref in score_corrections:
                corrected = _corrected_score_value(ref, hole_copy.get("strokes"), score_corrections)
                if corrected is not None:
                    try:
                        round_delta += corrected - int(hole_copy.get("strokes"))
                    except (TypeError, ValueError):
                        pass
                    hole_copy["strokes"] = corrected
                    hole_copy["_scoreCorrected"] = True
                    corrected_refs.append(ref)
            holes.append(hole_copy)
        if corrected_refs:
            row_copy["holes"] = holes
            if row_copy.get("strokes") is not None:
                try:
                    row_copy["strokes"] = int(row_copy["strokes"]) + round_delta
                except (TypeError, ValueError):
                    pass
            row_copy["_scoreCorrectedRefs"] = corrected_refs
        rounds.append(row_copy)
    return HistoryData(raw_rounds=data.raw_rounds, rounds=rounds, shots=data.shots)


def _effective_shots(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    club_corrections = _annotations_by_kind(annotations, "club_correction")
    lie_corrections = _annotations_by_kind(annotations, "lie_correction")
    rows = []
    for index, shot in enumerate(data.shots):
        row = _normalized_shot(shot)
        ref = _shot_ref(row, index)
        row["_ref"] = ref
        if ref in club_corrections:
            club = _payload_value(club_corrections[ref], "to", "club", "correctedClub")
            if club is not None:
                row["club"] = str(club)
                row["_clubCorrected"] = True
        if ref in lie_corrections:
            lie = _payload_value(lie_corrections[ref], "to", "surface", "lie", "correctedLie")
            if lie is not None:
                row["surface"] = str(lie)
                row["_lieCorrected"] = True
        rows.append(row)
    return rows


def _score_band(score: int) -> str:
    if score < 80:
        return "70s"
    if score < 90:
        return "80s"
    if score < 100:
        return "90s"
    return "100+"


def _score_band_class(label: str) -> str:
    return {"70s": "eagle", "80s": "birdie", "90s": "bogey", "100+": "double"}.get(label, "par")


def _score18(row: dict[str, Any]) -> int | None:
    if row.get("holesCompleted") != 18 or row.get("strokes") is None:
        return None
    try:
        return int(row["strokes"])
    except (TypeError, ValueError):
        return None


def _to_par18(row: dict[str, Any]) -> int | None:
    score = _score18(row)
    if score is None or row.get("par") is None:
        return None
    try:
        return score - int(row["par"])
    except (TypeError, ValueError):
        return None


def _hole_score_bucket(delta: int) -> tuple[str, str, str]:
    if delta <= -2:
        return ("eagleOrBetter", "Eagle+", "eagle")
    if delta == -1:
        return ("birdie", "Birdie", "birdie")
    if delta == 0:
        return ("par", "Par", "par")
    if delta == 1:
        return ("bogey", "Bogey", "bogey")
    return ("doubleOrWorse", "Double+", "double")


def _confidence(sample_count: int) -> str:
    if sample_count >= 10:
        return "high"
    if sample_count >= 2:
        return "medium"
    return "low"


def _coverage(ready: int, total: int) -> dict[str, Any]:
    return {
        "ready": ready,
        "total": total,
        "pct": round(ready / total * 100, 1) if total else 0.0,
    }


def _source_refs(refs: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ref in refs:
        text = str(ref)
        if not text or text == "None" or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _with_aggregate_contract(
    row: dict[str, Any],
    refs: list[Any],
    *,
    ready: int | None = None,
    total: int | None = None,
    confidence_count: int | None = None,
) -> dict[str, Any]:
    source_refs = _source_refs(refs)
    ready_count = len(source_refs) if ready is None else ready
    total_count = len(refs) if total is None else total
    row["sourceRefs"] = source_refs
    row["coverage"] = _coverage(ready_count, total_count)
    row["confidence"] = _confidence(len(source_refs) if confidence_count is None else confidence_count)
    return row


def _with_quality_contract(row: dict[str, Any]) -> dict[str, Any]:
    ready = int(row.get("ready") or 0)
    total = int(row.get("total") or 0)
    refs = row.get("refs") if isinstance(row.get("refs"), list) else []
    row["sourceRefs"] = _source_refs(refs)
    row["coverage"] = _coverage(ready, total)
    row["confidence"] = _confidence(ready)
    return row


def _hole_to_par(hole: dict[str, Any], fallback_par: int | None) -> int | None:
    par = hole.get("par")
    if isinstance(par, int):
        return par
    return fallback_par


def _par_from_string(hole_pars: str, hole_number: int) -> int | None:
    if 1 <= hole_number <= len(hole_pars):
        try:
            return int(hole_pars[hole_number - 1])
        except ValueError:
            return None
    return None


def _int_field(row: dict[str, Any], key: str) -> int | None:
    try:
        value = row.get(key)
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _global_id(row: dict[str, Any], hole_number: int | None = None) -> int | None:
    for key in ("globalId", "courseId"):
        value = _int_field(row, key)
        if value is not None:
            return value
    if hole_number is not None:
        key = "frontNineGlobalCourseId" if hole_number <= 9 else "backNineGlobalCourseId"
        value = _int_field(row, key)
        if value is not None:
            return value
    for key in ("frontNineGlobalCourseId", "backNineGlobalCourseId"):
        value = _int_field(row, key)
        if value is not None:
            return value
    return None


def _course_geometry_coverage(rows: list[dict[str, Any]]) -> str:
    global_id = next((_global_id(row) for row in rows if _global_id(row) is not None), None)
    if global_id is None:
        return "missing"
    hole_numbers = sorted(
        {
            int(hole.get("number"))
            for row in rows
            for hole in (row.get("holes") or [])
            if isinstance(hole, dict) and hole.get("number")
        }
    )
    try:
        return str(geometry_coverage_for_course(global_id, holes=hole_numbers or range(1, 19))["coverage"])
    except Exception:
        return "missing"


def _hole_geometry_coverage(pairs: list[tuple[dict[str, Any], dict[str, Any]]], hole_number: int) -> str:
    global_id = next((_global_id(row, hole_number) for row, _hole in pairs if _global_id(row, hole_number) is not None), None)
    if global_id is None:
        return "missing"
    try:
        return str(geometry_coverage_for_hole(global_id, hole_number)["coverage"])
    except Exception:
        return "missing"


def _summary(data: HistoryData) -> dict[str, Any]:
    rounds18 = [row for row in data.rounds if _score18(row) is not None]
    scores18 = [score for row in rounds18 if (score := _score18(row)) is not None]
    recent_scores18 = [
        score
        for row in sorted(rounds18, key=lambda row: str(row.get("date") or ""), reverse=True)
        if (score := _score18(row)) is not None
    ]
    refs = [_round_id(row) for row in data.rounds]
    return _with_aggregate_contract(
        {
            "totalRounds": len(data.rounds),
            "eighteenHoleRounds": len(rounds18),
            "nineHoleRounds": sum(1 for row in data.rounds if row.get("holesCompleted") == 9),
            "mergedRounds": sum(1 for row in data.rounds if row.get("merged")),
            "courseCount": len({row.get("courseKey") for row in data.rounds if row.get("courseKey")}),
            "shotCount": len(data.shots),
            "average18": average(scores18),
            "median18": round(float(median(scores18)), 1) if scores18 else None,
            "recent5Average": average(recent_scores18[:5]),
            "recent10Average": average(recent_scores18[:10]),
            "recent20Average": average(recent_scores18[:20]),
            "bestScore": min(scores18) if scores18 else None,
            "worstScore": max(scores18) if scores18 else None,
        },
        refs,
    )


def _period_score_bands(score_entries: list[tuple[int, str]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = {"70s": [], "80s": [], "90s": [], "100+": []}
    for score, ref in score_entries:
        grouped[_score_band(score)].append(ref)
    total = len(score_entries)
    return [
        _with_aggregate_contract(
            {
                "label": label,
                "count": len(round_refs),
                "pct": round(len(round_refs) / total * 100, 1) if total else 0.0,
                "className": _score_band_class(label),
                "roundIds": round_refs,
                "roundRefs": round_refs,
            },
            round_refs,
            total=total,
        )
        for label, round_refs in grouped.items()
    ]


def _period_score_histogram(score_entries: list[tuple[int, str]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[str]] = defaultdict(list)
    for score, ref in score_entries:
        grouped[(score // 5) * 5].append(ref)
    total = len(score_entries)
    return [
        _with_aggregate_contract(
            {
                "label": f"{start}-{start + 4}",
                "start": start,
                "end": start + 4,
                "count": len(round_refs),
                "pct": round(len(round_refs) / total * 100, 1) if total else 0.0,
                "roundIds": round_refs,
                "roundRefs": round_refs,
            },
            round_refs,
            total=total,
        )
        for start, round_refs in sorted(grouped.items())
    ]


def _period_outcome_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    outcomes = Counter({"eagleOrBetter": 0, "birdie": 0, "par": 0, "bogey": 0, "doubleOrWorse": 0})
    outcome_refs: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        hole_pars = str(row.get("holePars") or "")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            par = _hole_to_par(hole, _par_from_string(hole_pars, number))
            score = hole.get("strokes")
            if not number or par is None or score is None:
                continue
            try:
                delta = int(score) - int(par)
            except (TypeError, ValueError):
                continue
            key, _label, _class_name = _hole_score_bucket(delta)
            outcomes[key] += 1
            outcome_refs[key].append(_hole_ref(row, number))

    total = sum(len(refs) for refs in outcome_refs.values())
    rows_out = [
        _with_aggregate_contract(
            {
                "key": key,
                "label": label,
                "className": class_name,
                "count": len(outcome_refs.get(key, [])),
                "pct": round(len(outcome_refs.get(key, [])) / total * 100, 1) if total else 0.0,
                "holeRefs": outcome_refs.get(key, []),
            },
            outcome_refs.get(key, []),
            total=total,
        )
        for key, label, class_name in [
            ("eagleOrBetter", "Eagle+", "eagle"),
            ("birdie", "Birdie", "birdie"),
            ("par", "Par", "par"),
            ("bogey", "Bogey", "bogey"),
            ("doubleOrWorse", "Double+", "double"),
        ]
    ]
    return (
        {
            **dict(outcomes),
            "parOrBetter": outcomes["eagleOrBetter"] + outcomes["birdie"] + outcomes["par"],
            "bogeyOrWorse": outcomes["bogey"] + outcomes["doubleOrWorse"],
        },
        rows_out,
    )


def _period_pack(key: str, rows: list[dict[str, Any]], *, total_rounds: int) -> dict[str, Any]:
    date_sorted_rows = sorted(rows, key=lambda row: (str(row.get("date") or ""), _round_id(row)))
    round_ids = [_round_id(row) for row in rows]
    scores18 = [score for row in rows if (score := _score18(row)) is not None]
    score_entries = [(score, _round_id(row)) for row in rows if (score := _score18(row)) is not None]
    to_par18 = [value for row in rows if (value := _to_par18(row)) is not None]
    outcomes, outcome_rows = _period_outcome_rows(rows)
    dates = [str(row.get("date")) for row in date_sorted_rows if row.get("date")]
    best_round = min((row for row in rows if _score18(row) is not None), key=lambda row: _score18(row) or 10_000, default=None)
    worst_round = max((row for row in rows if _score18(row) is not None), key=lambda row: _score18(row) or -1, default=None)
    return _with_aggregate_contract(
        {
            "key": key,
            "year": key if len(key) == 4 else None,
            "roundCount": len(rows),
            "eighteenHoleRounds": len(scores18),
            "nineHoleRounds": sum(1 for row in rows if row.get("holesCompleted") == 9),
            "average18": average(scores18),
            "median18": round(float(median(scores18)), 1) if scores18 else None,
            "bestScore": min(scores18) if scores18 else None,
            "worstScore": max(scores18) if scores18 else None,
            "averageToPar18": average(to_par18),
            "bestRoundRef": _round_id(best_round) if best_round is not None else None,
            "worstRoundRef": _round_id(worst_round) if worst_round is not None else None,
            "firstDate": dates[0] if dates else None,
            "lastDate": dates[-1] if dates else None,
            "roundIds": round_ids,
            "roundRefs": round_ids,
            "scoreBands": _period_score_bands(score_entries),
            "scoreHistogram": _period_score_histogram(score_entries),
            "outcomes": outcomes,
            "outcomeRows": outcome_rows,
        },
        round_ids,
        total=total_rounds,
        confidence_count=len(round_ids),
    )


def _time_stats(data: HistoryData) -> dict[str, Any]:
    by_year: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_quarter: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.rounds:
        date = str(row.get("date") or "")
        year = date[:4] if len(date) >= 4 else "unknown"
        month = date[:7] if len(date) >= 7 else "unknown"
        by_year[year].append(row)
        by_month[month].append(row)
        if len(date) >= 7 and date[5:7].isdigit():
            quarter = (int(date[5:7]) - 1) // 3 + 1
            by_quarter[f"{year}-Q{quarter}"].append(row)
        else:
            by_quarter["unknown"].append(row)

    known_months = [key for key in sorted(by_month) if key != "unknown"]
    most_active_month = None
    if known_months:
        most_active_key = max(known_months, key=lambda key: (len(by_month[key]), key))
        most_active_month = {"key": most_active_key, "roundCount": len(by_month[most_active_key])}

    return {
        "byYear": [_period_pack(key, by_year[key], total_rounds=len(data.rounds)) for key in sorted(by_year, reverse=True)],
        "byQuarter": [_period_pack(key, by_quarter[key], total_rounds=len(data.rounds)) for key in sorted(by_quarter, reverse=True)],
        "byMonth": [_period_pack(key, by_month[key], total_rounds=len(data.rounds)) for key in sorted(by_month, reverse=True)],
        "improvement": _improvement_stats(data),
        "playFrequency": {
            "totalMonths": len(known_months),
            "roundsPerMonth": average([len(by_month[key]) for key in known_months]),
            "mostActiveMonth": most_active_month,
        },
    }


def _score_rounds18(data: HistoryData) -> list[dict[str, Any]]:
    return [
        row
        for row in sorted(data.rounds, key=lambda row: str(row.get("date") or ""))
        if row.get("holesCompleted") == 18 and row.get("strokes") is not None
    ]


def _linear_slope(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    xs = list(range(len(values)))
    x_mean = sum(xs) / len(xs)
    y_mean = sum(values) / len(values)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return None
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values, strict=True))
    return round(numerator / denominator, 2)


def _improvement_direction(delta_average: float | None, slope: float | None) -> str:
    if delta_average is None or slope is None:
        return "insufficient_data"
    if delta_average <= -1.0 and slope < -0.1:
        return "improving"
    if delta_average >= 1.0 and slope > 0.1:
        return "declining"
    return "flat"


def _improvement_confidence(round_count: int) -> str:
    if round_count >= 6:
        return "high"
    if round_count >= 4:
        return "medium"
    if round_count >= 2:
        return "low"
    return "insufficient"


def _improvement_stats(data: HistoryData) -> dict[str, Any]:
    rounds18 = _score_rounds18(data)
    scores = [float(row["strokes"]) for row in rounds18]
    round_refs = [_round_id(row) for row in rounds18]
    if len(scores) < 2:
        return {
            "roundCount": len(scores),
            "windowSize": len(scores),
            "baselineAverage18": average(scores),
            "recentAverage18": average(scores),
            "deltaAverage18": None,
            "strokesPerRoundTrend": None,
            "direction": "insufficient_data",
            "confidence": _improvement_confidence(len(scores)),
            "roundRefs": round_refs,
            "baselineRoundRefs": round_refs,
            "recentRoundRefs": round_refs,
        }

    window_size = min(5, max(2, len(scores) // 2))
    baseline_scores = scores[:window_size]
    recent_scores = scores[-window_size:]
    baseline_average = average(baseline_scores)
    recent_average = average(recent_scores)
    delta_average = round(float(recent_average) - float(baseline_average), 1) if baseline_average is not None and recent_average is not None else None
    slope = _linear_slope(scores)
    return {
        "roundCount": len(scores),
        "windowSize": window_size,
        "baselineAverage18": baseline_average,
        "recentAverage18": recent_average,
        "deltaAverage18": delta_average,
        "strokesPerRoundTrend": slope,
        "direction": _improvement_direction(delta_average, slope),
        "confidence": _improvement_confidence(len(scores)),
        "roundRefs": round_refs,
        "baselineRoundRefs": round_refs[:window_size],
        "recentRoundRefs": round_refs[-window_size:],
    }


ISSUE_STROKE_WEIGHTS: dict[str, float] = {
    "double_or_worse": 1.5,
    "hazard_result": 1.2,
    "water": 1.2,
    "ob": 2.0,
    "three_putt": 1.0,
    "approach_short": 0.8,
    "approach_long": 0.8,
    "approach_left": 0.8,
    "approach_right": 0.8,
    "bunker": 0.7,
    "rough": 0.4,
    "fairway_missed_left": 0.3,
    "fairway_missed_right": 0.3,
    "tee_miss": 0.5,
    "wrong_club": 0.8,
    "blocked_view": 0.6,
    "recovery_failed": 1.0,
}

DECISION_AUDIT_WEIGHTS: dict[str, float] = {
    "strategy": 1.2,
    "execution": 0.9,
    "info_gap": 0.5,
    "unknown": 0.2,
}


def _issue_weight(issue: str) -> float:
    return ISSUE_STROKE_WEIGHTS.get(issue, 0.5)


def _ref_round_id(ref: Any) -> str:
    return str(ref).split(":", 1)[0]


def _round_refs_by_date(data: HistoryData) -> list[str]:
    rows = sorted(data.rounds, key=lambda row: (str(row.get("date") or ""), _round_id(row)))
    return [_round_id(row) for row in rows]


def _diagnosis_direction(baseline_count: int, recent_count: int) -> str:
    delta = recent_count - baseline_count
    if baseline_count == 0 and recent_count > 0:
        return "new"
    if delta > 0:
        return "worsening"
    if delta < 0:
        return "improving"
    return "flat"


def _diagnosis(data: HistoryData, issue_rows: list[dict[str, Any]]) -> dict[str, Any]:
    round_refs = _round_refs_by_date(data)
    window_size = min(5, max(2, len(round_refs) // 2)) if len(round_refs) >= 2 else len(round_refs)
    baseline_round_refs = round_refs[:window_size]
    recent_round_refs = round_refs[-window_size:] if window_size else []
    baseline_set = set(baseline_round_refs)
    recent_set = set(recent_round_refs)

    grouped: dict[str, dict[str, Any]] = {}
    for row in issue_rows:
        issue = str(row.get("issue") or "").strip().lower()
        if not issue:
            continue
        target = grouped.setdefault(
            issue,
            {
                "issue": issue,
                "phase": row.get("phase"),
                "reason": row.get("reason"),
                "confidence": row.get("confidence"),
                "sources": set(),
                "refs": [],
            },
        )
        source = str(row.get("source") or "").strip()
        if source:
            target["sources"].add(source)
        for ref in row.get("sourceRefs") or row.get("refs") or []:
            ref_text = str(ref)
            if ref_text and ref_text not in target["refs"]:
                target["refs"].append(ref_text)

    trends: list[dict[str, Any]] = []
    for issue, row in grouped.items():
        refs = _source_refs(row["refs"])
        baseline_refs = [ref for ref in refs if _ref_round_id(ref) in baseline_set]
        recent_refs = [ref for ref in refs if _ref_round_id(ref) in recent_set]
        if not baseline_refs and not recent_refs:
            continue
        baseline_count = len(baseline_refs)
        recent_count = len(recent_refs)
        delta_count = recent_count - baseline_count
        weight = _issue_weight(issue)
        estimated_impact = round(delta_count * weight, 1)
        sources = sorted(row["sources"])
        trends.append(
            {
                "issue": issue,
                "phase": row.get("phase"),
                "reason": row.get("reason"),
                "source": sources[0] if len(sources) == 1 else "mixed",
                "sources": sources,
                "confidence": _confidence(len(refs)),
                "baselineCount": baseline_count,
                "recentCount": recent_count,
                "deltaCount": delta_count,
                "baselineRatePerRound": round(baseline_count / window_size, 2) if window_size else 0.0,
                "recentRatePerRound": round(recent_count / window_size, 2) if window_size else 0.0,
                "deltaRatePerRound": round(delta_count / window_size, 2) if window_size else 0.0,
                "strokeWeight": weight,
                "estimatedStrokesImpact": estimated_impact,
                "estimatedStrokesLost": round(max(0.0, estimated_impact), 1),
                "direction": _diagnosis_direction(baseline_count, recent_count),
                "baselineRefs": baseline_refs,
                "recentRefs": recent_refs,
                "sourceRefs": refs,
            }
        )

    trends.sort(
        key=lambda row: (
            -float(row["estimatedStrokesLost"]),
            -abs(float(row["deltaRatePerRound"])),
            -int(row["recentCount"]),
            str(row["issue"]),
        )
    )
    return {
        "windowSize": window_size,
        "baselineRoundRefs": baseline_round_refs,
        "recentRoundRefs": recent_round_refs,
        "issueTrends": trends,
        "topIssue": trends[0] if trends else None,
    }


def _audit_payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("audit")
    return payload if isinstance(payload, dict) else {}


def _audit_classification(record: dict[str, Any]) -> str:
    value = record.get("classification") or _audit_payload(record).get("classification") or "unknown"
    text = str(value).strip().lower()
    return text if text else "unknown"


def _audit_phase(record: dict[str, Any]) -> str:
    value = _audit_payload(record).get("phase") or record.get("phase") or "unknown"
    text = str(value).strip().lower()
    return text if text else "unknown"


def _audit_source_ref(record: dict[str, Any]) -> str | None:
    value = record.get("sourceRef") or _audit_payload(record).get("decisionSourceRef")
    text = str(value).strip() if value is not None else ""
    return text or None


def _audit_ref_values(record: dict[str, Any], key: str) -> list[str]:
    value = record.get(key)
    if not isinstance(value, list):
        value = _audit_payload(record).get(key)
    return _source_refs(value if isinstance(value, list) else [])


def _audit_all_refs(record: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    source_ref = _audit_source_ref(record)
    if source_ref:
        refs.append(source_ref)
    refs.extend(_audit_ref_values(record, "actualShotRefs"))
    refs.extend(_audit_ref_values(record, "evidenceRefs"))
    decision_id = record.get("decisionId") or _audit_payload(record).get("decisionId")
    if decision_id:
        refs.append(str(decision_id))
    return _source_refs(refs)


def _loaded_audit_records(data: HistoryData, decision_audits: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    round_ref_set = set(_round_refs_by_date(data))
    if not round_ref_set:
        return []
    rows = []
    for record in decision_audits or []:
        refs = _audit_all_refs(record)
        if any(_ref_round_id(ref) in round_ref_set for ref in refs):
            rows.append(record)
    return rows


def _audit_source_refs(records: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for record in records:
        source_ref = _audit_source_ref(record)
        if source_ref:
            refs.append(source_ref)
    return _source_refs(refs)


def _audit_decision_ids(records: list[dict[str, Any]]) -> list[str]:
    return _source_refs([record.get("decisionId") or _audit_payload(record).get("decisionId") for record in records])


def _audit_suggestions(records: list[dict[str, Any]]) -> list[str]:
    return _source_refs([_audit_payload(record).get("modelUpdateSuggestion") for record in records])


def _decision_audit_diagnosis(data: HistoryData, decision_audits: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    records = _loaded_audit_records(data, decision_audits)
    total = len(records)
    round_refs = _round_refs_by_date(data)
    window_size = min(5, max(2, len(round_refs) // 2)) if len(round_refs) >= 2 else len(round_refs)
    baseline_round_refs = round_refs[:window_size]
    recent_round_refs = round_refs[-window_size:] if window_size else []
    baseline_set = set(baseline_round_refs)
    recent_set = set(recent_round_refs)
    audited_round_refs = [ref for ref in round_refs if any(_ref_round_id(item) == ref for record in records for item in _audit_all_refs(record))]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[_audit_classification(record)].append(record)

    classification_counts = []
    recent_drivers = []
    for classification, rows in grouped.items():
        source_refs = _audit_source_refs(rows)
        actual_refs = _source_refs(ref for row in rows for ref in _audit_ref_values(row, "actualShotRefs"))
        evidence_refs = _source_refs(ref for row in rows for ref in _audit_ref_values(row, "evidenceRefs"))
        count = len(rows)
        classification_counts.append(
            _with_aggregate_contract(
                {
                    "classification": classification,
                    "count": count,
                    "pct": round(count / total * 100, 1) if total else 0.0,
                    "decisionIds": _audit_decision_ids(rows),
                    "actualShotRefs": actual_refs,
                    "evidenceRefs": evidence_refs,
                },
                source_refs,
                ready=len(source_refs),
                total=total,
                confidence_count=count,
            )
        )

        baseline_refs = [ref for ref in source_refs if _ref_round_id(ref) in baseline_set]
        recent_refs = [ref for ref in source_refs if _ref_round_id(ref) in recent_set]
        baseline_count = len(baseline_refs)
        recent_count = len(recent_refs)
        delta_count = recent_count - baseline_count
        phases = sorted({_audit_phase(row) for row in rows})
        weight = DECISION_AUDIT_WEIGHTS.get(classification, DECISION_AUDIT_WEIGHTS["unknown"])
        estimated_impact = round(delta_count * weight, 1)
        recent_drivers.append(
            _with_aggregate_contract(
                {
                    "classification": classification,
                    "phase": phases[0] if len(phases) == 1 else "mixed",
                    "phases": phases,
                    "count": count,
                    "baselineCount": baseline_count,
                    "recentCount": recent_count,
                    "deltaCount": delta_count,
                    "baselineRatePerRound": round(baseline_count / window_size, 2) if window_size else 0.0,
                    "recentRatePerRound": round(recent_count / window_size, 2) if window_size else 0.0,
                    "deltaRatePerRound": round(delta_count / window_size, 2) if window_size else 0.0,
                    "strokeWeight": weight,
                    "estimatedStrokesImpact": estimated_impact,
                    "estimatedStrokesLost": round(max(0.0, estimated_impact), 1),
                    "direction": _diagnosis_direction(baseline_count, recent_count),
                    "baselineRefs": baseline_refs,
                    "recentRefs": recent_refs,
                    "decisionIds": _audit_decision_ids(rows),
                    "actualShotRefs": actual_refs,
                    "evidenceRefs": evidence_refs,
                    "modelUpdateSuggestions": _audit_suggestions(rows),
                },
                source_refs,
                ready=len(source_refs),
                total=total,
                confidence_count=count,
            )
        )

    classification_counts.sort(key=lambda row: (-int(row["count"]), str(row["classification"])))
    recent_drivers.sort(
        key=lambda row: (
            -float(row["estimatedStrokesLost"]),
            -abs(float(row["deltaRatePerRound"])),
            -int(row["recentCount"]),
            str(row["classification"]),
        )
    )
    return {
        "totalAudits": total,
        "auditedRoundRefs": _source_refs(audited_round_refs),
        "baselineRoundRefs": baseline_round_refs,
        "recentRoundRefs": recent_round_refs,
        "classificationCounts": classification_counts,
        "recentCostDrivers": recent_drivers,
    }


def _fairway_direction(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"hit", "center", "centre", "fairway", "yes", "true"}:
        return "hit"
    if text in {"left", "miss_left", "missed_left", "left_rough"}:
        return "left"
    if text in {"right", "miss_right", "missed_right", "right_rough"}:
        return "right"
    if text in {"miss", "missed", "rough"}:
        return "other"
    return None


def _direction_pct(count: int, recorded: int) -> float | None:
    return round(count / recorded * 100, 1) if recorded else None


def _dominant_tee_miss(left: int, right: int, other: int, recorded: int) -> str:
    if not recorded:
        return "unknown"
    if left + right + other == 0:
        return "none"
    counts = {"left": left, "right": right, "other": other}
    max_count = max(counts.values())
    leaders = [key for key, value in counts.items() if value == max_count and value > 0]
    return leaders[0] if len(leaders) == 1 else "mixed"


def _tee_direction_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    refs: dict[str, list[str]] = defaultdict(list)
    total_holes = 0
    for row in rows:
        for hole in row.get("holes") or []:
            total_holes += 1
            number = int(hole.get("number") or 0)
            ref = _hole_ref(row, number) if number else ""
            direction = _fairway_direction(hole.get("fairway"))
            if direction is None:
                continue
            refs["recorded"].append(ref)
            refs[direction].append(ref)

    recorded = len(refs["recorded"])
    hit = len(refs["hit"])
    left = len(refs["left"])
    right = len(refs["right"])
    other = len(refs["other"])
    miss = left + right + other
    return _with_aggregate_contract(
        {
            "recorded": recorded,
            "total": total_holes,
            "hit": hit,
            "left": left,
            "right": right,
            "other": other,
            "miss": miss,
            "hitPct": _direction_pct(hit, recorded),
            "leftPct": _direction_pct(left, recorded),
            "rightPct": _direction_pct(right, recorded),
            "otherPct": _direction_pct(other, recorded),
            "missPct": _direction_pct(miss, recorded),
            "dominantMiss": _dominant_tee_miss(left, right, other, recorded),
            "holeRefs": refs["recorded"],
            "hitRefs": refs["hit"],
            "leftRefs": refs["left"],
            "rightRefs": refs["right"],
            "otherRefs": refs["other"],
        },
        refs["recorded"],
        ready=recorded,
        total=total_holes,
        confidence_count=recorded,
    )


def _par_type_scoring(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    total_scored_holes = 0
    for row in rows:
        hole_pars = str(row.get("holePars") or "")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            par = _hole_to_par(hole, _par_from_string(hole_pars, number))
            score = hole.get("strokes")
            if not number or par is None or score is None:
                continue
            try:
                par_int = int(par)
                score_int = int(score)
            except (TypeError, ValueError):
                continue
            ref = _hole_ref(row, number)
            delta = score_int - par_int
            total_scored_holes += 1
            target = grouped.setdefault(
                par_int,
                {
                    "scores": [],
                    "deltas": [],
                    "refs": [],
                    "parOrBetterRefs": [],
                    "bogeyOrWorseRefs": [],
                    "birdieOrBetterRefs": [],
                },
            )
            target["scores"].append(score_int)
            target["deltas"].append(delta)
            target["refs"].append(ref)
            if delta <= 0:
                target["parOrBetterRefs"].append(ref)
            if delta >= 1:
                target["bogeyOrWorseRefs"].append(ref)
            if delta <= -1:
                target["birdieOrBetterRefs"].append(ref)

    out = []
    for par, values in sorted(grouped.items()):
        refs = values["refs"]
        deltas = values["deltas"]
        par_or_better = len(values["parOrBetterRefs"])
        bogey_or_worse = len(values["bogeyOrWorseRefs"])
        birdie_or_better = len(values["birdieOrBetterRefs"])
        out.append(
            _with_aggregate_contract(
                {
                    "key": f"par{par}",
                    "label": f"Par {par}",
                    "par": par,
                    "holeCount": len(refs),
                    "averageScore": average(values["scores"]),
                    "averageToPar": average(deltas),
                    "parOrBetter": par_or_better,
                    "bogeyOrWorse": bogey_or_worse,
                    "birdieOrBetter": birdie_or_better,
                    "parOrBetterPct": _direction_pct(par_or_better, len(refs)),
                    "bogeyOrWorsePct": _direction_pct(bogey_or_worse, len(refs)),
                    "birdieOrBetterPct": _direction_pct(birdie_or_better, len(refs)),
                    "bestToPar": min(deltas) if deltas else None,
                    "worstToPar": max(deltas) if deltas else None,
                    "holeRefs": refs,
                    "parOrBetterRefs": values["parOrBetterRefs"],
                    "bogeyOrWorseRefs": values["bogeyOrWorseRefs"],
                    "birdieOrBetterRefs": values["birdieOrBetterRefs"],
                },
                refs,
                ready=len(refs),
                total=total_scored_holes,
                confidence_count=len(refs),
            )
        )
    return out


def _approach_miss_direction(hole: dict[str, Any]) -> str | None:
    value = (
        hole.get("approachMiss")
        if hole.get("approachMiss") is not None
        else hole.get("greenMiss")
        if hole.get("greenMiss") is not None
        else hole.get("girMiss")
        if hole.get("girMiss") is not None
        else hole.get("missDirection")
    )
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    if text in {"short", "miss_short", "short_left", "short_right", "front"}:
        return "short"
    if text in {"long", "miss_long", "back", "over"}:
        return "long"
    if text in {"left", "miss_left", "left_rough", "pin_high_left"}:
        return "left"
    if text in {"right", "miss_right", "right_rough", "pin_high_right"}:
        return "right"
    if text in {"miss", "missed", "other"}:
        return "other"
    return None


def _dominant_approach_miss(counts: dict[str, int], recorded: int) -> str:
    if not recorded:
        return "unknown"
    miss_counts = {key: counts.get(key, 0) for key in ("short", "long", "left", "right", "other")}
    if sum(miss_counts.values()) == 0:
        return "none"
    max_count = max(miss_counts.values())
    leaders = [key for key, value in miss_counts.items() if value == max_count and value > 0]
    return leaders[0] if len(leaders) == 1 else "mixed"


def _approach_miss_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    refs: dict[str, list[str]] = defaultdict(list)
    counts = Counter({"recorded": 0, "gir": 0, "missed": 0, "short": 0, "long": 0, "left": 0, "right": 0, "other": 0})
    total_holes = 0
    for row in rows:
        for hole in row.get("holes") or []:
            total_holes += 1
            number = int(hole.get("number") or 0)
            ref = _hole_ref(row, number) if number else ""
            if hole.get("gir") is None:
                continue
            counts["recorded"] += 1
            refs["recorded"].append(ref)
            if bool(hole.get("gir")):
                counts["gir"] += 1
                refs["gir"].append(ref)
                continue
            counts["missed"] += 1
            refs["missed"].append(ref)
            direction = _approach_miss_direction(hole) or "other"
            counts[direction] += 1
            refs[direction].append(ref)

    recorded = counts["recorded"]
    return _with_aggregate_contract(
        {
            "recorded": recorded,
            "total": total_holes,
            "gir": counts["gir"],
            "missed": counts["missed"],
            "short": counts["short"],
            "long": counts["long"],
            "left": counts["left"],
            "right": counts["right"],
            "other": counts["other"],
            "girPct": _direction_pct(counts["gir"], recorded),
            "missPct": _direction_pct(counts["missed"], recorded),
            "shortPct": _direction_pct(counts["short"], recorded),
            "longPct": _direction_pct(counts["long"], recorded),
            "leftPct": _direction_pct(counts["left"], recorded),
            "rightPct": _direction_pct(counts["right"], recorded),
            "otherPct": _direction_pct(counts["other"], recorded),
            "dominantMiss": _dominant_approach_miss(counts, recorded),
            "holeRefs": refs["recorded"],
            "girRefs": refs["gir"],
            "missedRefs": refs["missed"],
            "shortRefs": refs["short"],
            "longRefs": refs["long"],
            "leftRefs": refs["left"],
            "rightRefs": refs["right"],
            "otherRefs": refs["other"],
        },
        refs["recorded"],
        ready=recorded,
        total=total_holes,
        confidence_count=recorded,
    )


def _scoring(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    bands: dict[str, list[str]] = {"70s": [], "80s": [], "90s": [], "100+": []}
    outcomes = Counter({"eagleOrBetter": 0, "birdie": 0, "par": 0, "bogey": 0, "doubleOrWorse": 0})
    outcome_refs: dict[str, list[str]] = defaultdict(list)
    putt_corrections = _annotations_by_kind(annotations, "putt_correction")
    score_corrections = _annotations_by_kind(annotations, "score_correction")
    putts: list[int] = []
    putt_refs: list[str] = []
    three_putt_refs: list[str] = []
    corrected_putt_refs: list[str] = []
    corrected_score_refs: list[str] = []
    fairways = Counter({"recorded": 0, "hit": 0, "left": 0, "right": 0})
    tee_refs: list[str] = []
    gir = Counter({"recorded": 0, "hit": 0})
    approach_refs: list[str] = []
    total_holes = sum(len(row.get("holes") or []) for row in data.rounds)
    effective_shots = _effective_shots(data, annotations)
    for row in data.rounds:
        if row.get("holesCompleted") == 18 and row.get("strokes") is not None:
            bands[_score_band(int(row["strokes"]))].append(_round_id(row))
        hole_pars = str(row.get("holePars") or "")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            par = _hole_to_par(hole, _par_from_string(hole_pars, number))
            score = hole.get("strokes")
            ref = _hole_ref(row, number) if number else ""
            putt_count = _corrected_putt_value(ref, hole.get("putts"), putt_corrections)
            if putt_count is not None:
                putts.append(putt_count)
                putt_refs.append(ref)
                if putt_count >= 3:
                    three_putt_refs.append(ref)
                if ref in putt_corrections:
                    corrected_putt_refs.append(ref)
            if ref in score_corrections:
                corrected_score_refs.append(ref)
            fairway = _fairway_direction(hole.get("fairway"))
            if fairway:
                fairways["recorded"] += 1
                tee_refs.append(ref)
                if fairway == "hit":
                    fairways["hit"] += 1
                elif fairway == "left":
                    fairways["left"] += 1
                elif fairway == "right":
                    fairways["right"] += 1
            if hole.get("gir") is not None:
                gir["recorded"] += 1
                approach_refs.append(ref)
                if bool(hole.get("gir")):
                    gir["hit"] += 1
            if par is None or score is None:
                continue
            delta = int(score) - int(par)
            if delta <= -2:
                outcomes["eagleOrBetter"] += 1
                outcome_refs["eagleOrBetter"].append(ref)
            elif delta == -1:
                outcomes["birdie"] += 1
                outcome_refs["birdie"].append(ref)
            elif delta == 0:
                outcomes["par"] += 1
                outcome_refs["par"].append(ref)
            elif delta == 1:
                outcomes["bogey"] += 1
                outcome_refs["bogey"].append(ref)
            else:
                outcomes["doubleOrWorse"] += 1
                outcome_refs["doubleOrWorse"].append(ref)
    total_rounds18 = sum(len(round_ids) for round_ids in bands.values())
    total_outcomes = sum(len(refs) for refs in outcome_refs.values())
    short_game_refs = [
        str(shot.get("_ref"))
        for shot in effective_shots
        if str(shot.get("surface") or "").lower() in {"rough", "bunker"} and shot.get("_ref") is not None
    ]
    outcome_rows = [
        _with_aggregate_contract(
            {
                "key": key,
                "label": label,
                "className": class_name,
                "count": len(outcome_refs.get(key, [])),
                "pct": round(len(outcome_refs.get(key, [])) / total_outcomes * 100, 1) if total_outcomes else 0.0,
                "holeRefs": outcome_refs.get(key, []),
            },
            outcome_refs.get(key, []),
            total=total_outcomes,
        )
        for key, label, class_name in [
            ("eagleOrBetter", "Eagle+", "eagle"),
            ("birdie", "Birdie", "birdie"),
            ("par", "Par", "par"),
            ("bogey", "Bogey", "bogey"),
            ("doubleOrWorse", "Double+", "double"),
        ]
    ]
    return {
        "scoreBands": [
            _with_aggregate_contract(
                {"label": label, "count": len(round_ids), "roundIds": round_ids, "roundRefs": round_ids},
                round_ids,
                total=total_rounds18,
            )
            for label, round_ids in bands.items()
        ],
        "outcomes": {
            **dict(outcomes),
            "parOrBetter": outcomes["eagleOrBetter"] + outcomes["birdie"] + outcomes["par"],
            "bogeyOrWorse": outcomes["bogey"] + outcomes["doubleOrWorse"],
        },
        "outcomeRows": outcome_rows,
        "byPar": _par_type_scoring(data.rounds),
        "teeDirection": _tee_direction_stats(data.rounds),
        "approachMiss": _approach_miss_stats(data.rounds),
        "putting": {
            "totalPutts": sum(putts),
            "holesWithPutts": len(putts),
            "averagePutts": average(putts),
            "threePutts": len(three_putt_refs),
            "threePuttRefs": three_putt_refs,
            "correctedRefs": corrected_putt_refs,
        },
        "phaseStats": [
            _with_aggregate_contract(
                {
                    "phase": "Tee",
                    "fairwaysRecorded": fairways["recorded"],
                    "fairwaysHit": fairways["hit"],
                    "fairwayMissLeft": fairways["left"],
                    "fairwayMissRight": fairways["right"],
                    "holeRefs": tee_refs,
                },
                tee_refs,
                ready=fairways["recorded"],
                total=total_holes,
            ),
            _with_aggregate_contract(
                {
                    "phase": "Approach",
                    "girRecorded": gir["recorded"],
                    "gir": gir["hit"],
                    "missedGir": gir["recorded"] - gir["hit"],
                    "girPct": round(gir["hit"] / gir["recorded"] * 100, 1) if gir["recorded"] else None,
                    "holeRefs": approach_refs,
                },
                approach_refs,
                ready=gir["recorded"],
                total=total_holes,
            ),
            _with_aggregate_contract(
                {
                    "phase": "Short Game",
                    "roughOrBunkerShots": len(short_game_refs),
                    "shotRefs": short_game_refs,
                },
                short_game_refs,
                total=len(effective_shots),
            ),
            _with_aggregate_contract(
                {
                    "phase": "Putting",
                    "totalPutts": sum(putts),
                    "holesWithPutts": len(putts),
                    "averagePutts": average(putts),
                    "threePutts": len(three_putt_refs),
                    "holeRefs": putt_refs,
                    "threePuttRefs": three_putt_refs,
                    "correctedRefs": corrected_putt_refs,
                },
                putt_refs,
                ready=len(putts),
                total=total_holes,
            ),
        ],
        "scoreCorrections": {
            "count": len(corrected_score_refs),
            "correctedRefs": corrected_score_refs,
        },
    }


def _courses(data: HistoryData) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.rounds:
        grouped[str(row.get("courseKey") or "unknown")].append(row)
    out = []
    total_rounds = len(data.rounds)
    for course_key, rows in grouped.items():
        rows_sorted = sorted(rows, key=lambda row: str(row.get("date") or ""), reverse=True)
        round_ids = [_round_id(row) for row in rows_sorted]
        scores18 = [
            int(row["strokes"])
            for row in rows
            if row.get("holesCompleted") == 18 and row.get("strokes") is not None
        ]
        out.append(
            _with_aggregate_contract(
                {
                    "courseKey": course_key,
                    "courseName": str(rows_sorted[0].get("course") or rows_sorted[0].get("courseName") or "Unknown course"),
                    "roundCount": len(rows),
                    "average18": average(scores18),
                    "bestScore": min(scores18) if scores18 else None,
                    "worstScore": max(scores18) if scores18 else None,
                    "recentRoundId": _round_id(rows_sorted[0]),
                    "roundIds": round_ids,
                    "roundRefs": round_ids,
                    "recentForm": _course_recent_form(rows),
                    "teeDirection": _tee_direction_stats(rows),
                    "parScoring": _par_type_scoring(rows),
                    "approachMiss": _approach_miss_stats(rows),
                    "geometryCoverage": _course_geometry_coverage(rows),
                },
                round_ids,
                total=total_rounds,
            )
        )
    return sorted(out, key=lambda row: (-row["roundCount"], row["courseName"]))


def _course_recent_form(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rounds18 = [
        row
        for row in sorted(rows, key=lambda item: str(item.get("date") or ""))
        if row.get("holesCompleted") == 18 and row.get("strokes") is not None
    ]
    scores = [float(row["strokes"]) for row in rounds18]
    refs = [_round_id(row) for row in rounds18]
    if not scores:
        return {
            "roundCount": 0,
            "windowSize": 0,
            "baselineAverage18": None,
            "recentAverage18": None,
            "deltaAverage18": None,
            "direction": "insufficient_data",
            "confidence": "insufficient",
            "roundRefs": [],
            "baselineRoundRefs": [],
            "recentRoundRefs": [],
        }

    window_size = min(5, max(1, len(scores) // 2))
    baseline_scores = scores[:window_size]
    recent_scores = scores[-window_size:]
    baseline_average = average(baseline_scores)
    recent_average = average(recent_scores)
    delta_average = round(float(recent_average) - float(baseline_average), 1) if baseline_average is not None and recent_average is not None else None
    slope = _linear_slope(scores)
    return {
        "roundCount": len(scores),
        "windowSize": window_size,
        "baselineAverage18": baseline_average,
        "recentAverage18": recent_average,
        "deltaAverage18": delta_average,
        "direction": _improvement_direction(delta_average, slope),
        "confidence": _improvement_confidence(len(scores)),
        "roundRefs": refs,
        "baselineRoundRefs": refs[:window_size],
        "recentRoundRefs": refs[-window_size:],
    }


def _course_distribution(data: HistoryData) -> list[dict[str, Any]]:
    total = len(data.rounds)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.rounds:
        grouped[str(row.get("courseKey") or "unknown")].append(row)
    rows = []
    for course_key, course_rows in grouped.items():
        rows_sorted = sorted(course_rows, key=lambda row: str(row.get("date") or ""), reverse=True)
        round_refs = [_round_id(row) for row in rows_sorted]
        rows.append(
            _with_aggregate_contract(
                {
                    "courseKey": course_key,
                    "courseName": str(rows_sorted[0].get("course") or rows_sorted[0].get("courseName") or "Unknown course"),
                    "roundCount": len(course_rows),
                    "pct": round(len(course_rows) / total * 100, 1) if total else 0.0,
                    "roundRefs": round_refs,
                    "location": {
                        "latitude": rows_sorted[0].get("lat"),
                        "longitude": rows_sorted[0].get("lon"),
                    }
                    if rows_sorted[0].get("lat") is not None and rows_sorted[0].get("lon") is not None
                    else None,
                },
                round_refs,
                total=total,
            )
        )
    return sorted(rows, key=lambda row: (-row["roundCount"], row["courseName"]))


def _round_record(row: dict[str, Any]) -> dict[str, Any]:
    score = row.get("strokes")
    par = row.get("par")
    round_ref = _round_id(row)
    return _with_aggregate_contract(
        {
            "roundRef": round_ref,
            "courseKey": row.get("courseKey"),
            "courseName": str(row.get("course") or row.get("courseName") or "Unknown course"),
            "date": row.get("date"),
            "score": int(score) if score is not None else None,
            "par": int(par) if par is not None else None,
            "toPar": int(score) - int(par) if score is not None and par is not None else None,
        },
        [round_ref],
        total=1,
    )


def _records(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rounds18 = [
        row
        for row in data.rounds
        if row.get("holesCompleted") == 18 and row.get("strokes") is not None
    ]
    rounds9 = [
        row
        for row in data.rounds
        if row.get("holesCompleted") == 9 and row.get("strokes") is not None
    ]
    courses = _course_distribution(data)
    shots = [
        shot
        for shot in _effective_shots(data, annotations)
        if _shot_distance(shot) is not None and shot.get("_ref") is not None
    ]
    hole_outcomes = []
    for row in data.rounds:
        hole_pars = str(row.get("holePars") or "")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            par = _hole_to_par(hole, _par_from_string(hole_pars, number))
            score = hole.get("strokes")
            if not number or par is None or score is None:
                continue
            hole_outcomes.append(
                {
                    "holeRef": _hole_ref(row, number),
                    "roundRef": _round_id(row),
                    "courseKey": row.get("courseKey"),
                    "courseName": str(row.get("course") or row.get("courseName") or "Unknown course"),
                    "hole": number,
                    "score": int(score),
                    "par": int(par),
                    "toPar": int(score) - int(par),
                }
            )
    return {
        "best18": _round_record(min(rounds18, key=lambda row: (int(row["strokes"]), str(row.get("date") or "")))) if rounds18 else None,
        "worst18": _round_record(max(rounds18, key=lambda row: (int(row["strokes"]), str(row.get("date") or "")))) if rounds18 else None,
        "bestNine": _round_record(min(rounds9, key=lambda row: (int(row["strokes"]), str(row.get("date") or "")))) if rounds9 else None,
        "mostPlayedCourse": courses[0] if courses else None,
        "longestShots": [
            _with_aggregate_contract(
                {
                    "shotRef": str(shot.get("_ref")),
                    "roundRef": _shot_round_id(shot),
                    "holeRef": f"{_shot_round_id(shot)}:{shot.get('hole')}",
                    "club": _shot_club(shot),
                    "distance": float(_shot_distance(shot)),
                    "surface": _shot_surface(shot),
                },
                [shot.get("_ref")],
                total=1,
            )
            for shot in sorted(shots, key=lambda item: (-float(item.get("distance") or 0), str(item.get("_ref"))))[:5]
        ],
        "bestHoleOutcomes": [
            _with_aggregate_contract(dict(item), [item.get("holeRef")], total=1)
            for item in sorted(hole_outcomes, key=lambda item: (int(item["toPar"]), int(item["score"]), str(item["holeRef"])))[:5]
        ],
        "worstHoleOutcomes": [
            _with_aggregate_contract(dict(item), [item.get("holeRef")], total=1)
            for item in sorted(hole_outcomes, key=lambda item: (-int(item["toPar"]), -int(item["score"]), str(item["holeRef"])))[:5]
        ],
    }


def _hole_score_distribution(bucket_refs: dict[str, list[str]]) -> list[dict[str, Any]]:
    ordered = [
        ("eagleOrBetter", "Eagle+", "eagle"),
        ("birdie", "Birdie", "birdie"),
        ("par", "Par", "par"),
        ("bogey", "Bogey", "bogey"),
        ("doubleOrWorse", "Double+", "double"),
    ]
    total = sum(len(refs) for refs in bucket_refs.values())
    return [
        _with_aggregate_contract(
            {
                "key": key,
                "label": label,
                "className": class_name,
                "count": len(bucket_refs.get(key, [])),
                "pct": round(len(bucket_refs.get(key, [])) / total * 100, 1) if total else 0.0,
                "holeRefs": bucket_refs.get(key, []),
            },
            bucket_refs.get(key, []),
            total=total,
        )
        for key, label, class_name in ordered
    ]


def _issue_tag_payload(record: dict[str, Any]) -> str:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    return str(payload.get("tag") or "").strip().lower()


def _active_manual_issue_tags_by_target(annotations: list[dict[str, Any]] | None) -> dict[str, list[str]]:
    active: dict[tuple[str, str], bool] = {}
    order: list[tuple[str, str]] = []
    ordered: set[tuple[str, str]] = set()
    for record in annotations or []:
        kind = record.get("kind")
        if kind not in {"issue_tag", "issue_tag_removed"}:
            continue
        target_id = str(record.get("targetId") or "")
        tag = _issue_tag_payload(record)
        if not target_id or not tag:
            continue
        key = (target_id, tag)
        if kind == "issue_tag" and key not in ordered:
            order.append(key)
            ordered.add(key)
        active[key] = kind == "issue_tag"

    rows: dict[str, list[str]] = defaultdict(list)
    for target_id, tag in order:
        if active.get((target_id, tag)):
            rows[target_id].append(tag)
    return rows


def _hole_repeated_issue_records(issue_refs: dict[tuple[str, str], list[str]]) -> list[dict[str, Any]]:
    rows = [
        issue_record(issue, refs, source=source)
        for (issue, source), refs in issue_refs.items()
        if refs
    ]
    return sorted(
        rows,
        key=lambda row: (
            -int(row["count"]),
            0 if row["source"] == "deterministic" else 1,
            str(row["issue"]),
        ),
    )


def _club_dispersion_range(p10: float | None, p90: float | None) -> float | None:
    if p10 is None or p90 is None:
        return None
    return round(float(p90) - float(p10), 1)


def _club_consistency(dispersion_range: float | None, sample_count: int) -> str:
    if dispersion_range is None or sample_count < 4:
        return "unknown"
    if dispersion_range <= 10:
        return "tight"
    if dispersion_range <= 25:
        return "moderate"
    return "volatile"


def _club_distance_trend(distance_rows: list[tuple[float, str]]) -> dict[str, Any]:
    sample_count = len(distance_rows)
    shot_refs = [ref for _distance, ref in distance_rows]
    if sample_count < 4:
        sample_median = round(float(median([distance for distance, _ref in distance_rows])), 1) if distance_rows else None
        return _with_aggregate_contract(
            {
                "sampleCount": sample_count,
                "windowSize": sample_count,
                "baselineMedian": sample_median,
                "recentMedian": sample_median,
                "deltaMedian": None,
                "direction": "insufficient_data",
                "baselineShotRefs": shot_refs,
                "recentShotRefs": shot_refs,
            },
            shot_refs,
            ready=sample_count,
            total=sample_count,
            confidence_count=sample_count,
        )

    window_size = min(5, max(2, sample_count // 2))
    baseline_rows = distance_rows[:window_size]
    recent_rows = distance_rows[-window_size:]
    baseline_median = round(float(median([distance for distance, _ref in baseline_rows])), 1)
    recent_median = round(float(median([distance for distance, _ref in recent_rows])), 1)
    delta_median = round(recent_median - baseline_median, 1)
    if delta_median <= -5:
        direction = "shorter"
    elif delta_median >= 5:
        direction = "longer"
    else:
        direction = "stable"
    return _with_aggregate_contract(
        {
            "sampleCount": sample_count,
            "windowSize": window_size,
            "baselineMedian": baseline_median,
            "recentMedian": recent_median,
            "deltaMedian": delta_median,
            "direction": direction,
            "baselineShotRefs": [ref for _distance, ref in baseline_rows],
            "recentShotRefs": [ref for _distance, ref in recent_rows],
        },
        shot_refs,
        ready=sample_count,
        total=sample_count,
        confidence_count=sample_count,
    )


def _distance_quality(shot: dict[str, Any]) -> tuple[float | None, str | None]:
    raw_distance = _shot_distance(shot)
    if raw_distance is None:
        return None, "missing_distance"
    try:
        distance = float(raw_distance)
    except (TypeError, ValueError):
        return None, "non_numeric_distance"
    if not math.isfinite(distance):
        return None, "non_finite_distance"
    if distance <= 0:
        return None, "non_positive_distance"
    if distance > 400:
        return None, "implausible_distance"
    return distance, None


def _club_outlier_ref_set(valid_samples: list[dict[str, Any]]) -> set[str]:
    if len(valid_samples) < 5:
        return set()
    distances = [float(sample["distance"]) for sample in valid_samples]
    center = float(median(distances))
    deviations = [abs(distance - center) for distance in distances]
    mad = float(median(deviations))
    threshold = max(50.0, mad * 3)
    return {
        str(sample["shotRef"])
        for sample in valid_samples
        if abs(float(sample["distance"]) - center) > threshold
    }


def _club_sample_quality_rows(shots: list[dict[str, Any]]) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    invalid_samples: list[dict[str, Any]] = []
    initially_valid: list[dict[str, Any]] = []
    for shot in shots:
        shot_ref = str(shot.get("_ref")) if shot.get("_ref") is not None else ""
        distance, invalid_reason = _distance_quality(shot)
        if not shot_ref:
            continue
        if invalid_reason is not None or distance is None:
            invalid_samples.append({"shotRef": shot_ref, "reason": invalid_reason or "invalid_distance"})
            samples.append({"shotRef": shot_ref, "distance": None, "valid": False, "reason": invalid_reason or "invalid_distance"})
            continue
        sample = {"shotRef": shot_ref, "distance": distance, "valid": True, "reason": None}
        samples.append(sample)
        initially_valid.append(sample)

    outlier_refs = _club_outlier_ref_set(initially_valid)
    outlier_samples = [
        {"shotRef": str(sample["shotRef"]), "distance": float(sample["distance"]), "reason": "distance_outlier"}
        for sample in initially_valid
        if str(sample["shotRef"]) in outlier_refs
    ]
    valid_samples = [
        sample
        for sample in initially_valid
        if str(sample["shotRef"]) not in outlier_refs
    ]
    valid_refs = [str(sample["shotRef"]) for sample in valid_samples]
    invalid_refs = [str(sample["shotRef"]) for sample in invalid_samples]
    outlier_ref_list = [str(sample["shotRef"]) for sample in outlier_samples]
    return {
        "rawSampleCount": len(samples),
        "validSampleCount": len(valid_samples),
        "invalidSampleCount": len(invalid_samples),
        "outlierCount": len(outlier_samples),
        "validSamples": valid_samples,
        "invalidSamples": invalid_samples,
        "outlierSamples": outlier_samples,
        "validShotRefs": valid_refs,
        "invalidShotRefs": invalid_refs,
        "outlierShotRefs": outlier_ref_list,
        "problemRefs": invalid_refs + outlier_ref_list,
    }


def _club_sample_quality_contract(quality: dict[str, Any]) -> dict[str, Any]:
    return _with_aggregate_contract(
        {
            "rawSampleCount": quality["rawSampleCount"],
            "validSampleCount": quality["validSampleCount"],
            "invalidSampleCount": quality["invalidSampleCount"],
            "outlierCount": quality["outlierCount"],
            "validShotRefs": quality["validShotRefs"],
            "invalidShotRefs": quality["invalidShotRefs"],
            "outlierShotRefs": quality["outlierShotRefs"],
            "invalidSamples": quality["invalidSamples"],
            "outlierSamples": quality["outlierSamples"],
        },
        quality["validShotRefs"],
        ready=int(quality["validSampleCount"]),
        total=int(quality["rawSampleCount"]),
        confidence_count=int(quality["validSampleCount"]),
    )


def _sortable_int(value: Any, default: int = 999999) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _round_chronology(data: HistoryData) -> dict[str, tuple[str, int]]:
    return {_round_id(row): (str(row.get("date") or ""), index) for index, row in enumerate(data.rounds)}


def _shot_sort_order(shot: dict[str, Any]) -> int:
    for key in ("order", "shotOrder", "shotNumber", "shotIndex", "sequence"):
        if shot.get(key) is not None:
            return _sortable_int(shot.get(key))
    ref = str(shot.get("_ref") or "")
    return _sortable_int(ref.rsplit(":", 1)[-1])


def _club_trend_shot_sort_key(shot: dict[str, Any], round_chronology: dict[str, tuple[str, int]]) -> tuple[Any, ...]:
    round_id = _shot_round_id(shot)
    date, round_index = round_chronology.get(round_id, ("", 999999))
    return (
        date,
        round_index,
        round_id,
        _sortable_int(shot.get("hole")),
        _shot_sort_order(shot),
        str(shot.get("_ref") or ""),
    )


def _holes(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for row in data.rounds:
        course_key = str(row.get("courseKey") or "unknown")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            if number:
                grouped[(course_key, number)].append((row, hole))
    hazard_hole_refs = {
        f"{_shot_round_id(shot)}:{shot.get('hole')}"
        for shot in _effective_shots(data, annotations)
        if str(_shot_surface(shot) or "").lower() in {"water", "bunker", "rough"}
    }
    manual_tags = _active_manual_issue_tags_by_target(annotations)
    out = []
    for (course_key, number), pairs in grouped.items():
        deltas: list[int] = []
        distribution_refs: dict[str, list[str]] = defaultdict(list)
        issue_refs: dict[tuple[str, str], list[str]] = defaultdict(list)
        refs: list[str] = []
        for row, hole in pairs:
            par = _hole_to_par(hole, _par_from_string(str(row.get("holePars") or ""), number))
            score = hole.get("strokes")
            ref = f"{_round_id(row)}:{number}"
            if par is not None and score is not None:
                delta = int(score) - int(par)
                bucket_key, _bucket_label, _class_name = _hole_score_bucket(delta)
                deltas.append(delta)
                distribution_refs[bucket_key].append(ref)
                if delta >= 2:
                    issue_refs[("double_or_worse", "deterministic")].append(ref)
            if ref in hazard_hole_refs:
                issue_refs[("hazard_result", "deterministic")].append(ref)
            for tag in manual_tags.get(ref, []):
                issue_refs[(tag, "manual")].append(ref)
            refs.append(ref)
        out.append(
            _with_aggregate_contract(
                {
                    "courseKey": course_key,
                    "hole": number,
                    "sampleCount": len(pairs),
                    "averageToPar": average(deltas),
                    "worstToPar": max(deltas) if deltas else None,
                    "scoreDistribution": _hole_score_distribution(distribution_refs),
                    "repeatedIssues": _hole_repeated_issue_records(issue_refs),
                    "refs": refs,
                    "holeRefs": refs,
                    "geometryCoverage": _hole_geometry_coverage(pairs, number),
                },
                refs,
            )
        )
    return sorted(out, key=lambda row: (row["courseKey"], row["hole"]))


def _clubs(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shot in _effective_shots(data, annotations):
        club = _shot_club(shot)
        grouped[club].append(shot)
    out = []
    round_chronology = _round_chronology(data)
    for club, shots in grouped.items():
        quality = _club_sample_quality_rows(shots)
        valid_ref_set = set(quality["validShotRefs"])
        valid_shots = [
            shot
            for shot in shots
            if shot.get("_ref") is not None and str(shot.get("_ref")) in valid_ref_set
        ]
        trend_shots = sorted(valid_shots, key=lambda shot: _club_trend_shot_sort_key(shot, round_chronology))
        distances = [float(_shot_distance(shot)) for shot in valid_shots if _shot_distance(shot) is not None]
        distance_rows = [
            (float(_shot_distance(shot)), str(shot.get("_ref")))
            for shot in trend_shots
            if _shot_distance(shot) is not None and shot.get("_ref") is not None
        ]
        p10 = percentile(distances, 0.1)
        p90 = percentile(distances, 0.9)
        dispersion_range = _club_dispersion_range(p10, p90)
        round_ids = sorted({_shot_round_id(shot) for shot in shots if _shot_round_id(shot) != "None"})
        shot_refs = sorted(str(shot.get("_ref")) for shot in shots if shot.get("_ref") is not None)
        corrected_refs = sorted(
            str(shot.get("_ref"))
            for shot in shots
            if shot.get("_clubCorrected") and shot.get("_ref") is not None
        )
        out.append(
            _with_aggregate_contract(
                {
                    "club": club,
                    "sampleCount": len(distances),
                    "rawSampleCount": quality["rawSampleCount"],
                    "validSampleCount": quality["validSampleCount"],
                    "invalidSampleCount": quality["invalidSampleCount"],
                    "outlierCount": quality["outlierCount"],
                    "median": round(float(median(distances)), 1) if distances else None,
                    "p10": p10,
                    "p90": p90,
                    "dispersionRange": dispersion_range,
                    "consistency": _club_consistency(dispersion_range, len(distances)),
                    "distanceTrend": _club_distance_trend(distance_rows),
                    "max": max(distances) if distances else None,
                    "roundIds": round_ids,
                    "shotRefs": shot_refs,
                    "validShotRefs": quality["validShotRefs"],
                    "invalidShotRefs": quality["invalidShotRefs"],
                    "outlierShotRefs": quality["outlierShotRefs"],
                    "sampleQuality": _club_sample_quality_contract(quality),
                    "correctedRefs": corrected_refs,
                    "correctionCount": len(corrected_refs),
                },
                quality["validShotRefs"],
                ready=len(distances),
                total=len(shots),
                confidence_count=len(distances),
            )
        )
    return sorted(out, key=lambda row: row["club"])


def _issues(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    refs: dict[str, list[str]] = defaultdict(list)

    def add_ref(issue: str, ref: str) -> None:
        if ref and ref not in refs[issue]:
            refs[issue].append(ref)

    for row in data.rounds:
        if not row.get("hasShots"):
            add_ref("missing_shots", _round_id(row))
        has_geometry_identity = _global_id(row) is not None or row.get("courseId") is not None
        hole_pars = str(row.get("holePars") or "")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            hole_ref = f"{_round_id(row)}:{number}" if number else ""
            par = _hole_to_par(hole, _par_from_string(hole_pars, number))
            score = hole.get("strokes")
            if number and par is not None and score is not None and int(score) - int(par) >= 2:
                add_ref("double_or_worse", hole_ref)
            if not number:
                continue
            try:
                putts = int(hole.get("putts"))
                if putts >= 3:
                    add_ref("three_putt", hole_ref)
            except (TypeError, ValueError):
                if score is not None:
                    add_ref("missing_putt_data", hole_ref)
            fairway = str(hole.get("fairway") or "").strip().lower()
            if fairway in {"left", "miss_left", "missed_left", "fairway_left"}:
                add_ref("fairway_missed_left", hole_ref)
            elif fairway in {"right", "miss_right", "missed_right", "fairway_right"}:
                add_ref("fairway_missed_right", hole_ref)
            if hole.get("gir") is not None and not bool(hole.get("gir")):
                approach_miss = _approach_miss_direction(hole)
                if approach_miss in {"short", "long", "left", "right"}:
                    add_ref(f"approach_{approach_miss}", hole_ref)
            if not has_geometry_identity:
                add_ref("missing_geometry", hole_ref)

    effective_shots = _effective_shots(data, annotations)
    for shot in effective_shots:
        if str(_shot_surface(shot) or "").lower() in {"water", "bunker", "rough"}:
            add_ref("hazard_result", f"{_shot_round_id(shot)}:{shot.get('hole')}")

    shots_by_club: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shot in effective_shots:
        if _shot_distance(shot) is None:
            continue
        club = _shot_club(shot)
        shots_by_club[club].append(shot)
    for shots in shots_by_club.values():
        shot_refs = sorted(str(shot.get("_ref")) for shot in shots if shot.get("_ref") is not None)
        if len(shots) < 2:
            for ref in shot_refs:
                add_ref("low_confidence_club", ref)
        elif len(shots) < 10:
            for ref in shot_refs:
                add_ref("weak_sample_size", ref)

    rows = [issue_record(issue, items, source="deterministic") for issue, items in sorted(refs.items())]
    manual_refs: dict[str, list[str]] = defaultdict(list)
    for target_id, tags in _active_manual_issue_tags_by_target(annotations).items():
        for tag in tags:
            manual_refs[tag].append(target_id)

    for record in annotations or []:
        kind = record.get("kind")
        target_id = str(record.get("targetId") or "")
        if kind in {"issue_tag", "issue_tag_removed"}:
            continue
        if kind == "club_correction":
            manual_refs["wrong_club"].append(target_id)
            continue
        if kind == "lie_correction":
            lie = str(_payload_value(record, "to", "surface", "lie", "correctedLie") or "").lower()
            if lie in {"water", "bunker", "rough"}:
                manual_refs[lie].append(target_id)
            continue
        if kind == "penalty_correction":
            reason = str(_payload_value(record, "reason", "issue", "tag") or "penalty").strip().lower()
            if reason:
                manual_refs[reason.replace(" ", "_")].append(target_id)
            continue
        if kind == "putt_correction":
            putts = _payload_value(record, "to", "putts", "correctedPutts")
            try:
                if int(putts) >= 3:
                    manual_refs["three_putt"].append(target_id)
            except (TypeError, ValueError):
                manual_refs["missing_putt_data"].append(target_id)
            continue
    rows.extend(issue_record(issue, items, source="manual") for issue, items in sorted(manual_refs.items()))
    return rows


def _weather_quality(data: HistoryData, weather_snapshots: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    loaded_hole_refs = {
        _hole_ref(row, int(hole.get("number") or 0))
        for row in data.rounds
        for hole in (row.get("holes") or [])
        if isinstance(hole, dict) and int(hole.get("number") or 0)
    }
    total_holes = len(loaded_hole_refs)
    ready_refs = sorted(
        {
            f"{row.get('roundId')}:{row.get('hole')}"
            for row in weather_snapshots or []
            if row.get("state") == "ready"
            and row.get("roundId") is not None
            and row.get("hole") is not None
            and f"{row.get('roundId')}:{row.get('hole')}" in loaded_hole_refs
        }
    )
    return _with_quality_contract(
        {
            "label": "weather",
            "state": "good" if total_holes and len(ready_refs) >= total_holes else "partial" if ready_refs else "missing",
            "ready": len(ready_refs),
            "total": total_holes,
            "refs": ready_refs,
        }
    )


def _geometry_quality(hole_rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(int(row.get("sampleCount") or 0) for row in hole_rows)
    ready = sum(int(row.get("sampleCount") or 0) for row in hole_rows if row.get("geometryCoverage") == "ready")
    partial = sum(int(row.get("sampleCount") or 0) for row in hole_rows if row.get("geometryCoverage") == "partial")
    refs = [
        str(ref)
        for row in hole_rows
        if row.get("geometryCoverage") != "ready"
        for ref in (row.get("holeRefs") or row.get("refs") or [])
    ]
    return _with_quality_contract(
        {
            "label": "geometry",
            "state": "good" if total and ready == total else "partial" if ready or partial else "missing",
            "ready": ready,
            "partial": partial,
            "total": total,
            "refs": refs,
        }
    )


def _report_quality(data: HistoryData, report_records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    round_refs = [_round_id(row) for row in data.rounds]
    reported_rounds = {
        str(record.get("subjectId"))
        for record in report_records or []
        if record.get("kind") == "round" and record.get("subjectId") is not None
    }
    trend_subjects = _expected_trend_report_subjects(data)
    reported_trends = {
        str(record.get("subjectId"))
        for record in report_records or []
        if record.get("kind") == "trend" and record.get("subjectId") is not None
    }
    missing_refs = [ref for ref in round_refs if ref not in reported_rounds]
    missing_trend_refs = [ref for ref in trend_subjects if ref not in reported_trends]
    ready_rounds = len(round_refs) - len(missing_refs)
    ready_trends = len(trend_subjects) - len(missing_trend_refs)
    ready = ready_rounds + ready_trends
    total = len(round_refs) + len(trend_subjects)
    return _with_quality_contract(
        {
            "label": "reports",
            "state": "good" if total and ready == total else "partial" if ready else "missing",
            "ready": ready,
            "total": total,
            "refs": [*missing_refs, *(f"trend:{ref}" for ref in missing_trend_refs)],
            "roundReports": {
                "ready": ready_rounds,
                "total": len(round_refs),
                "missingRefs": missing_refs,
            },
            "trendReports": {
                "ready": ready_trends,
                "total": len(trend_subjects),
                "missingRefs": [f"trend:{ref}" for ref in missing_trend_refs],
            },
        }
    )


def _expected_trend_report_subjects(data: HistoryData) -> list[str]:
    subjects: set[str] = set()
    if data.rounds:
        subjects.add("recent_10")
    for row in data.rounds:
        date = str(row.get("date") or "")
        if len(date) >= 4:
            subjects.add(f"year:{date[:4]}")
        if len(date) >= 7 and date[5:7].isdigit():
            quarter = (int(date[5:7]) - 1) // 3 + 1
            subjects.add(f"quarter:{date[:4]}-Q{quarter}")
    return sorted(subjects)


def _shot_row_quality(data: HistoryData) -> dict[str, Any]:
    expected_ids = _source_refs([row.get("id") for row in data.raw_rounds if row.get("hasShots")])
    actual_ids = set()
    for shot in data.shots:
        if shot.get("scorecardId") is not None:
            actual_ids.add(str(shot.get("scorecardId")))
        if _shot_round_id(shot) != "None":
            actual_ids.add(_shot_round_id(shot))
    if not expected_ids:
        expected_ids = sorted(actual_ids)
    missing_refs = [round_id for round_id in expected_ids if round_id not in actual_ids]
    ready = len(expected_ids) - len(missing_refs)
    total = len(expected_ids)
    return _with_quality_contract(
        {
            "label": "shot_rows",
            "state": "good" if total and ready == total else "partial" if ready else "missing",
            "ready": ready,
            "total": total,
            "refs": missing_refs,
            "rowCount": len(data.shots),
        }
    )


def _putt_quality(data: HistoryData) -> dict[str, Any]:
    ready_refs: list[str] = []
    missing_refs: list[str] = []
    for row in data.rounds:
        for hole in row.get("holes") or []:
            if not isinstance(hole, dict):
                continue
            number = int(hole.get("number") or 0)
            if not number or hole.get("strokes") is None:
                continue
            ref = _hole_ref(row, number)
            if hole.get("putts") is None:
                missing_refs.append(ref)
            else:
                ready_refs.append(ref)
    total = len(ready_refs) + len(missing_refs)
    return _with_quality_contract(
        {
            "label": "putts",
            "state": "good" if total and not missing_refs else "partial" if ready_refs else "missing",
            "ready": len(ready_refs),
            "total": total,
            "refs": missing_refs,
        }
    )


def _club_sample_quality(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    shots_by_club: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shot in _effective_shots(data, annotations):
        shots_by_club[_shot_club(shot)].append(shot)
    problem_refs: list[str] = []
    ready = 0
    for shots in shots_by_club.values():
        quality = _club_sample_quality_rows(shots)
        if int(quality["validSampleCount"]) >= 2:
            ready += 1
        else:
            problem_refs.extend(quality["validShotRefs"])
        problem_refs.extend(quality["problemRefs"])
    total = len(shots_by_club)
    return _with_quality_contract(
        {
            "label": "club_samples",
            "state": "good" if total and ready == total and not problem_refs else "partial" if ready or problem_refs else "missing",
            "ready": ready,
            "total": total,
            "refs": _source_refs(problem_refs),
        }
    )


def _decision_audit_quality(data: HistoryData, decision_audits: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    round_refs = _round_refs_by_date(data)
    audited_rounds = {
        _ref_round_id(ref)
        for record in _loaded_audit_records(data, decision_audits)
        for ref in _audit_all_refs(record)
    }
    ready_refs = [ref for ref in round_refs if ref in audited_rounds]
    total = len(round_refs)
    ready = len(ready_refs)
    return _with_quality_contract(
        {
            "label": "decision_audits",
            "state": "good" if total and ready == total else "partial" if ready else "missing",
            "ready": ready,
            "total": total,
            "refs": ready_refs,
            "auditCount": len(_loaded_audit_records(data, decision_audits)),
        }
    )


def _data_quality(
    data: HistoryData,
    annotations: list[dict[str, Any]] | None = None,
    weather_snapshots: list[dict[str, Any]] | None = None,
    hole_rows: list[dict[str, Any]] | None = None,
    report_records: list[dict[str, Any]] | None = None,
    decision_audits: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    total = len(data.raw_rounds)
    shots_ready = sum(1 for row in data.raw_rounds if row.get("hasShots"))
    annotation_count = len(annotations or [])
    corrections = [row for row in annotations or [] if row.get("kind") in CORRECTION_KINDS]
    return [
        _with_quality_contract(
            {
                "label": "shots",
                "state": "good" if total and shots_ready == total else "partial" if shots_ready else "missing",
                "ready": shots_ready,
                "total": total,
                "refs": [str(row.get("id")) for row in data.raw_rounds if not row.get("hasShots")],
            }
        ),
        _shot_row_quality(data),
        _putt_quality(data),
        _club_sample_quality(data, annotations),
        _geometry_quality(hole_rows or []),
        _with_quality_contract(
            {
                "label": "annotations",
                "state": "good" if annotation_count else "missing",
                "ready": annotation_count,
                "total": annotation_count,
                "refs": [str(row.get("id")) for row in annotations or []],
            }
        ),
        _with_quality_contract(
            {
                "label": "corrections",
                "state": "good" if corrections else "missing",
                "ready": len(corrections),
                "total": annotation_count,
                "refs": [str(row.get("id")) for row in corrections],
            }
        ),
        _decision_audit_quality(data, decision_audits),
        _report_quality(data, report_records),
        _weather_quality(data, weather_snapshots),
    ]


def build_history_stats(
    data: HistoryData,
    *,
    data_mode: DataModeName,
    annotations_root: Path | str | None = None,
    weather_root: Path | str | None = None,
    reports_root: Path | str | None = None,
    decision_audit_root: Path | str | None = None,
) -> dict[str, Any]:
    annotations = list_annotations(root=annotations_root)
    weather_snapshots = list_weather_snapshots(root=weather_root)
    report_records = list_report_records(root=reports_root)
    decision_audits = list_decision_audits(root=decision_audit_root)
    scored_data = _effective_score_data(data, annotations)
    hole_rows = _holes(scored_data, annotations)
    issue_rows = _issues(scored_data, annotations)
    diagnosis = _diagnosis(scored_data, issue_rows)
    diagnosis["decisionAuditTrends"] = _decision_audit_diagnosis(scored_data, decision_audits)
    return {
        "schema": "ai-caddie-history-stats-v1",
        "dataMode": data_mode,
        "summary": _summary(scored_data),
        "time": _time_stats(scored_data),
        "scoring": _scoring(scored_data, annotations),
        "courseDistribution": _course_distribution(scored_data),
        "records": _records(scored_data, annotations),
        "courses": _courses(scored_data),
        "holes": hole_rows,
        "clubs": _clubs(data, annotations),
        "issues": issue_rows,
        "diagnosis": diagnosis,
        "dataQuality": _data_quality(data, annotations, weather_snapshots, hole_rows, report_records, decision_audits),
        "drillDown": build_drilldown_index(data),
    }
