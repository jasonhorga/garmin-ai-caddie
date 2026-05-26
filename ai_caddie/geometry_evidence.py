from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Literal

from ai_caddie.data import ROOT, hazard_path, local_to_wgs84, mesh_path, read_json, wgs84_to_local

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


def _position_to_local(position: Any, ref_lat: float | None, ref_lon: float | None) -> list[float] | None:
    if isinstance(position, dict):
        if position.get("x") is not None and position.get("y") is not None:
            return [float(position["x"]), float(position["y"])]
        if position.get("lat") is not None and position.get("lon") is not None and ref_lat is not None and ref_lon is not None:
            return wgs84_to_local(float(position["lat"]), float(position["lon"]), float(ref_lat), float(ref_lon))
    if isinstance(position, (list, tuple)) and len(position) >= 2:
        return [float(position[0]), float(position[1])]
    return None


def _point_in_ring(point: list[float], ring: list[Any]) -> bool:
    if len(ring) < 3:
        return False
    x, y = point
    inside = False
    previous = ring[-1]
    for current in ring:
        if not isinstance(current, (list, tuple)) or len(current) < 2:
            previous = current
            continue
        if not isinstance(previous, (list, tuple)) or len(previous) < 2:
            previous = current
            continue
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        intersects = (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
        if intersects:
            inside = not inside
        previous = current
    return inside


def _mesh_surface_rows(meshes: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key in ("surfaces", "meshes", "features"):
        values = meshes.get(key)
        if isinstance(values, list):
            rows.extend(row for row in values if isinstance(row, dict))
    return rows


def _surface_match(point: list[float], rows: list[dict[str, Any]], *, source: str) -> dict[str, Any] | None:
    for index, row in enumerate(rows):
        polygon = row.get("polygon") or row.get("points") or row.get("path")
        if not isinstance(polygon, list):
            continue
        if _point_in_ring(point, polygon):
            return {
                "kind": str(row.get("kind") or row.get("type") or row.get("surface") or source),
                "source": source,
                "id": str(row.get("id") or f"{source}-{index + 1}"),
            }
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


def classify_shot_surface(global_id: int, local_hole: int, shot: dict[str, Any]) -> dict[str, Any]:
    hazards = _load_json_if_ready(hazard_path(int(global_id), int(local_hole))) or {}
    meshes = _load_json_if_ready(mesh_path(int(global_id), int(local_hole))) or {}
    ref_lat = hazards.get("refLat")
    ref_lon = hazards.get("refLon")
    ref_lat_float = float(ref_lat) if ref_lat is not None else None
    ref_lon_float = float(ref_lon) if ref_lon is not None else None
    point = _position_to_local(shot.get("end") or shot.get("endLoc") or shot.get("position"), ref_lat_float, ref_lon_float)
    missing_data = []
    evidence = []
    if point is None:
        missing_data.append({"label": "shot_position", "reason": "shot end position is unavailable or lacks geometry reference"})
    if not hazards:
        missing_data.append({"label": "hazards", "reason": "prodgeometry hazard file missing"})
    if not meshes:
        missing_data.append({"label": "meshes", "reason": "prodgeometry mesh file missing"})

    surface = {"kind": "unknown", "source": "none", "id": None}
    if point is not None:
        hazard_match = _surface_match(point, [row for row in hazards.get("hazards", []) or [] if isinstance(row, dict)], source="hazard")
        mesh_match = _surface_match(point, _mesh_surface_rows(meshes), source="mesh")
        if hazard_match:
            surface = hazard_match
        elif mesh_match:
            surface = mesh_match
        else:
            missing_data.append({"label": "surface_match", "reason": "shot endpoint did not fall inside a known hazard or surface polygon"})
        evidence.append({"label": "shot_endpoint_local", "value": [round(point[0], 3), round(point[1], 3)]})

    return {
        "schema": "ai-caddie-shot-surface-classification-v1",
        "globalId": int(global_id),
        "localHole": int(local_hole),
        "shotRef": str(shot.get("ref") or shot.get("shotRef") or shot.get("id") or ""),
        "surface": surface,
        "evidence": evidence,
        "missingData": missing_data,
    }


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


def build_source_bound_hole_geometry_evidence(
    global_id: int,
    local_hole: int,
    *,
    data: Any | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    evidence = geometry_coverage_for_hole(global_id, local_hole)
    if not source_ref:
        return evidence

    source_ref_value = str(source_ref)
    shot_routes = _shot_routes_for_source(data, int(global_id), int(local_hole), source_ref_value)
    evidence["sourceRef"] = source_ref_value
    evidence["shotRoutes"] = shot_routes
    if shot_routes:
        evidence["evidence"].append(
            {
                "label": "shot_routes",
                "sourceRef": source_ref_value,
                "count": len(shot_routes),
                "refs": [route["shotRef"] for route in shot_routes],
            }
        )
        evidence["surfaceClassifications"] = [
            classify_shot_surface(int(global_id), int(local_hole), route)
            for route in shot_routes
        ]
    else:
        evidence["missingData"].append(
            {
                "label": "source_shots",
                "reason": f"{source_ref_value} has no matching normalized shots for this geometry hole",
            }
        )
    return evidence


def _shot_routes_for_source(data: Any | None, global_id: int, local_hole: int, source_ref: str) -> list[dict[str, Any]]:
    if data is None:
        return []
    shots = getattr(data, "shots", []) or []
    routes = []
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        shot_ref = _shot_ref_for_source_bound_route(shot, index)
        if not _shot_matches_geometry_hole(shot, global_id, local_hole):
            continue
        if not _shot_matches_source_ref(shot, shot_ref, source_ref):
            continue
        route = _shot_route(shot, shot_ref)
        if route is not None:
            routes.append(route)
    return routes


def _shot_ref_for_source_bound_route(shot: dict[str, Any], index: int) -> str:
    round_id = str(shot.get("roundId") or shot.get("scorecardId") or "")
    hole = str(shot.get("hole") or shot.get("localHole") or "")
    return f"{round_id}:{hole}:{index}"


def _shot_matches_geometry_hole(shot: dict[str, Any], global_id: int, local_hole: int) -> bool:
    shot_global = shot.get("globalId")
    if shot_global is not None and int(shot_global) != int(global_id):
        return False
    shot_local_hole = shot.get("localHole") if shot.get("localHole") is not None else shot.get("hole")
    return shot_local_hole is not None and int(shot_local_hole) == int(local_hole)


def _shot_matches_source_ref(shot: dict[str, Any], shot_ref: str, source_ref: str) -> bool:
    if source_ref == shot_ref:
        return True
    parts = [part for part in source_ref.split(":") if part != ""]
    round_id = str(shot.get("roundId") or shot.get("scorecardId") or "")
    hole = str(shot.get("hole") or shot.get("localHole") or "")
    if len(parts) == 1:
        return parts[0] == round_id
    if len(parts) == 2:
        return parts[0] == round_id and parts[1] == hole
    return False


def _shot_route(shot: dict[str, Any], shot_ref: str) -> dict[str, Any] | None:
    start = shot.get("start") or shot.get("startLoc")
    end = shot.get("end") or shot.get("endLoc")
    if start is None and end is None:
        return None
    return {
        "ref": shot_ref,
        "shotRef": shot_ref,
        "roundId": str(shot.get("roundId") or shot.get("scorecardId") or ""),
        "hole": shot.get("hole") or shot.get("localHole"),
        "club": shot.get("club") or shot.get("clubName"),
        "distance": shot.get("distance") or shot.get("meters"),
        "surface": shot.get("surface") or shot.get("endLie"),
        "start": start,
        "end": end,
    }


def build_hole_geometry_evidence(round_row: dict[str, Any]) -> dict[str, Any]:
    evidence = geometry_coverage_for_hole(int(round_row.get("globalId") or 0), int(round_row.get("localHole") or 0))
    if round_row.get("shots") and not evidence["hasMeshes"]:
        evidence["missingData"].append({"label": "shot_surface_classification", "reason": "mesh data missing"})
    if round_row.get("shots") and (evidence["hasHazards"] or evidence["hasMeshes"]):
        evidence["surfaceClassifications"] = [
            classify_shot_surface(int(round_row.get("globalId") or 0), int(round_row.get("localHole") or 0), shot)
            for shot in round_row.get("shots") or []
            if isinstance(shot, dict)
        ]
    return evidence
