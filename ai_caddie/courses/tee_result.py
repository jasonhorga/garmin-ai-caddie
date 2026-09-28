"""Tee-shot result classifier: did the drive finish in the fairway, left of it or right of it?

This is the single algorithm named in ``docs/design/2026-09-25-ui-redesign/IMPLEMENTATION_PLAN.md``
(B0).  The phone and Watch run a Swift port of it offline to preselect the scorecard's
fairway chip; the server runs this module for statistics.  Both read the shared vectors in
``tests/fixtures/tee_result_vectors.json``, so any behaviour change must update those vectors.

Inputs are plain WGS84 values so no client needs the server's local mesh frame:

* ``point``: ``[lat, lon]`` of the second shot (or the first putt when there was no second shot);
* ``fairway_outline``: the ``HolePrep.fairwayOutline`` payload (``version`` 1) or ``None``;
* ``route``: the factual tee-to-green line as ``[[lat, lon], ...]``;
* ``par``: the hole's par.

The result is ``"hit"``, ``"left"``, ``"right"`` or ``None``.  ``None`` means "do not preselect":
par 3, no outline, an unknown outline version, no position, no usable route, or a point exactly
on the route line outside the fairway.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

SUPPORTED_VERSION = 1
# Same WGS84 equatorial radius as ``ai_caddie.geometry.shot_projection`` (Garmin's mesh frame).
EARTH_RADIUS_M = 6378137.0
# A ball this close to the fairway edge counts as in the fairway (GPS and mesh are not better).
EDGE_TOLERANCE_M = 0.5

Point = tuple[float, float]


def _latlon(value) -> Point | None:
    try:
        lat, lon = float(value[0]), float(value[1])
    except (IndexError, TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    return lat, lon


def _ring(values) -> list[Point]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    ring = [point for point in (_latlon(value) for value in values) if point is not None]
    return ring if len(ring) >= 3 else []


def _polygons(fairway_outline) -> list[tuple[list[Point], list[list[Point]]]]:
    if not isinstance(fairway_outline, dict) or fairway_outline.get("version") != SUPPORTED_VERSION:
        return []
    polygons = []
    for row in fairway_outline.get("polygons") or []:
        if not isinstance(row, dict):
            continue
        outer = _ring(row.get("outerLatLon"))
        if not outer:
            continue
        holes = [ring for ring in (_ring(values) for values in row.get("holesLatLon") or []) if ring]
        polygons.append((outer, holes))
    return polygons


def _projector(origin: Point):
    lat0, lon0 = origin
    cos_lat0 = math.cos(math.radians(lat0))

    def project(point: Point) -> Point:
        lat, lon = point
        return (
            math.radians(lon - lon0) * EARTH_RADIUS_M * cos_lat0,
            math.radians(lat - lat0) * EARTH_RADIUS_M,
        )

    return project


def _inside(point: Point, ring: list[Point]) -> bool:
    """Even/odd ray cast; winding direction does not matter."""
    x, y = point
    inside = False
    count = len(ring)
    for index in range(count):
        x1, y1 = ring[index]
        x2, y2 = ring[(index + 1) % count]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _segment_distance(point: Point, start: Point, end: Point) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    t = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared))
    return math.hypot(point[0] - (start[0] + t * dx), point[1] - (start[1] + t * dy))


def _ring_distance(point: Point, ring: list[Point]) -> float:
    count = len(ring)
    return min(_segment_distance(point, ring[index], ring[(index + 1) % count]) for index in range(count))


def classify_tee_result(point, fairway_outline, route, par) -> str | None:
    try:
        if int(par) == 3:
            return None
    except (TypeError, ValueError):
        return None
    position = _latlon(point) if point is not None else None
    polygons = _polygons(fairway_outline)
    route_points = [p for p in (_latlon(value) for value in (route or [])) if p is not None]
    if position is None or not polygons or len(route_points) < 2:
        return None

    # Origin = mean of every outer-ring vertex, so the flat projection error stays sub-millimetre.
    outer_vertices = [vertex for outer, _holes in polygons for vertex in outer]
    origin = (
        sum(vertex[0] for vertex in outer_vertices) / len(outer_vertices),
        sum(vertex[1] for vertex in outer_vertices) / len(outer_vertices),
    )
    project = _projector(origin)
    p = project(position)

    for outer, holes in polygons:
        outer_m = [project(vertex) for vertex in outer]
        holes_m = [[project(vertex) for vertex in hole] for hole in holes]
        in_polygon = _inside(p, outer_m) and not any(_inside(p, hole) for hole in holes_m)
        near_edge = min(_ring_distance(p, ring) for ring in [outer_m, *holes_m]) <= EDGE_TOLERANCE_M
        if in_polygon or near_edge:
            return "hit"

    route_m = [project(vertex) for vertex in route_points]
    best: tuple[float, int] | None = None
    for index in range(len(route_m) - 1):
        distance = _segment_distance(p, route_m[index], route_m[index + 1])
        if best is None or distance < best[0]:
            best = (distance, index)
    assert best is not None
    start, end = route_m[best[1]], route_m[best[1] + 1]
    # x east / y north: a positive cross product is to the left of the direction of play.
    cross = (end[0] - start[0]) * (p[1] - start[1]) - (end[1] - start[1]) * (p[0] - start[0])
    if cross > 0:
        return "left"
    if cross < 0:
        return "right"
    return None
