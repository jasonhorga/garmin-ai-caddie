"""Realistic topo hole renderer — the LOCKED "精致写实 topo" base map (design-system §九).

The server pre-renders this bitmap base once per (course, hole); web / iOS / watch clients
draw their live vector overlays (playing line, shot dots, ball, reticle, yardages) ON TOP.

Built ON TOP of ``hole_render`` and never modifies it. It reuses ``hole_render._frame`` so the
PNG shares the EXACT projection + canvas size as ``hole_render.overlay_projector`` — the overlay
pixel coordinates the prep / shot-map responses already return line up with the topo base by
construction (variable-width portrait frame, ~0.64 minimum aspect). The off-course canvas is
transparent so iPhone/Watch/Web can place the same course asset on their platform-appropriate map
surface instead of baking a phone-style sky colour into every client.

The rich topo texturing is ported from the standalone prototype
(``docs/superpowers/specs/assets/hole-render-topo-prototype.py``) and the locked rules in
``docs/superpowers/specs/2026-07-03-design-system.md`` §九:
  - rough: two-tone fbm mottle + fine tuft grain (organic, not a flat fill)
  - fairway: hard-edge diagonal mow stripes (+6% only, never darker) + faint turf grain
  - green / fringe: manicured checker
  - bunker: sand grain + raked inner-edge depth shadow
  - hillshade: real elevation, luminance-only, ~±7%, NO ambient occlusion (AO turns unsmoothed
    mesh facets into dark triangles); height raster heavily smoothed
  - trees: 1..9 species field (size/brightness), broccoli silhouette + smooth NW->SE gradient +
    fine grain + one soft grounded shadow layer; trees only fall in the side rough, never the
    fairway/green; shadows never darken mown surfaces
  - water: THIS hole's connected lake plus decoded coastal Ocean/VfxOcean/OceanSide surfaces,
    shallow->deep gradient + ripple + bright shoreline
  - green: white target ring + flag on the REAL per-hole green centroid (clustered to the play
    line so a neighbour green never steals the flag)
  - clean super-sampled material edges (no Gaussian blur softening)

NOT baked into the base (they are dynamic per-shot overlays, drawn by the client): the playing
line, yardage pills, tee dot, and the hole/par title card.

Pure rendering — no network, no AI. PIL + numpy only (no scipy / cv2).
"""
from __future__ import annotations

import gc
import io
import math
import os
import random
import sys
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ai_caddie.core.data import ROOT, hazard_path, mesh_path
from ai_caddie.courses import course_prep
from ai_caddie.geometry import hole_render
from ai_caddie.geometry.geometry_authority import authority_path, cache_token

# Bump when the render rules change so previously-cached PNGs are superseded (the cache key
# includes this; old files stay on disk but are never served again).
# topo-v2: fill-the-frame projection (#233) — the hole now fills the height (FRAME_H=1060, variable
# width) instead of floating small in a fixed 720x1120 letterbox. Bump so the pre-#233 cached PNGs
# are superseded and every hole re-renders with the tighter framing.
STYLE_VERSION = "topo-v8"  # v8: bounded coast plus every route-visible water component

# PhysicsMesh is clipped to the same route corridor used by the renderer.  Unlike the decoded
# material layers, it is a continuous terrain authority and therefore cannot add TreeArea spikes.
HOLE_MASK_ROUTE_RADIUS_M = hole_render.FRAME_ROUTE_CORRIDOR_M

SS = hole_render.SS  # supersample factor — MUST match hole_render so the frame downsamples identically
AZ = math.radians(135)  # sun FROM the south-east (Garmin-matched: light in the lower-right)
ALT = math.radians(48)

PAL = {  # Garmin-matched realistic palette (the locked "realistic" panel of the prototype)
    "bg": (145, 196, 253),
    "Rough": (110, 168, 66), "TreeArea": (92, 148, 58),
    "Fairway": (160, 216, 88), "Fringe": (172, 220, 104), "Green": (158, 216, 78),
    "Bunker": (232, 224, 178), "Teebox": (128, 186, 90),
    "Beach": (226, 211, 164), "Cliff": (139, 130, 108), "CliffUV2": (139, 130, 108),
    "rough_lo": np.array([84, 138, 56], np.float32),
    "rough_hi": np.array([138, 190, 86], np.float32),
    "water_shallow": np.array([96, 190, 214], np.float32),
    "water_deep": np.array([2, 122, 172], np.float32),
    "shore": np.array([206, 238, 246], np.float32),
    "edge": (46, 72, 38),
}

ORDER = [
    "Rough", "TreeArea", "Beach", "Cliff", "CliffUV2",
    "Fairway", "Fringe", "Bunker", "Teebox", "Green",
]

# These layers are genuine coastal surfaces in Garmin's decoded course package.  Older renderers
# ignored them, leaving PAL["bg"] visible inside PhysicsMesh; on Cypress 15--17 that looked like a
# flat blue polygon clipped by the PNG edge.  OceanSide is a projected shoreline wall, but including
# it closes small gaps between Ocean and VfxOcean without inventing water beyond source geometry.
OCEAN_LAYERS = ("Ocean", "VfxOcean", "OceanSide")
WATER_LAYERS = ("Lake",) + OCEAN_LAYERS

# TreeArea is deliberately absent: some packages contain neighbouring-hole TreeArea triangles.
# Beach/Cliff are rendered, but also stay out: a coastal strip can continue to the arbitrary mesh
# edge and therefore cannot decide the visible hole envelope.  Only factual playable surfaces do.
ENVELOPE_SUPPORT_LAYERS = (
    "Rough", "Fairway", "Fringe", "Bunker", "Teebox", "Green",
)

ENVELOPE_PADDING_M = 4.0

# id -> distinct top-down tree look (our species field, which Garmin does not expose).
# rad=radius multiplier; base=body, hi=sun highlight, lo=dark underside, dap=dapple clump.
SPECIES = {
    1: dict(rad=1.38, base=(120, 182, 72),  hi=(182, 224, 112), lo=(80, 140, 54),  dap=(150, 204, 92)),
    2: dict(rad=0.80, base=(150, 206, 96),  hi=(200, 232, 132), lo=(106, 168, 68), dap=(174, 218, 112)),
    3: dict(rad=1.06, base=(96, 160, 66),   hi=(154, 200, 104), lo=(60, 116, 48),  dap=(126, 182, 84)),
    4: dict(rad=1.00, base=(132, 194, 84),  hi=(188, 224, 120), lo=(90, 150, 60),  dap=(162, 208, 102)),
    5: dict(rad=1.12, base=(112, 176, 70),  hi=(174, 216, 108), lo=(76, 136, 52),  dap=(146, 198, 90)),
    6: dict(rad=0.92, base=(74, 138, 58),   hi=(130, 182, 96),  lo=(46, 96, 42),   dap=(104, 158, 76)),
    7: dict(rad=0.96, base=(160, 208, 100), hi=(206, 234, 138), lo=(114, 170, 70), dap=(180, 220, 118)),
    8: dict(rad=1.28, base=(100, 166, 66),  hi=(162, 206, 100), lo=(66, 122, 50),  dap=(132, 186, 82)),
    9: dict(rad=0.82, base=(166, 212, 112), hi=(208, 236, 146), lo=(120, 174, 80), dap=(184, 222, 126)),
}


class TopoRenderError(Exception):
    """Base class for topo render failures (never raised through the request path uncaught)."""


class TopoGeometryUnavailable(TopoRenderError):
    """No decoded mesh geometry (or no derivable route) for this (gid, hole) — a 404, not a crash."""


def _local(p):
    # (east, north): negate mesh x so the player's right maps to image right — identical to
    # hole_render._local so points project through hole_render's frame consistently.
    return (-float(p[0]), float(p[2]))


def _font(sz):  # kept for callers that want their own labels; the base map itself draws no text
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            from PIL import ImageFont
            return ImageFont.truetype(path, sz)
        except Exception:
            continue
    from PIL import ImageFont
    return ImageFont.load_default()


def _clip_to_transparent_canvas(img: Image.Image, course_mask: Image.Image) -> Image.Image:
    """Place the clipped course on transparency before shadows/canopies are composited.

    Chroma-keying the final RGB render is insufficient: a tree shadow outside ``course_mask`` has
    already darkened the old blue canvas and therefore no longer equals ``PAL["bg"]``. Starting the
    overlay pass on a real transparent canvas preserves each overlay's own colour and alpha without
    baking any phone-specific sky into the shared asset.
    """
    result = Image.new("RGBA", img.size, (0, 0, 0, 0))
    result.paste(img.convert("RGBA"), (0, 0), course_mask)
    return result


def _route_corridor_mask(size, route_px, sc, radius_m):
    """Binary route corridor in the same supersampled projection as the renderer."""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    radius = max(1, int(round(float(radius_m) * sc)))
    if len(route_px) >= 2:
        try:
            draw.line(route_px, fill=255, width=radius * 2, joint="curve")
        except TypeError:
            draw.line(route_px, fill=255, width=radius * 2)
    for x, y in route_px:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
    return mask


def _ground_envelope(mask_for, fallback: Image.Image) -> Image.Image:
    """Choose continuous terrain; packages without it retain the exact legacy material union."""
    physics = mask_for("PhysicsMesh")
    return physics if physics is not None else fallback


def _combined_water_mask(mask_for) -> Image.Image | None:
    """Union every factual water component; the shared route/ground clip removes neighbour context.

    Selecting only the Lake component nearest the green hid valid earlier hazards on holes with two
    or more lakes.  Keeping the decoded union is both simpler and correct: the final hole corridor
    and bounded terrain envelope already decide which part belongs on this hole's bitmap.
    """
    combined = None
    for name in WATER_LAYERS:
        mask = mask_for(name)
        if mask is not None:
            combined = mask if combined is None else ImageChops.lighter(combined, mask)
    return combined


def _convex_hull(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Small monotone-chain hull used by the silhouette pass (keeps cv2 out of request workers)."""
    unique = sorted(set(points))
    if len(unique) <= 1:
        return unique

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[int, int]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[int, int]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _bounded_route_envelope(
    current_mask: Image.Image,
    support_mask: Image.Image,
    route_px: list[tuple[float, float]],
    pixels_per_metre: float,
    *,
    supersample: int = SS,
    padding_m: float = ENVELOPE_PADDING_M,
) -> Image.Image:
    """Keep the continuous PhysicsMesh shape, but only near this hole's factual surfaces.

    PhysicsMesh is the best continuous outline, yet seaside packages also contain ocean floor all
    the way to an arbitrary mesh/canvas edge.  The old renderer exposed that edge as a rectangular
    blue appendage.  Conversely, using the raw material union brought back neighbouring-hole spikes
    and large gaps.  This pass finds only material components touched by the selected route, wraps
    them in a rounded convex envelope, and intersects that envelope with the continuous current
    mask.  It therefore removes unsupported far-ocean pixels without changing the shared projector.

    Work happens at final display resolution; the result is expanded back to the supersampled mask
    and re-intersected with the original authority, so no pixel outside PhysicsMesh can be invented.
    """
    if current_mask.size != support_mask.size or not route_px:
        return current_mask

    ss = max(1, int(supersample))
    dw = max(1, current_mask.width // ss)
    dh = max(1, current_mask.height // ss)
    display_size = (dw, dh)

    def binary_small(mask: Image.Image) -> Image.Image:
        return mask.resize(display_size, Image.Resampling.NEAREST).point(
            lambda value: 255 if value >= 128 else 0
        )

    current = binary_small(current_mask)
    support = ImageChops.multiply(binary_small(support_mask), current)
    current_np = np.asarray(current, dtype=np.uint8)
    if not np.any(current_np) or not support.getbbox():
        return current_mask

    route_display = [
        (
            max(0, min(dw - 1, int(round(float(x) / ss)))),
            max(0, min(dh - 1, int(round(float(y) / ss)))),
        )
        for x, y in route_px
    ]

    # Label only support components reached by the selected route.  A small metric search tolerates
    # a tee/green centre that sits just outside the rasterised surface.  PIL floodfill is sufficient
    # here and avoids importing a second image-processing runtime into each API worker.
    labelled = support.copy()
    search_px = max(5, int(round(8.0 * float(pixels_per_metre) / ss)))
    touched = False
    for rx, ry in route_display:
        labelled_np = np.asarray(labelled, dtype=np.uint8)
        if labelled_np[ry, rx] == 128:  # this component was already retained
            continue
        x0, x1 = max(0, rx - search_px), min(dw, rx + search_px + 1)
        y0, y1 = max(0, ry - search_px), min(dh, ry + search_px + 1)
        patch = labelled_np[y0:y1, x0:x1]
        ys, xs = np.where(patch == 255)
        if not len(xs):
            continue
        distances = (xs + x0 - rx) ** 2 + (ys + y0 - ry) ** 2
        nearest = int(np.argmin(distances))
        seed = (int(xs[nearest] + x0), int(ys[nearest] + y0))
        ImageDraw.floodfill(labelled, seed, 128, thresh=0)
        touched = True

    labelled_np = np.asarray(labelled, dtype=np.uint8)
    selected = labelled_np == 128 if touched else labelled_np == 255
    # Row extrema are enough for a convex hull and bound the input to at most 2*height points.
    hull_points: list[tuple[int, int]] = []
    for y in np.flatnonzero(np.any(selected, axis=1)):
        xs = np.flatnonzero(selected[y])
        hull_points.append((int(xs[0]), int(y)))
        hull_points.append((int(xs[-1]), int(y)))
    hull_points.extend(route_display)
    hull = _convex_hull(hull_points)
    if len(hull) < 3:
        return current_mask

    min_x = min(point[0] for point in hull)
    max_x = max(point[0] for point in hull)
    min_y = min(point[1] for point in hull)
    max_y = max(point[1] for point in hull)
    requested_padding = max(0, int(round(float(padding_m) * float(pixels_per_metre) / ss)))
    # Always leave at least two final pixels between the bounded envelope and the arbitrary canvas
    # edge.  Normal holes already have the frame's 6% margin, so this cap changes only bad packages.
    edge_clearance = min(min_x, dw - 1 - max_x, min_y, dh - 1 - max_y) - 2
    padding = min(requested_padding, max(0, edge_clearance))

    envelope = Image.new("L", display_size, 0)
    draw = ImageDraw.Draw(envelope)
    draw.polygon(hull, fill=255)
    if padding:
        closed = hull + [hull[0]]
        draw.line(closed, fill=255, width=padding * 2 + 1, joint="curve")
        for x, y in hull:
            draw.ellipse((x - padding, y - padding, x + padding, y + padding), fill=255)

    bounded = ImageChops.multiply(current, envelope)
    if not bounded.getbbox():
        return current_mask
    expanded = bounded.resize(current_mask.size, Image.Resampling.NEAREST)
    return ImageChops.multiply(current_mask, expanded).point(
        lambda value: 255 if value >= 128 else 0
    )


def _fbm(w, h, seed, octaves=5, base_cells=6, persistence=0.55):
    """Fractal value noise (0..1, mean ~0.5) from upscaled random grids. No scipy needed."""
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        cw = base_cells * (2 ** o)
        ch = max(2, int(round(cw * h / w)))
        g = (rng.random((ch, cw)) * 255).astype(np.uint8)
        up = np.asarray(Image.fromarray(g).resize((w, h), Image.BICUBIC), np.float32) / 255.0
        acc += amp * up
        tot += amp
        amp *= persistence
    return np.clip(acc / tot, 0.0, 1.0)


def _build(md, by, route, project, sc, w, h, gid, hole):
    """The rich topo texture pass. Returns an RGBA image at SS resolution."""
    _mcache: dict[str, Image.Image | None] = {}

    def mask_L(name):
        if name in _mcache:
            return _mcache[name]
        m = by.get(name + ".drc")
        if not m:
            _mcache[name] = None
            return None
        mk = Image.new("L", (w, h), 0)
        dd = ImageDraw.Draw(mk)
        pj = [project(_local(p)) for p in m["positions"]]
        for a, b, c in m["faces"]:
            dd.polygon([pj[a], pj[b], pj[c]], fill=255)
        _mcache[name] = mk
        return mk

    def alpha(name):
        mk = mask_L(name)
        return None if mk is None else np.asarray(mk, np.float32) / 255.0

    # ---- height raster + LIGHT hillshade (real elevation, luminance only, NO AO) ----
    light = np.ones((h, w, 1), np.float32)
    terr = by.get("PhysicsMesh.drc") or by.get("Rough.drc")
    if terr is not None:
        pj = [project(_local(p)) for p in terr["positions"]]
        pz = [p[1] for p in terr["positions"]]
        ymin, ymax = min(pz), max(pz)
        ysp = (ymax - ymin) or 1.0
        hraw = Image.new("L", (w, h), 0)
        hd = ImageDraw.Draw(hraw)
        for a, b, c in terr["faces"]:
            cy = (pz[a] + pz[b] + pz[c]) / 3.0
            hd.polygon([pj[a], pj[b], pj[c]], fill=max(1, int(255 * (cy - ymin) / ysp)))
        hraw = hraw.filter(ImageFilter.GaussianBlur(10.0 * SS))  # heavy smooth: no single facet survives
        Hm = np.asarray(hraw, dtype=np.float32) / 255.0 * ysp
        gy, gx = np.gradient(Hm, 1.0 / sc)
        slope = np.arctan(np.hypot(gx, gy))
        aspect = np.arctan2(-gy, gx)
        shade = np.clip(np.sin(ALT) * np.cos(slope) + np.cos(ALT) * np.sin(slope) * np.cos(AZ - aspect), 0, 1)
        light = 1.0 + 0.08 * (shade - 0.5)               # very subtle relief only; NO ambient-occlusion
        light = np.clip(light, 0.94, 1.07)[..., None]

    # ---- flat base fills ----
    img = Image.new("RGB", (w, h), PAL["bg"])
    land_L = Image.new("L", (w, h), 0)
    support_L = Image.new("L", (w, h), 0)
    for name in ORDER:
        mk = mask_L(name)
        if mk is None:
            continue
        img.paste(Image.new("RGB", (w, h), PAL[name]), (0, 0), mk)
        land_L = ImageChops.lighter(land_L, mk)
        if name in ENVELOPE_SUPPORT_LAYERS:
            support_L = ImageChops.lighter(support_L, mk)
    base = np.asarray(img, dtype=np.float32)

    a_rough = alpha("Rough"); a_tree = alpha("TreeArea")
    a_fair = alpha("Fairway"); a_fringe = alpha("Fringe")
    a_green = alpha("Green"); a_bunker = alpha("Bunker"); a_tee = alpha("Teebox")
    a_beach = alpha("Beach")
    a_cliff = alpha("Cliff"); a_cliff_uv = alpha("CliffUV2")
    land_np = (np.asarray(land_L, np.float32) / 255.0)[..., None]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)

    def blend(mask, color):
        if mask is None:
            return
        m = mask[..., None]
        np.copyto(base, base * (1 - m) + color * m)

    def mul(mask, lum):
        if mask is None:
            return
        m = mask[..., None]
        np.copyto(base, base * (1 - m) + np.clip(base * lum, 0, 255) * m)

    # ---- rough: two-tone fbm mottle + fine tufts ----
    if a_rough is not None or a_tree is not None:
        rough_all = np.clip((a_rough if a_rough is not None else 0) +
                            (a_tree if a_tree is not None else 0), 0, 1)
        n = _fbm(w, h, gid * 7 + 11, octaves=5, base_cells=5, persistence=0.58)
        nf = _fbm(w, h, gid * 7 + 23, octaves=3, base_cells=30, persistence=0.5)
        g = np.clip((n - 0.5) * 1.55 + 0.5, 0, 1)[..., None]
        rc = PAL["rough_lo"] * (1 - g) + PAL["rough_hi"] * g
        rc = np.clip(rc * (1 + 0.085 * (nf - 0.5) * 2)[..., None], 0, 255)
        blend(rough_all, rc)

    # ---- fairway mow stripes (hard diagonal bands, +6% only) + fine turf grain ----
    if a_fair is not None:
        th = math.radians(35)
        coord = xx * math.cos(th) + yy * math.sin(th)
        period = 40.0 * SS
        band = np.floor(coord / (period / 2.0)) % 2
        mul(a_fair, (1.0 + 0.06 * band)[..., None])
        fg = _fbm(w, h, gid * 7 + 41, octaves=4, base_cells=20, persistence=0.5)
        mul(a_fair, (1.0 + 0.035 * (fg - 0.5) * 2)[..., None])

    # ---- green + fringe: manicured checker ----
    for gm in (a_fringe, a_green):
        if gm is None:
            continue
        cell = 19.0 * SS
        c1 = 0.5 + 0.5 * np.sin(2 * math.pi * (xx + yy) / cell)
        c2 = 0.5 + 0.5 * np.sin(2 * math.pi * (xx - yy) / cell)
        checker = c1 * c2
        mul(gm, (1 + 0.13 * (checker - 0.32))[..., None])

    # ---- bunker: sand grain + raked inner-edge depth shadow ----
    bmask = mask_L("Bunker")
    if bmask is not None and a_bunker is not None:
        grain = _fbm(w, h, gid * 7 + 53, octaves=4, base_cells=55, persistence=0.5)
        base += ((grain - 0.5) * 2 * 9.0)[..., None] * a_bunker[..., None]
        ksize = int(6 * SS) | 1
        er = bmask.filter(ImageFilter.MinFilter(ksize))
        ring = ImageChops.subtract(bmask, er).filter(ImageFilter.GaussianBlur(2.2 * SS))
        rim = np.asarray(ring, np.float32) / 255.0
        base -= (rim * 30.0)[..., None]
        depth = np.asarray(bmask.filter(ImageFilter.GaussianBlur(15 * SS)), np.float32) / 255.0
        base += ((depth - 0.5) * 10.0)[..., None] * a_bunker[..., None]

    # ---- decoded coast: warm beach grain + muted rock variation (never leave bg-blue holes) ----
    if a_beach is not None:
        beach_grain = _fbm(w, h, gid * 7 + 67, octaves=4, base_cells=42, persistence=0.5)
        base += ((beach_grain - 0.5) * 2 * 8.0)[..., None] * a_beach[..., None]
    cliff_all = None
    if a_cliff is not None or a_cliff_uv is not None:
        cliff_all = np.clip(
            (a_cliff if a_cliff is not None else 0) +
            (a_cliff_uv if a_cliff_uv is not None else 0),
            0,
            1,
        )
        rock = _fbm(w, h, gid * 7 + 71, octaves=4, base_cells=24, persistence=0.55)
        mul(cliff_all, (0.91 + 0.17 * rock)[..., None])

    # ---- hillshade over land; DAMPED on mown surfaces so the fairway/green stay evenly flat-lit ----
    mown = np.clip((a_fair if a_fair is not None else 0) + (a_green if a_green is not None else 0)
                   + (a_fringe if a_fringe is not None else 0) + (a_tee if a_tee is not None else 0),
                   0, 1)[..., None]
    light_eff = 1.0 + (light - 1.0) * (1 - 0.92 * mown)
    np.copyto(base, base * (1 - land_np) + np.clip(base * light_eff, 0, 255) * land_np)

    # ---- every factual water body; the final route/terrain mask removes neighbour context ----
    water_keep = _combined_water_mask(mask_L)

    # ---- water: depth gradient + ripple + bright shoreline ----
    if water_keep is not None:
        lk = np.asarray(water_keep, np.float32) / 255.0
        depth_src = np.asarray(water_keep.filter(ImageFilter.GaussianBlur(22 * SS)), np.float32)
        dn = np.clip(depth_src / (depth_src.max() + 1e-6) * 1.35, 0, 1) * lk
        dn3 = dn[..., None]
        wc = PAL["water_shallow"] * (1 - dn3) + PAL["water_deep"] * dn3
        rip = _fbm(w, h, gid * 7 + 61, octaves=4, base_cells=16, persistence=0.5)
        band = 0.5 + 0.5 * np.sin(2 * math.pi * yy / (7.0 * SS) + (rip - 0.5) * 6)
        wc = np.clip(wc * (1 + 0.05 * (rip - 0.5) * 2 + 0.03 * (band - 0.5) * 2)[..., None], 0, 255)
        lk3 = lk[..., None]
        np.copyto(base, base * (1 - lk3) + wc * lk3)
        ring = np.asarray(ImageChops.subtract(water_keep, water_keep.filter(ImageFilter.GaussianBlur(2.4 * SS))),
                          np.float32)
        ra = np.clip(ring * 3.4 / 255.0, 0, 1)[..., None]
        np.copyto(base, base * (1 - ra) + PAL["shore"] * ra)

    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))

    # ---- corridor + hard clip to continuous terrain ∪ kept water (drops neighbour holes) ----
    rpx = [project(tuple(p)) for p in route]

    def corridor(radius_m):
        return _route_corridor_mask((w, h), rpx, sc, radius_m)

    corr = corridor(HOLE_MASK_ROUTE_RADIUS_M)
    # PhysicsMesh is the continuous terrain authority.  Rough/TreeArea/paths are material layers
    # with holes and neighbouring polygons; unioning them for alpha caused the reported spikes.
    # Older/partial packages retain the legacy all-land union instead of using Rough alone (Rough
    # has intentional fairway/green cut-outs and is therefore not a complete fallback envelope).
    ground_envelope = _ground_envelope(mask_L, land_L)
    hole_mask = ImageChops.multiply(ground_envelope, corr).point(lambda v: 255 if v >= 128 else 0)
    if water_keep is not None:
        visible_water = ImageChops.multiply(water_keep, corr).point(lambda v: 255 if v >= 128 else 0)
        hole_mask = ImageChops.lighter(hole_mask, visible_water)
    hole_mask = _bounded_route_envelope(hole_mask, support_L, rpx, sc)
    img = _clip_to_transparent_canvas(img, hole_mask)
    outline = ImageChops.difference(hole_mask, hole_mask.filter(ImageFilter.MinFilter(3)))
    stroke = Image.new("RGBA", (w, h), PAL["edge"] + (0,))
    stroke.putalpha(outline.point(lambda v: int(v * 0.55)))
    img = Image.alpha_composite(img, stroke)

    # ---- crisp material boundary strokes (clean edges; no blur) ----
    def add_stroke(name, rgb, wpx, a):
        mk = mask_L(name)
        if mk is None:
            return None
        er = mk.filter(ImageFilter.MinFilter(wpx * 2 + 1))
        edge = ImageChops.multiply(ImageChops.subtract(mk, er), hole_mask)
        ov = Image.new("RGBA", (w, h), rgb + (0,))
        ov.putalpha(edge.point(lambda v: a if v > 60 else 0))
        return ov
    for _nm, _rgb, _wp, _a in [("Fairway", (92, 146, 54), 1, 130),
                               ("Bunker", (150, 132, 86), 1, 160),
                               ("Green", (70, 146, 52), 1, 205)]:
        _ov = add_stroke(_nm, _rgb, _wp, _a)
        if _ov is not None:
            img = Image.alpha_composite(img, _ov)

    # ---- trees: species-differentiated canopies (treeline in rough; none on the fairway) ----
    fmask = mask_L("Fairway")
    fair_np = np.asarray(fmask, np.uint8) if fmask is not None else None
    hole_np = np.asarray(hole_mask, np.uint8)
    trees = md.get("foliage", {}).get("trees", [])
    hdx, hdy = 0.7071, 0.7071          # highlight toward the sun (SE, lower-right)
    sdx, sdy = -0.7071, -0.7071        # shadow toward NW (upper-left)
    rnd = random.Random(gid * 131 + hole)

    placed = []
    for it in trees:
        if "x" not in it:
            continue
        px, py = project(_local([it["x"], it.get("y", 0), it["z"]]))
        ix, iy = int(px), int(py)
        if not (0 <= ix < w and 0 <= iy < h):
            continue
        if hole_np[iy, ix] < 128:
            continue
        if fair_np is not None and fair_np[iy, ix] > 127:
            continue
        spec = SPECIES.get(int(it.get("id", 4)), SPECIES[4])
        s = float(it.get("s", 0.7))
        r = (6.8 + s * 8.4) * SS * spec["rad"] * (0.92 + 0.16 * rnd.random())
        r = max(7.0 * SS, min(19.5 * SS, r))
        placed.append((px, py, r, spec, rnd.randint(0, 1 << 30)))
    placed.sort(key=lambda t: t[1])   # far (top) first so near trees overlap

    # (1) soft grounded shadows in one blurred pass
    shp = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ds = ImageDraw.Draw(shp, "RGBA")
    for px, py, r, spec, sd in placed:
        so = r * 0.95
        ds.ellipse((px + sdx * so - r * 1.15, py + sdy * so - r * 0.70,
                    px + sdx * so + r * 1.15, py + sdy * so + r * 0.70), fill=(32, 54, 32, 92))
    shp = shp.filter(ImageFilter.GaussianBlur(3.4 * SS))
    sa = np.asarray(shp.split()[3], np.float32) * (1 - 0.92 * mown[..., 0])  # keep shadows off mown turf
    shp.putalpha(Image.fromarray(np.clip(sa, 0, 255).astype(np.uint8)))
    img = Image.alpha_composite(img, shp)

    # (2) canopies on a dedicated layer, composited once at the end
    canopy = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(canopy, "RGBA")

    def draw_broadleaf(px, py, r, spec, rng):
        base_c = spec["base"]
        R = max(3, int(round(r)))
        pad = int(R * 0.30) + 6
        T = R * 2 + pad * 2
        c = R + pad
        tile = Image.new("RGBA", (T, T), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile, "RGBA")

        def te(cx, cy, rr, fill):
            td.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=fill)

        te(c, c, R * 0.74, base_c + (255,))
        nl = rng.randint(8, 11)
        a0 = rng.uniform(0, 2 * math.pi)
        for k in range(nl):
            ang = a0 + 2 * math.pi * k / nl + rng.uniform(-0.16, 0.16)
            rad = R * rng.uniform(0.36, 0.52)
            te(c + math.cos(ang) * rad, c + math.sin(ang) * rad,
               R * rng.uniform(0.38, 0.50), base_c + (255,))
        nrng = np.random.default_rng(rng.randint(0, 2 ** 31 - 1))
        low = (nrng.random((max(3, T // 7), max(3, T // 7))) * 255).astype(np.uint8)
        grain = np.asarray(Image.fromarray(low).resize((T, T), Image.BICUBIC), np.float32) / 255.0
        arr = np.asarray(tile, np.float32)
        yy2, xx2 = np.mgrid[0:T, 0:T].astype(np.float32)
        dsh = np.clip(((xx2 - c) * sdx + (yy2 - c) * sdy) / (R + 1e-3), -1.15, 1.15)
        fac = 1.0 - dsh * 0.16                       # NW (shadow) darker, SE (sun) brighter
        grainf = 1.0 + (grain - 0.5) * 0.12          # subtle broccoli grain
        rgb = np.clip(arr[..., :3] * (fac * grainf)[..., None], 0, 255)
        tile = Image.fromarray(np.concatenate([rgb, arr[..., 3:4]], -1).astype(np.uint8))
        tile = tile.filter(ImageFilter.GaussianBlur(max(0.6, R * 0.05)))
        cw, ch = tile.width, tile.height
        canopy.paste(tile, (int(round(px)) - cw // 2, int(round(py)) - ch // 2), tile)

    for px, py, r, spec, sd in placed:
        draw_broadleaf(px, py, r, spec, random.Random(sd))

    img = Image.alpha_composite(img, canopy)
    return img


def _draw_green_marker(img, project, by, route):
    """LOCKED green treatment: white target ring + flag on the REAL per-hole green centroid.

    Clusters green vertices near the play-line end so a neighbour hole's green never steals the
    flag. Draws directly on the SS image (downsampled with everything else)."""
    gm = by.get("Green.drc")
    if not gm:
        return img
    input_mode = img.mode
    marker = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(marker, "RGBA")
    component = course_prep.selected_green_component(by, route)
    if not component:
        return img
    near = [_local(gm["positions"][index]) for index in component["vertex_indices"]]
    cx = sum(p[0] for p in near) / len(near)
    cz = sum(p[1] for p in near) / len(near)
    gpx = [project(p) for p in near]
    gxs = [p[0] for p in gpx]; gys = [p[1] for p in gpx]
    rx = (max(gxs) - min(gxs)) / 2 + 6 * SS
    ry = (max(gys) - min(gys)) / 2 + 6 * SS
    gcx, gcy = project((cx, cz))
    d.ellipse((gcx - rx, gcy - ry, gcx + rx, gcy + ry), outline=(255, 255, 255, 235), width=2 * SS)
    d.ellipse((gcx - rx - 3 * SS, gcy - ry - 3 * SS, gcx + rx + 3 * SS, gcy + ry + 3 * SS),
              outline=(40, 70, 40, 150), width=SS)
    pole = 30 * SS
    d.line([(gcx, gcy), (gcx, gcy - pole)], fill=(250, 250, 250, 255), width=2 * SS)
    d.polygon([(gcx, gcy - pole), (gcx + 17 * SS, gcy - pole + 7 * SS), (gcx, gcy - pole + 14 * SS)],
              fill=(228, 58, 58, 255))
    d.ellipse((gcx - 3 * SS, gcy - 3 * SS, gcx + 3 * SS, gcy + 3 * SS), fill=(30, 30, 30, 255))
    composited = Image.alpha_composite(img.convert("RGBA"), marker)
    return composited if input_mode == "RGBA" else composited.convert(input_mode)


def _draw_tee_marker(img, project, by, route):
    """Small tee-box pad on the REAL tee point (``route[0]``), oriented along the play direction —
    the mirror of the green flag at the other end, marking where you tee off. Uses ``project`` so it
    lands on the actual tee (not the frame edge). Drawn on the SS image, downsampled with the rest."""
    if not route or len(route) < 2:
        return img
    input_mode = img.mode
    marker = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(marker, "RGBA")
    tpx, tpy = project(route[0])
    npx, npy = project(route[1])
    dx, dy = npx - tpx, npy - tpy
    ln = math.hypot(dx, dy) or 1.0
    ux, uy = dx / ln, dy / ln            # unit vector along the play direction
    qx, qy = -uy, ux                     # unit vector perpendicular (across the tee)
    hl, hw = 8 * SS, 13 * SS              # pad half-length (along) / half-width (across); tee boxes read wide
    corners = [
        (tpx + ux * hl + qx * hw, tpy + uy * hl + qy * hw),
        (tpx + ux * hl - qx * hw, tpy + uy * hl - qy * hw),
        (tpx - ux * hl - qx * hw, tpy - uy * hl - qy * hw),
        (tpx - ux * hl + qx * hw, tpy - uy * hl + qy * hw),
    ]
    # lighter mowed-green pad so it reads as a manicured tee box against the darker rough
    d.polygon(corners, fill=(170, 200, 120, 180))
    d.line(corners + [corners[0]], fill=(240, 240, 240, 225), width=SS)
    # two tee markers straddling the play line at the front edge (the classic tee-box look)
    fx, fy = tpx + ux * hl, tpy + uy * hl
    for s in (1.0, -1.0):
        mx, my = fx + qx * hw * 0.62 * s, fy + qy * hw * 0.62 * s
        d.ellipse((mx - 3 * SS, my - 3 * SS, mx + 3 * SS, my + 3 * SS), fill=(250, 250, 250, 240))
    composited = Image.alpha_composite(img.convert("RGBA"), marker)
    return composited if input_mode == "RGBA" else composited.convert(input_mode)


def render_hole_topo_image(gid: int, hole: int) -> Image.Image:
    """Render the LOCKED realistic topo base for (gid, hole) as a downsampled RGBA PIL image
    (the same variable-width frame as ``hole_render.overlay_projector``).

    Raises ``TopoGeometryUnavailable`` when the hole has no decoded geometry or no derivable
    route — the caller turns that into a 404. Any other rendering error propagates as a
    ``TopoRenderError`` so the request path can 404 rather than 500.
    """
    gid = int(gid)
    hole = int(hole)
    if not mesh_path(gid, hole).exists():
        raise TopoGeometryUnavailable(f"no geometry mesh for gid{gid} hole{hole}")
    try:
        md, by = hole_render.load_mesh(gid, hole)
        route, route_len = course_prep.derive_route(md)
        if not route or not route_len:
            raise TopoGeometryUnavailable(f"no derivable route for gid{gid} hole{hole}")
        project, sc, w, h, _margin = hole_render._frame(by, route)
        img = _build(md, by, route, project, sc, w, h, gid, hole)
        img = _draw_green_marker(img, project, by, route)
        img = _draw_tee_marker(img, project, by, route)
        return img.resize((w // SS, h // SS), Image.LANCZOS)
    except TopoGeometryUnavailable:
        raise
    except Exception as exc:  # a malformed mesh must 404, never crash the worker
        raise TopoRenderError(f"topo render failed for gid{gid} hole{hole}: {exc}") from exc


def render_hole_topo(gid: int, hole: int) -> bytes:
    """Render (gid, hole) and return PNG bytes. Raises ``TopoGeometryUnavailable`` /
    ``TopoRenderError`` on failure (never crashes the caller)."""
    img = render_hole_topo_image(gid, hole)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Render-once-then-cache: keyed by gid / hole / STYLE_VERSION on disk. First hit renders
# (~seconds), later hits read the cached bytes. Override the directory with
# AI_CADDIE_TOPO_CACHE_DIR (tests point it at a tmp dir).
# ---------------------------------------------------------------------------
def cache_dir() -> Path:
    override = os.environ.get("AI_CADDIE_TOPO_CACHE_DIR")
    root = Path(override) if override else (ROOT / "output" / "topo_render_cache")
    return root / STYLE_VERSION


def cache_identity(gid: int, hole: int) -> str:
    mesh_file = mesh_path(gid, hole)
    token = cache_token(
        global_id=int(gid),
        local_hole=int(hole),
        mesh_file=mesh_file,
        hazard_file=hazard_path(gid, hole),
        sidecar=authority_path(mesh_file),
    )
    return f"{STYLE_VERSION}-{token}"


def cache_path(gid: int, hole: int) -> Path:
    return cache_dir() / f"gid{int(gid)}_h{int(hole):02d}_{cache_identity(gid, hole)}.png"


_cache_lock = threading.Lock()
_cache_inflight: dict[Path, threading.Event] = {}
# A cold supersampled render owns several large NumPy rasters at once.  Different holes used to
# render concurrently (the per-path singleflight only protects duplicate requests), so an iPhone
# download plus Web/Watch prewarm could multiply that peak until the API host swapped or died.
# Serialise cold renders process-wide; warm PNG reads never take this gate.
_cold_render_slot = threading.BoundedSemaphore(1)


def _release_cold_render_working_set() -> None:
    """Return supersampled render arenas to Linux after a cold render.

    A render briefly owns several large PIL/NumPy buffers. Python releases those objects, but
    glibc normally retains their arenas, so a worker that pre-renders a course can remain multiple
    gigabytes larger even though no render object is reachable. ``malloc_trim`` returns those free
    pages to the OS. It is a best-effort Linux/glibc optimisation and must never affect rendering on
    Darwin or another libc.
    """
    gc.collect()
    if not sys.platform.startswith("linux"):
        return
    try:
        import ctypes

        malloc_trim = ctypes.CDLL(None).malloc_trim
        malloc_trim.argtypes = [ctypes.c_size_t]
        malloc_trim.restype = ctypes.c_int
        malloc_trim(0)
    except Exception:
        # musl and other C libraries may not export malloc_trim. Cache correctness and the response
        # must never depend on an optional allocator hint.
        return


def _read_cached_topo(path: Path) -> bytes | None:
    if not path.exists():
        return None
    try:
        cached = path.read_bytes()
    except OSError:
        return None
    try:
        # Atomic writes prevent readers from observing our own half-written file, but they cannot
        # protect a persistent volume from truncation or corruption. Never serve arbitrary non-empty
        # bytes as image/png forever: discard an invalid entry and let the normal singleflight path
        # rebuild it from the current Garmin geometry authority.
        with Image.open(io.BytesIO(cached)) as image:
            if image.format != "PNG":
                raise ValueError("cached topo is not PNG")
            image.verify()
        return cached
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def render_hole_topo_cached(gid: int, hole: int) -> bytes:
    """PNG bytes for (gid, hole, geometry authority), cached after the first render.

    Raises ``TopoGeometryUnavailable`` when the hole has no geometry (cheap ``mesh_path``
    check — negatives are not cached, they just fail fast) and ``TopoRenderError`` on a
    malformed mesh. A Garmin geometry update changes the cache identity and therefore
    cannot reuse the previous release's bitmap."""
    path = cache_path(gid, hole)
    if cached := _read_cached_topo(path):
        return cached

    # AsyncImage, the phone's offline cache, Watch transfer and Web may request the same cold hole
    # together. Rendering each copy wastes tens of seconds of CPU and can block unrelated catalogue
    # requests. One process-level leader renders; followers reuse its atomic cache result.
    with _cache_lock:
        if cached := _read_cached_topo(path):
            return cached
        waiter = _cache_inflight.get(path)
        if waiter is None:
            waiter = threading.Event()
            _cache_inflight[path] = waiter
            is_leader = True
        else:
            is_leader = False

    if not is_leader:
        waiter.wait()
        if cached := _read_cached_topo(path):
            return cached
        # The leader failed before producing a cache file. Become the next leader and preserve the
        # endpoint's existing honest 404/error behaviour instead of returning invented bytes.
        return render_hole_topo_cached(gid, hole)

    try:
        with _cold_render_slot:
            try:
                png = render_hole_topo(gid, hole)  # raises before any cache write
            finally:
                _release_cold_render_working_set()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".png.tmp")
            tmp.write_bytes(png)
            os.replace(tmp, path)  # atomic: concurrent readers never see a half-written file
        except OSError:
            pass  # cache write is best-effort; still return the freshly rendered bytes
        return png
    finally:
        with _cache_lock:
            _cache_inflight.pop(path, None)
            waiter.set()
