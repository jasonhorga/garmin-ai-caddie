"""Color-segment a BirdsEye hole image into fairway/green/bunker/water polygons.

The Garmin 730×730 raster3d render has very saturated zones — feature extraction
via HSV thresholding + contour finding works surprisingly well. Output: polygon
geometry per feature class, drawn as overlay PNGs and saved as GeoJSON-like JSON
(coords are still pixel space; conversion to lat/lon needs bbox separately).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]  # repo root: tools/<sub>/<file>.py is 2 dirs deep (P2 reorg fix)
OVERLAY_DIR = ROOT / "output" / "hole_overlays"
OUT_DIR = ROOT / "output" / "segmentation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# HSV ranges tuned by inspection of the 730×730 BirdsEye style.
# Hue (0-179), Sat (0-255), Val (0-255).
FEATURES = {
    "green":   {"hsv": [(35, 80, 80),  (75, 255, 200)],  "color": (0, 200, 0),     "min_area": 80},   # darker green for putting green
    "fairway": {"hsv": [(35, 30, 150), (75, 130, 255)],  "color": (60, 255, 60),   "min_area": 200},  # lighter green
    "bunker":  {"hsv": [(15, 40, 150), (35, 200, 255)],  "color": (255, 200, 100), "min_area": 30},   # tan/sand
    "water":   {"hsv": [(85, 80, 80),  (130, 255, 255)], "color": (50, 100, 255),  "min_area": 80},   # blue
    "rough":   {"hsv": [(35, 5, 60),   (90, 60, 150)],   "color": (90, 130, 70),   "min_area": 200},  # muted greenish background
}


def segment(img_path: Path, out_stem: str) -> dict:
    img = cv2.imread(str(img_path))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    overlay = img.copy()
    geometry: dict[str, list[list[list[int]]]] = {}

    for name, cfg in FEATURES.items():
        lo, hi = cfg["hsv"]
        mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
        # clean up: morphological close to fill small gaps, open to remove noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_TC89_KCOS)
        polys = []
        for c in contours:
            if cv2.contourArea(c) < cfg["min_area"]:
                continue
            # approximate polygon
            eps = 0.005 * cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, eps, True)
            polys.append(approx.reshape(-1, 2).tolist())
            cv2.drawContours(overlay, [approx], -1, cfg["color"], 2)
        geometry[name] = polys
        # also save individual mask preview
        mask_preview = cv2.bitwise_and(img, img, mask=mask)
        cv2.imwrite(str(OUT_DIR / f"{out_stem}_mask_{name}.jpg"), mask_preview)

    cv2.imwrite(str(OUT_DIR / f"{out_stem}_overlay.jpg"), overlay)
    (OUT_DIR / f"{out_stem}_geometry.json").write_text(json.dumps(geometry, indent=2))
    return geometry


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "img_gid031795_hole03_0_220542.jpg"
    src = OVERLAY_DIR / target
    if not src.exists():
        print(f"not found: {src}")
        return
    stem = src.stem
    geom = segment(src, stem)
    print(f"segmented {src.name}:")
    for k, v in geom.items():
        n_pts = sum(len(p) for p in v)
        print(f"  {k:>9}  {len(v):>3} polygons, {n_pts:>5} vertices")
    print(f"\noutputs in {OUT_DIR}:")
    print(f"  {stem}_overlay.jpg     — all polygons drawn over original")
    print(f"  {stem}_mask_*.jpg      — per-class masks")
    print(f"  {stem}_geometry.json   — polygon coordinates (pixel space)")


if __name__ == "__main__":
    main()
