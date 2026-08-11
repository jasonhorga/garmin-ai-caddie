from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from typing import Any

from ai_caddie.core.data import ROOT, atomic_write_json, safe_read_json, semicircle_to_deg
from ai_caddie.history.history import (
    HistoryData,
    canonical_course_name,
    course_key,
    merge_same_day_halves,
    millionths_to_deg,
    normalize_scorecard_hole,
)

from .base import ConnectorState, SnapshotManifest
from .redaction import sanitize_secret_text

SYNC_DIR = Path("data") / "sync"
SNAPSHOT_DIR = Path("data") / "snapshots"
STATUS_FILE = SYNC_DIR / "garmin_cn_status.json"
GEOMETRY_ASSET_DIRS = (
    Path("output") / "prodgeometry_hazards",
    Path("output") / "prodgeometry",
)
GEOMETRY_HAZARD_DIR = Path("output") / "prodgeometry_hazards"
GEOMETRY_MESH_DIR = Path("output") / "prodgeometry"
SOURCE_CONNECTOR = "garmin_cn_web_session"
ACCEPTANCE_SCHEMA = "ai-caddie-private-snapshot-acceptance-v1"
ACCEPTANCE_CREDENTIAL_TERMS = (
    "cookie",
    "csrf",
    "connect-csrf-token",
    "access_token",
    "refresh_token",
    "authorization",
    "password=",
    "secret=",
    ".garmin_tokens",
    ".env",
)
ACCEPTANCE_PRIVATE_PATH_RE = re.compile(r"(?i)(/(?:home|users)/[^\"'\s,;}]+|[a-z]:\\users\\[^\"'\s,;}]+)")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _json_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(item for item in path.glob("*.json") if item.is_file())


def _json_files_recursive(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(item for item in path.rglob("*.json") if item.is_file())


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _coerce_id(value: Any) -> Any:
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def _string_id(value: Any) -> str:
    return str(value)


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _provenance(
    *,
    snapshot_id: str,
    normalized_at: str,
    source_record_type: str,
    source_record_id: Any,
    source_file: str,
    field_refs: dict[str, str],
    source_record_ids: list[Any] | None = None,
    source_files: list[str] | None = None,
    source_refs: list[str] | None = None,
    parent_record_id: Any | None = None,
    confidence: str = "high",
    status: str = "normalized",
) -> dict[str, Any]:
    record_ids = _unique_strings(source_record_ids or [source_record_id])
    files = _unique_strings(source_files or [source_file])
    record_id = _string_id(source_record_id)
    if source_refs is None:
        if source_record_type == "shot" and parent_record_id is not None:
            source_refs = [f"{SOURCE_CONNECTOR}:{snapshot_id}:shot:{parent_record_id}:{record_id}"]
        else:
            source_refs = [f"{SOURCE_CONNECTOR}:{snapshot_id}:{source_record_type}:{record_id}"]
    payload: dict[str, Any] = {
        "sourceConnector": SOURCE_CONNECTOR,
        "snapshotId": snapshot_id,
        "sourceRecordType": source_record_type,
        "sourceRecordId": record_id,
        "sourceRecordIds": record_ids,
        "sourceFile": files[0] if files else source_file,
        "sourceFiles": files,
        "sourceRefs": _unique_strings(source_refs),
        "fieldRefs": dict(field_refs),
        "status": status,
        "confidence": confidence,
        "normalizedAt": normalized_at,
    }
    if parent_record_id is not None:
        payload["parentRecordId"] = _string_id(parent_record_id)
    return payload


def _par_from_hole_pars(hole_pars: str, hole_number: int) -> int | None:
    if 1 <= hole_number <= len(hole_pars):
        try:
            return int(hole_pars[hole_number - 1])
        except ValueError:
            return None
    return None


def _played_holes(scorecard: dict[str, Any], hole_pars: str) -> list[dict[str, Any]]:
    holes: list[dict[str, Any]] = []
    for index, hole in enumerate(scorecard.get("holes") or [], start=1):
        if hole.get("strokes") is None:
            continue
        number = int(hole.get("number") or index)
        par = hole.get("par")
        if not isinstance(par, int):
            par = _par_from_hole_pars(hole_pars, number)
        normalized = normalize_scorecard_hole(hole, number=number, par=par)
        holes.append(
            {
                "number": number,
                "strokes": normalized.get("strokes"),
                "par": normalized.get("par"),
                "putts": normalized.get("putts"),
                "gir": normalized.get("gir"),
                "fairway": normalized.get("fairway"),
            }
        )
    return holes


def _shot_payload_has_usable_rows(payload: Any) -> bool:
    if not isinstance(payload, dict) or payload.get("_no_data"):
        return False
    for hole in payload.get("holeShots", []) or []:
        if isinstance(hole, dict) and hole.get("shots"):
            return True
    return False


def _shot_file_status(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    try:
        payload = _read_json(path)
    except Exception:
        return False, "no_data"
    if not isinstance(payload, dict) or payload.get("_no_data"):
        return False, "no_data"
    if _shot_payload_has_usable_rows(payload):
        return True, "ready"
    return False, "pin_only"


def _shot_file_ready(path: Path) -> bool:
    ready, _status = _shot_file_status(path)
    return ready


def _normalize_scorecard(
    path: Path,
    *,
    root: Path,
    snapshot_id: str,
    normalized_at: str,
) -> dict[str, Any] | None:
    try:
        raw = _read_json(path)
        detail = raw["scorecardDetails"][0]
        scorecard = detail["scorecard"]
    except Exception:
        return None

    scorecard_id = _coerce_id(scorecard.get("id") or path.stem)
    snapshot = (raw.get("courseSnapshots") or [{}])[0] or {}
    stats = detail.get("scorecardStats", {}).get("round", {}) or {}
    course_name = str(snapshot.get("name") or "Unknown course")
    canonical = canonical_course_name(course_name)
    hole_pars = snapshot.get("holePars") or ""
    if isinstance(hole_pars, list):
        hole_pars = "".join(str(item) for item in hole_pars)
    hole_pars = str(hole_pars)
    holes = _played_holes(scorecard, hole_pars)
    par_values = [hole.get("par") for hole in holes if isinstance(hole.get("par"), int)]
    shot_path = root / "data" / "shots" / f"{scorecard_id}.json"
    has_shots, shot_status = _shot_file_status(shot_path)
    source_file = _relative(path, root)
    return {
        "id": scorecard_id,
        "ids": [scorecard_id],
        "date": scorecard.get("formattedStartTime") or scorecard.get("startTime") or "",
        "strokes": scorecard.get("strokes"),
        "holesCompleted": scorecard.get("holesCompleted"),
        "course": course_name,
        "courseCanonical": canonical,
        "courseKey": course_key(canonical),
        "courseId": scorecard.get("courseGlobalId"),
        "globalId": scorecard.get("courseGlobalId"),
        "frontNineGlobalCourseId": scorecard.get("frontNineGlobalCourseId") or scorecard.get("courseGlobalId"),
        "backNineGlobalCourseId": scorecard.get("backNineGlobalCourseId"),
        "snapshotId": scorecard.get("courseSnapshotId"),
        "lat": millionths_to_deg(snapshot.get("lat")),
        "lon": millionths_to_deg(snapshot.get("lon")),
        "city": snapshot.get("city"),
        "country": snapshot.get("country"),
        "par": sum(par_values) if par_values else snapshot.get("roundPar"),
        "holePars": hole_pars,
        "holes": holes,
        "fh": stats.get("fairwaysHit"),
        "fl": stats.get("fairwaysLeft"),
        "fr": stats.get("fairwaysRight"),
        "frec": stats.get("fairwaysRecorded"),
        "gir": stats.get("greensInRegulation"),
        "grec": stats.get("greensRecorded"),
        "putts": stats.get("putts"),
        "ub": stats.get("holesUnderPar"),
        "pa": stats.get("holesPar"),
        "bo": stats.get("holesBogey"),
        "ob": stats.get("holesOverBogey"),
        "bi": stats.get("holesBirdie"),
        "ea": stats.get("holesEagle"),
        "rating": scorecard.get("teeBoxRating"),
        "slope": scorecard.get("teeBoxSlope"),
        "hasShotFile": shot_path.exists(),
        "hasShots": has_shots,
        "shotStatus": shot_status,
        "merged": False,
        "sourceFile": source_file,
        "provenance": _provenance(
            snapshot_id=snapshot_id,
            normalized_at=normalized_at,
            source_record_type="scorecard",
            source_record_id=scorecard_id,
            source_file=source_file,
            field_refs={
                "id": "scorecardDetails[0].scorecard.id",
                "date": "scorecardDetails[0].scorecard.formattedStartTime",
                "strokes": "scorecardDetails[0].scorecard.strokes",
                "holes": "scorecardDetails[0].scorecard.holes",
                "holesCompleted": "scorecardDetails[0].scorecard.holesCompleted",
                "courseGlobalId": "scorecardDetails[0].scorecard.courseGlobalId",
                "courseSnapshot": "courseSnapshots[0]",
                "roundStats": "scorecardDetails[0].scorecardStats.round",
            },
        ),
    }


def _club_lookup(shot_payload: dict[str, Any]) -> dict[Any, str]:
    lookup: dict[Any, str] = {}
    for club in shot_payload.get("clubDetails", []) or []:
        club_id = club.get("clubId") or club.get("id")
        if club_id is None:
            continue
        lookup[club_id] = str(club.get("name") or club.get("clubName") or club_id)
    return lookup


def _loc_to_wgs84(loc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(loc, dict):
        return None
    lat = semicircle_to_deg(loc.get("lat"))
    lon = semicircle_to_deg(loc.get("lon"))
    if lat is None or lon is None:
        return None
    return {"lat": lat, "lon": lon, "lie": loc.get("lie"), "lieSource": loc.get("lieSource")}


def _shot_hole_ref(round_row: dict[str, Any], hole: int) -> tuple[Any, int]:
    if hole <= 9:
        return (
            round_row.get("frontNineGlobalCourseId") or round_row.get("globalId") or round_row.get("courseId"),
            hole,
        )
    if round_row.get("backNineGlobalCourseId"):
        return round_row.get("backNineGlobalCourseId"), hole - 9
    return round_row.get("globalId") or round_row.get("courseId"), hole


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _geometry_hazard_path(root: Path, global_id: int, local_hole: int) -> Path:
    return root / GEOMETRY_HAZARD_DIR / f"gid{global_id}_h{local_hole:02d}_hazards.json"


def _geometry_mesh_path(root: Path, global_id: int, local_hole: int) -> Path:
    return root / GEOMETRY_MESH_DIR / f"gid{global_id}_h{local_hole:02d}_meshes.json"


def _geometry_status(root: Path, global_id: int, local_hole: int) -> tuple[str, bool, bool, str | None, str | None]:
    hazard = _geometry_hazard_path(root, global_id, local_hole)
    mesh = _geometry_mesh_path(root, global_id, local_hole)
    has_hazards = hazard.exists()
    has_meshes = mesh.exists()
    if has_hazards and has_meshes:
        status = "ready"
    elif has_hazards or has_meshes:
        status = "partial"
    else:
        status = "missing"
    return (
        status,
        has_hazards,
        has_meshes,
        _relative(hazard, root) if has_hazards else None,
        _relative(mesh, root) if has_meshes else None,
    )


def _scorecard_hole_numbers(scorecard: dict[str, Any], hole_pars: str) -> list[int]:
    holes = scorecard.get("holes") if isinstance(scorecard.get("holes"), list) else []
    numbers: list[int] = []
    for index, hole in enumerate(holes, start=1):
        if not isinstance(hole, dict):
            continue
        number = _safe_int(hole.get("number")) or index
        if hole.get("strokes") is not None or hole.get("par") is not None or hole.get("number") is not None:
            numbers.append(number)
    if numbers:
        return sorted(set(numbers))
    completed = _safe_int(scorecard.get("holesCompleted"))
    if completed:
        return list(range(1, completed + 1))
    if hole_pars:
        return list(range(1, len(hole_pars) + 1))
    return []


def _scorecard_geometry_ref(scorecard: dict[str, Any], hole_number: int) -> tuple[int | None, int | None]:
    course_global_id = _safe_int(scorecard.get("courseGlobalId") or scorecard.get("globalId") or scorecard.get("courseId"))
    if hole_number <= 9:
        return _safe_int(scorecard.get("frontNineGlobalCourseId")) or course_global_id, hole_number
    back_global_id = _safe_int(scorecard.get("backNineGlobalCourseId"))
    if back_global_id is not None:
        return back_global_id, hole_number - 9
    return course_global_id, hole_number


def _dependency_record(
    *,
    root: Path,
    global_id: int,
    local_hole: int,
    source_ref: str,
    profile_id_available: bool,
) -> dict[str, Any]:
    status, has_hazards, has_meshes, hazard_ref, mesh_ref = _geometry_status(root, global_id, local_hole)
    row: dict[str, Any] = {
        "globalId": global_id,
        "localHole": local_hole,
        "status": status,
        "hasHazards": has_hazards,
        "hasMeshes": has_meshes,
        "sourceRefs": [source_ref],
        "profileIdAvailable": profile_id_available,
    }
    if hazard_ref:
        row["hazards"] = hazard_ref
    if mesh_ref:
        row["meshes"] = mesh_ref
    return row


def discover_geometry_dependencies(*, root: Path = ROOT, data_dir: Path | None = None) -> list[dict[str, Any]]:
    # ``data_dir`` is the per-data-source partition (scorecards/shots/summary). It
    # defaults to ``root/data`` (owner, byte-for-byte). A family member passes their
    # partition (``root/data/players/<id>``) so geometry deps are derived from THEIR
    # scorecards; the geometry assets + the relative source refs stay anchored at the
    # shared ``root`` (course geometry is public).
    scorecards_root = data_dir if data_dir is not None else (root / "data")
    dependencies: dict[tuple[int, int], dict[str, Any]] = {}
    for path in _json_files(scorecards_root / "scorecards"):
        try:
            raw = _read_json(path)
            detail = raw["scorecardDetails"][0]
            scorecard = detail["scorecard"]
        except Exception:
            continue
        snapshot = (raw.get("courseSnapshots") or [{}])[0] or {}
        hole_pars = snapshot.get("holePars") or ""
        if isinstance(hole_pars, list):
            hole_pars = "".join(str(item) for item in hole_pars)
        source_ref = _relative(path, root)
        profile_id_available = bool(scorecard.get("playerProfileId"))
        for hole_number in _scorecard_hole_numbers(scorecard, str(hole_pars)):
            global_id, local_hole = _scorecard_geometry_ref(scorecard, hole_number)
            if global_id is None or local_hole is None:
                continue
            key = (global_id, local_hole)
            if key not in dependencies:
                dependencies[key] = _dependency_record(
                    root=root,
                    global_id=global_id,
                    local_hole=local_hole,
                    source_ref=source_ref,
                    profile_id_available=profile_id_available,
                )
                continue
            row = dependencies[key]
            if source_ref not in row["sourceRefs"]:
                row["sourceRefs"].append(source_ref)
            row["profileIdAvailable"] = bool(row.get("profileIdAvailable") or profile_id_available)
    return [dependencies[key] for key in sorted(dependencies)]


def discover_played_geometry_dependencies(
    data: HistoryData,
    *,
    root: Path = ROOT,
    limit: int | None = None,
    include_ready: bool = False,
) -> list[dict[str, Any]]:
    """Rank geometry dependencies by actual played shot volume.

    Scorecard dependencies tell us every recorded hole. Played dependencies tell us
    which CourseView holes are blocking shot-map and route-evidence value first.
    """
    pairs: dict[tuple[int, int], dict[str, Any]] = {}
    for shot in data.shots:
        global_id = _safe_int(shot.get("globalId"))
        local_hole = _safe_int(shot.get("localHole"))
        if global_id is None or local_hole is None:
            continue
        key = (global_id, local_hole)
        row = pairs.setdefault(
            key,
            {
                "globalId": global_id,
                "localHole": local_hole,
                "shotCount": 0,
                "courseCounts": {},
                "sourceRefs": [],
            },
        )
        row["shotCount"] += 1
        course = str(shot.get("course") or "Unknown course")
        row["courseCounts"][course] = int(row["courseCounts"].get(course, 0)) + 1
        source_ref = str(shot.get("scorecardId") or shot.get("roundId") or shot.get("id") or "").strip()
        if source_ref and source_ref not in row["sourceRefs"]:
            row["sourceRefs"].append(source_ref)

    profile_id_available = geometry_player_profile_id(root=root) is not None
    rows: list[dict[str, Any]] = []
    for (global_id, local_hole), pair in pairs.items():
        status, has_hazards, has_meshes, hazard_ref, mesh_ref = _geometry_status(root, global_id, local_hole)
        if status == "ready" and not include_ready:
            continue
        course_counts = pair.get("courseCounts") or {}
        course = "Unknown course"
        if course_counts:
            course = sorted(course_counts.items(), key=lambda item: (-int(item[1]), item[0]))[0][0]
        row: dict[str, Any] = {
            "globalId": global_id,
            "localHole": local_hole,
            "status": status,
            "hasHazards": has_hazards,
            "hasMeshes": has_meshes,
            "course": course,
            "shotCount": int(pair["shotCount"]),
            "sourceRefs": pair["sourceRefs"][:20],
            "profileIdAvailable": profile_id_available,
        }
        if hazard_ref:
            row["hazards"] = hazard_ref
        if mesh_ref:
            row["meshes"] = mesh_ref
        rows.append(row)

    status_priority = {"partial": 0, "missing": 1, "ready": 2}
    rows.sort(
        key=lambda row: (
            -int(row.get("shotCount") or 0),
            status_priority.get(str(row.get("status")), 9),
            int(row.get("globalId") or 0),
            int(row.get("localHole") or 0),
        )
    )
    if limit is not None:
        rows = rows[: max(0, int(limit))]
    return rows


def ensure_geometry_dependencies(dependencies: list[dict[str, object]], *, root: Path = ROOT) -> dict[str, int]:
    """Idempotently download any MISSING per-hole prodgeometry. Skips rows already 'ready'."""
    from ai_caddie.geometry.geometry_sync import ensure_prodgeometry
    profile_id = geometry_player_profile_id(root=root)
    summary = {"attempted": 0, "cached": 0, "downloaded": 0, "failed": 0, "skipped": 0}
    for row in dependencies:
        if row.get("status") == "ready":
            summary["cached"] += 1
            continue
        global_id, local_hole = row.get("globalId"), row.get("localHole")
        if profile_id is None or global_id is None or local_hole is None:
            summary["skipped"] += 1
            continue
        summary["attempted"] += 1
        result = ensure_prodgeometry(int(global_id), int(local_hole), profile_id=profile_id, force=False)
        status = str(result.get("status") or "failed")
        summary["downloaded" if status == "downloaded" else "cached" if status == "cached" else "failed"] += 1
    return summary


def geometry_player_profile_id(*, root: Path = ROOT) -> str | None:
    for path in _json_files(root / "data" / "scorecards"):
        try:
            raw = _read_json(path)
            value = raw["scorecardDetails"][0]["scorecard"].get("playerProfileId")
        except Exception:
            continue
        if value:
            return str(value)
    return None


def _normalize_shot_file(
    path: Path,
    *,
    root: Path,
    round_row: dict[str, Any],
    snapshot_id: str,
    normalized_at: str,
) -> list[dict[str, Any]]:
    try:
        payload = _read_json(path)
    except Exception:
        return []
    if not isinstance(payload, dict) or payload.get("_no_data"):
        return []

    clubs = _club_lookup(payload)
    scorecard_id = round_row.get("id")
    source_file = _relative(path, root)
    rows: list[dict[str, Any]] = []
    for hole_data in payload.get("holeShots", []) or []:
        hole = int(hole_data.get("holeNumber") or 0)
        global_id, local_hole = _shot_hole_ref(round_row, hole)
        for shot in hole_data.get("shots", []) or []:
            club_id = shot.get("clubId")
            club = clubs.get(club_id) or str(club_id or "Unknown")
            end_loc = shot.get("endLoc") if isinstance(shot.get("endLoc"), dict) else {}
            shot_id = shot.get("id") or f"{scorecard_id}:{hole}:{shot.get('shotOrder') or len(rows) + 1}"
            rows.append(
                {
                    "id": shot.get("id"),
                    "roundId": scorecard_id,
                    "scorecardId": scorecard_id,
                    "date": str(round_row.get("date") or "")[:10],
                    "course": round_row.get("course"),
                    "courseCanonical": round_row.get("courseCanonical"),
                    "courseKey": round_row.get("courseKey"),
                    "hole": hole,
                    "globalId": global_id,
                    "localHole": local_hole,
                    "order": shot.get("shotOrder"),
                    "clubId": club_id,
                    "club": club,
                    "clubName": club,
                    "type": shot.get("shotType"),
                    "auto": shot.get("autoShotType"),
                    "distance": shot.get("meters"),
                    "meters": shot.get("meters"),
                    "start": _loc_to_wgs84(shot.get("startLoc")),
                    "end": _loc_to_wgs84(shot.get("endLoc")),
                    "surface": end_loc.get("lie"),
                    "endLie": end_loc.get("lie"),
                    "sourceFile": source_file,
                    "provenance": _provenance(
                        snapshot_id=snapshot_id,
                        normalized_at=normalized_at,
                        source_record_type="shot",
                        source_record_id=shot_id,
                        parent_record_id=scorecard_id,
                        source_file=source_file,
                        field_refs={
                            "holeNumber": "holeShots[].holeNumber",
                            "id": "holeShots[].shots[].id",
                            "shotOrder": "holeShots[].shots[].shotOrder",
                            "clubId": "holeShots[].shots[].clubId",
                            "meters": "holeShots[].shots[].meters",
                            "startLoc": "holeShots[].shots[].startLoc",
                            "endLoc": "holeShots[].shots[].endLoc",
                        },
                    ),
                }
            )
    return rows


def _merge_provenance_for_round(
    row: dict[str, Any],
    raw_rounds_by_id: dict[str, dict[str, Any]],
    *,
    snapshot_id: str,
    normalized_at: str,
) -> dict[str, Any]:
    if not row.get("merged"):
        return row
    ids = row.get("ids") if isinstance(row.get("ids"), list) else []
    source_provenance = [
        raw_rounds_by_id[str(item)].get("provenance")
        for item in ids
        if str(item) in raw_rounds_by_id and isinstance(raw_rounds_by_id[str(item)].get("provenance"), dict)
    ]
    if not source_provenance:
        return row
    merged = dict(row)
    source_files = _unique_strings(
        [
            file_name
            for provenance in source_provenance
            for file_name in provenance.get("sourceFiles", [])
        ]
    )
    source_refs = _unique_strings(
        [
            source_ref
            for provenance in source_provenance
            for source_ref in provenance.get("sourceRefs", [])
        ]
    )
    merged["provenance"] = _provenance(
        snapshot_id=snapshot_id,
        normalized_at=normalized_at,
        source_record_type="scorecard_merge",
        source_record_id=merged.get("id"),
        source_record_ids=ids,
        source_file=source_files[0] if source_files else str(merged.get("sourceFile") or ""),
        source_files=source_files,
        source_refs=source_refs,
        field_refs={
            "mergeRule": "same_day_two_9_hole_halves",
            "sourceRows": "rawRounds.ids",
        },
    )
    return merged


def _remap_shots_to_merged_rounds(shots: list[dict[str, Any]], rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aliases: dict[str, dict[str, Any]] = {}
    for row in rounds:
        row_id = row.get("id")
        ids = row.get("ids") if isinstance(row.get("ids"), list) else [row_id]
        if row.get("merged") and len(ids) >= 2:
            aliases[str(ids[0])] = {
                "roundId": row_id,
                "holeOffset": 0,
                "globalId": row.get("frontNineGlobalCourseId") or row.get("globalId") or row.get("courseId"),
            }
            aliases[str(ids[1])] = {
                "roundId": row_id,
                "holeOffset": 9,
                "globalId": row.get("backNineGlobalCourseId") or row.get("globalId") or row.get("courseId"),
            }
        elif row_id is not None:
            aliases[str(row_id)] = {"roundId": row_id, "holeOffset": 0, "globalId": None}

    remapped: list[dict[str, Any]] = []
    for shot in shots:
        row = dict(shot)
        raw_round_id = str(row.get("scorecardId") or row.get("roundId") or "")
        alias = aliases.get(raw_round_id)
        if alias:
            row["roundId"] = alias["roundId"]
            try:
                original_hole = int(row.get("hole") or 0)
            except (TypeError, ValueError):
                original_hole = 0
            if original_hole:
                row["hole"] = original_hole + int(alias["holeOffset"] or 0)
                row["localHole"] = original_hole
            if alias.get("globalId") is not None:
                row["globalId"] = alias["globalId"]
        remapped.append(row)
    return remapped


def build_snapshot_manifest(*, root: Path = ROOT, snapshot_id: str, data_dir: Path | None = None) -> SnapshotManifest:
    # ``data_dir`` defaults to ``root/data`` (owner, byte-for-byte). A member passes
    # their partition so the manifest counts THEIR scorecards/shots/summary while the
    # geometry assets stay anchored at the shared ``root`` (public course geometry).
    data_dir = data_dir if data_dir is not None else (root / "data")
    summary = data_dir / "summary.json"
    scorecards = _json_files(data_dir / "scorecards")
    shots = _json_files(data_dir / "shots")
    geometry_dependencies = discover_geometry_dependencies(root=root, data_dir=data_dir)
    files: list[str] = []
    if summary.exists():
        files.append(_relative(summary, root))
    files.extend(_relative(path, root) for path in scorecards)
    files.extend(_relative(path, root) for path in shots)
    for relative_dir in GEOMETRY_ASSET_DIRS:
        files.extend(_relative(path, root) for path in _json_files_recursive(root / relative_dir))
    return SnapshotManifest(
        snapshot_id=snapshot_id,
        scorecard_count=len(scorecards),
        shot_file_count=len(shots),
        summary_present=summary.exists(),
        files=files,
        geometry_dependencies=geometry_dependencies,
        geometry_dependency_count=len(geometry_dependencies),
        geometry_ready_count=sum(1 for row in geometry_dependencies if row.get("status") == "ready"),
        geometry_missing_count=sum(1 for row in geometry_dependencies if row.get("status") == "missing"),
    )


def write_snapshot_manifest(*, root: Path = ROOT, manifest: SnapshotManifest) -> Path:
    out_dir = root / SNAPSHOT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{manifest.snapshot_id}.json"
    payload = {
        "schema": "ai-caddie-raw-snapshot-v1",
        "snapshotId": manifest.snapshot_id,
        "createdAt": _utc_now(),
        "scorecardCount": manifest.scorecard_count,
        "shotFileCount": manifest.shot_file_count,
        "summaryPresent": manifest.summary_present,
        "files": manifest.files,
        "geometryDependencyCount": manifest.geometry_dependency_count,
        "geometryReadyCount": manifest.geometry_ready_count,
        "geometryMissingCount": manifest.geometry_missing_count,
        "geometryDependencies": manifest.geometry_dependencies,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def _snapshot_manifest_sort_key(path: Path) -> tuple[float, str]:
    try:
        payload = _read_json(path)
        created_at = payload.get("createdAt") if isinstance(payload, dict) else None
        if created_at:
            parsed = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            return (parsed.timestamp(), path.name)
    except Exception:
        pass
    try:
        return (path.stat().st_mtime, path.name)
    except OSError:
        return (0.0, path.name)


def read_latest_snapshot_manifest(*, root: Path = ROOT) -> dict[str, Any] | None:
    snapshot_root = root / SNAPSHOT_DIR
    if not snapshot_root.exists():
        return None
    for path in sorted(_json_files(snapshot_root), key=_snapshot_manifest_sort_key, reverse=True):
        try:
            payload = _read_json(path)
        except Exception:
            continue
        if isinstance(payload, dict) and payload.get("schema") == "ai-caddie-raw-snapshot-v1":
            return payload
    return None


def build_normalized_snapshot_payload(*, root: Path = ROOT, manifest: SnapshotManifest) -> dict[str, Any]:
    created_at = _utc_now()
    scorecard_paths = [root / file_name for file_name in manifest.files if file_name.startswith("data/scorecards/")]
    raw_rounds = [
        row
        for path in scorecard_paths
        for row in [
            _normalize_scorecard(
                path,
                root=root,
                snapshot_id=manifest.snapshot_id,
                normalized_at=created_at,
            )
        ]
        if row is not None
    ]
    raw_rounds.sort(key=lambda row: row.get("date") or "")
    rounds_by_id = {str(row.get("id")): row for row in raw_rounds}
    shots = [
        shot
        for file_name in manifest.files
        if file_name.startswith("data/shots/")
        for path in [root / file_name]
        for round_row in [rounds_by_id.get(path.stem)]
        if round_row is not None
        for shot in _normalize_shot_file(
            path,
            root=root,
            round_row=round_row,
            snapshot_id=manifest.snapshot_id,
            normalized_at=created_at,
        )
    ]
    rounds = [
        _merge_provenance_for_round(row, rounds_by_id, snapshot_id=manifest.snapshot_id, normalized_at=created_at)
        for row in merge_same_day_halves(raw_rounds)
    ]
    shots = _remap_shots_to_merged_rounds(shots, rounds)
    return {
        "schema": "ai-caddie-normalized-history-v1",
        "snapshotId": manifest.snapshot_id,
        "createdAt": created_at,
        "sourceFiles": manifest.files,
        "rawRounds": raw_rounds,
        "rounds": rounds,
        "shots": shots,
    }


def write_durable_snapshot(*, root: Path = ROOT, manifest: SnapshotManifest) -> Path:
    snapshot_dir = root / SNAPSHOT_DIR / manifest.snapshot_id
    raw_dir = snapshot_dir / "raw"
    for file_name in manifest.files:
        source = root / file_name
        if not source.exists() or not source.is_file():
            continue
        destination = raw_dir / file_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    normalized_path = snapshot_dir / "normalized" / "history.json"
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path.write_text(
        json.dumps(build_normalized_snapshot_payload(root=root, manifest=manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return normalized_path


def _snapshot_history_path(root: Path, snapshot_id: str) -> Path:
    return root / SNAPSHOT_DIR / snapshot_id / "normalized" / "history.json"


def _latest_snapshot_history_paths(root: Path) -> list[Path]:
    status = read_connector_status(root=root)
    paths: list[Path] = []
    if status and status.get("snapshotId"):
        paths.append(_snapshot_history_path(root, str(status["snapshotId"])))
    snapshot_root = root / SNAPSHOT_DIR
    if snapshot_root.exists():
        paths.extend(sorted(snapshot_root.glob("*/normalized/history.json"), reverse=True))
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def load_latest_snapshot_history(*, root: Path = ROOT) -> HistoryData | None:
    for path in _latest_snapshot_history_paths(root):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("schema") != "ai-caddie-normalized-history-v1":
            continue
        raw_rounds = payload.get("rawRounds") if isinstance(payload.get("rawRounds"), list) else []
        rounds = payload.get("rounds") if isinstance(payload.get("rounds"), list) else []
        shots = payload.get("shots") if isinstance(payload.get("shots"), list) else []
        if rounds:
            return HistoryData(raw_rounds=raw_rounds, rounds=rounds, shots=shots)
    return None


def _acceptance_check(label: str, state: str, detail: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"label": label, "state": state, "detail": detail, "evidence": evidence or {}}


def _manifest_files(manifest: dict[str, Any], prefix: str) -> list[str]:
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    return sorted(str(file_name) for file_name in files if str(file_name).startswith(prefix))


def _read_normalized_snapshot_payload(*, root: Path, snapshot_id: str) -> dict[str, Any] | None:
    path = _snapshot_history_path(root, snapshot_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _raw_snapshot_missing_files(*, root: Path, snapshot_id: str, files: list[str]) -> list[str]:
    raw_dir = root / SNAPSHOT_DIR / snapshot_id / "raw"
    return [file_name for file_name in files if not (raw_dir / file_name).is_file()]


def _scorecard_detail_counts(*, root: Path, scorecard_files: list[str]) -> tuple[int, int, list[str]]:
    valid = 0
    player_profile_ready = 0
    invalid: list[str] = []
    for file_name in scorecard_files:
        try:
            payload = _read_json(root / file_name)
            detail = payload["scorecardDetails"][0]
            scorecard = detail["scorecard"]
            if not isinstance(scorecard, dict) or scorecard.get("id") is None:
                raise ValueError("missing scorecard id")
        except Exception:
            invalid.append(file_name)
            continue
        valid += 1
        if scorecard.get("playerProfileId"):
            player_profile_ready += 1
    return valid, player_profile_ready, invalid


def _provenance_ready(row: dict[str, Any], *, snapshot_id: str, expected_prefix: str | None = None) -> bool:
    provenance = row.get("provenance")
    if not isinstance(provenance, dict):
        return False
    if provenance.get("sourceConnector") != SOURCE_CONNECTOR or provenance.get("snapshotId") != snapshot_id:
        return False
    source_refs = provenance.get("sourceRefs")
    source_files = provenance.get("sourceFiles")
    field_refs = provenance.get("fieldRefs")
    if not isinstance(source_refs, list) or not source_refs:
        return False
    if not isinstance(source_files, list) or not source_files:
        return False
    if not isinstance(field_refs, dict) or not field_refs:
        return False
    if any(str(file_name).startswith("/") for file_name in source_files):
        return False
    if expected_prefix and not all(str(file_name).startswith(expected_prefix) for file_name in source_files):
        return False
    return True


def _credential_issue_count(*payloads: object) -> int:
    issues = 0
    for payload in payloads:
        if payload is None:
            continue
        text = json.dumps(payload, ensure_ascii=False, default=str)
        lower = text.lower()
        if any(term in lower for term in ACCEPTANCE_CREDENTIAL_TERMS):
            issues += 1
        if ACCEPTANCE_PRIVATE_PATH_RE.search(text):
            issues += 1
    return issues


def validate_private_snapshot_acceptance(*, root: Path = ROOT) -> dict[str, Any]:
    """Validate that the latest Garmin CN snapshot is complete enough for private-data acceptance."""

    checks: list[dict[str, Any]] = []
    manifest = read_latest_snapshot_manifest(root=root)
    if not isinstance(manifest, dict):
        checks.append(_acceptance_check("snapshot_manifest", "failed", "No raw snapshot manifest is available."))
        return {
            "schema": ACCEPTANCE_SCHEMA,
            "state": "blocked",
            "hardGate": False,
            "snapshotId": None,
            "checks": checks,
            "failureLabels": ["snapshot_manifest"],
        }

    snapshot_id = str(manifest.get("snapshotId") or "")
    scorecard_files = _manifest_files(manifest, "data/scorecards/")
    shot_files = _manifest_files(manifest, "data/shots/")
    geometry_files = _manifest_files(manifest, "output/prodgeometry")
    normalized = _read_normalized_snapshot_payload(root=root, snapshot_id=snapshot_id) if snapshot_id else None
    connector_status = read_connector_status(root=root)

    manifest_scorecards = _snapshot_int_from_manifest(manifest, "scorecardCount")
    manifest_shots = _snapshot_int_from_manifest(manifest, "shotFileCount")
    checks.append(
        _acceptance_check(
            "snapshot_manifest",
            "ready" if snapshot_id and manifest_scorecards > 0 else "failed",
            "Raw snapshot manifest references synced scorecards." if snapshot_id and manifest_scorecards > 0 else "Snapshot manifest has no scorecards.",
            {
                "snapshotId": snapshot_id or None,
                "scorecardCount": manifest_scorecards,
                "shotFileCount": manifest_shots,
            },
        )
    )

    valid_scorecards, player_profile_ready, invalid_scorecards = _scorecard_detail_counts(root=root, scorecard_files=scorecard_files)
    checks.append(
        _acceptance_check(
            "scorecard_details",
            "ready" if valid_scorecards == manifest_scorecards and valid_scorecards > 0 else "failed",
            "Every manifest scorecard has Garmin detail payload and scorecard id."
            if valid_scorecards == manifest_scorecards and valid_scorecards > 0
            else "One or more manifest scorecards are missing usable Garmin detail payload.",
            {
                "scorecardFiles": len(scorecard_files),
                "validScorecards": valid_scorecards,
                "invalidScorecardCount": len(invalid_scorecards),
            },
        )
    )

    all_manifest_data_files = [*scorecard_files, *shot_files, *geometry_files]
    missing_raw_copies = _raw_snapshot_missing_files(root=root, snapshot_id=snapshot_id, files=all_manifest_data_files) if snapshot_id else []
    checks.append(
        _acceptance_check(
            "durable_snapshot",
            "ready" if snapshot_id and not missing_raw_copies and all_manifest_data_files else "failed",
            "Raw scorecards, shots, and geometry files are copied into the durable snapshot."
            if snapshot_id and not missing_raw_copies and all_manifest_data_files
            else "The durable snapshot is missing raw files referenced by the manifest.",
            {
                "manifestFileCount": len(all_manifest_data_files),
                "missingRawCopyCount": len(missing_raw_copies),
            },
        )
    )

    raw_rounds = normalized.get("rawRounds") if isinstance(normalized, dict) and isinstance(normalized.get("rawRounds"), list) else []
    rounds = normalized.get("rounds") if isinstance(normalized, dict) and isinstance(normalized.get("rounds"), list) else []
    normalized_shots = normalized.get("shots") if isinstance(normalized, dict) and isinstance(normalized.get("shots"), list) else []
    normalized_ready = (
        isinstance(normalized, dict)
        and normalized.get("schema") == "ai-caddie-normalized-history-v1"
        and normalized.get("snapshotId") == snapshot_id
        and len(raw_rounds) == manifest_scorecards
        and len(rounds) > 0
    )
    checks.append(
        _acceptance_check(
            "normalized_history",
            "ready" if normalized_ready else "failed",
            "Normalized history is present and tied to the latest snapshot."
            if normalized_ready
            else "Normalized history is missing or does not match the latest snapshot.",
            {
                "rawRoundCount": len(raw_rounds),
                "roundCount": len(rounds),
                "shotCount": len(normalized_shots),
            },
        )
    )

    ready_shot_files = sum(1 for file_name in shot_files if _shot_file_ready(root / file_name))
    shot_rounds_ready = sum(1 for row in raw_rounds if isinstance(row, dict) and row.get("shotStatus") == "ready")
    shots_ready = manifest_scorecards > 0 and ready_shot_files >= manifest_scorecards and shot_rounds_ready >= manifest_scorecards and len(normalized_shots) > 0
    checks.append(
        _acceptance_check(
            "shot_files",
            "ready" if shots_ready else "failed",
            "Each scorecard has ready shot data and normalized shot rows."
            if shots_ready
            else "One or more scorecards are missing ready Garmin shot data.",
            {
                "shotFileCount": len(shot_files),
                "readyShotFiles": ready_shot_files,
                "scorecardsWithReadyShots": shot_rounds_ready,
                "normalizedShotCount": len(normalized_shots),
            },
        )
    )

    provenance_rows = [row for row in [*raw_rounds, *rounds, *normalized_shots] if isinstance(row, dict)]
    provenance_ready_count = 0
    for row in provenance_rows:
        expected_prefix = "data/shots/" if row in normalized_shots else "data/scorecards/"
        if _provenance_ready(row, snapshot_id=snapshot_id, expected_prefix=expected_prefix):
            provenance_ready_count += 1
    provenance_ready = bool(provenance_rows) and provenance_ready_count == len(provenance_rows)
    checks.append(
        _acceptance_check(
            "provenance",
            "ready" if provenance_ready else "failed",
            "Rounds and shots expose connector, snapshot, source refs, source files, and field refs."
            if provenance_ready
            else "One or more normalized rounds or shots are missing complete provenance.",
            {
                "rowCount": len(provenance_rows),
                "readyRows": provenance_ready_count,
            },
        )
    )

    dependencies = manifest.get("geometryDependencies") if isinstance(manifest.get("geometryDependencies"), list) else []
    dependency_count = len(dependencies) or _snapshot_int_from_manifest(manifest, "geometryDependencyCount")
    profile_ready_count = sum(1 for row in dependencies if isinstance(row, dict) and row.get("profileIdAvailable") is True)
    geometry_ready = dependency_count > 0 and dependencies and profile_ready_count == len(dependencies)
    checks.append(
        _acceptance_check(
            "geometry_dependencies",
            "ready" if geometry_ready else "failed",
            "Geometry dependencies are discovered with player profile id availability for prodgeometry."
            if geometry_ready
            else "Geometry dependencies are missing or lack player profile id availability.",
            {
                "dependencyCount": dependency_count,
                "readyCount": _snapshot_int_from_manifest(manifest, "geometryReadyCount"),
                "missingCount": _snapshot_int_from_manifest(manifest, "geometryMissingCount"),
                "profileReadyCount": profile_ready_count,
            },
        )
    )

    issue_count = _credential_issue_count(manifest, normalized, connector_status)
    checks.append(
        _acceptance_check(
            "credential_scan",
            "ready" if issue_count == 0 else "failed",
            "Snapshot metadata is free of credential material and private filesystem paths."
            if issue_count == 0
            else "Credential material or private filesystem paths were found in snapshot metadata.",
            {"issueCount": issue_count},
        )
    )

    failure_labels = [check["label"] for check in checks if check["state"] != "ready"]
    return {
        "schema": ACCEPTANCE_SCHEMA,
        "state": "ready" if not failure_labels else "blocked",
        "hardGate": not failure_labels,
        "snapshotId": snapshot_id or None,
        "checks": checks,
        "failureLabels": failure_labels,
    }


def _snapshot_int_from_manifest(manifest: dict[str, Any], key: str) -> int:
    try:
        return int(manifest.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def write_connector_status(
    *,
    root: Path = ROOT,
    state: ConnectorState,
    detail: str,
    snapshot_id: str | None,
    error_code: str | None = None,
    data_dir: Path | None = None,
) -> Path:
    # The connector status lives WITH the data partition: ``data_dir/sync`` (defaults to
    # ``root/data/sync`` for the owner, byte-for-byte). A member passes their partition so
    # their status never clobbers the owner's at ``root/data/sync``.
    base = data_dir if data_dir is not None else (root / "data")
    out_dir = base / "sync"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "garmin_cn_status.json"
    payload = {
        "schema": "ai-caddie-connector-status-v1",
        "connector": "garmin_cn_web_session",
        "state": state,
        "detail": sanitize_secret_text(detail),
        "snapshotId": snapshot_id,
        "errorCode": error_code,
        "updatedAt": _utc_now(),
    }
    atomic_write_json(path, payload)
    return path


def read_connector_status(*, root: Path = ROOT) -> dict[str, Any] | None:
    path = root / STATUS_FILE
    if not path.exists():
        return None
    payload = safe_read_json(path)  # torn/corrupt status must not 500 the public /sync/status
    if not isinstance(payload, dict):
        return None
    if isinstance(payload, dict) and "detail" in payload:
        payload["detail"] = sanitize_secret_text(payload.get("detail") or "")
    return payload


def snapshot_to_payload(manifest: SnapshotManifest) -> dict[str, Any]:
    data = asdict(manifest)
    return {
        "snapshotId": data["snapshot_id"],
        "scorecardCount": data["scorecard_count"],
        "shotFileCount": data["shot_file_count"],
        "summaryPresent": data["summary_present"],
        "files": data["files"],
        "geometryDependencyCount": data["geometry_dependency_count"],
        "geometryReadyCount": data["geometry_ready_count"],
        "geometryMissingCount": data["geometry_missing_count"],
        "geometryDependencies": data["geometry_dependencies"],
    }
