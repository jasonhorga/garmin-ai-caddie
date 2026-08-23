#!/usr/bin/env python3
"""Bind GreenRadii to release-authorized VfxGreen A/B meshes and audit decoding."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ai_caddie.courses import course_prep, courseview_core
from ai_caddie.courses.courseview_core import green_radii_local_offsets
from ai_caddie.geometry.inspect_courseview_release import inspect_release
from ai_caddie.geometry.measure_prodgeometry_distances import mesh_components, target_point
from ai_caddie.geometry.shot_projection import world_to_local


SEMICIRCLE_DEGREES = 180.0 / (1 << 31)


def _mesh_points(mesh: dict[str, Any]) -> list[tuple[float, float]]:
    return [(-float(point[0]), float(point[2])) for point in mesh["positions"]]


def _mesh_center(mesh: dict[str, Any]) -> tuple[float, float]:
    points = _mesh_points(mesh)
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def _segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    squared = dx * dx + dy * dy
    t = (
        max(
            0.0,
            min(
                1.0,
                ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
                / squared,
            ),
        )
        if squared
        else 0.0
    )
    return math.hypot(
        point[0] - start[0] - t * dx,
        point[1] - start[1] - t * dy,
    )


def _triangle_distance(
    point: tuple[float, float],
    first: tuple[float, float],
    second: tuple[float, float],
    third: tuple[float, float],
) -> float:
    def cross(a: tuple[float, float], b: tuple[float, float]) -> float:
        return (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (
            point[0] - a[0]
        )

    signs = cross(first, second), cross(second, third), cross(third, first)
    if all(value >= -1e-8 for value in signs) or all(value <= 1e-8 for value in signs):
        return 0.0
    return min(
        _segment_distance(point, first, second),
        _segment_distance(point, second, third),
        _segment_distance(point, third, first),
    )


def _point_mesh_distance(
    point: tuple[float, float], mesh: dict[str, Any]
) -> float:
    points = _mesh_points(mesh)
    return min(
        _triangle_distance(point, points[face[0]], points[face[1]], points[face[2]])
        for face in mesh["faces"]
    )


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * quantile)]


def _raw_course_route(
    course_data: dict[int, dict[str, Any]],
    layout: int,
    hole_number: int,
) -> list[tuple[float, float]] | None:
    payload = course_data.get(int(layout))
    hole = next(
        (
            row
            for row in (payload or {}).get("Holes", [])
            if int(row["HoleNumber"]) == int(hole_number)
        ),
        None,
    )
    line = next(
        (
            row
            for row in (hole or {}).get("Line", [])
            if int(row["LineCode"]) == 3240
        ),
        None,
    )
    points = sorted(
        (line or {}).get("Points", []),
        key=lambda point: int(point["PointNumber"]),
    )
    route = [
        (
            int(point["Latitude"]) * SEMICIRCLE_DEGREES,
            int(point["Longitude"]) * SEMICIRCLE_DEGREES,
        )
        for point in points
    ]
    return route if len(route) >= 2 else None


def _audit_dual_green_product_binding(
    *,
    course_data: dict[int, dict[str, Any]],
    green_surface_root: Path,
) -> dict[str, Any]:
    """Exercise production route/target/component consumers on the A/B course."""
    paths = sorted(Path(green_surface_root).glob("*_meshes.json"))
    rows: list[dict[str, Any]] = []

    def route_loader(layout: int, hole_number: int, **_kwargs: Any):
        return _raw_course_route(course_data, layout, hole_number)

    with patch.object(
        courseview_core,
        "load_cached_hole_route",
        side_effect=route_loader,
    ):
        for path in paths:
            decoded = json.loads(path.read_bytes())
            hole = decoded["hole"]
            layout = int(hole["GlobalId"])
            hole_number = int(hole["HoleNumber"])
            raw_route = _raw_course_route(course_data, layout, hole_number)
            if not raw_route:
                continue
            endpoint = world_to_local(
                raw_route[-1][0],
                raw_route[-1][1],
                ref_lat=float(hole["RefLat"]),
                ref_lon=float(hole["RefLon"]),
            )
            dogleg = next(
                (
                    row.get("Line") or []
                    for row in hole.get("Doglegs") or []
                    if row.get("Line")
                ),
                [],
            )
            dogleg_target = (
                (float(dogleg[-1]["X"]), float(dogleg[-1]["Y"]))
                if dogleg
                else None
            )
            old_endpoint_delta = (
                math.dist(dogleg_target, endpoint)
                if dogleg_target is not None
                else math.inf
            )
            route, _route_length = course_prep.derive_route(decoded)
            by_name = {mesh["name"]: mesh for mesh in decoded["meshes"]}
            components = mesh_components(by_name["Green.drc"])
            selected_component = course_prep.selected_green_component(by_name, route)
            target_name, selected_target = target_point(hole, components)
            rows.append(
                {
                    "layoutId": layout,
                    "holeNumber": hole_number,
                    "routeAuthority": (
                        "courseData"
                        if old_endpoint_delta
                        > courseview_core.COURSE_DATA_ROUTE_ENDPOINT_OVERRIDE_METRES
                        else "hole.json"
                    ),
                    "oldDoglegToSelectedEndpointMetres": round(old_endpoint_delta, 6),
                    "routeEndpointResidualMetres": round(math.dist(route[-1], endpoint), 6),
                    "targetEndpointResidualMetres": round(
                        math.dist(selected_target, endpoint), 6
                    ),
                    "targetName": target_name,
                    "greenComponentCount": len(components),
                    "selectedGreenCenterResidualMetres": round(
                        math.dist(selected_component["centroid"], endpoint)
                        if selected_component
                        else math.inf,
                        6,
                    ),
                    "selectedGreenVertexCount": (
                        len(selected_component["vertex_indices"])
                        if selected_component
                        else 0
                    ),
                }
            )

    authority_counts = Counter(row["routeAuthority"] for row in rows)
    gates = {
        "allDualGreenHolesExercised": len(paths) == 18 and len(rows) == 18,
        "observedSelectionSplitPreserved": authority_counts
        == {"courseData": 10, "hole.json": 8},
        "routeAndTargetUseSelectedEndpoint": bool(rows)
        and max(row["routeEndpointResidualMetres"] for row in rows) < 2.0
        and max(row["targetEndpointResidualMetres"] for row in rows) < 2.0,
        "greenConsumersUseSelectedComponent": bool(rows)
        and all(row["selectedGreenVertexCount"] > 0 for row in rows)
        and max(row["selectedGreenCenterResidualMetres"] for row in rows) < 2.0,
    }
    return {
        "holeCount": len(rows),
        "routeAuthorityCounts": dict(sorted(authority_counts.items())),
        "maximumRouteEndpointResidualMetres": round(
            max(row["routeEndpointResidualMetres"] for row in rows), 6
        ) if rows else None,
        "maximumTargetEndpointResidualMetres": round(
            max(row["targetEndpointResidualMetres"] for row in rows), 6
        ) if rows else None,
        "maximumSelectedGreenCenterResidualMetres": round(
            max(row["selectedGreenCenterResidualMetres"] for row in rows), 6
        ) if rows else None,
        "holes": sorted(rows, key=lambda row: (row["layoutId"], row["holeNumber"])),
        "gates": {**gates, "passed": all(gates.values())},
    }


def audit_green_radii(
    *,
    course_data_root: Path,
    release_root: Path,
    mesh_root: Path,
    prodgeometry_root: Path,
    green_surface_root: Path,
) -> dict[str, Any]:
    course_data: dict[int, dict[str, Any]] = {}
    course_digest = hashlib.sha256()
    for path in sorted(Path(course_data_root).glob("*_medium-plus.json")):
        raw = path.read_bytes()
        course_digest.update(path.name.encode() + b"\0" + hashlib.sha256(raw).digest())
        payload = json.loads(raw)
        course_data[int(payload["GlobalLayoutId"])] = payload

    releases: dict[int, dict[str, Any]] = {}
    release_digest = hashlib.sha256()
    for path in sorted(Path(release_root).glob("*_releases.pb")):
        raw = path.read_bytes()
        release_digest.update(path.name.encode() + b"\0" + hashlib.sha256(raw).digest())
        releases[int(path.name.split("_", 1)[0])] = inspect_release(raw)

    mesh_paths = sorted(Path(mesh_root).glob("*_meshes.json"))
    mesh_digest = hashlib.sha256()
    authority_errors: list[dict[str, Any]] = []
    unmatched: list[dict[str, int]] = []
    selected_counts: Counter[str] = Counter()
    dual_selected_counts: Counter[str] = Counter()
    dual_selected_distances: list[float] = []
    dual_alternate_distances: list[float] = []
    point_distances: list[float] = []
    hole_results: list[dict[str, Any]] = []
    matched_courses: set[int] = set()

    for path in mesh_paths:
        raw = path.read_bytes()
        mesh_digest.update(path.name.encode() + b"\0" + hashlib.sha256(raw).digest())
        decoded = json.loads(raw)
        hole = decoded["hole"]
        layout = int(hole["GlobalId"])
        hole_number = int(hole["HoleNumber"])
        payload = course_data.get(layout)
        course_hole = next(
            (
                row
                for row in (payload or {}).get("Holes", [])
                if int(row["HoleNumber"]) == hole_number
            ),
            None,
        )
        release = releases.get(layout)
        if course_hole is None or release is None:
            unmatched.append({"layoutId": layout, "holeNumber": hole_number})
            continue

        release_hole = next(
            (row for row in release["holes"] if int(row.get("hole", -1)) == hole_number),
            None,
        )
        asset_dirs = list(
            (Path(prodgeometry_root) / str(layout)).glob(f"Hole{hole_number:02d}_*")
        )
        url_stem = (
            Path(urllib.parse.urlparse((release_hole or {}).get("geometry_url", "")).path).stem
            if release_hole
            else ""
        )
        expected_prefix = (
            f"hole{hole_number:02d}_{int(hole['CourseGenVersion'])}0{int(hole['Version'])}"
        )
        checks = {
            "courseDataBuild": int(payload["BuildId"]) == int(release.get("release_version", -1)),
            "releaseLayout": int(release.get("course_id", -1)) == layout,
            "courseGenVersion": int(release.get("course_gen_version", -1))
            == int(hole["CourseGenVersion"]),
            "holeIdentity": int(hole["GlobalId"]) == layout
            and int(hole["HoleNumber"]) == hole_number,
            "oneAssetDirectory": len(asset_dirs) == 1,
            "releaseAssetStem": len(asset_dirs) == 1
            and asset_dirs[0].name.lower() == url_stem.lower(),
            "holeVersionInAssetStem": url_stem.startswith(expected_prefix),
        }
        if not all(checks.values()):
            authority_errors.append(
                {
                    "layoutId": layout,
                    "holeNumber": hole_number,
                    "checks": checks,
                    "releaseAssetStem": url_stem,
                }
            )
            continue

        route = next(line for line in course_hole["Line"] if int(line["LineCode"]) == 3240)
        endpoint = max(route["Points"], key=lambda point: int(point["PointNumber"]))
        endpoint_latitude = int(endpoint["Latitude"]) * SEMICIRCLE_DEGREES
        endpoint_longitude = int(endpoint["Longitude"]) * SEMICIRCLE_DEGREES
        center = world_to_local(
            endpoint_latitude,
            endpoint_longitude,
            ref_lat=float(hole["RefLat"]),
            ref_lon=float(hole["RefLon"]),
        )
        meshes = decoded["meshes"]
        names = {mesh["name"] for mesh in meshes}
        if not names or not names <= {"VfxGreenA.drc", "VfxGreenB.drc"}:
            authority_errors.append(
                {"layoutId": layout, "holeNumber": hole_number, "meshNames": sorted(names)}
            )
            continue
        distances = [
            (math.dist(_mesh_center(mesh), center), mesh) for mesh in meshes
        ]
        selected_distance, selected = min(distances, key=lambda row: row[0])
        selected_counts[selected["name"]] += 1
        if len(distances) == 2:
            alternate_distance = max(distances, key=lambda row: row[0])[0]
            dual_selected_counts[selected["name"]] += 1
            dual_selected_distances.append(selected_distance)
            dual_alternate_distances.append(alternate_distance)

        offsets = green_radii_local_offsets(
            [int(value) for value in course_hole["GreenRadii"]], endpoint_latitude
        )
        distances_to_mesh = [
            _point_mesh_distance(
                (center[0] + east, center[1] + north),
                selected,
            )
            for east, north in offsets
        ]
        point_distances.extend(distances_to_mesh)
        matched_courses.add(layout)
        hole_results.append(
            {
                "layoutId": layout,
                "holeNumber": hole_number,
                "selectedMesh": selected["name"],
                "selectedCenterDistanceMetres": round(selected_distance, 6),
                "pointRmseMetres": round(
                    math.sqrt(
                        sum(value * value for value in distances_to_mesh)
                        / len(distances_to_mesh)
                    ),
                    6,
                ),
                "pointMaximumMetres": round(max(distances_to_mesh), 6),
            }
        )

    matched_holes = len(hole_results)
    point_rmse = math.sqrt(
        sum(value * value for value in point_distances) / len(point_distances)
    )
    gates = {
        "allDecodedArtifactsAccountedFor": len(mesh_paths) == 184
        and matched_holes == 166
        and len(unmatched) == 18,
        "courseReleaseAssetAuthorityBound": not authority_errors,
        "dualGreenSelectionResolved": len(dual_selected_distances) == 18
        and dual_selected_counts == {"VfxGreenA.drc": 8, "VfxGreenB.drc": 10}
        and max(dual_selected_distances) < 2.0
        and min(dual_alternate_distances) > 20.0,
        "angularVectorDecodeMatchesVfx": len(point_distances) == 4_980
        and _percentile(point_distances, 0.95) < 0.5
        and max(point_distances) < 1.5,
    }
    product_binding = _audit_dual_green_product_binding(
        course_data=course_data,
        green_surface_root=green_surface_root,
    )
    gates["dualGreenProductBindingPassed"] = bool(
        product_binding["gates"]["passed"]
    )
    return {
        "schema": "garmin-green-radii-vfx-audit-v1",
        "corpus": {
            "decodedMeshArtifactCount": len(mesh_paths),
            "authorityMatchedHoleCount": matched_holes,
            "authorityMatchedCourseCount": len(matched_courses),
            "unmatchedHoleCount": len(unmatched),
            "unmatchedHoles": sorted(unmatched, key=lambda row: (row["layoutId"], row["holeNumber"])),
            "courseDataSetSha256": course_digest.hexdigest(),
            "releaseSetSha256": release_digest.hexdigest(),
            "decodedMeshSetSha256": mesh_digest.hexdigest(),
        },
        "authorityBinding": {
            "errorCount": len(authority_errors),
            "errors": authority_errors[:20],
            "chain": (
                "courseData layout+BuildId -> release layout+version+CourseGenVersion -> "
                "hole geometry URL stem -> extracted asset directory -> hole GlobalId+HoleNumber+Version"
            ),
        },
        "greenSelection": {
            "selectedMeshCounts": dict(sorted(selected_counts.items())),
            "dualGreenHoleCount": len(dual_selected_distances),
            "dualGreenSelectedMeshCounts": dict(sorted(dual_selected_counts.items())),
            "dualGreenMaximumSelectedCenterDistanceMetres": round(
                max(dual_selected_distances), 6
            ),
            "dualGreenMinimumAlternateCenterDistanceMetres": round(
                min(dual_alternate_distances), 6
            ),
            "selectionRule": "choose VfxGreen A/B whose centre is nearest the courseData route endpoint",
        },
        "coordinateEncoding": {
            "sampleOrder": "north, clockwise, 12 degrees per sample in uncorrected angular coordinates",
            "localOffsetFormula": (
                "east = rawRadius * sin(theta) * cos(endpointLatitude); "
                "north = rawRadius * cos(theta)"
            ),
            "pointCount": len(point_distances),
            "insideMeshTriangleCount": sum(value == 0 for value in point_distances),
            "medianDistanceToSelectedVfxMetres": round(
                statistics.median(point_distances), 6
            ),
            "p95DistanceToSelectedVfxMetres": round(
                _percentile(point_distances, 0.95), 6
            ),
            "p99DistanceToSelectedVfxMetres": round(
                _percentile(point_distances, 0.99), 6
            ),
            "maximumDistanceToSelectedVfxMetres": round(max(point_distances), 6),
            "rmseDistanceToSelectedVfxMetres": round(point_rmse, 6),
            "worstHolesByRmse": sorted(
                hole_results,
                key=lambda row: row["pointRmseMetres"],
                reverse=True,
            )[:10],
            "productDecision": (
                "decode the latitude-corrected display outline; do not use raw radii "
                "or the outline for numeric front/middle/back distances"
            ),
        },
        "productBinding": product_binding,
        "gates": {**gates, "passed": all(gates.values())},
    }


def _report_bytes(report: dict[str, Any]) -> bytes:
    return (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-data-root", required=True, type=Path)
    parser.add_argument("--release-root", required=True, type=Path)
    parser.add_argument("--mesh-root", required=True, type=Path)
    parser.add_argument("--prodgeometry-root", required=True, type=Path)
    parser.add_argument("--green-surface-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit_green_radii(
        course_data_root=args.course_data_root,
        release_root=args.release_root,
        mesh_root=args.mesh_root,
        prodgeometry_root=args.prodgeometry_root,
        green_surface_root=args.green_surface_root,
    )
    payload = _report_bytes(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"{hashlib.sha256(payload).hexdigest()}  {args.output}")
    return 0 if report["gates"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
