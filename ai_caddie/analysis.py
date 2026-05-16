"""Rule-based hole analysis for the AI Caddie MVP."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
import html
import json
import math

from measure_prodgeometry_distances import (
    dist,
    line_intervals_for_component,
    mesh_components,
    point_triangle_distance,
)

from .data import (
    build_club_profiles,
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

ROOT = Path(__file__).resolve().parents[1]
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


@lru_cache(maxsize=128)
def load_geometry(global_id: int, local_hole: int) -> dict[str, Any]:
    h_path = hazard_path(global_id, local_hole)
    m_path = mesh_path(global_id, local_hole)
    hazards = read_json(h_path) if h_path.exists() else None
    meshes = read_json(m_path) if m_path.exists() else None
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
    tees = (geometry.get("hazards") or {}).get("tees") or []
    if tees and tees[0].get("position"):
        pos = tees[0]["position"]
        return "Tee", (float(pos[0]), float(pos[1]))
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
    target = (analysis.get("geometry") or {}).get("target", {}).get("position")
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
        start_local = tees[0]["position"] if tees else None
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
        surface = ((first.get("end") or {}).get("feature") or {}).get("surface") or {}
        surface_text = kind_cn.get(surface.get("kind"), (first.get("end") or {}).get("lie") or "未知区域")
        remain = first.get("remainingToTarget_m")
        remain_text = f"剩余目标约 {remain} 米" if remain is not None else "剩余距离暂时无法计算"
        lines.append(
            f"开球用 {first.get('clubName') or '未知球杆'}，落在{surface_text}，{remain_text}。"
        )
        risks = ((first.get("end") or {}).get("feature") or {}).get("nearRisks") or []
        if risks:
            risk_text = "，".join(f"{kind_cn.get(r['kind'], r['kind'])} {r['distance_m']} 米" for r in risks[:3])
            lines.append(f"开球落点附近主要风险：{risk_text}。")
    if candidates:
        best = candidates[0]
        lines.append(
            f"当前规则模型给出的低风险候选是「{best['label']}」，目标 carry 约 {best['carry_m']} 米，风险分 {best['riskScore']}。"
        )
    if quality["issues"]:
        lines.append("还需要补的数据：" + "；".join(quality["issues"][:4]) + "。")
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
                    "club": s.get("clubName"),
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
        },
    }


def build_hole_analysis(
    *,
    scorecard_id: int | str | None = None,
    manual_round_id: str | None = None,
    hole_number: int,
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

    geometry = load_geometry(int(hole["globalId"]), int(hole["localHole"]))
    club_profiles = build_club_profiles()
    shots = enrich_shots(hole, geometry)
    candidates = candidate_routes(hole, shots, geometry, club_profiles)
    quality = data_quality(hole, shots, geometry, club_profiles)
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
        "geometry": {
            "hasHazards": geometry["hasHazards"],
            "hasMeshes": geometry["hasMeshes"],
            "refLat": (geometry.get("hazards") or {}).get("refLat"),
            "refLon": (geometry.get("hazards") or {}).get("refLon"),
            "target": (geometry.get("hazards") or {}).get("target"),
            "hazardCount": len((geometry.get("hazards") or {}).get("hazards", [])),
        },
        "shots": shots,
        "clubProfiles": relevant_profiles,
        "candidateRoutes": candidates,
        "dataQuality": quality,
    }
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


def render_svg(analysis: dict[str, Any]) -> str:
    geometry = load_geometry(int(analysis["globalId"]), int(analysis["localHole"]))
    all_points: list[tuple[float, float]] = []
    hulls = []
    for component in geometry["components"]:
        if component["kind"] not in COLORS:
            continue
        pts = _component_points(component)
        hull = _convex_hull(pts)
        if len(hull) >= 3:
            hulls.append((component["kind"], component["id"], hull))
            all_points.extend(hull)
    for shot in analysis["shots"]:
        for key in ("start", "end"):
            local = (shot.get(key) or {}).get("local")
            if local:
                all_points.append((float(local[0]), float(local[1])))
    target = (analysis.get("geometry", {}).get("target") or {}).get("position")
    if target:
        all_points.append((float(target[0]), float(target[1])))
    if not all_points:
        return "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"900\" height=\"640\"></svg>"

    min_x = min(p[0] for p in all_points) - 30
    max_x = max(p[0] for p in all_points) + 30
    min_y = min(p[1] for p in all_points) - 30
    max_y = max(p[1] for p in all_points) + 30
    width = max(1.0, max_x - min_x)
    height = max(1.0, max_y - min_y)

    def sx(x: float) -> float:
        return (x - min_x) / width * 860 + 20

    def sy(y: float) -> float:
        return 620 - ((y - min_y) / height * 580 + 20)

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="640" viewBox="0 0 900 640">',
        '<rect width="900" height="640" fill="#f6f4ef"/>',
    ]
    for kind, cid, hull in hulls:
        color = COLORS[kind]
        if color == "none":
            fill = "none"
            stroke = "#6b7280"
            opacity = "0.45"
        else:
            fill = color
            stroke = "#334155"
            opacity = "0.55" if kind in {"fairway", "rough"} else "0.78"
        pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in hull)
        parts.append(
            f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="1" opacity="{opacity}">'
            f'<title>{html.escape(cid)}</title></polygon>'
        )

    for shot in analysis["shots"]:
        start = (shot.get("start") or {}).get("local")
        end = (shot.get("end") or {}).get("local")
        if start and end:
            parts.append(
                f'<line x1="{sx(start[0]):.1f}" y1="{sy(start[1]):.1f}" '
                f'x2="{sx(end[0]):.1f}" y2="{sy(end[1]):.1f}" stroke="#111827" stroke-width="2.5" opacity="0.85"/>'
            )
            parts.append(f'<circle cx="{sx(start[0]):.1f}" cy="{sy(start[1]):.1f}" r="5" fill="#ffffff" stroke="#111827" stroke-width="2"/>')
            parts.append(f'<circle cx="{sx(end[0]):.1f}" cy="{sy(end[1]):.1f}" r="6" fill="#ef4444" stroke="#ffffff" stroke-width="2"/>')
            parts.append(
                f'<text x="{sx(end[0]) + 7:.1f}" y="{sy(end[1]) - 7:.1f}" '
                f'font-family="Arial" font-size="12" fill="#111827">{shot.get("shotOrder")}</text>'
            )
    if target:
        parts.append(f'<circle cx="{sx(target[0]):.1f}" cy="{sy(target[1]):.1f}" r="7" fill="#10b981" stroke="#064e3b" stroke-width="2"/>')
        parts.append(f'<text x="{sx(target[0]) + 9:.1f}" y="{sy(target[1]) - 9:.1f}" font-family="Arial" font-size="12" fill="#064e3b">target</text>')
    parts.append(
        f'<text x="20" y="28" font-family="Arial" font-size="16" font-weight="700" fill="#111827">'
        f'{html.escape(str(analysis["courseName"]))} hole {analysis["hole"]}</text>'
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
    focus_kinds = {"fairway", "green", "bunker", "water", "water_edge", "teebox", "tree_area"}

    def point_from_local(point: list[float] | tuple[float, float]) -> tuple[float, float]:
        lat, lon = local_to_wgs84(float(point[0]), float(point[1]), float(ref_lat), float(ref_lon))
        return lon, lat

    for component in geometry["components"]:
        if component["kind"] not in COLORS:
            continue
        hull = _convex_hull(_component_points(component))
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
            },
        })

    for shot in analysis.get("shots", []):
        start = shot.get("start")
        end = shot.get("end")
        if start and end and start.get("lat") is not None and end.get("lat") is not None:
            coords = [
                [float(start["lon"]), float(start["lat"])],
                [float(end["lon"]), float(end["lat"])],
            ]
            bounds_points.extend((tuple(coords[0]), tuple(coords[1])))
            focus_points.extend((tuple(coords[0]), tuple(coords[1])))
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "layer": "shot",
                    "order": shot.get("shotOrder"),
                    "club": shot.get("clubName"),
                    "meters": shot.get("meters"),
                    "type": shot.get("shotType"),
                },
            })
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": coords[1]},
                "properties": {
                    "layer": "shot_end",
                    "order": shot.get("shotOrder"),
                    "club": shot.get("clubName"),
                    "lie": (end or {}).get("lie"),
                },
            })
        elif end and end.get("lat") is not None:
            coord = [float(end["lon"]), float(end["lat"])]
            bounds_points.append(tuple(coord))
            focus_points.append(tuple(coord))
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": coord},
                "properties": {"layer": "shot_end", "order": shot.get("shotOrder"), "club": shot.get("clubName")},
            })

    target = (analysis.get("geometry") or {}).get("target") or {}
    if target.get("position"):
        lon, lat = point_from_local(target["position"])
        bounds_points.append((lon, lat))
        focus_points.append((lon, lat))
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"layer": "target", "kind": "target"},
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
    return {
        "hole": analysis["hole"],
        "globalId": analysis["globalId"],
        "localHole": analysis["localHole"],
        "confidence": analysis["dataQuality"]["confidence"],
        "hasGeometry": bool(analysis["geometry"]["hasHazards"] and analysis["geometry"]["hasMeshes"]),
        "shotCount": len(analysis.get("shots", [])),
        "teeShotClub": first.get("clubName"),
        "teeShotMeters": first.get("meters"),
        "teeShotSurface": first_surface or (first.get("end") or {}).get("lie"),
        "risks": risks[:4],
        "bestRoute": (analysis.get("candidateRoutes") or [{}])[0],
        "review": analysis["review"],
    }


def build_round_analysis(*, scorecard_id: int | str, write_outputs: bool = False) -> dict[str, Any]:
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
            analysis = build_hole_analysis(scorecard_id=scorecard_id, hole_number=hole)
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
