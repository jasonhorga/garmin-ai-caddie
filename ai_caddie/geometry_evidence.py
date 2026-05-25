from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Literal

from ai_caddie.data import ROOT, hazard_path, local_to_wgs84, mesh_path, read_json

GeometryCoverage = Literal["ready", "partial", "missing"]
GCJ02_PROVIDERS = {"amap", "amap_gcj02", "gaode", "gaode_gcj02", "tencent", "baidu"}
MAP_PROVIDERS = {
    "esri_world_imagery": {
        "name": "esri_world_imagery",
        "label": "Esri World Imagery",
        "coordinateSystem": "WGS84",
        "gcj02": False,
    },
    "arcgis_world_imagery": {
        "name": "arcgis_world_imagery",
        "label": "ArcGIS World Imagery",
        "coordinateSystem": "WGS84",
        "gcj02": False,
    },
}


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def _coverage(has_hazards: bool, has_meshes: bool) -> GeometryCoverage:
    if has_hazards and has_meshes:
        return "ready"
    if has_hazards or has_meshes:
        return "partial"
    return "missing"


def geometry_coverage_for_hole(global_id: int, local_hole: int) -> dict[str, Any]:
    hazards = hazard_path(int(global_id), int(local_hole))
    meshes = mesh_path(int(global_id), int(local_hole))
    has_hazards = hazards.exists()
    has_meshes = meshes.exists()
    evidence = []
    missing_data = []

    if has_hazards:
        evidence.append({"label": "hazards", "ref": _display_path(hazards)})
    else:
        missing_data.append({"label": "hazards", "reason": "prodgeometry hazard file missing"})

    if has_meshes:
        evidence.append({"label": "meshes", "ref": _display_path(meshes)})
    else:
        missing_data.append({"label": "meshes", "reason": "prodgeometry mesh file missing"})

    return {
        "schema": "ai-caddie-geometry-evidence-v1",
        "globalId": int(global_id),
        "localHole": int(local_hole),
        "coverage": _coverage(has_hazards, has_meshes),
        "hasHazards": has_hazards,
        "hasMeshes": has_meshes,
        "evidence": evidence,
        "missingData": missing_data,
    }


def map_provider_config(provider: str = "esri_world_imagery") -> dict[str, Any]:
    key = provider.strip().lower()
    if key in GCJ02_PROVIDERS or "gcj" in key:
        raise ValueError("GCJ-02 map providers are not supported because Garmin geometry and shots use WGS84")
    if key not in MAP_PROVIDERS:
        raise ValueError(f"unsupported map provider: {provider}")
    return dict(MAP_PROVIDERS[key])


def _load_json_if_ready(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = read_json(path)
    return value if isinstance(value, dict) else None


def _position_to_lonlat(position: Any, ref_lat: float | None, ref_lon: float | None) -> list[float] | None:
    if isinstance(position, dict) and position.get("lat") is not None and position.get("lon") is not None:
        return [round(float(position["lon"]), 7), round(float(position["lat"]), 7)]
    if isinstance(position, (list, tuple)) and len(position) >= 2 and ref_lat is not None and ref_lon is not None:
        lat, lon = local_to_wgs84(float(position[0]), float(position[1]), float(ref_lat), float(ref_lon))
        return [round(float(lon), 7), round(float(lat), 7)]
    return None


def _polygon_ring(points: Any, ref_lat: float | None, ref_lon: float | None) -> list[list[float]]:
    if not isinstance(points, list):
        return []
    ring = []
    for point in points:
        coord = _position_to_lonlat(point, ref_lat, ref_lon)
        if coord is not None:
            ring.append(coord)
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def _feature(geometry: dict[str, Any], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def _hazard_features(hazards: dict[str, Any], ref_lat: float | None, ref_lon: float | None) -> list[dict[str, Any]]:
    features = []
    for index, hazard in enumerate(hazards.get("hazards") or []):
        if not isinstance(hazard, dict):
            continue
        points = hazard.get("polygon") or hazard.get("points") or hazard.get("path")
        ring = _polygon_ring(points, ref_lat, ref_lon)
        if not ring:
            continue
        features.append(
            _feature(
                {"type": "Polygon", "coordinates": [ring]},
                {
                    "layer": "hazard",
                    "id": str(hazard.get("id") or f"hazard-{index + 1}"),
                    "kind": str(hazard.get("kind") or hazard.get("type") or "hazard"),
                },
            )
        )
    return features


def _point_features(hazards: dict[str, Any], ref_lat: float | None, ref_lon: float | None) -> list[dict[str, Any]]:
    features = []
    target = hazards.get("target") if isinstance(hazards.get("target"), dict) else {}
    target_coord = _position_to_lonlat(target.get("position"), ref_lat, ref_lon)
    if target_coord is not None:
        features.append(
            _feature(
                {"type": "Point", "coordinates": target_coord},
                {"layer": "target", "id": str(target.get("id") or "target")},
            )
        )
    for index, tee in enumerate(hazards.get("tees") or []):
        if not isinstance(tee, dict):
            continue
        coord = _position_to_lonlat(tee.get("position"), ref_lat, ref_lon)
        if coord is not None:
            features.append(
                _feature(
                    {"type": "Point", "coordinates": coord},
                    {"layer": "tee", "id": str(tee.get("id") or f"tee-{index + 1}")},
                )
            )
    return features


def _shot_features(shots: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    features = []
    for index, shot in enumerate(shots or []):
        start = _position_to_lonlat(shot.get("start"), None, None)
        end = _position_to_lonlat(shot.get("end"), None, None)
        if start is None or end is None:
            continue
        features.append(
            _feature(
                {"type": "LineString", "coordinates": [start, end]},
                {
                    "layer": "shot_route",
                    "id": str(shot.get("ref") or f"shot-{index + 1}"),
                    "club": shot.get("club"),
                },
            )
        )
    return features


def build_hole_map_dto(
    global_id: int,
    local_hole: int,
    *,
    shots: list[dict[str, Any]] | None = None,
    provider: str = "esri_world_imagery",
) -> dict[str, Any]:
    provider_config = map_provider_config(provider)
    coverage = geometry_coverage_for_hole(global_id, local_hole)
    hazards = _load_json_if_ready(hazard_path(int(global_id), int(local_hole))) or {}
    ref_lat = hazards.get("refLat")
    ref_lon = hazards.get("refLon")
    ref_lat_float = float(ref_lat) if ref_lat is not None else None
    ref_lon_float = float(ref_lon) if ref_lon is not None else None
    features = []
    if hazards:
        features.extend(_hazard_features(hazards, ref_lat_float, ref_lon_float))
        features.extend(_point_features(hazards, ref_lat_float, ref_lon_float))
    features.extend(_shot_features(shots))
    missing_data = list(coverage["missingData"])
    if hazards and (ref_lat_float is None or ref_lon_float is None):
        missing_data.append({"label": "geometry_reference", "reason": "hazard geometry missing WGS84 reference"})
    return {
        "schema": "ai-caddie-hole-map-v1",
        "globalId": int(global_id),
        "localHole": int(local_hole),
        "provider": provider_config,
        "coverage": coverage["coverage"],
        "layers": sorted({str(feature["properties"]["layer"]) for feature in features}),
        "featureCollection": {"type": "FeatureCollection", "features": features},
        "missingData": missing_data,
    }


def geometry_coverage_for_course(global_id: int, holes: Iterable[int] = range(1, 19)) -> dict[str, Any]:
    hole_rows = [geometry_coverage_for_hole(int(global_id), int(hole)) for hole in holes]
    ready = sum(1 for row in hole_rows if row["coverage"] == "ready")
    partial = sum(1 for row in hole_rows if row["coverage"] == "partial")
    if ready == len(hole_rows) and hole_rows:
        coverage: GeometryCoverage = "ready"
    elif ready or partial:
        coverage = "partial"
    else:
        coverage = "missing"
    return {
        "schema": "ai-caddie-course-geometry-coverage-v1",
        "globalId": int(global_id),
        "coverage": coverage,
        "readyHoles": ready,
        "partialHoles": partial,
        "totalHoles": len(hole_rows),
        "holes": hole_rows,
    }


def build_hole_geometry_evidence(round_row: dict[str, Any]) -> dict[str, Any]:
    evidence = geometry_coverage_for_hole(int(round_row.get("globalId") or 0), int(round_row.get("localHole") or 0))
    if round_row.get("shots") and not evidence["hasMeshes"]:
        evidence["missingData"].append({"label": "shot_surface_classification", "reason": "mesh data missing"})
    return evidence
