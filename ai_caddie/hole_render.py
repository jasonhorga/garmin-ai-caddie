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

from ai_caddie.data import mesh_path
from measure_prodgeometry_distances import mesh_components  # noqa: F401  (kept for parity / callers)

import json

SS = 2  # supersample factor
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


def _setup(by, tee, green, w, h, margin):
    dx, dy = green[0] - tee[0], green[1] - tee[1]
    ln = math.hypot(dx, dy) or 1
    u = (dx / ln, dy / ln)
    perp = (-u[1], u[0])
    # Frame by the union of the surfaces we actually draw (the playing corridor), NOT PlayableBounds:
    # PlayableBounds is a generous, per-hole-varying box that left the hole tiny in a corner and the
    # scale inconsistent between holes. Falls back to PlayableBounds/Rough only if no surface is present.
    pts = [_local(p) for name in ORDER if (m := by.get(name + ".drc")) for p in m["positions"]]
    if not pts:
        pb = by.get("PlayableBounds.drc") or by.get("Rough.drc")
        pts = [_local(p) for p in pb["positions"]] if pb else [tee, green]
    pr = [((px - tee[0]) * u[0] + (py - tee[1]) * u[1], (px - tee[0]) * perp[0] + (py - tee[1]) * perp[1]) for px, py in pts]
    amin = min(a for a, _ in pr) - 14
    amax = max(a for a, _ in pr) + 14
    smin = min(s for _, s in pr) - 14
    smax = max(s for _, s in pr) + 14
    sc = min((w - 2 * margin) / (smax - smin), (h - 2 * margin) / (amax - amin))
    cx = (smin + smax) / 2

    def project(pt):
        a = (pt[0] - tee[0]) * u[0] + (pt[1] - tee[1]) * u[1]
        s = (pt[0] - tee[0]) * perp[0] + (pt[1] - tee[1]) * perp[1]
        return (w / 2 - (s - cx) * sc, h - margin - (a - amin) * sc)

    return project, sc


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
    """Single source of truth for the render frame (supersampled projector + canvas)."""
    w, h = 720 * SS, 1120 * SS
    margin = 40 * SS
    project, sc = _setup(by, tuple(route[0]), tuple(route[-1]), w, h, margin)
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
