"""Resolve history aggregate references back to source rounds, holes, and shots."""

from __future__ import annotations

from typing import Any, Literal

from ai_caddie.history import HistoryData


RefType = Literal["round", "hole", "shot", "unknown"]


def _round_id(row: dict[str, Any]) -> str:
    return str(row.get("id"))


def _hole_ref(round_id: str, hole_number: int) -> str:
    return f"{round_id}:{hole_number}"


def _shot_ref(shot: dict[str, Any], index: int) -> str:
    return f"{shot.get('roundId')}:{shot.get('hole')}:{index}"


def _parse_ref(source_ref: str) -> tuple[RefType, list[str]]:
    parts = [part for part in str(source_ref).split(":") if part != ""]
    if len(parts) == 1:
        return "round", parts
    if len(parts) == 2:
        return "hole", parts
    if len(parts) == 3:
        return "shot", parts
    return "unknown", parts


def build_drilldown_index(data: HistoryData) -> dict[str, list[str]]:
    round_refs = [_round_id(row) for row in data.rounds]
    hole_refs = [
        _hole_ref(_round_id(row), int(hole.get("number")))
        for row in data.rounds
        for hole in (row.get("holes") or [])
        if isinstance(hole, dict) and hole.get("number")
    ]
    shot_refs = [_shot_ref(shot, index) for index, shot in enumerate(data.shots)]
    return {
        "roundIds": round_refs,
        "roundRefs": round_refs,
        "holeRefs": hole_refs,
        "shotRefs": shot_refs,
    }


def resolve_history_ref(data: HistoryData, source_ref: str) -> dict[str, Any]:
    ref = str(source_ref)
    ref_type, parts = _parse_ref(ref)
    rounds_by_id = {_round_id(row): row for row in data.rounds}
    shots_by_ref = {_shot_ref(shot, index): (index, shot) for index, shot in enumerate(data.shots)}

    if ref_type == "round" and parts:
        row = rounds_by_id.get(parts[0])
        if row:
            return _round_detail(data, row, ref)
    elif ref_type == "hole" and len(parts) == 2:
        row = rounds_by_id.get(parts[0])
        hole = _find_hole(row, parts[1]) if row else None
        if row and hole:
            return _hole_detail(data, row, hole, ref)
    elif ref_type == "shot" and len(parts) == 3:
        item = shots_by_ref.get(ref)
        row = rounds_by_id.get(parts[0])
        hole = _find_hole(row, parts[1]) if row else None
        if item and row:
            index, shot = item
            return _shot_detail(row, hole, shot, index, ref)

    return _missing_detail(ref, ref_type)


def _round_summary(row: dict[str, Any]) -> dict[str, Any]:
    score = row.get("strokes")
    par = row.get("par")
    return {
        "id": _round_id(row),
        "date": row.get("date"),
        "courseName": row.get("course") or row.get("courseName") or "Unknown course",
        "courseKey": row.get("courseKey"),
        "score": score,
        "par": par,
        "toPar": int(score) - int(par) if score is not None and par is not None else None,
        "holesCompleted": row.get("holesCompleted"),
        "hasShots": bool(row.get("hasShots")),
        "globalId": row.get("globalId"),
    }


def _hole_summary(row: dict[str, Any], hole: dict[str, Any]) -> dict[str, Any]:
    par = hole.get("par")
    score = hole.get("strokes")
    if par is None:
        par = _par_from_string(str(row.get("holePars") or ""), int(hole.get("number") or 0))
    return {
        "number": hole.get("number"),
        "par": par,
        "strokes": score,
        "toPar": int(score) - int(par) if score is not None and par is not None else None,
        "putts": hole.get("putts"),
        "gir": hole.get("gir"),
        "fairway": hole.get("fairway"),
    }


def _shot_summary(shot: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "ref": _shot_ref(shot, index),
        "roundId": str(shot.get("roundId")),
        "hole": shot.get("hole"),
        "club": shot.get("club") or shot.get("clubName"),
        "distance": shot.get("distance"),
        "surface": shot.get("surface"),
        "globalShotIndex": index,
    }


def _round_detail(data: HistoryData, row: dict[str, Any], ref: str) -> dict[str, Any]:
    round_ref = _round_id(row)
    hole_refs = [
        _hole_ref(round_ref, int(hole.get("number")))
        for hole in (row.get("holes") or [])
        if isinstance(hole, dict) and hole.get("number")
    ]
    shot_refs = [
        _shot_ref(shot, index)
        for index, shot in enumerate(data.shots)
        if str(shot.get("roundId")) == round_ref
    ]
    return _base_detail(
        ref=ref,
        ref_type="round",
        found=True,
        title=f"{row.get('course') or row.get('courseName') or 'Unknown course'} - {row.get('date') or 'unknown date'}",
        round_summary=_round_summary(row),
        hole=None,
        shot=None,
        related_refs={"roundRefs": [round_ref], "holeRefs": hole_refs, "shotRefs": shot_refs},
        source_fields=_pick(row, ["id", "ids", "date", "course", "courseKey", "strokes", "par", "holesCompleted", "hasShots"]),
    )


def _hole_detail(data: HistoryData, row: dict[str, Any], hole: dict[str, Any], ref: str) -> dict[str, Any]:
    round_ref = _round_id(row)
    hole_number = int(hole.get("number"))
    shot_refs = [
        _shot_ref(shot, index)
        for index, shot in enumerate(data.shots)
        if str(shot.get("roundId")) == round_ref and int(shot.get("hole") or 0) == hole_number
    ]
    return _base_detail(
        ref=ref,
        ref_type="hole",
        found=True,
        title=f"{row.get('course') or row.get('courseName') or 'Unknown course'} H{hole_number}",
        round_summary=_round_summary(row),
        hole=_hole_summary(row, hole),
        shot=None,
        related_refs={"roundRefs": [round_ref], "holeRefs": [ref], "shotRefs": shot_refs},
        source_fields=_pick(hole, ["number", "strokes", "par", "putts", "gir", "fairway"]),
    )


def _shot_detail(
    row: dict[str, Any],
    hole: dict[str, Any] | None,
    shot: dict[str, Any],
    index: int,
    ref: str,
) -> dict[str, Any]:
    round_ref = _round_id(row)
    hole_number = int(shot.get("hole") or 0)
    shot_summary = _shot_summary(shot, index)
    source_fields = _pick(shot, ["roundId", "hole", "club", "clubName", "distance", "surface"])
    source_fields["globalShotIndex"] = index
    return _base_detail(
        ref=ref,
        ref_type="shot",
        found=True,
        title=f"{shot_summary.get('club') or 'Shot'} on H{hole_number}",
        round_summary=_round_summary(row),
        hole=_hole_summary(row, hole) if hole else None,
        shot=shot_summary,
        related_refs={"roundRefs": [round_ref], "holeRefs": [_hole_ref(round_ref, hole_number)], "shotRefs": [ref]},
        source_fields=source_fields,
    )


def _missing_detail(ref: str, ref_type: RefType) -> dict[str, Any]:
    return _base_detail(
        ref=ref,
        ref_type=ref_type,
        found=False,
        title="Source reference not found",
        round_summary=None,
        hole=None,
        shot=None,
        related_refs={"roundRefs": [], "holeRefs": [], "shotRefs": []},
        source_fields={},
        missing_data=[{"label": "source_ref", "reason": f"{ref} was not found in loaded history data"}],
    )


def _base_detail(
    *,
    ref: str,
    ref_type: RefType,
    found: bool,
    title: str,
    round_summary: dict[str, Any] | None,
    hole: dict[str, Any] | None,
    shot: dict[str, Any] | None,
    related_refs: dict[str, list[str]],
    source_fields: dict[str, Any],
    missing_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "ai-caddie-history-drilldown-v1",
        "ref": ref,
        "refType": ref_type,
        "found": found,
        "title": title,
        "round": round_summary,
        "hole": hole,
        "shot": shot,
        "relatedRefs": related_refs,
        "sourceFields": source_fields,
        "missingData": missing_data or [],
    }


def _find_hole(row: dict[str, Any] | None, hole_number: str) -> dict[str, Any] | None:
    if row is None:
        return None
    try:
        number = int(hole_number)
    except ValueError:
        return None
    for hole in row.get("holes") or []:
        if isinstance(hole, dict) and int(hole.get("number") or 0) == number:
            return hole
    return None


def _par_from_string(hole_pars: str, hole_number: int) -> int | None:
    if 1 <= hole_number <= len(hole_pars):
        try:
            return int(hole_pars[hole_number - 1])
        except ValueError:
            return None
    return None


def _pick(row: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if key in row}
