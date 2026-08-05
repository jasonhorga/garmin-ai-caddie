"""Batch-validate Garmin prodgeometry for every hole in a course release.

For each hole this script:

1. Downloads the encrypted prodgeometry zip from the CourseView release record.
2. Calls `fetch_courseview_geometry_key.js` to derive the zip password and extract it.
3. Calls `decode_courseview_geometry.js` to decode Draco meshes.
4. Calls `measure_prodgeometry_distances.py` to generate tee/hazard distances.
5. Optionally calls `overlay_prodgeometry_on_raster.py` for visual validation.

Outputs are written under data/courseview/prodgeometry/<course_id>/ and
output/prodgeometry*/. Secrets are not printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from ai_caddie.geometry.geometry_authority import (
    authority_path,
    build_authority,
    legacy_outputs_match,
    write_authority,
)
from ai_caddie.geometry.inspect_courseview_release import inspect_valid_release, load_release_pb

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent  # sibling .js/.py invoked via subprocess below
PROD_ROOT = ROOT / "data" / "courseview" / "prodgeometry"
OUT_ROOT = ROOT / "output" / "prodgeometry"
HAZARD_ROOT = ROOT / "output" / "prodgeometry_hazards"
SUMMARY_ROOT = ROOT / "output" / "prodgeometry_batch"
DEFAULT_SNAPSHOT = ROOT / "logs" / "probe_map_bodies" / "snapshot_400065_hole.json"


# node/python children here are network- AND CPU-bound (download + Draco decode). Without a
# timeout one hung child blocks its caller forever; under the on-demand geometry path that used
# to wedge every other hole too (P1-6). Cap each child so a hang fails fast and self-recovers.
GEOMETRY_SUBPROCESS_TIMEOUT_S = 180.0


def run(
    cmd: list[str],
    *,
    allow_fail: bool = False,
    timeout: float | None = GEOMETRY_SUBPROCESS_TIMEOUT_S,
) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        message = f"command timed out after {timeout}s: {' '.join(cmd)}\n{partial}"
        if not allow_fail:
            raise RuntimeError(message) from exc
        return False, message
    ok = proc.returncode == 0
    if not ok and not allow_fail:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout}")
    return ok, proc.stdout


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read()


def zip_name(url: str) -> str:
    return Path(url.split("?", 1)[0]).name


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_extract_dir(course_id: int, hole_number: int, zip_path: Path) -> Path:
    version = zip_path.stem.split("_", 1)[1] if "_" in zip_path.stem else zip_path.stem
    return PROD_ROOT / str(course_id) / f"Hole{hole_number:02d}_{version}"


def hole_range(value: str) -> set[int]:
    holes: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            holes.update(range(int(a), int(b) + 1))
        else:
            holes.add(int(part))
    return holes


def mesh_json_path(course_id: int, hole_number: int) -> Path:
    return OUT_ROOT / f"gid{course_id}_h{hole_number:02d}_meshes.json"


def stats_path(course_id: int, hole_number: int) -> Path:
    return OUT_ROOT / f"gid{course_id}_h{hole_number:02d}_stats.json"


def distances_path(course_id: int, hole_number: int) -> Path:
    return OUT_ROOT / f"gid{course_id}_h{hole_number:02d}_tee_distances.json"


def hazards_path(course_id: int, hole_number: int) -> Path:
    return HAZARD_ROOT / f"gid{course_id}_h{hole_number:02d}_hazards.json"


def process_hole(
    *,
    course_id: int,
    hole: dict[str, Any],
    profile_id: str,
    snapshot: Path | None,
    skip_overlay: bool,
    force_download: bool,
) -> dict[str, Any]:
    hole_number = int(hole["hole"])
    geometry_url = hole.get("geometry_url")
    if not geometry_url:
        return {"hole": hole_number, "ok": False, "error": "missing geometry_url"}

    zip_path = PROD_ROOT / str(course_id) / zip_name(geometry_url)
    extract_dir = expected_extract_dir(course_id, hole_number, zip_path)
    row: dict[str, Any] = {
        "hole": hole_number,
        "yardage_or_length": hole.get("yardage_or_length"),
        "zip": str(zip_path.relative_to(ROOT)),
        "extract_dir": str(extract_dir.relative_to(ROOT)),
        "mesh_json": str(mesh_json_path(course_id, hole_number).relative_to(ROOT)),
        "hazards": str(hazards_path(course_id, hole_number).relative_to(ROOT)),
        "distances": str(distances_path(course_id, hole_number).relative_to(ROOT)),
        "steps": {},
    }

    try:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        if force_download or not zip_path.exists():
            data = fetch_bytes(geometry_url)
            staged_zip = zip_path.with_name(f".{zip_path.name}.{os.getpid()}.tmp")
            try:
                staged_zip.write_bytes(data)
                os.replace(staged_zip, zip_path)
            finally:
                staged_zip.unlink(missing_ok=True)
            row["steps"]["download"] = {"ok": True, "bytes": len(data)}
        else:
            row["steps"]["download"] = {"ok": True, "cached": True, "bytes": zip_path.stat().st_size}
        row["geometry_zip_sha256"] = file_sha256(zip_path)

        key_cmd = [
            "node",
            str(SCRIPT_DIR / "fetch_courseview_geometry_key.js"),
            "--image-url",
            geometry_url,
            "--profile-id",
            profile_id,
            "--zip",
            str(zip_path),
            "--extract",
            str(extract_dir),
            "--json",
        ]
        ok, out = run(key_cmd)
        key_result = json.loads(out)
        row["steps"]["extract"] = {
            "ok": ok,
            "zipPasswordWorks": key_result.get("zipPasswordWorks"),
            "passwordLength": key_result.get("passwordLength"),
        }

        # Build every derivative privately. If any build step fails, readers
        # continue seeing the complete previous version. The authority sidecar
        # is the commit marker for the later per-file installation.
        staging_root = ROOT / "output" / ".prodgeometry-staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f"gid{course_id}_h{hole_number:02d}-",
            dir=staging_root,
        ) as tmp:
            stage = Path(tmp)
            staged_mesh = stage / "meshes.json"
            staged_stats = stage / "stats.json"
            staged_distances = stage / "tee_distances.json"
            staged_hazards = stage / "hazards.json"

            decode_cmd = [
                "node",
                str(SCRIPT_DIR / "decode_courseview_geometry.js"),
                "--geometry-dir",
                str(extract_dir),
                "--out",
                str(staged_mesh),
                "--stats",
                str(staged_stats),
            ]
            ok, out = run(decode_cmd)
            decode_result = json.loads(out)
            row["steps"]["decode"] = {"ok": ok, "meshCount": decode_result.get("meshCount")}

            distance_cmd = [
                sys.executable,
                "-m",
                "ai_caddie.geometry.measure_prodgeometry_distances",
                "--mesh-json",
                str(staged_mesh),
                "--out",
                str(staged_distances),
            ]
            ok, out = run(distance_cmd)
            row["steps"]["distances"] = {"ok": ok}

            hazard_cmd = [
                sys.executable,
                "-m",
                "ai_caddie.geometry.export_prodgeometry_hazards",
                "--mesh-json",
                str(staged_mesh),
                "--out",
                str(staged_hazards),
            ]
            ok, out = run(hazard_cmd)
            row["steps"]["hazards"] = {"ok": ok, "output_tail": out.strip().splitlines()[-1:]}

            if not skip_overlay and snapshot:
                overlay_cmd = [
                    sys.executable,
                    "-m",
                    "ai_caddie.geometry.overlay_prodgeometry_on_raster",
                    "--mesh-json",
                    str(staged_mesh),
                    "--snapshot",
                    str(snapshot),
                    "--hole",
                    str(hole_number),
                ]
                ok, out = run(overlay_cmd, allow_fail=True)
                row["steps"]["overlay"] = {"ok": ok, "output_tail": out.strip().splitlines()[-3:]}
                if not ok:
                    row["steps"]["overlay"]["error"] = out.strip()[-800:]

            installs = (
                (staged_mesh, mesh_json_path(course_id, hole_number)),
                (staged_stats, stats_path(course_id, hole_number)),
                (staged_distances, distances_path(course_id, hole_number)),
                (staged_hazards, hazards_path(course_id, hole_number)),
            )
            # A crash between the individual replaces must never leave the old
            # authority marker claiming that a mixed set is release-bound.
            authority_path(mesh_json_path(course_id, hole_number)).unlink(missing_ok=True)
            for staged, target in installs:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged, target)
            row["steps"]["install"] = {"ok": True, "files": len(installs)}

        row["ok"] = all(step.get("ok") for step in row["steps"].values())
    except Exception as exc:
        row["ok"] = False
        row["error"] = str(exc)
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("course_id", type=int)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--holes", default="1-9")
    parser.add_argument("--live", action="store_true", help="fetch fresh release protobuf")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--skip-overlay", action="store_true")
    parser.add_argument("--force-download", action="store_true")
    args = parser.parse_args()

    selected = hole_range(args.holes)
    release = inspect_valid_release(
        load_release_pb(args.course_id, args.live), expected_course_id=args.course_id
    )
    holes = [h for h in release["holes"] if int(h.get("hole", -1)) in selected]
    if not holes:
        raise SystemExit(f"no selected holes found for course {args.course_id}")

    SUMMARY_ROOT.mkdir(parents=True, exist_ok=True)
    summary = {
        "course_id": args.course_id,
        "course_name": release.get("course_name"),
        "release_id": release.get("release_id"),
        "holes_requested": sorted(selected),
        "holes": [],
    }

    for hole in sorted(holes, key=lambda h: int(h["hole"])):
        hole_number = int(hole["hole"])
        print(f"[hole {hole_number:02d}] start", flush=True)
        row = process_hole(
            course_id=args.course_id,
            hole=hole,
            profile_id=args.profile_id,
            snapshot=args.snapshot if args.snapshot.exists() else None,
            skip_overlay=args.skip_overlay,
            force_download=args.force_download,
        )
        if row.get("ok"):
            authority = build_authority(
                global_id=args.course_id,
                local_hole=hole_number,
                release=release,
                hole=hole,
                release_source="live" if args.live else "cache",
                geometry_zip_sha256=row.get("geometry_zip_sha256"),
            )
            mesh_file = mesh_json_path(args.course_id, hole_number)
            hazard_file = hazards_path(args.course_id, hole_number)
            if legacy_outputs_match(authority, mesh_file=mesh_file, hazard_file=hazard_file):
                write_authority(authority_path(mesh_file), authority)
            else:
                row["ok"] = False
                row["error"] = "decoded prodgeometry does not match the release asset authority"
        summary["holes"].append(row)
        status = "ok" if row.get("ok") else "FAIL"
        mesh_count = row.get("steps", {}).get("decode", {}).get("meshCount")
        print(f"[hole {hole_number:02d}] {status} meshCount={mesh_count}", flush=True)

    summary["ok"] = all(row.get("ok") for row in summary["holes"])
    summary_path = SUMMARY_ROOT / f"gid{args.course_id}_holes_{min(selected):02d}-{max(selected):02d}_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[done] wrote {summary_path.relative_to(ROOT)}")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
