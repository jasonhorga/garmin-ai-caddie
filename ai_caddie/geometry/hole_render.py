"""Render a golf hole top-down from decoded prodgeometry meshes, ROUTE-driven (follows
the dogleg fairway), neighbour holes clipped out. Returns a styled JPEG (base64) + a
transform/route overlay model so the web/mobile clients can draw the interactive layer
(draggable ball, club chips, dynamic hazard labels) over an identical image.

Pure rendering — no network, no AI. Coordinate frame matches the geometry so computed
shot points align exactly. Ported from the validated prototype; gotchas preserved:
no horizontal mirror (negate s in P), corridor clip (~54 m buffer around the route to
drop adjacent holes), water gradient, fairway stripes, foliage with shadows.
"""
from __future__ import annotations

import base64
import io
import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ai_caddie.core.data import mesh_path
from ai_caddie.geometry.measure_prodgeometry_distances import mesh_components  # noqa: F401  (kept for parity / callers)

import json

SS = 2  # supersample factor
# Fill-the-frame framing (design-system §九, ported from the locked prototype `make_frame`; the
# funnel /render-final.png reference is 678x1060). The hole fills the HEIGHT; the canvas WIDTH
# shrinks to the hole (never below FRAME_MIN_ASPECT portrait, hole centred, sky padding on the
# sides for a thin hole) so the played surfaces fill the frame instead of floating small inside a
# fixed 720x1120 letterbox. The OLD frame fixed w=720/h=1120 and min-scaled to fit, leaving the hole
# floating in extra sky; this drops the empty margins (matching render-final.png's 678x1060) and
# raises the land fill on every gid31795 hole (h2 +14pt, h8 +5pt, others +1-2pt) — a long, thin hole
# is geometry-bounded by the 0.64 portrait floor. Every consumer that reuses _frame /
# overlay_projector (flat render, topo base, round_shot_map, course_prep) shares this projection, so
# all overlays stay pixel-aligned by construction.
FRAME_H = 1060           # display px the hole fills to along the tee->green axis
FRAME_MIN_ASPECT = 0.64  # portrait floor (w/h); a hole wider than this widens the canvas
FRAME_MARGIN = 0.06      # proportional breathing room around the framed surfaces
# The rendered hole is clipped to a route corridor.  Geometry farther away can only be an
# adjacent-hole fragment, so it must not widen the shared topo/overlay frame before that clip.
FRAME_ROUTE_CORRIDOR_M = 110.0
PALETTE = {
    "bg": (191, 222, 240), "Rough": (122, 167, 92), "TreeArea": (92, 138, 74),
    "Fairway": (150, 196, 104), "Fringe": (167, 207, 122), "Green": (126, 205, 110),
    "Bunker": (231, 219, 170), "Lake": (74, 162, 214), "LakeSide": (60, 140, 190),
    "Cartpath": (188, 182, 170), "Teebox": (180, 205, 170),
}
ORDER = ["Rough", "TreeArea", "Cartpath", "Fairway", "Fringe", "Bunker", "LakeSide", "Lake", "Teebox", "Green"]


def _local(p):
    return (-float(p[0]), float(p[2]))  # (east, north); negate x so player's right -> image right


def load_mesh(global_id: int, local_hole: int):
    md = json.loads(mesh_path(global_id, local_hole).read_text())
    return md, {m["name"]: m for m in md["meshes"]}


def _distance_sq_to_route(pt, route):
    """Squared metre distance from a local 2D point to a route polyline."""
    best = math.inf
    for a, b in zip(route, route[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        denom = vx * vx + vy * vy
        t = 0.0 if denom == 0 else max(
            0.0,
            min(1.0, ((pt[0] - a[0]) * vx + (pt[1] - a[1]) * vy) / denom),
        )
        qx, qy = a[0] + t * vx, a[1] + t * vy
        best = min(best, (pt[0] - qx) ** 2 + (pt[1] - qy) ** 2)
    return best


def _setup(
    by,
    tee,
    green,
    oh=FRAME_H,
    min_aspect=FRAME_MIN_ASPECT,
    margin_frac=FRAME_MARGIN,
    route=None,
    route_corridor_m=FRAME_ROUTE_CORRIDOR_M,
):
    """Fill-the-frame projector: the hole fills the height ``oh``; the canvas width is the hole's own
    width (floored at ``min_aspect`` portrait, hole centred), with ``margin_frac`` breathing room.

    Returns ``(project, sc, w, h)`` at SUPERSAMPLED resolution (multiply ``oh``/width by ``SS``).
    ``project`` maps a hole-LOCAL 2D point (east, north metres) to supersampled pixels; handedness is
    identical to the historic frame (larger cross-axis -> left) so nothing mirrors.
    """
    dx, dy = green[0] - tee[0], green[1] - tee[1]
    ln = math.hypot(dx, dy) or 1
    u = (dx / ln, dy / ln)
    perp = (-u[1], u[0])
    # Frame by the union of the surfaces we actually draw (the playing corridor), NOT PlayableBounds:
    # PlayableBounds is a generous, per-hole-varying box that left the hole tiny in a corner and the
    # scale inconsistent between holes. Falls back to PlayableBounds/Rough only if no surface is present.
    pts = [_local(p) for name in ORDER if (m := by.get(name + ".drc")) for p in m["positions"]]
    route_pts = [(float(p[0]), float(p[1])) for p in (route or [])]
    if len(route_pts) >= 2 and pts:
        limit_sq = float(route_corridor_m) ** 2
        # A decoded file can contain surfaces from neighbouring holes.  Those fragments are clipped
        # later and therefore are not visible, but historically they still stretched the canvas.
        # Keep only geometry that could survive the route clip, and include the route itself so a
        # malformed surface cannot crop a dogleg or either endpoint out of the shared projection.
        pts = [p for p in pts if _distance_sq_to_route(p, route_pts) <= limit_sq] + route_pts
    if not pts:
        pb = by.get("PlayableBounds.drc") or by.get("Rough.drc")
        pts = [_local(p) for p in pb["positions"]] if pb else [tee, green]
    pr = [((px - tee[0]) * u[0] + (py - tee[1]) * u[1], (px - tee[0]) * perp[0] + (py - tee[1]) * perp[1]) for px, py in pts]
    amin = min(a for a, _ in pr)
    amax = max(a for a, _ in pr)
    smin = min(s for _, s in pr)
    smax = max(s for _, s in pr)
    aspan = (amax - amin) or 1.0
    sspan = (smax - smin) or 1.0
    amin -= aspan * margin_frac
    amax += aspan * margin_frac
    smin -= sspan * margin_frac
    smax += sspan * margin_frac
    aspan = amax - amin
    sspan = smax - smin
    scx = (smin + smax) / 2.0
    sc_disp = oh / aspan                                  # scale to FILL the along-axis (height)
    ow = max(round(sspan * sc_disp), round(oh * min_aspect))  # width = hole width, floored to portrait
    w, h = ow * SS, int(round(oh)) * SS
    sc = sc_disp * SS

    def project(pt):
        a = (pt[0] - tee[0]) * u[0] + (pt[1] - tee[1]) * u[1]
        s = (pt[0] - tee[0]) * perp[0] + (pt[1] - tee[1]) * perp[1]
        return (w / 2 - (s - scx) * sc, h - (a - amin) * sc)

    return project, sc, w, h


def _fill(d, by, name, color, project, alpha=255):
    m = by.get(name + ".drc")
    if not m:
        return
    pj = [project(_local(p)) for p in m["positions"]]
    col = color + (alpha,)
    for a, b, c in m["faces"]:
        d.polygon([pj[a], pj[b], pj[c]], fill=col)


def _mask(by, name, project, size):
    m = by.get(name + ".drc")
    if not m:
        return None
    mk = Image.new("L", size, 0)
    dd = ImageDraw.Draw(mk)
    pj = [project(_local(p)) for p in m["positions"]]
    for a, b, c in m["faces"]:
        dd.polygon([pj[a], pj[b], pj[c]], fill=255)
    return mk


def _frame(by, route):
    """Single source of truth for the render frame (supersampled projector + canvas).

    Returns ``(project, sc, w, h, margin)``. ``w``/``h`` are supersampled; the display frame is
    ``w // SS`` x ``h // SS`` (variable width, ``FRAME_H`` tall). ``margin`` is the nominal
    breathing room in supersampled px, kept for signature/back-compat (callers derive geometry from
    ``project``, not ``margin``)."""
    project, sc, w, h = _setup(by, tuple(route[0]), tuple(route[-1]), route=route)
    margin = int(round(FRAME_H * FRAME_MARGIN)) * SS
    return project, sc, w, h, margin


def overlay_projector(by, route):
    """Display-pixel projector IDENTICAL to render_hole's overlay route mapping.

    Returns ``to_px((x, y)) -> (px, py)`` taking points in the hole's LOCAL 2D frame
    (hole.json X/Y == (-mesh_x, mesh_z) metres) and yielding post-downsample pixel coords
    on the rendered map — the same frame as ``overlay['route']`` rows, so anything projected
    through it aligns with the map and route by construction.
    """
    project, _sc, _w, _h, _margin = _frame(by, route)

    def to_px(pt):
        x, y = project((float(pt[0]), float(pt[1])))
        return (x / SS, y / SS)

    return to_px


def overlay_unprojector(by, route):
    """``overlay_projector`` 的逆:post-downsample 显示像素 ``(px,py)`` → 本地 2D 米 ``(east,north)``。

    ``project`` 是仿射(把 tee→green 旋转对齐 + 缩放 + 居中);用三点(原点、+X 单位、+Y 单位)
    求出 2x2 线性 + 平移再解逆。与 ``overlay_projector`` 的 ``/SS`` 约定一致,所以两者互逆。
    """
    import numpy as np

    project, _sc, _w, _h, _margin = _frame(by, route)
    o = np.array(project((0.0, 0.0)), dtype=float)
    ex = np.array(project((1.0, 0.0)), dtype=float) - o
    ey = np.array(project((0.0, 1.0)), dtype=float) - o
    minv = np.linalg.inv(np.column_stack([ex, ey]))

    def from_px(pt):
        p = np.array([float(pt[0]) * SS, float(pt[1]) * SS], dtype=float) - o
        xy = minv @ p
        return (float(xy[0]), float(xy[1]))

    return from_px


def render_hole(global_id: int, local_hole: int, route, route_len: float, landing_m=None):
    """Render the hole. Returns (image_data_uri, overlay_meta).

    overlay_meta = {w, h, ppm, ln, route:[[px,py,cumM],...]} in display (post-downsample)
    pixel coords, so a client can map metres<->pixels and place the interactive layer.
    """
    md, by = load_mesh(global_id, local_hole)
    project, sc, w, h, margin = _frame(by, route)
    img = Image.new("RGBA", (w, h), PALETTE["bg"] + (255,))
    d = ImageDraw.Draw(img, "RGBA")
    for name in ORDER:
        _fill(d, by, name, PALETTE[name], project, 235 if name == "TreeArea" else 255)
    fmask = _mask(by, "Fairway", project, (w, h))
    if fmask:
        st = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(st)
        band = 46 * SS
        for i in range(-h, w + h, band * 2):
            sd.polygon([(i, 0), (i + band, 0), (i + band + h, h), (i + h, h)], fill=(255, 255, 255, 26))
        st.putalpha(ImageChops.multiply(st.split()[3], fmask))
        img = Image.alpha_composite(img, st)
    lmask = _mask(by, "Lake", project, (w, h))
    if lmask:
        grad = Image.new("L", (1, h))
        for y in range(h):
            grad.putpixel((0, y), int(20 + 60 * y / h))
        gg = Image.new("RGBA", (w, h), (20, 70, 120, 0))
        gg.putalpha(ImageChops.multiply(grad.resize((w, h)), lmask))
        img = Image.alpha_composite(img, gg)
    d = ImageDraw.Draw(img, "RGBA")
    rnd = random.Random(global_id * 100 + local_hole)
    fol = md.get("foliage", {})

    def tree(px, py, r, c):
        d.ellipse((px - r + 2 * SS, py - r + 3 * SS, px + r + 2 * SS, py + r + 3 * SS), fill=(20, 40, 20, 90))
        d.ellipse((px - r, py - r, px + r, py + r), fill=c + (255,))
        d.ellipse((px - r * 0.55, py - r * 0.7, px + r * 0.25, py - r * 0.05),
                  fill=(min(c[0] + 45, 255), min(c[1] + 55, 255), min(c[2] + 35, 255), 150))

    for it in fol.get("foliage", [])[::3]:
        if "x" not in it:
            continue
        px, py = project(_local([it["x"], it.get("y", 0), it["z"]]))
        r = max(1.5 * SS, min(4 * SS, it.get("s", 1) * 0.25 * SS))
        d.ellipse((px - r, py - r, px + r, py + r), fill=(86, 128, 70, 120))
    for it in fol.get("trees", []):
        if "x" not in it:
            continue
        px, py = project(_local([it["x"], it.get("y", 0), it["z"]]))
        r = max(4 * SS, min(16 * SS, (it.get("s", 1) * 7 + 5) * SS * 0.6))
        tree(px, py, r, rnd.choice([(58, 96, 46), (70, 110, 52), (48, 84, 40), (92, 124, 58)]))

    # clip to this hole's play corridor (drops neighbour holes' fairways/greens)
    corridor = Image.new("L", (w, h), 0)
    cdr = ImageDraw.Draw(corridor)
    rpx = [project(tuple(p)) for p in route]
    rad = int(54 * sc)
    if len(rpx) >= 2:
        try:
            cdr.line(rpx, fill=255, width=rad * 2, joint="curve")
        except TypeError:
            cdr.line(rpx, fill=255, width=rad * 2)
    for q in rpx:
        cdr.ellipse((q[0] - rad, q[1] - rad, q[0] + rad, q[1] + rad), fill=255)
    corridor = corridor.filter(ImageFilter.GaussianBlur(7 * SS))
    bgimg = Image.new("RGBA", (w, h), PALETTE["bg"] + (255,))
    bgimg.paste(img, (0, 0), corridor)
    img = bgimg

    route_px = []
    cum = 0.0
    for i, pt in enumerate(route):
        if i > 0:
            cum += math.hypot(route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1])
        x, y = project(tuple(pt))
        route_px.append([round(x / SS, 1), round(y / SS, 1), round(cum, 1)])
    meta = {"w": w // SS, "h": h // SS, "ppm": round(sc / SS, 4), "ln": round(route_len, 1), "route": route_px}
    small = img.convert("RGB").resize((w // SS, h // SS), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), meta


def render_hole_overlay(global_id: int, local_hole: int, route, route_len: float) -> dict:
    """只出 overlay meta(画框 + route px)——``render_hole`` 便宜的那半,**不渲任何像素**。

    让复盘(round_shot_map)可以把**缓存好的 topo 底图**当底图,同时拿到与之逐字节一致的画框,
    从而 shot 矢量仍对齐、且谁都不在"你看的时候"现画。形状同 ``render_hole`` 返回的 meta。
    """
    _md, by = load_mesh(global_id, local_hole)
    project, sc, w, h, margin = _frame(by, route)
    route_px = []
    cum = 0.0
    for i, pt in enumerate(route):
        if i > 0:
            cum += math.hypot(route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1])
        x, y = project(tuple(pt))
        route_px.append([round(x / SS, 1), round(y / SS, 1), round(cum, 1)])
    return {"w": w // SS, "h": h // SS, "ppm": round(sc / SS, 4), "ln": round(route_len, 1), "route": route_px}
