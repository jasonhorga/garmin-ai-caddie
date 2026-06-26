"""Render Garmin CourseView polygons over Esri World Imagery satellite tiles.

Why Esri: it's WGS84 (no GCJ-02 offset like Chinese map providers), free, no API key
needed, covers China.

Pipeline:
  1. parse_courseview → polygons in WGS84 lat/lon
  2. compute bbox (course-wide for v1, per-hole later)
  3. fetch Esri tiles covering bbox at zoom 18
  4. stitch into a single canvas with consistent Web Mercator projection
  5. project polygons onto the canvas and alpha-blend
  6. save PNG

For v1: render whole course (黑骑士 31795). If polygons align with the visible
features in the satellite image, the WGS84 hypothesis is confirmed.
"""
from __future__ import annotations

import io
import math
import time
import json
from pathlib import Path

import requests

from PIL import Image, ImageDraw

from parse_courseview import parse_img_all

ROOT = Path(__file__).resolve().parents[2]  # repo root: tools/<sub>/<file>.py is 2 dirs deep (P2 reorg fix)
TILE_CACHE = ROOT / "data" / "esri_tiles"
TILE_CACHE.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "output" / "hole_views"
OUT.mkdir(parents=True, exist_ok=True)

ESRI_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
TILE_SIZE = 256


# ----------------------------------------------------------------------
# Web Mercator projection
# ----------------------------------------------------------------------

def lonlat_to_world_pixel(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """Convert WGS84 (lon, lat) to global Web Mercator pixel coordinates at `zoom`."""
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n * TILE_SIZE
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n * TILE_SIZE
    return x, y


def fetch_tile(z: int, x: int, y: int) -> Image.Image:
    """Fetch one Esri tile, with disk cache. Returns RGB PIL image of size TILE_SIZE."""
    cache = TILE_CACHE / f"{z}_{x}_{y}.jpg"
    if cache.exists():
        return Image.open(cache).convert("RGB")
    url = ESRI_URL.format(z=z, x=x, y=y)
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    cache.write_bytes(r.content)
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def stitch_tiles(min_lon: float, min_lat: float, max_lon: float, max_lat: float, zoom: int) -> tuple[Image.Image, float, float]:
    """Build a single image covering the bbox.

    Returns (image, origin_world_px_x, origin_world_px_y) where origin is the
    top-left corner of the stitched image in Web Mercator pixel space at `zoom`.
    """
    # Compute tile range. Note y axis flips in tiles (north is lower y).
    nw_x, nw_y = lonlat_to_world_pixel(min_lon, max_lat, zoom)
    se_x, se_y = lonlat_to_world_pixel(max_lon, min_lat, zoom)
    tile_x0 = int(nw_x // TILE_SIZE)
    tile_y0 = int(nw_y // TILE_SIZE)
    tile_x1 = int(se_x // TILE_SIZE)
    tile_y1 = int(se_y // TILE_SIZE)

    n_x = tile_x1 - tile_x0 + 1
    n_y = tile_y1 - tile_y0 + 1
    print(f"  stitching {n_x}×{n_y} = {n_x*n_y} tiles at zoom {zoom}")

    canvas = Image.new("RGB", (n_x * TILE_SIZE, n_y * TILE_SIZE))
    for tx in range(tile_x0, tile_x1 + 1):
        for ty in range(tile_y0, tile_y1 + 1):
            tile = fetch_tile(zoom, tx, ty)
            canvas.paste(tile, ((tx - tile_x0) * TILE_SIZE, (ty - tile_y0) * TILE_SIZE))
            time.sleep(0.05)  # be polite

    origin_x = tile_x0 * TILE_SIZE
    origin_y = tile_y0 * TILE_SIZE
    return canvas, origin_x, origin_y


# ----------------------------------------------------------------------
# Render polygons onto stitched tile
# ----------------------------------------------------------------------

# Same as render_courseview.py — color by ext_type (empirical mapping)
TYPE_COLOR = {
    0x011407: (255, 230, 130),  # Yellow - bunkers/greens?
    0x01140e: (90, 200, 90),    # OVERVIEW BLOB (exclude)
    0x011409: (60, 130, 240),   # OVERVIEW BLOB (exclude)
    0x011604: (60, 130, 240),
    0x011405: (255, 100, 0),    # Orange
    0x011403: (0, 255, 0),      # Bright Green - fairways?
    0x011404: (255, 0, 255),    # Magenta
    0x010b08: (255, 255, 255),  # White - cart paths
    0x011402: (0, 255, 255),    # Cyan
    0x012e00: (200, 80, 255),   # lines
    0x014103: (80, 200, 255),   # lines
    0x010202: (50, 50, 50),     # OVERVIEW BLOB (exclude)
    0x010208: (255, 0, 0),      # point markers
    0x013801: (0, 255, 0),      # point markers
    0x013800: (0, 0, 255),      # point markers
}
DEFAULT_COLOR = (200, 200, 200)

EXCLUDE_TYPES = {0x01140e, 0x011409, 0x010202}

def render(img_path: Path, out_path: Path, shots_path: Path | None = None, zoom: int = 18, only_types: set | None = None) -> None:
    tre, polys, lines, points = parse_img_all(img_path)
    
    # Filter out overview blobs
    polys = [p for p in polys if p.ext_type not in EXCLUDE_TYPES]
    
    if only_types is not None:
        polys = [p for p in polys if p.ext_type in only_types]
        lines = [p for p in lines if p.ext_type in only_types]
        points = [p for p in points if p.ext_type in only_types]
        
    b = tre.bbox
    print(f"course bbox: ({b.south:.5f}, {b.west:.5f}) → ({b.north:.5f}, {b.east:.5f})")
    center_lat = (b.north + b.south) / 2
    print(f"course size: {(b.north-b.south)*111000:.0f}m × {(b.east-b.west)*111000*math.cos(math.radians(center_lat)):.0f}m")

    # Load shots
    shots_data = []
    if shots_path and shots_path.exists():
        with open(shots_path) as f:
            s_json = json.load(f)
            for hole in s_json.get("holeShots", []):
                for shot in hole.get("shots", []):
                    sl = shot.get("startLoc")
                    if sl and "lat" in sl and "lon" in sl:
                        lat = sl["lat"] * 180.0 / (1<<31)
                        lon = sl["lon"] * 180.0 / (1<<31)
                        shots_data.append((lon, lat))
    print(f"loaded {len(shots_data)} shots")

    # Expand bbox slightly so we have context margin around the course
    margin_deg = 0.001
    lon0, lat0, lon1, lat1 = (
        b.west - margin_deg, b.south - margin_deg,
        b.east + margin_deg, b.north + margin_deg,
    )

    canvas, ox, oy = stitch_tiles(lon0, lat0, lon1, lat1, zoom)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    def project(lon: float, lat: float) -> tuple[float, float]:
        if lat < -89.0 or lat > 89.0:
            return 0.0, 0.0
        wx, wy = lonlat_to_world_pixel(lon, lat, zoom)
        return wx - ox, wy - oy

    # Render polygons
    drawn_polys = skipped_polys = 0
    for poly in sorted(polys, key=lambda p: -len(p.lats)):
        min_lat, max_lat = min(poly.lats), max(poly.lats)
        min_lon, max_lon = min(poly.lons), max(poly.lons)
        
        # Sane size check: golf features are not > 5000m (0.05 degrees)
        if (max_lat - min_lat) > 0.05 or (max_lon - min_lon) > 0.05:
            skipped_polys += 1
            continue

        in_bbox = sum(
            1 for la, lo in zip(poly.lats, poly.lons)
            if b.south - margin_deg <= la <= b.north + margin_deg
            and b.west - margin_deg <= lo <= b.east + margin_deg
        )
        if in_bbox < len(poly.lats) * 0.7:
            skipped_polys += 1
            continue
        pts = [project(lo, la) for la, lo in zip(poly.lats, poly.lons)]
        color = TYPE_COLOR.get(poly.ext_type, DEFAULT_COLOR)
        if len(pts) >= 3:
            d.polygon(pts, fill=(*color, 130), outline=(*color, 255))
        elif len(pts) >= 2:
            d.line(pts, fill=(*color, 255), width=2)
        drawn_polys += 1
        
    # Render lines
    for line in lines:
        pts = [project(lo, la) for la, lo in zip(line.lats, line.lons)]
        color = TYPE_COLOR.get(line.ext_type, DEFAULT_COLOR)
        if len(pts) >= 2:
            d.line(pts, fill=(*color, 200), width=3)
            
    # Render points
    for pt in points:
        px, py = project(pt.lon, pt.lat)
        color = TYPE_COLOR.get(pt.ext_type, DEFAULT_COLOR)
        d.ellipse([px-4, py-4, px+4, py+4], fill=(*color, 255), outline=(255, 255, 255, 255))

    print(f"  drew {drawn_polys} polys, skipped {skipped_polys} OOB")
    print(f"  drew {len(lines)} lines")
    print(f"  drew {len(points)} points")

    # Render shots on top
    for slon, slat in shots_data:
        px, py = project(slon, slat)
        d.ellipse([px-3, py-3, px+3, py+3], fill=(255, 0, 0, 255), outline=(255, 255, 255, 255))
        
    result = Image.alpha_composite(canvas.convert("RGBA"), overlay)

    # Crop to course bbox + small margin (the tile grid is wider)
    p_lon0, p_lat0 = project(lon0, lat1)  # top-left
    p_lon1, p_lat1 = project(lon1, lat0)  # bottom-right
    crop = (max(0, int(p_lon0)), max(0, int(p_lat0)),
            min(result.size[0], int(p_lon1)), min(result.size[1], int(p_lat1)))
    result.crop(crop).save(out_path)
    print(f"saved {out_path}")


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/courseview/31795.img")
    shots_path = Path("data/shots/17344568.json")
    out = OUT / f"{target.stem}_satellite_with_shots.png"
    render(target, out, shots_path)
