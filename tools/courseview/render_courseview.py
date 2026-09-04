"""Render parsed CourseView polygons onto an image for visual inspection.

Usage: render_courseview.py [path/to/course.img]
Output: output/courseview/{course_id}.png — polygon overlay colored by type code.
"""
from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from parse_courseview import parse_img

ROOT = Path(__file__).resolve().parents[2]  # repo root: tools/<sub>/<file>.py is 2 dirs deep (P2 reorg fix)
OUT = ROOT / "output" / "courseview"
OUT.mkdir(parents=True, exist_ok=True)

# Research-only palette.  The labels below are the terminal cross-source
# classifications from audit_dskimg_vector_semantics.py; the colors do not make
# these coarse vectors authoritative for distance, lie or penalty decisions.
TYPE_COLOR = {
    0x010B01: (50, 110, 190),  # ocean context
    0x010B08: (130, 130, 130),  # opaque mixed context; preserve, do not label
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
    0x011604: (60, 130, 220),  # legacy parser-only type; no semantic claim
    0x010202: (50, 130, 50),  # legacy parser-only type; no semantic claim
    0x010203: (50, 130, 50),
}
_PALETTE = [
    (200, 200, 60), (60, 180, 200), (200, 100, 180), (120, 180, 80),
    (240, 140, 40), (90, 120, 220), (200, 100, 60), (60, 60, 200),
    (160, 100, 200), (100, 200, 200), (220, 200, 200), (140, 140, 80),
]


def color_for(ext_type: int, idx: int) -> tuple[int, int, int]:
    return _PALETTE[idx % len(_PALETTE)]


def project(bbox, lat: float, lon: float, w: int, h: int, margin: int = 30) -> tuple[float, float]:
    """Map (lat,lon) → pixel (x,y). Equirectangular with cos-lat correction at bbox center."""
    cx_lat = (bbox.north + bbox.south) / 2
    aspect_corr = math.cos(math.radians(cx_lat))
    span_lon = (bbox.east - bbox.west) * aspect_corr
    span_lat = (bbox.north - bbox.south)
    avail_w = w - 2 * margin
    avail_h = h - 2 * margin
    # Fit while preserving aspect
    scale = min(avail_w / span_lon, avail_h / span_lat)
    drawn_w = span_lon * scale
    drawn_h = span_lat * scale
    ox = margin + (avail_w - drawn_w) / 2
    oy = margin + (avail_h - drawn_h) / 2
    x = ox + (lon - bbox.west) * aspect_corr * scale
    y = oy + (bbox.north - lat) * scale  # y inverted
    return x, y


def render(img_path: Path, out_path: Path, only_types: set | None = None) -> None:
    tre, polys = parse_img(img_path)
    if only_types:
        polys = [p for p in polys if p.ext_type in only_types]
    print(f"{len(polys)} polygons; rendering to {out_path}")

    W, H = 1200, 900
    img = Image.new("RGB", (W, H), (30, 30, 40))
    d = ImageDraw.Draw(img, "RGBA")

    type_counts = Counter(p.ext_type for p in polys)
    type_order = [et for et, _ in type_counts.most_common()]
    # Use semantic colors when known; fall back to palette
    type_colors = {}
    pal_i = 0
    for et in type_order:
        if et in TYPE_COLOR:
            type_colors[et] = TYPE_COLOR[et]
        else:
            type_colors[et] = _PALETTE[pal_i % len(_PALETTE)]
            pal_i += 1

    # Draw bbox frame
    x0, y0 = project(tre.bbox, tre.bbox.north, tre.bbox.west, W, H)
    x1, y1 = project(tre.bbox, tre.bbox.south, tre.bbox.east, W, H)
    d.rectangle([x0, y0, x1, y1], outline=(80, 80, 100), width=1)

    # Drop obviously-malformed polygons (too far OOB, or span > 80% of bbox = stretch errors)
    span_lat_max = (tre.bbox.north - tre.bbox.south) * 0.8
    span_lon_max = (tre.bbox.east - tre.bbox.west) * 0.8

    drawn = 0
    skipped_oob = skipped_huge = 0
    # Structural domains first, then broad surfaces, then small detail.
    LAYER_ORDER = {
        0x010D01: 0,
        0x01140E: 0,
        0x011409: 0,
        0x010202: 0,
        0x010203: 0,
        0x011403: 1,
        0x011407: 1,
        0x01140A: 2,
        0x011604: 2,
        0x011402: 3,
        0x011404: 3,
        0x011405: 3,
        0x01140B: 3,
    }
    def sort_key(p):
        return (LAYER_ORDER.get(p.ext_type, 1), -len(p.lats))
    for poly in sorted(polys, key=sort_key):
        in_bbox = sum(
            1 for la, lo in zip(poly.lats, poly.lons)
            if tre.bbox.south - 0.0005 <= la <= tre.bbox.north + 0.0005
            and tre.bbox.west - 0.0005 <= lo <= tre.bbox.east + 0.0005
        )
        if in_bbox < len(poly.lats) * 0.7:
            skipped_oob += 1
            continue
        # Filter out polygons that span almost the whole course — those are stretch-recursion bugs
        s_lat = max(poly.lats) - min(poly.lats)
        s_lon = max(poly.lons) - min(poly.lons)
        if s_lat > span_lat_max or s_lon > span_lon_max:
            skipped_huge += 1
            continue
        pts = [project(tre.bbox, la, lo, W, H) for la, lo in zip(poly.lats, poly.lons)]
        c = type_colors[poly.ext_type]
        if len(pts) >= 3:
            d.polygon(pts, fill=(*c, 130), outline=(*c, 255))
        else:
            d.line(pts, fill=(*c, 255), width=2)
        drawn += 1

    # Legend
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    except Exception:
        font = ImageFont.load_default()
    ly = 10
    d.text((10, ly), f"{img_path.stem} — {drawn} drawn  ({skipped_oob} OOB, {skipped_huge} oversized)", fill=(220, 220, 220), font=font)
    ly += 18
    d.text((10, ly), f"bbox: {(tre.bbox.north - tre.bbox.south)*111000:.0f}m × "
           f"{(tre.bbox.east - tre.bbox.west)*111000*math.cos(math.radians((tre.bbox.north+tre.bbox.south)/2)):.0f}m",
           fill=(180, 180, 180), font=font)
    ly += 22
    for et, n in type_counts.most_common():
        c = type_colors[et]
        avg_v = sum(len(p.lats) for p in polys if p.ext_type == et) / n
        d.rectangle([10, ly + 2, 22, ly + 14], fill=c)
        d.text((28, ly), f"0x{et:06x}  n={n}  avg_v={avg_v:.0f}", fill=(220, 220, 220), font=font)
        ly += 16
        if ly > H - 20:
            break

    img.save(out_path)
    print(f"saved {out_path}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/courseview/31795.img")
    out_path = OUT / f"{target.stem}.png"
    render(target, out_path)
