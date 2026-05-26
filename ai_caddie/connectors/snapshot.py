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


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _coerce_id(value: Any) -> Any:
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value


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


def _normalize_scorecard(path: Path, *, root: Path) -> dict[str, Any] | None:
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
        "sourceFile": _relative(path, root),
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


def _normalize_shot_file(path: Path, *, root: Path, round_row: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        payload = _read_json(path)
    except Exception:
        return []
    if not isinstance(payload, dict) or payload.get("_no_data"):
        return []

    clubs = _club_lookup(payload)
    scorecard_id = round_row.get("id")
    rows: list[dict[str, Any]] = []
    for hole_data in payload.get("holeShots", []) or []:
        hole = int(hole_data.get("holeNumber") or 0)
        global_id, local_hole = _shot_hole_ref(round_row, hole)
        for shot in hole_data.get("shots", []) or []:
            club_id = shot.get("clubId")
            club = clubs.get(club_id) or str(club_id or "Unknown")
            end_loc = shot.get("endLoc") if isinstance(shot.get("endLoc"), dict) else {}
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
                    "sourceFile": _relative(path, root),
                }
            )
    return rows


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
    files: list[str] = []
    if summary.exists():
        files.append(_relative(summary, root))
    files.extend(_relative(path, root) for path in scorecards)
    files.extend(_relative(path, root) for path in shots)
    return SnapshotManifest(
        snapshot_id=snapshot_id,
        scorecard_count=len(scorecards),
        shot_file_count=len(shots),
        summary_present=summary.exists(),
        files=files,
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
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def build_normalized_snapshot_payload(*, root: Path = ROOT, manifest: SnapshotManifest) -> dict[str, Any]:
    scorecard_paths = [root / file_name for file_name in manifest.files if file_name.startswith("data/scorecards/")]
    raw_rounds = [
        row
        for path in scorecard_paths
        for row in [_normalize_scorecard(path, root=root)]
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
        for shot in _normalize_shot_file(path, root=root, round_row=round_row)
    ]
    rounds = merge_same_day_halves(raw_rounds)
    shots = _remap_shots_to_merged_rounds(shots, rounds)
    return {
        "schema": "ai-caddie-normalized-history-v1",
        "snapshotId": manifest.snapshot_id,
        "createdAt": _utc_now(),
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
    }
