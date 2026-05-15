from pathlib import Path
from parse_courseview import parse_img_all, parse_polygons, parse_gmp_header, extract_gmp, parse_rgn_header

target = Path("data/courseview/31795.img")
tre, polys, lines, points = parse_img_all(target)
print(f"Original: {len(polys)} polys")

tre.ext_first_subdiv_index = 0
gmp = extract_gmp(target.read_bytes())
offsets = parse_gmp_header(gmp)
rgn = parse_rgn_header(gmp, offsets.rgn)
polys = parse_polygons(gmp, rgn, tre)
print(f"Subdiv 0: {len(polys)} polys")

good = 0
for p in polys:
    min_lat = min(p.lats)
    max_lat = max(p.lats)
    if -90 <= min_lat <= 90 and -90 <= max_lat <= 90:
        good += 1
print(f"Good polys: {good}")
