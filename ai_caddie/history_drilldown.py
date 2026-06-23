"""Resolve history aggregate references back to source rounds, holes, and shots."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from ai_caddie.annotations import list_annotations
from ai_caddie.decision import list_decision_audits
from ai_caddie.geometry_evidence import geometry_coverage_for_hole
from ai_caddie.history import HistoryData
from ai_caddie.reports import list_report_records
from ai_caddie.weather_context import list_weather_snapshots


RefType = Literal["round", "hole", "shot", "unknown"]
CORRECTION_KINDS = {"club_correction", "lie_correction", "penalty_correction", "putt_correction", "score_correction"}


def _round_id(row: dict[str, Any]) -> str:
    return str(row.get("id"))


def _hole_ref(round_id: str, hole_number: int) -> str:
    return f"{round_id}:{hole_number}"


def _shot_ref(shot: dict[str, Any], index: int) -> str:
    # _globalIndex (stamped at load on the full shots list) keeps the ref stable under windowing —
    # build_drilldown_index runs on the WINDOWED data, so the enumerate position would otherwise drift.
    return f"{_shot_round_id(shot)}:{shot.get('hole')}:{shot.get('_globalIndex', index)}"


def _shot_round_id(shot: dict[str, Any]) -> str:
    return str(shot.get("roundId") or shot.get("scorecardId"))


def _shot_distance(shot: dict[str, Any]) -> Any:
    return shot.get("distance") if shot.get("distance") is not None else shot.get("meters")


def _shot_surface(shot: dict[str, Any]) -> Any:
    return shot.get("surface") if shot.get("surface") is not None else shot.get("endLie")


def _shot_club(shot: dict[str, Any]) -> Any:
    return shot.get("club") or shot.get("clubName")


def _parse_ref(source_ref: str) -> tuple[RefType, list[str]]:
    parts = [part for part in str(source_ref).split(":") if part != ""]
    if len(parts) == 1:
        return "round", parts
    if len(parts) == 2:
        return "hole", parts
    if len(parts) == 3:
        return "shot", parts
    return "unknown", parts


def _source_refs(row: dict[str, Any]) -> list[str]:
    provenance = row.get("provenance")
    if not isinstance(provenance, dict):
        return []
    refs = provenance.get("sourceRefs")
    if not isinstance(refs, list):
        return []
    return [str(ref).strip() for ref in refs if str(ref).strip()]


def _source_ref_index(rows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    refs: list[str] = []
    for row in rows:
        for ref in _source_refs(row):
            if ref in seen:
                continue
            seen.add(ref)
            refs.append(ref)
    return refs


def _round_aliases(data: HistoryData) -> dict[str, dict[str, Any]]:
    aliases: dict[str, dict[str, Any]] = {}
    for row in data.rounds:
        row_id = _round_id(row)
        aliases[row_id] = row
        for item in row.get("ids") or []:
            aliases[str(item)] = row
        for source_ref in _source_refs(row):
            aliases[source_ref] = row
    return aliases


def _shot_aliases(data: HistoryData) -> dict[str, tuple[int, dict[str, Any]]]:
    aliases: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, shot in enumerate(data.shots):
        aliases[_shot_ref(shot, index)] = (index, shot)
        for source_ref in _source_refs(shot):
            aliases[source_ref] = (index, shot)
    return aliases


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
        "sourceRefs": _source_ref_index([*data.rounds, *data.shots]),
    }


def resolve_history_ref(
    data: HistoryData,
    source_ref: str,
    *,
    annotations_root: Path | str | None = None,
    reports_root: Path | str | None = None,
    weather_root: Path | str | None = None,
    decision_audit_root: Path | str | None = None,
) -> dict[str, Any]:
    ref = str(source_ref)
    ref_type, parts = _parse_ref(ref)
    rounds_by_id = _round_aliases(data)
    shots_by_ref = _shot_aliases(data)

    if ref in rounds_by_id:
        return _attach_evidence(_round_detail(data, rounds_by_id[ref], ref), annotations_root, reports_root, weather_root, decision_audit_root)
    if ref in shots_by_ref:
        index, shot = shots_by_ref[ref]
        row = rounds_by_id.get(_shot_round_id(shot))
        hole = _find_hole(row, str(shot.get("hole") or "")) if row else None
        if row:
            return _attach_evidence(_shot_detail(row, hole, shot, index, ref), annotations_root, reports_root, weather_root, decision_audit_root)

    if ref_type == "round" and parts:
        row = rounds_by_id.get(parts[0])
        if row:
            return _attach_evidence(_round_detail(data, row, ref), annotations_root, reports_root, weather_root, decision_audit_root)
    elif ref_type == "hole" and len(parts) == 2:
        row = rounds_by_id.get(parts[0])
        hole = _find_hole(row, parts[1]) if row else None
        if row and hole:
            return _attach_evidence(_hole_detail(data, row, hole, ref), annotations_root, reports_root, weather_root, decision_audit_root)
    elif ref_type == "shot" and len(parts) == 3:
        item = shots_by_ref.get(ref)
        row = rounds_by_id.get(parts[0])
        hole = _find_hole(row, parts[1]) if row else None
        if item and row:
            index, shot = item
            return _attach_evidence(_shot_detail(row, hole, shot, index, ref), annotations_root, reports_root, weather_root, decision_audit_root)

    return _attach_evidence(_missing_detail(ref, ref_type), annotations_root, reports_root, weather_root, decision_audit_root)


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
        "globalId": _round_global_id(row),
        "courseId": row.get("courseId"),
        "frontNineGlobalCourseId": row.get("frontNineGlobalCourseId"),
        "backNineGlobalCourseId": row.get("backNineGlobalCourseId"),
    }


def _hole_summary(row: dict[str, Any], hole: dict[str, Any]) -> dict[str, Any]:
    par = hole.get("par")
    score = hole.get("strokes")
    hole_number = int(hole.get("number") or 0)
    geometry_target = _hole_geometry_target(row, hole_number)
    if par is None:
        par = _par_from_string(str(row.get("holePars") or ""), hole_number)
    return {
        "number": hole.get("number"),
        "par": par,
        "strokes": score,
        "toPar": int(score) - int(par) if score is not None and par is not None else None,
        "putts": hole.get("putts"),
        "gir": hole.get("gir"),
        "fairway": hole.get("fairway"),
        "globalId": geometry_target.get("globalId"),
        "localHole": geometry_target.get("localHole"),
    }


def _shot_summary(shot: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "ref": _shot_ref(shot, index),
        "roundId": _shot_round_id(shot),
        "hole": shot.get("hole"),
        "club": _shot_club(shot),
        "distance": _shot_distance(shot),
        "surface": _shot_surface(shot),
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
        if _shot_round_id(shot) == round_ref
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
        source_fields=_pick(
            row,
            [
                "id",
                "ids",
                "date",
                "course",
                "courseKey",
                "courseId",
                "globalId",
                "frontNineGlobalCourseId",
                "backNineGlobalCourseId",
                "strokes",
                "par",
                "holesCompleted",
                "hasShots",
                "provenance",
            ],
        ),
    )


def _hole_detail(data: HistoryData, row: dict[str, Any], hole: dict[str, Any], ref: str) -> dict[str, Any]:
    round_ref = _round_id(row)
    hole_number = int(hole.get("number"))
    shot_refs = [
        _shot_ref(shot, index)
        for index, shot in enumerate(data.shots)
        if _shot_round_id(shot) == round_ref and int(shot.get("hole") or 0) == hole_number
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
        source_fields={**_pick(hole, ["number", "strokes", "par", "putts", "gir", "fairway"]), **_hole_geometry_target(row, hole_number)},
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
    source_fields = _pick(
        shot,
        ["roundId", "scorecardId", "hole", "club", "clubName", "distance", "meters", "surface", "endLie", "provenance"],
    )
    source_fields.setdefault("roundId", _shot_round_id(shot))
    source_fields.setdefault("club", _shot_club(shot))
    source_fields.setdefault("distance", _shot_distance(shot))
    source_fields.setdefault("surface", _shot_surface(shot))
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
        "annotations": [],
        "corrections": [],
        "reports": [],
        "weatherSnapshots": [],
        "decisionAudits": [],
        "geometryEvidence": [],
    }


def _annotation_target_candidates(detail: dict[str, Any]) -> tuple[str | None, list[str]]:
    ref_type = detail.get("refType")
    candidates: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    add(detail.get("ref"))
    if ref_type == "round":
        row = detail.get("round") if isinstance(detail.get("round"), dict) else {}
        add(row.get("id"))
        return "round", candidates
    if ref_type == "hole":
        related = detail.get("relatedRefs") if isinstance(detail.get("relatedRefs"), dict) else {}
        for ref in related.get("holeRefs") or []:
            add(ref)
        row = detail.get("round") if isinstance(detail.get("round"), dict) else {}
        hole = detail.get("hole") if isinstance(detail.get("hole"), dict) else {}
        if row.get("id") and hole.get("number"):
            add(f"{row.get('id')}:{hole.get('number')}")
        return "hole", candidates
    if ref_type == "shot":
        shot = detail.get("shot") if isinstance(detail.get("shot"), dict) else {}
        add(shot.get("ref"))
        related = detail.get("relatedRefs") if isinstance(detail.get("relatedRefs"), dict) else {}
        for ref in related.get("shotRefs") or []:
            add(ref)
        return "shot", candidates
    return None, candidates


def _attach_annotations(detail: dict[str, Any], annotations_root: Path | str | None) -> dict[str, Any]:
    target_type, target_ids = _annotation_target_candidates(detail)
    if not target_type or not target_ids:
        return detail
    target_set = set(target_ids)
    annotations = [
        record
        for record in list_annotations(root=annotations_root)
        if record.get("targetType") == target_type and str(record.get("targetId") or "") in target_set
    ]
    detail["annotations"] = annotations
    detail["corrections"] = [record for record in annotations if record.get("kind") in CORRECTION_KINDS]
    return detail


def _attach_evidence(
    detail: dict[str, Any],
    annotations_root: Path | str | None,
    reports_root: Path | str | None,
    weather_root: Path | str | None,
    decision_audit_root: Path | str | None,
) -> dict[str, Any]:
    detail = _attach_annotations(detail, annotations_root)
    refs = set(_detail_ref_set(detail))
    detail["reports"] = _matching_reports(refs, reports_root)
    detail["weatherSnapshots"] = _matching_weather_snapshots(detail, weather_root)
    detail["decisionAudits"] = _matching_decision_audits(refs, decision_audit_root)
    detail["geometryEvidence"] = _geometry_evidence(detail)
    return detail


def _detail_ref_set(detail: dict[str, Any]) -> list[str]:
    refs: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in refs:
            refs.append(text)

    add(detail.get("ref"))
    related = detail.get("relatedRefs") if isinstance(detail.get("relatedRefs"), dict) else {}
    for key in ("roundRefs", "holeRefs", "shotRefs"):
        for ref in related.get(key) or []:
            add(ref)
    row = detail.get("round") if isinstance(detail.get("round"), dict) else {}
    add(row.get("id"))
    shot = detail.get("shot") if isinstance(detail.get("shot"), dict) else {}
    add(shot.get("ref"))
    return refs


def _record_refs(record: dict[str, Any]) -> list[str]:
    refs: list[str] = []

    def extend(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                text = str(item or "").strip()
                if text and text not in refs:
                    refs.append(text)

    extend(record.get("sourceRefs"))
    extend(record.get("evidenceRefs"))
    extend(record.get("actualShotRefs"))
    report = record.get("report") if isinstance(record.get("report"), dict) else {}
    extend(report.get("sourceRefs"))
    extend(report.get("evidenceRefs"))
    for fact in report.get("factsUsed") or []:
        if isinstance(fact, dict):
            extend(fact.get("sourceRefs"))
            extend(fact.get("refs"))
    return refs


def _matching_reports(refs: set[str], reports_root: Path | str | None) -> list[dict[str, Any]]:
    if not refs:
        return []
    rows: list[dict[str, Any]] = []
    for record in list_report_records(root=reports_root):
        report = record.get("report") if isinstance(record.get("report"), dict) else {}
        subject_id = str(record.get("subjectId") or "")
        record_refs = set(_record_refs(record))
        if subject_id not in refs and not record_refs.intersection(refs):
            continue
        unsupported = report.get("unsupportedClaims") if isinstance(report.get("unsupportedClaims"), list) else []
        facts = report.get("factsUsed") if isinstance(report.get("factsUsed"), list) else []
        missing = report.get("missingData") if isinstance(report.get("missingData"), list) else []
        rows.append(
            {
                "id": record.get("id"),
                "storedAt": record.get("storedAt"),
                "kind": record.get("kind"),
                "subjectId": subject_id,
                "provider": report.get("provider"),
                "model": report.get("model"),
                "confidence": report.get("confidence"),
                "sourceRefs": sorted(record_refs),
                "factsUsedCount": len(facts),
                "missingDataCount": len(missing),
                "unsupportedClaimCount": len(unsupported),
            }
        )
    return rows


def _matching_weather_snapshots(detail: dict[str, Any], weather_root: Path | str | None) -> list[dict[str, Any]]:
    round_id = None
    hole_number = None
    round_row = detail.get("round") if isinstance(detail.get("round"), dict) else {}
    hole_row = detail.get("hole") if isinstance(detail.get("hole"), dict) else {}
    if round_row.get("id"):
        round_id = str(round_row["id"])
    if hole_row.get("number") is not None:
        try:
            hole_number = int(hole_row["number"])
        except (TypeError, ValueError):
            hole_number = None
    rows: list[dict[str, Any]] = []
    for snapshot in list_weather_snapshots(root=weather_root):
        if round_id and str(snapshot.get("roundId") or "") != round_id:
            continue
        if detail.get("refType") in {"hole", "shot"} and hole_number is not None and snapshot.get("hole") not in {hole_number, None}:
            continue
        rows.append(
            {
                "state": snapshot.get("state"),
                "source": snapshot.get("source"),
                "roundId": snapshot.get("roundId"),
                "hole": snapshot.get("hole"),
                "capturedAt": snapshot.get("capturedAt"),
                "windSpeedMps": snapshot.get("windSpeedMps"),
                "windDirectionDeg": snapshot.get("windDirectionDeg"),
                "temperatureC": snapshot.get("temperatureC"),
                "precipitationMm": snapshot.get("precipitationMm"),
                "confidence": snapshot.get("confidence"),
            }
        )
    return rows


def _matching_decision_audits(refs: set[str], decision_audit_root: Path | str | None) -> list[dict[str, Any]]:
    if not refs:
        return []
    rows: list[dict[str, Any]] = []
    for record in list_decision_audits(root=decision_audit_root):
        record_refs = set(_record_refs(record))
        source_ref = str(record.get("sourceRef") or "")
        decision_id = str(record.get("decisionId") or "")
        if source_ref not in refs and decision_id not in refs and not record_refs.intersection(refs):
            continue
        rows.append(
            {
                "id": record.get("id"),
                "storedAt": record.get("storedAt"),
                "decisionId": record.get("decisionId"),
                "sourceRef": record.get("sourceRef"),
                "selectedOptionId": record.get("selectedOptionId"),
                "actualOptionId": record.get("actualOptionId"),
                "actualShotRefs": record.get("actualShotRefs") or [],
                "evidenceRefs": record.get("evidenceRefs") or [],
                "classification": record.get("classification"),
            }
        )
    return rows


def _geometry_evidence(detail: dict[str, Any]) -> list[dict[str, Any]]:
    geometry_rows: list[dict[str, Any]] = []
    targets: list[tuple[int, int, str]] = []

    def add_target(global_id: Any, local_hole: Any, source_ref: str) -> None:
        try:
            global_id_int = int(global_id)
            local_hole_int = int(local_hole)
        except (TypeError, ValueError):
            return
        if global_id_int <= 0 or local_hole_int <= 0:
            return
        target = (global_id_int, local_hole_int, source_ref)
        if target not in targets:
            targets.append(target)

    if detail.get("refType") in {"hole", "shot"}:
        hole = detail.get("hole") if isinstance(detail.get("hole"), dict) else {}
        add_target(hole.get("globalId"), hole.get("localHole"), str(detail.get("ref") or ""))
    elif detail.get("refType") == "round":
        round_row = detail.get("round") if isinstance(detail.get("round"), dict) else {}
        for ref in (detail.get("relatedRefs") or {}).get("holeRefs") or []:
            try:
                hole_number = int(str(ref).split(":")[1])
            except (IndexError, ValueError):
                continue
            target = _hole_geometry_target(round_row, hole_number)
            add_target(target.get("globalId"), target.get("localHole"), str(ref))

    for global_id, local_hole, source_ref in targets[:18]:
        coverage = geometry_coverage_for_hole(global_id, local_hole)
        geometry_rows.append(
            {
                "sourceRef": source_ref,
                "globalId": global_id,
                "localHole": local_hole,
                "coverage": coverage.get("coverage"),
                "hasHazards": coverage.get("hasHazards"),
                "hasMeshes": coverage.get("hasMeshes"),
                "evidence": coverage.get("evidence") or [],
                "missingData": coverage.get("missingData") or [],
            }
        )
    return geometry_rows


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


def _int_field(row: dict[str, Any], key: str) -> int | None:
    try:
        value = row.get(key)
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _round_global_id(row: dict[str, Any]) -> int | None:
    for key in ("globalId", "courseId", "frontNineGlobalCourseId", "backNineGlobalCourseId"):
        value = _int_field(row, key)
        if value is not None:
            return value
    return None


def _hole_geometry_target(row: dict[str, Any], hole_number: int) -> dict[str, int | None]:
    if hole_number <= 0:
        return {"globalId": _round_global_id(row), "localHole": None}
    if hole_number <= 9:
        global_id = _int_field(row, "frontNineGlobalCourseId") or _int_field(row, "globalId") or _int_field(row, "courseId")
        return {"globalId": global_id, "localHole": hole_number}
    back_global_id = _int_field(row, "backNineGlobalCourseId")
    if back_global_id is not None:
        return {"globalId": back_global_id, "localHole": hole_number - 9}
    return {
        "globalId": _int_field(row, "globalId") or _int_field(row, "courseId") or _int_field(row, "frontNineGlobalCourseId"),
        "localHole": hole_number,
    }


def _pick(row: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if key in row}
