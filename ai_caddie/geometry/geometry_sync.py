"""On-demand Garmin prodgeometry sync for local AI Caddie requests."""

from __future__ import annotations

import datetime
import json
import threading
import time
from pathlib import Path
from typing import Any

from ai_caddie.core.data import ROOT, hazard_path, mesh_path, scorecard_files
from ai_caddie.courses import course_reference
from ai_caddie.geometry.batch_prodgeometry_course import (
    derivative_state as _derivative_state,
    distances_path,
    process_hole,
    schedule_missing_derivatives,
)
from ai_caddie.geometry.geometry_authority import (
    authority_is_bound,
    authority_path,
    build_authority,
    load_authority,
    mesh_output_matches,
    same_geometry_content,
    same_release_binding,
    valid_geometry_zip_sha256,
    write_authority,
)
from ai_caddie.geometry.inspect_courseview_release import (
    COURSEVIEW,
    GARMIN_OMT_SIMPLIFIED_CHINESE,
    inspect_valid_release,
    load_layout_by_date,
    load_release_pb,
    parse_date_layout,
)


# Per-hole locks (P1-6): serialize concurrent ensure() for the SAME hole — so two requests
# never race the same download/extract/write — WITHOUT letting one hung node-subprocess wedge
# geometry for every OTHER hole, which the single global lock did. The registry lock is held
# only long enough to hand out a hole's lock, never across the network/subprocess work.
_REGISTRY_LOCK = threading.Lock()
_HOLE_LOCKS: dict[tuple[int, int], threading.Lock] = {}
_RELEASE_MEMORY: dict[int, tuple[float, dict[str, Any], str]] = {}

# Release URLs contain expiring asset signatures.  Refresh at most hourly per
# course; one in-process memory entry prevents an 18-hole install from issuing
# the same release request 18 times.
RELEASE_REFRESH_MAX_AGE_S = 3600.0
RELEASE_MEMORY_MAX_AGE_S = 300.0


def _hole_lock(global_id: int, local_hole: int) -> threading.Lock:
    key = (int(global_id), int(local_hole))
    with _REGISTRY_LOCK:
        lock = _HOLE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _HOLE_LOCKS[key] = lock
        return lock


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def geometry_present(global_id: int, local_hole: int) -> bool:
    # The decoded mesh is independently playable by topo/green.  Obstacle and distance exports
    # are supplements and may still be running (or may have failed) without invalidating pixels.
    return mesh_path(global_id, local_hole).exists()


def _schedule_missing_derivatives(
    global_id: int,
    local_hole: int,
    *,
    mesh_file: Path,
    hazard_file: Path,
) -> bool:
    """Repair a supplement worker after a failure or API process restart."""
    return schedule_missing_derivatives(
        int(global_id),
        int(local_hole),
        mesh_file=mesh_file,
        distance_target=distances_path(int(global_id), int(local_hole)),
        hazard_target=hazard_file,
    )


def derivative_state(global_id: int, local_hole: int) -> dict[str, Any]:
    """Supplement (distance/obstacle) state of one installed hole; never starts work."""
    gid, hole_no = int(global_id), int(local_hole)
    return _derivative_state(
        gid,
        hole_no,
        mesh_file=mesh_path(gid, hole_no),
        distance_target=distances_path(gid, hole_no),
        hazard_target=hazard_path(gid, hole_no),
    )


def schedule_derivatives(global_id: int, local_hole: int) -> dict[str, Any]:
    """Start a due supplement export for an installed mesh and return the resulting state.

    The backoff in the derivative lane is still authoritative: a hole whose last failure is not yet
    due stays ``retrying`` and nothing is submitted.
    """
    gid, hole_no = int(global_id), int(local_hole)
    if derivative_state(gid, hole_no).get("state") == "due":
        _schedule_missing_derivatives(
            gid, hole_no, mesh_file=mesh_path(gid, hole_no), hazard_file=hazard_path(gid, hole_no)
        )
    return derivative_state(gid, hole_no)


def _release_cache_is_fresh(course_id: int) -> bool:
    fetched_at = course_reference.release_cache_fetched_at(
        course_id,
        root=COURSEVIEW.parent.parent,
    )
    return fetched_at is not None and time.time() - fetched_at <= RELEASE_REFRESH_MAX_AGE_S


def _player_profile_id() -> str | None:
    for path in scorecard_files():
        try:
            data = json.loads(path.read_text())
            value = data["scorecardDetails"][0]["scorecard"].get("playerProfileId")
            if value:
                return str(value)
        except Exception:
            continue
    return None


def _round_ts_ms(course_id: int) -> int | None:
    """Epoch-ms of a stored round on this course (latest wins) — used to fetch the CourseView layout
    AS OF a play date when the ``/releases/`` (latest) endpoint 404s on a withdrawn-latest course."""
    best: int | None = None
    for path in scorecard_files():
        try:
            sc = json.loads(path.read_text())["scorecardDetails"][0]["scorecard"]
            ids = {sc.get("courseGlobalId"), sc.get("frontNineGlobalCourseId"), sc.get("backNineGlobalCourseId")}
            if course_id not in ids:
                continue
            raw = sc.get("startTime") or sc.get("formattedStartTime")
            if not raw:
                continue
            dt = datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            ms = int(dt.timestamp() * 1000)
            best = ms if best is None else max(best, ms)
        except Exception:
            continue
    return best


def _release(course_id: int, *, live: bool | None = None) -> tuple[dict[str, Any], str]:
    errors: list[str] = []
    modes = (live,) if live is not None else (False, True)
    for mode in modes:
        try:
            pb = load_release_pb(
                course_id,
                bool(mode),
                language_code=GARMIN_OMT_SIMPLIFIED_CHINESE,
            )
            release = inspect_valid_release(pb, expected_course_id=course_id)
            if mode:
                course_reference.save_release_pb(
                    course_id,
                    pb,
                    root=COURSEVIEW.parent.parent,
                )
            return release, "live" if mode else "cache"
        except Exception as exc:
            errors.append(f"{'live' if mode else 'cache'}: {exc}")
    # Fallback: the LATEST release is gone (404) but the course still exists (an old course whose
    # newest release Garmin withdrew). Fetch the historical layout AS OF a stored round's play date —
    # exactly what the Garmin app does; it still serves the withdrawn-latest course's geometry.
    ts = _round_ts_ms(course_id)
    if ts is not None:
        try:
            layout = parse_date_layout(load_layout_by_date(course_id, ts))
            if layout.get("holes"):
                return layout, f"date:{ts}"
            errors.append("date: no geometry URLs in layout")
        except Exception as exc:
            errors.append(f"date: {exc}")
    raise RuntimeError("; ".join(errors))


def _release_for_update(course_id: int, *, force: bool = False) -> tuple[dict[str, Any], str]:
    """Current release with bounded network traffic and stale-cache fallback."""
    gid = int(course_id)
    now = time.monotonic()
    with _REGISTRY_LOCK:
        cached = _RELEASE_MEMORY.get(gid)
    if not force and cached is not None and now - cached[0] <= RELEASE_MEMORY_MAX_AGE_S:
        return cached[1], cached[2]

    # Hole 0 is reserved as this course's release singleflight lock.  Different
    # courses still refresh independently; concurrent holes of one course share it.
    with _hole_lock(gid, 0):
        now = time.monotonic()
        with _REGISTRY_LOCK:
            cached = _RELEASE_MEMORY.get(gid)
        if not force and cached is not None and now - cached[0] <= RELEASE_MEMORY_MAX_AGE_S:
            return cached[1], cached[2]

        if not force and _release_cache_is_fresh(gid):
            try:
                release, source = _release(gid, live=False)
                source = "cache:fresh"
            except Exception:
                # A recently written but unreadable legacy cache must not
                # suppress a live self-heal for the rest of the hour.
                release, source = _release(gid, live=True)
        else:
            try:
                release, source = _release(gid, live=True)
            except Exception:
                release, source = _release(gid, live=False)
                source = "cache:stale"
        with _REGISTRY_LOCK:
            _RELEASE_MEMORY[gid] = (time.monotonic(), release, source)
        return release, source


def ensure_prodgeometry(
    global_id: int,
    local_hole: int,
    *,
    profile_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    gid = int(global_id)
    hole_no = int(local_hole)
    with _hole_lock(gid, hole_no):
        mesh_file = mesh_path(gid, hole_no)
        hazard_file = hazard_path(gid, hole_no)
        sidecar = authority_path(mesh_file)
        current = load_authority(sidecar)
        files_exist = geometry_present(gid, hole_no)
        current_is_bound = authority_is_bound(
            current,
            global_id=gid,
            local_hole=hole_no,
            mesh_file=mesh_file,
            hazard_file=hazard_file,
        )

        def cached_result(*, release_source: str | None, authority_state: str) -> dict[str, Any]:
            return {
                "status": "cached",
                "ok": True,
                "globalId": gid,
                "localHole": hole_no,
                "releaseSource": release_source,
                "hazards": _display_path(hazard_file),
                "meshes": _display_path(mesh_file),
                "authority": _display_path(sidecar) if sidecar.exists() else None,
                "authorityState": authority_state,
            }

        try:
            try:
                release, release_source = _release_for_update(gid, force=force)
            except Exception:
                # Offline use must keep working.  A previously bound artifact is
                # trustworthy without a live update check; a legacy pair remains
                # usable but visibly unbound until the provider is reachable.
                if files_exist:
                    if current_is_bound:
                        _schedule_missing_derivatives(
                            gid,
                            hole_no,
                            mesh_file=mesh_file,
                            hazard_file=hazard_file,
                        )
                    return cached_result(
                        release_source=None,
                        authority_state="bound-stale" if current_is_bound else "legacy-unbound",
                    )
                raise
            hole = next((h for h in release.get("holes", []) if int(h.get("hole") or -1) == hole_no), None)
            if not hole:
                return {
                    "status": "failed",
                    "ok": False,
                    "globalId": gid,
                    "localHole": hole_no,
                    "releaseSource": release_source,
                    "error": "hole not found in CourseView release",
                }
            expected = build_authority(
                global_id=gid,
                local_hole=hole_no,
                release=release,
                hole=hole,
                release_source=release_source,
                geometry_zip_sha256=(current or {}).get("geometryZipSha256")
                if current_is_bound
                else None,
            )

            if not force and files_exist:
                # Matching embedded ids/version are enough to keep legacy pixels available
                # offline, but not enough to claim current provider authority.  Only an authority
                # with the real ZIP digest may take this fast path; legacy outputs are downloaded
                # and verified once below to acquire that digest.
                reusable = (
                    current_is_bound
                    and current is not None
                    and same_geometry_content(current, expected)
                )
                if reusable:
                    if current is None or not same_release_binding(current, expected):
                        write_authority(sidecar, expected)
                    _schedule_missing_derivatives(
                        gid,
                        hole_no,
                        mesh_file=mesh_file,
                        hazard_file=hazard_file,
                    )
                    return cached_result(release_source=release_source, authority_state="bound")

            profile = profile_id or _player_profile_id()
            if not profile:
                return {
                    "status": "failed",
                    "ok": False,
                    "globalId": gid,
                    "localHole": hole_no,
                    "releaseSource": release_source,
                    "error": "playerProfileId not found in local scorecards",
                }
            row = process_hole(
                course_id=gid,
                hole=hole,
                profile_id=profile,
                snapshot=None,
                skip_overlay=True,
                force_download=force,
                defer_derivatives=True,
                derivative_release_identity=expected,
            )
            zip_sha256 = row.get("geometry_zip_sha256")
            row_ok = bool(row.get("ok")) and valid_geometry_zip_sha256(zip_sha256)
            if row.get("ok") and not row_ok:
                row["error"] = "downloaded prodgeometry is missing a real ZIP SHA256"
            if row_ok:
                expected = build_authority(
                    global_id=gid,
                    local_hole=hole_no,
                    release=release,
                    hole=hole,
                    release_source=release_source,
                    geometry_zip_sha256=zip_sha256,
                )
                row_ok = mesh_output_matches(expected, mesh_file=mesh_file)
                if row_ok:
                    installed = load_authority(sidecar)
                    if (not installed or not same_release_binding(installed, expected)
                            or installed.get("geometryZipSha256") != zip_sha256):
                        write_authority(sidecar, expected)
                    # Also supports legacy/test installers that did not bind before starting the
                    # daemon. Avoid rewriting an identical sidecar after vectors fingerprint it.
                    _schedule_missing_derivatives(
                        gid,
                        hole_no,
                        mesh_file=mesh_file,
                        hazard_file=hazard_file,
                    )
                else:
                    sidecar.unlink(missing_ok=True)
                    row["error"] = "decoded prodgeometry does not match the release asset authority"
            status = "downloaded" if row_ok else "failed"
            return {
                "status": status,
                "ok": row_ok,
                "globalId": gid,
                "localHole": hole_no,
                "releaseSource": release_source,
                "releaseId": release.get("release_id"),
                "courseName": release.get("course_name"),
                "hazards": _display_path(hazard_file),
                "meshes": _display_path(mesh_file),
                "authority": _display_path(sidecar) if sidecar.exists() else None,
                "authorityState": "bound" if row_ok else "invalid",
                "steps": row.get("steps", {}),
                **({"error": row.get("error")} if row.get("error") else {}),
            }
        except Exception as exc:
            return {
                "status": "failed",
                "ok": False,
                "globalId": gid,
                "localHole": hole_no,
                "error": str(exc),
            }
