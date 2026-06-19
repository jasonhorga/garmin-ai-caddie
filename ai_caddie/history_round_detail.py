"""Scorecard-first round detail contract for history review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_caddie.annotations import list_annotations
from ai_caddie.history import HistoryData


CORRECTION_KINDS = {"club_correction", "lie_correction", "penalty_correction", "putt_correction", "score_correction"}


def build_history_round_detail(
    data: HistoryData,
    round_ref: str,
    *,
    annotations_root: Path | str | None = None,
) -> dict[str, Any]:
    """Build a Garmin-like round review payload with scorecard as the first object."""

    ref = str(round_ref).strip()
    round_row = _round_aliases(data).get(ref)
    if not round_row:
        return _missing_round_detail(ref)

    canonical_ref = _round_id(round_row)
    shots = _shots_for_round(data, canonical_ref)
    shots_by_hole = _shots_by_hole(shots)
    scorecard = _scorecard(round_row, shots_by_hole)
    hole_details = _hole_details(round_row, shots_by_hole)
    related_refs = _related_refs(round_row, shots, scorecard)
    source_fields = _pick(
        round_row,
        [
            "id",
            "ids",
            "date",
            "course",
            "courseCanonical",
            "courseKey",
            "courseId",
            "globalId",
            "frontNineGlobalCourseId",
            "backNineGlobalCourseId",
            "snapshotId",
            "strokes",
            "par",
            "holePars",
            "holesCompleted",
            "hasShots",
            "shotStatus",
            "putts",
            "fh",
            "fl",
            "fr",
            "frec",
            "gir",
            "merged",
            "provenance",
        ],
    )
    round_summary = _round_summary(round_row, scorecard, shots)
    detail = {
        "schema": "ai-caddie-history-round-detail-v1",
        "roundRef": canonical_ref,
        "requestedRef": ref,
        "found": True,
        "title": f"{round_summary['courseName']} - {round_summary.get('date') or 'unknown date'}",
        "round": round_summary,
        "scorecard": scorecard,
        "phaseSummary": _phase_summary(round_row, scorecard, shots_by_hole),
        "holeDetails": hole_details,
        "relatedRefs": related_refs,
        "sourceFields": source_fields,
        "missingData": _missing_data(round_row, scorecard, shots),
        "annotations": [],
        "corrections": [],
    }
    return _attach_annotations(detail, annotations_root)


def _round_id(row: dict[str, Any]) -> str:
    return str(row.get("id"))


def _hole_ref(round_ref: str, hole_number: int) -> str:
    return f"{round_ref}:{hole_number}"


def _shot_round_id(shot: dict[str, Any]) -> str:
    return str(shot.get("roundId") or shot.get("scorecardId"))


def _shot_ref(shot: dict[str, Any], index: int) -> str:
    return f"{_shot_round_id(shot)}:{shot.get('hole')}:{index}"


def _source_refs(row: dict[str, Any]) -> list[str]:
    provenance = row.get("provenance")
    if not isinstance(provenance, dict):
        return []
    refs = provenance.get("sourceRefs")
    if not isinstance(refs, list):
        return []
    return [str(ref).strip() for ref in refs if str(ref).strip()]


def _round_aliases(data: HistoryData) -> dict[str, dict[str, Any]]:
    aliases: dict[str, dict[str, Any]] = {}
    for row in data.rounds:
        aliases[_round_id(row)] = row
        for item in row.get("ids") or []:
            aliases[str(item)] = row
        for source_ref in _source_refs(row):
            aliases[source_ref] = row
    return aliases


def _shots_for_round(data: HistoryData, round_ref: str) -> list[tuple[int, dict[str, Any]]]:
    return [
        (index, shot)
        for index, shot in enumerate(data.shots)
        if _shot_round_id(shot) == round_ref
    ]


def _shots_by_hole(shots: list[tuple[int, dict[str, Any]]]) -> dict[int, list[tuple[int, dict[str, Any]]]]:
    by_hole: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    for index, shot in shots:
        try:
            hole = int(shot.get("hole") or 0)
        except (TypeError, ValueError):
            continue
        if hole <= 0:
            continue
        by_hole.setdefault(hole, []).append((index, shot))
    for rows in by_hole.values():
        rows.sort(key=lambda item: _shot_order(item[1], item[0]))
    return by_hole


def _shot_order(shot: dict[str, Any], fallback: int) -> int:
    try:
        return int(shot.get("order") if shot.get("order") is not None else fallback)
    except (TypeError, ValueError):
        return fallback


def _holes_by_number(row: dict[str, Any]) -> dict[int, dict[str, Any]]:
    holes: dict[int, dict[str, Any]] = {}
    for index, hole in enumerate(row.get("holes") or [], start=1):
        if not isinstance(hole, dict):
            continue
        try:
            number = int(hole.get("number") or index)
        except (TypeError, ValueError):
            continue
        if number > 0:
            holes[number] = hole
    return holes


def _scorecard_length(row: dict[str, Any], holes_by_number: dict[int, dict[str, Any]], shots_by_hole: dict[int, list[tuple[int, dict[str, Any]]]]) -> int:
    holes_completed = row.get("holesCompleted")
    if holes_completed in (9, 18):
        return int(holes_completed)
    hole_pars = str(row.get("holePars") or "")
    if len(hole_pars) in (9, 18):
        return len(hole_pars)
    max_hole = max([0, *holes_by_number.keys(), *shots_by_hole.keys()])
    return max_hole


def _par_for_hole(row: dict[str, Any], hole: dict[str, Any] | None, hole_number: int) -> int | None:
    value = hole.get("par") if hole else None
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    hole_pars = str(row.get("holePars") or "")
    if 1 <= hole_number <= len(hole_pars):
        try:
            return int(hole_pars[hole_number - 1])
        except ValueError:
            return None
    return None


def _score_class(score: int | None, par: int | None) -> str:
    if score is None or par is None:
        return "missing"
    delta = score - par
    if delta <= -2:
        return "eagle"
    if delta == -1:
        return "birdie"
    if delta == 0:
        return "par"
    if delta == 1:
        return "bogey"
    return "double"


def _scorecard(row: dict[str, Any], shots_by_hole: dict[int, list[tuple[int, dict[str, Any]]]]) -> list[dict[str, Any]]:
    holes_by_number = _holes_by_number(row)
    length = _scorecard_length(row, holes_by_number, shots_by_hole)
    round_ref = _round_id(row)
    cells: list[dict[str, Any]] = []
    for hole_number in range(1, length + 1):
        hole = holes_by_number.get(hole_number)
        par = _par_for_hole(row, hole, hole_number)
        score = _int_value(hole.get("strokes")) if hole else None
        to_par = score - par if score is not None and par is not None else None
        shot_refs = [_shot_ref(shot, index) for index, shot in shots_by_hole.get(hole_number, [])]
        geometry_target = _hole_geometry_target(row, hole_number)
        source_refs = [_hole_ref(round_ref, hole_number), *shot_refs]
        cells.append(
            {
                "hole": hole_number,
                "par": par,
                "score": score,
                "toPar": to_par,
                "className": _score_class(score, par),
                "putts": _int_value(hole.get("putts")) if hole else None,
                "gir": hole.get("gir") if hole else None,
                "fairway": hole.get("fairway") if hole else None,
                "globalId": geometry_target.get("globalId"),
                "localHole": geometry_target.get("localHole"),
                "holeRef": _hole_ref(round_ref, hole_number),
                "shotRefs": shot_refs,
                "sourceRefs": _dedupe([*source_refs, *_source_refs(hole or {})]),
                "status": "complete" if hole and score is not None else "missing_score",
            }
        )
    return cells


def _hole_details(row: dict[str, Any], shots_by_hole: dict[int, list[tuple[int, dict[str, Any]]]]) -> list[dict[str, Any]]:
    holes_by_number = _holes_by_number(row)
    all_holes = sorted(set(holes_by_number) | set(shots_by_hole))
    round_ref = _round_id(row)
    details = []
    for hole_number in all_holes:
        hole = holes_by_number.get(hole_number)
        par = _par_for_hole(row, hole, hole_number)
        score = _int_value(hole.get("strokes")) if hole else None
        shot_summaries = [_shot_summary(shot, index) for index, shot in shots_by_hole.get(hole_number, [])]
        geometry_target = _hole_geometry_target(row, hole_number)
        details.append(
            {
                "hole": hole_number,
                "par": par,
                "score": score,
                "toPar": score - par if score is not None and par is not None else None,
                "putts": _int_value(hole.get("putts")) if hole else None,
                "gir": hole.get("gir") if hole else None,
                "fairway": hole.get("fairway") if hole else None,
                "globalId": geometry_target.get("globalId"),
                "localHole": geometry_target.get("localHole"),
                "holeRef": _hole_ref(round_ref, hole_number),
                "shotCount": len(shot_summaries),
                "shotRefs": [shot["ref"] for shot in shot_summaries],
                "shots": shot_summaries,
            }
        )
    return details


def _shot_summary(shot: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "ref": _shot_ref(shot, index),
        "hole": _int_value(shot.get("hole")),
        "order": _shot_order(shot, index),
        "club": shot.get("club") or shot.get("clubName"),
        "distance": shot.get("distance") if shot.get("distance") is not None else shot.get("meters"),
        "surface": shot.get("surface") if shot.get("surface") is not None else shot.get("endLie"),
        "shotType": shot.get("type") or shot.get("shotType"),
        "sourceRefs": _dedupe([_shot_ref(shot, index), *_source_refs(shot)]),
    }


def _round_summary(row: dict[str, Any], scorecard: list[dict[str, Any]], shots: list[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    score = _int_value(row.get("strokes"))
    par = _int_value(row.get("par"))
    scored_cells = [cell for cell in scorecard if cell.get("score") is not None]
    shot_ready = bool(row.get("hasShots")) or bool(shots)
    putt_cells = [cell for cell in scorecard if cell.get("putts") is not None]
    return {
        "id": _round_id(row),
        "date": row.get("date"),
        "courseName": row.get("course") or row.get("courseName") or "Unknown course",
        "courseKey": row.get("courseKey"),
        "courseId": row.get("courseId"),
        "globalId": _round_global_id(row),
        "frontNineGlobalCourseId": row.get("frontNineGlobalCourseId"),
        "backNineGlobalCourseId": row.get("backNineGlobalCourseId"),
        "score": score,
        "par": par,
        "toPar": score - par if score is not None and par is not None else None,
        "holesCompleted": row.get("holesCompleted"),
        "holesScored": len(scored_cells),
        "shotCount": len(shots),
        "hasShots": shot_ready,
        "shotStatus": row.get("shotStatus") or ("ready" if shot_ready else "missing"),
        "coverage": {
            "scorecard": "ready" if scored_cells else "missing",
            "shots": "ready" if shots else "missing",
            "putts": "ready" if putt_cells and len(putt_cells) == len(scored_cells) else "partial" if putt_cells else "missing",
        },
        "confidence": _confidence(row, scorecard, shots),
        "sourceRefs": _dedupe([_round_id(row), *[str(item) for item in row.get("ids") or []], *_source_refs(row)]),
    }


def _confidence(row: dict[str, Any], scorecard: list[dict[str, Any]], shots: list[tuple[int, dict[str, Any]]]) -> str:
    provenance = row.get("provenance")
    if isinstance(provenance, dict):
        confidence = provenance.get("confidence")
        if isinstance(confidence, str) and confidence in {"low", "medium", "high"}:
            return confidence
    scored = sum(1 for cell in scorecard if cell.get("score") is not None)
    if scored and shots:
        return "high"
    if scored:
        return "medium"
    return "low"


def _phase_summary(
    row: dict[str, Any],
    scorecard: list[dict[str, Any]],
    shots_by_hole: dict[int, list[tuple[int, dict[str, Any]]]],
) -> list[dict[str, Any]]:
    tee_shots: list[tuple[int, dict[str, Any]]] = []
    approach_shots: list[tuple[int, dict[str, Any]]] = []
    short_game_shots: list[tuple[int, dict[str, Any]]] = []
    putt_shots: list[tuple[int, dict[str, Any]]] = []

    for hole_number, shots in sorted(shots_by_hole.items()):
        for position, item in enumerate(shots):
            shot_type = _shot_type(item[1])
            if shot_type == "putt":
                putt_shots.append(item)
            elif position == 0:
                tee_shots.append(item)
            elif _looks_short_game(item[1]):
                short_game_shots.append(item)
            else:
                approach_shots.append(item)

    fairways = [cell for cell in scorecard if cell.get("fairway") is not None]
    fairways_hit = sum(1 for cell in fairways if _fairway_hit(cell.get("fairway")))
    gir_recorded = [cell for cell in scorecard if cell.get("gir") is not None]
    gir_hit = sum(1 for cell in gir_recorded if bool(cell.get("gir")))
    putt_cells = [cell for cell in scorecard if cell.get("putts") is not None]
    putts_total = sum(int(cell["putts"]) for cell in putt_cells)
    three_putts = sum(1 for cell in putt_cells if int(cell["putts"]) >= 3)
    score_penalties = sum(1 for cell in scorecard if (cell.get("toPar") or 0) >= 2)

    return [
        {
            "phase": "Tee",
            "state": "ready" if tee_shots or fairways else "missing",
            "primary": f"{fairways_hit}/{len(fairways)} 球道命中" if fairways else f"{len(tee_shots)} 次开球",
            "metrics": {"shots": len(tee_shots), "fairwaysHit": fairways_hit, "fairwaysRecorded": len(fairways)},
            "sourceRefs": _dedupe([_shot_ref(shot, index) for index, shot in tee_shots]),
        },
        {
            "phase": "Approach",
            "state": "ready" if approach_shots or gir_recorded else "missing",
            "primary": f"{gir_hit}/{len(gir_recorded)} 标准杆上果岭" if gir_recorded else f"{len(approach_shots)} 次攻果岭",
            "metrics": {"shots": len(approach_shots), "gir": gir_hit, "girRecorded": len(gir_recorded)},
            "sourceRefs": _dedupe([_shot_ref(shot, index) for index, shot in approach_shots]),
        },
        {
            "phase": "Short Game",
            "state": "ready" if short_game_shots else "missing",
            "primary": f"{len(short_game_shots)} 次短杆",
            "metrics": {"shots": len(short_game_shots)},
            "sourceRefs": _dedupe([_shot_ref(shot, index) for index, shot in short_game_shots]),
        },
        {
            "phase": "Putting",
            "state": "ready" if putt_cells or putt_shots else "missing",
            "primary": f"{putts_total} 推" if putt_cells else f"{len(putt_shots)} 次推击",
            "metrics": {"totalPutts": putts_total if putt_cells else None, "holesWithPutts": len(putt_cells), "threePutts": three_putts},
            "sourceRefs": _dedupe([_hole_ref(_round_id(row), int(cell["hole"])) for cell in putt_cells]),
        },
        {
            "phase": "Penalty / Damage",
            "state": "partial" if score_penalties else "missing",
            "primary": f"{score_penalties} 个双柏忌及以上",
            "metrics": {"doubleOrWorseHoles": score_penalties},
            "sourceRefs": _dedupe([str(cell.get("holeRef")) for cell in scorecard if (cell.get("toPar") or 0) >= 2]),
        },
    ]


def _shot_type(shot: dict[str, Any]) -> str:
    text = str(shot.get("type") or shot.get("shotType") or shot.get("auto") or "").lower()
    if "putt" in text:
        return "putt"
    return "shot"


def _looks_short_game(shot: dict[str, Any]) -> bool:
    club = str(shot.get("club") or shot.get("clubName") or "").lower()
    distance = shot.get("distance") if shot.get("distance") is not None else shot.get("meters")
    if any(token in club for token in ("sw", "lw", "gw", "pw", "54", "56", "58", "wedge")):
        return True
    try:
        return float(distance) <= 70
    except (TypeError, ValueError):
        return False


def _fairway_hit(value: Any) -> bool:
    return str(value or "").strip().lower() in {"hit", "fairway", "center", "centre", "true", "1"}


def _related_refs(row: dict[str, Any], shots: list[tuple[int, dict[str, Any]]], scorecard: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "roundRefs": _dedupe([_round_id(row), *[str(item) for item in row.get("ids") or []]]),
        "holeRefs": _dedupe([str(cell["holeRef"]) for cell in scorecard]),
        "shotRefs": _dedupe([_shot_ref(shot, index) for index, shot in shots]),
        "sourceRefs": _dedupe([*_source_refs(row), *[ref for _, shot in shots for ref in _source_refs(shot)]]),
    }


def _missing_data(row: dict[str, Any], scorecard: list[dict[str, Any]], shots: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not scorecard:
        rows.append({"label": "scorecard", "state": "missing", "reason": "这一局没有记分卡洞数据"})
    elif any(cell.get("score") is None for cell in scorecard):
        missing = sum(1 for cell in scorecard if cell.get("score") is None)
        rows.append({"label": "hole scores", "state": "partial", "reason": f"{missing} 个洞没有成绩"})
    if not shots:
        rows.append({"label": "shot rows", "state": "missing", "reason": "这一局没有逐杆 GPS 数据"})
    if not any(cell.get("putts") is not None for cell in scorecard):
        rows.append({"label": "putts", "state": "missing", "reason": "记分卡没有推杆数"})
    if row.get("par") is None:
        rows.append({"label": "round par", "state": "missing", "reason": "没有标准杆数据"})
    return rows


def _missing_round_detail(ref: str) -> dict[str, Any]:
    return {
        "schema": "ai-caddie-history-round-detail-v1",
        "roundRef": ref,
        "requestedRef": ref,
        "found": False,
        "title": "未找到这一局",
        "round": None,
        "scorecard": [],
        "phaseSummary": [],
        "holeDetails": [],
        "relatedRefs": {"roundRefs": [], "holeRefs": [], "shotRefs": [], "sourceRefs": []},
        "sourceFields": {},
        "missingData": [{"label": "round_ref", "state": "missing", "reason": f"{ref} 在历史数据里没找到"}],
        "annotations": [],
        "corrections": [],
    }


def _attach_annotations(detail: dict[str, Any], annotations_root: Path | str | None) -> dict[str, Any]:
    if not detail.get("found"):
        return detail
    target_ids = set(detail.get("relatedRefs", {}).get("roundRefs") or [])
    target_ids.add(str(detail.get("roundRef") or ""))
    annotations = [
        record
        for record in list_annotations(root=annotations_root)
        if record.get("targetType") == "round" and str(record.get("targetId") or "") in target_ids
    ]
    detail["annotations"] = annotations
    detail["corrections"] = [record for record in annotations if record.get("kind") in CORRECTION_KINDS]
    return detail


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round_global_id(row: dict[str, Any]) -> int | None:
    for key in ("globalId", "courseId", "frontNineGlobalCourseId", "backNineGlobalCourseId"):
        value = _int_value(row.get(key))
        if value is not None:
            return value
    return None


def _hole_geometry_target(row: dict[str, Any], hole_number: int) -> dict[str, int | None]:
    if hole_number <= 0:
        return {"globalId": _round_global_id(row), "localHole": None}
    if hole_number <= 9:
        return {
            "globalId": _int_value(row.get("frontNineGlobalCourseId")) or _int_value(row.get("globalId")) or _int_value(row.get("courseId")),
            "localHole": hole_number,
        }
    back_global_id = _int_value(row.get("backNineGlobalCourseId"))
    if back_global_id is not None:
        return {"globalId": back_global_id, "localHole": hole_number - 9}
    return {
        "globalId": _int_value(row.get("globalId")) or _int_value(row.get("courseId")) or _int_value(row.get("frontNineGlobalCourseId")),
        "localHole": hole_number,
    }


def _dedupe(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _pick(row: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if key in row}
