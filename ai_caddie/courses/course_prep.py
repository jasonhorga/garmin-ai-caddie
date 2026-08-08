"""Pre-round course-prep facts for a hole/nine: par + playing route + hazard carries +
recommended club/target (from the player's real distances) + a styled hole map. NO AI.

Geometry-only and self-contained (works before any shot exists), using the decoded
prodgeometry meshes in the mesh coord frame — the same frame as :mod:`ai_caddie.geometry.hole_render`,
so map + overlay + hazards align exactly. Par comes from :mod:`ai_caddie.courses.course_reference`
(played -> courseview -> estimate), labelled with its source. Ported from the validated
prototype (route = blue-tee + dogleg centreline; green = dogleg line end; hazards by
point-in-polygon along the densified route).
"""
from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from ai_caddie.courses import course_reference, courseview_core
from ai_caddie.geometry import elevation, hole_render, shot_projection
from ai_caddie.core.data import build_club_profiles, read_json
from ai_caddie.core.data import OWNER_ID, load_manual_club_bag
from ai_caddie.core.data import available_prep_holes as available_prep_holes  # re-export: prep's hole-list default
from ai_caddie.caddie import club_catalog
from ai_caddie.geometry.geometry_evidence import geometry_coverage_for_hole

YARD = 1.09361
MAX_SCATTER_SHOTS = 80  # newest rounds first; keeps the overlay readable and the payload small
DEFAULT_LADDER = {  # metres; overridden by the player's real club model when available
    "1W": 200, "3W": 171, "3H": 159, "5I": 146, "6I": 132, "7I": 128,
    "8I": 122, "9I": 114, "PW": 102, "A杆": 84, "50°": 53, "54°": 52, "58°": 42,
}


def yd(metres: float) -> int:
    return round(metres * YARD)


def _local(p):
    return (-float(p[0]), float(p[2]))


# ---------- route derivation (tee -> dogleg centreline -> green) ----------

def _xy(p):
    if isinstance(p, dict):
        return (float(p["X"]), float(p["Y"]))
    return (float(p[0]), float(p[1]))


def _blue_tee(hole_meta: dict, fallback):
    """Blue tee = TeeLocations whose Sets include 2; else the tee nearest the dogleg start."""
    tees = hole_meta.get("TeeLocations") or []
    blue = next((t for t in tees if 2 in (t.get("Sets") or [])), None)
    if blue is not None:
        return _xy(blue)
    if tees and fallback:
        return min((_xy(t) for t in tees), key=lambda p: math.hypot(p[0] - fallback[0], p[1] - fallback[1]))
    return _xy(tees[0]) if tees else fallback


def _dogleg_line(hole_meta: dict):
    for dl in hole_meta.get("Doglegs") or []:
        line = dl.get("Line") or []
        if len(line) >= 2:
            return [_xy(p) for p in line]
    return None


def _course_data_route_in_hole_frame(hole_meta: dict) -> list[tuple[float, float]] | None:
    """Project the cached selected-layout route into ``hole.json``'s local frame."""
    try:
        route = courseview_core.load_cached_hole_route(
            int(hole_meta["GlobalId"]),
            int(hole_meta["HoleNumber"]),
        )
        ref_lat = float(hole_meta["RefLat"])
        ref_lon = float(hole_meta["RefLon"])
        projected = [
            shot_projection.world_to_local(
                latitude,
                longitude,
                ref_lat=ref_lat,
                ref_lon=ref_lon,
            )
            for latitude, longitude in (route or [])
        ]
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    deduped: list[tuple[float, float]] = []
    for point in projected:
        if not deduped or math.dist(point, deduped[-1]) > 0.01:
            deduped.append(point)
    return deduped if len(deduped) >= 2 else None


def derive_route(md: dict):
    """Return the selected-layout route, or ``(None, None)`` when unavailable.

    Garmin ``hole.json`` is normally the exact route authority, but a dual-green
    package can keep its Doglegs endpoint on physical green A while ``courseData``
    selects green B for this layout.  Preserve the precise blue Tee and Doglegs
    route unless the release-bound endpoint differs by more than the proven
    layout-selection threshold; only then use courseData's subsequent route
    points and selected endpoint.
    """
    hole_meta = md.get("hole") or {}
    line = _dogleg_line(hole_meta)
    if not line:
        return None, None
    tee = _blue_tee(hole_meta, line[0])
    if not tee:
        return None, None
    selected_route = _course_data_route_in_hole_frame(hole_meta)
    if (
        selected_route
        and math.dist(selected_route[-1], line[-1])
        > courseview_core.COURSE_DATA_ROUTE_ENDPOINT_OVERRIDE_METRES
    ):
        route = [tee]
        for point in selected_route[1:]:
            if math.dist(point, route[-1]) > 0.01:
                route.append(point)
    else:
        route = [tee] + line[1:]
    if len(route) < 2:
        return None, None
    length = sum(math.hypot(route[i + 1][0] - route[i][0], route[i + 1][1] - route[i][1])
                 for i in range(len(route) - 1))
    return route, length


# ---------- hazards along the route (mesh point-in-polygon) ----------

def _triangles(mesh):
    pts = [_local(p) for p in mesh["positions"]]
    return [(pts[a], pts[b], pts[c]) for a, b, c in mesh["faces"]]


def _in_tri(p, a, b, c) -> bool:
    d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
    d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
    d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
    neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (neg and pos)


def _point_in_mesh(p, tris) -> bool:
    return any(_in_tri(p, a, b, c) for a, b, c in tris)


def _densify(route, step=4.0):
    out = []
    cum = 0.0
    for i in range(len(route) - 1):
        a, b = route[i], route[i + 1]
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(seg / step))
        for k in range(n):
            t = k / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, cum + seg * t))
        cum += seg
    out.append((route[-1][0], route[-1][1], cum))
    return out


WATER_MIN_M = 3.0   # ignore water clips shorter than this along the route (carry not meaningful)
WATER_SIDE_MAX_M = 30.0  # list nearby side water like S70; exclude water belonging to adjacent holes
BUNKER_MAX_M = 30.0  # only report a bunker whose nearest edge is within this of the route


def _route_segments(route) -> list[tuple[tuple[float, float], tuple[float, float], float, float]]:
    """Route vertices as ``(a, b, cum_at_a_m, seg_len_m)`` segments (cumulative measured at ``a``)."""
    segments = []
    cum = 0.0
    for i in range(len(route) - 1):
        a = (float(route[i][0]), float(route[i][1]))
        b = (float(route[i + 1][0]), float(route[i + 1][1]))
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg > 0:
            segments.append((a, b, cum, seg))
        cum += seg
    return segments


def _merge_intervals(intervals, gap=1e-6) -> list[list[float]]:
    """Merge only numerically-contiguous ``[start, end]`` metre intervals.

    Adjacent mesh triangles split one contiguous water crossing into touching sub-intervals; this
    glues them back into a single carry. Genuinely separate water bodies (a real dry gap) stay
    split — that is the more accurate behaviour. Degenerate (zero-length) intervals are dropped.
    """
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if end - start <= gap:
            continue
        if merged and start <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _water_carry(lake, segments) -> list[list[float]]:
    """Carry intervals (metres along the route) from the EXACT route-segment ∩ lake intersection.

    Each route segment is intersected with every Lake mesh component via the precise
    :func:`measure_prodgeometry_distances.line_intervals_for_component`, so a narrow water strip
    the route crosses BETWEEN the old 4 m samples is no longer missed. Sub-``WATER_MIN_M`` clips
    are dropped (unchanged noise filter).
    """
    if not lake:
        return []
    from ai_caddie.geometry.measure_prodgeometry_distances import line_intervals_for_component, mesh_components

    raw: list[tuple[float, float]] = []
    for component in mesh_components(lake):
        for a, b, cum, seg in segments:
            for t0, t1 in line_intervals_for_component(a, b, component):
                raw.append((cum + t0 * seg, cum + t1 * seg))
    return [
        [round(start, 1), round(end, 1)]
        for start, end in _merge_intervals(raw)
        if end - start >= WATER_MIN_M
    ]


def _component_boundary_edges(triangles) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Exterior mesh edges only; shared triangulation edges are internal and cancel in pairs."""
    edge_counts: dict[tuple[tuple[float, float], tuple[float, float]], int] = {}
    for triangle in triangles:
        for first, second in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        ):
            edge = (first, second) if first <= second else (second, first)
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    return [edge for edge, count in edge_counts.items() if count == 1]


def _closest_point_on_segment(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= 0:
        return start
    t = max(0.0, min(1.0, (
        (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
    ) / length_squared))
    return (start[0] + t * dx, start[1] + t * dy)


def _radial_boundary_points(boundary_edges, origin):
    """True boundary points for player-facing ``到`` (nearest) and ``过`` (farthest).

    The nearest point can lie inside a boundary edge, so project the player origin onto every edge.
    The farthest point on a line segment is always one of its endpoints.  Both returned points are
    therefore on the decoded Garmin hazard boundary, and their straight-line ranges cannot invert on
    a dogleg the way route-station-selected points can.
    """
    nearest_candidates = [
        _closest_point_on_segment(origin, start, end)
        for start, end in boundary_edges
    ]
    vertices = {point for edge in boundary_edges for point in edge}
    if not nearest_candidates or not vertices:
        return None
    front = min(nearest_candidates, key=lambda point: (
        math.hypot(point[0] - origin[0], point[1] - origin[1]), point,
    ))
    back = max(vertices, key=lambda point: (
        math.hypot(point[0] - origin[0], point[1] - origin[1]), point,
    ))
    return front, back


def _side_water_measurements(lake, route) -> list[dict]:
    """Nearby lake components that do not cross the intended route, with true front/back edges.

    ``water_carry`` deliberately remains an exact route-intersection contract for strategy code. The
    S70 hazard browser is broader: a lake beside the fairway is still a hazard for the hole and needs
    distances to its front and back. This companion measurement adds only non-crossing components
    within the same 30 m hole corridor used for bunkers, so water from an adjacent hole is not listed.
    """
    if not lake:
        return []
    from ai_caddie.geometry.measure_prodgeometry_distances import (
        line_intervals_for_component,
        mesh_components,
        point_segment_distance,
        segment_edge_intersection_t,
    )

    segments = _route_segments(route)
    if not segments:
        return []
    route_points = [segments[0][0], *(segment[1] for segment in segments)]
    xs = [point[0] for point in route_points]
    ys = [point[1] for point in route_points]
    route_bbox = (min(xs), min(ys), max(xs), max(ys))
    measurements: list[dict] = []

    def segment_gap(route_start, route_end, edge_start, edge_end) -> float:
        if segment_edge_intersection_t(route_start, route_end, edge_start, edge_end) is not None:
            return 0.0
        return min(
            point_segment_distance(route_start, edge_start, edge_end),
            point_segment_distance(route_end, edge_start, edge_end),
            point_segment_distance(edge_start, route_start, route_end),
            point_segment_distance(edge_end, route_start, route_end),
        )

    for component in mesh_components(lake):
        if _bbox_gap(route_bbox, component["bbox"]) > WATER_SIDE_MAX_M:
            continue
        crosses_route = any(
            t1 - t0 > 1e-6
            for a, b, _cum, _seg in segments
            for t0, t1 in line_intervals_for_component(a, b, component)
        )
        if crosses_route:
            continue  # already represented precisely by ``water_carry``

        boundary_edges = _component_boundary_edges(component["triangles"])
        if not boundary_edges:
            continue
        side = min(
            segment_gap(route_start, route_end, edge_start, edge_end)
            for route_start, route_end, _cum, _length in segments
            for edge_start, edge_end in boundary_edges
        )
        if side > WATER_SIDE_MAX_M:
            continue

        vertices = {point for edge in boundary_edges for point in edge}
        projected = []
        for point in vertices:
            route_projection = _project_point_to_route(point, segments)
            if route_projection is not None:
                projected.append((route_projection[1], route_projection[0], point))
        if not projected:
            continue
        route_front = min(projected, key=lambda row: (row[0], row[1], row[2]))
        route_back = min(projected, key=lambda row: (-row[0], row[1], row[2]))
        radial = _radial_boundary_points(boundary_edges, route[0])
        if radial is None:
            continue
        front_point, back_point = radial
        measurements.append({
            "frontRouteM": round(route_front[0], 1),
            "backRouteM": round(route_back[0], 1),
            "frontPoint": front_point,
            "backPoint": back_point,
            "sideM": round(side, 1),
        })

    measurements.sort(key=lambda row: (row["frontRouteM"], row["backRouteM"], row["sideM"]))
    return measurements


def _bbox_gap(route_bbox, comp_bbox) -> float:
    """Lower bound on the route↔component distance from their bounding boxes (safe to reject on)."""
    dx = max(comp_bbox[0] - route_bbox[2], route_bbox[0] - comp_bbox[2], 0.0)
    dy = max(comp_bbox[1] - route_bbox[3], route_bbox[1] - comp_bbox[3], 0.0)
    return math.hypot(dx, dy)


def _project_point_to_route(point, segments):
    """Return ``(side_m, route_m, route_point)`` for the closest point on a polyline route."""
    best = None
    for a, b, cum, seg in segments:
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (seg * seg)))
        route_point = (a[0] + t * dx, a[1] + t * dy)
        side = math.hypot(point[0] - route_point[0], point[1] - route_point[1])
        row = (side, cum + t * seg, route_point)
        if best is None or row[:2] < best[:2]:
            best = row
    return best


def _route_point(segments, route_m: float):
    """Interpolate a local-metre point at an absolute cumulative distance on the route."""
    if not segments:
        return None
    for a, b, cum, seg in segments:
        if route_m <= cum + seg:
            t = max(0.0, min(1.0, (route_m - cum) / seg))
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    return segments[-1][1]


def _bunker_measurements(bunker, route) -> list[dict]:
    """Internal measurement per bunker, retaining both legacy side gap and real front/back edges.

    Uses :func:`measure_prodgeometry_distances.point_triangle_distance` (exact point→triangle) from
    each densified route point to the bunker's triangles, so a long bunker whose near edge hugs the
    route is measured by that edge — not by its far-away centroid (the old approximation, which
    over-stated the gap and could push a near-edge bunker past the ``BUNKER_MAX_M`` gate). The
    along-route position keeps the existing 4 m route resolution.  For the player-facing S70 readout,
    ``到`` and ``过`` are the nearest/farthest true boundary points from the player origin.  Route
    projection remains only an internal monotonic range for sorting/filtering; it does not choose the
    displayed points (doing so inverted the two ranges on a real dogleg greenside bunker).
    """
    if not bunker:
        return []
    from ai_caddie.geometry.measure_prodgeometry_distances import mesh_components, point_triangle_distance

    dense = _densify(route)
    if not dense:
        return []
    xs = [p[0] for p in dense]
    ys = [p[1] for p in dense]
    route_bbox = (min(xs), min(ys), max(xs), max(ys))
    segments = _route_segments(route)
    bunkers: list[dict] = []
    for component in mesh_components(bunker):
        if _bbox_gap(route_bbox, component["bbox"]) > BUNKER_MAX_M:
            continue  # whole component is provably out of range — skip the per-point distance work
        triangles = component["triangles"]
        best_side = None
        best_cum = None
        for p in dense:
            side = min(point_triangle_distance((p[0], p[1]), tri) for tri in triangles)
            if best_side is None or side < best_side:
                best_side, best_cum = side, p[2]
        if best_side is not None and best_side <= BUNKER_MAX_M:
            boundary_edges = _component_boundary_edges(triangles)
            vertices = {point for edge in boundary_edges for point in edge}
            projected = []
            for point in vertices:
                route_projection = _project_point_to_route(point, segments)
                if route_projection is not None:
                    projected.append((route_projection[1], route_projection[0], point))
            if not projected:
                continue
            route_front = min(projected, key=lambda row: (row[0], row[1], row[2]))
            route_back = min(projected, key=lambda row: (-row[0], row[1], row[2]))
            radial = _radial_boundary_points(boundary_edges, route[0])
            if radial is None:
                continue
            front_point, back_point = radial
            bunkers.append({
                "legacy": [round(best_cum, 1), round(best_side, 1)],
                "frontRouteM": round(route_front[0], 1),
                "backRouteM": round(route_back[0], 1),
                "frontPoint": front_point,
                "backPoint": back_point,
                "sideM": round(best_side, 1),
            })
    bunkers.sort(key=lambda row: row["legacy"])
    return bunkers


def _hazard_detail(kind: str, front_route_m: float, back_route_m: float, front_point, back_point,
                   tee, to_px, side_m: float | None = None) -> dict:
    front_px = to_px(front_point)
    back_px = to_px(back_point)
    return {
        "kind": kind,
        "frontM": round(math.hypot(front_point[0] - tee[0], front_point[1] - tee[1]), 1),
        "backM": round(math.hypot(back_point[0] - tee[0], back_point[1] - tee[1]), 1),
        "frontRouteM": round(front_route_m, 1),
        "backRouteM": round(back_route_m, 1),
        "frontPx": [round(front_px[0], 1), round(front_px[1], 1)],
        "backPx": [round(back_px[0], 1), round(back_px[1], 1)],
        "sideM": side_m,
    }


def route_hazards(by: dict, route) -> dict:
    """Water-carry intervals + greenside/fairway bunkers along the route (metres along route).

    Geometry is measured EXACTLY against the decoded meshes (same coord frame as the map/overlay).
    Water carries come from the true route-segment ∩ Lake-component intersection (a narrow strip
    crossed between samples is never missed); bunker ``side`` is the shortest distance to the bunker
    BOUNDARY rather than its centroid (a long bunker is measured by its near edge). Legacy arrays stay
    byte-compatible for strategy code. Additive ``details`` rows give both hazard kinds the same
    player-facing front/back contract and put their map markers on real geometry boundary pixels.
    """
    segments = _route_segments(route)
    water = _water_carry(by.get("Lake.drc"), segments)
    side_water_measurements = _side_water_measurements(by.get("Lake.drc"), route)
    bunker_measurements = _bunker_measurements(by.get("Bunker.drc"), route)
    details: list[dict] = []
    if water or side_water_measurements or bunker_measurements:
        tee = (float(route[0][0]), float(route[0][1]))
        to_px = hole_render.overlay_projector(by, route)
        for start, end in water:
            front_point = _route_point(segments, start)
            back_point = _route_point(segments, end)
            if front_point is not None and back_point is not None:
                details.append(_hazard_detail(
                    "water", start, end, front_point, back_point, tee, to_px,
                ))
        for water_row in side_water_measurements:
            details.append(_hazard_detail(
                "water",
                water_row["frontRouteM"],
                water_row["backRouteM"],
                water_row["frontPoint"],
                water_row["backPoint"],
                tee,
                to_px,
                side_m=water_row["sideM"],
            ))
        for bunker_row in bunker_measurements:
            details.append(_hazard_detail(
                "bunker",
                bunker_row["frontRouteM"],
                bunker_row["backRouteM"],
                bunker_row["frontPoint"],
                bunker_row["backPoint"],
                tee,
                to_px,
                side_m=bunker_row["sideM"],
            ))
    return {
        "water_carry": water,
        "bunkers": [row["legacy"] for row in bunker_measurements],
        "details": details,
    }


# ---------- club ladder (player's real distances) ----------

def club_ladder(path=None) -> list[tuple[str, int]]:
    """Median distance per club, longest-first, from product club profiles when available."""
    ladder = dict(DEFAULT_LADDER)
    try:
        if path is not None and path.exists():
            data = read_json(path)
            ladder = {k: round(v["median"]) for k, v in data.items() if isinstance(v, dict) and v.get("median")}
        else:
            profiles = build_club_profiles()
            if profiles:
                ladder = {
                    name: round(profile["median"])
                    for name, profile in profiles.items()
                    if isinstance(profile, dict) and profile.get("median")
                }
    except Exception:
        pass
    ordered = sorted(ladder.items(), key=lambda kv: -kv[1])
    # Only recommend clubs the player actually carries (real Garmin bag), so a stale mis-tagged
    # club from shot history (e.g. a "2 Hybrid" no longer in the bag) never gets suggested.
    from ai_caddie.caddie.club_bag import restrict_to_bag

    return restrict_to_bag(ordered, lambda kv: kv[0])


def _member_measured_by_token(player_id: str) -> dict[str, int]:
    """A member's MEASURED median distance per catalog token, from their OWN logged shots only.

    Reads the member's player-scoped shot dir(s) (``history._player_shot_sources``) — never the
    owner's or another member's — and maps each measured profile's club name to a catalog token
    the same way ``restrict_to_bag`` canonicalises names. On a token collision the larger sample
    wins. Empty when the member has logged nothing yet. Imports are local to mirror the existing
    lazy ``restrict_to_bag`` import and stay clear of any module-load import cycle.
    """
    from ai_caddie.history.history import _player_shot_sources
    from ai_caddie.caddie.club_bag import canonical_club_name

    shot_dirs = [shots for _sc, shots in _player_shot_sources(player_id)]
    # apply_overrides=False: the owner's clubs.json must never resolve a member's club names.
    measured = build_club_profiles(shot_dirs=shot_dirs, apply_overrides=False)
    by_token: dict[str, int] = {}
    samples: dict[str, int] = {}
    for club_name, profile in measured.items():
        if not isinstance(profile, dict) or not profile.get("median"):
            continue
        token = canonical_club_name(club_name)
        if not token or not club_catalog.is_valid_token(token):
            continue
        n = int(profile.get("sampleSize") or 0)
        if token not in by_token or n > samples.get(token, 0):
            by_token[token] = round(profile["median"])
            samples[token] = n
    return by_token


def effective_club_ladder(player_id: str) -> list[tuple[str, int]]:
    """The recommended-club ladder for a player, used by every member-reachable prep builder.

    - Owner -> club_ladder() (history-derived distances, restricted to the owner's effective bag).
    - A member WITH a manual bag -> a ladder over their selected tokens, each distance taken as
      their OWN measured median (from their logged shots) ?? manual distanceM ?? CLUB_CATALOG
      default, sorted descending (clubs with none are dropped). Measured distances are read only
      from the member's own tree, so no other player's distances ever leak in.
    - A member with no manual bag -> the generic DEFAULT_LADDER. Never the owner's distances.
    """
    if player_id == OWNER_ID:
        return club_ladder()
    manual = load_manual_club_bag(player_id)
    if manual:
        measured_by_token = _member_measured_by_token(player_id)
        pairs: list[tuple[str, int]] = []
        for club in manual.get("clubs") or []:
            token = str(club.get("token") or "")
            if not club_catalog.is_valid_token(token):
                continue
            dist = measured_by_token.get(token)
            if dist is None:
                dist = club.get("distanceM")
            if dist is None:
                dist = club_catalog.default_distance_m(token)
            if dist is None:
                continue
            pairs.append((token, int(dist)))
        if pairs:
            return sorted(pairs, key=lambda kv: -kv[1])
    return sorted(DEFAULT_LADDER.items(), key=lambda kv: -kv[1])


def club_for(distance_m: float, ladder, *, exclude=()):
    cand = [(n, d) for n, d in ladder if n not in exclude]
    if not cand:
        return None, None
    return min(cand, key=lambda kv: abs(kv[1] - distance_m))


# ---------- strategy + per-hole DTO ----------

@dataclass
class HolePrep:
    globalId: int
    localHole: int
    hole: int
    par: int
    par_source: str
    blue_yards: int
    route_len_m: float
    route: list[list[float]] = field(default_factory=list)
    geometryCoverage: str = "missing"
    geometryRevision: str | None = None
    sourceRefs: list[str] = field(default_factory=list)
    missingData: list[dict] = field(default_factory=list)
    candidateRoutes: list[dict] = field(default_factory=list)
    carryTargets: list[dict] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    landing_m: float | None = None
    tee_club: str | None = None
    hazards: dict = field(default_factory=dict)
    playsLike: dict = field(default_factory=dict)  # round-13: {available, teeElevM, greenElevM, deltaM, deltaYd}
    greenDistances: dict = field(default_factory=dict)  # round-13 E3: {available, front/middle/back M+Yd}
    greenSlope: dict = field(default_factory=dict)  # {available, magnitudePct, directionDeg (break dir), flat}
    holeImageProjection: dict = field(default_factory=dict)  # watch P0.1: geo→px anchors for the topo map
    greenOutline: dict | None = None  # CourseView lightweight outline in the same display frame

    def to_dict(self) -> dict:
        return asdict(self)


def _hole_playslike(by: dict, route) -> dict:
    """PlaysLike (elevation ±yd, tee/ball -> green) from the hole's mesh elevation. round-13.

    Uses the same meshes the map/hazards use (no DEM); empty when route or geometry is missing.
    ``route`` points are in the ``(-mesh_x, mesh_z)`` frame, matching ``elevation._ground``.
    """
    if not route or len(route) < 2:
        return {"available": False}
    try:
        return elevation.playslike(by, route[0], route[-1])
    except Exception:
        return {"available": False}


def selected_green_component(by: dict, route) -> dict | None:
    """Return the connected Green component nearest the selected route endpoint."""
    green = (by or {}).get("Green.drc") if isinstance(by, dict) else None
    if not route or not isinstance(green, dict):
        return None
    try:
        from ai_caddie.geometry.measure_prodgeometry_distances import mesh_components

        components = mesh_components(green)
        target = (float(route[-1][0]), float(route[-1][1]))
        return min(
            components,
            key=lambda component: math.dist(component["centroid"], target),
        ) if components else None
    except Exception:
        return None


def _green_slope(by: dict, route) -> dict:
    """Green break arrow from only the selected Green component (v1, no DSKIMG)."""
    green = by.get("Green.drc") if isinstance(by, dict) else None
    component = selected_green_component(by, route)
    if not green or not component:
        return {"available": False}
    try:
        selected_positions = [
            green["positions"][index] for index in component["vertex_indices"]
        ]
        return elevation.green_slope({"meshes": [{"positions": selected_positions}]})
    except Exception:
        return {"available": False}


def _green_distances(by: dict, route, md: dict | None = None) -> dict:
    """Front/Middle/Back green distances from the tee (前/中/后果岭), flat plan-view m+yd. round-13 E3.

    Reuses the green surface mesh (``by["Green.drc"]``) the map already ships — NO DEM (elevation
    lives in ``playsLike``). ``measure_prodgeometry_distances.mesh_components`` returns components
    whose triangles/centroid are ALREADY in the ``(-mesh_x, mesh_z)`` frame (same as ``route``), so
    no re-projection. A Green.drc tile can include neighbour-hole greens, so we pick the component
    whose centroid is nearest ``route[-1]`` (the dogleg/green endpoint). Front = nearest green
    vertex to the tee, Back = farthest, Middle = the chosen component's centroid. Degrades to
    ``{"available": False}`` on any missing route/green/usable geometry.

    round-13 B1 (LIVE rangefinder): when ``md`` carries the hole's ``RefLat``/``RefLon`` anchor, the
    three green points are ALSO returned as WGS84 ``front/middle/backLat`` + ``…Lon`` so the phone can
    recompute its live distance to the green from its own GPS fix, offline on the course. The points
    are in the mesh ``(-mesh_x, mesh_z)`` frame, so they convert with the exact inverse of the
    calibrated ``world_to_local`` (:func:`shot_projection.local_to_world`). Coords are omitted (the
    tee distances are kept) when RefLat/RefLon is unavailable — no regression on geometry-only holes.
    """
    if not route:
        return {"available": False}
    green = (by or {}).get("Green.drc")
    if not isinstance(green, dict) or not green.get("positions") or not green.get("faces"):
        return {"available": False}
    try:
        comp = selected_green_component(by, route)
        if not comp:
            return {"available": False}
        tee = (float(route[0][0]), float(route[0][1]))
        verts = [p for tri in comp["triangles"] for p in tri]
        if not verts:
            return {"available": False}

        def _from_tee(point) -> float:
            return math.hypot(point[0] - tee[0], point[1] - tee[1])

        # Keep the actual F/M/B POINTS (not just their distances) so they can also be projected to
        # WGS84 below — frontM/middleM/backM stay byte-identical to the previous min/max-of-distances.
        front_pt = min(verts, key=_from_tee)
        back_pt = max(verts, key=_from_tee)
        middle_pt = comp["centroid"]
        front_m, middle_m, back_m = _from_tee(front_pt), _from_tee(middle_pt), _from_tee(back_pt)
        result = {
            "available": True,
            "frontM": round(front_m, 1), "frontYd": yd(front_m),
            "middleM": round(middle_m, 1), "middleYd": yd(middle_m),
            "backM": round(back_m, 1), "backYd": yd(back_m),
        }
        result.update(_green_latlon(md, front_pt, middle_pt, back_pt))
        return result
    except Exception:
        return {"available": False}


def _green_latlon(md: dict | None, front_pt, middle_pt, back_pt) -> dict:
    """WGS84 lat/lon for the three green points so the phone can range-find live (round-13 B1).

    Empty when the hole has no ``RefLat``/``RefLon`` anchor (or it is malformed) — the caller keeps
    the tee distances, so a geometry-only hole still degrades gracefully. The points are already in
    the mesh ``(-mesh_x, mesh_z)`` metric frame, so they convert with the EXACT inverse of the
    calibrated ``world_to_local`` (NOT data.local_to_wgs84, whose mean radius drifts ~0.1 %).
    """
    try:
        hole_meta = (md or {}).get("hole") or {}
        ref_lat, ref_lon = hole_meta.get("RefLat"), hole_meta.get("RefLon")
        if ref_lat is None or ref_lon is None:
            return {}
        ref_lat, ref_lon = float(ref_lat), float(ref_lon)
        out: dict = {}
        for name, point in (("front", front_pt), ("middle", middle_pt), ("back", back_pt)):
            lat, lon = shot_projection.local_to_world(
                float(point[0]), float(point[1]), ref_lat=ref_lat, ref_lon=ref_lon
            )
            out[f"{name}Lat"] = round(lat, 7)
            out[f"{name}Lon"] = round(lon, 7)
        return out
    except Exception:
        return {}


def _hole_image_projection(by: dict, route, md: dict | None = None) -> dict:
    """The geo→pixel mapping for the hole's ``/topo.png``, so a CLIENT (watch/phone) can place its own
    live GPS fix + the pin + landing points onto the same rendered map. Returns 3 NON-collinear
    reference points, each as WGS84 (lat/lon) + its pixel on the map; the client fits an affine from
    them (same 3-point technique as the server's ``overlay_unprojector``). ``widthPx``/``heightPx`` are
    the display dims of ``/topo.png`` (``_frame`` size ÷ SS). Empty when the hole has no RefLat/RefLon
    anchor — a geometry-only hole still ships the F/M/B distances, just can't be GPS-overlaid."""
    if not route:
        return {"available": False}
    hole_meta = (md or {}).get("hole") or {}
    ref_lat, ref_lon = hole_meta.get("RefLat"), hole_meta.get("RefLon")
    if ref_lat is None or ref_lon is None:
        return {"available": False}
    try:
        ref_lat, ref_lon = float(ref_lat), float(ref_lon)
        to_px = hole_render.overlay_projector(by, route)
        _project, _sc, w, h, _margin = hole_render._frame(by, route)
        ss = hole_render.SS
        # 3 non-collinear anchors (metres, (-mesh_x, mesh_z) frame). local→px is affine, so any 3
        # non-collinear points define it exactly; local→WGS84 via the calibrated inverse.
        refs = []
        for lx, ly in ((0.0, 0.0), (120.0, 0.0), (0.0, 120.0)):
            lat, lon = shot_projection.local_to_world(lx, ly, ref_lat=ref_lat, ref_lon=ref_lon)
            px, py = to_px((lx, ly))
            refs.append({"lat": round(lat, 7), "lon": round(lon, 7), "px": round(px, 1), "py": round(py, 1)})
        return {"available": True, "widthPx": int(w // ss), "heightPx": int(h // ss), "refs": refs}
    except Exception:
        return {"available": False}


def _strategy(par: int, route_len_m: float, hazards: dict, ladder):
    steps: list[dict] = []
    cautions: list[str] = []
    driver = next((d for n, d in ladder if n == "1W"), 200)
    landing = None
    if par == 3:
        club, cd = club_for(route_len_m, ladder)
        steps.append({"club": club, "note": f"约 {yd(route_len_m)}y 到果岭中心，一杆上果岭"})
    else:
        landing = min(driver, route_len_m - 8) if route_len_m > driver else route_len_m * 0.55
        tee_club, _ = club_for(landing, ladder)
        steps.append({"club": tee_club, "note": f"开球落点约 {yd(landing)}y"})
        remaining = route_len_m - landing
        if remaining > 5:
            ap_club, _ = club_for(remaining, ladder, exclude=("1W",))
            steps.append({"club": ap_club, "note": f"剩约 {yd(remaining)}y 上果岭"})
    for w in hazards.get("water_carry") or []:
        if w[0] < route_len_m - 5:
            cautions.append(f"水障碍：进水前约 {yd(w[0])}y，过水需 {yd(w[1])}y")
    green_side_bunkers = [
        (cum, side)
        for cum, side in hazards.get("bunkers") or []
        if cum >= route_len_m - 45 and side <= 25
    ]
    if green_side_bunkers:
        # Exact front/back yardages already appear in the measured hazard list. Repeating one
        # warning per bunker made a real green complex produce several near-identical red rows.
        cautions.append("果岭边有沙坑——别短别偏")
    tee_club = steps[0]["club"] if steps else None
    return steps, cautions, landing, tee_club


def _route_with_cumulative(route: list[tuple[float, float]]) -> list[list[float]]:
    out: list[list[float]] = []
    cumulative = 0.0
    for index, point in enumerate(route):
        if index:
            previous = route[index - 1]
            cumulative += math.hypot(point[0] - previous[0], point[1] - previous[1])
        out.append([round(point[0], 1), round(point[1], 1), round(cumulative, 1)])
    return out


def _course_data_route(hole: dict) -> tuple[list[tuple[float, float]], float, float] | None:
    """Convert a lightweight CourseView route to the prodgeometry local-metre frame."""
    route_line = next(
        (
            row
            for row in hole.get("lines") or []
            if isinstance(row, dict) and row.get("role") == "route"
        ),
        None,
    )
    points = (route_line or {}).get("points") or []
    if len(points) < 2:
        return None
    try:
        ref_lat = float(points[0]["latitude"])
        ref_lon = float(points[0]["longitude"])
        route = [
            shot_projection.world_to_local(
                float(point["latitude"]),
                float(point["longitude"]),
                ref_lat=ref_lat,
                ref_lon=ref_lon,
            )
            for point in points
        ]
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    deduped: list[tuple[float, float]] = []
    for point in route:
        if not deduped or math.hypot(
            point[0] - deduped[-1][0], point[1] - deduped[-1][1]
        ) > 0.01:
            deduped.append(point)
    return (deduped, ref_lat, ref_lon) if len(deduped) >= 2 else None


def _route_station(
    point: tuple[float, float],
    route: list[tuple[float, float]],
) -> tuple[float, float]:
    """Nearest cumulative route metre and lateral gap for one factual point."""
    best_station = 0.0
    best_gap = math.inf
    cumulative = 0.0
    for start, end in zip(route, route[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_squared = dx * dx + dy * dy
        if length_squared <= 0:
            continue
        length = math.sqrt(length_squared)
        t = max(
            0.0,
            min(
                1.0,
                ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
                / length_squared,
            ),
        )
        projected = (start[0] + t * dx, start[1] + t * dy)
        gap = math.hypot(point[0] - projected[0], point[1] - projected[1])
        if gap < best_gap:
            best_station = cumulative + t * length
            best_gap = gap
        cumulative += length
    return best_station, best_gap


def _course_data_local_point(
    point: dict,
    *,
    ref_lat: float,
    ref_lon: float,
) -> tuple[float, float] | None:
    try:
        return shot_projection.world_to_local(
            float(point["latitude"]),
            float(point["longitude"]),
            ref_lat=ref_lat,
            ref_lon=ref_lon,
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _course_data_green_outline(
    hole: dict,
    route: list[tuple[float, float]],
    *,
    green_latitude: float,
) -> list[tuple[float, float]]:
    """Decode Garmin's 30-direction legacy green outline for drawing only.

    Garmin sampled the values from north clockwise before applying longitude's
    latitude correction. ``green_radii_local_offsets`` restores that coordinate
    transform. The result remains a display outline, not numeric F/M/B evidence.
    """
    radii = hole.get("greenRadii") or []
    if len(radii) != 30 or not route:
        return []
    center = route[-1]
    try:
        offsets = courseview_core.green_radii_local_offsets(radii, green_latitude)
    except (TypeError, ValueError, OverflowError):
        return []
    return [(center[0] + east, center[1] + north) for east, north in offsets]


def _course_data_hazards(
    hole: dict,
    route: list[tuple[float, float]],
    *,
    ref_lat: float,
    ref_lon: float,
) -> tuple[dict, list[dict]]:
    """Return proven water/bunker spans; unknown codes stay absent from product UI."""
    details: list[dict] = []
    local_rows: list[dict] = []
    water: list[list[float]] = []
    bunkers: list[list[float]] = []
    tee = route[0]
    for line in hole.get("lines") or []:
        if not isinstance(line, dict) or line.get("role") != "hazard-span":
            continue
        kind = line.get("surface")
        if kind not in ("water", "bunker"):
            continue
        source_points = line.get("points") or []
        if len(source_points) != 2:
            continue
        local = [
            _course_data_local_point(point, ref_lat=ref_lat, ref_lon=ref_lon)
            for point in source_points
        ]
        if any(point is None for point in local):
            continue
        first, second = local  # type: ignore[misc]
        first_distance = math.hypot(first[0] - tee[0], first[1] - tee[1])
        second_distance = math.hypot(second[0] - tee[0], second[1] - tee[1])
        front, back = (first, second) if first_distance <= second_distance else (second, first)
        front_m, back_m = sorted((first_distance, second_distance))
        front_route, front_side = _route_station(front, route)
        back_route, back_side = _route_station(back, route)
        if kind == "water":
            water.append([round(min(front_route, back_route), 1), round(max(front_route, back_route), 1)])
        else:
            bunkers.append([round(min(front_route, back_route), 1), round(min(front_side, back_side), 1)])
        local_rows.append(
            {
                "kind": kind,
                "front": front,
                "back": back,
                "frontM": round(front_m, 1),
                "backM": round(back_m, 1),
                "frontRouteM": round(front_route, 1),
                "backRouteM": round(back_route, 1),
                "sideM": round(min(front_side, back_side), 1),
            }
        )
    return {
        "water_carry": sorted(water),
        "bunkers": sorted(bunkers),
        "details": details,
    }, local_rows


def _course_data_frame(
    route: list[tuple[float, float]],
    extra_points: list[tuple[float, float]],
    *,
    ref_lat: float,
    ref_lon: float,
) -> tuple[Callable[[tuple[float, float]], tuple[float, float]], dict]:
    """Fit lightweight facts into a stable portrait affine display frame."""
    width, height, margin = 360, 560, 28.0
    tee, green = route[0], route[-1]
    dx, dy = green[0] - tee[0], green[1] - tee[1]
    length = math.hypot(dx, dy)
    forward = (dx / length, dy / length) if length > 0 else (0.0, 1.0)
    right = (forward[1], -forward[0])
    points = [*route, *extra_points]

    def axes(point: tuple[float, float]) -> tuple[float, float]:
        return (
            point[0] * right[0] + point[1] * right[1],
            point[0] * forward[0] + point[1] * forward[1],
        )

    values = [axes(point) for point in points]
    cross_min = min(value[0] for value in values)
    cross_max = max(value[0] for value in values)
    along_min = min(value[1] for value in values)
    along_max = max(value[1] for value in values)
    scale = min(
        (width - 2 * margin) / max(cross_max - cross_min, 1.0),
        (height - 2 * margin) / max(along_max - along_min, 1.0),
    )

    def project(point: tuple[float, float]) -> tuple[float, float]:
        cross, along = axes(point)
        return (
            margin + (cross - cross_min) * scale,
            height - margin - (along - along_min) * scale,
        )

    refs = []
    for local in ((0.0, 0.0), (120.0, 0.0), (0.0, 120.0)):
        latitude, longitude = shot_projection.local_to_world(
            local[0], local[1], ref_lat=ref_lat, ref_lon=ref_lon
        )
        px, py = project(local)
        refs.append(
            {
                "lat": round(latitude, 7),
                "lon": round(longitude, 7),
                "px": round(px, 1),
                "py": round(py, 1),
            }
        )
    return project, {
        "available": True,
        "widthPx": width,
        "heightPx": height,
        "refs": refs,
    }


def _lightweight_prep_hole(
    global_id: int,
    local_hole: int,
    *,
    ladder,
    par_record,
    render: bool,
) -> HolePrep | dict | None:
    course_data = courseview_core.load_cached_course_data(int(global_id))
    if not course_data:
        return None
    hole = next(
        (
            row
            for row in course_data.get("holes") or []
            if isinstance(row, dict) and row.get("holeNumber") == int(local_hole)
        ),
        None,
    )
    route_result = _course_data_route(hole or {})
    if hole is None or route_result is None:
        return None
    route, ref_lat, ref_lon = route_result
    route_rows = _route_with_cumulative(route)
    route_len = route_rows[-1][2]
    route_line = next(
        (
            row
            for row in hole.get("lines") or []
            if isinstance(row, dict) and row.get("role") == "route"
        ),
        None,
    )
    green_latitude = float((route_line or {}).get("points", [{}])[-1]["latitude"])
    green_outline = _course_data_green_outline(
        hole,
        route,
        green_latitude=green_latitude,
    )
    hazards, local_hazards = _course_data_hazards(
        hole,
        route,
        ref_lat=ref_lat,
        ref_lon=ref_lon,
    )
    extra = [*green_outline]
    for hazard in local_hazards:
        extra.extend((hazard["front"], hazard["back"]))
    project, projection = _course_data_frame(
        route,
        extra,
        ref_lat=ref_lat,
        ref_lon=ref_lon,
    )
    for hazard in local_hazards:
        front_px = project(hazard.pop("front"))
        back_px = project(hazard.pop("back"))
        hazards["details"].append(
            {
                **hazard,
                "frontPx": [round(front_px[0], 1), round(front_px[1], 1)],
                "backPx": [round(back_px[0], 1), round(back_px[1], 1)],
            }
        )
    green_px = [project(point) for point in green_outline]
    par_index = int(local_hole) - 1
    if par_record is not None and 0 <= par_index < len(par_record.par):
        par = int(par_record.par[par_index])
        par_source = par_record.par_source
    else:
        male = next(
            (
                row
                for row in hole.get("pars") or []
                if isinstance(row, dict) and row.get("playerType") == 1
            ),
            None,
        )
        first = male or next(iter(hole.get("pars") or []), {})
        par = int(first.get("par") or course_reference.estimate_par_from_length(route_len))
        par_source = "courseData"
    steps, cautions, landing, tee_club = _strategy(par, route_len, hazards, ladder)
    green_lat, green_lon = shot_projection.local_to_world(
        route[-1][0], route[-1][1], ref_lat=ref_lat, ref_lon=ref_lon
    )
    source_ref = (
        f"courseData:{int(global_id)}:{int(course_data['buildId'])}:"
        f"{course_data['sourceVariant']}"
    )
    prep = HolePrep(
        globalId=int(global_id),
        localHole=int(local_hole),
        hole=int(local_hole),
        par=par,
        par_source=par_source,
        blue_yards=yd(route_len),
        route_len_m=round(route_len, 1),
        route=route_rows,
        geometryCoverage="partial",
        sourceRefs=[f"course:{int(global_id)}", source_ref],
        missingData=[
            {
                "label": "geometry",
                "reason": "precise prodgeometry is pending; factual CourseView courseData is active",
            }
        ],
        candidateRoutes=_candidate_routes(ladder, hazards),
        carryTargets=_carry_targets(landing, hazards),
        steps=steps,
        cautions=cautions,
        landing_m=round(landing, 1) if landing else None,
        tee_club=tee_club,
        hazards=hazards,
        playsLike={"available": False},
        greenDistances={
            "available": True,
            "middleM": round(route_len, 1),
            "middleYd": yd(route_len),
            "middleLat": round(green_lat, 7),
            "middleLon": round(green_lon, 7),
        },
        greenSlope={"available": False},
        holeImageProjection=projection,
        greenOutline={
            "available": bool(green_px),
            "source": "courseData.GreenRadii",
            "distanceUnit": None,
            "pointsPx": [[round(x, 1), round(y, 1)] for x, y in green_px],
        },
    )
    return prep.to_dict() if render else prep


def lightweight_prep_hole(
    global_id: int,
    local_hole: int,
    *,
    ladder=None,
    par_record=None,
    player_id: str = OWNER_ID,
) -> dict | None:
    """Build the factual CourseView-only map without touching precise mesh geometry.

    Mobile course packages use this for one first-hole seed.  It is deliberately separate from
    :func:`prep_hole`: if a background prodgeometry install wins the race by a few milliseconds,
    the first screen must still receive the small route/green/hazard drawing immediately instead
    of entering the expensive precise mesh path before anything can be shown.
    """
    resolved_ladder = ladder or effective_club_ladder(player_id)
    resolved_par = par_record or course_reference.load_course_par(int(global_id))
    value = _lightweight_prep_hole(
        int(global_id),
        int(local_hole),
        ladder=resolved_ladder,
        par_record=resolved_par,
        render=True,
    )
    return value if isinstance(value, dict) else None


def _candidate_routes(ladder: list[tuple[str, int]], hazards: dict) -> list[dict]:
    if not ladder:
        return []
    longest_name, longest_m = ladder[0]
    safe_name, safe_m = next((row for row in ladder[1:] if row[1] >= 120), ladder[0])
    risk = 3 if (hazards.get("water_carry") or hazards.get("bunkers")) else 1
    return [
        {"id": "safe", "club": safe_name, "carryM": float(safe_m), "riskScore": 0, "source": "course_prep"},
        {"id": "stock", "club": longest_name, "carryM": float(longest_m), "riskScore": 1, "source": "course_prep"},
        {"id": "attack", "club": longest_name, "carryM": float(longest_m), "riskScore": risk, "source": "course_prep"},
    ]


def _carry_targets(landing_m: float | None, hazards: dict) -> list[dict]:
    rows: list[dict] = []
    if landing_m is not None:
        rows.append({"kind": "landing", "distanceM": round(landing_m, 1)})
    for start, end in hazards.get("water_carry") or []:
        rows.append({"kind": "water_clear", "enterM": float(start), "clearM": float(end)})
    for distance, side in hazards.get("bunkers") or []:
        rows.append({"kind": "bunker", "distanceM": float(distance), "sideM": float(side)})
    return rows


def _your_shots(md: dict, by: dict, route, global_id: int, local_hole: int, overlay: dict,
                player_id: str = OWNER_ID) -> list[dict]:
    """The player's past TEE/APPROACH end positions projected into display px.

    World→local uses the calibrated frame in :mod:`ai_caddie.geometry.shot_projection`; local→px reuses
    render_hole's EXACT overlay transform (:func:`ai_caddie.geometry.hole_render.overlay_projector`).
    Pixel ints are clipped to the overlay bounds; capped at ``MAX_SCATTER_SHOTS`` newest-first.
    """
    hole_meta = md.get("hole") or {}
    ref_lat, ref_lon = hole_meta.get("RefLat"), hole_meta.get("RefLon")
    if ref_lat is None or ref_lon is None:
        return []
    # Owner: None -> the flat owner tree (unchanged). Member: only their own player-scoped tree,
    # so a member's scatter is built solely from their own logged rounds (never another player's).
    sources = None
    if player_id != OWNER_ID:
        from ai_caddie.history.history import _player_shot_sources
        sources = _player_shot_sources(player_id)
    # Owner keeps its clubs.json override; a member never applies the owner override to their shots.
    shots = shot_projection.shots_for_hole(
        global_id, local_hole, sources=sources, apply_overrides=(player_id == OWNER_ID)
    )
    if not shots:
        return []
    to_px = hole_render.overlay_projector(by, route)
    width, height = int(overlay["w"]), int(overlay["h"])
    out: list[dict] = []
    for shot in shots[:MAX_SCATTER_SHOTS]:
        x, y = shot_projection.project_world_to_pixel(
            shot["lat"], shot["lon"], ref_lat=float(ref_lat), ref_lon=float(ref_lon), to_px=to_px,
        )
        out.append({
            "x": min(max(int(round(x)), 0), width - 1),
            "y": min(max(int(round(y)), 0), height - 1),
            "club": shot.get("club"),
            "shotType": shot.get("shotType"),
            "roundId": shot.get("roundId"),
        })
    return out


def prep_hole(global_id: int, local_hole: int, *, ladder=None, par_record=None, render=True,
              include_shots=False, player_id: str = OWNER_ID) -> HolePrep | dict | None:
    """Compose exact prep, or the cached factual CourseView fallback while geometry upgrades."""
    ladder = ladder or effective_club_ladder(player_id)
    try:
        coverage = geometry_coverage_for_hole(
            global_id,
            local_hole,
            require_current_authority=True,
        )
    except Exception:
        coverage = {
            "coverage": "missing",
            "missingData": [{"label": "geometry", "reason": "prodgeometry geometry could not be loaded"}],
        }
    if coverage.get("coverage") != "ready":
        lightweight = _lightweight_prep_hole(
            global_id,
            local_hole,
            ladder=ladder,
            par_record=par_record,
            render=render,
        )
        if lightweight is not None:
            return lightweight
    try:
        md, by = hole_render.load_mesh(global_id, local_hole)
    except Exception:
        return _lightweight_prep_hole(
            global_id,
            local_hole,
            ladder=ladder,
            par_record=par_record,
            render=render,
        )
    route, route_len = derive_route(md)
    if not route or not route_len:
        return _lightweight_prep_hole(
            global_id,
            local_hole,
            ladder=ladder,
            par_record=par_record,
            render=render,
        )
    if par_record is None:
        par_record = course_reference.load_course_par(global_id)
    par_idx = local_hole - 1
    if par_record is not None and 0 <= par_idx < len(par_record.par):
        par = par_record.par[par_idx]
        par_source = par_record.par_source
    else:
        par = course_reference.estimate_par_from_length(route_len)
        par_source = "estimate"
    hazards = route_hazards(by, route)
    steps, cautions, landing, tee_club = _strategy(par, route_len, hazards, ladder)
    missing_data = [
        row
        for row in coverage.get("missingData", [])
        if isinstance(row, dict)
    ]
    prep = HolePrep(
        globalId=int(global_id), localHole=int(local_hole),
        hole=local_hole, par=par, par_source=par_source,
        blue_yards=yd(route_len), route_len_m=round(route_len, 1),
        route=_route_with_cumulative(route),
        geometryCoverage=str(coverage.get("coverage") or "missing"),
        geometryRevision=(
            str(coverage.get("geometryRevision"))
            if coverage.get("geometryRevision")
            else None
        ),
        sourceRefs=[f"course:{int(global_id)}", f"geometry:{int(global_id)}:{int(local_hole)}"],
        missingData=missing_data,
        candidateRoutes=_candidate_routes(ladder, hazards),
        carryTargets=_carry_targets(landing, hazards),
        steps=steps, cautions=cautions, landing_m=(round(landing, 1) if landing else None),
        tee_club=tee_club, hazards=hazards,
        playsLike=_hole_playslike(by, route),
        greenDistances=_green_distances(by, route, md),
        greenSlope=_green_slope(by, route),
        holeImageProjection=_hole_image_projection(by, route, md),
    )
    result = prep.to_dict()
    if render:
        image, meta = hole_render.render_hole(global_id, local_hole, route, route_len, landing_m=landing)
        result["map"] = {"image": image, "overlay": meta}
        if include_shots:
            try:
                scatter = _your_shots(md, by, route, global_id, local_hole, meta, player_id=player_id)
            except Exception:
                scatter = []  # scatter is an enhancement — never break prep over it
            if scatter:
                result["yourShots"] = scatter
    return result if render else prep


def _missing_hole(global_id: int, local_hole: int, par_record=None) -> dict:
    par_idx = int(local_hole) - 1
    if par_record is not None and 0 <= par_idx < len(par_record.par):
        par = int(par_record.par[par_idx])
        par_source = par_record.par_source
    else:
        par = 4
        par_source = "estimate"
    return {
        "globalId": int(global_id),
        "localHole": int(local_hole),
        "hole": int(local_hole),
        "par": par,
        "par_source": par_source,
        "blue_yards": 0,
        "route_len_m": 0.0,
        "route": [],
        "geometryCoverage": "missing",
        "sourceRefs": [f"course:{int(global_id)}", f"geometry:{int(global_id)}:{int(local_hole)}"],
        "missingData": [{"label": "geometry", "reason": "prodgeometry geometry is missing for this hole"}],
        "candidateRoutes": [],
        "carryTargets": [],
        "steps": [],
        "cautions": [],
        "landing_m": None,
        "tee_club": None,
        "hazards": {"water_carry": [], "bunkers": [], "details": []},
    }


def prep_nine(global_id: int, holes=range(1, 10), *, ladder=None, render=True, include_missing: bool = False,
              include_shots: bool = False, player_id: str = OWNER_ID) -> list:
    """Pre-round prep for every hole of a nine that has geometry.

    Par is cache-first: the stored ``data/courses/<gid>.json`` record, else ``resolve_par``
    (courseview). For an UNPLAYED course with no cached release, ``resolve_par`` does a one-time
    blocking CourseView fetch (then caches it), so the first prep of a cold course is slower.
    When ``include_missing`` is true, requested holes without geometry are returned as degraded
    DTO rows instead of being skipped.
    """
    if ladder is None:
        ladder = effective_club_ladder(player_id)
    par_record = course_reference.load_course_par(global_id)
    if par_record is None:
        par_record = course_reference.resolve_par(global_id)
    out = []
    for hole in holes:
        prep = prep_hole(global_id, hole, ladder=ladder, par_record=par_record, render=render,
                         include_shots=include_shots, player_id=player_id)
        if prep is not None:
            out.append(prep.to_dict() if include_missing and hasattr(prep, "to_dict") else prep)
        elif include_missing:
            out.append(_missing_hole(global_id, hole, par_record))
    return out
