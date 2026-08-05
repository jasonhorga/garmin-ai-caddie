#!/usr/bin/env python3
"""Cross-check private DSKIMG vector types against factual CourseView sources.

The audit never assigns a product label from visual resemblance.  It samples
decoded prodgeometry triangle interiors and release-bound lightweight control
points, then reports which DSKIMG area types cover those facts.  The JSON output
is intended to make a later consume/ignore decision reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from itertools import pairwise
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw

from ai_caddie.courses.courseview_core import parse_course_data_json
from ai_caddie.geometry.shot_projection import local_to_world
from tools.courseview.parse_courseview import (
    _unwrap_pb_img,
    extract_gmp,
    parse_gmp_header,
    parse_lbl_header,
    parse_points,
    parse_polygons,
    parse_polylines,
    parse_rgn_header,
    parse_tre,
)

SCHEMA = "ai-caddie-dskimg-vector-semantics-audit-v1"
MAX_TRIANGLE_SAMPLES_PER_MESH = 180
AREA_EDGE_TOLERANCE_METRES = 1.5
SURFACE_MATCH_RESOLUTION_METRES = 2.0

# These meshes have an observable 2D product meaning.  Structural/cosmetic
# meshes remain available in the input but are intentionally not used to name a
# private vector type.
SURFACE_MESHES = {
    "Beach.drc",
    "Bunker.drc",
    "Cartpath.drc",
    "Cliff.drc",
    "Fairway.drc",
    "Green.drc",
    "Lake.drc",
    "Ocean.drc",
    "Rough.drc",
    "Teebox.drc",
    "TreeArea.drc",
}

# Every top-down mesh that could plausibly explain a DSKIMG area.  Renderer-only
# variants are kept here as negative controls: a private type is not promoted to
# a product surface merely because it happens to overlap a VFX duplicate.
SURFACE_MATCH_MESHES = {
    "Beach.drc",
    "Bridge.drc",
    "Bunker.drc",
    "Cartpath.drc",
    "Cliff.drc",
    "CliffUV2.drc",
    "Fairway.drc",
    "Fringe.drc",
    "Green.drc",
    "IslandExt.drc",
    "Lake.drc",
    "LakeSide.drc",
    "Ocean.drc",
    "OceanSide.drc",
    "Rough.drc",
    "Teebox.drc",
    "TreeArea.drc",
    "VfxGreenA.drc",
    "VfxGreenB.drc",
    "VfxOcean.drc",
    "VfxStream.drc",
}
SCENE_COVERAGE_MESH = "PlayableBounds.drc"

# Terminal product decisions.  "fallback-display-only" never authorizes exact
# distances, lies or penalties; prodgeometry/courseData remain authoritative.
# Opaque rows are deliberately terminal: preserve the raw object for a future
# version review, but do not invent a UI or domain meaning today.
SEMANTIC_DECISIONS: dict[str, dict[int, dict[str, str]]] = {
    "area": {
        0x010B01: {
            "semantic": "ocean_context",
            "productUse": "fallback-display-only",
            "basis": "Ocean/OceanSide/VfxOcean cross-source overlap; one observed image",
        },
        0x010B08: {
            "semantic": "opaque_mixed_context_area",
            "productUse": "preserve-raw-ignore",
            "basis": "no stable single-surface mapping across the bound corpus",
        },
        0x010D01: {
            "semantic": "course_complex_boundary",
            "productUse": "structural-framing-only",
            "basis": "one enclosing polygon per unique embedded image",
        },
        0x011400: {
            "semantic": "opaque_singleton_context_area",
            "productUse": "preserve-raw-ignore",
            "basis": "sparse singleton geometry with no stable surface binding",
        },
        0x011402: {
            "semantic": "tee_area",
            "productUse": "fallback-display-only",
            "basis": "tee-route-start and Teebox cross-source coverage",
        },
        0x011403: {
            "semantic": "fairway_area",
            "productUse": "fallback-display-only",
            "basis": "per-hole topology, shape and Fairway cross-source coverage",
        },
        0x011404: {
            "semantic": "green_area",
            "productUse": "fallback-display-only",
            "basis": "one-per-route topology, shape and Green/VfxGreen coverage",
        },
        0x011405: {
            "semantic": "bunker_area",
            "productUse": "fallback-display-only",
            "basis": "multi-object topology, shape and bunker control/surface coverage",
        },
        0x011406: {
            "semantic": "opaque_coastal_terrain_area",
            "productUse": "preserve-raw-ignore",
            "basis": "two-image coastal class with mixed Beach/Cliff/Ocean/land overlap",
        },
        0x011407: {
            "semantic": "tree_area",
            "productUse": "fallback-display-only",
            "basis": "TreeArea triangle coverage and reverse surface overlap",
        },
        0x011409: {
            "semantic": "inner_hole_corridor",
            "productUse": "structural-clipping-only",
            "basis": "one-per-route nested hole domain; smaller of the paired layers",
        },
        0x01140A: {
            "semantic": "stream_water_area",
            "productUse": "fallback-display-only",
            "basis": "Lake and VfxStream cross-source overlap",
        },
        0x01140B: {
            "semantic": "teebox_surface",
            "productUse": "fallback-display-only",
            "basis": "near-exact Teebox cross-source overlap",
        },
        0x01140D: {
            "semantic": "opaque_small_context_area",
            "productUse": "preserve-raw-ignore",
            "basis": "two-image sparse class with no stable surface binding",
        },
        0x01140E: {
            "semantic": "outer_hole_domain",
            "productUse": "structural-clipping-only",
            "basis": "one-per-route nested hole domain; larger of the paired layers",
        },
    },
    "line": {
        0x010A00: {
            "semantic": "stream_water_edge",
            "productUse": "fallback-display-only",
            "basis": "Lake/VfxStream overlap and exact 0x01140a edge binding",
        },
        0x012E00: {
            "semantic": "hole_route",
            "productUse": "fallback-route",
            "basis": "sub-metre courseData and hole.json route residuals",
        },
        0x012E05: {
            "semantic": "cart_path",
            "productUse": "fallback-display-only",
            "basis": "direct Cartpath triangle overlap across seven observed images",
        },
    },
    "point": {
        0x013800: {
            "semantic": "course_layout_label_anchor",
            "productUse": "metadata-anchor-only",
            "basis": "decoded LBL course/layout names",
        },
        0x013801: {
            "semantic": "tee_route_start_anchor",
            "productUse": "fallback-position-anchor",
            "basis": "nearest courseData tee-route-start residual",
        },
    },
}


def _percent(count: int, total: int) -> float:
    return round(100.0 * count / total, 6) if total else 0.0


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[round((len(ordered) - 1) * quantile)], 6)


def _distance_metres(first: tuple[float, float], second: tuple[float, float]) -> float:
    latitude = (first[0] + second[0]) / 2.0
    return math.hypot(
        (first[1] - second[1]) * 111_320.0 * math.cos(math.radians(latitude)),
        (first[0] - second[0]) * 111_320.0,
    )


def _point_polyline_metres(
    point: tuple[float, float], line: list[tuple[float, float]]
) -> float:
    if len(line) == 1:
        return _distance_metres(point, line[0])
    latitude, longitude = point
    return min(
        _point_segment_metres(
            latitude,
            longitude,
            first[0],
            first[1],
            second[0],
            second[1],
        )
        for first, second in pairwise(line)
    )


def _nearest_polyline_metres(
    point: tuple[float, float], lines: list[list[tuple[float, float]]]
) -> float | None:
    return min((_point_polyline_metres(point, line) for line in lines), default=None)


def _nearest_point_metres(
    point: tuple[float, float], candidates: list[tuple[float, float]]
) -> float | None:
    return min((_distance_metres(point, other) for other in candidates), default=None)


def _line_length_metres(line: list[tuple[float, float]]) -> float:
    return sum(_distance_metres(first, second) for first, second in pairwise(line))


def _polygon_area_metres(polygon: Any) -> float:
    latitude = sum(polygon.lats[:-1]) / max(1, len(polygon.lats) - 1)
    scale_x = 111_320.0 * math.cos(math.radians(latitude))
    scale_y = 111_320.0
    return (
        abs(
            sum(
                polygon.lons[index] * scale_x * polygon.lats[index + 1] * scale_y
                - polygon.lons[index + 1] * scale_x * polygon.lats[index] * scale_y
                for index in range(len(polygon.lats) - 1)
            )
        )
        / 2.0
    )


def _point_in_ring(latitude: float, longitude: float, polygon: Any) -> bool:
    """Odd/even point-in-polygon test in the tiny local WGS84 footprint."""
    inside = False
    lats = polygon.lats
    lons = polygon.lons
    for index in range(len(lats) - 1):
        lat_a, lon_a = lats[index], lons[index]
        lat_b, lon_b = lats[index + 1], lons[index + 1]
        if (lat_a > latitude) == (lat_b > latitude):
            continue
        crossing = lon_a + (latitude - lat_a) * (lon_b - lon_a) / (lat_b - lat_a)
        if longitude < crossing:
            inside = not inside
    return inside


def _point_segment_metres(
    latitude: float,
    longitude: float,
    lat_a: float,
    lon_a: float,
    lat_b: float,
    lon_b: float,
) -> float:
    cos_lat = math.cos(math.radians(latitude))
    east = (longitude - lon_a) * 111_320.0 * cos_lat
    north = (latitude - lat_a) * 111_320.0
    edge_east = (lon_b - lon_a) * 111_320.0 * cos_lat
    edge_north = (lat_b - lat_a) * 111_320.0
    squared = edge_east * edge_east + edge_north * edge_north
    ratio = (
        max(0.0, min(1.0, (east * edge_east + north * edge_north) / squared))
        if squared
        else 0.0
    )
    return math.hypot(east - ratio * edge_east, north - ratio * edge_north)


def _near_ring(latitude: float, longitude: float, polygon: Any) -> bool:
    if _point_in_ring(latitude, longitude, polygon):
        return True
    return any(
        _point_segment_metres(
            latitude,
            longitude,
            polygon.lats[index],
            polygon.lons[index],
            polygon.lats[index + 1],
            polygon.lons[index + 1],
        )
        <= AREA_EDGE_TOLERANCE_METRES
        for index in range(len(polygon.lats) - 1)
    )


def _area_index(
    polygons: Iterable[Any],
) -> dict[int, list[tuple[Any, tuple[float, ...]]]]:
    by_type: dict[int, list[tuple[Any, tuple[float, ...]]]] = defaultdict(list)
    for polygon in polygons:
        by_type[polygon.ext_type].append(
            (
                polygon,
                (
                    min(polygon.lats),
                    min(polygon.lons),
                    max(polygon.lats),
                    max(polygon.lons),
                ),
            )
        )
    return dict(by_type)


def _memberships(
    latitude: float,
    longitude: float,
    areas: dict[int, list[tuple[Any, tuple[float, ...]]]],
) -> set[int]:
    latitude_pad = AREA_EDGE_TOLERANCE_METRES / 111_320.0
    longitude_pad = latitude_pad / max(0.05, math.cos(math.radians(latitude)))
    result: set[int] = set()
    for ext_type, rows in areas.items():
        for polygon, (south, west, north, east) in rows:
            if not (
                south - latitude_pad <= latitude <= north + latitude_pad
                and west - longitude_pad <= longitude <= east + longitude_pad
            ):
                continue
            if _near_ring(latitude, longitude, polygon):
                result.add(ext_type)
                break
    return result


def _load_vectors(path: Path) -> dict[str, Any]:
    source = path.read_bytes()
    image = source if source[0x10:0x16] == b"DSKIMG" else _unwrap_pb_img(source)
    gmp = extract_gmp(image)
    offsets = parse_gmp_header(gmp)
    tre = parse_tre(gmp, offsets.tre)
    rgn = parse_rgn_header(gmp, offsets.rgn)
    lbl = parse_lbl_header(gmp, offsets.lbl)
    points = parse_points(gmp, rgn, tre, strict=True)
    return {
        "sourceSha256": hashlib.sha256(source).hexdigest(),
        "embeddedImageSha256": hashlib.sha256(image).hexdigest(),
        "bbox": tre.bbox,
        "areas": parse_polygons(gmp, rgn, tre, strict=True),
        "lines": parse_polylines(gmp, rgn, tre, strict=True),
        "points": points,
        "pointLabels": [
            lbl.text_at(gmp, point.label_off) if point.has_label else None
            for point in points
        ],
    }


def _triangle_samples(decoded: dict[str, Any]) -> Iterable[tuple[str, float, float]]:
    hole = decoded["hole"]
    ref_lat = float(hole["RefLat"])
    ref_lon = float(hole["RefLon"])
    for mesh in decoded.get("meshes") or []:
        name = mesh.get("name")
        faces = mesh.get("faces") or []
        positions = mesh.get("positions") or []
        if name not in SURFACE_MESHES or not faces or not positions:
            continue
        stride = max(1, math.ceil(len(faces) / MAX_TRIANGLE_SAMPLES_PER_MESH))
        for face in faces[::stride]:
            try:
                vertices = [positions[int(index)] for index in face]
                east = -sum(float(vertex[0]) for vertex in vertices) / 3.0
                north = sum(float(vertex[2]) for vertex in vertices) / 3.0
                latitude, longitude = local_to_world(
                    east,
                    north,
                    ref_lat=ref_lat,
                    ref_lon=ref_lon,
                )
            except (IndexError, TypeError, ValueError, OverflowError):
                continue
            yield str(name), latitude, longitude


def _inside_bbox(latitude: float, longitude: float, bbox: Any) -> bool:
    return bbox.south <= latitude <= bbox.north and bbox.west <= longitude <= bbox.east


def _route_controls(parsed: dict[str, Any]) -> Iterable[tuple[str, float, float]]:
    for hole in parsed.get("holes") or []:
        route = next(
            (
                row.get("points") or []
                for row in hole.get("lines") or []
                if row.get("role") == "route"
            ),
            [],
        )
        if route:
            yield (
                "teeRouteStart",
                float(route[0]["latitude"]),
                float(route[0]["longitude"]),
            )
            yield (
                "greenRouteEnd",
                float(route[-1]["latitude"]),
                float(route[-1]["longitude"]),
            )
            for first, second in pairwise(route):
                yield (
                    "routeInterior",
                    (float(first["latitude"]) + float(second["latitude"])) / 2.0,
                    (float(first["longitude"]) + float(second["longitude"])) / 2.0,
                )
        for line in hole.get("lines") or []:
            surface = line.get("surface")
            if surface not in {"water", "bunker"}:
                continue
            for point in line.get("points") or []:
                yield (
                    f"{surface}SpanEndpoint",
                    float(point["latitude"]),
                    float(point["longitude"]),
                )
        for anchor in hole.get("hazardAnchors") or []:
            surface = anchor.get("surface")
            if surface in {"water", "bunker"}:
                yield (
                    f"{surface}Anchor",
                    float(anchor["latitude"]),
                    float(anchor["longitude"]),
                )


def _route_reference(parsed: dict[str, Any]) -> dict[str, Any]:
    routes: list[list[tuple[float, float]]] = []
    starts: list[tuple[float, float]] = []
    ends: list[tuple[float, float]] = []
    hazards: dict[str, list[tuple[float, float]]] = {
        "water": [],
        "bunker": [],
    }
    for hole in parsed.get("holes") or []:
        route = next(
            (
                [
                    (float(point["latitude"]), float(point["longitude"]))
                    for point in row.get("points") or []
                ]
                for row in hole.get("lines") or []
                if row.get("role") == "route"
            ),
            [],
        )
        if route:
            routes.append(route)
            starts.append(route[0])
            ends.append(route[-1])
        for line in hole.get("lines") or []:
            surface = line.get("surface")
            if surface in hazards:
                hazards[surface].extend(
                    (float(point["latitude"]), float(point["longitude"]))
                    for point in line.get("points") or []
                )
        for anchor in hole.get("hazardAnchors") or []:
            surface = anchor.get("surface")
            if surface in hazards:
                hazards[surface].append(
                    (float(anchor["latitude"]), float(anchor["longitude"]))
                )
    return {"routes": routes, "starts": starts, "ends": ends, "hazards": hazards}


def _route_points(parsed: dict[str, Any]) -> list[tuple[float, float]]:
    return [point for route in _route_reference(parsed)["routes"] for point in route]


def _route_alignment(
    parsed: dict[str, Any], vectors: dict[str, Any]
) -> tuple[float, float | None, float | None]:
    points = _route_points(parsed)
    if not points:
        return 0.0, None, None
    coverage = sum(
        _inside_bbox(latitude, longitude, vectors["bbox"])
        for latitude, longitude in points
    ) / len(points)
    route_lines = [
        list(zip(line.lats, line.lons))
        for line in vectors["lines"]
        if line.ext_type == 0x012E00
    ]
    distances = [
        distance
        for point in points
        if (distance := _nearest_polyline_metres(point, route_lines)) is not None
    ]
    return (
        coverage,
        round(statistics.median(distances), 6) if distances else None,
        _percentile(distances, 0.95),
    )


def _hole_route_alignment(
    hole: dict[str, Any], vectors: dict[str, Any]
) -> tuple[float, float | None, float | None]:
    try:
        ref_lat = float(hole["RefLat"])
        ref_lon = float(hole["RefLon"])
        local_points = next(
            (
                row.get("Line") or []
                for row in hole.get("Doglegs") or []
                if row.get("Line")
            ),
            [],
        )
        points = [
            local_to_world(
                float(point["X"]),
                float(point["Y"]),
                ref_lat=ref_lat,
                ref_lon=ref_lon,
            )
            for point in local_points
        ]
    except (KeyError, TypeError, ValueError, OverflowError):
        points = []
    if not points:
        return 0.0, None, None
    coverage = sum(
        _inside_bbox(latitude, longitude, vectors["bbox"])
        for latitude, longitude in points
    ) / len(points)
    route_lines = [
        list(zip(line.lats, line.lons))
        for line in vectors["lines"]
        if line.ext_type == 0x012E00
    ]
    distances = [
        distance
        for point in points
        if (distance := _nearest_polyline_metres(point, route_lines)) is not None
    ]
    return (
        coverage,
        round(statistics.median(distances), 6) if distances else None,
        _percentile(distances, 0.95),
    )


def _dedupe_points(points: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    return list(dict.fromkeys((round(lat, 8), round(lon, 8)) for lat, lon in points))


def _vector_geometry_summary(
    vectors_by_sha: dict[str, dict[str, Any]],
    course_data_by_sha: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    area_sizes: dict[int, list[float]] = defaultdict(list)
    line_lengths: dict[int, list[float]] = defaultdict(list)
    line_route_distances: dict[int, list[float]] = defaultdict(list)
    line_area_hits: dict[int, Counter[int]] = defaultdict(Counter)
    line_vertices: Counter[int] = Counter()
    point_distances: dict[int, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    point_labels: dict[int, Counter[str]] = defaultdict(Counter)
    point_counts: Counter[int] = Counter()

    for image_sha, vectors in vectors_by_sha.items():
        areas = _area_index(vectors["areas"])
        for polygon in vectors["areas"]:
            area_sizes[polygon.ext_type].append(_polygon_area_metres(polygon))

        references = [
            _route_reference(row) for row in course_data_by_sha.get(image_sha, [])
        ]
        routes = [route for ref in references for route in ref["routes"]]
        starts = _dedupe_points(point for ref in references for point in ref["starts"])
        ends = _dedupe_points(point for ref in references for point in ref["ends"])
        hazards = {
            surface: _dedupe_points(
                point for ref in references for point in ref["hazards"][surface]
            )
            for surface in ("water", "bunker")
        }

        for line in vectors["lines"]:
            ext_type = line.ext_type
            points = list(zip(line.lats, line.lons))
            line_lengths[ext_type].append(_line_length_metres(points))
            for point in points:
                line_vertices[ext_type] += 1
                distance = _nearest_polyline_metres(point, routes)
                if distance is not None:
                    line_route_distances[ext_type].append(distance)
                line_area_hits[ext_type].update(_memberships(*point, areas))

        for point, label in zip(vectors["points"], vectors["pointLabels"]):
            ext_type = point.ext_type
            position = (point.lat, point.lon)
            point_counts[ext_type] += 1
            if label:
                point_labels[ext_type][label] += 1
            for name, candidates in (
                ("teeRouteStart", starts),
                ("greenRouteEnd", ends),
                ("waterControl", hazards["water"]),
                ("bunkerControl", hazards["bunker"]),
            ):
                distance = _nearest_point_metres(position, candidates)
                if distance is not None:
                    point_distances[ext_type][name].append(distance)

    return {
        "areas": {
            f"0x{ext_type:06x}": {
                "objectCount": len(values),
                "medianAreaSquareMetres": round(statistics.median(values), 6),
                "p95AreaSquareMetres": _percentile(values, 0.95),
            }
            for ext_type, values in sorted(area_sizes.items())
        },
        "lines": {
            f"0x{ext_type:06x}": {
                "objectCount": len(line_lengths[ext_type]),
                "vertexCount": line_vertices[ext_type],
                "medianLengthMetres": round(
                    statistics.median(line_lengths[ext_type]), 6
                ),
                "routeVertexDistanceMetres": {
                    "median": (
                        round(statistics.median(line_route_distances[ext_type]), 6)
                        if line_route_distances[ext_type]
                        else None
                    ),
                    "p95": _percentile(line_route_distances[ext_type], 0.95),
                },
                "areaTypeVertexCoverage": {
                    f"0x{area_type:06x}": {
                        "coveredVertices": count,
                        "coveragePercent": _percent(count, line_vertices[ext_type]),
                    }
                    for area_type, count in line_area_hits[ext_type].most_common()
                },
            }
            for ext_type in sorted(line_lengths)
        },
        "points": {
            f"0x{ext_type:06x}": {
                "objectCount": point_counts[ext_type],
                "labels": dict(point_labels[ext_type]),
                "nearestControlDistanceMetres": {
                    name: {
                        "median": round(statistics.median(values), 6),
                        "p95": _percentile(values, 0.95),
                    }
                    for name, values in sorted(point_distances[ext_type].items())
                    if values
                },
            }
            for ext_type in sorted(point_counts)
        },
    }


def _coverage_rows(
    totals: Counter[str],
    hits: dict[str, Counter[int]],
) -> dict[str, Any]:
    return {
        label: {
            "sampleCount": totals[label],
            "areaTypeCoverage": {
                f"0x{ext_type:06x}": {
                    "coveredSamples": count,
                    "coveragePercent": _percent(count, totals[label]),
                }
                for ext_type, count in hits[label].most_common()
            },
        }
        for label in sorted(totals)
    }


def _mask_pixel_count(mask: Image.Image) -> int:
    return sum(mask.histogram()[1:])


def _vector_surface_coverage(
    vectors_by_sha: dict[str, dict[str, Any]],
    meshes_by_sha: dict[str, list[dict[str, Any]]],
    *,
    resolution_metres: float = SURFACE_MATCH_RESOLUTION_METRES,
) -> dict[str, Any]:
    """Measure DSKIMG vector pixels against unioned prodgeometry surface triangles.

    Each per-hole geometry package carries neighbouring scene meshes, while a
    DSKIMG covers a whole course or complex.  Forward triangle sampling therefore
    under-reports a valid private type.  This reverse pass clips each DSKIMG type
    to the union of captured PlayableBounds and asks which factual/VFX surface
    masks explain the private pixels.  Unioning before measurement also removes
    duplicated neighbour components across hole packages.
    """
    if resolution_metres <= 0:
        raise ValueError("surface-match resolution must be positive")

    totals: Counter[int] = Counter()
    private_totals: Counter[int] = Counter()
    hits: dict[int, Counter[str]] = defaultdict(Counter)
    observed_images: Counter[int] = Counter()
    line_totals: Counter[int] = Counter()
    line_private_totals: Counter[int] = Counter()
    line_hits: dict[int, Counter[str]] = defaultdict(Counter)
    line_observed_images: Counter[int] = Counter()
    image_rows: list[dict[str, Any]] = []

    for image_sha, payloads in sorted(meshes_by_sha.items()):
        vectors = vectors_by_sha[image_sha]
        bbox = vectors["bbox"]
        middle_latitude = (bbox.north + bbox.south) / 2.0
        metres_per_longitude_degree = 111_320.0 * math.cos(
            math.radians(middle_latitude)
        )
        width = max(
            1,
            math.ceil(
                (bbox.east - bbox.west)
                * metres_per_longitude_degree
                / resolution_metres
            )
            + 3,
        )
        height = max(
            1,
            math.ceil((bbox.north - bbox.south) * 111_320.0 / resolution_metres) + 3,
        )

        def world_pixel(
            latitude: float,
            longitude: float,
            *,
            west: float = bbox.west,
            north: float = bbox.north,
            metres_per_longitude: float = metres_per_longitude_degree,
        ) -> tuple[int, int]:
            return (
                round((longitude - west) * metres_per_longitude / resolution_metres)
                + 1,
                round((north - latitude) * 111_320.0 / resolution_metres) + 1,
            )

        surface_masks: dict[str, Image.Image] = {}
        scene_mask = Image.new("1", (width, height))
        scene_draw = ImageDraw.Draw(scene_mask)
        for decoded in payloads:
            hole = decoded["hole"]
            ref_lat = float(hole["RefLat"])
            ref_lon = float(hole["RefLon"])
            for mesh in decoded.get("meshes") or []:
                name = str(mesh.get("name"))
                if name != SCENE_COVERAGE_MESH and name not in SURFACE_MATCH_MESHES:
                    continue
                positions = mesh.get("positions") or []
                faces = mesh.get("faces") or []
                if not positions or not faces:
                    continue
                projected: list[tuple[int, int]] = []
                for point in positions:
                    latitude, longitude = local_to_world(
                        -float(point[0]),
                        float(point[2]),
                        ref_lat=ref_lat,
                        ref_lon=ref_lon,
                    )
                    projected.append(world_pixel(latitude, longitude))
                if name == SCENE_COVERAGE_MESH:
                    draw = scene_draw
                else:
                    mask = surface_masks.setdefault(
                        name,
                        Image.new("1", (width, height)),
                    )
                    draw = ImageDraw.Draw(mask)
                for face in faces:
                    try:
                        draw.polygon(
                            [projected[int(index)] for index in face],
                            fill=1,
                        )
                    except (IndexError, TypeError, ValueError):
                        continue

        scene_authority = SCENE_COVERAGE_MESH
        scene_pixels = _mask_pixel_count(scene_mask)
        if not scene_pixels:
            scene_authority = "decoded-surface-union"
            for surface_mask in surface_masks.values():
                scene_mask = ImageChops.logical_or(scene_mask, surface_mask)
            scene_pixels = _mask_pixel_count(scene_mask)
        if not scene_pixels:
            continue
        per_image_types: dict[str, Any] = {}
        for ext_type in sorted({polygon.ext_type for polygon in vectors["areas"]}):
            private_mask = Image.new("1", (width, height))
            draw = ImageDraw.Draw(private_mask)
            for polygon in vectors["areas"]:
                if polygon.ext_type == ext_type:
                    draw.polygon(
                        [
                            world_pixel(lat, lon)
                            for lat, lon in zip(polygon.lats, polygon.lons)
                        ],
                        fill=1,
                    )
            private_pixels = _mask_pixel_count(private_mask)
            observed_mask = ImageChops.logical_and(private_mask, scene_mask)
            observed_pixels = _mask_pixel_count(observed_mask)
            if not observed_pixels:
                continue
            private_totals[ext_type] += private_pixels
            totals[ext_type] += observed_pixels
            observed_images[ext_type] += 1
            surface_hits: dict[str, int] = {}
            for name, surface_mask in sorted(surface_masks.items()):
                covered = _mask_pixel_count(
                    ImageChops.logical_and(observed_mask, surface_mask)
                )
                if covered:
                    hits[ext_type][name] += covered
                    surface_hits[name] = covered
            per_image_types[f"0x{ext_type:06x}"] = {
                "privatePixelCount": private_pixels,
                "observedPixelCount": observed_pixels,
                "observedCoveragePercent": _percent(
                    observed_pixels,
                    private_pixels,
                ),
                "surfaceCoveragePercent": {
                    name: _percent(count, observed_pixels)
                    for name, count in sorted(
                        surface_hits.items(), key=lambda row: (-row[1], row[0])
                    )
                },
            }
        per_image_lines: dict[str, Any] = {}
        lines = vectors.get("lines") or []
        for ext_type in sorted({line.ext_type for line in lines}):
            private_mask = Image.new("1", (width, height))
            draw = ImageDraw.Draw(private_mask)
            for line in lines:
                if line.ext_type == ext_type:
                    draw.line(
                        [
                            world_pixel(lat, lon)
                            for lat, lon in zip(line.lats, line.lons)
                        ],
                        fill=1,
                        width=1,
                    )
            private_pixels = _mask_pixel_count(private_mask)
            observed_mask = ImageChops.logical_and(private_mask, scene_mask)
            observed_pixels = _mask_pixel_count(observed_mask)
            if not observed_pixels:
                continue
            line_private_totals[ext_type] += private_pixels
            line_totals[ext_type] += observed_pixels
            line_observed_images[ext_type] += 1
            surface_hits = {}
            for name, surface_mask in sorted(surface_masks.items()):
                covered = _mask_pixel_count(
                    ImageChops.logical_and(observed_mask, surface_mask)
                )
                if covered:
                    line_hits[ext_type][name] += covered
                    surface_hits[name] = covered
            per_image_lines[f"0x{ext_type:06x}"] = {
                "privatePixelCount": private_pixels,
                "observedPixelCount": observed_pixels,
                "observedCoveragePercent": _percent(
                    observed_pixels,
                    private_pixels,
                ),
                "surfaceCoveragePercent": {
                    name: _percent(count, observed_pixels)
                    for name, count in sorted(
                        surface_hits.items(), key=lambda row: (-row[1], row[0])
                    )
                },
            }
        image_rows.append(
            {
                "embeddedImageSha256": image_sha,
                "widthPixels": width,
                "heightPixels": height,
                "scenePixelCount": scene_pixels,
                "sceneAuthority": scene_authority,
                "areaTypes": per_image_types,
                "lineTypes": per_image_lines,
            }
        )

    return {
        "resolutionMetres": resolution_metres,
        "areaTypes": {
            f"0x{ext_type:06x}": {
                "observedImageCount": observed_images[ext_type],
                "privatePixelCount": private_totals[ext_type],
                "observedPixelCount": total,
                "observedCoveragePercent": _percent(
                    total,
                    private_totals[ext_type],
                ),
                "surfaceCoverage": {
                    name: {
                        "coveredPixels": count,
                        "coveragePercent": _percent(count, total),
                    }
                    for name, count in hits[ext_type].most_common()
                },
            }
            for ext_type, total in sorted(totals.items())
        },
        "lineTypes": {
            f"0x{ext_type:06x}": {
                "observedImageCount": line_observed_images[ext_type],
                "privatePixelCount": line_private_totals[ext_type],
                "observedPixelCount": total,
                "observedCoveragePercent": _percent(
                    total,
                    line_private_totals[ext_type],
                ),
                "surfaceCoverage": {
                    name: {
                        "coveredPixels": count,
                        "coveragePercent": _percent(count, total),
                    }
                    for name, count in line_hits[ext_type].most_common()
                },
            }
            for ext_type, total in sorted(line_totals.items())
        },
        "images": image_rows,
    }


def _prodgeometry_accounting(
    *,
    artifact_count: int,
    bound_hole_count: int,
    unbound_meshes: list[dict[str, Any]],
    expected_unavailable_layouts: set[int],
) -> dict[str, Any]:
    actual_unavailable_layouts = {int(row["layoutId"]) for row in unbound_meshes}
    expected_unavailable_hole_count = sum(
        int(row["layoutId"]) in expected_unavailable_layouts for row in unbound_meshes
    )
    unexpected_unbound_layouts = sorted(
        actual_unavailable_layouts - expected_unavailable_layouts
    )
    expected_but_bound_or_absent_layouts = sorted(
        expected_unavailable_layouts - actual_unavailable_layouts
    )
    accounted_hole_count = bound_hole_count + expected_unavailable_hole_count
    return {
        "expectedUnavailableLayouts": sorted(expected_unavailable_layouts),
        "actualUnavailableLayouts": sorted(actual_unavailable_layouts),
        "unexpectedUnboundLayouts": unexpected_unbound_layouts,
        "expectedButBoundOrAbsentLayouts": expected_but_bound_or_absent_layouts,
        "expectedUnavailableHoleCount": expected_unavailable_hole_count,
        "accountedHoleCount": accounted_hole_count,
        "allProdgeometryHolesAccountedFor": (
            actual_unavailable_layouts == expected_unavailable_layouts
            and accounted_hole_count == artifact_count
        ),
    }


def _semantic_classification(
    vector_counts: dict[str, Counter[int]],
    surface_coverage: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    coverage_keys = {
        "area": "areaTypes",
        "line": "lineTypes",
    }
    result: dict[str, Any] = {}
    complete = True
    for kind in ("area", "line", "point"):
        observed = set(vector_counts[kind])
        declared = set(SEMANTIC_DECISIONS[kind])
        complete = complete and observed == declared
        rows: dict[str, Any] = {}
        for ext_type, decision in sorted(SEMANTIC_DECISIONS[kind].items()):
            key = f"0x{ext_type:06x}"
            row: dict[str, Any] = {
                **decision,
                "objectCount": vector_counts[kind].get(ext_type, 0),
            }
            coverage_kind = coverage_keys.get(kind)
            if coverage_kind:
                coverage = surface_coverage.get(coverage_kind, {}).get(key)
                if coverage is not None:
                    row["surfaceCoverage"] = coverage
            rows[key] = row
        result[kind] = {
            "observedButUnclassified": [
                f"0x{ext_type:06x}" for ext_type in sorted(observed - declared)
            ],
            "classifiedButUnobserved": [
                f"0x{ext_type:06x}" for ext_type in sorted(declared - observed)
            ],
            "types": rows,
        }
    return result, complete


def _covered_by_area_rows(
    latitude: float,
    longitude: float,
    rows: list[tuple[Any, tuple[float, ...]]],
) -> bool:
    latitude_pad = AREA_EDGE_TOLERANCE_METRES / 111_320.0
    longitude_pad = latitude_pad / max(0.05, math.cos(math.radians(latitude)))
    return any(
        south - latitude_pad <= latitude <= north + latitude_pad
        and west - longitude_pad <= longitude <= east + longitude_pad
        and _near_ring(latitude, longitude, polygon)
        for polygon, (south, west, north, east) in rows
    )


def _domain_nesting_summary(
    vectors_by_sha: dict[str, dict[str, Any]],
    *,
    inner_type: int = 0x011409,
    outer_type: int = 0x01140E,
) -> dict[str, Any]:
    counts = Counter()
    for vectors in vectors_by_sha.values():
        inner = [row for row in vectors["areas"] if row.ext_type == inner_type]
        outer = [row for row in vectors["areas"] if row.ext_type == outer_type]
        counts["innerObjectCount"] += len(inner)
        counts["outerObjectCount"] += len(outer)
        inner_rows = _area_index(inner).get(inner_type, [])
        outer_rows = _area_index(outer).get(outer_type, [])
        for name, polygons, containers in (
            ("inner", inner, outer_rows),
            ("outer", outer, inner_rows),
        ):
            for polygon in polygons:
                for latitude, longitude in zip(polygon.lats[:-1], polygon.lons[:-1]):
                    counts[f"{name}VertexCount"] += 1
                    if _covered_by_area_rows(latitude, longitude, containers):
                        counts[f"{name}CoveredVertexCount"] += 1
    return {
        "innerType": f"0x{inner_type:06x}",
        "outerType": f"0x{outer_type:06x}",
        **counts,
        "innerVertexCoverageByOuterPercent": _percent(
            counts["innerCoveredVertexCount"],
            counts["innerVertexCount"],
        ),
        "outerVertexCoverageByInnerPercent": _percent(
            counts["outerCoveredVertexCount"],
            counts["outerVertexCount"],
        ),
    }


def _line_area_boundary_summary(
    vectors_by_sha: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pairs = (
        (0x010A00, 0x01140A, 25.0),
        (0x012E05, 0x011409, 50.0),
        (0x012E05, 0x01140E, 50.0),
    )
    distances: dict[tuple[int, int], list[float]] = defaultdict(list)
    totals: Counter[tuple[int, int]] = Counter()
    for vectors in vectors_by_sha.values():
        indexed = _area_index(vectors["areas"])
        for line_type, area_type, search_metres in pairs:
            rows = indexed.get(area_type, [])
            for line in vectors["lines"]:
                if line.ext_type != line_type:
                    continue
                for latitude, longitude in zip(line.lats, line.lons):
                    key = line_type, area_type
                    totals[key] += 1
                    latitude_pad = search_metres / 111_320.0
                    longitude_pad = latitude_pad / max(
                        0.05,
                        math.cos(math.radians(latitude)),
                    )
                    candidates = [
                        polygon
                        for polygon, (south, west, north, east) in rows
                        if south - latitude_pad <= latitude <= north + latitude_pad
                        and west - longitude_pad <= longitude <= east + longitude_pad
                    ]
                    nearest = min(
                        (
                            _point_segment_metres(
                                latitude,
                                longitude,
                                polygon.lats[index],
                                polygon.lons[index],
                                polygon.lats[index + 1],
                                polygon.lons[index + 1],
                            )
                            for polygon in candidates
                            for index in range(len(polygon.lats) - 1)
                        ),
                        default=None,
                    )
                    if nearest is not None:
                        distances[key].append(nearest)
    return {
        f"0x{line_type:06x}->0x{area_type:06x}": {
            "lineVertexCount": totals[(line_type, area_type)],
            "matchedVertexCount": len(distances[(line_type, area_type)]),
            "medianBoundaryResidualMetres": (
                round(statistics.median(distances[(line_type, area_type)]), 6)
                if distances[(line_type, area_type)]
                else None
            ),
            "p95BoundaryResidualMetres": _percentile(
                distances[(line_type, area_type)],
                0.95,
            ),
            "withinTwoMetresPercent": _percent(
                sum(value <= 2.0 for value in distances[(line_type, area_type)]),
                totals[(line_type, area_type)],
            ),
        }
        for line_type, area_type, _search_metres in pairs
    }


def audit(
    *,
    dskimg_root: Path,
    course_data_root: Path,
    mesh_root: Path,
    expected_unavailable_layouts: set[int] | None = None,
) -> dict[str, Any]:
    expected_unavailable_layouts = expected_unavailable_layouts or set()
    dskimg_paths = sorted(Path(dskimg_root).glob("*_coursedata.pb"))
    course_data_paths = sorted(Path(course_data_root).glob("*_medium-plus.json"))
    mesh_paths = sorted(Path(mesh_root).glob("*_meshes.json"))

    vectors_by_layout: dict[int, dict[str, Any]] = {}
    layout_to_image_sha: dict[int, str] = {}
    vectors_by_sha: dict[str, dict[str, Any]] = {}
    vector_counts = {kind: Counter() for kind in ("area", "line", "point")}
    artifact_rows: list[dict[str, Any]] = []
    for path in dskimg_paths:
        layout = int(path.name.split("_", 1)[0])
        vectors = _load_vectors(path)
        vectors_by_layout[layout] = vectors
        image_sha = vectors["embeddedImageSha256"]
        layout_to_image_sha[layout] = image_sha
        vectors_by_sha.setdefault(image_sha, vectors)
        artifact_rows.append(
            {
                "layoutId": layout,
                "artifact": path.name,
                "sourceSha256": vectors["sourceSha256"],
                "embeddedImageSha256": vectors["embeddedImageSha256"],
            }
        )
    for vectors in vectors_by_sha.values():
        for kind, counts in vector_counts.items():
            counts.update(item.ext_type for item in vectors[f"{kind}s"])

    parsed_course_data: list[dict[str, Any]] = [
        parse_course_data_json(path.read_bytes(), includes_hazard_lines=True)
        for path in course_data_paths
    ]
    course_data_by_sha: dict[str, list[dict[str, Any]]] = defaultdict(list)
    vectors_for_course_data_layout: dict[int, dict[str, Any]] = {}
    course_data_bindings: list[dict[str, Any]] = []
    for parsed in parsed_course_data:
        layout = int(parsed["globalLayoutId"])
        image_sha = layout_to_image_sha.get(layout)
        authority = "direct-layout"
        selected_alignment: tuple[float, float | None, float | None] | None = None
        if image_sha is None:
            candidates = sorted(
                (
                    (*_route_alignment(parsed, vectors), sha)
                    for sha, vectors in vectors_by_sha.items()
                ),
                key=lambda row: (
                    math.inf if row[1] is None else row[1],
                    math.inf if row[2] is None else row[2],
                    row[3],
                ),
            )
            plausible = [
                row
                for row in candidates
                if row[0] >= 0.8 and row[1] is not None and row[1] <= 2.0
            ]
            if plausible and (
                len(plausible) == 1
                or plausible[1][1] is None
                or plausible[1][1] - plausible[0][1] > 2.0
            ):
                selected_alignment = plausible[0][:3]
                image_sha = plausible[0][3]
                authority = "route-line-alignment"
        if image_sha is None:
            continue
        if selected_alignment is None:
            selected_alignment = _route_alignment(parsed, vectors_by_sha[image_sha])
        course_data_by_sha[image_sha].append(parsed)
        vectors_for_course_data_layout[layout] = vectors_by_sha[image_sha]
        course_data_bindings.append(
            {
                "layoutId": layout,
                "embeddedImageSha256": image_sha,
                "authority": authority,
                "routePointBboxCoveragePercent": round(
                    selected_alignment[0] * 100.0, 6
                ),
                "medianRouteLineResidualMetres": selected_alignment[1],
                "p95RouteLineResidualMetres": selected_alignment[2],
            }
        )

    surface_totals: Counter[str] = Counter()
    surface_hits: dict[str, Counter[int]] = defaultdict(Counter)
    mesh_holes = 0
    mesh_layout_counts: Counter[int] = Counter()
    unbound_meshes: list[dict[str, Any]] = []
    mesh_bindings: dict[int, dict[str, Any]] = {}
    meshes_by_sha: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in mesh_paths:
        decoded = json.loads(path.read_bytes())
        layout = int(decoded["hole"]["GlobalId"])
        binding = mesh_bindings.get(layout)
        if binding is None:
            image_sha = layout_to_image_sha.get(layout)
            authority = "direct-layout"
            alignment: tuple[float, float | None, float | None] | None = None
            if image_sha is None and layout in vectors_for_course_data_layout:
                image_sha = vectors_for_course_data_layout[layout][
                    "embeddedImageSha256"
                ]
                authority = "course-data-route-binding"
            if image_sha is None:
                candidates = sorted(
                    (
                        (*_hole_route_alignment(decoded["hole"], vectors), sha)
                        for sha, vectors in vectors_by_sha.items()
                    ),
                    key=lambda row: (
                        math.inf if row[1] is None else row[1],
                        math.inf if row[2] is None else row[2],
                        row[3],
                    ),
                )
                plausible = [
                    row
                    for row in candidates
                    if row[0] >= 0.8 and row[1] is not None and row[1] <= 2.0
                ]
                if plausible and (
                    len(plausible) == 1
                    or plausible[1][1] is None
                    or plausible[1][1] - plausible[0][1] > 2.0
                ):
                    alignment = plausible[0][:3]
                    image_sha = plausible[0][3]
                    authority = "hole-route-line-alignment"
            if image_sha is not None:
                if alignment is None:
                    alignment = _hole_route_alignment(
                        decoded["hole"], vectors_by_sha[image_sha]
                    )
                binding = {
                    "layoutId": layout,
                    "embeddedImageSha256": image_sha,
                    "authority": authority,
                    "routePointBboxCoveragePercent": round(alignment[0] * 100.0, 6),
                    "medianRouteLineResidualMetres": alignment[1],
                    "p95RouteLineResidualMetres": alignment[2],
                }
                mesh_bindings[layout] = binding
        vectors = (
            vectors_by_sha.get(binding["embeddedImageSha256"])
            if binding is not None
            else None
        )
        if vectors is None:
            candidate_alignments = sorted(
                (
                    (*_hole_route_alignment(decoded["hole"], item), sha)
                    for sha, item in vectors_by_sha.items()
                ),
                key=lambda row: (
                    math.inf if row[1] is None else row[1],
                    math.inf if row[2] is None else row[2],
                    row[3],
                ),
            )
            unbound_meshes.append(
                {
                    "artifact": path.name,
                    "layoutId": layout,
                    "refLat": decoded["hole"].get("RefLat"),
                    "refLon": decoded["hole"].get("RefLon"),
                    "candidateAlignments": [
                        {
                            "embeddedImageSha256": row[3],
                            "routePointBboxCoveragePercent": round(row[0] * 100.0, 6),
                            "medianRouteLineResidualMetres": row[1],
                            "p95RouteLineResidualMetres": row[2],
                        }
                        for row in candidate_alignments[:3]
                    ],
                }
            )
            continue
        mesh_holes += 1
        mesh_layout_counts[layout] += 1
        meshes_by_sha[binding["embeddedImageSha256"]].append(decoded)
        areas = _area_index(vectors["areas"])
        for surface, latitude, longitude in _triangle_samples(decoded):
            if not _inside_bbox(latitude, longitude, vectors["bbox"]):
                continue
            surface_totals[surface] += 1
            surface_hits[surface].update(_memberships(latitude, longitude, areas))

    control_totals: Counter[str] = Counter()
    control_hits: dict[str, Counter[int]] = defaultdict(Counter)
    bound_layouts: set[int] = set()
    for image_sha, rows in course_data_by_sha.items():
        vectors = vectors_by_sha[image_sha]
        areas = _area_index(vectors["areas"])
        for parsed in rows:
            bound_layouts.add(int(parsed["globalLayoutId"]))
            for label, latitude, longitude in _route_controls(parsed):
                if not _inside_bbox(latitude, longitude, vectors["bbox"]):
                    continue
                control_totals[label] += 1
                control_hits[label].update(_memberships(latitude, longitude, areas))

    prodgeometry_accounting = _prodgeometry_accounting(
        artifact_count=len(mesh_paths),
        bound_hole_count=mesh_holes,
        unbound_meshes=unbound_meshes,
        expected_unavailable_layouts=expected_unavailable_layouts,
    )
    vector_surface_coverage = _vector_surface_coverage(
        vectors_by_sha,
        meshes_by_sha,
    )
    semantic_classification, classifications_complete = _semantic_classification(
        vector_counts,
        vector_surface_coverage,
    )
    gates = {
        "dskimgArtifactsPresent": bool(dskimg_paths),
        "strictVectorDecodeComplete": bool(dskimg_paths)
        and all(vector_counts[kind] for kind in vector_counts),
        "courseDataControlsBound": bool(bound_layouts)
        and sum(control_totals.values()) > 0,
        "prodgeometrySurfacesBound": mesh_holes > 0
        and sum(surface_totals.values()) > 0,
        "allProdgeometryHolesAccountedFor": prodgeometry_accounting[
            "allProdgeometryHolesAccountedFor"
        ],
        "allDecodedVectorTypesTerminallyClassified": classifications_complete,
    }
    return {
        "schema": SCHEMA,
        "inputs": {
            "dskimgArtifactCount": len(dskimg_paths),
            "uniqueEmbeddedImageCount": len(vectors_by_sha),
            "courseDataLayoutCount": len(bound_layouts),
            "prodgeometryArtifactCount": len(mesh_paths),
            "prodgeometryHoleCount": mesh_holes,
            "prodgeometryHoleCountByLayout": {
                str(layout): count
                for layout, count in sorted(mesh_layout_counts.items())
            },
            "prodgeometryAccounting": {
                key: value
                for key, value in prodgeometry_accounting.items()
                if key != "allProdgeometryHolesAccountedFor"
            },
            "unboundProdgeometryHoles": unbound_meshes,
            "courseDataBindings": sorted(
                course_data_bindings, key=lambda row: row["layoutId"]
            ),
            "prodgeometryBindings": sorted(
                mesh_bindings.values(), key=lambda row: row["layoutId"]
            ),
            "artifacts": artifact_rows,
        },
        "decodedObjectCounts": {
            kind: {
                f"0x{ext_type:06x}": count
                for ext_type, count in vector_counts[kind].most_common()
            }
            for kind in vector_counts
        },
        "courseDataControlCoverage": _coverage_rows(control_totals, control_hits),
        "prodgeometrySurfaceCoverage": _coverage_rows(surface_totals, surface_hits),
        "dskimgVectorSurfaceCoverage": vector_surface_coverage,
        "structuralGeometryBindings": {
            "holeDomainNesting": _domain_nesting_summary(vectors_by_sha),
            "lineAreaBoundaries": _line_area_boundary_summary(vectors_by_sha),
        },
        "semanticClassification": semantic_classification,
        "vectorGeometry": _vector_geometry_summary(vectors_by_sha, course_data_by_sha),
        "gates": {**gates, "passed": all(gates.values())},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dskimg-root", type=Path, required=True)
    parser.add_argument("--course-data-root", type=Path, required=True)
    parser.add_argument("--mesh-root", type=Path, required=True)
    parser.add_argument(
        "--expected-unavailable-layout",
        action="append",
        default=[],
        type=int,
        help=(
            "Layout whose release-bound DSKIMG request is proven unavailable. "
            "Repeat for multiple layouts; the set must exactly match unbound layouts."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(
        dskimg_root=args.dskimg_root,
        course_data_root=args.course_data_root,
        mesh_root=args.mesh_root,
        expected_unavailable_layouts=set(args.expected_unavailable_layout),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["gates"], sort_keys=True))
    return 0 if report["gates"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
