"""Export AI-caddie friendly hazard components from decoded prodgeometry meshes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from measure_prodgeometry_distances import (
    dist,
    line_intervals_for_component,
    mesh_components,
    point_triangle_distance,
    target_point,
)

ROOT = Path(__file__).parent
DEFAULT_MESH_JSON = ROOT / "output" / "prodgeometry" / "gid31795_h02_meshes.json"
DEFAULT_OUT_DIR = ROOT / "output" / "prodgeometry_hazards"

FEATURES = {
    "Bunker.drc": "bunker",
    "Lake.drc": "water",
    "LakeSide.drc": "water_edge",
    "Green.drc": "green",
    "Fairway.drc": "fairway",
    "Rough.drc": "rough",
    "Teebox.drc": "teebox",
    "TreeArea.drc": "tree_area",
    "PlayableBounds.drc": "playable_bounds",
}


def rounded_point(point: tuple[float, float]) -> list[float]:
    return [round(point[0], 2), round(point[1], 2)]


def rounded_bbox(bbox: list[float]) -> list[float]:
    return [round(v, 2) for v in bbox]


def component_distance_to_point(component: dict[str, Any], point: tuple[float, float]) -> float:
    return min(point_triangle_distance(point, tri) for tri in component["triangles"])


def export(decoded: dict[str, Any]) -> dict[str, Any]:
    hole = decoded["hole"]
    meshes = {mesh["name"]: mesh for mesh in decoded["meshes"]}
    components_by_mesh = {
        source: mesh_components(meshes[source])
        for source in FEATURES
        if source in meshes
    }
    target_name, target = target_point(hole, components_by_mesh.get("Green.drc", []))

    tees = []
    for index, tee in enumerate(hole.get("TeeLocations", []) or [], start=1):
        position = (float(tee["X"]), float(tee["Y"]))
        tees.append({
            "tee_index": index,
            "sets": tee.get("Sets", []),
            "position": rounded_point(position),
            "target_distance_m": round(dist(position, target), 1),
        })

    hazards = []
    for source, kind in FEATURES.items():
        components = components_by_mesh.get(source, [])
        for component_index, component in enumerate(components, start=1):
            row = {
                "id": f"{kind}_{component_index}",
                "kind": kind,
                "source": source,
                "component": component_index,
                "area_m2": round(component["area_m2"], 1),
                "centroid": rounded_point(component["centroid"]),
                "bbox": rounded_bbox(component["bbox"]),
                "point_count": component["point_count"],
                "face_count": component["face_count"],
                "tee_distances": [],
            }
            for tee in tees:
                tee_pos = tuple(tee["position"])
                target_distance = float(tee["target_distance_m"])
                intervals = []
                for t0, t1 in line_intervals_for_component(tee_pos, target, component):
                    intervals.append({
                        "start_m": round(t0 * target_distance, 1),
                        "end_m": round(t1 * target_distance, 1),
                    })
                row["tee_distances"].append({
                    "tee_index": tee["tee_index"],
                    "nearest_m": round(component_distance_to_point(component, tee_pos), 1),
                    "center_m": round(dist(tee_pos, component["centroid"]), 1),
                    "along_target_line_m": intervals,
                })
            hazards.append(row)

    hazards.sort(key=lambda h: (h["kind"], h["component"]))
    return {
        "globalId": hole.get("GlobalId"),
        "holeNumber": hole.get("HoleNumber"),
        "courseGenVersion": hole.get("CourseGenVersion"),
        "version": hole.get("Version"),
        "refLat": hole.get("RefLat"),
        "refLon": hole.get("RefLon"),
        "target": {"name": target_name, "position": rounded_point(target)},
        "tees": tees,
        "hazards": hazards,
        "mesh_sources_present": sorted(meshes),
        "mesh_sources_missing": sorted(set(FEATURES) - set(meshes)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh-json", type=Path, default=DEFAULT_MESH_JSON)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    decoded = json.loads(args.mesh_json.read_text())
    result = export(decoded)
    out = args.out
    if out is None:
        out = args.out_dir / f"gid{result['globalId']}_h{int(result['holeNumber']):02d}_hazards.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[ok] hazards={len(result['hazards'])} wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
