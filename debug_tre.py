from pathlib import Path
from parse_courseview import extract_gmp, parse_gmp_header, parse_tre
gmp = extract_gmp(Path("data/courseview/31795.img").read_bytes())
offsets = parse_gmp_header(gmp)
tre = parse_tre(gmp, offsets.tre)
print(f"Ext first subdiv index: {tre.ext_first_subdiv_index}")
print(f"Levels: {len(tre.subdivisions)}")
print(f"ogs length: {len(tre.object_groups)}")
