"""Pre-round course-prep facts for a hole/nine: par + playing route + hazard carries +
recommended club/target (from the player's real distances) + a styled hole map. NO AI.

Geometry-only and self-contained (works before any shot exists), using the decoded
prodgeometry meshes in the mesh coord frame — the same frame as :mod:`ai_caddie.hole_render`,
so map + overlay + hazards align exactly. Par comes from :mod:`ai_caddie.course_reference`
(played -> official -> estimate), labelled with its source. Ported from the validated
prototype (route = blue-tee + dogleg centreline; green = dogleg line end; hazards by
point-in-polygon along the densified route).
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field

from ai_caddie import course_reference, hole_render
from ai_caddie.data import build_club_profiles, read_json

YARD = 1.09361
DEFAULT_LADDER = {  # metres; overridden by the player's real club model when available
    "1W": 200, "3W": 171, "3H": 159, "5I": 146, "6I": 132, "7I": 128,
    "8I": 122, "9I": 114, "PW": 102, "A杆": 84, "50°": 53, "54°": 52, "58°": 42,
}


def yd(metres: float) -> int:
    return round(metres * YARD)


def _local(p):
    return (-float(p[0]), float(p[2]))


# ---------- route derivation (tee -> dogleg centreline -> green) ----------

def _xy(p):
    if isinstance(p, dict):
        return (float(p["X"]), float(p["Y"]))
    return (float(p[0]), float(p[1]))


def _blue_tee(hole_meta: dict, fallback):
    """Blue tee = TeeLocations whose Sets include 2; else the tee nearest the dogleg start."""
    tees = hole_meta.get("TeeLocations") or []
    blue = next((t for t in tees if 2 in (t.get("Sets") or [])), None)
    if blue is not None:
        return _xy(blue)
    if tees and fallback:
        return min((_xy(t) for t in tees), key=lambda p: math.hypot(p[0] - fallback[0], p[1] - fallback[1]))
    return _xy(tees[0]) if tees else fallback


def _dogleg_line(hole_meta: dict):
    for dl in hole_meta.get("Doglegs") or []:
        line = dl.get("Line") or []
        if len(line) >= 2:
            return [_xy(p) for p in line]
    return None


def derive_route(md: dict):
    """Return (route, route_len_m) following the dogleg, or (None, None)."""
    hole_meta = md.get("hole") or {}
    line = _dogleg_line(hole_meta)
    if not line:
        return None, None
    tee = _blue_tee(hole_meta, line[0])
    if not tee:
        return None, None
    route = [tee] + line[1:]
    length = sum(math.hypot(route[i + 1][0] - route[i][0], route[i + 1][1] - route[i][1])
                 for i in range(len(route) - 1))
    return route, length


# ---------- hazards along the route (mesh point-in-polygon) ----------

def _triangles(mesh):
    pts = [_local(p) for p in mesh["positions"]]
    return [(pts[a], pts[b], pts[c]) for a, b, c in mesh["faces"]]


def _in_tri(p, a, b, c) -> bool:
    d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
    d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
    d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
    neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (neg and pos)


def _point_in_mesh(p, tris) -> bool:
    return any(_in_tri(p, a, b, c) for a, b, c in tris)


def _densify(route, step=4.0):
    out = []
    cum = 0.0
    for i in range(len(route) - 1):
        a, b = route[i], route[i + 1]
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(seg / step))
        for k in range(n):
            t = k / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, cum + seg * t))
        cum += seg
    out.append((route[-1][0], route[-1][1], cum))
    return out


def route_hazards(by: dict, route) -> dict:
    """Water-carry intervals + greenside/fairway bunkers along the route (metres along route)."""
    dense = _densify(route)
    water_carry = []
    lake = by.get("Lake.drc")
    if lake:
        tris = _triangles(lake)
        inside = [(_point_in_mesh((p[0], p[1]), tris), p[2]) for p in dense]
        i = 0
        while i < len(inside):
            if inside[i][0]:
                start = inside[i][1]
                while i < len(inside) and inside[i][0]:
                    i += 1
                end = inside[i - 1][1]
                if end - start >= 3:
                    water_carry.append([round(start, 1), round(end, 1)])
            else:
                i += 1
    bunkers = []
    bunker = by.get("Bunker.drc")
    if bunker:
        from measure_prodgeometry_distances import mesh_components
        for comp in mesh_components(bunker):
            cen = comp.get("centroid")
            if not cen:
                continue
            cx, cz = _local([cen[0], cen[1], cen[2]]) if len(cen) >= 3 else (cen[0], cen[1])
            best = min(dense, key=lambda p: math.hypot(p[0] - cx, p[1] - cz))
            side = math.hypot(best[0] - cx, best[1] - cz)
            if side <= 30:
                bunkers.append([round(best[2], 1), round(side, 1)])
    bunkers.sort()
    return {"water_carry": water_carry, "bunkers": bunkers}


# ---------- club ladder (player's real distances) ----------

def club_ladder(path=None) -> list[tuple[str, int]]:
    """Median distance per club, longest-first, from product club profiles when available."""
    ladder = dict(DEFAULT_LADDER)
    try:
        if path is not None and path.exists():
            data = read_json(path)
            ladder = {k: round(v["median"]) for k, v in data.items() if isinstance(v, dict) and v.get("median")}
        else:
            profiles = build_club_profiles()
            if profiles:
                ladder = {
                    name: round(profile["median"])
                    for name, profile in profiles.items()
                    if isinstance(profile, dict) and profile.get("median")
                }
    except Exception:
        pass
    return sorted(ladder.items(), key=lambda kv: -kv[1])


def club_for(distance_m: float, ladder, *, exclude=()):
    cand = [(n, d) for n, d in ladder if n not in exclude]
    if not cand:
        return None, None
    return min(cand, key=lambda kv: abs(kv[1] - distance_m))


# ---------- strategy + per-hole DTO ----------

@dataclass
class HolePrep:
    hole: int
    par: int
    par_source: str
    blue_yards: int
    route_len_m: float
    steps: list[dict] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    landing_m: float | None = None
    tee_club: str | None = None
    hazards: dict = field(default_factory=dict)


def _strategy(par: int, route_len_m: float, hazards: dict, ladder):
    steps: list[dict] = []
    cautions: list[str] = []
    driver = next((d for n, d in ladder if n == "1W"), 200)
    landing = None
    if par == 3:
        club, cd = club_for(route_len_m, ladder)
        steps.append({"club": club, "note": f"约 {yd(route_len_m)}y 到果岭中心，一杆上果岭"})
    else:
        landing = min(driver, route_len_m - 8) if route_len_m > driver else route_len_m * 0.55
        tee_club, _ = club_for(landing, ladder)
        steps.append({"club": tee_club, "note": f"开球落点约 {yd(landing)}y"})
        remaining = route_len_m - landing
        if remaining > 5:
            ap_club, _ = club_for(remaining, ladder, exclude=("1W",))
            steps.append({"club": ap_club, "note": f"剩约 {yd(remaining)}y 上果岭"})
    for w in hazards.get("water_carry") or []:
        if w[0] < route_len_m - 5:
            cautions.append(f"水障碍：进水前约 {yd(w[0])}y，过水需 {yd(w[1])}y")
    for cum, side in hazards.get("bunkers") or []:
        if cum >= route_len_m - 45 and side <= 25:
            cautions.append(f"果岭边沙坑（约 {yd(cum)}y）——别短别偏")
    tee_club = steps[0]["club"] if steps else None
    return steps, cautions, landing, tee_club


def prep_hole(global_id: int, local_hole: int, *, ladder=None, par_record=None, render=True) -> HolePrep | None:
    """Compose pre-round prep for one hole. Returns None if geometry is unavailable."""
    try:
        md, by = hole_render.load_mesh(global_id, local_hole)
    except Exception:
        return None
    route, route_len = derive_route(md)
    if not route or not route_len:
        return None
    ladder = ladder or club_ladder()
    if par_record is None:
        par_record = course_reference.load_course_par(global_id)
    par_idx = local_hole - 1
    if par_record is not None and 0 <= par_idx < len(par_record.par):
        par = par_record.par[par_idx]
        par_source = par_record.par_source
    else:
        par = course_reference.estimate_par_from_length(route_len)
        par_source = "estimate"
    hazards = route_hazards(by, route)
    steps, cautions, landing, tee_club = _strategy(par, route_len, hazards, ladder)
    prep = HolePrep(
        hole=local_hole, par=par, par_source=par_source,
        blue_yards=yd(route_len), route_len_m=round(route_len, 1),
        steps=steps, cautions=cautions, landing_m=(round(landing, 1) if landing else None),
        tee_club=tee_club, hazards=hazards,
    )
    result = asdict(prep)
    if render:
        image, meta = hole_render.render_hole(global_id, local_hole, route, route_len, landing_m=landing)
        result["map"] = {"image": image, "overlay": meta}
    return result if render else prep


def prep_nine(global_id: int, holes=range(1, 10), *, ladder=None, render=True) -> list:
    """Pre-round prep for every hole of a nine that has geometry. Skips missing holes."""
    if ladder is None:
        ladder = club_ladder()
    par_record = course_reference.load_course_par(global_id)
    out = []
    for hole in holes:
        prep = prep_hole(global_id, hole, ladder=ladder, par_record=par_record, render=render)
        if prep is not None:
            out.append(prep)
    return out
