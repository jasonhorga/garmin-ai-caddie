"""Overlay decoded Garmin prodgeometry meshes on Garmin's 730x730 raster image.

This uses the official CourseView 3D geometry as the geometry source:

1. `decode_courseview_geometry.js` decodes encrypted/extracted `.drc` files.
2. This script fits local CourseView meters to Garmin raster pixels using shot
   control points from a snapshot JSON.
3. Mesh triangles are rendered on top of the 730x730 Garmin raster.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MESH_JSON = ROOT / "output" / "prodgeometry" / "gid31795_h02_meshes.json"
DEFAULT_SNAPSHOT = ROOT / "logs" / "probe_map_bodies" / "snapshot_400065_hole.json"
RASTER_CACHE = ROOT / "output" / "hole_overlays"
OUT_DIR = ROOT / "output" / "prodgeometry_overlay"

SEMI31_TO_DEG = 180 / (1 << 31)
EARTH_RADIUS_M = 6_378_137.0

MESH_ORDER = [
    "PlayableBounds.drc",
    "IslandExt.drc",
    "PhysicsMesh.drc",
    "Rough.drc",
    "Lake.drc",
    "LakeSide.drc",
    "Fairway.drc",
    "Fringe.drc",
    "Green.drc",
    "Bunker.drc",
    "Teebox.drc",
    "TreeArea.drc",
    "VfxGreenA.drc",
]

MESH_COLORS = {
    "PlayableBounds.drc": (236, 88, 69, 32),
    "IslandExt.drc": (190, 181, 146, 72),
    "PhysicsMesh.drc": (80, 80, 80, 16),
    "Rough.drc": (108, 137, 79, 82),
    "Fairway.drc": (64, 178, 91, 135),
    "Fringe.drc": (110, 205, 117, 118),
    "Green.drc": (48, 220, 108, 170),
    "Bunker.drc": (232, 197, 112, 178),
    "Lake.drc": (54, 137, 220, 150),
    "LakeSide.drc": (43, 93, 152, 100),
    "Teebox.drc": (54, 139, 67, 155),
    "TreeArea.drc": (42, 104, 56, 135),
    "VfxGreenA.drc": (21, 242, 118, 118),
}


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def fetch_raster(url: str) -> Image.Image:
    RASTER_CACHE.mkdir(parents=True, exist_ok=True)
    cache = RASTER_CACHE / ("img_" + url.split("/")[-1].split("?")[0])
    if cache.exists():
        return Image.open(cache).convert("RGBA")
    with urllib.request.urlopen(url, timeout=20) as response:
        body = response.read()
    cache.write_bytes(body)
    return Image.open(io.BytesIO(body)).convert("RGBA")


def snapshot_hole(snapshot_path: Path, hole_number: int) -> dict[str, Any]:
    data = json.loads(snapshot_path.read_text())
    for hole in data.get("holeShots", []):
        if hole.get("holeNumber") == hole_number:
            return hole
    raise ValueError(f"hole {hole_number} not found in {snapshot_path}")


def raster_course_and_hole(hole: dict[str, Any]) -> tuple[int, int]:
    url = hole["holeImageUrl"]
    match = re.search(r"gid0?(\d+)/hole(\d+)", url)
    if not match:
        raise ValueError(f"cannot parse course/hole from {url}")
    return int(match.group(1)), int(match.group(2))


def lonlat_to_local_meters(lon: float, lat: float, ref_lon: float, ref_lat: float) -> tuple[float, float]:
    lat0 = math.radians(ref_lat)
    east = math.radians(lon - ref_lon) * EARTH_RADIUS_M * math.cos(lat0)
    north = math.radians(lat - ref_lat) * EARTH_RADIUS_M
    return east, north


def shot_control_points(
    hole: dict[str, Any],
    *,
    ref_lon: float,
    ref_lat: float,
) -> list[tuple[float, float, float, float]]:
    points = []
    seen = set()
    for shot in hole.get("shots", []):
        for key in ("startLoc", "endLoc"):
            loc = shot.get(key)
            if not loc or not {"x", "y", "lat", "lon"} <= loc.keys():
                continue
            lat = float(loc["lat"]) * SEMI31_TO_DEG
            lon = float(loc["lon"]) * SEMI31_TO_DEG
            east, north = lonlat_to_local_meters(lon, lat, ref_lon, ref_lat)
            row = (float(loc["x"]), float(loc["y"]), east, north)
            dedupe = tuple(round(v, 6) for v in row)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            points.append(row)
    if len(points) < 3:
        raise ValueError(f"need at least 3 shot control points, got {len(points)}")
    return points


def fit_local_to_pixel(points: list[tuple[float, float, float, float]]) -> tuple[np.ndarray, dict[str, Any]]:
    px = np.array([p[0] for p in points])
    py = np.array([p[1] for p in points])
    east = np.array([p[2] for p in points])
    north = np.array([p[3] for p in points])
    design = np.vstack([east, north, np.ones_like(east)]).T

    row_x, *_ = np.linalg.lstsq(design, px, rcond=None)
    row_y, *_ = np.linalg.lstsq(design, py, rcond=None)
    matrix = np.vstack([row_x, row_y])

    pred_x = design @ row_x
    pred_y = design @ row_y
    res_x = np.abs(px - pred_x)
    res_y = np.abs(py - pred_y)
    diag = {
        "control_points": len(points),
        "residual_x_mean_px": float(res_x.mean()),
        "residual_x_max_px": float(res_x.max()),
        "residual_y_mean_px": float(res_y.mean()),
        "residual_y_max_px": float(res_y.max()),
        "matrix": matrix.tolist(),
    }
    return matrix, diag


def project(matrix: np.ndarray, east: float, north: float) -> tuple[float, float]:
    return (
        float(matrix[0, 0] * east + matrix[0, 1] * north + matrix[0, 2]),
        float(matrix[1, 0] * east + matrix[1, 1] * north + matrix[1, 2]),
    )


def mesh_point_to_local(point: list[float]) -> tuple[float, float]:
    x, _y, z = point
    return -float(x), float(z)


def draw_meshes(raster: Image.Image, decoded: dict[str, Any], matrix: np.ndarray, out_path: Path) -> None:
    overlay = Image.new("RGBA", raster.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    by_name = {mesh["name"]: mesh for mesh in decoded["meshes"]}

    for name in MESH_ORDER:
        mesh = by_name.get(name)
        if not mesh:
            continue
        color = MESH_COLORS.get(name, (255, 255, 255, 90))
        positions = mesh["positions"]
        projected = [project(matrix, *mesh_point_to_local(p)) for p in positions]
        for a, b, c in mesh["faces"]:
            draw.polygon([projected[a], projected[b], projected[c]], fill=color)

        if name in {"Green.drc", "Bunker.drc", "Teebox.drc", "TreeArea.drc"}:
            outline = (color[0], color[1], color[2], min(255, color[3] + 80))
            for a, b, c in mesh["faces"]:
                pts = [projected[a], projected[b], projected[c]]
                draw.line([pts[0], pts[1], pts[2], pts[0]], fill=outline, width=1)

    foliage = decoded.get("foliage") or {}
    for name, color, radius_scale in (
        ("foliage", (31, 96, 42, 125), 0.20),
        ("trees", (19, 84, 32, 185), 6.0),
        ("rocks", (92, 92, 84, 150), 2.5),
    ):
        for item in foliage.get(name, []) or []:
            px, py = project(matrix, -float(item["x"]), float(item["z"]))
            radius = max(2.0, float(item.get("s", 1.0)) * radius_scale)
            draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=color)

    hole = decoded.get("hole", {})
    for dogleg in hole.get("Doglegs", []) or []:
        pts = [project(matrix, float(p["X"]), float(p["Y"])) for p in dogleg.get("Line", [])]
        if len(pts) >= 2:
            draw.line(pts, fill=(255, 255, 255, 210), width=3)
            draw.line(pts, fill=(35, 35, 35, 210), width=1)

    for tee in hole.get("TeeLocations", []) or []:
        px, py = project(matrix, float(tee["X"]), float(tee["Y"]))
        draw.rectangle((px - 4, py - 4, px + 4, py + 4), fill=(255, 255, 255, 230), outline=(25, 25, 25, 230))

    composed = Image.alpha_composite(raster, overlay)
    bar = Image.new("RGBA", (composed.width, 34), (0, 0, 0, 170))
    bd = ImageDraw.Draw(bar)
    hole_number = hole.get("HoleNumber", "?")
    global_id = hole.get("GlobalId", "?")
    bd.text(
        (10, 8),
        f"prodgeometry DRC mesh over Garmin raster · gid {global_id} · hole {hole_number}",
        fill=(255, 255, 255),
        font=_font(15),
    )

    final = Image.new("RGBA", (composed.width, composed.height + 34), (0, 0, 0, 0))
    final.paste(bar, (0, 0))
    final.paste(composed, (0, 34))
    final.save(out_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh-json", type=Path, default=DEFAULT_MESH_JSON)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--hole", type=int, default=None)
    parser.add_argument(
        "--snapshot-hole",
        type=int,
        default=None,
        help="Absolute hole number in the snapshot JSON when it differs from the prodgeometry local hole.",
    )
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    decoded = json.loads(args.mesh_json.read_text())
    hole_meta = decoded["hole"]
    hole_number = args.hole if args.hole is not None else int(hole_meta["HoleNumber"])
    snapshot_hole_number = args.snapshot_hole if args.snapshot_hole is not None else hole_number
    snapshot = snapshot_hole(args.snapshot, snapshot_hole_number)
    course_id, raster_hole_number = raster_course_and_hole(snapshot)
    raster = fetch_raster(snapshot["holeImageUrl"])

    ref_lat = float(hole_meta["RefLat"])
    ref_lon = float(hole_meta["RefLon"])
    control_points = shot_control_points(snapshot, ref_lon=ref_lon, ref_lat=ref_lat)
    matrix, fit = fit_local_to_pixel(control_points)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"gid{course_id}_rasterh{raster_hole_number:02d}_prodgeometry_h{hole_number:02d}"
    overlay_path = args.out_dir / f"{stem}_overlay.png"
    diag_path = args.out_dir / f"{stem}_diagnostics.json"
    draw_meshes(raster, decoded, matrix, overlay_path)

    diag = {
        "mesh_json": str(args.mesh_json),
        "snapshot": str(args.snapshot),
        "course_id": course_id,
        "raster_hole_number": raster_hole_number,
        "hole_number": hole_number,
        "snapshot_hole_number": snapshot_hole_number,
        "raster_size": raster.size,
        "refLat": ref_lat,
        "refLon": ref_lon,
        "fit": fit,
        "mesh_count": len(decoded["meshes"]),
        "overlay": str(overlay_path),
    }
    diag_path.write_text(json.dumps(diag, ensure_ascii=False, indent=2))

    print(f"[ok] overlay: {overlay_path}")
    print(f"[ok] diagnostics: {diag_path}")
    print(
        "[fit] "
        f"n={fit['control_points']} "
        f"x_mean={fit['residual_x_mean_px']:.2f}px "
        f"x_max={fit['residual_x_max_px']:.2f}px "
        f"y_mean={fit['residual_y_mean_px']:.2f}px "
        f"y_max={fit['residual_y_max_px']:.2f}px"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
