#!/usr/bin/env python3
"""Cross-check decoded CourseView DEM samples against prodgeometry ground meshes.

The two sources use different frames. DSKIMG stores absolute course elevation in
feet/metres on a WGS84 grid. A prodgeometry vertex is ``[mesh_x, local_y,
mesh_z]``; its ground coordinate is ``(-mesh_x, mesh_z)`` around the hole's
``RefLat/RefLon`` and its absolute elevation is ``local_y + ElevationMinimum``.

This validator intentionally reports both raw vertical-datum bias and residuals
after removing that per-course median. It does not tune or rewrite either source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any

from tools.courseview.parse_courseview import (
    _unwrap_pb_img,
    decode_dem_level,
    extract_gmp,
    parse_dem_header,
    parse_gmp_header,
)

EARTH_RADIUS_WGS84_M = 6_378_137.0
GROUND_MESHES = {
    "Bunker.drc",
    "Fairway.drc",
    "Fringe.drc",
    "Green.drc",
    "Rough.drc",
    "Teebox.drc",
}


def _round(value: float) -> float:
    return round(value, 3)


def _percentile(values: list[float], proportion: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * proportion)]


def _stats(residuals: list[float]) -> dict[str, float | int]:
    if not residuals:
        raise ValueError("cannot summarize an empty elevation comparison")
    bias = statistics.median(residuals)
    absolute = [abs(value) for value in residuals]
    centered = [value - bias for value in residuals]
    centered_absolute = [abs(value) for value in centered]
    return {
        "sampleCount": len(residuals),
        "medianBiasM": _round(bias),
        "medianAbsoluteErrorM": _round(statistics.median(absolute)),
        "p95AbsoluteErrorM": _round(_percentile(absolute, 0.95)),
        "rmseM": _round(math.sqrt(sum(value * value for value in residuals) / len(residuals))),
        "centeredMedianAbsoluteErrorM": _round(statistics.median(centered_absolute)),
        "centeredP95AbsoluteErrorM": _round(_percentile(centered_absolute, 0.95)),
        "centeredRmseM": _round(
            math.sqrt(sum(value * value for value in centered) / len(centered))
        ),
    }


def _world_from_mesh(
    mesh_x: float,
    mesh_z: float,
    *,
    ref_latitude: float,
    ref_longitude: float,
) -> tuple[float, float]:
    latitude = ref_latitude + math.degrees(mesh_z / EARTH_RADIUS_WGS84_M)
    longitude = ref_longitude + math.degrees(
        -mesh_x
        / (EARTH_RADIUS_WGS84_M * math.cos(math.radians(ref_latitude)))
    )
    return latitude, longitude


def _parse_course_argument(value: str) -> tuple[int, Path]:
    course_id_text, separator, path_text = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("course data must use GLOBAL_ID=PATH")
    try:
        course_id = int(course_id_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("course global id must be an integer") from exc
    path = Path(path_text)
    if course_id <= 0 or not path.is_file():
        raise argparse.ArgumentTypeError("course data id/path is invalid")
    return course_id, path


def _mesh_files(roots: list[Path], course_ids: set[int]) -> list[Path]:
    paths: set[Path] = set()
    for root in roots:
        if root.is_file():
            paths.add(root)
            continue
        for course_id in course_ids:
            paths.update(root.rglob(f"gid{course_id}_h*_meshes.json"))
    return sorted(paths)


def _load_course(path: Path) -> tuple[Any, Any, str]:
    source = path.read_bytes()
    image = source if source[0x10:0x16] == b"DSKIMG" else _unwrap_pb_img(source)
    gmp = extract_gmp(image)
    dem = parse_dem_header(gmp, parse_gmp_header(gmp).dem)
    return dem, decode_dem_level(gmp, dem), hashlib.sha256(source).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--course-data",
        action="append",
        required=True,
        type=_parse_course_argument,
        metavar="GLOBAL_ID=PATH",
    )
    parser.add_argument(
        "--mesh-root",
        action="append",
        required=True,
        type=Path,
        help="Mesh JSON file or a directory searched recursively for matching gid*_meshes.json files.",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    course_paths = dict(args.course_data)
    if len(course_paths) != len(args.course_data):
        raise ValueError("course-data repeats a global id")
    meshes_by_course: dict[int, list[Path]] = {course_id: [] for course_id in course_paths}
    for path in _mesh_files(args.mesh_root, set(course_paths)):
        payload = json.loads(path.read_text())
        course_id = int(payload["hole"]["GlobalId"])
        if course_id in meshes_by_course:
            meshes_by_course[course_id].append(path)

    output: dict[str, Any] = {
        "schema": "garmin-dem-prodgeometry-crosscheck-v1",
        "groundMeshNames": sorted(GROUND_MESHES),
        "courses": [],
    }
    for course_id, course_path in sorted(course_paths.items()):
        dem, decoded, source_sha256 = _load_course(course_path)
        unit_to_metres = 0.3048 if dem.elevation_unit == "feet" else 1.0
        course_residuals: list[float] = []
        holes: list[dict[str, Any]] = []
        for mesh_path in sorted(meshes_by_course[course_id]):
            payload = json.loads(mesh_path.read_text())
            hole = payload["hole"]
            ref_latitude = float(hole["RefLat"])
            ref_longitude = float(hole["RefLon"])
            elevation_minimum = float(hole["ElevationMinimum"])
            residuals: list[float] = []
            for mesh in payload.get("meshes") or []:
                if mesh.get("name") not in GROUND_MESHES:
                    continue
                for position in mesh.get("positions") or []:
                    if not isinstance(position, list) or len(position) < 3:
                        continue
                    mesh_x, local_elevation, mesh_z = map(float, position[:3])
                    latitude, longitude = _world_from_mesh(
                        mesh_x,
                        mesh_z,
                        ref_latitude=ref_latitude,
                        ref_longitude=ref_longitude,
                    )
                    dem_elevation = decoded.elevation_at(latitude, longitude)
                    if dem_elevation is None:
                        continue
                    absolute_mesh_elevation = local_elevation + elevation_minimum
                    residuals.append(
                        dem_elevation * unit_to_metres - absolute_mesh_elevation
                    )
            if not residuals:
                raise ValueError(f"{mesh_path} has no ground vertices inside the DEM")
            course_residuals.extend(residuals)
            holes.append(
                {
                    "hole": int(hole["HoleNumber"]),
                    "meshPath": str(mesh_path),
                    "meshSha256": hashlib.sha256(mesh_path.read_bytes()).hexdigest(),
                    "elevationMinimumM": _round(elevation_minimum),
                    **_stats(residuals),
                }
            )
        if not holes:
            raise ValueError(f"course {course_id} has no matching prodgeometry mesh JSON")
        valid_elevations = [
            value
            for row in decoded.elevations
            for value in row
            if value is not None
        ]
        output["courses"].append(
            {
                "globalId": course_id,
                "courseDataPath": str(course_path),
                "courseDataSha256": source_sha256,
                "unit": dem.elevation_unit,
                "grid": {
                    "levelCount": len(dem.levels),
                    "columns": decoded.level.columns,
                    "rows": decoded.level.rows,
                    "shrinkValue": decoded.level.shrink_value,
                    "shrinkFactor": decoded.level.shrink_factor,
                    "encodingTypes": sorted(
                        {tile.descriptor.encoding_type for tile in decoded.tiles}
                    ),
                    "decodedMinimum": min(valid_elevations),
                    "decodedMaximum": max(valid_elevations),
                    "headerMinimum": decoded.level.min_elevation,
                    "headerMaximum": decoded.level.max_elevation,
                    "tileCount": len(decoded.tiles),
                    "minimumPaddingBits": min(
                        tile.padding_bits for tile in decoded.tiles
                    ),
                    "maximumPaddingBits": max(tile.padding_bits for tile in decoded.tiles),
                },
                "holes": holes,
                "allHoles": _stats(course_residuals),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
