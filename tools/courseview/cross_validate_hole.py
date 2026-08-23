"""Cross-validate the GMP-extracted polygons against the 730×730 BirdsEye raster.

For one hole, we have:
  - Raster JPG (730×730, served by birdseye.garmin.cn)
  - Shots with BOTH pixel x/y AND lat/lon (from a now-stale probe endpoint that
    bundled both representations — `logs/probe_map_bodies/snapshot_400065_hole.json`)

So we can fit (lat, lon) → (px, py) directly from a handful of shot pairs, then
project our GMP polygon vertices through the same fit and overlay on the raster.

If alignment is good, we've proven:
  1. Our GMP polygons are in the right physical location
  2. The 730×730 raster and GMP IMG share the same WGS84 frame
  3. We can use this raster as ground truth for what each ext_type means
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from parse_courseview import parse_img

ROOT = Path(__file__).resolve().parents[2]  # repo root: tools/<sub>/<file>.py is 2 dirs deep (P2 reorg fix)
SNAPSHOT = ROOT / "logs" / "probe_map_bodies" / "snapshot_400065_hole.json"
RASTER_DIR = ROOT / "output" / "hole_overlays"
OUT = ROOT / "output" / "hole_views"


SEMI31_TO_DEG = 180 / (1 << 31)  # the OTHER semicircle scale (Garmin shot data uses this)


def fit_pixel_to_geo(hole: dict) -> tuple[np.ndarray, list[tuple]]:
    """Fit a 2D affine transform from (lon, lat) → (px, py) so we handle hole rotation.

      [px]   [a b c] [lon]
      [py] = [d e f] [lat]
                     [ 1 ]

    Returns the 2×3 transform matrix M and the raw input pairs.
    """
    pairs = []
    for s in hole["shots"]:
        for loc in (s.get("startLoc"), s.get("endLoc")):
            if loc and "x" in loc and "lat" in loc:
                pairs.append((
                    loc["x"], loc["y"],
                    loc["lat"] * SEMI31_TO_DEG, loc["lon"] * SEMI31_TO_DEG,
                ))
    pairs = list(set(pairs))
    if len(pairs) < 3:
        raise RuntimeError(f"only {len(pairs)} pairs — can't fit")

    xs = np.array([p[0] for p in pairs])
    ys = np.array([p[1] for p in pairs])
    lats = np.array([p[2] for p in pairs])
    lons = np.array([p[3] for p in pairs])

    # Stack [lon, lat, 1] and solve for the two rows of M independently
    A = np.vstack([lons, lats, np.ones_like(lons)]).T  # n × 3
    (row_x, *_) = np.linalg.lstsq(A, xs, rcond=None)
    (row_y, *_) = np.linalg.lstsq(A, ys, rcond=None)
    M = np.vstack([row_x, row_y])

    px_pred = A @ row_x
    py_pred = A @ row_y
    res_x = np.abs(xs - px_pred)
    res_y = np.abs(ys - py_pred)
    print(f"  fit residual: x mean={res_x.mean():.2f}px max={res_x.max():.2f}px  "
          f"y mean={res_y.mean():.2f}px max={res_y.max():.2f}px  (n={len(pairs)} pairs)")
    # Show the rotation angle implied by the matrix
    import math as _m
    theta = _m.degrees(_m.atan2(M[0, 1], M[0, 0]))
    print(f"  rotation: {theta:.1f}° (0 = north-up)")
    return M, pairs


def apply_M(M: np.ndarray, lon: float, lat: float) -> tuple[float, float]:
    return float(M[0, 0] * lon + M[0, 1] * lat + M[0, 2]), float(M[1, 0] * lon + M[1, 1] * lat + M[1, 2])


# Research palette using terminal cross-source classifications.  It is only a
# visualization aid and does not promote DSKIMG above prodgeometry authority.
TYPE_COLOR = {
    0x010B08: (130, 130, 130),  # opaque mixed context; not a cart path
    0x010D01: (75, 75, 75),  # course/complex boundary
    0x011402: (70, 210, 210),  # tee area
    0x011403: (80, 190, 90),  # fairway area
    0x011404: (90, 240, 120),  # green area
    0x011405: (235, 205, 120),  # bunker area
    0x011407: (40, 115, 55),  # tree area
    0x011409: (110, 110, 135),  # inner hole corridor
    0x01140A: (45, 125, 220),  # stream/water area
    0x01140B: (70, 180, 165),  # teebox surface
    0x01140E: (80, 80, 105),  # outer hole domain
}
DEFAULT_COLOR = (200, 200, 200)


def overlay_hole(snapshot_hole_n: int) -> None:
    """Snapshot hole numbering (1-18) is what shots are indexed by.
    The image URL tells us which course (gid) + per-course hole-N to look up."""
    import re
    print(f"=== snapshot hole {snapshot_hole_n} ===")
    snap = json.loads(SNAPSHOT.read_text())
    hole = next(h for h in snap["holeShots"] if h["holeNumber"] == snapshot_hole_n)
    url = hole["holeImageUrl"]
    m = re.search(r"gid0?(\d+)/hole(\d+)", url)
    if not m:
        print(f"  bad image url: {url}")
        return
    course_id = int(m.group(1))
    raster_hole = int(m.group(2))
    print(f"  → gid {course_id}, raster hole {raster_hole}")
    print(f"  url: {url.split('?')[0]}")

    raster_glob = list(RASTER_DIR.glob(f"img_gid{course_id:06d}_hole{raster_hole:02d}_*.jpg"))
    if not raster_glob:
        print(f"  no cached raster")
        return
    bg = Image.open(raster_glob[0]).convert("RGBA")
    W, H = bg.size
    print(f"  raster: {raster_glob[0].name}  {W}×{H}")

    M, pairs = fit_pixel_to_geo(hole)

    # Image lat/lon coverage — invert M and project the 4 image corners back
    M3 = np.vstack([M, [0, 0, 1]])
    M_inv = np.linalg.inv(M3)
    corners_px = np.array([[0, 0, 1], [W, 0, 1], [W, H, 1], [0, H, 1]]).T
    corners_geo = M_inv @ corners_px  # rows = [lon, lat, 1]
    lons_c = corners_geo[0]
    lats_c = corners_geo[1]
    lat0, lat1 = lats_c.min(), lats_c.max()
    lon0, lon1 = lons_c.min(), lons_c.max()
    print(f"  image bbox (axis-aligned envelope): ({lat0:.5f}, {lon0:.5f}) → ({lat1:.5f}, {lon1:.5f})")
    print(f"  image span: {(lat1-lat0)*111000:.0f}m × {(lon1-lon0)*111000*0.766:.0f}m")

    img_path = Path(f"data/courseview/{course_id}.img")
    if not img_path.exists():
        # Fall back to the protobuf wrapper that fetch_courseview.py writes
        img_path = Path(f"data/courseview/{course_id}_coursedata.pb")
    tre, polys = parse_img(img_path)

    # Filter polygons to this hole's bbox (with small margin)
    margin = 0.0003
    in_view = []
    for p in polys:
        cx_lat = sum(p.lats) / len(p.lats)
        cx_lon = sum(p.lons) / len(p.lons)
        if lat0 - margin <= cx_lat <= lat1 + margin and lon0 - margin <= cx_lon <= lon1 + margin:
            in_view.append(p)
    print(f"  {len(in_view)} polygons centroid-in-bbox (of {len(polys)} total)")

    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # Structural hole domains are useful for clipping/framing, not as surfaces.
    structural_types = {0x010D01, 0x01140E, 0x011409}
    in_view = [p for p in in_view if p.ext_type not in structural_types]

    # Larger features first so small detail stays on top
    for p in sorted(in_view, key=lambda p: -len(p.lats)):
        pts = [apply_M(M, lon, lat) for lat, lon in zip(p.lats, p.lons)]
        c = TYPE_COLOR.get(p.ext_type, DEFAULT_COLOR)
        if len(pts) >= 3:
            d.polygon(pts, outline=(*c, 255))
            # Thicker outline by drawing offset copies
            for dx, dy in [(1, 0), (0, 1), (-1, 0), (0, -1)]:
                d.polygon([(x+dx, y+dy) for x, y in pts], outline=(*c, 220))
        else:
            d.line(pts, fill=(*c, 255), width=2)

    # Also mark the original shot pixels (so we can visually verify the fit)
    for px, py, lat, lon in pairs:
        d.ellipse([px - 3, py - 3, px + 3, py + 3], outline=(255, 255, 0, 255), width=1)

    out_path = OUT / f"snap{snapshot_hole_n:02d}_gid{course_id}_h{raster_hole:02d}_overlay.png"
    Image.alpha_composite(bg, overlay).save(out_path)
    print(f"  saved → {out_path}")


def main() -> None:
    holes = [int(h) for h in sys.argv[1:]] if len(sys.argv) > 1 else [2]
    for h in holes:
        overlay_hole(h)


if __name__ == "__main__":
    main()
