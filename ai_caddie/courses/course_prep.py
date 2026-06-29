"""Pre-round course-prep facts for a hole/nine: par + playing route + hazard carries +
recommended club/target (from the player's real distances) + a styled hole map. NO AI.

Geometry-only and self-contained (works before any shot exists), using the decoded
prodgeometry meshes in the mesh coord frame — the same frame as :mod:`ai_caddie.geometry.hole_render`,
so map + overlay + hazards align exactly. Par comes from :mod:`ai_caddie.courses.course_reference`
(played -> courseview -> estimate), labelled with its source. Ported from the validated
prototype (route = blue-tee + dogleg centreline; green = dogleg line end; hazards by
point-in-polygon along the densified route).
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field

from ai_caddie.courses import course_reference
from ai_caddie.geometry import elevation, hole_render, shot_projection
from ai_caddie.core.data import build_club_profiles, read_json
from ai_caddie.core.data import OWNER_ID, load_manual_club_bag
from ai_caddie.core.data import available_prep_holes as available_prep_holes  # re-export: prep's hole-list default
from ai_caddie.caddie import club_catalog
from ai_caddie.geometry.geometry_evidence import geometry_coverage_for_hole

YARD = 1.09361
MAX_SCATTER_SHOTS = 80  # newest rounds first; keeps the overlay readable and the payload small
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


WATER_MIN_M = 3.0   # ignore water clips shorter than this along the route (carry not meaningful)
BUNKER_MAX_M = 30.0  # only report a bunker whose nearest edge is within this of the route


def _route_segments(route) -> list[tuple[tuple[float, float], tuple[float, float], float, float]]:
    """Route vertices as ``(a, b, cum_at_a_m, seg_len_m)`` segments (cumulative measured at ``a``)."""
    segments = []
    cum = 0.0
    for i in range(len(route) - 1):
        a = (float(route[i][0]), float(route[i][1]))
        b = (float(route[i + 1][0]), float(route[i + 1][1]))
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg > 0:
            segments.append((a, b, cum, seg))
        cum += seg
    return segments


def _merge_intervals(intervals, gap=1e-6) -> list[list[float]]:
    """Merge only numerically-contiguous ``[start, end]`` metre intervals.

    Adjacent mesh triangles split one contiguous water crossing into touching sub-intervals; this
    glues them back into a single carry. Genuinely separate water bodies (a real dry gap) stay
    split — that is the more accurate behaviour. Degenerate (zero-length) intervals are dropped.
    """
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if end - start <= gap:
            continue
        if merged and start <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _water_carry(lake, segments) -> list[list[float]]:
    """Carry intervals (metres along the route) from the EXACT route-segment ∩ lake intersection.

    Each route segment is intersected with every Lake mesh component via the precise
    :func:`measure_prodgeometry_distances.line_intervals_for_component`, so a narrow water strip
    the route crosses BETWEEN the old 4 m samples is no longer missed. Sub-``WATER_MIN_M`` clips
    are dropped (unchanged noise filter).
    """
    if not lake:
        return []
    from ai_caddie.geometry.measure_prodgeometry_distances import line_intervals_for_component, mesh_components

    raw: list[tuple[float, float]] = []
    for component in mesh_components(lake):
        for a, b, cum, seg in segments:
            for t0, t1 in line_intervals_for_component(a, b, component):
                raw.append((cum + t0 * seg, cum + t1 * seg))
    return [
        [round(start, 1), round(end, 1)]
        for start, end in _merge_intervals(raw)
        if end - start >= WATER_MIN_M
    ]


def _bbox_gap(route_bbox, comp_bbox) -> float:
    """Lower bound on the route↔component distance from their bounding boxes (safe to reject on)."""
    dx = max(comp_bbox[0] - route_bbox[2], route_bbox[0] - comp_bbox[2], 0.0)
    dy = max(comp_bbox[1] - route_bbox[3], route_bbox[1] - comp_bbox[3], 0.0)
    return math.hypot(dx, dy)


def _bunkers(bunker, route) -> list[list[float]]:
    """``[along_route_m, side_m]`` per bunker, side = shortest distance to the bunker BOUNDARY.

    Uses :func:`measure_prodgeometry_distances.point_triangle_distance` (exact point→triangle) from
    each densified route point to the bunker's triangles, so a long bunker whose near edge hugs the
    route is measured by that edge — not by its far-away centroid (the old approximation, which
    over-stated the gap and could push a near-edge bunker past the ``BUNKER_MAX_M`` gate). The
    along-route position keeps the existing 4 m route resolution.
    """
    if not bunker:
        return []
    from ai_caddie.geometry.measure_prodgeometry_distances import mesh_components, point_triangle_distance

    dense = _densify(route)
    if not dense:
        return []
    xs = [p[0] for p in dense]
    ys = [p[1] for p in dense]
    route_bbox = (min(xs), min(ys), max(xs), max(ys))
    bunkers: list[list[float]] = []
    for component in mesh_components(bunker):
        if _bbox_gap(route_bbox, component["bbox"]) > BUNKER_MAX_M:
            continue  # whole component is provably out of range — skip the per-point distance work
        triangles = component["triangles"]
        best_side = None
        best_cum = None
        for p in dense:
            side = min(point_triangle_distance((p[0], p[1]), tri) for tri in triangles)
            if best_side is None or side < best_side:
                best_side, best_cum = side, p[2]
        if best_side is not None and best_side <= BUNKER_MAX_M:
            bunkers.append([round(best_cum, 1), round(best_side, 1)])
    bunkers.sort()
    return bunkers


def route_hazards(by: dict, route) -> dict:
    """Water-carry intervals + greenside/fairway bunkers along the route (metres along route).

    Geometry is measured EXACTLY against the decoded meshes (same coord frame as the map/overlay).
    Water carries come from the true route-segment ∩ Lake-component intersection (a narrow strip
    crossed between samples is never missed); bunker ``side`` is the shortest distance to the bunker
    BOUNDARY rather than its centroid (a long bunker is measured by its near edge). The output shape
    is unchanged: ``water_carry`` = ``[[enter_m, clear_m], ...]`` and ``bunkers`` =
    ``[[along_route_m, side_m], ...]``, both in metres along the route, rounded to 0.1 m.
    """
    segments = _route_segments(route)
    return {
        "water_carry": _water_carry(by.get("Lake.drc"), segments),
        "bunkers": _bunkers(by.get("Bunker.drc"), route),
    }


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
    ordered = sorted(ladder.items(), key=lambda kv: -kv[1])
    # Only recommend clubs the player actually carries (real Garmin bag), so a stale mis-tagged
    # club from shot history (e.g. a "2 Hybrid" no longer in the bag) never gets suggested.
    from ai_caddie.caddie.club_bag import restrict_to_bag

    return restrict_to_bag(ordered, lambda kv: kv[0])


def _member_measured_by_token(player_id: str) -> dict[str, int]:
    """A member's MEASURED median distance per catalog token, from their OWN logged shots only.

    Reads the member's player-scoped shot dir(s) (``history._player_shot_sources``) — never the
    owner's or another member's — and maps each measured profile's club name to a catalog token
    the same way ``restrict_to_bag`` canonicalises names. On a token collision the larger sample
    wins. Empty when the member has logged nothing yet. Imports are local to mirror the existing
    lazy ``restrict_to_bag`` import and stay clear of any module-load import cycle.
    """
    from ai_caddie.history.history import _player_shot_sources
    from ai_caddie.caddie.club_bag import canonical_club_name

    shot_dirs = [shots for _sc, shots in _player_shot_sources(player_id)]
    measured = build_club_profiles(shot_dirs=shot_dirs)
    by_token: dict[str, int] = {}
    samples: dict[str, int] = {}
    for club_name, profile in measured.items():
        if not isinstance(profile, dict) or not profile.get("median"):
            continue
        token = canonical_club_name(club_name)
        if not token or not club_catalog.is_valid_token(token):
            continue
        n = int(profile.get("sampleSize") or 0)
        if token not in by_token or n > samples.get(token, 0):
            by_token[token] = round(profile["median"])
            samples[token] = n
    return by_token


def effective_club_ladder(player_id: str) -> list[tuple[str, int]]:
    """The recommended-club ladder for a player, used by every member-reachable prep builder.

    - Owner -> club_ladder() (history-derived distances, restricted to the owner's effective bag).
    - A member WITH a manual bag -> a ladder over their selected tokens, each distance taken as
      their OWN measured median (from their logged shots) ?? manual distanceM ?? CLUB_CATALOG
      default, sorted descending (clubs with none are dropped). Measured distances are read only
      from the member's own tree, so no other player's distances ever leak in.
    - A member with no manual bag -> the generic DEFAULT_LADDER. Never the owner's distances.
    """
    if player_id == OWNER_ID:
        return club_ladder()
    manual = load_manual_club_bag(player_id)
    if manual:
        measured_by_token = _member_measured_by_token(player_id)
        pairs: list[tuple[str, int]] = []
        for club in manual.get("clubs") or []:
            token = str(club.get("token") or "")
            if not club_catalog.is_valid_token(token):
                continue
            dist = measured_by_token.get(token)
            if dist is None:
                dist = club.get("distanceM")
            if dist is None:
                dist = club_catalog.default_distance_m(token)
            if dist is None:
                continue
            pairs.append((token, int(dist)))
        if pairs:
            return sorted(pairs, key=lambda kv: -kv[1])
    return sorted(DEFAULT_LADDER.items(), key=lambda kv: -kv[1])


def club_for(distance_m: float, ladder, *, exclude=()):
    cand = [(n, d) for n, d in ladder if n not in exclude]
    if not cand:
        return None, None
    return min(cand, key=lambda kv: abs(kv[1] - distance_m))


# ---------- strategy + per-hole DTO ----------

@dataclass
class HolePrep:
    globalId: int
    localHole: int
    hole: int
    par: int
    par_source: str
    blue_yards: int
    route_len_m: float
    route: list[list[float]] = field(default_factory=list)
    geometryCoverage: str = "missing"
    sourceRefs: list[str] = field(default_factory=list)
    missingData: list[dict] = field(default_factory=list)
    candidateRoutes: list[dict] = field(default_factory=list)
    carryTargets: list[dict] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    landing_m: float | None = None
    tee_club: str | None = None
    hazards: dict = field(default_factory=dict)
    playsLike: dict = field(default_factory=dict)  # round-13: {available, teeElevM, greenElevM, deltaM, deltaYd}
    greenDistances: dict = field(default_factory=dict)  # round-13 E3: {available, front/middle/back M+Yd}

    def to_dict(self) -> dict:
        return asdict(self)


def _hole_playslike(by: dict, route) -> dict:
    """PlaysLike (elevation ±yd, tee/ball -> green) from the hole's mesh elevation. round-13.

    Uses the same meshes the map/hazards use (no DEM); empty when route or geometry is missing.
    ``route`` points are in the ``(-mesh_x, mesh_z)`` frame, matching ``elevation._ground``.
    """
    if not route or len(route) < 2:
        return {"available": False}
    try:
        return elevation.playslike(by, route[0], route[-1])
    except Exception:
        return {"available": False}


def _green_distances(by: dict, route) -> dict:
    """Front/Middle/Back green distances from the tee (前/中/后果岭), flat plan-view m+yd. round-13 E3.

    Reuses the green surface mesh (``by["Green.drc"]``) the map already ships — NO DEM (elevation
    lives in ``playsLike``). ``measure_prodgeometry_distances.mesh_components`` returns components
    whose triangles/centroid are ALREADY in the ``(-mesh_x, mesh_z)`` frame (same as ``route``), so
    no re-projection. A Green.drc tile can include neighbour-hole greens, so we pick the component
    whose centroid is nearest ``route[-1]`` (the dogleg/green endpoint). Front = nearest green
    vertex to the tee, Back = farthest, Middle = the chosen component's centroid. Degrades to
    ``{"available": False}`` on any missing route/green/usable geometry.
    """
    if not route:
        return {"available": False}
    green = (by or {}).get("Green.drc")
    if not isinstance(green, dict) or not green.get("positions") or not green.get("faces"):
        return {"available": False}
    try:
        from ai_caddie.geometry.measure_prodgeometry_distances import mesh_components

        comps = mesh_components(green)
        if not comps:
            return {"available": False}
        tee = (float(route[0][0]), float(route[0][1]))
        target = (float(route[-1][0]), float(route[-1][1]))
        comp = min(comps, key=lambda c: math.hypot(c["centroid"][0] - target[0], c["centroid"][1] - target[1]))
        verts = [p for tri in comp["triangles"] for p in tri]
        dists = [math.hypot(v[0] - tee[0], v[1] - tee[1]) for v in verts]
        if not dists:
            return {"available": False}
        front_m, back_m = min(dists), max(dists)
        middle_m = math.hypot(comp["centroid"][0] - tee[0], comp["centroid"][1] - tee[1])
        return {
            "available": True,
            "frontM": round(front_m, 1), "frontYd": yd(front_m),
            "middleM": round(middle_m, 1), "middleYd": yd(middle_m),
            "backM": round(back_m, 1), "backYd": yd(back_m),
        }
    except Exception:
        return {"available": False}


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


def _route_with_cumulative(route: list[tuple[float, float]]) -> list[list[float]]:
    out: list[list[float]] = []
    cumulative = 0.0
    for index, point in enumerate(route):
        if index:
            previous = route[index - 1]
            cumulative += math.hypot(point[0] - previous[0], point[1] - previous[1])
        out.append([round(point[0], 1), round(point[1], 1), round(cumulative, 1)])
    return out


def _candidate_routes(ladder: list[tuple[str, int]], hazards: dict) -> list[dict]:
    if not ladder:
        return []
    longest_name, longest_m = ladder[0]
    safe_name, safe_m = next((row for row in ladder[1:] if row[1] >= 120), ladder[0])
    risk = 3 if (hazards.get("water_carry") or hazards.get("bunkers")) else 1
    return [
        {"id": "safe", "club": safe_name, "carryM": float(safe_m), "riskScore": 0, "source": "course_prep"},
        {"id": "stock", "club": longest_name, "carryM": float(longest_m), "riskScore": 1, "source": "course_prep"},
        {"id": "attack", "club": longest_name, "carryM": float(longest_m), "riskScore": risk, "source": "course_prep"},
    ]


def _carry_targets(landing_m: float | None, hazards: dict) -> list[dict]:
    rows: list[dict] = []
    if landing_m is not None:
        rows.append({"kind": "landing", "distanceM": round(landing_m, 1)})
    for start, end in hazards.get("water_carry") or []:
        rows.append({"kind": "water_clear", "enterM": float(start), "clearM": float(end)})
    for distance, side in hazards.get("bunkers") or []:
        rows.append({"kind": "bunker", "distanceM": float(distance), "sideM": float(side)})
    return rows


def _your_shots(md: dict, by: dict, route, global_id: int, local_hole: int, overlay: dict,
                player_id: str = OWNER_ID) -> list[dict]:
    """The player's past TEE/APPROACH end positions projected into display px.

    World→local uses the calibrated frame in :mod:`ai_caddie.geometry.shot_projection`; local→px reuses
    render_hole's EXACT overlay transform (:func:`ai_caddie.geometry.hole_render.overlay_projector`).
    Pixel ints are clipped to the overlay bounds; capped at ``MAX_SCATTER_SHOTS`` newest-first.
    """
    hole_meta = md.get("hole") or {}
    ref_lat, ref_lon = hole_meta.get("RefLat"), hole_meta.get("RefLon")
    if ref_lat is None or ref_lon is None:
        return []
    # Owner: None -> the flat owner tree (unchanged). Member: only their own player-scoped tree,
    # so a member's scatter is built solely from their own logged rounds (never another player's).
    sources = None
    if player_id != OWNER_ID:
        from ai_caddie.history.history import _player_shot_sources
        sources = _player_shot_sources(player_id)
    shots = shot_projection.shots_for_hole(global_id, local_hole, sources=sources)
    if not shots:
        return []
    to_px = hole_render.overlay_projector(by, route)
    width, height = int(overlay["w"]), int(overlay["h"])
    out: list[dict] = []
    for shot in shots[:MAX_SCATTER_SHOTS]:
        x, y = shot_projection.project_world_to_pixel(
            shot["lat"], shot["lon"], ref_lat=float(ref_lat), ref_lon=float(ref_lon), to_px=to_px,
        )
        out.append({
            "x": min(max(int(round(x)), 0), width - 1),
            "y": min(max(int(round(y)), 0), height - 1),
            "club": shot.get("club"),
            "shotType": shot.get("shotType"),
            "roundId": shot.get("roundId"),
        })
    return out


def prep_hole(global_id: int, local_hole: int, *, ladder=None, par_record=None, render=True,
              include_shots=False, player_id: str = OWNER_ID) -> HolePrep | None:
    """Compose pre-round prep for one hole. Returns None if geometry is unavailable."""
    try:
        md, by = hole_render.load_mesh(global_id, local_hole)
    except Exception:
        return None
    route, route_len = derive_route(md)
    if not route or not route_len:
        return None
    ladder = ladder or effective_club_ladder(player_id)
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
    try:
        coverage = geometry_coverage_for_hole(global_id, local_hole)
    except Exception:
        coverage = {
            "coverage": "missing",
            "missingData": [{"label": "geometry", "reason": "prodgeometry geometry could not be loaded"}],
        }
    missing_data = [
        row
        for row in coverage.get("missingData", [])
        if isinstance(row, dict)
    ]
    prep = HolePrep(
        globalId=int(global_id), localHole=int(local_hole),
        hole=local_hole, par=par, par_source=par_source,
        blue_yards=yd(route_len), route_len_m=round(route_len, 1),
        route=_route_with_cumulative(route),
        geometryCoverage=str(coverage.get("coverage") or "missing"),
        sourceRefs=[f"course:{int(global_id)}", f"geometry:{int(global_id)}:{int(local_hole)}"],
        missingData=missing_data,
        candidateRoutes=_candidate_routes(ladder, hazards),
        carryTargets=_carry_targets(landing, hazards),
        steps=steps, cautions=cautions, landing_m=(round(landing, 1) if landing else None),
        tee_club=tee_club, hazards=hazards,
        playsLike=_hole_playslike(by, route),
        greenDistances=_green_distances(by, route),
    )
    result = prep.to_dict()
    if render:
        image, meta = hole_render.render_hole(global_id, local_hole, route, route_len, landing_m=landing)
        result["map"] = {"image": image, "overlay": meta}
        if include_shots:
            try:
                scatter = _your_shots(md, by, route, global_id, local_hole, meta, player_id=player_id)
            except Exception:
                scatter = []  # scatter is an enhancement — never break prep over it
            if scatter:
                result["yourShots"] = scatter
    return result if render else prep


def _missing_hole(global_id: int, local_hole: int, par_record=None) -> dict:
    par_idx = int(local_hole) - 1
    if par_record is not None and 0 <= par_idx < len(par_record.par):
        par = int(par_record.par[par_idx])
        par_source = par_record.par_source
    else:
        par = 4
        par_source = "estimate"
    return {
        "globalId": int(global_id),
        "localHole": int(local_hole),
        "hole": int(local_hole),
        "par": par,
        "par_source": par_source,
        "blue_yards": 0,
        "route_len_m": 0.0,
        "route": [],
        "geometryCoverage": "missing",
        "sourceRefs": [f"course:{int(global_id)}", f"geometry:{int(global_id)}:{int(local_hole)}"],
        "missingData": [{"label": "geometry", "reason": "prodgeometry geometry is missing for this hole"}],
        "candidateRoutes": [],
        "carryTargets": [],
        "steps": [],
        "cautions": [],
        "landing_m": None,
        "tee_club": None,
        "hazards": {"water_carry": [], "bunkers": []},
    }


def prep_nine(global_id: int, holes=range(1, 10), *, ladder=None, render=True, include_missing: bool = False,
              include_shots: bool = False, player_id: str = OWNER_ID) -> list:
    """Pre-round prep for every hole of a nine that has geometry.

    Par is cache-first: the stored ``data/courses/<gid>.json`` record, else ``resolve_par``
    (courseview). For an UNPLAYED course with no cached release, ``resolve_par`` does a one-time
    blocking CourseView fetch (then caches it), so the first prep of a cold course is slower.
    When ``include_missing`` is true, requested holes without geometry are returned as degraded
    DTO rows instead of being skipped.
    """
    if ladder is None:
        ladder = effective_club_ladder(player_id)
    par_record = course_reference.load_course_par(global_id)
    if par_record is None:
        par_record = course_reference.resolve_par(global_id)
    out = []
    for hole in holes:
        prep = prep_hole(global_id, hole, ladder=ladder, par_record=par_record, render=render,
                         include_shots=include_shots, player_id=player_id)
        if prep is not None:
            out.append(prep.to_dict() if include_missing and hasattr(prep, "to_dict") else prep)
        elif include_missing:
            out.append(_missing_hole(global_id, hole, par_record))
    return out
