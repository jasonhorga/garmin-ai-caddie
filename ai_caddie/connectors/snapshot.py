from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any

from ai_caddie.data import ROOT, semicircle_to_deg
from ai_caddie.history import (
    HistoryData,
    canonical_course_name,
    course_key,
    merge_same_day_halves,
    millionths_to_deg,
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
        holes.append(
            {
                "number": number,
                "strokes": hole.get("strokes"),
                "par": par,
                "putts": hole.get("putts"),
                "gir": hole.get("gir"),
                "fairway": hole.get("fairway"),
            }
        )
    return holes


def _shot_file_ready(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = _read_json(path)
    except Exception:
        return False
    return not bool(isinstance(payload, dict) and payload.get("_no_data"))


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
    has_shots = _shot_file_ready(shot_path)
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
        "shotStatus": "ready" if has_shots else "no_data" if shot_path.exists() else "missing",
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


def discover_geometry_dependencies(*, root: Path = ROOT) -> list[dict[str, Any]]:
    dependencies: dict[tuple[int, int], dict[str, Any]] = {}
    for path in _json_files(root / "data" / "scorecards"):
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


def build_snapshot_manifest(*, root: Path = ROOT, snapshot_id: str) -> SnapshotManifest:
    data_dir = root / "data"
    summary = data_dir / "summary.json"
    scorecards = _json_files(data_dir / "scorecards")
    shots = _json_files(data_dir / "shots")
    geometry_dependencies = discover_geometry_dependencies(root=root)
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


def write_connector_status(
    *,
    root: Path = ROOT,
    state: ConnectorState,
    detail: str,
    snapshot_id: str | None,
    error_code: str | None = None,
) -> Path:
    out_dir = root / SYNC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = root / STATUS_FILE
    payload = {
        "schema": "ai-caddie-connector-status-v1",
        "connector": "garmin_cn_web_session",
        "state": state,
        "detail": sanitize_secret_text(detail),
        "snapshotId": snapshot_id,
        "errorCode": error_code,
        "updatedAt": _utc_now(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def read_connector_status(*, root: Path = ROOT) -> dict[str, Any] | None:
    path = root / STATUS_FILE
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
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
