"""Rule-based hole analysis for the AI Caddie MVP."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
import html
import json
import math

from ai_caddie.geometry.measure_prodgeometry_distances import (
    bind_selected_green_target,
    dist,
    line_intervals_for_component,
    mesh_components,
    point_triangle_distance,
)

from ai_caddie.core.data import (
    available_prep_holes,
    build_club_profiles,
    clean_club_name,
    hazard_path,
    load_shot_file,
    load_scorecard,
    local_to_wgs84,
    mesh_path,
    normalize_garmin_hole,
    normalize_manual_hole,
    round_hole_ref,
    read_json,
    wgs84_to_local,
    write_json,
)
from ai_caddie.caddie.decision import build_decision_plan, judge_decision_outcome

ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_OUT = ROOT / "output" / "ai_caddie"

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
RISK_KINDS = {"bunker", "water", "tree_area", "water_edge"}
GOOD_SURFACES = {"fairway", "green", "teebox"}
SURFACE_PRIORITY = ["water", "bunker", "green", "fairway", "rough", "tree_area", "teebox", "playable_bounds"]
STRATEGY_DISTANCE_KINDS = {"water", "bunker", "tree_area", "green"}
KIND_CN = {
    "fairway": "球道",
    "green": "果岭",
    "rough": "长草",
    "bunker": "沙坑",
    "water": "水障碍",
    "water_edge": "水边",
    "tree_area": "树林",
    "teebox": "Tee 台",
    "playable_bounds": "可打边界",
    "target": "目标",
}

COLORS = {
    "fairway": "#6fbf73",
    "green": "#27ae60",
    "rough": "#73945b",
    "bunker": "#d9c27f",
    "water": "#4da3d9",
    "water_edge": "#2b7da8",
    "tree_area": "#2d6b3f",
    "teebox": "#9bd29b",
    "playable_bounds": "none",
}


def _round_point(point: list[float] | tuple[float, float] | None) -> list[float] | None:
    if point is None:
        return None
    return [round(float(point[0]), 2), round(float(point[1]), 2)]


TEE_SET_BY_BOX = {
    "black": 1,
    "blue": 2,
    "white": 3,
    "gold": 4,
    "yellow": 4,
    "red": 5,
}


def _selected_tee(geometry: dict[str, Any], tee_box: str | None = None) -> dict[str, Any] | None:
    hazards = geometry.get("hazards") or {}
    tees = hazards.get("tees") or []
    tees = [t for t in tees if t.get("position")]
    if not tees:
        return None

    tee_set = None
    requested = str(tee_box or "").strip().lower()
    global_id = hazards.get("globalId") or geometry.get("globalId")
    if requested and global_id is not None:
        try:
            from ai_caddie.courses.course_reference import courseview_tees

            used_keys: set[str] = set()
            for row in courseview_tees(int(global_id), allow_fetch=False):
                key = _release_tee_box_key(row.get("name"), row.get("index"), used_keys)
                if requested in {key, str(row.get("name") or "").strip().lower()}:
                    tee_set = int(row["index"])
                    break
        except Exception:
            tee_set = None
    if tee_set is None:
        tee_set = TEE_SET_BY_BOX.get(requested)
    if tee_set is not None:
        match = next((t for t in tees if tee_set in (t.get("sets") or [])), None)
        if match:
            return match

    return max(tees, key=lambda t: float(t.get("target_distance_m") or 0.0))


# Canonical tee colours → geometry set number, ordered longest tee (set 1) to shortest (set 5).
# Mirrors TEE_SET_BY_BOX but deduped to one colour per set (gold/yellow both map to set 4 → gold is the
# canonical key). The returned tee list reads back-tee → forward-tee, like Garmin's own picker order.
_CANONICAL_TEES: list[tuple[str, int]] = [
    ("black", 1),
    ("blue", 2),
    ("white", 3),
    ("gold", 4),
    ("red", 5),
]

# CourseView tee display names → canonical colour, tolerant of English + Chinese labels so a course's
# OWN tee name (Garmin's label) can be pinned onto the matching geometry set. Unknown names stay
# unmapped (the tee still lists by its geometry set, just under the generic colour title).
_TEE_COLOR_ALIASES: dict[str, str] = {
    "black": "black", "championship": "black", "champ": "black", "tips": "black", "back": "black",
    "blue": "blue",
    "white": "white",
    "gold": "gold", "yellow": "gold",
    "red": "red", "forward": "red", "ladies": "red",
    "黑": "black", "蓝": "blue", "白": "white", "金": "gold", "黄": "gold", "红": "red",
}


def _normalize_tee_color(name: str | None) -> str | None:
    """Best-effort map a CourseView tee display name (English or Chinese) to a canonical colour key."""
    key = str(name or "").strip().lower()
    if not key:
        return None
    if key in _TEE_COLOR_ALIASES:
        return _TEE_COLOR_ALIASES[key]
    for token, color in _TEE_COLOR_ALIASES.items():
        if token in key:
            return color
    return None


def _release_tee_box_key(name: Any, index: Any, used: set[str]) -> str:
    """Stable request key for a release tee; the real numeric index remains in ``set``."""
    key = str(name or "").strip().lower()
    for suffix in (" tees", " tee"):
        if key.endswith(suffix):
            key = key[:-len(suffix)].strip()
            break
    key = {
        "黑": "black", "蓝": "blue", "白": "white", "金": "gold",
        "黄": "yellow", "红": "red", "绿": "green", "银": "silver",
    }.get(key, key)
    try:
        set_index = int(index)
    except (TypeError, ValueError):
        set_index = 0
    if not key or key in used:
        key = f"cv-{set_index}"
    used.add(key)
    return key


def course_tee_options(
    global_id: int,
    *,
    tee_name_resolver: Any = None,
    holes_resolver: Any = None,
    geometry_loader: Any = None,
) -> dict[str, Any]:
    """The course's selectable tee boxes for the pre-round picker: each colour's total yards (summed
    tee→target geometry, honestly ``None`` when a tee has no geometry — never faked), its geometry set
    number, hole count and which is the default (blue when the course has it, else the longest tee).
    Colour names come from the CourseView release when available. A course with neither geometry nor
    CourseView names degrades to generic 长/中/短 tiers. Resolvers are injectable for hermetic tests."""
    gid = int(global_id)

    if tee_name_resolver is None:
        def tee_name_resolver(_gid: int) -> list[str]:
            try:
                from ai_caddie.courses.course_reference import courseview_tees
                return courseview_tees(_gid, allow_fetch=False)
            except Exception:
                return []
    resolve_holes = holes_resolver or available_prep_holes
    resolve_geometry = geometry_loader or load_geometry

    # Sum every REAL release set's tee→target distance across holes. A geometry tee may serve
    # several release sets; each named scorecard tee remains selectable even when two share a marker.
    set_meters: dict[int, float] = {}
    set_holes: dict[int, int] = {}
    for hole in resolve_holes(gid):
        tees = ((resolve_geometry(gid, int(hole)) or {}).get("hazards") or {}).get("tees") or []
        for tee in tees:
            distance = tee.get("target_distance_m")
            if distance is None:
                continue
            for raw_set in tee.get("sets") or []:
                try:
                    set_num = int(raw_set)
                except (TypeError, ValueError):
                    continue
                set_meters[set_num] = set_meters.get(set_num, 0.0) + float(distance)
                set_holes[set_num] = set_holes.get(set_num, 0) + 1

    raw_tees = list(tee_name_resolver(gid) or [])
    release_rows = [row for row in raw_tees if isinstance(row, dict)]
    men_rows = [row for row in release_rows if str(row.get("gender") or "").upper() == "MEN"]
    if men_rows:
        release_rows = men_rows
    release_rows.sort(key=lambda row: int(row.get("index") or 0))

    tees_out: list[dict[str, Any]] = []
    if release_rows:
        used_keys: set[str] = set()
        for row in release_rows:
            name = str(row.get("name") or "").strip()
            try:
                set_num = int(row.get("index"))
            except (TypeError, ValueError):
                continue
            if not name or set_num <= 0:
                continue
            meters = set_meters.get(set_num)
            tees_out.append({
                "teeBox": _release_tee_box_key(name, set_num, used_keys),
                "name": name,
                "set": set_num,
                "yards": int(round(meters * 1.09361)) if meters else None,
                "holeCount": set_holes.get(set_num, 0),
                "slopeRating": row.get("slopeRating"),
                "courseRating": row.get("courseRating"),
                "default": False,
            })

    if not release_rows:
        # Legacy/cache fallback when the release is unavailable: retain the previous canonical list.
        named_by_color: dict[str, str] = {}
        for raw_name in raw_tees:
            color = _normalize_tee_color(raw_name)
            if color and color not in named_by_color:
                named_by_color[color] = str(raw_name).strip()

        seen_yards: set[int] = set()
        for color, set_num in _CANONICAL_TEES:
            has_geometry = set_num in set_meters or set_num in set_holes
            if not (has_geometry or color in named_by_color):
                continue
            meters = set_meters.get(set_num)
            yards = int(round(meters * 1.09361)) if meters else None
            if yards is not None and yards in seen_yards:
                continue
            if yards is not None:
                seen_yards.add(yards)
            tees_out.append({
                "teeBox": color,
                "name": named_by_color.get(color) or color.title(),
                "set": set_num,
                "yards": yards,
                "holeCount": set_holes.get(set_num, 0),
                "default": False,
            })

    # Neither geometry nor CourseView names → generic long/mid/short tiers (no yardage — honest).
    if not tees_out:
        tees_out = [
            {"teeBox": "black", "name": "长台", "set": 1, "yards": None, "holeCount": 0, "default": False},
            {"teeBox": "white", "name": "中台", "set": 3, "yards": None, "holeCount": 0, "default": False},
            {"teeBox": "red", "name": "短台", "set": 5, "yards": None, "holeCount": 0, "default": False},
        ]

    boxes = [tee["teeBox"] for tee in tees_out]
    default_box = "blue" if "blue" in boxes else min(tees_out, key=lambda tee: tee["set"])["teeBox"]
    for tee in tees_out:
        tee["default"] = tee["teeBox"] == default_box

    return {"defaultTeeBox": default_box, "tees": tees_out}


def _looks_like_tee_start(shot: dict[str, Any]) -> bool:
    lie = str(((shot.get("start") or {}).get("lie")) or "").lower()
    return lie in {"teebox", "tee box", "tee", "teeboxes"}


def _overlay_tee_start(
    first_shot: dict[str, Any],
    selected_tee: dict[str, Any] | None,
) -> tuple[tuple[float, float] | None, str | None]:
    """Return the Tee marker/reference point, without rewriting shot starts."""
    start = (first_shot.get("start") or {}).get("local")
    selected_pos = (selected_tee or {}).get("position")
    start_point = (float(start[0]), float(start[1])) if start else None
    selected_point = (float(selected_pos[0]), float(selected_pos[1])) if selected_pos else None
    if not selected_point:
        return start_point, "shot_start" if start_point else None
    if not start_point:
        return selected_point, "selected_tee"
    if _looks_like_tee_start(first_shot):
        return start_point, "shot_start"
    if math.hypot(start_point[0] - selected_point[0], start_point[1] - selected_point[1]) <= 35.0:
        return start_point, "shot_start"
    return selected_point, "selected_tee_reference"


def _first_recorded_shot_is_from_tee(first_shot: dict[str, Any], selected_tee: dict[str, Any] | None) -> bool:
    return _overlay_tee_start(first_shot, selected_tee)[1] == "shot_start"


@lru_cache(maxsize=128)
def load_geometry(global_id: int, local_hole: int) -> dict[str, Any]:
    h_path = hazard_path(global_id, local_hole)
    m_path = mesh_path(global_id, local_hole)
    hazards = read_json(h_path) if h_path.exists() else None
    meshes = read_json(m_path) if m_path.exists() else None
    hazards = bind_selected_green_target(hazards, meshes)
    components = []
    if meshes:
        by_name = {mesh["name"]: mesh for mesh in meshes.get("meshes", [])}
        for source, kind in FEATURES.items():
            if source not in by_name:
                continue
            for index, comp in enumerate(mesh_components(by_name[source]), start=1):
                components.append({
                    "id": f"{kind}_{index}",
                    "kind": kind,
                    "source": source,
                    "component": index,
                    "area_m2": comp["area_m2"],
                    "bbox": comp["bbox"],
                    "centroid": comp["centroid"],
                    "triangles": comp["triangles"],
                })
    return {
        "hazards": hazards,
        "meshes": meshes,
        "components": components,
        "hasHazards": hazards is not None,
        "hasMeshes": meshes is not None,
    }


def _component_distance(point: tuple[float, float], component: dict[str, Any]) -> float:
    return min(point_triangle_distance(point, tri) for tri in component["triangles"])


def classify_point(point: tuple[float, float], geometry: dict[str, Any]) -> dict[str, Any]:
    distances = []
    for component in geometry["components"]:
        distance_m = _component_distance(point, component)
        distances.append({
            "id": component["id"],
            "kind": component["kind"],
            "source": component["source"],
            "component": component["component"],
            "distance_m": round(distance_m, 1),
            "inside": distance_m <= 0.75,
        })
    distances.sort(key=lambda row: (row["distance_m"], SURFACE_PRIORITY.index(row["kind"]) if row["kind"] in SURFACE_PRIORITY else 99))

    inside = [d for d in distances if d["inside"]]
    surface = None
    for kind in SURFACE_PRIORITY:
        match = next((d for d in inside if d["kind"] == kind), None)
        if match:
            surface = match
            break
    if surface is None and distances:
        surface = distances[0]

    risks = [d for d in distances if d["kind"] in RISK_KINDS and d["distance_m"] <= 25.0]
    return {
        "surface": surface,
        "inside": inside[:5],
        "nearest": distances[:8],
        "nearRisks": risks[:5],
    }


def enrich_shots(hole: dict[str, Any], geometry: dict[str, Any]) -> list[dict[str, Any]]:
    hazards = geometry.get("hazards") or {}
    ref_lat = hazards.get("refLat")
    ref_lon = hazards.get("refLon")
    target = hazards.get("target", {}).get("position")
    rows = []
    for shot in hole["shots"]:
        row = dict(shot)
        for key in ("start", "end"):
            loc = row.get(key)
            if loc and ref_lat is not None and ref_lon is not None:
                local = wgs84_to_local(float(loc["lat"]), float(loc["lon"]), float(ref_lat), float(ref_lon))
                loc["local"] = _round_point(local)
                loc["feature"] = classify_point((local[0], local[1]), geometry) if geometry["components"] else None
        end_local = (row.get("end") or {}).get("local")
        if end_local and target:
            row["remainingToTarget_m"] = round(dist(tuple(end_local), tuple(target)), 1)
        rows.append(row)
    return rows


def _line_risks(start: tuple[float, float], end: tuple[float, float], geometry: dict[str, Any]) -> list[dict[str, Any]]:
    risks = []
    line_length = dist(start, end)
    if line_length <= 0:
        return risks
    for component in geometry["components"]:
        if component["kind"] not in RISK_KINDS:
            continue
        intervals = line_intervals_for_component(start, end, component)
        if intervals:
            risks.append({
                "id": component["id"],
                "kind": component["kind"],
                "crossesLineAt_m": [
                    {"start_m": round(t0 * line_length, 1), "end_m": round(t1 * line_length, 1)}
                    for t0, t1 in intervals[:4]
                ],
            })
    return risks[:8]


def _strategy_reference(analysis: dict[str, Any], geometry: dict[str, Any]) -> tuple[str, tuple[float, float]] | None:
    first = (analysis.get("shots") or [{}])[0]
    start_local = (first.get("start") or {}).get("local")
    if start_local:
        return "第 1 杆起点", (float(start_local[0]), float(start_local[1]))
    tee = _selected_tee(geometry, analysis.get("teeBox"))
    if tee and tee.get("position"):
        pos = tee["position"]
        return f"{analysis.get('teeBox') or 'Tee'} Tee", (float(pos[0]), float(pos[1]))
    return None


def _signed_lateral(point: tuple[float, float], start: tuple[float, float], unit: tuple[float, float]) -> float:
    rel_x = point[0] - start[0]
    rel_y = point[1] - start[1]
    return rel_x * unit[1] - rel_y * unit[0]


def strategy_distances(analysis: dict[str, Any], *, max_labels: int = 9) -> dict[str, Any]:
    """Return strategy-yardage facts for a hole map.

    Distances are calculated in prodgeometry local meters from the first shot
    start when available, otherwise from the first tee. The UI can present the
    same facts in meters or yards.
    """
    ref_lat = analysis.get("geometry", {}).get("refLat")
    ref_lon = analysis.get("geometry", {}).get("refLon")
    target = ((analysis.get("geometry") or {}).get("target") or {}).get("position")
    if ref_lat is None or ref_lon is None or not target:
        return {"status": "missing geometry reference", "labels": []}

    geometry = load_geometry(int(analysis["globalId"]), int(analysis["localHole"]))
    reference = _strategy_reference(analysis, geometry)
    if not reference:
        return {"status": "missing tee/reference", "labels": []}

    reference_label, start = reference
    target_point = (float(target[0]), float(target[1]))
    total = dist(start, target_point)
    if total <= 0:
        return {"status": "invalid target distance", "labels": []}

    unit = ((target_point[0] - start[0]) / total, (target_point[1] - start[1]) / total)

    def to_wgs(local: tuple[float, float]) -> dict[str, float]:
        lat, lon = local_to_wgs84(local[0], local[1], float(ref_lat), float(ref_lon))
        return {"lat": lat, "lon": lon}

    def label_row(
        *,
        row_id: str,
        kind: str,
        label: str,
        local: tuple[float, float],
        carry_m: float,
        priority: float,
        clear_m: float | None = None,
        nearest_m: float | None = None,
        offset_m: float | None = None,
        crosses_line: bool = False,
    ) -> dict[str, Any]:
        pos = to_wgs(local)
        return {
            "id": row_id,
            "kind": kind,
            "label": label,
            "local": _round_point(local),
            "lat": pos["lat"],
            "lon": pos["lon"],
            "carry_m": round(carry_m, 1),
            "clear_m": round(clear_m, 1) if clear_m is not None else None,
            "nearest_m": round(nearest_m, 1) if nearest_m is not None else None,
            "offset_m": round(offset_m, 1) if offset_m is not None else None,
            "crossesLine": crosses_line,
            "priority": priority,
        }

    labels: list[dict[str, Any]] = [
        label_row(
            row_id="target",
            kind="target",
            label="目标",
            local=target_point,
            carry_m=total,
            priority=0,
        )
    ]

    for component in geometry["components"]:
        kind = component["kind"]
        if kind not in STRATEGY_DISTANCE_KINDS:
            continue
        points = _component_points(component)
        if not points:
            continue

        projections = [(p[0] - start[0]) * unit[0] + (p[1] - start[1]) * unit[1] for p in points]
        front = min(projections)
        back = max(projections)
        centroid = (float(component["centroid"][0]), float(component["centroid"][1]))
        offset = _signed_lateral(centroid, start, unit)
        min_abs_offset = min(abs(_signed_lateral(p, start, unit)) for p in points)

        if back < -8.0 or front > total + 45.0:
            continue
        if min_abs_offset > 58.0 and kind != "green":
            continue

        intervals = line_intervals_for_component(start, target_point, component)
        line_interval = next((row for row in intervals if row[1] * total >= 0.0 and row[0] * total <= total), None)
        nearest = _component_distance(start, component)

        if line_interval:
            carry = max(0.0, line_interval[0] * total)
            clear = max(carry, line_interval[1] * total)
            point = (start[0] + unit[0] * carry, start[1] + unit[1] * carry)
            label = "果岭前" if kind == "green" else KIND_CN.get(kind, kind)
            priority = {"water": 1, "bunker": 2, "green": 3, "tree_area": 4}.get(kind, 8)
            labels.append(label_row(
                row_id=component["id"],
                kind=kind,
                label=label,
                local=point,
                carry_m=carry,
                clear_m=clear,
                nearest_m=nearest,
                offset_m=0.0,
                crosses_line=True,
                priority=priority,
            ))
        else:
            carry = max(0.0, min(front, dist(start, centroid)))
            if kind == "green":
                label = "果岭前"
                priority = 3.5
            elif kind == "bunker":
                label = "沙坑"
                priority = 4.0 + min_abs_offset / 100.0
            elif kind == "water":
                label = "水障碍"
                priority = 3.0 + min_abs_offset / 100.0
            else:
                label = KIND_CN.get(kind, kind)
                priority = 5.5 + min_abs_offset / 100.0
            labels.append(label_row(
                row_id=component["id"],
                kind=kind,
                label=label,
                local=centroid,
                carry_m=carry,
                clear_m=max(carry, back),
                nearest_m=nearest,
                offset_m=offset,
                crosses_line=False,
                priority=priority,
            ))

    labels.sort(key=lambda row: (row["priority"], row["carry_m"]))
    target_label = labels[0:1]
    other_labels = labels[1:max_labels]
    reference_wgs = to_wgs(start)
    target_wgs = to_wgs(target_point)
    return {
        "status": "ok",
        "reference": {
            "label": reference_label,
            "local": _round_point(start),
            "lat": reference_wgs["lat"],
            "lon": reference_wgs["lon"],
        },
        "target": {
            "label": "目标",
            "local": _round_point(target_point),
            "lat": target_wgs["lat"],
            "lon": target_wgs["lon"],
            "distance_m": round(total, 1),
        },
        "labels": target_label + other_labels,
        "unitSource": "meters",
    }


def candidate_routes(hole: dict[str, Any], shots: list[dict[str, Any]], geometry: dict[str, Any], club_profiles: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    hazards = geometry.get("hazards") or {}
    target = hazards.get("target", {}).get("position")
    if not target:
        return []
    first = shots[0] if shots else None
    start_local = (first or {}).get("start", {}).get("local")
    if not start_local:
        tees = hazards.get("tees") or []
        # P2: tees is not pre-filtered for "position" here (unlike the selected-tee paths), so a tee
        # row without a position must degrade to None, not KeyError out of the whole route build.
        start_local = tees[0].get("position") if tees else None
    if not start_local:
        return []
    start = tuple(start_local)
    target_point = tuple(target)
    total = dist(start, target_point)
    if total <= 0:
        return []

    unit = ((target_point[0] - start[0]) / total, (target_point[1] - start[1]) / total)

    actual_club = (first or {}).get("clubName") if first else None
    actual_profile = club_profiles.get(actual_club or "")
    stock_distance = actual_profile["median"] if actual_profile else min(210.0, total * 0.75)

    candidates = [
        ("conservative_layup", "保守 layup", min(170.0, max(80.0, total * 0.55))),
        ("stock_line", f"{actual_club or 'Stock'} 常规线", min(float(stock_distance), max(80.0, total - 25.0))),
        ("aggressive_line", "进攻线", min(total, max(100.0, total * 0.88))),
    ]

    rows = []
    for cid, label, carry in candidates:
        landing = (start[0] + unit[0] * carry, start[1] + unit[1] * carry)
        landing_class = classify_point(landing, geometry) if geometry["components"] else {"surface": None, "nearRisks": []}
        risks = landing_class.get("nearRisks", [])
        line_risks = _line_risks(start, landing, geometry)
        score = len(risks) * 2 + len(line_risks)
        surface = landing_class.get("surface") or {}
        if surface.get("kind") not in GOOD_SURFACES:
            score += 1
        rows.append({
            "id": cid,
            "label": label,
            "carry_m": round(carry, 1),
            "landingLocal": _round_point(landing),
            "expectedSurface": surface,
            "nearRisks": risks,
            "lineRisks": line_risks,
            "riskScore": score,
            "recommendation": "preferred" if score == 0 else "watch",
        })
    rows.sort(key=lambda r: (r["riskScore"], -r["carry_m"]))
    if rows:
        rows[0]["recommendation"] = "preferred"
    return rows


def data_quality(hole: dict[str, Any], shots: list[dict[str, Any]], geometry: dict[str, Any], club_profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    issues = []
    if not geometry["hasHazards"]:
        issues.append("missing prodgeometry hazard index")
    if not geometry["hasMeshes"]:
        issues.append("missing decoded mesh JSON; feature hit tests are unavailable")
    if not shots:
        issues.append("no shots on this hole")
    elif not _first_recorded_shot_is_from_tee(shots[0], _selected_tee(geometry, hole.get("teeBox"))):
        issues.append("Garmin tee shot not recorded; first recorded shot starts after tee")
    for shot in shots:
        if not shot.get("start") or not shot.get("end"):
            issues.append(f"shot {shot.get('shotOrder')} missing start/end location")
        profile = club_profiles.get(shot.get("clubName") or "")
        if not profile or profile["sampleSize"] < 10:
            issues.append(f"club sample low for {shot.get('clubName') or 'Unknown'}")
    confidence = "high"
    if issues:
        confidence = "medium" if geometry["hasHazards"] and geometry["hasMeshes"] else "low"
    return {"confidence": confidence, "issues": sorted(set(issues))}


def rule_review(analysis: dict[str, Any]) -> str:
    shots = analysis["shots"]
    candidates = analysis["candidateRoutes"]
    quality = analysis["dataQuality"]
    kind_cn = {
        "fairway": "球道",
        "green": "果岭",
        "rough": "长草",
        "bunker": "沙坑",
        "water": "水障碍",
        "water_edge": "水障碍边缘",
        "tree_area": "树林",
        "teebox": "Tee 台",
        "playable_bounds": "可打边界",
    }
    confidence_cn = {"high": "高", "medium": "中", "low": "低"}.get(quality["confidence"], quality["confidence"])
    lines = [
        f"{analysis['courseName']}第 {analysis['hole']} 洞：数据置信度 {confidence_cn}。",
    ]
    if shots:
        first = shots[0]
        first_from_tee = _first_recorded_shot_is_from_tee(
            first,
            _selected_tee(load_geometry(int(analysis["globalId"]), int(analysis["localHole"])), analysis.get("teeBox")),
        )
        surface = ((first.get("end") or {}).get("feature") or {}).get("surface") or {}
        surface_text = kind_cn.get(surface.get("kind"), (first.get("end") or {}).get("lie") or "未知区域")
        remain = first.get("remainingToTarget_m")
        remain_text = f"剩余目标约 {remain} 米" if remain is not None else "剩余距离暂时无法计算"
        shot_label = "开球" if first_from_tee else "记录的第 1 杆"
        if not first_from_tee:
            start_lie_raw = (first.get("start") or {}).get("lie") or "未知位置"
            start_lie = kind_cn.get(str(start_lie_raw).lower(), str(start_lie_raw))
            lines.append(f"Garmin 没有记录 Tee 台发球；当前回放从{start_lie}开始。")
        lines.append(
            f"{shot_label}用 {first.get('clubName') or '未知球杆'}，落在{surface_text}，{remain_text}。"
        )
        risks = ((first.get("end") or {}).get("feature") or {}).get("nearRisks") or []
        if risks:
            risk_text = "，".join(f"{kind_cn.get(r['kind'], r['kind'])} {r['distance_m']} 米" for r in risks[:3])
            lines.append(f"{shot_label}落点附近主要风险：{risk_text}。")
    if candidates:
        best = candidates[0]
        lines.append(
            f"当前规则模型给出的低风险候选是「{best['label']}」，目标 carry 约 {best['carry_m']} 米，风险分 {best['riskScore']}。"
        )
    if quality["issues"]:
        issue_cn = {
            "Garmin tee shot not recorded; first recorded shot starts after tee": "缺 Tee 台发球记录",
            "missing prodgeometry hazard index": "缺 prodgeometry 障碍索引",
            "missing decoded mesh JSON; feature hit tests are unavailable": "缺 decoded mesh JSON，无法做 feature 命中判断",
            "no shots on this hole": "本洞没有击球记录",
        }
        lines.append("还需要补的数据：" + "；".join(issue_cn.get(issue, issue) for issue in quality["issues"][:4]) + "。")
    return " ".join(lines)


def llm_brief(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": "Write a concise Chinese golf hole review. Use only the facts in this JSON. Do not infer unobserved weather, intent, or private data.",
        "facts": {
            "courseName": analysis["courseName"],
            "hole": analysis["hole"],
            "globalId": analysis["globalId"],
            "localHole": analysis["localHole"],
            "shots": [
                {
                    "order": s.get("shotOrder"),
                    "club": clean_club_name(s.get("clubName")),
                    "type": s.get("shotType"),
                    "meters": s.get("meters"),
                    "endLie": (s.get("end") or {}).get("lie"),
                    "endFeature": (((s.get("end") or {}).get("feature") or {}).get("surface") or {}).get("kind"),
                    "remainingToTarget_m": s.get("remainingToTarget_m"),
                    "nearRisks": ((s.get("end") or {}).get("feature") or {}).get("nearRisks", [])[:3],
                }
                for s in analysis["shots"]
            ],
            "candidateRoutes": analysis["candidateRoutes"][:3],
            "dataQuality": analysis["dataQuality"],
            "decision": {
                "selectedOptionId": (analysis.get("decisionPlan") or {}).get("selectedOptionId"),
                "selectedOption": (analysis.get("decisionPlan") or {}).get("selectedOption"),
                "confidence": (analysis.get("decisionPlan") or {}).get("confidence"),
                "failureType": (analysis.get("decisionOutcome") or {}).get("failureType"),
                "outcome": analysis.get("decisionOutcome"),
            },
        },
    }


def build_hole_analysis(
    *,
    scorecard_id: int | str | None = None,
    manual_round_id: str | None = None,
    hole_number: int,
    ensure_geometry: bool = False,
    write_outputs: bool = False,
) -> dict[str, Any]:
    if scorecard_id is None and manual_round_id is None:
        raise ValueError("scorecard_id or manual_round_id is required")
    if scorecard_id is not None:
        hole = normalize_garmin_hole(scorecard_id, hole_number)
    else:
        hole = normalize_manual_hole(str(manual_round_id), hole_number)
    if hole["globalId"] is None:
        raise ValueError("hole has no globalId")

    geometry_sync: dict[str, Any] | None = None
    if ensure_geometry:
        from ai_caddie.geometry.geometry_sync import ensure_prodgeometry

        geometry_sync = ensure_prodgeometry(int(hole["globalId"]), int(hole["localHole"]))
        if geometry_sync.get("ok"):
            load_geometry.cache_clear()

    geometry = load_geometry(int(hole["globalId"]), int(hole["localHole"]))
    club_profiles = build_club_profiles()
    shots = enrich_shots(hole, geometry)
    candidates = candidate_routes(hole, shots, geometry, club_profiles)
    quality = data_quality(hole, shots, geometry, club_profiles)
    pin = dict(hole.get("pin") or {})
    ref_lat = (geometry.get("hazards") or {}).get("refLat")
    ref_lon = (geometry.get("hazards") or {}).get("refLon")
    if pin.get("lat") is not None and pin.get("lon") is not None and ref_lat is not None and ref_lon is not None:
        local = wgs84_to_local(float(pin["lat"]), float(pin["lon"]), float(ref_lat), float(ref_lon))
        pin["local"] = _round_point(local)
        pin["feature"] = classify_point((local[0], local[1]), geometry) if geometry["components"] else None
    relevant_profiles = {
        name: club_profiles[name]
        for name in sorted({s.get("clubName") for s in shots if s.get("clubName")} & set(club_profiles))
    }
    analysis = {
        "schema": "ai-caddie-hole-analysis-v1",
        "roundId": hole["id"],
        "source": hole["source"],
        "courseName": hole["courseName"],
        "date": hole.get("date"),
        "hole": hole["hole"],
        "globalId": hole["globalId"],
        "localHole": hole["localHole"],
        "teeBox": hole.get("teeBox"),
        "strokes": hole.get("strokes"),
        "putts": hole.get("putts"),
        "penalties": hole.get("penalties"),
        "fairwayShotOutcome": hole.get("fairwayShotOutcome"),
        "pin": pin or None,
        "holeImageUrl": hole.get("holeImageUrl"),
        "geometry": {
            "hasHazards": geometry["hasHazards"],
            "hasMeshes": geometry["hasMeshes"],
            "refLat": (geometry.get("hazards") or {}).get("refLat"),
            "refLon": (geometry.get("hazards") or {}).get("refLon"),
            "target": (geometry.get("hazards") or {}).get("target"),
            "hazardCount": len((geometry.get("hazards") or {}).get("hazards", [])),
        },
        "geometrySync": geometry_sync,
        "rasterPixelSource": next(
            (s.get("pixelSource") or "garmin-shot-map" for s in shots if (
                ((s.get("start") or {}).get("x") is not None and (s.get("start") or {}).get("y") is not None)
                or ((s.get("end") or {}).get("x") is not None and (s.get("end") or {}).get("y") is not None)
            )),
            None,
        ),
        "shots": shots,
        "clubProfiles": relevant_profiles,
        "candidateRoutes": candidates,
        "dataQuality": quality,
    }
    analysis["decisionPlan"] = build_decision_plan(analysis)
    analysis["decisionOutcome"] = judge_decision_outcome(analysis["decisionPlan"], analysis)
    analysis["review"] = rule_review(analysis)
    analysis["llmBrief"] = llm_brief(analysis)

    if write_outputs:
        stem = f"{analysis['source']}_{analysis['roundId']}_h{int(hole_number):02d}"
        write_json(ANALYSIS_OUT / f"{stem}_analysis.json", analysis)
        (ANALYSIS_OUT / f"{stem}_overlay.svg").write_text(render_svg(analysis))
    return analysis


def _component_points(component: dict[str, Any]) -> list[tuple[float, float]]:
    pts = []
    seen = set()
    for tri in component["triangles"]:
        for p in tri:
            key = (round(p[0], 3), round(p[1], 3))
            if key not in seen:
                pts.append((float(p[0]), float(p[1])))
                seen.add(key)
    return pts


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _local_overlay_frame(
    points: list[tuple[float, float]],
    tee_point: tuple[float, float] | None,
    target_point: tuple[float, float] | None,
) -> dict[str, Any] | None:
    if not points or not tee_point or not target_point:
        return None
    dx = target_point[0] - tee_point[0]
    dy = target_point[1] - tee_point[1]
    length = math.hypot(dx, dy)
    if length < 1.0:
        ux, uy = 1.0, 0.0
        vx, vy = 0.0, 1.0
    else:
        vx, vy = -dx / length, -dy / length
        ux, uy = dy / length, -dx / length

    def rot(point: tuple[float, float]) -> tuple[float, float]:
        nx = point[0] - tee_point[0]
        ny = point[1] - tee_point[1]
        return nx * ux + ny * uy, nx * vx + ny * vy

    rotated = [rot(point) for point in points]
    min_x, max_x = min(p[0] for p in rotated), max(p[0] for p in rotated)
    min_y, max_y = min(p[1] for p in rotated), max(p[1] for p in rotated)
    return {
        "tee": _round_point(tee_point),
        "target": _round_point(target_point),
        "minX": round(min_x, 2),
        "maxX": round(max_x, 2),
        "minY": round(min_y, 2),
        "maxY": round(max_y, 2),
    }


def render_svg(analysis: dict[str, Any]) -> str:
    geometry = load_geometry(int(analysis["globalId"]), int(analysis["localHole"]))
    all_points: list[tuple[float, float]] = []
    selected_tee = _selected_tee(geometry, analysis.get("teeBox"))
    selected_tee_pos = selected_tee.get("position") if selected_tee else None

    # Collect all points for bounding box and rotation
    for component in geometry["components"]:
        if component["kind"] not in COLORS:
            continue
        for tri in component["triangles"]:
            for p in tri:
                all_points.append((float(p[0]), float(p[1])))

    shot_points = []
    for shot in analysis.get("shots", []):
        for key in ("start", "end"):
            local = (shot.get(key) or {}).get("local")
            if local:
                shot_points.append((float(local[0]), float(local[1])))
                all_points.append((float(local[0]), float(local[1])))

    if selected_tee_pos:
        all_points.append((float(selected_tee_pos[0]), float(selected_tee_pos[1])))

    target = (analysis.get("geometry", {}).get("target") or {}).get("position")
    if target:
        all_points.append((float(target[0]), float(target[1])))
    pin_local = (analysis.get("pin") or {}).get("local")
    if pin_local:
        all_points.append((float(pin_local[0]), float(pin_local[1])))

    # Also collect foliage points
    meshes = geometry.get("meshes") or {}
    foliage_data = meshes.get("foliage") or {}
    for f_type in ["trees", "foliage", "rocks"]:
        for item in foliage_data.get(f_type) or []:
            all_points.append((-float(item["x"]), float(item["z"])))

    if not all_points:
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 640" style="background:#80b3ff; border-radius:12px;"></svg>'

    # Auto-rotation: Tee at bottom, Target at top
    first_shot = (analysis.get("shots") or [{}])[0]
    first_start = (first_shot.get("start") or {}).get("local")
    tee_start, tee_source = _overlay_tee_start(first_shot, selected_tee)
    if tee_start:
        tee_pt = tee_start
    elif shot_points:
        tee_pt = shot_points[0]
    else:
        tee_pt = all_points[0] if all_points else (0, 0)
    target_pt = (float(target[0]), float(target[1])) if target else (
        sum(p[0] for p in all_points) / len(all_points),
        sum(p[1] for p in all_points) / len(all_points)
    )

    dx = target_pt[0] - tee_pt[0]
    dy = target_pt[1] - tee_pt[1]
    L = math.hypot(dx, dy)

    if L < 1.0:
        ux, uy = 1.0, 0.0
        vx, vy = 0.0, 1.0
    else:
        vx, vy = -dx / L, -dy / L
        ux, uy = dy / L, -dx / L

    def rot(x: float, y: float) -> tuple[float, float]:
        nx = x - tee_pt[0]
        ny = y - tee_pt[1]
        return nx * ux + ny * uy, nx * vx + ny * vy

    rotated_pts = [rot(x, y) for x, y in all_points]
    min_x, max_x = min(p[0] for p in rotated_pts), max(p[0] for p in rotated_pts)
    min_y, max_y = min(p[1] for p in rotated_pts), max(p[1] for p in rotated_pts)

    pad = 40
    width = max(1.0, max_x - min_x) + 2 * pad
    height = max(1.0, max_y - min_y) + 2 * pad

    def svg_p(x: float, y: float) -> tuple[float, float]:
        rx, ry = rot(x, y)
        return rx - min_x + pad, ry - min_y + pad

    # Garmin-like rich palette
    VIVID_COLORS = {
        "playable_bounds": "none",
        "rough": "#8eb072",
        "tree_area": "#77965b",
        "fairway": "url(#fairway-pattern)", # using pattern
        "water": "#4da6ff",
        "water_edge": "#3b82f6",
        "teebox": "#a3d977",
        "bunker": "#e6d596",
        "green": "#79c968",
    }

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" '
        f'style="width:100%; height:auto; max-height:85vh; border-radius:12px; background:#90c2f9; '
        f'box-shadow: inset 0 2px 10px rgba(0,0,0,0.05); font-family: system-ui, -apple-system, sans-serif;">',
        f'<defs>',
        f'<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">',
        f'<feDropShadow dx="1" dy="2" stdDeviation="2" flood-color="#000000" flood-opacity="0.3"/>',
        f'</filter>',
        f'<filter id="tree-shadow" x="-30%" y="-30%" width="160%" height="160%">',
        f'<feDropShadow dx="2" dy="3" stdDeviation="1.5" flood-color="#000000" flood-opacity="0.4"/>',
        f'</filter>',
        # Fairway diagonal stripes
        f'<pattern id="fairway-pattern" width="12" height="12" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">',
        f'<rect width="12" height="12" fill="#a1d374"/>',
        f'<line x1="0" y1="0" x2="0" y2="12" stroke="#95ca65" stroke-width="6"/>',
        f'</pattern>',
        # Tree 3D gradients
        f'<radialGradient id="tree-grad" cx="30%" cy="30%" r="70%">',
        f'<stop offset="0%" stop-color="#5fa33f"/>',
        f'<stop offset="70%" stop-color="#3b7022"/>',
        f'<stop offset="100%" stop-color="#1e400e"/>',
        f'</radialGradient>',
        f'<radialGradient id="bush-grad" cx="30%" cy="30%" r="70%">',
        f'<stop offset="0%" stop-color="#79c251"/>',
        f'<stop offset="70%" stop-color="#53962f"/>',
        f'<stop offset="100%" stop-color="#316117"/>',
        f'</radialGradient>',
        f'</defs>',
    ]

    # Fixed Z-order: rough is at the bottom, then tree_area, fairway, water, teebox, bunker, green
    order = {"playable_bounds":-1, "rough":0, "tree_area":1, "fairway":2, "water":3, "water_edge":4, "teebox":5, "bunker":6, "green":7}

    # Group triangles by kind to optimize SVG size
    kind_paths = {k: [] for k in VIVID_COLORS}
    for component in geometry["components"]:
        kind = component["kind"]
        if kind not in VIVID_COLORS or kind == "playable_bounds":
            continue
        for tri in component["triangles"]:
            p1, p2, p3 = [svg_p(p[0], p[1]) for p in tri]
            kind_paths[kind].append(f"M {p1[0]:.1f},{p1[1]:.1f} L {p2[0]:.1f},{p2[1]:.1f} L {p3[0]:.1f},{p3[1]:.1f} Z")

    for kind in sorted(kind_paths.keys(), key=lambda k: order.get(k, 99)):
        if not kind_paths[kind]:
            continue
        fill = VIVID_COLORS[kind]
        stroke = fill if kind != "fairway" else "none"
        parts.append(f'<path d="{" ".join(kind_paths[kind])}" fill="{fill}" stroke="{stroke}" stroke-width="0.5" />')

    # Draw trees with much smaller scale and 3D gradient
    for f_type, grad, r_scale in [("trees", "url(#tree-grad)", 0.6), ("foliage", "url(#bush-grad)", 0.3)]:
        for item in foliage_data.get(f_type) or []:
            tx, ty = svg_p(-float(item["x"]), float(item["z"]))
            r = max(0.5, float(item.get("s", 1.0)) * r_scale)
            parts.append(f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="{r:.1f}" fill="{grad}" filter="url(#tree-shadow)"/>')

    # Draw shot lines first
    shots = analysis.get("shots", [])
    def route_start_for(shot: dict[str, Any], index: int) -> list[float] | tuple[float, float] | None:
        return (shot.get("start") or {}).get("local")

    for i, shot in enumerate(shots):
        start = route_start_for(shot, i)
        end = (shot.get("end") or {}).get("local")
        if start and end:
            sx, sy = svg_p(start[0], start[1])
            ex, ey = svg_p(end[0], end[1])
            parts.append(
                f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
                f'stroke="#ffffff" stroke-width="3.5" filter="url(#shadow)"/>'
            )

    def shot_color(order):
        if order == 1: return "#fef08a" # Tee (Yellow)
        if order == 2: return "#cbd5e1" # 2nd (Grey)
        if order == 3: return "#fdba74" # Approach (Orange)
        return "#a78bfa" # Putt (Purple)

    for i, shot in enumerate(shots):
        start = route_start_for(shot, i)
        end = (shot.get("end") or {}).get("local")
        if not (start and end):
            continue

        sx, sy = svg_p(start[0], start[1])
        order = int(shot.get("shotOrder", i + 1))
        color = shot_color(order)

        meters = shot.get("meters", 0)
        yards = int(meters * 1.09361) if meters else 0

        # Determine label text
        is_putt = shot.get("shotType") in ("PUTT", "PENALTY_PUTT", "UNKNOWN") and shot.get("start", {}).get("lie") == "Green"
        if is_putt:
            # Count remaining putts from this shot onwards
            putts = sum(1 for s in shots[i:] if s.get("shotType") in ("PUTT", "PENALTY_PUTT", "UNKNOWN") and s.get("start", {}).get("lie") == "Green")
            if putts == 0: putts = 1
            label = f"{putts} 次推杆"
        else:
            label = f"{yards} 码"

        # Alternate left (-40) and right (+40) based on index
        point_left = (i % 2 != 0)
        if is_putt:
            point_left = True # Prefer pointing left for putts on the green

        box_x = -80 if point_left else 0
        text_x = -40 if point_left else 40

        parts.append(
            f'<g transform="translate({sx:.1f}, {sy:.1f})" filter="url(#shadow)">'
            f'<rect x="{box_x}" y="-14" width="80" height="28" rx="14" fill="#1f2937" fill-opacity="0.85" stroke="#ffffff" stroke-opacity="0.6" stroke-width="2.5"/>'
            f'<text x="{text_x}" y="5" font-size="13" font-weight="500" fill="#ffffff" text-anchor="middle">{label}</text>'
            f'<circle cx="0" cy="0" r="12" fill="#1f2937" fill-opacity="0.85" stroke="#ffffff" stroke-opacity="0.6" stroke-width="2.5"/>'
            f'<circle cx="0" cy="0" r="5" fill="{color}"/>'
            f'</g>'
        )

    tee_marker_pos = tee_start or first_start or selected_tee_pos
    if tee_marker_pos:
        tx, ty = svg_p(tee_marker_pos[0], tee_marker_pos[1])
        parts.append(
            f'<g transform="translate({tx:.1f}, {ty:.1f})" filter="url(#shadow)">'
            f'<circle cx="0" cy="0" r="12" fill="#1f2937" fill-opacity="0.82" stroke="#ffffff" stroke-width="2.5"/>'
            f'<circle cx="0" cy="0" r="7" fill="#2563eb"/>'
            f'<text x="0" y="4" font-size="10" font-weight="800" fill="#ffffff" text-anchor="middle">T</text>'
            f'</g>'
        )

    if target:
        tx, ty = svg_p(target[0], target[1])
        parts.append(
            f'<g transform="translate({tx:.1f}, {ty:.1f})" filter="url(#shadow)">'
            f'<path d="M 0,-4 L 12,-10 L 0,-16 Z M 0,6 L 0,-16" stroke="#ef4444" fill="#ef4444" stroke-width="2"/>'
            f'<circle cx="0" cy="0" r="12" fill="#1f2937" fill-opacity="0.85" stroke="#ffffff" stroke-opacity="0.6" stroke-width="2.5"/>'
            f'<circle cx="0" cy="0" r="4" fill="#ef4444"/>'
            f'</g>'
        )

    putts = analysis.get("putts")
    putt_local = pin_local or target
    if putts is not None and putt_local:
        px, py = svg_p(putt_local[0], putt_local[1])
        putt_label = html.escape(f"{putts} 次推杆")
        parts.append(
            f'<g transform="translate({px:.1f}, {py:.1f})" filter="url(#shadow)">'
            f'<rect x="-82" y="-14" width="82" height="28" rx="14" fill="#1f2937" fill-opacity="0.86" stroke="#ffffff" stroke-opacity="0.65" stroke-width="2.5"/>'
            f'<text x="-41" y="5" font-size="13" font-weight="600" fill="#ffffff" text-anchor="middle">{putt_label}</text>'
            f'<circle cx="0" cy="0" r="12" fill="#1f2937" fill-opacity="0.86" stroke="#ffffff" stroke-opacity="0.65" stroke-width="2.5"/>'
            f'<circle cx="0" cy="0" r="5" fill="#7c3aed"/>'
            f'</g>'
        )

    course_name = html.escape(str(analysis.get("courseName", "Unknown Course")))
    hole_num = analysis.get("hole", "?")
    parts.append(
        f'<g transform="translate(15, 30)">'
        f'<text x="0" y="0" font-size="18" font-weight="800" fill="#1e293b" filter="url(#shadow)">{course_name}</text>'
        f'<text x="0" y="20" font-size="14" font-weight="600" fill="#334155" filter="url(#shadow)">HOLE {hole_num}</text>'
        f'</g>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def overlay_geojson(analysis: dict[str, Any]) -> dict[str, Any]:
    """Return WGS84 GeoJSON for satellite-map overlay.

    The browser uses this for a visually normal north-up comparison against
    satellite imagery. The existing SVG stays in prodgeometry local meters.
    """
    ref_lat = analysis.get("geometry", {}).get("refLat")
    ref_lon = analysis.get("geometry", {}).get("refLon")
    if ref_lat is None or ref_lon is None:
        return {
            "type": "FeatureCollection",
            "features": [],
            "bounds": None,
            "status": "missing geometry reference",
        }

    geometry = load_geometry(int(analysis["globalId"]), int(analysis["localHole"]))
    features: list[dict[str, Any]] = []
    bounds_points: list[tuple[float, float]] = []
    focus_points: list[tuple[float, float]] = []
    local_points: list[tuple[float, float]] = []
    focus_kinds = {"fairway", "green", "bunker", "water", "water_edge", "teebox"}

    def point_from_local(point: list[float] | tuple[float, float]) -> tuple[float, float]:
        lat, lon = local_to_wgs84(float(point[0]), float(point[1]), float(ref_lat), float(ref_lon))
        return lon, lat

    selected_tee = _selected_tee(geometry, analysis.get("teeBox"))
    first_shot = (analysis.get("shots") or [{}])[0]
    tee_local, tee_source = _overlay_tee_start(first_shot, selected_tee)
    target = (analysis.get("geometry") or {}).get("target") or {}
    target_local = tuple(float(v) for v in target["position"]) if target.get("position") else None

    for component in geometry["components"]:
        if component["kind"] not in COLORS:
            continue
        component_points = _component_points(component)
        local_points.extend(component_points)
        hull = _convex_hull(component_points)
        if len(hull) < 3:
            continue
        ring = [point_from_local(point) for point in hull]
        ring.append(ring[0])
        bounds_points.extend(ring)
        if component["kind"] in focus_kinds:
            focus_points.extend(ring)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "layer": "geometry",
                "kind": component["kind"],
                "id": component["id"],
                "source": component["source"],
                "localRing": [_round_point(point) for point in hull] + [_round_point(hull[0])],
                "localTriangles": [
                    [_round_point(point) for point in tri]
                    for tri in component["triangles"]
                ] if component["kind"] in (focus_kinds | {"rough", "tree_area"}) else None,
            },
        })

    if tee_local:
        tee_lon, tee_lat = point_from_local(tee_local)
        bounds_points.append((tee_lon, tee_lat))
        focus_points.append((tee_lon, tee_lat))
        local_points.append(tee_local)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [tee_lon, tee_lat]},
            "properties": {
                "layer": "tee",
                "kind": "tee",
                "teeBox": analysis.get("teeBox"),
                "local": _round_point(tee_local),
                "source": tee_source,
            },
        })

    previous_end: dict[str, Any] | None = None
    for index, shot in enumerate(analysis.get("shots", [])):
        start = shot.get("start")
        end = shot.get("end")
        start_coord = None
        start_local = (start or {}).get("local")
        start_source = "shot"
        if start and start.get("lat") is not None and start.get("lon") is not None:
            start_coord = (float(start["lon"]), float(start["lat"]))
        elif previous_end:
            start_coord = previous_end.get("coord")
            start_local = previous_end.get("local")
            start_source = "previous_end"

        if end and end.get("lat") is not None and end.get("lon") is not None:
            end_coord = (float(end["lon"]), float(end["lat"]))
            end_local = (end or {}).get("local")
            if end_local:
                local_points.append((float(end_local[0]), float(end_local[1])))
            if start_local:
                local_points.append((float(start_local[0]), float(start_local[1])))
            previous_end = {"coord": end_coord, "local": end_local}
        else:
            end_coord = None

        if start_coord and end_coord:
            coords = [
                [float(start_coord[0]), float(start_coord[1])],
                [float(end_coord[0]), float(end_coord[1])],
            ]
            bounds_points.extend((tuple(coords[0]), tuple(coords[1])))
            focus_points.extend((tuple(coords[0]), tuple(coords[1])))
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "layer": "shot",
                    "order": shot.get("shotOrder"),
                    "club": clean_club_name(shot.get("clubName")),
                    "meters": shot.get("meters"),
                    "type": shot.get("shotType"),
                    "startLie": (start or {}).get("lie"),
                    "endLie": (end or {}).get("lie"),
                    "startLocal": _round_point(start_local),
                    "endLocal": _round_point(end_local),
                    "startPixel": (
                        {"x": float(start["x"]), "y": float(start["y"])}
                        if start and start.get("x") is not None and start.get("y") is not None
                        else None
                    ),
                    "endPixel": (
                        {"x": float(end["x"]), "y": float(end["y"])}
                        if end and end.get("x") is not None and end.get("y") is not None
                        else None
                    ),
                    "startSource": start_source,
                },
            })
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": coords[1]},
                "properties": {
                    "layer": "shot_end",
                    "order": shot.get("shotOrder"),
                    "club": clean_club_name(shot.get("clubName")),
                    "lie": (end or {}).get("lie"),
                    "local": _round_point(end_local),
                    "pixel": (
                        {"x": float(end["x"]), "y": float(end["y"])}
                        if end and end.get("x") is not None and end.get("y") is not None
                        else None
                    ),
                },
            })
        elif end_coord:
            coord = [float(end_coord[0]), float(end_coord[1])]
            bounds_points.append(tuple(coord))
            focus_points.append(tuple(coord))
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": coord},
                "properties": {
                    "layer": "shot_end",
                    "order": shot.get("shotOrder"),
                    "club": clean_club_name(shot.get("clubName")),
                    "lie": (end or {}).get("lie"),
                    "local": _round_point((end or {}).get("local")),
                },
            })

    if target_local:
        lon, lat = point_from_local(target_local)
        bounds_points.append((lon, lat))
        focus_points.append((lon, lat))
        local_points.append(target_local)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"layer": "target", "kind": "target", "local": _round_point(target_local)},
        })

    pin = analysis.get("pin") or {}
    if pin.get("lat") is not None and pin.get("lon") is not None:
        pin_coord = (float(pin["lon"]), float(pin["lat"]))
        bounds_points.append(pin_coord)
        focus_points.append(pin_coord)
        pin_local = pin.get("local")
        if pin_local:
            local_points.append((float(pin_local[0]), float(pin_local[1])))
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [pin_coord[0], pin_coord[1]]},
            "properties": {
                "layer": "pin",
                "kind": "pin",
                "putts": analysis.get("putts"),
                "local": _round_point(pin_local),
            },
        })

    def bounds_for(points: list[tuple[float, float]]) -> dict[str, float] | None:
        if not points:
            return None
        lons = [p[0] for p in points]
        lats = [p[1] for p in points]
        return {
            "south": min(lats),
            "west": min(lons),
            "north": max(lats),
            "east": max(lons),
        }

    bounds = bounds_for(bounds_points)
    focus_bounds = bounds_for(focus_points) or bounds
    return {
        "type": "FeatureCollection",
        "features": features,
        "bounds": bounds,
        "focusBounds": focus_bounds,
        "localFrame": _local_overlay_frame(local_points, tee_local, target_local),
        "putts": analysis.get("putts"),
        "status": "ok",
    }


def save_analysis_artifacts(analysis: dict[str, Any]) -> dict[str, str]:
    stem = f"{analysis['source']}_{analysis['roundId']}_h{int(analysis['hole']):02d}"
    json_path = ANALYSIS_OUT / f"{stem}_analysis.json"
    svg_path = ANALYSIS_OUT / f"{stem}_overlay.svg"
    write_json(json_path, analysis)
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(render_svg(analysis))
    return {"analysis": str(json_path), "overlay": str(svg_path)}


def _hole_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    risks = []
    for shot in analysis.get("shots", []):
        for risk in ((shot.get("end") or {}).get("feature") or {}).get("nearRisks", [])[:2]:
            risks.append({
                "shotOrder": shot.get("shotOrder"),
                "kind": risk.get("kind"),
                "distance_m": risk.get("distance_m"),
            })
    first = (analysis.get("shots") or [{}])[0]
    first_surface = (((first.get("end") or {}).get("feature") or {}).get("surface") or {}).get("kind")
    first_from_tee = _first_recorded_shot_is_from_tee(
        first,
        _selected_tee(load_geometry(int(analysis["globalId"]), int(analysis["localHole"])), analysis.get("teeBox")),
    )
    return {
        "hole": analysis["hole"],
        "globalId": analysis["globalId"],
        "localHole": analysis["localHole"],
        "confidence": analysis["dataQuality"]["confidence"],
        "hasGeometry": bool(analysis["geometry"]["hasHazards"] and analysis["geometry"]["hasMeshes"]),
        "shotCount": len(analysis.get("shots", [])),
        "teeShotRecorded": first_from_tee,
        "teeShotClub": first.get("clubName") if first_from_tee else None,
        "teeShotMeters": first.get("meters") if first_from_tee else None,
        "teeShotSurface": first_surface or (first.get("end") or {}).get("lie") if first_from_tee else None,
        "firstRecordedClub": first.get("clubName"),
        "firstRecordedMeters": first.get("meters"),
        "firstRecordedSurface": first_surface or (first.get("end") or {}).get("lie"),
        "risks": risks[:4],
        "bestRoute": (analysis.get("candidateRoutes") or [{}])[0],
        "decision": {
            "selectedOptionId": (analysis.get("decisionPlan") or {}).get("selectedOptionId"),
            "selectedLabel": ((analysis.get("decisionPlan") or {}).get("selectedOption") or {}).get("label"),
            "selectedCarry_m": ((analysis.get("decisionPlan") or {}).get("selectedOption") or {}).get("carry_m"),
            "confidence": ((analysis.get("decisionPlan") or {}).get("confidence") or {}).get("level"),
            "failureType": (analysis.get("decisionOutcome") or {}).get("failureType"),
        },
        "review": analysis["review"],
    }


def build_round_analysis(
    *,
    scorecard_id: int | str,
    ensure_geometry: bool = False,
    write_outputs: bool = False,
) -> dict[str, Any]:
    scorecard = load_scorecard(scorecard_id)
    detail = scorecard["scorecardDetails"][0]
    sc = detail["scorecard"]
    shot_data = load_shot_file(scorecard_id)
    holes_with_shots = {
        int(h.get("holeNumber"))
        for h in (shot_data or {}).get("holeShots", []) or []
        if h.get("shots")
    }
    holes = []
    errors = []
    for hole in sorted(holes_with_shots):
        try:
            analysis = build_hole_analysis(
                scorecard_id=scorecard_id,
                hole_number=hole,
                ensure_geometry=ensure_geometry,
            )
            holes.append(_hole_summary(analysis))
        except Exception as exc:
            ref = round_hole_ref(scorecard, hole)
            errors.append({
                "hole": hole,
                "globalId": ref.global_id,
                "localHole": ref.local_hole,
                "error": str(exc),
            })

    confidence_counts: dict[str, int] = {}
    missing_geometry = []
    for row in holes:
        confidence_counts[row["confidence"]] = confidence_counts.get(row["confidence"], 0) + 1
        if not row["hasGeometry"]:
            missing_geometry.append({"globalId": row["globalId"], "localHole": row["localHole"], "hole": row["hole"]})

    repeated_risks: dict[str, int] = {}
    for row in holes:
        for risk in row.get("risks", []):
            key = str(risk.get("kind"))
            repeated_risks[key] = repeated_risks.get(key, 0) + 1
    top_risks = sorted(repeated_risks.items(), key=lambda kv: kv[1], reverse=True)
    decision_counts: dict[str, int] = {}
    for row in holes:
        failure_type = ((row.get("decision") or {}).get("failureType")) or "unknown"
        decision_counts[failure_type] = decision_counts.get(failure_type, 0) + 1

    snap = (scorecard.get("courseSnapshots") or [{}])[0]
    result = {
        "schema": "ai-caddie-round-analysis-v1",
        "scorecardId": str(scorecard_id),
        "courseName": snap.get("name") or "Unknown course",
        "date": sc.get("formattedStartTime") or sc.get("startTime"),
        "strokes": sc.get("strokes"),
        "holesCompleted": sc.get("holesCompleted"),
        "frontNineGlobalCourseId": sc.get("frontNineGlobalCourseId") or sc.get("courseGlobalId"),
        "backNineGlobalCourseId": sc.get("backNineGlobalCourseId"),
        "holes": holes,
        "errors": errors,
        "summary": {
            "analyzedHoles": len(holes),
            "confidenceCounts": confidence_counts,
            "missingGeometry": missing_geometry,
            "topRisks": [{"kind": k, "count": v} for k, v in top_risks],
            "decisionFailureTypes": decision_counts,
        },
    }
    result["review"] = round_review(result)
    result["llmBrief"] = round_llm_brief(result)
    if write_outputs:
        write_json(ANALYSIS_OUT / f"garmin_{scorecard_id}_round_analysis.json", result)
        (ANALYSIS_OUT / f"garmin_{scorecard_id}_round_report.md").write_text(render_round_markdown(result))
    return result


def round_review(round_analysis: dict[str, Any]) -> str:
    summary = round_analysis["summary"]
    missing = len(summary["missingGeometry"])
    high = summary["confidenceCounts"].get("high", 0)
    analyzed = summary["analyzedHoles"]
    bits = [
        f"{round_analysis['courseName']}：已分析 {analyzed} 洞，{high} 洞为高置信度。",
    ]
    if missing:
        bits.append(f"{missing} 洞缺少 prodgeometry，需要先补球场几何。")
    if summary["topRisks"]:
        kind_cn = {"bunker": "沙坑", "water": "水障碍", "tree_area": "树林", "water_edge": "水障碍边缘"}
        risks = "，".join(f"{kind_cn.get(r['kind'], r['kind'])}×{r['count']}" for r in summary["topRisks"][:3])
        bits.append(f"本轮重复出现的风险类型：{risks}。")
    decision_counts = summary.get("decisionFailureTypes") or {}
    if decision_counts:
        label_cn = {"strategy": "策略", "execution": "执行", "info_gap": "信息缺口", "variance": "正常波动"}
        counts = "，".join(
            f"{label_cn.get(kind, kind)}×{count}"
            for kind, count in sorted(decision_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
        )
        bits.append(f"决策审计：{counts}。")
    weak = [h for h in round_analysis["holes"] if h["confidence"] != "high"]
    if weak:
        bits.append("低置信度洞：" + "、".join(str(h["hole"]) for h in weak[:8]) + "。")
    return " ".join(bits)


def round_llm_brief(round_analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": "Write a concise Chinese round review. Use only the supplied facts. Separate geometry gaps from player mistakes.",
        "facts": {
            "courseName": round_analysis["courseName"],
            "date": round_analysis["date"],
            "strokes": round_analysis["strokes"],
            "summary": round_analysis["summary"],
            "holes": [
                {
                    "hole": h["hole"],
                    "confidence": h["confidence"],
                    "shotCount": h["shotCount"],
                    "teeShotClub": h["teeShotClub"],
                    "teeShotMeters": h["teeShotMeters"],
                    "teeShotSurface": h["teeShotSurface"],
                    "risks": h["risks"],
                    "bestRoute": {
                        "label": (h.get("bestRoute") or {}).get("label"),
                        "carry_m": (h.get("bestRoute") or {}).get("carry_m"),
                        "riskScore": (h.get("bestRoute") or {}).get("riskScore"),
                    },
                    "decision": h.get("decision"),
                }
                for h in round_analysis["holes"]
            ],
        },
    }


def render_round_markdown(round_analysis: dict[str, Any]) -> str:
    lines = [
        f"# {round_analysis['courseName']} Round Analysis",
        "",
        round_analysis["review"],
        "",
        "| Hole | Confidence | Shots | Tee shot | Risks | Best route |",
        "|---:|---|---:|---|---|---|",
    ]
    for h in round_analysis["holes"]:
        risks = ", ".join(f"{r['kind']} {r['distance_m']}m" for r in h.get("risks", [])[:3])
        best = h.get("bestRoute") or {}
        tee = f"{h.get('teeShotClub') or '-'} {h.get('teeShotMeters') or '-'}m {h.get('teeShotSurface') or ''}"
        route = f"{best.get('label') or '-'} {best.get('carry_m') or ''}m"
        lines.append(f"| {h['hole']} | {h['confidence']} | {h['shotCount']} | {tee} | {risks or '-'} | {route} |")
    if round_analysis["errors"]:
        lines.extend(["", "## Errors"])
        for err in round_analysis["errors"]:
            lines.append(f"- Hole {err['hole']}: {err['error']}")
    return "\n".join(lines) + "\n"
