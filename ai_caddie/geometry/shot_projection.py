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
from pathlib import Path
from typing import Any, Callable

from ai_caddie.core.data import (
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


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _scorecard_shot_rows(path, shots_loader, gid: int, local: int, shot_types, apply_overrides: bool = True) -> tuple[str, str, list[dict]] | None:
    """Project one scorecard file's matching-hole shots. ``shots_loader(scorecard_id)`` returns
    that scorecard's shot data (or None). Shared by the owner path and the player-scoped path so
    the matching/projection logic stays identical for both."""
    try:
        sc = read_json(path)["scorecardDetails"][0]["scorecard"]
    except Exception:
        return None
    front = _int_or_none(sc.get("frontNineGlobalCourseId")) or _int_or_none(sc.get("courseGlobalId"))
    back = _int_or_none(sc.get("backNineGlobalCourseId"))
    wanted = set()
    if front == gid:
        wanted.add(local)
    if back == gid:
        wanted.add(local + 9)
    if not wanted:
        return None
    scorecard_id = sc.get("id") or path.stem
    shot_data = shots_loader(scorecard_id)
    if not shot_data:
        return None
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
                "club": club_name_from_details(club_id, shot_data, apply_overrides=apply_overrides) if club_id else None,
                "lat": lat,
                "lon": lon,
            })
    if rows:
        return (date, str(scorecard_id), rows)
    return None


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
    gid = int(global_id)
    local = int(local_hole)
    per_round: list[tuple[str, str, list[dict]]] = []
    if sources is None:
        for path in scorecard_files():
            res = _scorecard_shot_rows(path, load_shot_file, gid, local, shot_types, apply_overrides)
            if res is not None:
                per_round.append(res)
    else:
        for scorecards_dir, shots_dir in sources:
            def _loader(scorecard_id, _shots_dir=shots_dir):
                p = _shots_dir / f"{scorecard_id}.json"
                if not p.exists():
                    return None
                d = read_json(p)
                return None if d.get("_no_data") else d
            for path in sorted(scorecards_dir.glob("*.json")):
                res = _scorecard_shot_rows(path, _loader, gid, local, shot_types, apply_overrides)
                if res is not None:
                    per_round.append(res)
    per_round.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [row for _date, _sid, rows in per_round for row in rows]
