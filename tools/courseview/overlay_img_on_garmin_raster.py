"""Overlay Garmin CourseView IMG polygons on Garmin's 730x730 raster hole image.

This is a focused verification tool for the AI-caddie geometry work:

1. Use a snapshot-level hole JSON that contains both Garmin raster URLs and
   shot control points with (lat/lon, x/y).
2. Fit an affine transform from WGS84 lon/lat to Garmin raster pixels.
3. Parse CourseView IMG polygons and project them through the fitted transform.
4. Save an all-types overlay, per-type overlays, and a diagnostics JSON.

The default sample is 黑骑士 B/C snapshot 400065, hole 2.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import urllib.request
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from parse_courseview import parse_img_all

ROOT = Path(__file__).resolve().parents[2]  # repo root: tools/<sub>/<file>.py is 2 dirs deep (P2 reorg fix)
DEFAULT_SNAPSHOT = ROOT / "logs" / "probe_map_bodies" / "snapshot_400065_hole.json"
RASTER_CACHE = ROOT / "output" / "hole_overlays"
OUT = ROOT / "output" / "img_raster_overlay"
OUT.mkdir(parents=True, exist_ok=True)
RASTER_CACHE.mkdir(parents=True, exist_ok=True)

SEMI31_TO_DEG = 180 / (1 << 31)

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
DEFAULT_COLOR = (220, 220, 220)

SEGMENT_FEATURES = {
    "green": {"hsv": ((35, 80, 80), (75, 255, 200)), "color": (0, 220, 0), "min_area": 80},
    "fairway": {"hsv": ((35, 30, 150), (75, 130, 255)), "color": (60, 255, 60), "min_area": 200},
    "bunker": {"hsv": ((15, 40, 150), (35, 200, 255)), "color": (255, 200, 90), "min_area": 30},
    "water": {"hsv": ((85, 80, 80), (130, 255, 255)), "color": (40, 120, 255), "min_area": 80},
}


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fetch_raster(url: str) -> Image.Image:
    """Return the Garmin 730x730 raster image, using the existing cache format."""
    cache = RASTER_CACHE / ("img_" + url.split("/")[-1].split("?")[0])
    if cache.exists():
        return Image.open(cache).convert("RGBA")
    with urllib.request.urlopen(url, timeout=20) as r:
        body = r.read()
    cache.write_bytes(body)
    return Image.open(io.BytesIO(body)).convert("RGBA")


def snapshot_hole(snapshot_path: Path, hole_number: int) -> dict:
    data = json.loads(snapshot_path.read_text())
    for hole in data.get("holeShots", []):
        if hole.get("holeNumber") == hole_number:
            return hole
    raise ValueError(f"hole {hole_number} not found in {snapshot_path}")


def course_and_raster_hole(hole: dict) -> tuple[int, int]:
    url = hole["holeImageUrl"]
    match = re.search(r"gid0?(\d+)/hole(\d+)", url)
    if not match:
        raise ValueError(f"cannot parse course id / hole number from {url}")
    return int(match.group(1)), int(match.group(2))


def fit_lonlat_to_pixel(hole: dict) -> tuple[np.ndarray, dict]:
    pairs = []
    for shot in hole.get("shots", []):
        for loc in (shot.get("startLoc"), shot.get("endLoc")):
            if not loc:
                continue
            if {"x", "y", "lat", "lon"} <= loc.keys():
                pairs.append((
                    float(loc["x"]),
                    float(loc["y"]),
                    loc["lat"] * SEMI31_TO_DEG,
                    loc["lon"] * SEMI31_TO_DEG,
                ))
    pairs = sorted(set(pairs))
    if len(pairs) < 3:
        raise ValueError(f"need at least 3 control points with x/y+lat/lon, got {len(pairs)}")

    xs = np.array([p[0] for p in pairs])
    ys = np.array([p[1] for p in pairs])
    lats = np.array([p[2] for p in pairs])
    lons = np.array([p[3] for p in pairs])

    design = np.vstack([lons, lats, np.ones_like(lons)]).T
    (row_x, *_) = np.linalg.lstsq(design, xs, rcond=None)
    (row_y, *_) = np.linalg.lstsq(design, ys, rcond=None)
    matrix = np.vstack([row_x, row_y])

    pred_x = design @ row_x
    pred_y = design @ row_y
    res_x = np.abs(xs - pred_x)
    res_y = np.abs(ys - pred_y)
    diag = {
        "control_points": len(pairs),
        "residual_x_mean_px": float(res_x.mean()),
        "residual_x_max_px": float(res_x.max()),
        "residual_y_mean_px": float(res_y.mean()),
        "residual_y_max_px": float(res_y.max()),
        "rotation_degrees": float(math.degrees(math.atan2(matrix[0, 1], matrix[0, 0]))),
        "matrix": matrix.tolist(),
    }
    return matrix, diag


def apply_matrix(matrix: np.ndarray, lon: float, lat: float) -> tuple[float, float]:
    return (
        float(matrix[0, 0] * lon + matrix[0, 1] * lat + matrix[0, 2]),
        float(matrix[1, 0] * lon + matrix[1, 1] * lat + matrix[1, 2]),
    )


def image_bbox_geo(matrix: np.ndarray, width: int, height: int) -> tuple[float, float, float, float]:
    matrix3 = np.vstack([matrix, [0, 0, 1]])
    inv = np.linalg.inv(matrix3)
    corners_px = np.array([[0, 0, 1], [width, 0, 1], [width, height, 1], [0, height, 1]]).T
    corners_geo = inv @ corners_px
    lons = corners_geo[0]
    lats = corners_geo[1]
    return float(lats.min()), float(lons.min()), float(lats.max()), float(lons.max())


def pixel_to_lonlat(matrix: np.ndarray, x: float, y: float) -> tuple[float, float]:
    matrix3 = np.vstack([matrix, [0, 0, 1]])
    lon, lat, _one = np.linalg.inv(matrix3) @ np.array([x, y, 1.0])
    return float(lon), float(lat)


def polygons_in_view(polygons, bbox: tuple[float, float, float, float], margin: float = 0.0003):
    south, west, north, east = bbox
    selected = []
    for poly in polygons:
        p_south = min(poly.lats)
        p_north = max(poly.lats)
        p_west = min(poly.lons)
        p_east = max(poly.lons)
        intersects = not (
            p_north < south - margin
            or p_south > north + margin
            or p_east < west - margin
            or p_west > east + margin
        )
        if intersects:
            selected.append(poly)
    return selected


def points_in_view(points, bbox: tuple[float, float, float, float], margin: float = 0.0003):
    south, west, north, east = bbox
    return [
        point for point in points
        if south - margin <= point.lat <= north + margin and west - margin <= point.lon <= east + margin
    ]


def draw_overlay(
    raster: Image.Image,
    matrix: np.ndarray,
    polygons,
    out_path: Path,
    *,
    title: str,
    alpha: int = 115,
) -> None:
    overlay = Image.new("RGBA", raster.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for poly in sorted(polygons, key=lambda p: -len(p.lats)):
        pts = [apply_matrix(matrix, lon, lat) for lat, lon in zip(poly.lats, poly.lons)]
        color = TYPE_COLOR.get(poly.ext_type, DEFAULT_COLOR)
        if len(pts) >= 3:
            draw.polygon(pts, fill=(*color, alpha), outline=(*color, 255))
        elif len(pts) >= 2:
            draw.line(pts, fill=(*color, 255), width=2)

    composed = Image.alpha_composite(raster, overlay)
    bar = Image.new("RGBA", (composed.width, 34), (0, 0, 0, 170))
    bd = ImageDraw.Draw(bar)
    bd.text((10, 8), title, fill=(255, 255, 255), font=_font(15))

    final = Image.new("RGBA", (composed.width, composed.height + 34), (0, 0, 0, 0))
    final.paste(bar, (0, 0))
    final.paste(composed, (0, 34))
    final.save(out_path)


def draw_all_img_geometry(
    raster: Image.Image,
    matrix: np.ndarray,
    polygons,
    polylines,
    points,
    out_path: Path,
    *,
    title: str,
) -> None:
    overlay = Image.new("RGBA", raster.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for poly in sorted(polygons, key=lambda p: -len(p.lats)):
        pts = [apply_matrix(matrix, lon, lat) for lat, lon in zip(poly.lats, poly.lons)]
        color = TYPE_COLOR.get(poly.ext_type, DEFAULT_COLOR)
        if len(pts) >= 3:
            draw.polygon(pts, fill=(*color, 55), outline=(*color, 180))

    for line in polylines:
        pts = [apply_matrix(matrix, lon, lat) for lat, lon in zip(line.lats, line.lons)]
        color = TYPE_COLOR.get(line.ext_type, (255, 255, 255))
        if len(pts) >= 2:
            draw.line(pts, fill=(*color, 255), width=3)

    for point in points:
        x, y = apply_matrix(matrix, point.lon, point.lat)
        r = 5
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 240), outline=(0, 0, 0, 240), width=1)

    composed = Image.alpha_composite(raster, overlay)
    bar = Image.new("RGBA", (composed.width, 34), (0, 0, 0, 170))
    bd = ImageDraw.Draw(bar)
    bd.text((10, 8), title, fill=(255, 255, 255), font=_font(15))
    final = Image.new("RGBA", (composed.width, composed.height + 34), (0, 0, 0, 0))
    final.paste(bar, (0, 0))
    final.paste(composed, (0, 34))
    final.save(out_path)


def draw_raster_segmentation(
    raster: Image.Image,
    out_path: Path,
    title: str,
    matrix: np.ndarray,
) -> tuple[dict[str, int], dict]:
    """Segment obvious features from the Garmin raster itself for visual ground truth."""
    rgb = np.array(raster.convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    overlay = raster.copy()
    draw = ImageDraw.Draw(overlay, "RGBA")
    counts: dict[str, int] = {}
    geometry = {"type": "FeatureCollection", "features": []}

    for name, cfg in SEGMENT_FEATURES.items():
        lo, hi = cfg["hsv"]
        mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_TC89_KCOS)
        color = cfg["color"]
        kept = 0
        for contour in contours:
            if cv2.contourArea(contour) < cfg["min_area"]:
                continue
            eps = 0.005 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, eps, True).reshape(-1, 2)
            pts = [(int(x), int(y)) for x, y in approx]
            if len(pts) >= 3:
                draw.line(pts + [pts[0]], fill=(*color, 255), width=3)
                ring_geo = [pixel_to_lonlat(matrix, x, y) for x, y in pts]
                ring_geo.append(ring_geo[0])
                geometry["features"].append({
                    "type": "Feature",
                    "properties": {
                        "feature": name,
                        "pixel_area": float(cv2.contourArea(contour)),
                        "vertices": len(pts),
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [ring_geo],
                    },
                    "pixel_geometry": [pts + [pts[0]]],
                })
                kept += 1
        counts[name] = kept

    bar = Image.new("RGBA", (overlay.width, 34), (0, 0, 0, 170))
    bd = ImageDraw.Draw(bar)
    bd.text((10, 8), title, fill=(255, 255, 255), font=_font(15))
    final = Image.new("RGBA", (overlay.width, overlay.height + 34), (0, 0, 0, 0))
    final.paste(bar, (0, 0))
    final.paste(overlay, (0, 34))
    final.save(out_path)
    return counts, geometry


def make_comparison(seg_path: Path, img_path: Path, out_path: Path) -> None:
    left = Image.open(seg_path).convert("RGBA")
    right = Image.open(img_path).convert("RGBA")
    height = max(left.height, right.height)
    width = left.width + right.width
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    canvas.paste(left, (0, 0))
    canvas.paste(right, (left.width, 0))
    canvas.save(out_path)


def render(snapshot_path: Path, hole_number: int, course_img: Path | None = None, per_type: bool = True) -> dict:
    hole = snapshot_hole(snapshot_path, hole_number)
    course_id, raster_hole_number = course_and_raster_hole(hole)
    if course_img is None:
        for candidate in (
            ROOT / "data" / "courseview" / f"{course_id}.img",
            ROOT / "data" / "courseview" / f"{course_id}_coursedata.pb",
        ):
            if candidate.exists():
                course_img = candidate
                break
    if course_img is None or not course_img.exists():
        raise FileNotFoundError(f"CourseView IMG/PB for course {course_id} not found")

    raster = fetch_raster(hole["holeImageUrl"])
    matrix, fit_diag = fit_lonlat_to_pixel(hole)
    bbox = image_bbox_geo(matrix, *raster.size)
    tre, polygons, polylines, points = parse_img_all(course_img)
    selected = polygons_in_view(polygons, bbox)
    selected_lines = polygons_in_view(polylines, bbox)
    selected_points = points_in_view(points, bbox)
    counts = Counter(poly.ext_type for poly in selected)
    line_counts = Counter(line.ext_type for line in selected_lines)
    point_counts = Counter(point.ext_type for point in selected_points)

    stem = f"gid{course_id}_rasterh{raster_hole_number:02d}_snapshot_h{hole_number:02d}"
    all_path = OUT / f"{stem}_all_types.png"
    all_geometry_path = OUT / f"{stem}_all_img_geometry.png"
    seg_path = OUT / f"{stem}_raster_segmentation.png"
    comparison_path = OUT / f"{stem}_comparison_segmentation_vs_img.png"
    draw_overlay(
        raster,
        matrix,
        selected,
        all_path,
        title=f"CourseView IMG over Garmin raster · gid {course_id} · hole {hole_number}",
    )
    segmentation_counts, segmentation_geometry = draw_raster_segmentation(
        raster,
        seg_path,
        title=f"Raster-derived visible features · gid {course_id} · hole {hole_number}",
        matrix=matrix,
    )
    draw_all_img_geometry(
        raster,
        matrix,
        selected,
        selected_lines,
        selected_points,
        all_geometry_path,
        title=(
            f"IMG polygons+lines+points · "
            f"{len(selected)} polys / {len(selected_lines)} lines / {len(selected_points)} pts"
        ),
    )
    make_comparison(seg_path, all_geometry_path, comparison_path)

    per_type_paths = []
    if per_type:
        for ext_type, _count in counts.most_common():
            polys = [poly for poly in selected if poly.ext_type == ext_type]
            out = OUT / f"{stem}_type_0x{ext_type:06x}.png"
            draw_overlay(
                raster,
                matrix,
                polys,
                out,
                title=f"ext_type 0x{ext_type:06x} · {len(polys)} polygons",
                alpha=135,
            )
            per_type_paths.append(str(out.relative_to(ROOT)))

    segmentation_geometry_path = OUT / f"{stem}_raster_segmentation_geometry.json"
    segmentation_geometry_path.write_text(json.dumps(segmentation_geometry, ensure_ascii=False, indent=2))

    diag = {
        "snapshot": str(snapshot_path.relative_to(ROOT) if snapshot_path.is_relative_to(ROOT) else snapshot_path),
        "course_id": course_id,
        "raster_hole_number": raster_hole_number,
        "snapshot_hole_number": hole_number,
        "course_img": str(course_img.relative_to(ROOT) if course_img.is_relative_to(ROOT) else course_img),
        "raster_size": raster.size,
        "fit": fit_diag,
        "image_bbox": {
            "south": bbox[0],
            "west": bbox[1],
            "north": bbox[2],
            "east": bbox[3],
        },
        "parsed_polygons_total": len(polygons),
        "parsed_polylines_total": len(polylines),
        "parsed_points_total": len(points),
        "view_selection": "geometry_bbox_intersects_raster_geo_bbox",
        "polygons_in_view": len(selected),
        "polylines_in_view": len(selected_lines),
        "points_in_view": len(selected_points),
        "type_counts_in_view": {f"0x{k:06x}": v for k, v in counts.most_common()},
        "line_type_counts_in_view": {f"0x{k:06x}": v for k, v in line_counts.most_common()},
        "point_type_counts_in_view": {f"0x{k:06x}": v for k, v in point_counts.most_common()},
        "raster_segmentation_counts": segmentation_counts,
        "raster_segmentation_features": len(segmentation_geometry["features"]),
        "all_types_overlay": str(all_path.relative_to(ROOT)),
        "all_img_geometry_overlay": str(all_geometry_path.relative_to(ROOT)),
        "raster_segmentation_overlay": str(seg_path.relative_to(ROOT)),
        "raster_segmentation_geometry": str(segmentation_geometry_path.relative_to(ROOT)),
        "comparison_overlay": str(comparison_path.relative_to(ROOT)),
        "per_type_overlays": per_type_paths,
    }
    diag_path = OUT / f"{stem}_diagnostics.json"
    diag_path.write_text(json.dumps(diag, ensure_ascii=False, indent=2))
    diag["diagnostics"] = str(diag_path.relative_to(ROOT))
    return diag


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--hole", type=int, default=2)
    parser.add_argument("--course-img", type=Path, default=None)
    parser.add_argument("--no-per-type", action="store_true")
    args = parser.parse_args()

    diag = render(args.snapshot, args.hole, args.course_img, per_type=not args.no_per_type)
    print(f"[ok] all-types overlay: {diag['all_types_overlay']}")
    print(f"[ok] diagnostics: {diag['diagnostics']}")
    print(
        "[fit] "
        f"n={diag['fit']['control_points']} "
        f"x_mean={diag['fit']['residual_x_mean_px']:.2f}px "
        f"x_max={diag['fit']['residual_x_max_px']:.2f}px "
        f"y_mean={diag['fit']['residual_y_mean_px']:.2f}px "
        f"y_max={diag['fit']['residual_y_max_px']:.2f}px"
    )
    print("[types] " + ", ".join(f"{k}:{v}" for k, v in diag["type_counts_in_view"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
