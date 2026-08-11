"""Per-hole shot map for round review (复盘).

Projects THIS round's actual shot positions onto the hole's 2D top-down render (the same server
image + overlay frame the live/prep maps use), so the player can open a hole and see where each
ball went — tee → landing → … → green — instead of only the scorecard number.

Reuses the calibrated projection chain (mean 0.04 m error): shot lat/lon (already degrees in the
normalized shot rows) → hole-local metres → overlay pixels via
``shot_projection.project_world_to_pixel`` + ``hole_render.overlay_projector`` (the SAME transform
``render_hole`` used for ``overlay['route']``, so dots align by construction).

Auto-complete: if the drive wasn't recorded (no shot starting on the tee box) a synthetic tee shot
is added from the tee (route[0]) so every hole shows a shot off the tee; synthetic rows are flagged
so the client can render them faded/dashed and 复盘 stays honest about what is real vs inferred.
"""
from __future__ import annotations

import base64
import math
from typing import Any

from ai_caddie.core.data import clean_club_name
from ai_caddie.courses import course_prep
from ai_caddie.geometry import hole_render, shot_projection, topo_render
from ai_caddie.geometry.geometry_evidence import geometry_coverage_for_hole
from ai_caddie.history.history import HistoryData
from ai_caddie.rounds import round_corrections

SCHEMA = "ai-caddie-round-hole-shotmap-v1"


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _geometry_target(row: dict[str, Any], hole: int) -> tuple[int | None, int]:
    """Physical (globalId, localHole) for a display hole number — front/back-nine aware (a composite
    18 plays its back nine from a second loop's gid)."""
    if hole <= 9:
        gid = _int(row.get("frontNineGlobalCourseId")) or _int(row.get("globalId")) or _int(row.get("courseId"))
        return gid, hole
    back = _int(row.get("backNineGlobalCourseId"))
    if back is not None:
        return back, hole - 9
    return _int(row.get("globalId")) or _int(row.get("courseId")) or _int(row.get("frontNineGlobalCourseId")), hole


def _round_ids(row: dict[str, Any]) -> set[str]:
    return {str(row.get("id"))} | {str(item) for item in (row.get("ids") or [])}


def _match_round(data: HistoryData, round_ref: str) -> dict[str, Any] | None:
    ref = str(round_ref).strip()
    for row in data.rounds:
        if ref in _round_ids(row):
            return row
    return None


def _par_for(row: dict[str, Any], hole: int) -> int | None:
    pars = str(row.get("holePars") or "")
    if 1 <= hole <= len(pars):
        return _int(pars[hole - 1])
    for entry in row.get("holes") or []:
        if isinstance(entry, dict) and _int(entry.get("number")) == hole:
            return _int(entry.get("par"))
    return None


def _display_hole_for_shot(row: dict[str, Any], shot: dict[str, Any]) -> int | None:
    """Map a member scorecard's physical hole to the merged round's display hole."""
    source_hole = _int(shot.get("hole"))
    if source_hole is None:
        return None
    ids = [str(value) for value in (row.get("ids") or [row.get("id")])]
    source_id = str(shot.get("scorecardId") or shot.get("roundId") or "")
    if row.get("merged") and len(ids) >= 2 and source_id == ids[1]:
        return source_hole + 9
    return source_hole


def _source_shots_for_hole(
    data: HistoryData,
    row: dict[str, Any],
    hole: int,
    corrections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Select source shots before map preparation, keeping GPS independent from geometry."""
    round_ids = _round_ids(row)
    selected: list[dict[str, Any]] = []
    for source in data.shots:
        source_id = str(source.get("scorecardId") or source.get("roundId") or "")
        display_hole = _display_hole_for_shot(row, source)
        if source_id not in round_ids or display_hole != hole:
            continue
        shot = dict(source)
        shot["localHole"] = shot.get("localHole") or _int(shot.get("hole"))
        shot["hole"] = display_hole
        selected.append(shot)
    selected.sort(key=lambda shot: _int(shot.get("order")) or 0)
    return round_corrections.apply_corrections(selected, corrections, hole=hole)


def _unprojected_shot_rows(shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retain honest per-shot facts when no factual map frame is available yet."""
    rows: list[dict[str, Any]] = []
    for shot in shots:
        start = shot.get("start") if isinstance(shot.get("start"), dict) else {}
        end = shot.get("end") if isinstance(shot.get("end"), dict) else {}
        row = {
            "id": round_corrections.mint_shot_id(shot),
            "start": None,
            "end": None,
            "club": clean_club_name(shot.get("clubName")),
            "lie": start.get("lie"),
            "endLie": shot.get("endLie"),
            "shotType": shot.get("type"),
            "order": _int(shot.get("_displayOrder")) or _int(shot.get("order")),
            "synthetic": False,
            "gpsAvailable": all(
                value is not None
                for value in (
                    start.get("lat"), start.get("lon"), end.get("lat"), end.get("lon")
                )
            ),
        }
        if shot.get("clubSource") == "manual":
            row["clubSource"] = "manual"
        if shot.get("lieSource") == "manual":
            row["lieSource"] = "manual"
        rows.append(row)
    return rows


def _lightweight_map_frame(
    global_id: int,
    local_hole: int,
) -> tuple[dict[str, Any], Any, Any] | None:
    """Build a factual CourseView-only overlay and WGS84 affine projection.

    This is not a fabricated hole outline: it uses Garmin CourseView's cached route and the exact
    three geo/pixel anchors already shipped to phone and watch while prodgeometry is preparing.
    """
    try:
        prep = course_prep.lightweight_prep_hole(int(global_id), int(local_hole))
        route = prep.get("route") if isinstance(prep, dict) else None
        projection = prep.get("holeImageProjection") if isinstance(prep, dict) else None
        refs = projection.get("refs") if isinstance(projection, dict) else None
        width = int(projection.get("widthPx") or 0) if isinstance(projection, dict) else 0
        height = int(projection.get("heightPx") or 0) if isinstance(projection, dict) else 0
        if not isinstance(route, list) or len(route) < 2 or not isinstance(refs, list) or len(refs) < 3:
            return None
        origin, x_ref, y_ref = refs[:3]
        x_basis = (
            (float(x_ref["px"]) - float(origin["px"])) / 120.0,
            (float(x_ref["py"]) - float(origin["py"])) / 120.0,
        )
        y_basis = (
            (float(y_ref["px"]) - float(origin["px"])) / 120.0,
            (float(y_ref["py"]) - float(origin["py"])) / 120.0,
        )
        pixels = []
        for item in route:
            if not isinstance(item, list) or len(item) < 2:
                return None
            local_x, local_y = float(item[0]), float(item[1])
            pixels.append(
                [
                    float(origin["px"]) + local_x * x_basis[0] + local_y * y_basis[0],
                    float(origin["py"]) + local_x * x_basis[1] + local_y * y_basis[1],
                    float(item[2]) if len(item) >= 3 else 0.0,
                ]
            )
        ppm = (math.hypot(*x_basis) + math.hypot(*y_basis)) / 2.0
        if width <= 0 or height <= 0 or ppm <= 0:
            return None
        overlay = {
            "w": width,
            "h": height,
            "ppm": ppm,
            "ln": float(prep.get("route_len_m") or pixels[-1][2]),
            "route": pixels,
        }

        def project(location: dict[str, Any] | None) -> list[int] | None:
            if not location or location.get("lat") is None or location.get("lon") is None:
                return None
            a = float(x_ref["lon"]) - float(origin["lon"])
            b = float(y_ref["lon"]) - float(origin["lon"])
            c = float(x_ref["lat"]) - float(origin["lat"])
            d = float(y_ref["lat"]) - float(origin["lat"])
            determinant = a * d - b * c
            if abs(determinant) <= 1e-12:
                return None
            dlon = float(location["lon"]) - float(origin["lon"])
            dlat = float(location["lat"]) - float(origin["lat"])
            s = (dlon * d - b * dlat) / determinant
            t = (a * dlat - dlon * c) / determinant
            px = float(origin["px"]) + s * (float(x_ref["px"]) - float(origin["px"])) + t * (float(y_ref["px"]) - float(origin["px"]))
            py = float(origin["py"]) + s * (float(x_ref["py"]) - float(origin["py"])) + t * (float(y_ref["py"]) - float(origin["py"]))
            return [min(max(int(round(px)), 0), width - 1), min(max(int(round(py)), 0), height - 1)]

        def unproject(px: float, py: float) -> tuple[float, float]:
            a = float(x_ref["px"]) - float(origin["px"])
            b = float(y_ref["px"]) - float(origin["px"])
            c = float(x_ref["py"]) - float(origin["py"])
            d = float(y_ref["py"]) - float(origin["py"])
            determinant = a * d - b * c
            if abs(determinant) <= 1e-12:
                raise ValueError("degenerate lightweight projection")
            dx, dy = float(px) - float(origin["px"]), float(py) - float(origin["py"])
            s = (dx * d - b * dy) / determinant
            t = (a * dy - dx * c) / determinant
            latitude = float(origin["lat"]) + s * (float(x_ref["lat"]) - float(origin["lat"])) + t * (float(y_ref["lat"]) - float(origin["lat"]))
            longitude = float(origin["lon"]) + s * (float(x_ref["lon"]) - float(origin["lon"])) + t * (float(y_ref["lon"]) - float(origin["lon"]))
            return latitude, longitude

        return overlay, project, unproject
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _pixel_pair(value: Any, width: int, height: int) -> list[int] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    try:
        x = int(round(float(value[0])))
        y = int(round(float(value[1])))
    except (TypeError, ValueError, OverflowError):
        return None
    return [min(max(x, 0), max(width - 1, 0)), min(max(y, 0), max(height - 1, 0))]


def _reconnect_pixel_shots(rows: list[dict[str, Any]], tee_px: list[int] | None) -> None:
    """Make list order and map lines one fact after any draft reorder/delete/add."""
    previous_end: list[int] | None = None
    for index, shot in enumerate(rows):
        if index == 0:
            shot["start"] = shot.get("start") or tee_px
        elif previous_end is not None:
            shot["start"] = list(previous_end)
        shot["order"] = index + 1
        previous_end = shot.get("end") if isinstance(shot.get("end"), list) else None


def _snapshot_pixel_shots(
    event: dict[str, Any],
    *,
    width: int,
    height: int,
    tee_px: list[int] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(event.get("shots") or []):
        if not isinstance(raw, dict):
            continue
        shot_id = str(raw.get("id") or "").strip()
        if not shot_id:
            # Validation rejects this for new writes; a defensive read fallback keeps an older/corrupt
            # line from making the whole historical round unavailable.
            shot_id = f"snapshot:{event.get('seq', 0)}:{index}"
        rows.append(
            {
                "id": shot_id,
                "start": _pixel_pair(raw.get("start"), width, height),
                "end": _pixel_pair(raw.get("end"), width, height),
                "club": clean_club_name(raw.get("club")),
                "lie": raw.get("lie"),
                "endLie": raw.get("endLie"),
                "shotType": raw.get("shotType"),
                "order": index + 1,
                "clubSource": raw.get("clubSource"),
                "lieSource": raw.get("lieSource"),
                "synthetic": bool(raw.get("synthetic", False)),
            }
        )
    _reconnect_pixel_shots(rows, tee_px)
    return rows


def _apply_post_snapshot_ops(
    rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    hole: int,
    width: int,
    height: int,
    tee_px: list[int] | None,
) -> list[dict[str, Any]]:
    """Keep older granular clients usable after a new whole-hole snapshot has been saved."""
    removed: dict[str, tuple[int, dict[str, Any]]] = {}
    for event in events:
        event_hole = _int(event.get("hole"))
        if event_hole is not None and event_hole != hole:
            continue
        op = event.get("op")
        shot_id = str(event.get("shotId") or "")
        index = next((i for i, shot in enumerate(rows) if shot.get("id") == shot_id), None)

        if op == "editField" and index is not None:
            field = event.get("field")
            if field == "club":
                rows[index]["club"] = clean_club_name(event.get("value"))
                rows[index]["clubSource"] = "manual"
            elif field == "lie":
                rows[index]["lie"] = event.get("value")
                rows[index]["lieSource"] = "manual"
            elif field == "position":
                moved = _pixel_pair(event.get("value"), width, height)
                if moved is not None:
                    rows[index]["end"] = moved
        elif op == "deleteShot" and index is not None:
            removed[shot_id] = (index, rows.pop(index))
        elif op == "restoreShot" and shot_id in removed:
            old_index, restored = removed.pop(shot_id)
            rows.insert(min(old_index, len(rows)), restored)
        elif op == "reorderShot" and isinstance(event.get("order"), list):
            by_id = {str(shot.get("id")): shot for shot in rows}
            ordered = [by_id.pop(str(value)) for value in event["order"] if str(value) in by_id]
            if ordered:
                rows = [*ordered, *[shot for shot in rows if str(shot.get("id")) in by_id]]
        elif op == "addShot":
            after = str(event.get("insertAfterShotId") or "")
            # Legacy addShot omitted hole. It is safe to infer the current hole only from a stable
            # anchor already present here; an unanchored legacy event is ambiguous and must not leak
            # into all 18 holes.
            if event_hole is None and (not after or not any(shot.get("id") == after for shot in rows)):
                continue
            end = _pixel_pair(event.get("px"), width, height)
            if end is None:
                continue
            insert_at = len(rows)
            if after:
                anchor = next((i for i, shot in enumerate(rows) if shot.get("id") == after), None)
                if anchor is not None:
                    insert_at = anchor + 1
            new_id = shot_id or f"legacy-add:{event.get('seq', len(rows) + 1)}"
            rows.insert(
                insert_at,
                {
                    "id": new_id,
                    "start": None,
                    "end": end,
                    "club": clean_club_name(event.get("club")),
                    "lie": event.get("lie"),
                    "endLie": None,
                    "shotType": "MANUAL",
                    "order": insert_at + 1,
                    "synthetic": False,
                },
            )
        _reconnect_pixel_shots(rows, tee_px)
    return rows


def build_round_hole_shot_map(
    data: HistoryData, round_ref: str, hole: int,
    corrections: list[dict[str, Any]] | None = None,
    *,
    include_image: bool = True,
) -> dict[str, Any]:
    hole = _int(hole) or 0
    row = _match_round(data, round_ref)
    if row is None or hole < 1:
        return {"schema": SCHEMA, "found": False, "roundRef": str(round_ref), "hole": hole, "map": None, "shots": [],
                "missingData": [{"label": "round", "reason": f"{round_ref} 第 {hole} 洞没找到"}]}

    gid, local = _geometry_target(row, hole)
    par = _par_for(row, hole)
    corr = corrections or []
    manual_penalty = round_corrections.hole_penalty(corr, hole)
    shots = _source_shots_for_hole(data, row, hole, corr)
    geometry_revision: str | None = None
    map_kind: str | None = None
    missing_data: list[dict[str, Any]] = []
    uses_lightweight_frame = False
    project: Any
    unproject: Any
    try:
        current_geometry = geometry_coverage_for_hole(
            int(gid),
            int(local),
            require_current_authority=True,
            # History review is a read path. Never make opening a played hole wait on a Garmin
            # release request; use the cached release binding and fall back to the last complete
            # local frame below. Course selection/download owns remote release refreshes.
            refresh_release=False,
        )
        geometry_evidence = current_geometry
        if current_geometry.get("coverage") != "ready":
            # A Garmin release change invalidates a pixel snapshot, but it must not erase source GPS.
            # Existing mesh/hazard files remain a valid geographic projection for WGS84 source shots;
            # use them as a visibly stale base until the selected course download installs the update.
            geometry_evidence = geometry_coverage_for_hole(
                int(gid),
                int(local),
                require_current_authority=False,
                refresh_release=False,
            )
            if geometry_evidence.get("coverage") != "ready":
                raise ValueError("no complete local geometry")
            missing_data.append(
                {
                    "label": "geometry_authority",
                    "reason": "球场地图正在更新；当前显示上次可用地图，GPS 落点不受影响",
                }
            )
        geometry_revision = (
            str(geometry_evidence.get("geometryRevision"))
            if geometry_evidence.get("geometryRevision")
            else None
        )
        md, by = hole_render.load_mesh(int(gid), int(local))
        route, route_len = course_prep.derive_route(md)
        if not route or not route_len:
            raise ValueError("no route")
        overlay = hole_render.render_hole_overlay(int(gid), int(local), route, route_len)
        # Legacy/web callers may still ask for an embedded fallback. Native round browsing uses the
        # revision-bound /topo.png authority instead: embedding the same PNG in each shot-map JSON
        # and then downloading it again doubled an 18-hole transfer and defeated URL caching.
        image = None
        if include_image:
            try:
                _topo_png = topo_render.render_hole_topo_cached(int(gid), int(local))
                image = "data:image/png;base64," + base64.b64encode(_topo_png).decode()
            except Exception:
                image = None
        ref_lat = float((md.get("hole") or {})["RefLat"])
        ref_lon = float((md.get("hole") or {})["RefLon"])
        to_px = hole_render.overlay_projector(by, route)
        width, height = int(overlay["w"]), int(overlay["h"])

        def project_precise(loc: dict[str, Any] | None) -> list[int] | None:
            if not loc or loc.get("lat") is None or loc.get("lon") is None:
                return None
            px, py = shot_projection.project_world_to_pixel(
                float(loc["lat"]),
                float(loc["lon"]),
                ref_lat=ref_lat,
                ref_lon=ref_lon,
                to_px=to_px,
            )
            return [
                min(max(int(round(px)), 0), width - 1),
                min(max(int(round(py)), 0), height - 1),
            ]

        from_px = hole_render.overlay_unprojector(by, route)

        def unproject_precise(px: float, py: float) -> tuple[float, float]:
            return shot_projection.pixel_to_world(
                float(px),
                float(py),
                ref_lat=ref_lat,
                ref_lon=ref_lon,
                from_px=from_px,
            )

        project = project_precise
        unproject = unproject_precise
        map_kind = "prodgeometry"
    except Exception:
        lightweight = (
            _lightweight_map_frame(int(gid), int(local))
            if gid is not None and local is not None
            else None
        )
        if lightweight is None:
            available = _unprojected_shot_rows(shots)
            reason = (
                f"已保留 {sum(1 for shot in available if shot.get('gpsAvailable'))} 杆 GPS；"
                "球场地图素材正在准备"
                if available
                else "这一洞没有可显示的逐杆 GPS"
            )
            return {
                "schema": SCHEMA,
                "found": True,
                "roundRef": str(row.get("id")),
                "hole": hole,
                "par": par,
                "globalId": int(gid) if gid is not None else None,
                "localHole": int(local) if local is not None else None,
                "mapKind": None,
                "map": None,
                "shots": available,
                "manualPenalty": manual_penalty,
                "missingData": [{"label": "geometry", "reason": reason}],
            }
        overlay, project, unproject = lightweight
        width, height = int(overlay["w"]), int(overlay["h"])
        image = None
        uses_lightweight_frame = True
        map_kind = "courseData"
        missing_data.append(
            {
                "label": "geometry",
                "reason": "精确球场底图准备中；当前按 Garmin CourseView 路线显示真实 GPS 落点",
            }
        )

    tee_px = [
        int(round(overlay["route"][0][0])),
        int(round(overlay["route"][0][1])),
    ] if overlay.get("route") else None
    snapshot = round_corrections.latest_hole_snapshot(corr, hole)
    fact_snapshot = round_corrections.latest_hole_fact_snapshot(corr, hole)
    post_fact_corrections = (
        corr[fact_snapshot[0] + 1 :]
        if fact_snapshot is not None
        else corr
    )
    pixel_snapshot = (
        snapshot
        if snapshot is not None and snapshot[1].get("op") == "replaceHoleShots"
        else None
    )
    if pixel_snapshot is not None:
        snapshot_index, snapshot_event = pixel_snapshot
        raw_snapshot_revision = snapshot_event.get("geometryRevision")
        snapshot_revision = (
            str(raw_snapshot_revision).strip()
            if raw_snapshot_revision is not None and str(raw_snapshot_revision).strip()
            else None
        )
        # Whole-hole edits are pixel snapshots. They are authoritative only in the exact geometry
        # frame in which the user approved them. Legacy snapshots carried no revision, so retain
        # their historical behaviour; a known mismatch must fall back to freshly projected source
        # shots instead of clamping old pixels into a new Garmin release.
        if not uses_lightweight_frame and (
            snapshot_revision is None or snapshot_revision == geometry_revision
        ):
            plotted = _snapshot_pixel_shots(
                snapshot_event,
                width=width,
                height=height,
                tee_px=tee_px,
            )
            plotted = _apply_post_snapshot_ops(
                plotted,
                corr[snapshot_index + 1 :],
                hole=hole,
                width=width,
                height=height,
                tee_px=tee_px,
            )
            return {
                "schema": SCHEMA,
                "found": True,
                "roundRef": str(row.get("id")),
                "hole": hole,
                "par": par,
                "globalId": int(gid) if gid is not None else None,
                "localHole": int(local),
                "geometryRevision": geometry_revision,
                "mapKind": map_kind,
                "map": {"image": image, "overlay": overlay},
                "shots": plotted,
                "manualPenalty": manual_penalty,
                "missingData": missing_data,
            }

    # addShot(点地图加杆):px 反投影成世界坐标,造一杆合成落点插进顺序;shotmap 按序画线自动连前后。
    # 空洞(shots 为空)也能加 → 永不变砖。
    _added = 0
    for e in post_fact_corrections:
        if uses_lightweight_frame:
            continue
        if e.get("op") != "addShot":
            continue
        added_index = _added
        _added += 1
        px = e.get("px") or []
        if len(px) != 2:
            continue
        event_hole = _int(e.get("hole"))
        if event_hole is not None and event_hole != hole:
            continue
        after = e.get("insertAfterShotId")
        # Before whole-hole drafts, addShot carried no hole. Infer it from its stable predecessor;
        # never replay an unscoped add into every hole.
        if event_hole is None and (
            not after
            or not any(round_corrections.mint_shot_id(shot) == after for shot in shots)
        ):
            continue
        lat, lon = unproject(float(px[0]), float(px[1]))
        idx = 0
        if after:
            for i, s in enumerate(shots):
                if round_corrections.mint_shot_id(s) == after:
                    idx = i + 1
                    break
        prev = shots[idx - 1] if idx > 0 else None
        start = dict(prev.get("end") or {}) if prev else {"lat": lat, "lon": lon}
        added_shot = {
            "id": f"m{added_index}", "scorecardId": str(row.get("id")), "hole": hole,
            "order": (prev.get("order") if prev else 0),
            "start": {**start, "lie": e.get("lie")}, "end": {"lat": lat, "lon": lon},
            "endLie": None, "clubName": e.get("club"), "type": "MANUAL", "manualAdded": True,
        }
        shots.insert(idx, added_shot)
        # The inserted landing is the next shot's physical origin. Keep that next shot's recorded lie
        # but reconnect its coordinates, matching the optimistic iOS route and surviving a refetch.
        if idx + 1 < len(shots):
            next_start = dict(shots[idx + 1].get("start") or {})
            shots[idx + 1]["start"] = {**next_start, "lat": lat, "lon": lon, "posSource": "manual"}

    # editField position(拖动改落点):px 反投影成世界坐标,改这一杆的 end。作用于原始杆 + 手动加的杆。
    pos_edits: dict[str, list[Any]] = {}
    for e in post_fact_corrections:
        if uses_lightweight_frame:
            continue
        if e.get("op") == "editField" and e.get("field") == "position" and e.get("shotId"):
            v = e.get("value") or []
            if len(v) == 2:
                pos_edits[str(e["shotId"])] = v
    if pos_edits:
        for index, s in enumerate(shots):
            v = pos_edits.get(round_corrections.mint_shot_id(s))
            if v:
                lat, lon = unproject(float(v[0]), float(v[1]))
                s["end"] = {**(s.get("end") or {}), "lat": lat, "lon": lon, "posSource": "manual"}
                # A landing and the following shot's origin are the same point. Previously the iOS
                # preview updated both but this rebuilt server response updated only `end`, so the
                # route snapped into a broken line after closing and reopening the review.
                if index + 1 < len(shots):
                    next_start = dict(shots[index + 1].get("start") or {})
                    shots[index + 1]["start"] = {
                        **next_start,
                        "lat": lat,
                        "lon": lon,
                        "posSource": "manual",
                    }

    plotted: list[dict[str, Any]] = []
    for shot in shots:
        start = (shot.get("start") or {})
        shot_row: dict[str, Any] = {
            "id": round_corrections.mint_shot_id(shot),
            "start": project(shot.get("start")),
            "end": project(shot.get("end")),
            # Resolved bag label (一号木 / 7I / 58° …) or None when Garmin logged the shot with no club
            # (clubId 0) — a null renders the landing WITHOUT a meaningless "Unknown"/number label.
            "club": clean_club_name(shot.get("clubName")),
            "lie": start.get("lie"),
            "endLie": shot.get("endLie"),
            "shotType": shot.get("type"),
            "order": _int(shot.get("_displayOrder")) or _int(shot.get("order")),
            "synthetic": False,
            "gpsAvailable": all(
                value is not None
                for value in (
                    start.get("lat"),
                    start.get("lon"),
                    (shot.get("end") or {}).get("lat"),
                    (shot.get("end") or {}).get("lon"),
                )
            ),
        }
        # Provenance from the 复盘 correction layer: surface a per-field "manual" override so the client
        # can mark an edited shot 已修正. Only emitted when the player actually changed that field
        # (apply_corrections tags it) — untouched shots stay clean, so the flag never shows on originals.
        if shot.get("clubSource") == "manual":
            shot_row["clubSource"] = "manual"
        if shot.get("lieSource") == "manual":
            shot_row["lieSource"] = "manual"
        plotted.append(shot_row)

    # Auto-complete the drive: if no recorded shot starts on the tee box, add a synthetic tee shot
    # from the tee (route[0], already the first overlay route px) to the first recorded shot's start
    # (or to the green when nothing was recorded at all).
    green_px = [int(round(overlay["route"][-1][0])), int(round(overlay["route"][-1][1]))] if overlay.get("route") else None
    first_start_lie = str((shots[0].get("start") or {}).get("lie") or "").lower() if shots else ""
    # A fact snapshot is the player's explicit count/list. Never add an inferred stroke back after
    # the player deliberately deleted or reordered that list.
    needs_tee = (
        fact_snapshot is None
        and tee_px is not None
        and (not shots or first_start_lie not in {"teebox", "tee"})
    )
    if needs_tee:
        target = plotted[0]["start"] if plotted and plotted[0]["start"] else green_px
        plotted.insert(0, {
            "id": None,
            "start": tee_px,
            "end": target,
            "club": None,
            "lie": "TeeBox",
            "endLie": None,
            "shotType": "TEE",
            "order": 0,
            "synthetic": True,
            "gpsAvailable": False,
        })

    skipped_pixel_edits = uses_lightweight_frame and any(
        event.get("op") in {"replaceHoleShots", "addShot"}
        or (event.get("op") == "editField" and event.get("field") == "position")
        for event in post_fact_corrections
        if _int(event.get("hole")) in {None, hole}
    )
    if skipped_pixel_edits:
        missing_data.append(
            {
                "label": "position_edits",
                "reason": "精确地图恢复前，之前按精确底图保存的位置修正暂不套用",
            }
        )
    elif pixel_snapshot is not None:
        missing_data.append(
            {
                "label": "geometry",
                "reason": "球场地图已更新，这一洞的手工修正需要重做",
            }
        )

    return {
        "schema": SCHEMA,
        "found": True,
        "roundRef": str(row.get("id")),
        "hole": hole,
        "par": par,
        # Physical (gid, localHole) is retained for precise and CourseView-only frames. The client
        # requests a topo bitmap only when geometryRevision is present.
        "globalId": int(gid) if gid is not None else None,
        "localHole": int(local),
        "geometryRevision": geometry_revision,
        "mapKind": map_kind,
        "map": {"image": image, "overlay": overlay},
        "shots": plotted,
        "manualPenalty": manual_penalty,
        "missingData": missing_data,
    }
