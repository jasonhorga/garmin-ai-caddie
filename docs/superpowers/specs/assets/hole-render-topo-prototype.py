"""Standalone topo hole renderer (does NOT touch shared hole_render.py). gid31795 h1.
v4 — light A only, RICH TEXTURE pass. Benchmarked against the Garmin official reference.
  Surfaces are no longer flat:
  - Rough: fbm two-tone mottling + fine tuft noise (organic, not a flat fill).
  - Fairway: soft alternating mow stripes (diagonal) + faint mottle.
  - Green/Fringe: manicured checker/crosshatch texture.
  - Water: shallow->deep gradient + ripple + bright cyan shoreline.
  - Bunker: sand grain + raked inner-edge depth shadow.
  - Trees: species-differentiated volumetric canopies (id 1..9 -> distinct size/shape/warm-cool
    green: round broadleaf / spiky top-down conifer / columnar oval), dappled clumping, sun-side
    highlight + dark underside, soft grounded cast shadows (single blurred pass). This is where we
    beat Garmin: we render the real species field it doesn't expose.
  - hillshade: real-elevation relief, luminance-only (colours stay vivid).
Keeps every v3 structural win: fill-the-frame framing, flag on the real green centroid + white
  target ring, this hole's connected water only, dashed play line, yard pills, tee dot, title card.
  NO contour lines, NO "S" bunker letters.
"""
import math, time, sys, random
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, "/home/ubuntu/claude-web-data/repo/garmin-ai-caddie")
from ai_caddie.geometry import hole_render
from ai_caddie.courses import course_prep

GID, HOLE = 31795, 1
SS = 2
AZ = math.radians(135)          # light FROM the south-east (matches Garmin: sun lower-right)
ALT = math.radians(48)
YARD = 1.09361
OUTDIR = "/tmp/claude-1000/-home-ubuntu-claude-web-data-repo-garmin-ai-caddie/fd54adc1-8919-4101-8ac1-18473cebd965/scratchpad"

PAL = {  # Garmin-matched light palette
    "bg": (145, 196, 253),
    "Rough": (110, 168, 66), "TreeArea": (92, 148, 58),
    "Fairway": (160, 216, 88), "Fringe": (172, 220, 104), "Green": (158, 216, 78),
    "Bunker": (232, 224, 178), "Teebox": (128, 186, 90),
    "rough_lo": np.array([84, 138, 56], np.float32),
    "rough_hi": np.array([138, 190, 86], np.float32),
    "water_shallow": np.array([96, 190, 214], np.float32),
    "water_deep": np.array([2, 122, 172], np.float32),
    "shore": np.array([206, 238, 246], np.float32),
    "edge": (46, 72, 38),
}
STYLE = "realistic"   # "realistic" | "flat" | "ghibli" — set per panel by render()
_REAL_PAL = dict(PAL)

GHIBLI_PAL = {  # warm hand-painted watercolour palette
    "bg": (152, 202, 236),
    "Rough": (122, 166, 78), "TreeArea": (102, 148, 66),
    "Fairway": (176, 212, 110), "Fringe": (188, 220, 126), "Green": (178, 216, 108),
    "Bunker": (240, 224, 172), "Teebox": (142, 186, 98),
    "rough_lo": np.array([106, 150, 70], np.float32),
    "rough_hi": np.array([154, 196, 108], np.float32),
    "water_shallow": np.array([126, 198, 210], np.float32),
    "water_deep": np.array([58, 140, 176], np.float32),
    "shore": np.array([216, 238, 240], np.float32),
    "edge": (78, 94, 58),
}
FLAT_PAL = {  # clean flat vector palette (solid blocks, no texture)
    "bg": (152, 206, 246),
    "Rough": (104, 176, 74), "TreeArea": (96, 162, 66),
    "Fairway": (150, 214, 92), "Fringe": (172, 224, 112), "Green": (150, 216, 84),
    "Bunker": (242, 228, 168), "Teebox": (128, 192, 88),
    "rough_lo": np.array([104, 176, 74], np.float32),
    "rough_hi": np.array([104, 176, 74], np.float32),
    "water_shallow": np.array([80, 188, 226], np.float32),
    "water_deep": np.array([80, 188, 226], np.float32),
    "shore": np.array([80, 188, 226], np.float32),
    "edge": (38, 72, 40),
}

ORDER = ["Rough", "TreeArea", "Fairway", "Fringe", "Bunker", "Teebox", "Green"]
BBOX_LAYERS = ORDER + ["Lake"]

# id -> distinct top-down tree look. rad=radius mult; shape=round|conifer|oval.
#   base=body, hi=sun highlight, lo=dark underside/edge, dap=dapple clump colour.
SPECIES = {  # all broccoli-round like Garmin; variety comes from brightness+size (our species field)
    1: dict(rad=1.38, shape="round", base=(120, 182, 72),  hi=(182, 224, 112), lo=(80, 140, 54),  dap=(150, 204, 92)),   # big lime oak
    2: dict(rad=0.80, shape="round", base=(150, 206, 96),  hi=(200, 232, 132), lo=(106, 168, 68), dap=(174, 218, 112)),  # small bright lime
    3: dict(rad=1.06, shape="round", base=(96, 160, 66),   hi=(154, 200, 104), lo=(60, 116, 48),  dap=(126, 182, 84)),   # mid-green
    4: dict(rad=1.00, shape="round", base=(132, 194, 84),  hi=(188, 224, 120), lo=(90, 150, 60),  dap=(162, 208, 102)),  # generic lime
    5: dict(rad=1.12, shape="round", base=(112, 176, 70),  hi=(174, 216, 108), lo=(76, 136, 52),  dap=(146, 198, 90)),   # mid
    6: dict(rad=0.92, shape="round", base=(74, 138, 58),   hi=(130, 182, 96),  lo=(46, 96, 42),   dap=(104, 158, 76)),   # deep green
    7: dict(rad=0.96, shape="round", base=(160, 208, 100), hi=(206, 234, 138), lo=(114, 170, 70), dap=(180, 220, 118)),  # yellow-green
    8: dict(rad=1.28, shape="round", base=(100, 166, 66),  hi=(162, 206, 100), lo=(66, 122, 50),  dap=(132, 186, 82)),   # big mid-green
    9: dict(rad=0.82, shape="round", base=(166, 212, 112), hi=(208, 236, 146), lo=(120, 174, 80), dap=(184, 222, 126)),  # ornamental bright
}


def _local(p):
    return (-float(p[0]), float(p[2]))


def font(sz):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            continue
    return ImageFont.load_default()


def fbm(w, h, seed, octaves=5, base_cells=6, persistence=0.55):
    """Fractal value noise (0..1, mean ~0.5) built from upscaled random grids. No scipy needed."""
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


def make_frame(by, route):
    """Projector that FILLS the canvas by the hole polygon-union bbox (uniform scale, ~6% margin)."""
    tee, green_end = tuple(route[0]), tuple(route[-1])
    dx, dy = green_end[0] - tee[0], green_end[1] - tee[1]
    ln = math.hypot(dx, dy) or 1.0
    u = (dx / ln, dy / ln)
    perp = (u[1], -u[0])        # v5: flip handedness of the cross-axis so orientation matches Garmin
                               # (water ends up TOP-RIGHT, creek LEFT) — mirror fixed in the transform,
                               # not by flipping the final PNG (title text stays correct).
    pts = []
    for name in BBOX_LAYERS:
        m = by.get(name + ".drc")
        if m:
            pts.extend(_local(p) for p in m["positions"])
    if not pts:
        pts = [tee, green_end]

    def along_side(p):
        return ((p[0] - tee[0]) * u[0] + (p[1] - tee[1]) * u[1],
                (p[0] - tee[0]) * perp[0] + (p[1] - tee[1]) * perp[1])

    rot = [along_side(p) for p in pts]
    amin = min(a for a, _ in rot); amax = max(a for a, _ in rot)
    smin = min(s for _, s in rot); smax = max(s for _, s in rot)
    aspan = (amax - amin) or 1.0; sspan = (smax - smin) or 1.0
    marg = 0.06
    amin -= aspan * marg; amax += aspan * marg
    smin -= sspan * marg; smax += sspan * marg
    aspan = amax - amin; sspan = smax - smin

    OH = 1060
    sc_disp = OH / aspan
    hole_w = sspan * sc_disp
    OW = max(round(hole_w), round(OH * 0.64))   # pad to Garmin-ish portrait; hole centred, sky on the sides
    xoff_px = (OW - hole_w) / 2.0 * SS
    w, h = OW * SS, OH * SS
    sc = sc_disp * SS

    def project(pt):
        a = (pt[0] - tee[0]) * u[0] + (pt[1] - tee[1]) * u[1]
        s = (pt[0] - tee[0]) * perp[0] + (pt[1] - tee[1]) * perp[1]
        return ((s - smin) * sc + xoff_px, h - (a - amin) * sc)

    return project, sc, w, h


def build(md, by, route):
    project, sc, w, h = make_frame(by, route)
    _mcache = {}

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

    # ---- height raster + LIGHT hillshade (real elevation, luminance only) ----
    terr = by.get("PhysicsMesh.drc") or by.get("Rough.drc")
    pj = [project(_local(p)) for p in terr["positions"]]
    pz = [p[1] for p in terr["positions"]]
    ymin, ymax = min(pz), max(pz)
    ysp = (ymax - ymin) or 1.0
    hraw = Image.new("L", (w, h), 0)
    hd = ImageDraw.Draw(hraw)
    for a, b, c in terr["faces"]:
        cy = (pz[a] + pz[b] + pz[c]) / 3.0
        hd.polygon([pj[a], pj[b], pj[c]], fill=max(1, int(255 * (cy - ymin) / ysp)))
    hraw = hraw.filter(ImageFilter.GaussianBlur(10.0 * SS))  # heavy smooth: no single mesh facet survives
    Hm = np.asarray(hraw, dtype=np.float32) / 255.0 * ysp
    gy, gx = np.gradient(Hm, 1.0 / sc)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gy, gx)
    shade = np.clip(np.sin(ALT) * np.cos(slope) + np.cos(ALT) * np.sin(slope) * np.cos(AZ - aspect), 0, 1)
    light = 1.0 + 0.08 * (shade - 0.5)               # very subtle relief only; NO ambient-occlusion
    light = np.clip(light, 0.94, 1.07)[..., None]    # (AO was what darkened the facet into a triangle)

    # ---- flat base fills ----
    img = Image.new("RGB", (w, h), PAL["bg"])
    land_L = Image.new("L", (w, h), 0)
    for name in ORDER:
        mk = mask_L(name)
        if mk is None:
            continue
        img.paste(Image.new("RGB", (w, h), PAL[name]), (0, 0), mk)
        land_L = ImageChops.lighter(land_L, mk)
    base = np.asarray(img, dtype=np.float32)

    a_rough = alpha("Rough"); a_tree = alpha("TreeArea")
    a_fair = alpha("Fairway"); a_fringe = alpha("Fringe")
    a_green = alpha("Green"); a_bunker = alpha("Bunker"); a_tee = alpha("Teebox")
    land_np = (np.asarray(land_L, np.float32) / 255.0)[..., None]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)

    def blend(mask, color):        # replace base colour where mask>0
        if mask is None:
            return
        m = mask[..., None]
        np.copyto(base, base * (1 - m) + color * m)

    def mul(mask, lum):            # luminance multiply where mask>0
        if mask is None:
            return
        m = mask[..., None]
        np.copyto(base, base * (1 - m) + np.clip(base * lum, 0, 255) * m)

    # ---- rough: two-tone fbm mottle + fine tufts (skipped for flat vector style) ----
    rough_all = None
    if STYLE != "flat" and (a_rough is not None or a_tree is not None):
        rough_all = np.clip((a_rough if a_rough is not None else 0) +
                            (a_tree if a_tree is not None else 0), 0, 1)
        n = fbm(w, h, GID * 7 + 11, octaves=5, base_cells=5, persistence=0.58)
        nf = fbm(w, h, GID * 7 + 23, octaves=3, base_cells=30, persistence=0.5)
        g = np.clip((n - 0.5) * 1.55 + 0.5, 0, 1)[..., None]
        rc = PAL["rough_lo"] * (1 - g) + PAL["rough_hi"] * g
        rc = np.clip(rc * (1 + 0.085 * (nf - 0.5) * 2)[..., None], 0, 255)
        blend(rough_all, rc)
        # (TreeArea no longer darkened as a block — that made an angular geometric patch under the
        #  clusters; the trees' own cast shadows already darken the ground beneath them.)

    # ---- fairway mow stripes (style-dependent; flat = none) ----
    if a_fair is not None and STYLE != "flat":
        th = math.radians(35)                          # diagonal (lower-left -> upper-right)
        coord = xx * math.cos(th) + yy * math.sin(th)
        period = 40.0 * SS
        if STYLE == "ghibli":
            s = 0.5 + 0.5 * np.sin(2 * math.pi * coord / period)
            lum = 1.0 + 0.05 * s                               # soft painterly bands
        else:
            band = np.floor(coord / (period / 2.0)) % 2        # crisp hard bands (never darker than base)
            lum = 1.0 + 0.06 * band
        mul(a_fair, lum[..., None])
        # subtle turf grain on top of the stripes — a little life, NOT the old low-freq 'dirty' mottle
        fg = fbm(w, h, GID * 7 + 41, octaves=4, base_cells=20, persistence=0.5)
        mul(a_fair, (1.0 + 0.035 * (fg - 0.5) * 2)[..., None])

    # ---- green + fringe: manicured checker (skipped for flat) ----
    for gm in ((a_fringe, a_green) if STYLE != "flat" else ()):
        if gm is None:
            continue
        cell = 19.0 * SS
        c1 = 0.5 + 0.5 * np.sin(2 * math.pi * (xx + yy) / cell)
        c2 = 0.5 + 0.5 * np.sin(2 * math.pi * (xx - yy) / cell)
        checker = c1 * c2
        lum = 1 + 0.13 * (checker - 0.32)
        mul(gm, lum[..., None])

    # ---- teebox: kept FLAT (the fine diagonal stripe made the small tee ovals look like
    #      striped coins scattered in the rough); a plain mowed patch reads correctly ----

    # ---- bunker: sand grain + raked inner-edge depth shadow ----
    bmask = mask_L("Bunker")
    if bmask is not None and a_bunker is not None and STYLE != "flat":
        grain = fbm(w, h, GID * 7 + 53, octaves=4, base_cells=55, persistence=0.5)
        base += ((grain - 0.5) * 2 * 9.0)[..., None] * a_bunker[..., None]
        ksize = int(6 * SS) | 1
        er = bmask.filter(ImageFilter.MinFilter(ksize))
        ring = ImageChops.subtract(bmask, er).filter(ImageFilter.GaussianBlur(2.2 * SS))
        rim = np.asarray(ring, np.float32) / 255.0
        base -= (rim * 30.0)[..., None]
        depth = np.asarray(bmask.filter(ImageFilter.GaussianBlur(15 * SS)), np.float32) / 255.0
        base += ((depth - 0.5) * 10.0)[..., None] * a_bunker[..., None]

    # ---- hillshade over land; DAMPED on mown surfaces so the fairway/green stay evenly bright
    #      (kills the ugly dark slope/AO blobs on the fairway; Garmin's fairway is flat-lit) ----
    mown = np.clip((a_fair if a_fair is not None else 0) + (a_green if a_green is not None else 0)
                   + (a_fringe if a_fringe is not None else 0) + (a_tee if a_tee is not None else 0),
                   0, 1)[..., None]
    if STYLE != "flat":
        light_eff = 1.0 + (light - 1.0) * (1 - 0.92 * mown)   # fairway/green stay clean & flat-lit
        np.copyto(base, base * (1 - land_np) + np.clip(base * light_eff, 0, 255) * land_np)

    # ---- this hole's water only (flood fill the body nearest the green) ----
    lmask = mask_L("Lake")
    water_keep = None
    if lmask is not None:
        la = np.asarray(lmask, dtype=np.uint8)
        ys, xs = np.where(la == 255)
        if len(xs):
            tgt = project(tuple(route[-1]))
            k = int(np.argmin((xs - tgt[0]) ** 2 + (ys - tgt[1]) ** 2))
            ff = lmask.copy()
            ImageDraw.floodfill(ff, (int(xs[k]), int(ys[k])), 128, thresh=0)
            water_keep = ff.point(lambda v: 255 if v == 128 else 0)
        else:
            water_keep = lmask

    # ---- water: depth gradient + ripple + bright shoreline ----
    if water_keep is not None:
        lk = np.asarray(water_keep, np.float32) / 255.0
        depth_src = np.asarray(water_keep.filter(ImageFilter.GaussianBlur(22 * SS)), np.float32)
        dn = np.clip(depth_src / (depth_src.max() + 1e-6) * 1.35, 0, 1) * lk
        dn3 = dn[..., None]
        wc = PAL["water_shallow"] * (1 - dn3) + PAL["water_deep"] * dn3
        rip = fbm(w, h, GID * 7 + 61, octaves=4, base_cells=16, persistence=0.5)
        band = 0.5 + 0.5 * np.sin(2 * math.pi * yy / (7.0 * SS) + (rip - 0.5) * 6)
        wc = np.clip(wc * (1 + 0.05 * (rip - 0.5) * 2 + 0.03 * (band - 0.5) * 2)[..., None], 0, 255)
        lk3 = lk[..., None]
        np.copyto(base, base * (1 - lk3) + wc * lk3)
        ring = np.asarray(ImageChops.subtract(water_keep, water_keep.filter(ImageFilter.GaussianBlur(2.4 * SS))),
                          np.float32)
        ra = np.clip(ring * 3.4 / 255.0, 0, 1)[..., None]
        np.copyto(base, base * (1 - ra) + PAL["shore"] * ra)

    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))

    # ---- corridor + hard clip to land ∪ kept water ----
    rpx = [project(tuple(p)) for p in route]

    def corridor(radius_m):
        c = Image.new("L", (w, h), 0)
        cd = ImageDraw.Draw(c)
        r = int(radius_m * sc)
        if len(rpx) >= 2:
            try:
                cd.line(rpx, fill=255, width=r * 2, joint="curve")
            except TypeError:
                cd.line(rpx, fill=255, width=r * 2)
        for q in rpx:
            cd.ellipse((q[0] - r, q[1] - r, q[0] + r, q[1] + r), fill=255)
        return c

    corr = corridor(110)   # show more surrounding rough (bigger range, less blank sky)
    hole = land_L
    if water_keep is not None:
        hole = ImageChops.lighter(hole, water_keep)
    hole = ImageChops.multiply(hole, corr).point(lambda v: 255 if v >= 128 else 0)
    bg = Image.new("RGB", (w, h), PAL["bg"])
    bg.paste(img, (0, 0), hole)
    outline = ImageChops.difference(hole, hole.filter(ImageFilter.MinFilter(3)))
    stroke = Image.new("RGBA", (w, h), PAL["edge"] + (0,))
    stroke.putalpha(outline.point(lambda v: int(v * 0.55)))
    img = Image.alpha_composite(bg.convert("RGBA"), stroke).convert("RGB")

    # ---- crisp material boundary strokes (Garmin-like clean edges; no blur) ----
    def add_stroke(name, rgb, wpx, a):
        mk = mask_L(name)
        if mk is None:
            return None
        er = mk.filter(ImageFilter.MinFilter(wpx * 2 + 1))
        edge = ImageChops.multiply(ImageChops.subtract(mk, er), hole)   # clip to the kept hole; no neighbour leaks
        ov = Image.new("RGBA", (w, h), rgb + (0,))
        ov.putalpha(edge.point(lambda v: a if v > 60 else 0))
        return ov
    for _nm, _rgb, _wp, _a in [("Fairway", (92, 146, 54), 1, 130),
                               ("Bunker", (150, 132, 86), 1, 160),
                               ("Green", (70, 146, 52), 1, 205)]:
        _ov = add_stroke(_nm, _rgb, _wp, _a)
        if _ov is not None:
            img = Image.alpha_composite(img.convert("RGBA"), _ov).convert("RGB")

    # ---- trees: species-differentiated canopies (treeline in rough; none on the fairway) ----
    fair_np = np.asarray(mask_L("Fairway"), np.uint8) if mask_L("Fairway") is not None else None
    hole_np = np.asarray(hole, np.uint8)
    trees = md.get("foliage", {}).get("trees", [])
    hdx, hdy = 0.7071, 0.7071          # highlight toward the sun (SE, lower-right — like Garmin)
    sdx, sdy = -0.7071, -0.7071        # shadow toward NW (upper-left)
    rnd = random.Random(GID * 131 + HOLE)

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
    shp = shp.filter(ImageFilter.GaussianBlur(({"flat": 1.4, "ghibli": 4.6}.get(STYLE, 3.4)) * SS))
    # keep tree cast-shadows OFF the mown surfaces — they only darken rough, never the fairway/green
    sa = np.asarray(shp.split()[3], np.float32) * (1 - 0.92 * mown[..., 0])
    shp.putalpha(Image.fromarray(np.clip(sa, 0, 255).astype(np.uint8)))
    img = Image.alpha_composite(img.convert("RGBA"), shp).convert("RGB")

    # (2) canopies on a dedicated layer (composited once at the end) so each broadleaf
    #     tile can be blurred to a smooth matte blob without fighting the base draw context.
    canopy = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(canopy, "RGBA")

    def bb(cx, cy, rx, ry):
        return (cx - rx, cy - ry, cx + rx, cy + ry)

    def draw_broadleaf(px, py, r, spec, rng, ry_mul=1.0):
        """Smooth matte canopy (Garmin-style 'buttery' blob): built on its own small tile and
        Gaussian-blurred so it reads as ONE soft whole rather than a cluster of discrete dots.
        A gentle NW(lit)->SE(shaded) gradient gives volume. Per-species size/shape variety is
        preserved via r (silhouette bumps) and ry_mul (vertical stretch for columnar species)."""
        base_c, hi, lo, dap = spec["base"], spec["hi"], spec["lo"], spec["dap"]
        R = max(3, int(round(r)))
        if STYLE == "flat":                          # flat vector tree: crisp two-tone discs, no blur
            d.ellipse(bb(px, py, R, R), fill=lo + (255,))
            d.ellipse(bb(px, py, R * 0.90, R * 0.90), fill=base_c + (255,))
            d.ellipse(bb(px + hdx * R * 0.30, py + hdy * R * 0.30, R * 0.50, R * 0.50), fill=dap + (255,))
            return
        pad = int(R * 0.30) + 6
        T = R * 2 + pad * 2
        c = R + pad
        tile = Image.new("RGBA", (T, T), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile, "RGBA")

        def te(cx, cy, rr, fill):
            td.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=fill)

        # (1) broccoli silhouette — one bright base colour, many small perimeter lobes (bumpy edge)
        te(c, c, R * 0.74, base_c + (255,))
        nl = rng.randint(8, 11)
        a0 = rng.uniform(0, 2 * math.pi)
        for k in range(nl):
            ang = a0 + 2 * math.pi * k / nl + rng.uniform(-0.16, 0.16)
            rad = R * rng.uniform(0.36, 0.52)
            te(c + math.cos(ang) * rad, c + math.sin(ang) * rad,
               R * rng.uniform(0.38, 0.50), base_c + (255,))
        # (1b) fine low-contrast noise texture (broccoli grain, NOT big spots) so the crown reads
        #      textured, not a flat blob. Smooth upscaled noise → no 'face/hole' artefacts.
        nrng = np.random.default_rng(rng.randint(0, 2 ** 31 - 1))
        low = (nrng.random((max(3, T // 7), max(3, T // 7))) * 255).astype(np.uint8)
        grain = np.asarray(Image.fromarray(low).resize((T, T), Image.BICUBIC), np.float32) / 255.0
        # (2) SMOOTH directional shade via a numpy gradient (NO discrete circles → no dark dot,
        #     no bright crescent). NW lit, SE shaded; the bright base stays dominant.
        arr = np.asarray(tile, np.float32)
        yy2, xx2 = np.mgrid[0:T, 0:T].astype(np.float32)
        dsh = np.clip(((xx2 - c) * sdx + (yy2 - c) * sdy) / (R + 1e-3), -1.15, 1.15)
        fac = 1.0 - dsh * 0.16                        # toward NW (shadow) darker, toward SE (sun) brighter
        grainf = 1.0 + (grain - 0.5) * 0.12           # subtle broccoli grain (~±6%), smooth (no spots)
        rgb = np.clip(arr[..., :3] * (fac * grainf)[..., None], 0, 255)
        tile = Image.fromarray(np.concatenate([rgb, arr[..., 3:4]], -1).astype(np.uint8))
        # (3) blur — very light for realistic (crisp), heavier for ghibli (soft painterly)
        tile = tile.filter(ImageFilter.GaussianBlur(max(0.6, R * (0.15 if STYLE == "ghibli" else 0.05))))
        if abs(ry_mul - 1.0) > 1e-3:
            tile = tile.resize((T, max(1, int(round(T * ry_mul)))), Image.BILINEAR)
        cw, ch = tile.width, tile.height
        canopy.paste(tile, (int(round(px)) - cw // 2, int(round(py)) - ch // 2), tile)

    def draw_conifer(px, py, r, spec, rng):
        """Top-down conifer: dark-green textured rosette with a lightly serrated edge (distinct
        from broadleaf, but a tree — not an ink blot)."""
        base_c, hi, lo, dap = spec["base"], spec["hi"], spec["lo"], spec["dap"]
        ns = rng.randint(11, 14)
        a0 = rng.uniform(0, 2 * math.pi)
        d.ellipse(bb(px, py, r * 0.95, r * 0.95), fill=base_c + (255,))        # body
        for k in range(ns):                                                    # short serrated edge
            ang = a0 + 2 * math.pi * k / ns
            tip = (px + math.cos(ang) * r * 1.06, py + math.sin(ang) * r * 1.06)
            b1 = (px + math.cos(ang + 0.30) * r * 0.86, py + math.sin(ang + 0.30) * r * 0.86)
            b2 = (px + math.cos(ang - 0.30) * r * 0.86, py + math.sin(ang - 0.30) * r * 0.86)
            tw = math.cos(ang) * hdx + math.sin(ang) * hdy
            d.polygon([tip, b1, b2], fill=(dap if tw > 0.1 else base_c) + (255,))
        for _ in range(6):                                                     # needle-clump dapple
            ang = rng.uniform(0, 2 * math.pi); rad = rng.uniform(0.15, 0.62) * r
            cx, cy = px + math.cos(ang) * rad, py + math.sin(ang) * rad
            tw = math.cos(ang) * hdx + math.sin(ang) * hdy
            col = dap if tw > 0 else lo
            d.ellipse(bb(cx, cy, r * 0.17, r * 0.17), fill=col + (180,))
        base_ang = math.atan2(hdy, hdx)
        for _ in range(5):                                                     # sunward radial streaks
            ang = base_ang + rng.uniform(-0.8, 0.8)
            ex, ey = px + math.cos(ang) * r * 0.62, py + math.sin(ang) * r * 0.62
            d.line([(px, py), (ex, ey)], fill=hi + (120,), width=max(1, int(0.08 * r)))
        d.ellipse(bb(px, py, r * 0.22, r * 0.22), fill=lo + (130,))            # soft dark crown centre

    drawn = 0
    for px, py, r, spec, sd in placed:
        rng = random.Random(sd)
        sh = spec["shape"]
        if sh == "conifer":
            draw_conifer(px, py, r, spec, rng)
        elif sh == "oval":
            draw_broadleaf(px, py, r, spec, rng, ry_mul=1.30)
        else:
            draw_broadleaf(px, py, r, spec, rng, ry_mul=1.0)
        drawn += 1

    img = Image.alpha_composite(img.convert("RGBA"), canopy).convert("RGB")

    # ---- ghibli post: soft paper grain + warm sunlit wash (painterly finish) ----
    if STYLE == "ghibli":
        arr = np.asarray(img, np.float32)
        paper = fbm(w, h, GID * 7 + 91, octaves=5, base_cells=8, persistence=0.55)
        pf = (1.0 + (paper - 0.5) * 0.10)[..., None]
        warm = np.array([1.045, 1.015, 0.95], np.float32)
        img = Image.fromarray(np.clip(arr * pf * warm, 0, 255).astype(np.uint8))
    return img, project, sc, w, h, drawn


# ---------- vector overlay ----------
def overlay(img, project, sc, w, h, md, by, route, prep_haz):
    d = ImageDraw.Draw(img, "RGBA")

    def route_pt_at(dist_m):
        cum = 0.0
        for i in range(len(route) - 1):
            a, b = route[i], route[i + 1]
            seg = math.hypot(b[0] - a[0], b[1] - a[1])
            if cum + seg >= dist_m:
                t = (dist_m - cum) / seg
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            cum += seg
        return route[-1]

    # ---- target ring on the real green component ----
    green_c = None
    gm = by.get("Green.drc")
    if gm:
        gl = [_local(p) for p in gm["positions"]]
        tgt = route[-1]
        nv = min(gl, key=lambda p: math.hypot(p[0] - tgt[0], p[1] - tgt[1]))
        near = [p for p in gl if math.hypot(p[0] - nv[0], p[1] - nv[1]) < 35]
        cx = sum(p[0] for p in near) / len(near)
        cz = sum(p[1] for p in near) / len(near)
        green_c = (cx, cz)
        gpx = [project(p) for p in near]
        gxs = [p[0] for p in gpx]; gys = [p[1] for p in gpx]
        rx = (max(gxs) - min(gxs)) / 2 + 6 * SS
        ry = (max(gys) - min(gys)) / 2 + 6 * SS
        gcx, gcy = project(green_c)
        d.ellipse((gcx - rx, gcy - ry, gcx + rx, gcy + ry), outline=(255, 255, 255, 235), width=2 * SS)
        d.ellipse((gcx - rx - 3 * SS, gcy - ry - 3 * SS, gcx + rx + 3 * SS, gcy + ry + 3 * SS),
                  outline=(40, 70, 40, 150), width=SS)

    # ---- play line REMOVED (it's a play-time overlay drawn dynamically from club/GPS,
    #       not part of the base hole map) ----
    rpx = [project(tuple(p)) for p in route]

    # ---- tee dot REMOVED (the tee-box surface already marks the tee; a bare dot was confusing) ----

    # ---- yard distance pills REMOVED (play-time overlay, not part of the base map) ----

    # ---- flag on the green ----
    if green_c is not None:
        gx, gy = project(green_c)
        pole = 30 * SS
        d.line([(gx, gy), (gx, gy - pole)], fill=(250, 250, 250, 255), width=2 * SS)
        d.polygon([(gx, gy - pole), (gx + 17 * SS, gy - pole + 7 * SS), (gx, gy - pole + 14 * SS)],
                  fill=(228, 58, 58, 255))
        d.ellipse((gx - 3 * SS, gy - 3 * SS, gx + 3 * SS, gy + 3 * SS), fill=(30, 30, 30, 255))

    # ---- title card ----
    d.rounded_rectangle([14 * SS, 14 * SS, 206 * SS, 74 * SS], radius=10 * SS, fill=(250, 250, 248, 236))
    d.text((26 * SS, 22 * SS), "HOLE 1", font=font(23 * SS), fill=(28, 32, 28))
    d.text((26 * SS, 50 * SS), "PAR 5  ·  543 y  ·  BLUE", font=font(12 * SS), fill=(110, 120, 108))
    return img


def render_one(md, by, route, style):
    global STYLE, PAL
    STYLE = style
    PAL = {"ghibli": GHIBLI_PAL, "flat": FLAT_PAL}.get(style, _REAL_PAL)
    img, project, sc, w, h, nt = build(md, by, route)
    img = overlay(img, project, sc, w, h, md, by, route, None)
    return img.resize((w // SS, h // SS), Image.LANCZOS)


def render():
    md, by = hole_render.load_mesh(GID, HOLE)
    route, _ = course_prep.derive_route(md)
    t0 = time.time()
    im = render_one(md, by, route, "realistic")
    im.save(f"{OUTDIR}/render-final.png")
    gm = Image.open(f"{OUTDIR}/cmp_garmin_official.png").convert("RGB")
    TH, lab, gap = 1160, 48, 20
    def fit(x, tag):
        r = TH / x.height
        rs = x.resize((max(1, int(x.width * r)), TH), Image.LANCZOS)
        p = Image.new("RGB", (rs.width, TH + lab), (250, 250, 248))
        p.paste(rs, (0, lab))
        ImageDraw.Draw(p).text((12, 12), tag, font=font(26), fill=(28, 32, 28))
        return p
    a = fit(gm, "GARMIN OFFICIAL"); b = fit(im, "AI CADDIE  (realistic)")
    board = Image.new("RGB", (a.width + b.width + gap * 3, a.height + gap), (250, 250, 248))
    board.paste(a, (gap, gap)); board.paste(b, (a.width + gap * 2, gap))
    board.save(f"{OUTDIR}/render-final-compare.png")
    print(f"realistic {im.size} in {time.time() - t0:.1f}s -> render-final.png + render-final-compare.png")


if __name__ == "__main__":
    render()
