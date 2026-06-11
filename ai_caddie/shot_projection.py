"""Project the player's Garmin shot positions into prep hole-map pixels.

Frame chain (every step verified against real data, 2026-06):

1. Shot/pin ``lat``/``lon`` are RAW 32-bit Garmin semicircles → degrees = value × 180 / 2³¹
   (existing :func:`ai_caddie.data.semicircle_to_deg`).
2. WGS84 degrees → hole-local metres: equirectangular about the hole.json ``RefLat``/``RefLon``
   anchor using the WGS84 EQUATORIAL radius 6378137.0 m. Calibration: across all 18 holes of a
   real round (gids 31870/31871), shots-file pin positions land on the hole.json dogleg-end
   (the green) with mean 0.04 m / max 0.08 m error — exact to the 1/8 m quantisation of
   hole.json coords. (The 6371000.0 mean radius used by :func:`ai_caddie.data.wgs84_to_local`
   gives max 0.67 m and is kept only for legacy overlay paths.) The local frame equals
   hole.json ``(X, Y)`` == ``(-mesh_x, mesh_z)`` == (east, north).
3. Local metres → display pixels via :func:`ai_caddie.hole_render.overlay_projector`, the EXACT
   transform ``render_hole`` uses for ``overlay['route']`` px, so scatter dots align with the
   rendered map and route overlay by construction.
"""
from __future__ import annotations

import math
from typing import Any, Callable

from ai_caddie.data import (
    club_name_from_details,
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


def project_world_to_pixel(
    lat_deg: float,
    lon_deg: float,
    *,
    ref_lat: float,
    ref_lon: float,
    to_px: Callable[[tuple[float, float]], tuple[float, float]],
) -> tuple[float, float]:
    """World WGS84 → display pixels. ``to_px`` MUST come from
    :func:`ai_caddie.hole_render.overlay_projector` so the mapping is identical to the
    overlay route px the clients draw against."""
    return to_px(world_to_local(lat_deg, lon_deg, ref_lat=ref_lat, ref_lon=ref_lon))


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def shots_for_hole(
    global_id: int,
    local_hole: int,
    *,
    shot_types: tuple[str, ...] = SCATTER_SHOT_TYPES,
) -> list[dict]:
    """End positions (degrees) of the player's past shots on one physical hole.

    Scorecards are matched on their nine globalIds (same source ``round_hole_ref`` /
    ``course_reference`` use): front nine == gid → holeNumber = local_hole; back nine == gid →
    holeNumber = local_hole + 9 (a nine played twice as front+back matches both). Shots are
    filtered to ``shot_types`` with ``excludeFromStats`` false, ordered newest round first
    (then file order: hole, shotOrder).
    """
    gid = int(global_id)
    local = int(local_hole)
    per_round: list[tuple[str, str, list[dict]]] = []
    for path in scorecard_files():
        try:
            sc = read_json(path)["scorecardDetails"][0]["scorecard"]
        except Exception:
            continue
        front = _int_or_none(sc.get("frontNineGlobalCourseId")) or _int_or_none(sc.get("courseGlobalId"))
        back = _int_or_none(sc.get("backNineGlobalCourseId"))
        wanted = set()
        if front == gid:
            wanted.add(local)
        if back == gid:
            wanted.add(local + 9)
        if not wanted:
            continue
        scorecard_id = sc.get("id") or path.stem
        shot_data = load_shot_file(scorecard_id)
        if not shot_data:
            continue
        date = str(sc.get("formattedStartTime") or sc.get("startTime") or "")
        rows: list[dict] = []
        for hole in shot_data.get("holeShots") or []:
            if _int_or_none(hole.get("holeNumber")) not in wanted:
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
                rows.append({
                    "roundId": str(scorecard_id),
                    "date": date,
                    "shotType": shot.get("shotType"),
                    "club": club_name_from_details(club_id, shot_data) if club_id else None,
                    "lat": lat,
                    "lon": lon,
                })
        if rows:
            per_round.append((date, str(scorecard_id), rows))
    per_round.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [row for _date, _sid, rows in per_round for row in rows]
