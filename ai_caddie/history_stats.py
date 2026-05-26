from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Literal

from ai_caddie.annotations import list_annotations
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


def _global_id(row: dict[str, Any]) -> int | None:
    try:
        return int(row["globalId"])
    except (KeyError, TypeError, ValueError):
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
    global_id = next((_global_id(row) for row, _hole in pairs if _global_id(row) is not None), None)
    if global_id is None:
        return "missing"
    try:
        return str(geometry_coverage_for_hole(global_id, hole_number)["coverage"])
    except Exception:
        return "missing"


def _summary(data: HistoryData) -> dict[str, Any]:
    rounds18 = [row for row in data.rounds if row.get("holesCompleted") == 18 and row.get("strokes") is not None]
    scores18 = [int(row["strokes"]) for row in rounds18]
    recent_scores18 = [
        int(row["strokes"])
        for row in sorted(rounds18, key=lambda row: str(row.get("date") or ""), reverse=True)
        if row.get("strokes") is not None
    ]
    return {
        "totalRounds": len(data.rounds),
        "eighteenHoleRounds": len(rounds18),
        "nineHoleRounds": sum(1 for row in data.rounds if row.get("holesCompleted") == 9),
        "courseCount": len({row.get("courseKey") for row in data.rounds if row.get("courseKey")}),
        "shotCount": len(data.shots),
        "average18": average(scores18),
        "median18": round(float(median(scores18)), 1) if scores18 else None,
        "recent5Average": average(recent_scores18[:5]),
        "recent10Average": average(recent_scores18[:10]),
        "recent20Average": average(recent_scores18[:20]),
        "bestScore": min(scores18) if scores18 else None,
        "worstScore": max(scores18) if scores18 else None,
    }


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

    def pack(key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        scores18 = [
            int(row["strokes"])
            for row in rows
            if row.get("holesCompleted") == 18 and row.get("strokes") is not None
        ]
        return {
            "key": key,
            "year": key if len(key) == 4 else None,
            "roundCount": len(rows),
            "average18": average(scores18),
            "bestScore": min(scores18) if scores18 else None,
            "roundIds": [_round_id(row) for row in rows],
        }

    known_months = [key for key in sorted(by_month) if key != "unknown"]
    most_active_month = None
    if known_months:
        most_active_key = max(known_months, key=lambda key: (len(by_month[key]), key))
        most_active_month = {"key": most_active_key, "roundCount": len(by_month[most_active_key])}

    return {
        "byYear": [pack(key, by_year[key]) for key in sorted(by_year, reverse=True)],
        "byQuarter": [pack(key, by_quarter[key]) for key in sorted(by_quarter, reverse=True)],
        "byMonth": [pack(key, by_month[key]) for key in sorted(by_month, reverse=True)],
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


def _scoring(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    bands: dict[str, list[str]] = {"70s": [], "80s": [], "90s": [], "100+": []}
    outcomes = Counter({"eagleOrBetter": 0, "birdie": 0, "par": 0, "bogey": 0, "doubleOrWorse": 0})
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
            fairway = str(hole.get("fairway") or "").lower()
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
            elif delta == -1:
                outcomes["birdie"] += 1
            elif delta == 0:
                outcomes["par"] += 1
            elif delta == 1:
                outcomes["bogey"] += 1
            else:
                outcomes["doubleOrWorse"] += 1
    return {
        "scoreBands": [
            {"label": label, "count": len(round_ids), "roundIds": round_ids}
            for label, round_ids in bands.items()
        ],
        "outcomes": {
            **dict(outcomes),
            "parOrBetter": outcomes["eagleOrBetter"] + outcomes["birdie"] + outcomes["par"],
            "bogeyOrWorse": outcomes["bogey"] + outcomes["doubleOrWorse"],
        },
        "putting": {
            "totalPutts": sum(putts),
            "holesWithPutts": len(putts),
            "averagePutts": average(putts),
            "threePutts": len(three_putt_refs),
            "threePuttRefs": three_putt_refs,
            "correctedRefs": corrected_putt_refs,
        },
        "phaseStats": [
            {
                "phase": "Tee",
                "fairwaysRecorded": fairways["recorded"],
                "fairwaysHit": fairways["hit"],
                "fairwayMissLeft": fairways["left"],
                "fairwayMissRight": fairways["right"],
                "holeRefs": tee_refs,
            },
            {
                "phase": "Approach",
                "girRecorded": gir["recorded"],
                "gir": gir["hit"],
                "missedGir": gir["recorded"] - gir["hit"],
                "girPct": round(gir["hit"] / gir["recorded"] * 100, 1) if gir["recorded"] else None,
                "holeRefs": approach_refs,
            },
            {
                "phase": "Short Game",
                "roughOrBunkerShots": sum(
                    1
                    for shot in _effective_shots(data, annotations)
                    if str(shot.get("surface") or "").lower() in {"rough", "bunker"}
                ),
                "shotRefs": [
                    str(shot.get("_ref"))
                    for shot in _effective_shots(data, annotations)
                    if str(shot.get("surface") or "").lower() in {"rough", "bunker"} and shot.get("_ref") is not None
                ],
            },
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
    for course_key, rows in grouped.items():
        rows_sorted = sorted(rows, key=lambda row: str(row.get("date") or ""), reverse=True)
        scores18 = [
            int(row["strokes"])
            for row in rows
            if row.get("holesCompleted") == 18 and row.get("strokes") is not None
        ]
        out.append(
            {
                "courseKey": course_key,
                "courseName": str(rows_sorted[0].get("course") or rows_sorted[0].get("courseName") or "Unknown course"),
                "roundCount": len(rows),
                "average18": average(scores18),
                "bestScore": min(scores18) if scores18 else None,
                "worstScore": max(scores18) if scores18 else None,
                "recentRoundId": _round_id(rows_sorted[0]),
                "roundIds": [_round_id(row) for row in rows_sorted],
                "roundRefs": [_round_id(row) for row in rows_sorted],
                "recentForm": _course_recent_form(rows),
                "geometryCoverage": _course_geometry_coverage(rows),
            }
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
        rows.append(
            {
                "courseKey": course_key,
                "courseName": str(rows_sorted[0].get("course") or rows_sorted[0].get("courseName") or "Unknown course"),
                "roundCount": len(course_rows),
                "pct": round(len(course_rows) / total * 100, 1) if total else 0.0,
                "roundRefs": [_round_id(row) for row in rows_sorted],
                "location": {
                    "latitude": rows_sorted[0].get("lat"),
                    "longitude": rows_sorted[0].get("lon"),
                }
                if rows_sorted[0].get("lat") is not None and rows_sorted[0].get("lon") is not None
                else None,
            }
        )
    return sorted(rows, key=lambda row: (-row["roundCount"], row["courseName"]))


def _round_record(row: dict[str, Any]) -> dict[str, Any]:
    score = row.get("strokes")
    par = row.get("par")
    return {
        "roundRef": _round_id(row),
        "courseKey": row.get("courseKey"),
        "courseName": str(row.get("course") or row.get("courseName") or "Unknown course"),
        "date": row.get("date"),
        "score": int(score) if score is not None else None,
        "par": int(par) if par is not None else None,
        "toPar": int(score) - int(par) if score is not None and par is not None else None,
    }


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
            {
                "shotRef": str(shot.get("_ref")),
                "roundRef": _shot_round_id(shot),
                "holeRef": f"{_shot_round_id(shot)}:{shot.get('hole')}",
                "club": _shot_club(shot),
                "distance": float(_shot_distance(shot)),
                "surface": _shot_surface(shot),
            }
            for shot in sorted(shots, key=lambda item: (-float(item.get("distance") or 0), str(item.get("_ref"))))[:5]
        ],
        "bestHoleOutcomes": sorted(hole_outcomes, key=lambda item: (int(item["toPar"]), int(item["score"]), str(item["holeRef"])))[:5],
        "worstHoleOutcomes": sorted(hole_outcomes, key=lambda item: (-int(item["toPar"]), -int(item["score"]), str(item["holeRef"])))[:5],
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
        {
            "key": key,
            "label": label,
            "className": class_name,
            "count": len(bucket_refs.get(key, [])),
            "pct": round(len(bucket_refs.get(key, [])) / total * 100, 1) if total else 0.0,
            "holeRefs": bucket_refs.get(key, []),
        }
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
            }
        )
    return sorted(out, key=lambda row: (row["courseKey"], row["hole"]))


def _clubs(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shot in _effective_shots(data, annotations):
        club = _shot_club(shot)
        grouped[club].append(shot)
    out = []
    for club, shots in grouped.items():
        distances = [float(_shot_distance(shot)) for shot in shots if _shot_distance(shot) is not None]
        round_ids = sorted({_shot_round_id(shot) for shot in shots if _shot_round_id(shot) != "None"})
        shot_refs = sorted(str(shot.get("_ref")) for shot in shots if shot.get("_ref") is not None)
        corrected_refs = sorted(
            str(shot.get("_ref"))
            for shot in shots
            if shot.get("_clubCorrected") and shot.get("_ref") is not None
        )
        out.append(
            {
                "club": club,
                "sampleCount": len(distances),
                "median": round(float(median(distances)), 1) if distances else None,
                "p10": percentile(distances, 0.1),
                "p90": percentile(distances, 0.9),
                "max": max(distances) if distances else None,
                "confidence": _confidence(len(distances)),
                "roundIds": round_ids,
                "shotRefs": shot_refs,
                "correctedRefs": corrected_refs,
                "correctionCount": len(corrected_refs),
            }
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
    total_holes = sum(len(row.get("holes") or []) for row in data.rounds)
    ready_refs = sorted(
        {
            f"{row.get('roundId')}:{row.get('hole')}"
            for row in weather_snapshots or []
            if row.get("state") == "ready" and row.get("roundId") is not None and row.get("hole") is not None
        }
    )
    return {
        "label": "weather",
        "state": "good" if total_holes and len(ready_refs) >= total_holes else "partial" if ready_refs else "missing",
        "ready": len(ready_refs),
        "total": total_holes,
        "refs": ready_refs,
    }


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
    return {
        "label": "geometry",
        "state": "good" if total and ready == total else "partial" if ready or partial else "missing",
        "ready": ready,
        "partial": partial,
        "total": total,
        "refs": refs,
    }


def _report_quality(data: HistoryData, report_records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    round_refs = [_round_id(row) for row in data.rounds]
    reported_rounds = {
        str(record.get("subjectId"))
        for record in report_records or []
        if record.get("kind") == "round" and record.get("subjectId") is not None
    }
    missing_refs = [ref for ref in round_refs if ref not in reported_rounds]
    ready = len(round_refs) - len(missing_refs)
    total = len(round_refs)
    return {
        "label": "reports",
        "state": "good" if total and ready == total else "partial" if ready else "missing",
        "ready": ready,
        "total": total,
        "refs": missing_refs,
    }


def _data_quality(
    data: HistoryData,
    annotations: list[dict[str, Any]] | None = None,
    weather_snapshots: list[dict[str, Any]] | None = None,
    hole_rows: list[dict[str, Any]] | None = None,
    report_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    total = len(data.raw_rounds)
    shots_ready = sum(1 for row in data.raw_rounds if row.get("hasShots"))
    annotation_count = len(annotations or [])
    corrections = [row for row in annotations or [] if row.get("kind") in CORRECTION_KINDS]
    return [
        {
            "label": "shots",
            "state": "good" if total and shots_ready == total else "partial" if shots_ready else "missing",
            "ready": shots_ready,
            "total": total,
            "refs": [str(row.get("id")) for row in data.raw_rounds if not row.get("hasShots")],
        },
        {
            "label": "shot_rows",
            "state": "good" if data.shots else "missing",
            "ready": len(data.shots),
            "total": len(data.shots),
            "refs": [],
        },
        _geometry_quality(hole_rows or []),
        {
            "label": "annotations",
            "state": "good" if annotation_count else "missing",
            "ready": annotation_count,
            "total": annotation_count,
            "refs": [str(row.get("id")) for row in annotations or []],
        },
        {
            "label": "corrections",
            "state": "good" if corrections else "missing",
            "ready": len(corrections),
            "total": annotation_count,
            "refs": [str(row.get("id")) for row in corrections],
        },
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
) -> dict[str, Any]:
    annotations = list_annotations(root=annotations_root)
    weather_snapshots = list_weather_snapshots(root=weather_root)
    report_records = list_report_records(root=reports_root)
    scored_data = _effective_score_data(data, annotations)
    hole_rows = _holes(scored_data, annotations)
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
        "issues": _issues(data, annotations),
        "dataQuality": _data_quality(data, annotations, weather_snapshots, hole_rows, report_records),
        "drillDown": build_drilldown_index(data),
    }
