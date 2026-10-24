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
from datetime import UTC, datetime
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from ai_caddie.geometry.geometry_authority import (
    asset_version,
    authority_path,
    build_authority,
    canonical_asset_path,
    derivatives_status_path,
    load_authority,
    load_derivatives_status,
    mesh_output_matches,
    valid_geometry_zip_sha256,
    write_authority,
    write_derivatives_status,
)
from ai_caddie.geometry.inspect_courseview_release import inspect_valid_release, load_release_pb

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent  # sibling .js/.py invoked via subprocess below
PROD_ROOT = ROOT / "data" / "courseview" / "prodgeometry"
OUT_ROOT = ROOT / "output" / "prodgeometry"
HAZARD_ROOT = ROOT / "output" / "prodgeometry_hazards"
SUMMARY_ROOT = ROOT / "output" / "prodgeometry_batch"
DEFAULT_SNAPSHOT = ROOT / "logs" / "probe_map_bodies" / "snapshot_400065_hole.json"
logger = logging.getLogger(__name__)


def _finish_stage(row: dict, stage: str, started: float, *, course_id: int) -> float:
    now = time.perf_counter()
    duration_ms = round((now - started) * 1000, 1)
    row["steps"][stage]["durationMs"] = duration_ms
    row["steps"][stage]["finishedAt"] = datetime.now(UTC).isoformat()
    logger.info("course_asset gid=%s hole=%s stage=%s duration_ms=%.1f", course_id, row["hole"], stage, duration_ms)
    return now


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


# Digest reads are shared by the request and derivative lanes.  Keep this tiny cache separate from
# derivative identity state so tests and process restarts can discard it independently.
_FILE_SHA256_LOCK = threading.Lock()
_FILE_SHA256_CACHE: dict[tuple[str, int, int, int, int], str] = {}


def file_sha256(path: Path) -> str:
    """Return a file digest without rereading an unchanged mesh on every request.

    Geometry requests repeatedly inspect the same canonical mesh while a deferred derivative is
    running. The mtime/size/inode/ctime key keeps the common path cheap and also invalidates a
    same-size ZIP replacement that preserved mtime. The cache is bounded to the latest
    fingerprint for each path; it is only an optimization, never an authority record.
    """
    resolved = str(path.resolve())
    stat = path.stat()
    key = (resolved, stat.st_mtime_ns, stat.st_size, stat.st_ino, stat.st_ctime_ns)
    with _FILE_SHA256_LOCK:
        cached = _FILE_SHA256_CACHE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    with _FILE_SHA256_LOCK:
        # Keep one entry per path so a sequence of release swaps cannot grow this cache forever.
        for old_key in tuple(_FILE_SHA256_CACHE):
            if old_key[0] == resolved and old_key != key:
                _FILE_SHA256_CACHE.pop(old_key, None)
        _FILE_SHA256_CACHE[key] = value
    return value


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


# Decoding is the first playable derivative.  On-demand installs hand the slower distance and
# obstacle exports to a daemon lane after the mesh has been published, so a topo request can render
# while those supplements catch up.  The key prevents two overlapping requests for one hole from
# writing the same derivative files concurrently.
_DERIVATIVE_LOCK = threading.Lock()
# Mesh publication and derivative replacement share this lock.  It closes the small but real
# race where an old worker validates the old mesh and then replaces a hazard file immediately
# after a newer release has installed its mesh.
_DERIVATIVE_PUBLISH_LOCK = threading.Lock()
_DERIVATIVE_JOBS: dict[tuple[int, int, str, str, str, str], threading.Thread] = {}
# A failed exporter must not be relaunched on every package request.  The identity is part of the
# key, so a new mesh/release gets a clean retry budget immediately while a permanently broken
# exporter backs off exponentially for the same bytes.  The timer is checked lazily by the next
# ensure request; no extra process or resident retry thread is needed.
_DERIVATIVE_FAILURES: dict[tuple[int, int, str, str, str, str], tuple[int, float]] = {}
DERIVATIVE_BACKOFF_BASE_S = 1.0
DERIVATIVE_BACKOFF_MAX_S = 300.0

_DERIVATIVE_AUTHORITY_FIELDS = (
    "releaseVersion",
    "releaseId",
    "courseGenVersion",
    "geometryAssetPath",
    "geometryAssetVersion",
    "rasterAssetPath",
    "geometryZipSha256",
)


def _authority_descriptor(value: dict[str, Any] | None) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return tuple("" for _ in _DERIVATIVE_AUTHORITY_FIELDS)
    return tuple(str(value.get(key) or "") for key in _DERIVATIVE_AUTHORITY_FIELDS)


def _derivative_key(
    course_id: int,
    hole_number: int,
    mesh_file: Path,
    distance_target: Path,
    hazard_target: Path,
    identity: str,
) -> tuple[int, int, str, str, str, str]:
    return (
        int(course_id),
        int(hole_number),
        str(mesh_file),
        str(distance_target),
        str(hazard_target),
        str(identity),
    )


def _record_derivative_result(
    key: tuple[int, int, str, str, str, str],
    *,
    success: bool,
    error_type: str | None = None,
) -> None:
    """Clear or advance the per-identity exporter backoff after a worker exits."""
    with _DERIVATIVE_LOCK:
        status = load_derivatives_status(Path(key[2])) or {}
        previous_attempts = int(status.get("failureCount") or 0) if status.get("identity") == key[-1] else 0
        attempts, _ = _DERIVATIVE_FAILURES.get(key, (previous_attempts, 0.0))
        attempts += int(not success)
        delay = min(
            float(DERIVATIVE_BACKOFF_MAX_S),
            float(DERIVATIVE_BACKOFF_BASE_S) * (2 ** min(20, max(0, attempts - 1))),
        )
        if success:
            _DERIVATIVE_FAILURES.pop(key, None)
        else:
            _DERIVATIVE_FAILURES[key] = (attempts, time.monotonic() + delay)
    write_derivatives_status(Path(key[2]), {
        "status": "ready" if success else "failed",
        "identity": key[-1],
        "failureCount": attempts,
        "lastErrorType": None if success else (error_type or "ExportFailed"),
        "retryAfterEpoch": None if success else time.time() + delay,
        "updatedAt": datetime.now(UTC).isoformat(),
    })


def _derivative_snapshot(
    mesh_file: Path,
    *,
    release_identity: dict[str, Any] | None = None,
) -> tuple[str, str, tuple[str, ...]]:
    """Return the immutable identity a supplement worker is allowed to publish beside."""
    mesh_digest = file_sha256(mesh_file)
    authority = load_authority(authority_path(mesh_file))
    descriptor = _authority_descriptor(authority or release_identity)
    raw = json.dumps(
        {"meshSha256": mesh_digest, "authority": descriptor},
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), mesh_digest, descriptor


def _derivative_target_is_current(
    mesh_file: Path,
    *,
    mesh_digest: str,
    authority_descriptor: tuple[str, ...],
) -> bool:
    """Check the live mesh and authority while holding the publication lock."""
    try:
        if file_sha256(mesh_file) != mesh_digest:
            return False
    except OSError:
        return False
    current = load_authority(authority_path(mesh_file))
    if current is None:
        # process_hole() starts the worker just before geometry_sync writes the new sidecar.  The
        # mesh digest still protects direct legacy callers that have no release identity.  An
        # online release-bound job must wait for its sidecar; otherwise a same-byte mesh from an
        # older release could accept the old worker's obstacle export during the short install
        # window.
        return not any(authority_descriptor)
    current_descriptor = _authority_descriptor(current)
    return all(
        not expected or expected == actual
        for expected, actual in zip(authority_descriptor, current_descriptor)
    )


def _derivative_commands(
    *,
    mesh_file: Path,
    staged_distances: Path,
    staged_hazards: Path,
) -> tuple[list[str], list[str]]:
    distance_cmd = [
        sys.executable,
        "-m",
        "ai_caddie.geometry.measure_prodgeometry_distances",
        "--mesh-json",
        str(mesh_file),
        "--out",
        str(staged_distances),
    ]
    hazard_cmd = [
        sys.executable,
        "-m",
        "ai_caddie.geometry.export_prodgeometry_hazards",
        "--mesh-json",
        str(mesh_file),
        "--out",
        str(staged_hazards),
    ]
    return distance_cmd, hazard_cmd


def _run_derivatives(
    course_id: int,
    hole_number: int,
    mesh_file: Path,
    distance_target: Path,
    hazard_target: Path,
    identity: str | None = None,
    mesh_digest: str | None = None,
    authority_descriptor: tuple[str, ...] | None = None,
) -> None:
    """Build and atomically publish the optional distance and obstacle derivatives."""
    if mesh_digest is None or authority_descriptor is None:
        try:
            snapshot_identity, snapshot_digest, snapshot_descriptor = _derivative_snapshot(mesh_file)
        except OSError:
            return
        identity = identity or snapshot_identity
        mesh_digest = mesh_digest or snapshot_digest
        authority_descriptor = authority_descriptor or snapshot_descriptor
    if identity is None:
        identity = ""
    key = _derivative_key(
        course_id,
        hole_number,
        mesh_file,
        distance_target,
        hazard_target,
        identity,
    )
    success = False
    error_type = None
    try:
        distance_target.parent.mkdir(parents=True, exist_ok=True)
        hazard_target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _record_derivative_result(key, success=False, error_type=type(exc).__name__)
        return
    try:
        with _DERIVATIVE_PUBLISH_LOCK:
            if _derivative_target_is_current(
                mesh_file, mesh_digest=mesh_digest, authority_descriptor=authority_descriptor
            ):
                previous = load_derivatives_status(mesh_file) or {}
                write_derivatives_status(mesh_file, {
                    "status": "pending", "identity": identity,
                    "failureCount": previous.get("failureCount", 0) if previous.get("identity") == identity else 0,
                    "lastErrorType": previous.get("lastErrorType") if previous.get("identity") == identity else None,
                    "updatedAt": datetime.now(UTC).isoformat(),
                })
        with tempfile.TemporaryDirectory(
            prefix=f"gid{course_id}_h{hole_number:02d}-derivatives-",
            dir=str(distance_target.parent),
        ) as tmp:
            stage = Path(tmp)
            # Snapshot the mesh once.  A later release may replace the canonical file while this
            # worker is still running; reading the live path throughout would let old hazards land
            # beside a new mesh.
            staged_mesh = stage / "meshes.json"
            try:
                staged_mesh.write_bytes(mesh_file.read_bytes())
            except OSError:
                # The mesh may have been replaced or removed while a retry worker was starting.
                # Its identity is no longer current; leave the job unsatisfied for the next
                # ensure request rather than surfacing an exception from a daemon thread.
                return
            staged_distances = stage / "tee_distances.json"
            staged_hazards = stage / "hazards.json"
            distance_cmd, hazard_cmd = _derivative_commands(
                mesh_file=staged_mesh,
                staged_distances=staged_distances,
                staged_hazards=staged_hazards,
            )
            try:
                distance_ok, _ = run(distance_cmd)
            except Exception as exc:
                distance_ok = False
                error_type = type(exc).__name__
            if not distance_ok:
                error_type = error_type or "ExportFailed"
            if distance_ok and staged_distances.is_file():
                with _DERIVATIVE_PUBLISH_LOCK:
                    if _derivative_target_is_current(
                        mesh_file,
                        mesh_digest=mesh_digest,
                        authority_descriptor=authority_descriptor,
                    ):
                        os.replace(staged_distances, distance_target)
            try:
                hazard_ok, _ = run(hazard_cmd)
            except Exception as exc:
                hazard_ok = False
                error_type = type(exc).__name__
            if not hazard_ok:
                error_type = error_type or "ExportFailed"
            if hazard_ok and staged_hazards.is_file():
                with _DERIVATIVE_PUBLISH_LOCK:
                    if _derivative_target_is_current(
                        mesh_file,
                        mesh_digest=mesh_digest,
                        authority_descriptor=authority_descriptor,
                    ):
                        os.replace(staged_hazards, hazard_target)
    finally:
        with _DERIVATIVE_LOCK:
            _DERIVATIVE_JOBS.pop(key, None)
        # Obsolete jobs must never overwrite the newer release's status or prebuild its vectors.
        with _DERIVATIVE_PUBLISH_LOCK:
            current = _derivative_target_is_current(
                mesh_file, mesh_digest=mesh_digest, authority_descriptor=authority_descriptor
            )
            if current:
                success = distance_target.is_file() and hazard_target.is_file()
                _record_derivative_result(key, success=success, error_type=error_type)
        if success:
            # Full factual vectors need BOTH supplements. Keep this off the mesh/topo hand-off.
            from ai_caddie.courses.vector_prep import cached_vector_hole

            try:
                cached_vector_hole(course_id, hole_number)
            except Exception:
                logger.exception("geometry_derivatives vector_failed gid=%s hole=%s", course_id, hole_number)


def _start_derivative_job(
    course_id: int,
    hole_number: int,
    mesh_file: Path,
    distance_target: Path,
    hazard_target: Path,
    *,
    release_identity: dict[str, Any] | None = None,
) -> bool:
    try:
        identity, mesh_digest, authority_descriptor = _derivative_snapshot(
            mesh_file,
            release_identity=release_identity,
        )
    except OSError:
        return False
    key = _derivative_key(
        course_id,
        hole_number,
        mesh_file,
        distance_target,
        hazard_target,
        identity,
    )
    with _DERIVATIVE_LOCK:
        previous = _DERIVATIVE_JOBS.get(key)
        if previous is not None and previous.is_alive():
            return False
        # A changed mesh/release identity starts with a fresh budget.  Drop only older identities
        # for this exact target tuple; unrelated holes and releases keep their own backoff.
        base = key[:-1]
        for old_key in tuple(_DERIVATIVE_FAILURES):
            if old_key[:-1] == base and old_key != key:
                _DERIVATIVE_FAILURES.pop(old_key, None)
        failure = _DERIVATIVE_FAILURES.get(key)
        if failure is not None and time.monotonic() < failure[1]:
            return False
        status = load_derivatives_status(mesh_file) or {}
        if (failure is None and status.get("identity") == identity
                and status.get("status") == "failed"
                and time.time() < float(status.get("retryAfterEpoch") or 0)):
            return False
        worker = threading.Thread(
            target=_run_derivatives,
            args=(
                int(course_id),
                int(hole_number),
                mesh_file,
                distance_target,
                hazard_target,
                identity,
                mesh_digest,
                authority_descriptor,
            ),
            name=f"geometry-derivatives-{course_id}-{hole_number}",
            daemon=True,
        )
        _DERIVATIVE_JOBS[key] = worker
        try:
            worker.start()
        except Exception:
            _DERIVATIVE_JOBS.pop(key, None)
            return False
    return True


def schedule_missing_derivatives(
    course_id: int,
    hole_number: int,
    *,
    mesh_file: Path,
    distance_target: Path,
    hazard_target: Path,
) -> bool:
    """Queue supplements when a prior daemon/process did not finish them.

    This is intentionally safe to call on every cached geometry request.  It repairs a failed
    worker and also repairs the in-memory queue after an API process restart without making the
    request wait for the expensive exports.
    """
    if not mesh_file.is_file():
        return False
    if distance_target.is_file() and hazard_target.is_file():
        return False
    _start_derivative_job(
        course_id,
        hole_number,
        mesh_file,
        distance_target,
        hazard_target,
    )
    return True


def process_hole(
    *,
    course_id: int,
    hole: dict[str, Any],
    profile_id: str,
    snapshot: Path | None,
    skip_overlay: bool,
    force_download: bool,
    defer_derivatives: bool = False,
    derivative_release_identity: dict[str, Any] | None = None,
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
        stage_started = time.perf_counter()
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
        stage_started = _finish_stage(row, "download", stage_started, course_id=course_id)
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
        stage_started = _finish_stage(row, "extract", stage_started, course_id=course_id)

        # Decode privately, then publish the mesh before the slower distance and obstacle
        # derivatives.  The mesh is the first playable artifact and the authority sidecar is
        # recreated by the caller immediately after this function returns.
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
            mesh_target = mesh_json_path(course_id, hole_number)
            stats_target = stats_path(course_id, hole_number)
            distance_target = distances_path(course_id, hole_number)
            hazard_target = hazards_path(course_id, hole_number)

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
            stage_started = _finish_stage(row, "decode", stage_started, course_id=course_id)

            # Never let a derivative from the previous mesh remain authoritative while the new
            # mesh is being installed.  Each replace is atomic; readers see either the previous
            # complete mesh or the new mesh, and the hazard/distance files are then rebuilt.
            with _DERIVATIVE_PUBLISH_LOCK:
                previous_authority = load_authority(authority_path(mesh_target)) or {}
                authority_path(mesh_target).unlink(missing_ok=True)
                derivatives_status_path(mesh_target).unlink(missing_ok=True)
                distance_target.unlink(missing_ok=True)
                hazard_target.unlink(missing_ok=True)
                for staged, target in ((staged_mesh, mesh_target), (staged_stats, stats_target)):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staged, target)
                if derivative_release_identity:
                    installed_authority = {
                        **derivative_release_identity,
                        "geometryZipSha256": row["geometry_zip_sha256"],
                    }
                    if previous_authority.get("cachedCourseDataRoute"):
                        installed_authority["cachedCourseDataRoute"] = previous_authority["cachedCourseDataRoute"]
                    if mesh_output_matches(installed_authority, mesh_file=mesh_target):
                        # Bind before starting fast exporters: even an immediate distance result
                        # must be publishable before ensure_prodgeometry returns to its caller.
                        write_authority(authority_path(mesh_target), installed_authority)
            row["mesh_ready"] = True
            row["steps"]["mesh_install"] = {"ok": True, "files": 2}
            _finish_stage(row, "mesh_install", stage_started, course_id=course_id)
            installed_mesh_digest = file_sha256(mesh_target)

            if defer_derivatives:
                # The on-demand path returns as soon as the mesh can render.  Supplement workers
                # read the canonical mesh and publish each output independently, so a failed
                # obstacle exporter cannot remove or invalidate topo pixels.
                row["steps"]["distances"] = {"ok": None, "pending": True}
                row["steps"]["hazards"] = {"ok": None, "pending": True}
                row["steps"]["install"] = {"ok": True, "files": 2}
                _start_derivative_job(
                    course_id,
                    hole_number,
                    mesh_target,
                    distance_target,
                    hazard_target,
                    release_identity={
                        **(derivative_release_identity or {}),
                        "geometryAssetPath": canonical_asset_path(geometry_url),
                        "geometryAssetVersion": asset_version(canonical_asset_path(geometry_url)),
                        "geometryZipSha256": row.get("geometry_zip_sha256"),
                    },
                )
                row["ok"] = True
                return row

            distance_cmd, hazard_cmd = _derivative_commands(
                mesh_file=mesh_target,
                staged_distances=staged_distances,
                staged_hazards=staged_hazards,
            )
            try:
                ok, out = run(distance_cmd)
            except Exception as exc:
                ok, out = False, str(exc)
            if ok and staged_distances.is_file():
                with _DERIVATIVE_PUBLISH_LOCK:
                    if _derivative_target_is_current(
                        mesh_target,
                        mesh_digest=installed_mesh_digest,
                        authority_descriptor=tuple("" for _ in _DERIVATIVE_AUTHORITY_FIELDS),
                    ):
                        os.replace(staged_distances, distance_target)
            row["steps"]["distances"] = {"ok": ok}
            stage_started = _finish_stage(row, "distances", stage_started, course_id=course_id)

            try:
                ok, out = run(hazard_cmd)
            except Exception as exc:
                ok, out = False, str(exc)
            if ok and staged_hazards.is_file():
                with _DERIVATIVE_PUBLISH_LOCK:
                    if _derivative_target_is_current(
                        mesh_target,
                        mesh_digest=installed_mesh_digest,
                        authority_descriptor=tuple("" for _ in _DERIVATIVE_AUTHORITY_FIELDS),
                    ):
                        os.replace(staged_hazards, hazard_target)
            row["steps"]["hazards"] = {"ok": ok, "output_tail": out.strip().splitlines()[-1:]}
            stage_started = _finish_stage(row, "hazards", stage_started, course_id=course_id)

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

            row["steps"]["install"] = {
                "ok": True,
                "files": 2 + int(distance_target.is_file()) + int(hazard_target.is_file()),
            }
            _finish_stage(row, "install", stage_started, course_id=course_id)

        row["ok"] = bool(row.get("mesh_ready")) and all(
            step.get("ok") for step in row["steps"].values()
        )
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
        if row.get("mesh_ready") and valid_geometry_zip_sha256(row.get("geometry_zip_sha256")):
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
            if mesh_output_matches(authority, mesh_file=mesh_file):
                write_authority(authority_path(mesh_file), authority)
            else:
                row["ok"] = False
                row["error"] = "decoded prodgeometry does not match the release asset authority"
        elif row.get("ok"):
            row["ok"] = False
            row["error"] = "downloaded prodgeometry is missing a real ZIP SHA256"
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
