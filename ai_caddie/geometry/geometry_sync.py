"""On-demand Garmin prodgeometry sync for local AI Caddie requests."""

from __future__ import annotations

import datetime
import json
import threading
from pathlib import Path
from typing import Any

from ai_caddie.geometry.inspect_courseview_release import (
    COURSEVIEW,
    inspect_release,
    load_layout_by_date,
    load_release_pb,
    parse_date_layout,
)

from ai_caddie.geometry.batch_prodgeometry_course import process_hole

from ai_caddie.core.data import ROOT, hazard_path, mesh_path, scorecard_files


# Per-hole locks (P1-6): serialize concurrent ensure() for the SAME hole — so two requests
# never race the same download/extract/write — WITHOUT letting one hung node-subprocess wedge
# geometry for every OTHER hole, which the single global lock did. The registry lock is held
# only long enough to hand out a hole's lock, never across the network/subprocess work.
_REGISTRY_LOCK = threading.Lock()
_HOLE_LOCKS: dict[tuple[int, int], threading.Lock] = {}


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
    return hazard_path(global_id, local_hole).exists() and mesh_path(global_id, local_hole).exists()


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
            pb = load_release_pb(course_id, bool(mode))
            if mode:
                COURSEVIEW.mkdir(parents=True, exist_ok=True)
                (COURSEVIEW / f"{course_id}_releases.pb").write_bytes(pb)
            return inspect_release(pb), "live" if mode else "cache"
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
        if not force and geometry_present(gid, hole_no):
            return {
                "status": "cached",
                "ok": True,
                "globalId": gid,
                "localHole": hole_no,
                "hazards": _display_path(hazard_path(gid, hole_no)),
                "meshes": _display_path(mesh_path(gid, hole_no)),
            }

        profile = profile_id or _player_profile_id()
        if not profile:
            return {
                "status": "failed",
                "ok": False,
                "globalId": gid,
                "localHole": hole_no,
                "error": "playerProfileId not found in local scorecards",
            }

        try:
            try:
                release, release_source = _release(gid, live=True)
            except Exception:
                release, release_source = _release(gid, live=False)
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
            row = process_hole(
                course_id=gid,
                hole=hole,
                profile_id=profile,
                snapshot=None,
                skip_overlay=True,
                force_download=force,
            )
            status = "downloaded" if row.get("ok") else "failed"
            return {
                "status": status,
                "ok": bool(row.get("ok")),
                "globalId": gid,
                "localHole": hole_no,
                "releaseSource": release_source,
                "releaseId": release.get("release_id"),
                "courseName": release.get("course_name"),
                "hazards": _display_path(hazard_path(gid, hole_no)),
                "meshes": _display_path(mesh_path(gid, hole_no)),
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
