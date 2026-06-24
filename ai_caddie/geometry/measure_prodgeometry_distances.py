"""Measure distances from tee/target points to decoded CourseView geometry.

The decoded prodgeometry coordinate convention used here is:

- mesh POSITION x/z -> local hole meters as east=-x, north=z
- hole.json TeeLocations and Doglegs already use the same local meter frame
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MESH_JSON = ROOT / "output" / "prodgeometry" / "gid31795_h02_meshes.json"
DEFAULT_OUT = ROOT / "output" / "prodgeometry" / "gid31795_h02_tee_distances.json"

FEATURES = [
    "Bunker.drc",
    "Lake.drc",
    "LakeSide.drc",
    "Green.drc",
    "Fairway.drc",
    "Teebox.drc",
    "TreeArea.drc",
]


Point = tuple[float, float]
Face = tuple[int, int, int]


def mesh_point_to_local(point: list[float]) -> Point:
    x, _y, z = point
    return -float(x), float(z)


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx = bx - ax
    dy = by - ay
    denom = dx * dx + dy * dy
    if denom == 0:
        return dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return dist(p, (ax + t * dx, ay + t * dy))


def point_in_triangle(p: Point, a: Point, b: Point, c: Point, eps: float = 1e-8) -> bool:
    px, py = p
    ax, ay = a
    bx, by = b
    cx, cy = c
    v0x, v0y = cx - ax, cy - ay
    v1x, v1y = bx - ax, by - ay
    v2x, v2y = px - ax, py - ay
    dot00 = v0x * v0x + v0y * v0y
    dot01 = v0x * v1x + v0y * v1y
    dot02 = v0x * v2x + v0y * v2y
    dot11 = v1x * v1x + v1y * v1y
    dot12 = v1x * v2x + v1y * v2y
    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) < eps:
        return False
    inv = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv
    v = (dot00 * dot12 - dot01 * dot02) * inv
    return u >= -eps and v >= -eps and u + v <= 1.0 + eps


def point_triangle_distance(p: Point, tri: tuple[Point, Point, Point]) -> float:
    a, b, c = tri
    if point_in_triangle(p, a, b, c):
        return 0.0
    return min(
        point_segment_distance(p, a, b),
        point_segment_distance(p, b, c),
        point_segment_distance(p, c, a),
    )


def triangle_area(a: Point, b: Point, c: Point) -> float:
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2.0


class Dsu:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def mesh_components(mesh: dict[str, Any]) -> list[dict[str, Any]]:
    positions = [mesh_point_to_local(p) for p in mesh["positions"]]
    faces: list[Face] = [tuple(face) for face in mesh["faces"]]
    dsu = Dsu(len(faces))
    vertex_faces: dict[int, list[int]] = defaultdict(list)
    for face_index, face in enumerate(faces):
        for vertex in face:
            vertex_faces[vertex].append(face_index)
    for touching_faces in vertex_faces.values():
        first = touching_faces[0]
        for other in touching_faces[1:]:
            dsu.union(first, other)

    grouped: dict[int, list[int]] = defaultdict(list)
    for i in range(len(faces)):
        grouped[dsu.find(i)].append(i)

    components = []
    for face_indices in grouped.values():
        tris = [(positions[a], positions[b], positions[c]) for a, b, c in (faces[i] for i in face_indices)]
        vertices = sorted({v for i in face_indices for v in faces[i]})
        xs = [positions[v][0] for v in vertices]
        ys = [positions[v][1] for v in vertices]
        area = 0.0
        cx = 0.0
        cy = 0.0
        for a, b, c in tris:
            tri_area = triangle_area(a, b, c)
            area += tri_area
            cx += (a[0] + b[0] + c[0]) / 3.0 * tri_area
            cy += (a[1] + b[1] + c[1]) / 3.0 * tri_area
        centroid = (cx / area, cy / area) if area else (sum(xs) / len(xs), sum(ys) / len(ys))
        components.append({
            "triangles": tris,
            "face_count": len(face_indices),
            "point_count": len(vertices),
            "area_m2": area,
            "centroid": centroid,
            "bbox": [min(xs), min(ys), max(xs), max(ys)],
        })

    components.sort(key=lambda c: c["area_m2"], reverse=True)
    return components


def segment_edge_intersection_t(start: Point, end: Point, a: Point, b: Point) -> float | None:
    sx, sy = start
    ex, ey = end
    ax, ay = a
    bx, by = b
    rx, ry = ex - sx, ey - sy
    qx, qy = bx - ax, by - ay
    denom = rx * qy - ry * qx
    if abs(denom) < 1e-9:
        return None
    dx, dy = ax - sx, ay - sy
    t = (dx * qy - dy * qx) / denom
    u = (dx * ry - dy * rx) / denom
    if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= u <= 1.0 + 1e-9:
        return max(0.0, min(1.0, t))
    return None


def line_intervals_for_component(start: Point, end: Point, component: dict[str, Any]) -> list[tuple[float, float]]:
    t_values = [0.0, 1.0]
    for a, b, c in component["triangles"]:
        for p, q in ((a, b), (b, c), (c, a)):
            t = segment_edge_intersection_t(start, end, p, q)
            if t is not None:
                t_values.append(t)
    unique = sorted({round(t, 10) for t in t_values})
    intervals = []
    for t0, t1 in zip(unique, unique[1:]):
        if t1 - t0 < 1e-9:
            continue
        mid = (t0 + t1) / 2.0
        probe = (start[0] + (end[0] - start[0]) * mid, start[1] + (end[1] - start[1]) * mid)
        if any(point_in_triangle(probe, *tri) for tri in component["triangles"]):
            intervals.append((t0, t1))
    if any(point_in_triangle(start, *tri) for tri in component["triangles"]):
        intervals.insert(0, (0.0, 0.0))
    if any(point_in_triangle(end, *tri) for tri in component["triangles"]):
        intervals.append((1.0, 1.0))
    return intervals


def target_point(hole: dict[str, Any], green_components: list[dict[str, Any]]) -> tuple[str, Point]:
    for dogleg in hole.get("Doglegs", []) or []:
        line = dogleg.get("Line", [])
        if line:
            last = line[-1]
            return "Dogleg/green endpoint", (float(last["X"]), float(last["Y"]))

    largest_green = green_components[0]
    return "Largest green component centroid", largest_green["centroid"]


def rounded_point(p: Point) -> list[float]:
    return [round(p[0], 2), round(p[1], 2)]


def measure(decoded: dict[str, Any]) -> dict[str, Any]:
    by_name = {mesh["name"]: mesh for mesh in decoded["meshes"]}
    component_cache = {name: mesh_components(by_name[name]) for name in FEATURES if name in by_name}

    hole = decoded["hole"]
    target_name, target = target_point(hole, component_cache["Green.drc"])
    tee_rows = []
    for index, tee in enumerate(hole.get("TeeLocations", []), start=1):
        start = (float(tee["X"]), float(tee["Y"]))
        line_length = dist(start, target)
        feature_rows = []
        for feature, components in component_cache.items():
            component_rows = []
            for comp_index, component in enumerate(components, start=1):
                nearest = min(point_triangle_distance(start, tri) for tri in component["triangles"])
                interval_rows = []
                for t0, t1 in line_intervals_for_component(start, target, component):
                    interval_rows.append({
                        "start_m": round(t0 * line_length, 1),
                        "end_m": round(t1 * line_length, 1),
                    })
                component_rows.append({
                    "component": comp_index,
                    "nearest_m": round(nearest, 1),
                    "center_m": round(dist(start, component["centroid"]), 1),
                    "area_m2": round(component["area_m2"], 1),
                    "centroid": rounded_point(component["centroid"]),
                    "bbox": [round(v, 2) for v in component["bbox"]],
                    "along_line_m": interval_rows,
                })
            feature_rows.append({
                "feature": feature.replace(".drc", ""),
                "components": component_rows,
            })
        tee_rows.append({
            "tee_index": index,
            "sets": tee.get("Sets", []),
            "position": rounded_point(start),
            "target_distance_m": round(line_length, 1),
            "features": feature_rows,
        })

    return {
        "globalId": hole.get("GlobalId"),
        "holeNumber": hole.get("HoleNumber"),
        "target": {
            "name": target_name,
            "position": rounded_point(target),
        },
        "tees": tee_rows,
    }


def print_summary(result: dict[str, Any]) -> None:
    print(f"gid {result['globalId']} hole {result['holeNumber']}")
    print(f"target: {result['target']['name']} {result['target']['position']}")
    for tee in result["tees"]:
        sets = ",".join(str(v) for v in tee["sets"])
        print(
            f"\ntee {tee['tee_index']} sets=[{sets}] "
            f"pos={tee['position']} -> target={tee['target_distance_m']}m"
        )
        for feature in tee["features"]:
            name = feature["feature"]
            if name not in {"Bunker", "Lake", "Green", "Fairway", "Teebox"}:
                continue
            comps = feature["components"]
            if name == "Green":
                target = result["target"]["position"]
                nearest = sorted(
                    comps,
                    key=lambda c: math.hypot(c["centroid"][0] - target[0], c["centroid"][1] - target[1]),
                )[:1]
            else:
                nearest = sorted(comps, key=lambda c: c["nearest_m"])[:4]
            bits = []
            for comp in nearest:
                line = comp["along_line_m"]
                line_text = ""
                if line:
                    line_text = f", line {line[0]['start_m']}-{line[-1]['end_m']}m"
                bits.append(f"#{comp['component']} nearest {comp['nearest_m']}m{line_text}")
            print(f"  {name:>7}: " + "; ".join(bits))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh-json", type=Path, default=DEFAULT_MESH_JSON)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    decoded = json.loads(args.mesh_json.read_text())
    result = measure(decoded)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print_summary(result)
    print(f"\n[ok] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
