from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Literal

from ai_caddie.annotations import list_annotations
from ai_caddie.geometry_evidence import geometry_coverage_for_course, geometry_coverage_for_hole
from ai_caddie.history import HistoryData, average, percentile
from ai_caddie.issue_taxonomy import issue_record
from ai_caddie.weather_context import list_weather_snapshots

DataModeName = Literal["local", "fixture"]
CORRECTION_KINDS = {"club_correction", "lie_correction", "penalty_correction", "putt_correction"}


def _round_id(row: dict[str, Any]) -> str:
    return str(row.get("id"))


def _hole_ref(row: dict[str, Any], hole_number: int) -> str:
    return f"{_round_id(row)}:{hole_number}"


def _shot_ref(shot: dict[str, Any], index: int) -> str:
    return f"{shot.get('roundId')}:{shot.get('hole')}:{index}"


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


def _effective_shots(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    club_corrections = _annotations_by_kind(annotations, "club_correction")
    lie_corrections = _annotations_by_kind(annotations, "lie_correction")
    rows = []
    for index, shot in enumerate(data.shots):
        ref = _shot_ref(shot, index)
        row = dict(shot)
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
    return {
        "totalRounds": len(data.rounds),
        "eighteenHoleRounds": len(rounds18),
        "nineHoleRounds": sum(1 for row in data.rounds if row.get("holesCompleted") == 9),
        "courseCount": len({row.get("courseKey") for row in data.rounds if row.get("courseKey")}),
        "shotCount": len(data.shots),
        "average18": average(scores18),
        "bestScore": min(scores18) if scores18 else None,
        "worstScore": max(scores18) if scores18 else None,
    }


def _time_stats(data: HistoryData) -> dict[str, Any]:
    by_year: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.rounds:
        date = str(row.get("date") or "")
        year = date[:4] if len(date) >= 4 else "unknown"
        month = date[:7] if len(date) >= 7 else "unknown"
        by_year[year].append(row)
        by_month[month].append(row)

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

    return {
        "byYear": [pack(key, by_year[key]) for key in sorted(by_year, reverse=True)],
        "byMonth": [pack(key, by_month[key]) for key in sorted(by_month, reverse=True)],
    }


def _scoring(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    bands: dict[str, list[str]] = {"70s": [], "80s": [], "90s": [], "100+": []}
    outcomes = Counter({"eagleOrBetter": 0, "birdie": 0, "par": 0, "bogey": 0, "doubleOrWorse": 0})
    putt_corrections = _annotations_by_kind(annotations, "putt_correction")
    putts: list[int] = []
    three_putt_refs: list[str] = []
    corrected_putt_refs: list[str] = []
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
                if putt_count >= 3:
                    three_putt_refs.append(ref)
                if ref in putt_corrections:
                    corrected_putt_refs.append(ref)
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
                "geometryCoverage": _course_geometry_coverage(rows),
            }
        )
    return sorted(out, key=lambda row: (-row["roundCount"], row["courseName"]))


def _holes(data: HistoryData) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for row in data.rounds:
        course_key = str(row.get("courseKey") or "unknown")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            if number:
                grouped[(course_key, number)].append((row, hole))
    out = []
    for (course_key, number), pairs in grouped.items():
        deltas: list[int] = []
        refs: list[str] = []
        for row, hole in pairs:
            par = _hole_to_par(hole, _par_from_string(str(row.get("holePars") or ""), number))
            score = hole.get("strokes")
            if par is not None and score is not None:
                deltas.append(int(score) - int(par))
            refs.append(f"{_round_id(row)}:{number}")
        out.append(
            {
                "courseKey": course_key,
                "hole": number,
                "sampleCount": len(pairs),
                "averageToPar": average(deltas),
                "worstToPar": max(deltas) if deltas else None,
                "refs": refs,
                "geometryCoverage": _hole_geometry_coverage(pairs, number),
            }
        )
    return sorted(out, key=lambda row: (row["courseKey"], row["hole"]))


def _clubs(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shot in _effective_shots(data, annotations):
        club = str(shot.get("club") or shot.get("clubName") or "Unknown")
        grouped[club].append(shot)
    out = []
    for club, shots in grouped.items():
        distances = [float(shot["distance"]) for shot in shots if shot.get("distance") is not None]
        round_ids = sorted({str(shot.get("roundId")) for shot in shots if shot.get("roundId") is not None})
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
                "correctedRefs": corrected_refs,
                "correctionCount": len(corrected_refs),
            }
        )
    return sorted(out, key=lambda row: row["club"])


def _issues(data: HistoryData, annotations: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    refs: dict[str, list[str]] = defaultdict(list)
    for row in data.rounds:
        if not row.get("hasShots"):
            refs["missing_shots"].append(_round_id(row))
        hole_pars = str(row.get("holePars") or "")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            par = _hole_to_par(hole, _par_from_string(hole_pars, number))
            score = hole.get("strokes")
            if number and par is not None and score is not None and int(score) - int(par) >= 2:
                refs["double_or_worse"].append(f"{_round_id(row)}:{number}")
    for shot in _effective_shots(data, annotations):
        if str(shot.get("surface") or "").lower() in {"water", "bunker", "rough"}:
            refs["hazard_result"].append(f"{shot.get('roundId')}:{shot.get('hole')}")
    rows = [issue_record(issue, items, source="deterministic") for issue, items in sorted(refs.items())]
    manual_refs: dict[str, list[str]] = defaultdict(list)
    for record in annotations or []:
        kind = record.get("kind")
        target_id = str(record.get("targetId") or "")
        if kind == "issue_tag":
            tag = str((record.get("payload") or {}).get("tag") or "").strip()
            if tag:
                manual_refs[tag].append(target_id)
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


def _data_quality(
    data: HistoryData,
    annotations: list[dict[str, Any]] | None = None,
    weather_snapshots: list[dict[str, Any]] | None = None,
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
        _weather_quality(data, weather_snapshots),
    ]


def build_history_stats(
    data: HistoryData,
    *,
    data_mode: DataModeName,
    annotations_root: Path | str | None = None,
    weather_root: Path | str | None = None,
) -> dict[str, Any]:
    annotations = list_annotations(root=annotations_root)
    weather_snapshots = list_weather_snapshots(root=weather_root)
    return {
        "schema": "ai-caddie-history-stats-v1",
        "dataMode": data_mode,
        "summary": _summary(data),
        "time": _time_stats(data),
        "scoring": _scoring(data, annotations),
        "courses": _courses(data),
        "holes": _holes(data),
        "clubs": _clubs(data, annotations),
        "issues": _issues(data, annotations),
        "dataQuality": _data_quality(data, annotations, weather_snapshots),
        "drillDown": {
            "roundIds": [_round_id(row) for row in data.rounds],
            "shotRefs": [f"{shot.get('roundId')}:{shot.get('hole')}:{index}" for index, shot in enumerate(data.shots)],
        },
    }
