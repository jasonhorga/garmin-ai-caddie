#!/usr/bin/env python3
"""One-shot report/apply command for historical manual GIR backfill.

The public functions are intentionally small so the fixture product tests can exercise the exact
same dry-run and apply paths as the production command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ai_caddie.core import data as core_data
from ai_caddie.geometry.geometry_evidence import _mesh_gir_surface_match, _mesh_surface_rows
from ai_caddie.geometry.measure_prodgeometry_distances import bind_selected_green_target
from ai_caddie.rounds import round_ingest


def _runtime_root(root: Path | str | None) -> Path:
    return Path(root).expanduser() if root is not None else Path(
        os.environ.get("AI_CADDIE_ROOT") or core_data.ROOT
    )


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number


def _hole_par(raw: dict[str, Any], hole: dict[str, Any], number: int) -> int | None:
    direct = _int(hole.get("par"))
    if direct is not None:
        return direct
    snapshots = raw.get("courseSnapshots") or []
    snapshot = snapshots[0] if snapshots and isinstance(snapshots[0], dict) else {}
    pars = snapshot.get("holePars")
    if pars is None:
        pars = raw.get("holePars")
    if isinstance(pars, list):
        return _int(pars[number - 1]) if 0 < number <= len(pars) else None
    if isinstance(pars, str) and 0 < number <= len(pars) and pars[number - 1].isdigit():
        return int(pars[number - 1])
    return None


def _location_degrees(location: Any) -> tuple[float, float] | None:
    if not isinstance(location, dict):
        return None
    lat = core_data.semicircle_to_deg(location.get("lat"))
    lon = core_data.semicircle_to_deg(location.get("lon"))
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def _landing(rows: list[dict[str, Any]], index: int) -> tuple[tuple[float, float] | None, str]:
    if index + 1 < len(rows):
        return _location_degrees(rows[index + 1].get("startLoc")), "nextShotStart"
    return None, "lastShotAim"


def _geometry_classification(
    root: Path,
    raw: dict[str, Any],
    number: int,
    endpoint: tuple[float, float],
) -> tuple[bool | None, str]:
    ref = core_data.round_hole_ref(raw, number)
    if ref.global_id is None:
        return None, "course global id is missing"
    mesh_path = root / "output" / "prodgeometry" / f"gid{int(ref.global_id)}_h{int(ref.local_hole):02d}_meshes.json"
    hazard_path = root / "output" / "prodgeometry_hazards" / f"gid{int(ref.global_id)}_h{int(ref.local_hole):02d}_hazards.json"
    if not mesh_path.exists():
        return None, f"selected Green.drc geometry is missing ({mesh_path.name})"
    try:
        meshes = core_data.read_json(mesh_path)
        hazards = core_data.read_json(hazard_path) if hazard_path.exists() else {}
    except (OSError, ValueError, TypeError):
        return None, "selected Green.drc geometry is unreadable"
    if not isinstance(meshes, dict):
        return None, "selected Green.drc geometry has no mesh object"
    rebound = bind_selected_green_target(hazards, meshes, include_selected_component=True) or {}
    selected = rebound.get("_selectedGreenComponent") if "_selectedGreenComponent" in rebound else None
    ref_lat = hazards.get("refLat") if isinstance(hazards, dict) else None
    ref_lon = hazards.get("refLon") if isinstance(hazards, dict) else None
    mesh_hole = meshes.get("hole") if isinstance(meshes.get("hole"), dict) else {}
    ref_lat = ref_lat if ref_lat is not None else mesh_hole.get("RefLat")
    ref_lon = ref_lon if ref_lon is not None else mesh_hole.get("RefLon")
    if ref_lat is None or ref_lon is None:
        return None, "selected Green.drc geometry has no WGS84 reference"
    try:
        point = core_data.wgs84_to_local(endpoint[0], endpoint[1], float(ref_lat), float(ref_lon))
    except (TypeError, ValueError, OverflowError):
        return None, "landing coordinate is invalid"
    surface = _mesh_gir_surface_match(point, _mesh_surface_rows(meshes), selected_component=selected)
    kind = (surface or {}).get("kind")
    if kind == "green":
        return True, "landing is inside the selected Green.drc connected component triangle"
    if kind is not None:
        return False, f"landing is outside the selected Green.drc component ({kind})"
    return None, "landing is not classifiable against the selected Green.drc component"


def _evaluate_hole(
    root: Path, raw: dict[str, Any], hole: dict[str, Any], shot_data: dict[str, Any] | None
) -> tuple[bool | None, str, str | None]:
    number = _int(hole.get("number"))
    if number is None or number <= 0:
        return None, "hole number is missing", None
    par = _hole_par(raw, hole, number)
    strokes = _int(hole.get("strokes"))
    if par is None:
        return None, "hole par is missing", None
    if strokes is None:
        return None, "hole strokes are missing", None
    rows = [
        shot
        for hole_row in (shot_data or {}).get("holeShots", []) or []
        if isinstance(hole_row, dict) and _int(hole_row.get("holeNumber")) == number
        for shot in (hole_row.get("shots") or [])
        if isinstance(shot, dict)
    ]
    putts = round_ingest._shot_putt_count(
        rows, total_strokes=strokes, club_details=(shot_data or {}).get("clubDetails"),
    )
    if putts is not None:
        gir = strokes - putts <= par - 2
        return gir, f"shot log counted {putts} putts; strokes-putts={strokes - putts} vs par-2={par - 2}", None
    if strokes <= par - 2:
        return True, f"strokes {strokes} are at or below the regulation limit par-2={par - 2}", None
    required_index = par - 3
    if required_index < 0 or required_index >= len(rows):
        return None, f"regulation landing shot {required_index + 1} is missing", None
    endpoint, landing_source = _landing(rows, required_index)
    if endpoint is None:
        return None, "regulation landing not recorded (only aim target)", landing_source
    gir, basis = _geometry_classification(root, raw, number, endpoint)
    return gir, basis, landing_source


def _scorecard_files(root: Path) -> list[tuple[str, Path]]:
    players = root / "data" / "players"
    if not players.is_dir():
        return []
    rows: list[tuple[str, Path]] = []
    for player_dir in sorted(players.iterdir()):
        if not player_dir.is_dir() or player_dir.is_symlink():
            continue
        for path in sorted((player_dir / "scorecards").glob("*.json")):
            rows.append((player_dir.name, path))
    return rows


def _digest_bytes(value: bytes | None) -> str | None:
    return hashlib.sha256(value).hexdigest() if value is not None else None


def _round_id(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return None
    details = raw.get("scorecardDetails")
    if not isinstance(details, list) or not details or not isinstance(details[0], dict):
        return None
    scorecard = details[0].get("scorecard")
    return scorecard.get("id") if isinstance(scorecard, dict) else None


def _scan(root: Path) -> tuple[dict[str, Any], dict[Path, dict[str, Any]]]:
    changes: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    mutations: dict[Path, dict[str, Any]] = {}
    before = 0
    manual_rounds = 0
    manual_putts_zero = 0
    for player_id, path in _scorecard_files(root):
        try:
            scorecard_bytes = path.read_bytes()
            raw = json.loads(scorecard_bytes)
        except (OSError, ValueError, TypeError):
            skipped.append({"playerId": player_id, "path": str(path), "reason": "scorecard is unreadable"})
            continue
        if not isinstance(raw, dict):
            skipped.append({"playerId": player_id, "path": str(path), "reason": "scorecard is not an object"})
            continue
        if raw.get("source") != "manual":
            reason = "source missing (treated as Garmin)" if "source" not in raw else "source is not manual (treated as Garmin)"
            skipped.append({"playerId": player_id, "path": str(path), "roundId": _round_id(raw), "reason": reason})
            continue
        details = raw.get("scorecardDetails")
        if not isinstance(details, list) or not details:
            skipped.append({"playerId": player_id, "path": str(path), "reason": "scorecard details missing"})
            continue
        scorecard = details[0].get("scorecard") if details and isinstance(details[0], dict) else None
        if not isinstance(scorecard, dict):
            skipped.append({"playerId": player_id, "path": str(path), "roundId": _round_id(raw), "reason": "scorecard missing"})
            continue
        manual_rounds += 1
        round_id = scorecard.get("id")
        shot_path = path.parent.parent / "shots" / path.name
        try:
            shots_bytes = shot_path.read_bytes()
        except FileNotFoundError:
            shots_bytes = None
        except OSError:
            skipped.append({"playerId": player_id, "path": str(path), "roundId": round_id, "reason": "shots are unreadable"})
            continue
        try:
            shot_data = json.loads(shots_bytes) if shots_bytes is not None else None
        except (ValueError, TypeError):
            shot_data = None
        if not isinstance(shot_data, dict):
            shot_data = None
        holes = scorecard.get("holes") or []
        for hole in holes:
            if not isinstance(hole, dict):
                continue
            if hole.get("putts") == 0:
                manual_putts_zero += 1
            if hole.get("gir") is not None:
                before += 1
                skipped.append({"roundId": round_id, "hole": hole.get("number"), "reason": "GIR already recorded"})
                continue
            if hole.get("putts") is not None:
                skipped.append({"roundId": round_id, "hole": hole.get("number"), "reason": "putts already recorded"})
                continue
            gir, basis, landing_source = _evaluate_hole(root, raw, hole, shot_data)
            if gir is None:
                unresolved.append({"roundId": round_id, "hole": hole.get("number"), "oldGir": None, "newGir": None, "reason": basis})
                continue
            change = {"playerId": player_id, "roundId": round_id, "hole": hole.get("number"), "oldGir": None, "newGir": bool(gir), "basis": basis, "path": str(path)}
            if landing_source is not None:
                change["landingSource"] = landing_source
            changes.append(change)
            entry = mutations.setdefault(path, {"rows": [], "scorecardDigest": _digest_bytes(scorecard_bytes), "shotsDigest": _digest_bytes(shots_bytes)})
            entry["rows"].append(change)
        # A missing GIR is not a recorded denominator, so only existing values count here.
    after = before + len(changes)
    report = {
        "mode": "dry-run",
        "changes": changes,
        "unresolved": unresolved,
        "skipped": skipped,
        "summary": {
            "manualRounds": manual_rounds,
            "changes": len(changes),
            "unresolved": len(unresolved),
            "girRecordedBefore": before,
            "girRecordedAfter": after,
            "manualHolesPuttsZero": manual_putts_zero,
        },
    }
    return report, mutations


def _apply(root: Path, report: dict[str, Any], mutations: dict[Path, dict[str, Any]]) -> None:
    by_player: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for path, entry in mutations.items():
        rows = entry["rows"]
        player = path.parent.parent.name
        by_player.setdefault(player, []).append((path, entry))
    backup_dir = root / "backups" / f"c187-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    backup_manifest: list[dict[str, Any]] = []
    actual_changes: list[dict[str, Any]] = []
    planned = report.get("changes", [])
    report["plannedChanges"] = planned
    report["changes"] = actual_changes
    for player, files in by_player.items():
        if any(path.parent.parent.parent != root / "data" / "players" for path, _entry in files):
            raise RuntimeError("refusing to apply GIR changes outside manual player storage")
        with round_ingest._player_ingest_lock(player, root):
            for path, entry in files:
                rows = entry["rows"]
                try:
                    current_bytes = path.read_bytes()
                    shots_path = path.parent.parent / "shots" / path.name
                    shots_bytes = shots_path.read_bytes() if shots_path.exists() else None
                    if _digest_bytes(current_bytes) != entry["scorecardDigest"] or _digest_bytes(shots_bytes) != entry["shotsDigest"]:
                        report.setdefault("skipped", []).extend({**row, "reason": "scorecard or shots changed after scan"} for row in rows)
                        continue
                    raw = json.loads(current_bytes.decode("utf-8"))
                    details = raw.get("scorecardDetails") if isinstance(raw, dict) else None
                    scorecard = details[0].get("scorecard") if isinstance(details, list) and details and isinstance(details[0], dict) else None
                    if not isinstance(scorecard, dict) or raw.get("source") != "manual":
                        report.setdefault("skipped", []).extend({**row, "reason": "scorecard no longer manual or is malformed"} for row in rows)
                        continue
                    holes = scorecard.get("holes") or []
                    wrote: list[dict[str, Any]] = []
                    for change in rows:
                        target = next((hole for hole in holes if isinstance(hole, dict) and hole.get("number") == change["hole"]), None)
                        if target is None or target.get("gir") is not None or target.get("putts") is not None:
                            report.setdefault("skipped", []).append({**change, "reason": "hole changed after scan"})
                            continue
                        target["gir"] = change["newGir"]
                        wrote.append(change)
                    if not wrote:
                        continue
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    backup = backup_dir / player / path.name
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, backup)
                    backup_entry = {"path": str(path), "backup": str(backup), "changes": 0}
                    backup_manifest.append(backup_entry)
                    manifest_path = backup_dir / "manifest.json"
                    manifest_path.write_text(json.dumps(backup_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    round_ingest._atomic_write_json(path, raw)
                    actual_changes.extend(wrote)
                    backup_entry["changes"] = len(wrote)
                    manifest_path.write_text(json.dumps(backup_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    print(f"C187 wrote {path} ({len(wrote)} GIR)", file=sys.stderr)
                except Exception as exc:
                    report.setdefault("applyErrors", []).append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
            round_ingest._invalidate_cache(player)
    report["summary"]["changes"] = len(actual_changes)
    report["summary"]["girRecordedAfter"] = report["summary"]["girRecordedBefore"] + len(actual_changes)


def backfill(*, root: Path | str | None = None, apply: bool = False) -> dict[str, Any]:
    runtime_root = _runtime_root(root)
    report, mutations = _scan(runtime_root)
    if apply:
        report["mode"] = "apply"
        if mutations:
            _apply(runtime_root, report, mutations)
    return report

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None, help="runtime root containing data/ and output/")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the change report without writing (default)")
    mode.add_argument("--apply", action="store_true", help="write changes after backing up each file")
    args = parser.parse_args(argv)
    report = backfill(root=args.root, apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report.get("applyErrors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
