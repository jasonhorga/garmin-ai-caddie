"""Project the player's Garmin shot positions into prep hole-map pixels.

Frame chain (every step verified against real data, 2026-06):

1. Shot/pin ``lat``/``lon`` are RAW 32-bit Garmin semicircles → degrees = value × 180 / 2³¹
   (existing :func:`ai_caddie.core.data.semicircle_to_deg`).
2. WGS84 degrees → hole-local metres: equirectangular about the hole.json ``RefLat``/``RefLon``
   anchor using the WGS84 EQUATORIAL radius 6378137.0 m. Calibration: across all 18 holes of a
   real round (gids 31870/31871), shots-file pin positions land on the hole.json dogleg-end
   (the green) with mean 0.04 m / max 0.08 m error — exact to the 1/8 m quantisation of
   hole.json coords. (The 6371000.0 mean radius used by :func:`ai_caddie.core.data.wgs84_to_local`
   gives max 0.67 m and is kept only for legacy overlay paths.) The local frame equals
   hole.json ``(X, Y)`` == ``(-mesh_x, mesh_z)`` == (east, north).
3. Local metres → display pixels via :func:`ai_caddie.geometry.hole_render.overlay_projector`, the EXACT
   transform ``render_hole`` uses for ``overlay['route']`` px, so scatter dots align with the
   rendered map and route overlay by construction.
"""
from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from ai_caddie.core.data import (
    clean_club_name,
    club_name_from_details,
    load_club_overrides,
    load_shot_file,
    read_json,
    scorecard_files,
    semicircle_to_deg,
)

EARTH_RADIUS_WGS84_M = 6_378_137.0

#: shot types drawn on the prep scatter (putts/chips/recoveries excluded by product decision)
SCATTER_SHOT_TYPES = ("TEE", "APPROACH")

# degrees = semicircles × 180 / 2**31 — plan-facing name for the existing converter
semicircles_to_degrees = semicircle_to_deg


def world_to_local(lat_deg: float, lon_deg: float, *, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """WGS84 degrees → hole-local metres ``(x=east, y=north)`` about RefLat/RefLon.

    This is Garmin's own mesh frame (see module docstring for the calibration evidence).
    """
    x = math.radians(lon_deg - ref_lon) * EARTH_RADIUS_WGS84_M * math.cos(math.radians(ref_lat))
    y = math.radians(lat_deg - ref_lat) * EARTH_RADIUS_WGS84_M
    return (x, y)


def local_to_world(x: float, y: float, *, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """Hole-local metres ``(x=east, y=north)`` → WGS84 degrees ``(lat, lon)`` about RefLat/RefLon.

    The EXACT inverse of :func:`world_to_local` (same calibrated WGS84 equatorial radius), so a
    point round-trips ``local_to_world`` → ``world_to_local`` to floating-point precision. Use this —
    not :func:`ai_caddie.core.data.local_to_wgs84` (mean radius 6371000 m) — for any point already in
    the mesh ``(-mesh_x, mesh_z)`` frame (route / green vertices), or the WGS84 result drifts ~0.1 %
    of the distance from the anchor (see module docstring: 0.04 m vs 0.67 m calibration error).
    """
    lat = ref_lat + math.degrees(y / EARTH_RADIUS_WGS84_M)
    lon = ref_lon + math.degrees(x / (EARTH_RADIUS_WGS84_M * math.cos(math.radians(ref_lat))))
    return (lat, lon)


def project_world_to_pixel(
    lat_deg: float,
    lon_deg: float,
    *,
    ref_lat: float,
    ref_lon: float,
    to_px: Callable[[tuple[float, float]], tuple[float, float]],
) -> tuple[float, float]:
    """World WGS84 → display pixels. ``to_px`` MUST come from
    :func:`ai_caddie.geometry.hole_render.overlay_projector` so the mapping is identical to the
    overlay route px the clients draw against."""
    return to_px(world_to_local(lat_deg, lon_deg, ref_lat=ref_lat, ref_lon=ref_lon))


def pixel_to_world(
    px: float,
    py: float,
    *,
    ref_lat: float,
    ref_lon: float,
    from_px: Callable[[tuple[float, float]], tuple[float, float]],
) -> tuple[float, float]:
    """Display pixels → world WGS84 ``(lat, lon)``. The inverse of :func:`project_world_to_pixel`;
    ``from_px`` MUST come from :func:`ai_caddie.geometry.hole_render.overlay_unprojector` (the exact
    inverse of the ``to_px`` used to project), so a tapped pixel round-trips to its world coord."""
    x, y = from_px((px, py))
    return local_to_world(x, y, ref_lat=ref_lat, ref_lon=ref_lon)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _scorecard_shot_rows_for_holes(
    path,
    shots_loader,
    gid: int,
    local_holes: set[int],
    shot_types,
    apply_overrides: bool = True,
    club_overrides: dict[int, dict[str, Any]] | None = None,
) -> tuple[str, str, dict[int, list[dict]]] | None:
    """Read one scorecard/shot pair once and distribute rows to requested physical holes."""
    try:
        sc = read_json(path)["scorecardDetails"][0]["scorecard"]
    except Exception:
        return None
    front = _int_or_none(sc.get("frontNineGlobalCourseId")) or _int_or_none(sc.get("courseGlobalId"))
    back = _int_or_none(sc.get("backNineGlobalCourseId"))
    locals_by_scorecard_hole: dict[int, set[int]] = defaultdict(set)
    for local in local_holes:
        if front == gid:
            locals_by_scorecard_hole[local].add(local)
        if back == gid:
            locals_by_scorecard_hole[local + 9].add(local)
    if not locals_by_scorecard_hole:
        return None
    scorecard_id = sc.get("id") or path.stem
    shot_data = shots_loader(scorecard_id)
    if not shot_data:
        return None
    date = str(sc.get("formattedStartTime") or sc.get("startTime") or "")
    rows_by_local: dict[int, list[dict]] = defaultdict(list)
    for hole in shot_data.get("holeShots") or []:
        matching_locals = locals_by_scorecard_hole.get(_int_or_none(hole.get("holeNumber")))
        if not matching_locals:
            continue
        for shot in sorted(hole.get("shots") or [], key=lambda s: s.get("shotOrder") or 0):
            if shot.get("shotType") not in shot_types or shot.get("excludeFromStats"):
                continue
            end = shot.get("endLoc") or {}
            lat = semicircles_to_degrees(end.get("lat"))
            lon = semicircles_to_degrees(end.get("lon"))
            if lat is None or lon is None:
                continue
            club_id = shot.get("clubId")
            if club_id and apply_overrides and club_id in (club_overrides or {}):
                club_name = str((club_overrides or {})[club_id].get("name") or "Unknown")
            else:
                club_name = club_name_from_details(club_id, shot_data, apply_overrides=False)
            row = {
                "roundId": str(scorecard_id),
                "date": date,
                "shotType": shot.get("shotType"),
                # Real bag label or None (no signal) — never an "Unknown"/number placeholder, so the
                # 备战 scatter matches the 复盘 shot-map (shared prep layer, not per-surface).
                "club": clean_club_name(club_name) if club_id else None,
                "lat": lat,
                "lon": lon,
            }
            for local in matching_locals:
                rows_by_local[local].append(row)
    if rows_by_local:
        return (date, str(scorecard_id), dict(rows_by_local))
    return None


def _scorecard_shot_rows(path, shots_loader, gid: int, local: int, shot_types, apply_overrides: bool = True) -> tuple[str, str, list[dict]] | None:
    """Backward-compatible single-hole wrapper around the batched scorecard reader."""
    result = _scorecard_shot_rows_for_holes(
        path,
        shots_loader,
        gid,
        {local},
        shot_types,
        apply_overrides,
        load_club_overrides() if apply_overrides else {},
    )
    if result is None:
        return None
    date, scorecard_id, rows_by_local = result
    rows = rows_by_local.get(local)
    return (date, scorecard_id, rows) if rows else None


def shots_for_holes(
    global_id: int,
    local_holes,
    *,
    shot_types: tuple[str, ...] = SCATTER_SHOT_TYPES,
    sources: list[tuple[Path, Path]] | None = None,
    apply_overrides: bool = True,
) -> dict[int, list[dict]]:
    """Batch form of :func:`shots_for_hole`, scanning each scorecard/shot file at most once."""
    gid = int(global_id)
    requested = {int(local) for local in local_holes}
    per_hole: dict[int, list[tuple[str, str, list[dict]]]] = {
        local: [] for local in requested
    }
    club_overrides = load_club_overrides() if apply_overrides else {}

    def consume(path, loader) -> None:
        result = _scorecard_shot_rows_for_holes(
            path,
            loader,
            gid,
            requested,
            shot_types,
            apply_overrides,
            club_overrides,
        )
        if result is None:
            return
        date, scorecard_id, rows_by_local = result
        for local, rows in rows_by_local.items():
            per_hole[local].append((date, scorecard_id, rows))

    if sources is None:
        for path in scorecard_files():
            consume(path, load_shot_file)
    else:
        for scorecards_dir, shots_dir in sources:
            def _loader(scorecard_id, _shots_dir=shots_dir):
                path = _shots_dir / f"{scorecard_id}.json"
                if not path.exists():
                    return None
                data = read_json(path)
                return None if data.get("_no_data") else data

            for path in sorted(scorecards_dir.glob("*.json")):
                consume(path, _loader)

    output: dict[int, list[dict]] = {}
    for local, rounds in per_hole.items():
        rounds.sort(key=lambda item: (item[0], item[1]), reverse=True)
        output[local] = [row for _date, _scorecard_id, rows in rounds for row in rows]
    return output


def shots_for_hole(
    global_id: int,
    local_hole: int,
    *,
    shot_types: tuple[str, ...] = SCATTER_SHOT_TYPES,
    sources: list[tuple[Path, Path]] | None = None,
    apply_overrides: bool = True,
) -> list[dict]:
    """End positions (degrees) of the player's past shots on one physical hole.

    Scorecards are matched on their nine globalIds (same source ``round_hole_ref`` /
    ``course_reference`` use): front nine == gid → holeNumber = local_hole; back nine == gid →
    holeNumber = local_hole + 9 (a nine played twice as front+back matches both). Shots are
    filtered to ``shot_types`` with ``excludeFromStats`` false, ordered newest round first
    (then file order: hole, shotOrder).

    ``sources`` is None → the owner's flat ``data/scorecards`` + ``data/shots`` (unchanged). When
    given (a member's ``(scorecards_dir, shots_dir)`` pairs from ``history._player_shot_sources``),
    only those trees are read — so a member's scatter comes solely from their own logged rounds.
    """
    local = int(local_hole)
    return shots_for_holes(
        global_id,
        [local],
        shot_types=shot_types,
        sources=sources,
        apply_overrides=apply_overrides,
    ).get(local, [])
