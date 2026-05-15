import math
from pathlib import Path
from parse_courseview import parse_img_all

target = Path("data/courseview/31795.img")
tre, polys, lines, points = parse_img_all(target)

for p in polys:
    min_lat = min(p.lats)
    max_lat = max(p.lats)
    min_lon = min(p.lons)
    max_lon = max(p.lons)
    width_m = (max_lon - min_lon) * 111000 * math.cos(math.radians((min_lat+max_lat)/2))
    height_m = (max_lat - min_lat) * 111000
    area_approx = width_m * height_m
    print(f"Type: 0x{p.ext_type:06x}, Verts: {len(p.lats):>3}, Size: {width_m:.0f}m x {height_m:.0f}m, Area: {area_approx:.0f} sqm")
