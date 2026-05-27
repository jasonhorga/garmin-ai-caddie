from __future__ import annotations

from pathlib import Path
import math
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
SURFACE_KIND_ALIASES = {
    "bunker": "bunker",
    "bunkerdrc": "bunker",
    "sand": "bunker",
    "sandtrap": "bunker",
    "lake": "water",
    "lakedrc": "water",
    "water": "water",
    "waterhazard": "water",
    "lakeside": "water_edge",
    "lakesidedrc": "water_edge",
    "wateredge": "water_edge",
    "water_edge": "water_edge",
    "green": "green",
    "greendrc": "green",
    "puttinggreen": "green",
    "fairway": "fairway",
    "fairwaydrc": "fairway",
    "rough": "rough",
    "roughdrc": "rough",
    "teebox": "teebox",
    "teeboxdrc": "teebox",
    "tee": "teebox",
    "tee_box": "teebox",
    "treearea": "tree_area",
    "treeareadrc": "tree_area",
    "tree_area": "tree_area",
    "trees": "tree_area",
    "playablebounds": "playable_bounds",
    "playableboundsdrc": "playable_bounds",
    "playable_bounds": "playable_bounds",
    "bounds": "playable_bounds",
}
SURFACE_PRIORITY = ["water", "bunker", "green", "fairway", "rough", "tree_area", "teebox", "playable_bounds"]
GENERIC_SURFACE_KINDS = {"mesh", "hazard", "surface", "feature"}


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


def _surface_kind_values(row: dict[str, Any]) -> list[Any]:
    values = []
    for key in ("kind", "type", "surface", "name", "source", "file", "filename", "layer"):
        value = row.get(key)
        if value is not None:
            values.append(value)
    return values


def _surface_value_to_text(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("kind", "type", "surface", "name", "source", "file", "filename", "layer"):
            nested = value.get(key)
            if nested is not None:
                text = _surface_value_to_text(nested)
                if text:
                    return text
        return None
    text = str(value).strip()
    return text or None


def _snake_case_surface_name(value: str) -> str:
    stem = value.replace("\\", "/").rsplit("/", 1)[-1]
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    chars: list[str] = []
    previous = ""
    for char in stem:
        if char.isupper() and previous and (previous.islower() or previous.isdigit()):
            chars.append("_")
        if char.isalnum():
            chars.append(char.lower())
        elif chars and chars[-1] != "_":
            chars.append("_")
        previous = char
    return "".join(chars).strip("_") or "unknown"


def _normalize_surface_kind(value: Any) -> str | None:
    text = _surface_value_to_text(value)
    if text is None:
        return None
    leaf = text.replace("\\", "/").rsplit("/", 1)[-1].strip()
    lower = leaf.lower().replace("-", "_").replace(" ", "_")
    compact = "".join(char for char in lower if char.isalnum())
    return SURFACE_KIND_ALIASES.get(lower) or SURFACE_KIND_ALIASES.get(compact) or _snake_case_surface_name(leaf)


def _known_surface_kind(value: Any) -> str | None:
    text = _surface_value_to_text(value)
    if text is None:
        return None
    leaf = text.replace("\\", "/").rsplit("/", 1)[-1].strip()
    lower = leaf.lower().replace("-", "_").replace(" ", "_")
    compact = "".join(char for char in lower if char.isalnum())
    return SURFACE_KIND_ALIASES.get(lower) or SURFACE_KIND_ALIASES.get(compact)


def _surface_kind(row: dict[str, Any], fallback: str) -> str:
    deferred: list[str] = []
    for value in _surface_kind_values(row):
        known_kind = _known_surface_kind(value)
        if known_kind:
            return known_kind
        kind = _normalize_surface_kind(value)
        if kind:
            deferred.append(kind)
    raw_id = row.get("id")
    id_kind = _known_surface_kind(raw_id)
    if id_kind:
        return id_kind
    id_kind = _normalize_surface_kind(raw_id)
    if id_kind and ".drc" in str(raw_id).lower():
        return id_kind
    for kind in deferred:
        if kind != fallback and kind not in GENERIC_SURFACE_KINDS:
            return kind
    if deferred:
        return deferred[0]
    return fallback


def _surface_priority(kind: str) -> int:
    if kind in SURFACE_PRIORITY:
        return SURFACE_PRIORITY.index(kind)
    return len(SURFACE_PRIORITY)


def _surface_id(row: dict[str, Any], fallback: str, kind: str) -> str:
    raw_id = row.get("id")
    if raw_id is None:
        return fallback
    raw_text = str(raw_id).strip()
    if not raw_text:
        return fallback
    normalized = _normalize_surface_kind(raw_text)
    if normalized == kind and ".drc" in raw_text.lower():
        return kind
    return raw_text


def _surface_match(point: list[float], rows: list[dict[str, Any]], *, source: str) -> dict[str, Any] | None:
    matches = []
    for index, row in enumerate(rows):
        polygon = row.get("polygon") or row.get("points") or row.get("path")
        if not isinstance(polygon, list):
            continue
        if _point_in_ring(point, polygon):
            kind = _surface_kind(row, source)
            matches.append(
                {
                    "priority": _surface_priority(kind),
                    "index": index,
                    "surface": {
                        "kind": kind,
                        "source": source,
                        "id": _surface_id(row, f"{source}-{index + 1}", kind),
                    },
                }
            )
    if matches:
        return min(matches, key=lambda row: (row["priority"], row["index"]))["surface"]
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


def build_route_geometry_evidence(
    global_id: int,
    local_hole: int,
    *,
    start: Any,
    target: Any | None = None,
    landing_radius_m: float = 18.0,
) -> dict[str, Any]:
    coverage = geometry_coverage_for_hole(int(global_id), int(local_hole))
    hazards = _load_json_if_ready(hazard_path(int(global_id), int(local_hole))) or {}
    ref_lat = hazards.get("refLat")
    ref_lon = hazards.get("refLon")
    ref_lat_float = float(ref_lat) if ref_lat is not None else None
    ref_lon_float = float(ref_lon) if ref_lon is not None else None
    start_local = _position_to_local(start, ref_lat_float, ref_lon_float)
    target_position = target
    if target_position is None and isinstance(hazards.get("target"), dict):
        target_position = hazards["target"].get("position")
    target_local = _position_to_local(target_position, ref_lat_float, ref_lon_float)
    missing_data = list(coverage["missingData"])
    if start_local is None:
        missing_data.append({"label": "route_start", "reason": "route start position is unavailable"})
    if target_local is None:
        missing_data.append({"label": "route_target", "reason": "route target position is unavailable"})
    if hazards and (ref_lat_float is None or ref_lon_float is None):
        missing_data.append({"label": "geometry_reference", "reason": "hazard geometry missing WGS84 reference"})

    line_intersections: list[dict[str, Any]] = []
    hazard_clearances: list[dict[str, Any]] = []
    landing_window_risks: list[dict[str, Any]] = []
    avoid_zones: list[dict[str, Any]] = []
    route_length = _point_distance(start_local, target_local) if start_local and target_local else None

    if start_local and target_local:
        for index, hazard in enumerate(hazards.get("hazards") or []):
            if not isinstance(hazard, dict):
                continue
            fallback_id = f"hazard-{index + 1}"
            route_rows = _route_intersections_for_hazard(
                start_local,
                target_local,
                hazard,
                fallback_id=fallback_id,
            )
            landing_risk = _landing_window_risk_for_hazard(
                target_local,
                float(landing_radius_m),
                hazard,
                fallback_id=fallback_id,
            )
            hazard_id = str(hazard.get("id") or f"hazard-{index + 1}")
            kind = str(hazard.get("kind") or hazard.get("type") or "hazard")
            if route_rows:
                line_intersections.extend(route_rows)
                distances = [float(row["distanceFromStart_m"]) for row in route_rows]
                clear = {
                    "hazardId": hazard_id,
                    "kind": kind,
                    "carryToFront_m": round(min(distances), 1),
                    "carryToClear_m": round(max(distances), 1),
                    "intersectionCount": len(route_rows),
                }
                hazard_clearances.append(clear)
                avoid_zones.append({"id": hazard_id, "kind": kind, "carryToClear_m": clear["carryToClear_m"]})
            if landing_risk:
                landing_window_risks.append(landing_risk)
                if not any(row.get("id") == hazard_id for row in avoid_zones):
                    avoid_zones.append(
                        {
                            "id": hazard_id,
                            "kind": kind,
                            "distanceToCenter_m": landing_risk["distanceToCenter_m"],
                            "source": "landing_window",
                        }
                    )

    line_intersections.sort(key=lambda row: (float(row.get("distanceFromStart_m") or 0), str(row.get("hazardId") or "")))
    hazard_clearances.sort(key=lambda row: (float(row.get("carryToFront_m") or 0), str(row.get("hazardId") or "")))
    landing_window_risks.sort(key=lambda row: (float(row.get("distanceToCenter_m") or 0), str(row.get("hazardId") or "")))
    avoid_zones.sort(key=lambda row: (float(row.get("carryToClear_m") or row.get("distanceToCenter_m") or 0), str(row.get("id") or "")))

    return {
        "schema": "ai-caddie-route-geometry-evidence-v1",
        "globalId": int(global_id),
        "localHole": int(local_hole),
        "coverage": coverage["coverage"],
        "routeStartLocal": _rounded_point(start_local),
        "routeTargetLocal": _rounded_point(target_local),
        "routeLength_m": round(route_length, 1) if route_length is not None else None,
        "landingWindowLocal": {
            "center": _rounded_point(target_local),
            "radius_m": round(float(landing_radius_m), 1),
        }
        if target_local is not None
        else None,
        "lineIntersections": line_intersections,
        "hazardClearances": hazard_clearances,
        "landingWindowRisks": landing_window_risks,
        "avoidZones": avoid_zones,
        "missingData": missing_data,
    }


def _rounded_point(point: list[float] | None) -> list[float] | None:
    if point is None:
        return None
    return [round(float(point[0]), 3), round(float(point[1]), 3)]


def _point_distance(start: list[float] | None, end: list[float] | None) -> float | None:
    if start is None or end is None:
        return None
    return math.hypot(float(end[0]) - float(start[0]), float(end[1]) - float(start[1]))


def _landing_window_risk_for_hazard(
    center: list[float],
    radius_m: float,
    hazard: dict[str, Any],
    *,
    fallback_id: str,
) -> dict[str, Any] | None:
    ring = hazard.get("polygon") or hazard.get("points") or hazard.get("path")
    if not isinstance(ring, list) or len(ring) < 3:
        return None
    distance = _point_to_polygon_distance(center, ring)
    if distance is None or distance > radius_m:
        return None
    return {
        "hazardId": str(hazard.get("id") or fallback_id),
        "kind": str(hazard.get("kind") or hazard.get("type") or "hazard"),
        "distanceToCenter_m": round(distance, 1),
        "landingRadius_m": round(float(radius_m), 1),
        "overlap_m": round(max(0.0, float(radius_m) - distance), 1),
    }


def _point_to_polygon_distance(point: list[float], ring: list[Any]) -> float | None:
    if _point_in_ring(point, ring):
        return 0.0
    points = ring if ring[0] == ring[-1] else [*ring, ring[0]]
    distances = []
    for first, second in zip(points, points[1:]):
        if not isinstance(first, (list, tuple)) or not isinstance(second, (list, tuple)) or len(first) < 2 or len(second) < 2:
            continue
        distances.append(
            _point_to_segment_distance(
                (float(point[0]), float(point[1])),
                (float(first[0]), float(first[1])),
                (float(second[0]), float(second[1])),
            )
        )
    return min(distances) if distances else None


def _point_to_segment_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    px, py = point
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return math.hypot(px - sx, py - sy)
    t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / length_sq))
    nearest_x = sx + t * dx
    nearest_y = sy + t * dy
    return math.hypot(px - nearest_x, py - nearest_y)


def _route_intersections_for_hazard(
    start: list[float],
    target: list[float],
    hazard: dict[str, Any],
    *,
    fallback_id: str,
) -> list[dict[str, Any]]:
    ring = hazard.get("polygon") or hazard.get("points") or hazard.get("path")
    if not isinstance(ring, list) or len(ring) < 3:
        return []
    hazard_id = str(hazard.get("id") or fallback_id)
    kind = str(hazard.get("kind") or hazard.get("type") or "hazard")
    rows: list[dict[str, Any]] = []
    seen: set[tuple[float, float, float]] = set()
    points = ring if ring[0] == ring[-1] else [*ring, ring[0]]
    for first, second in zip(points, points[1:]):
        if not isinstance(first, (list, tuple)) or not isinstance(second, (list, tuple)) or len(first) < 2 or len(second) < 2:
            continue
        intersection = _segment_intersection(
            (float(start[0]), float(start[1])),
            (float(target[0]), float(target[1])),
            (float(first[0]), float(first[1])),
            (float(second[0]), float(second[1])),
        )
        if intersection is None:
            continue
        x, y, t = intersection
        distance = math.hypot(x - float(start[0]), y - float(start[1]))
        key = (round(x, 3), round(y, 3), round(distance, 3))
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "hazardId": hazard_id,
                "kind": kind,
                "local": [round(x, 3), round(y, 3)],
                "routeFraction": round(t, 4),
                "distanceFromStart_m": round(distance, 1),
            }
        )
    rows.sort(key=lambda row: float(row["distanceFromStart_m"]))
    return rows


def _segment_intersection(
    p1: tuple[float, float],
    p2: tuple[float, float],
    q1: tuple[float, float],
    q2: tuple[float, float],
) -> tuple[float, float, float] | None:
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = q1
    x4, y4 = q2
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denominator
    if t < -1e-9 or t > 1 + 1e-9 or u < -1e-9 or u > 1 + 1e-9:
        return None
    x = x1 + t * (x2 - x1)
    y = y1 + t * (y2 - y1)
    return x, y, t


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
    start: Any | None = None,
    target: Any | None = None,
    landing_radius_m: float = 18.0,
) -> dict[str, Any]:
    evidence = geometry_coverage_for_hole(global_id, local_hole)
    if start is not None or target is not None:
        evidence["routeEvidence"] = build_route_geometry_evidence(
            global_id,
            local_hole,
            start=start,
            target=target,
            landing_radius_m=landing_radius_m,
        )
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
