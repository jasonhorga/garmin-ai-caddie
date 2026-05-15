# Garmin Golf Project — Status

**Last updated**: 2026-05-15
**Working directory**: `/Users/jason/workspace/garmin/`

---

## 1. Goal

**Long term**: build an AI caddie that uses the user's full Garmin shot history + course geometry to give actionable advice (club selection, target lines, risk).

**Current focus (this week)**: extract per-hole hazard data (fairway / green / bunker / water polygons) from Garmin and overlay it with shot data, so the AI has a complete picture of where each shot landed relative to course features.

**User**: ~10-year Garmin golfer. 14-club bag (1W, 3W, 3H, 5I–9I, PW, A, 50°, 54°, 58°, putter). Plays mostly in Beijing/China. ~443 rounds in Garmin (after dedup, 418 rounds covering ~90 unique courses).

---

## 0. Latest Breakthrough — Prodgeometry Works

The reliable short-term geometry route is Garmin CourseView `prodgeometry`, not
the small IMG alone. For 黑骑士 B (`globalId=31795`) hole 2:

- The encrypted `prodgeometry` zip was decrypted using the Garmin Golf app's
  token/image-key flow and extracted locally.
- The extracted `.drc` files are valid Draco meshes, not opaque blobs.
- `Fairway.drc`, `Green.drc`, `Bunker.drc`, `Lake.drc`, `Rough.drc`,
  `Teebox.drc`, and related meshes decode cleanly.
- The decoded local meter coordinates map onto the Garmin 730x730 raster using
  shot control points with max residual under 0.6 px.

Working files:

- Key/decrypt/extract script:
  [fetch_courseview_geometry_key.js](/Users/jason/workspace/garmin/fetch_courseview_geometry_key.js)
- Draco decode script:
  [decode_courseview_geometry.js](/Users/jason/workspace/garmin/decode_courseview_geometry.js)
- 730 raster overlay script:
  [overlay_prodgeometry_on_raster.py](/Users/jason/workspace/garmin/overlay_prodgeometry_on_raster.py)
- Validated overlay:
  `output/prodgeometry_overlay/gid31795_rasterh02_prodgeometry_h02_overlay.png`
- Diagnostics:
  `output/prodgeometry_overlay/gid31795_rasterh02_prodgeometry_h02_diagnostics.json`

This means IMG is still worth reverse-engineering for coarse layers/anchors, but
the production AI-caddie hazard model should start from `prodgeometry` meshes.

Batch validation has now been run for 黑骑士 B holes 1-9:

- 9/9 holes downloaded, decrypted, extracted, and decoded successfully.
- Holes 1-7 and 9 each decoded 13 mesh sources.
- Hole 8 decoded 11 mesh sources; `Fairway.drc` and `TreeArea.drc` are absent,
  likely because Garmin does not provide separate fairway/tree-area meshes for
  that short hole.
- 9/9 holes generated `hazards.json`, tee distance JSON, and overlay PNGs.

Working batch scripts:

- [batch_prodgeometry_course.py](/Users/jason/workspace/garmin/batch_prodgeometry_course.py)
- [export_prodgeometry_hazards.py](/Users/jason/workspace/garmin/export_prodgeometry_hazards.py)

Key local outputs:

- `output/prodgeometry_batch/gid31795_holes_01-09_summary.json`
- `output/prodgeometry_hazards/gid31795_h01_hazards.json` through
  `output/prodgeometry_hazards/gid31795_h09_hazards.json`
- `output/prodgeometry_overlay/gid31795_prodgeometry_h01-h09_contact_sheet.png`

---

## 2. Data Layers Available

| Layer | Source | Files | Size | Status |
|---|---|---|---|---|
| Scorecard summaries | `connect.garmin.cn/golf-api/.../scorecard/summary` | `data/summary.json` | 720 KB | 443 rounds |
| Scorecard details | `.../scorecard/detail?scorecard-ids={sid}` | `data/scorecards/*.json` | 5 MB | per-round |
| Shot-by-shot | `.../shot/scorecard/{sid}/hole` | `data/shots/*.json` | 17 MB | 20,624 shots across 443 rounds; **each shot is WGS84 lat/lon (semicircle×2³¹)**, no pixel coords |
| Course geometry (CourseView IMG) | `omt.garmin.cn/CourseViewData/coursedata/images/{rel}/courses/{id}` | `data/courseview/*.pb` | 6.5 MB | 90 courses; anonymous access (no auth); useful coarse layers/anchors |
| Course geometry (prodgeometry) | `securemaps.garmin.cn/golf/coursegenout/prodgeometry/...` + `CourseViewData/image-key/v2` | `data/courseview/prodgeometry/` | per-hole zip | encrypted zip; now decrypted for 31795 hole 2; best fine geometry source |
| Esri World Imagery (satellite tiles, WGS84) | `server.arcgisonline.com/...` | `data/esri_tiles/*.jpg` | 2.3 MB cache | Fetched on demand by zoom/x/y |
| BirdsEye JPGs (730×730 raster) | Old probe data | `logs/probe_map_bodies/` | — | Used by `build_hole_overlay.py` only; new code doesn't depend on these |

### Authentication

- Garmin CN web requires `Cookie` + `connect-csrf-token` header (no Bearer/OAuth). Cookie lifetime ~9 h.
- `omt.garmin.cn/CourseViewData/coursedata/*` endpoints are **anonymous** — no auth needed.
- `CourseViewData/image-key/v2` requires the Garmin Golf mobile token exchange;
  local OAuth material lives under `.garmin_tokens/` and must not be printed.
- Tokens stored in `.garmin_tokens/web_cookie.txt` + `csrf.txt` (gitignored).

---

## 3. Code Layout (after cleanup)

```
.
├── README.md           # Original auth+fetch doc (still valid for layers 1-3)
├── FEASIBILITY.md      # Earlier prototype-feasibility writeup (May 9, 2026)
├── STATUS.md           # THIS DOCUMENT
├── clubs.json          # User's 14-club bag mapping; Garmin clubId → name/retired
├── pyproject.toml      # uv-managed; deps: requests, Pillow, opencv-python, numpy
│
├── fetch.py            # Pull scorecards (+ shots via --shots)
├── fetch_courseview.py # Pull CourseView IMG for every course in scorecards (one-shot batch)
├── parse_courseview.py # IMG → GMP → TRE/RGN/LBL → polygon list (lat/lon)
├── render_courseview.py# Render polygons to PNG (no satellite background)
├── build_hole_view.py  # Render polygons over Esri satellite tiles — the current focus
├── build_dashboard.py  # Stats dashboard (trend, course map, distance histogram, ...)
├── build_hole_overlay.py # OLD: per-hole shot overlay on 730×730 BirdsEye JPG (legacy data)
├── ai_review.py        # Single-round LLM review (Claude Sonnet); brief → recap
├── segment_hole.py     # OpenCV HSV segmentation on BirdsEye JPG (alternative path, paused)
│
├── data/
│   ├── courseview/     # 90 IMG files (course-id keyed) + releases.pb
│   ├── scorecards/     # 443 scorecard JSONs
│   ├── shots/          # 443 shot JSONs (some are {"_no_data": true} for older rounds)
│   └── esri_tiles/     # Disk cache of Esri tiles, z/y/x naming
│
├── output/
│   ├── dashboard/      # Generated HTML dashboard (built from build_dashboard.py)
│   ├── courseview/     # PNG renders of polygons (no background)
│   ├── hole_views/     # PNG renders of polygons + satellite (current debug target)
│   ├── ai_reviews/     # LLM review outputs
│   └── …
│
└── archive/            # Dead-but-kept exploration: probe*.py, video frames, IMG header probes
```

External tools cloned during development (kept under `/tmp/`):
- `/tmp/imgdecode-mb/` — burto's C decoder for Garmin IMG (used as reference for RGN polygon format)
- `/tmp/garmin-img-parser/` — asamm Java parser (used as reference for bitstream decoder)
- `/tmp/mkgmap-r4924/` — mkgmap (not actually used; can delete)
- `/tmp/garmin_subfiles.pdf` + `.txt` — Memotech IMG format spec

---

## 4. Recent Phase 1 — CourseView IMG Parser

**What it does**: parses Garmin's proprietary CourseView IMG file into WGS84 lat/lon polygons + feature type codes.

**Status**: 16/16 subdivisions decode with perfect alignment; **591 polygons extracted from 黑骑士 (course 31795)**. 10% (60 polygons) still drift OOB — likely level-0 overview polygons or edge cases.

### Format discoveries (not documented in OSM wiki, Memotech PDF, or asamm parser)

CourseView IMG embeds polygons inside the standard Garmin GMP container, but with **two CourseView-specific quirks** I had to reverse from empirical byte-tracing:

1. **Subtype bit 6 (the "unk1" bit imgdecode-mb names but never uses)** indicates a 4-byte trailer after the bitstream, format `02 02 LL NN`.

2. **The trailer's third byte LL is a length code**:
   - `LL == 0x03` → 4-byte trailer (the common case, mid-group polygons)
   - `LL == 0x07` → 6-byte trailer (last polygon in a group; 2 extra padding bytes follow `NN`)

Before these two fixes the decoder ran past subdivision span_end and mis-aligned every polygon after the first OK-looking one. After: every subdivision parses cleanly to `span_end`.

### Format summary (for future reference)

```
IMG container (Garmin filesystem, 512-byte blocks)
  └─ FAT @0x1000 lists subfiles, second entry is .GMP
GMP file (single subfile inside the IMG)
  ├─ GMP header @0x00 — points to TRE/RGN/LBL/DEM start offsets (absolute in GMP)
  ├─ TRE header @0xf0:
  │   ├─ bbox: 4 × s24 semicircles, scale 360/2²⁴
  │   ├─ map_levels offset+length (4 bytes/level: zoom, bits-per-coord, n_subdivisions)
  │   ├─ subdivisions offset+length (14B/last-level rec, 16B/non-last)
  │   └─ object_groups @TRE+0x7C: per-subdivision cumulative offsets into RGN data
  ├─ RGN header @0x26f — points to extended-type polygon data section
  ├─ LBL @0x3e4 — metadata strings only (course name/address/tee colors); NO feature labels
  └─ DEM @0x68d — heightmap (not used)

Extended-type polygon record:
  byte 0: type
  byte 1: subtype (low 5 bits) + flags (bit 5=hasLabel, bit 6=unk-trailer, bit 7=hasExtra)
  bytes 2-3: lon delta from subdivision center (s16, scaled by 2^(24-bits))
  bytes 4-5: lat delta (s16)
  byte 6: bitstream length indicator (LSB=1 → single byte; LSB=0 → read next byte too)
  byte 7: bitstream encoding info (low 4 bits = base lon bits, high 4 = base lat bits)
  bytes 8+:
    bitstream (length from above) — bit-packed vertex deltas
      First bits: sign-same flag + optional shared sign per axis, then 1 longExtraBit
      Then loop: read longBits + latBits per vertex until exhausted (handles negZero stretch recursion)
    optional 3-byte label offset (if hasLabel)
    optional N-byte extra (if hasExtra; usually 1 byte 0x08)
    optional 4 or 6-byte unk trailer (if bit 6 set; format `02 02 LL NN [..]`)
```

### `ext_type` codes seen in 31795.img (黑骑士)

`ext_type = 0x10000 | (type_byte << 8) | subtype`. Counts and shapes from 591 decoded polygons:

| ext_type | n | avg vertices | observed shape | best guess |
|---|---|---|---|---|
| 0x011407 | 258 | 14 | small angular shapes scattered | bunkers + greens + tees? |
| 0x011402 | 103 | 5 | tiny markers | yardage points? |
| 0x011405 | 100 | 31 | small elongated | cart path segments? |
| 0x011403 | 30 | 95 | narrow strips following holes | fairway centerline? |
| 0x01140e | 27 | 71 | large overlapping ovals (300×400m each) | **per-hole overview blob** (level 0, not detail) |
| 0x011409 | 27 | 119 | large overlapping ovals | same — another overview layer |
| 0x011404 | 27 | 28 | medium irregular | ? |
| 0x010b08 | 17 | 67 | thin lines along visible cart paths | **cart paths** (confirmed visually) |
| 0x011400 | 1 | 8 | — | edge case |
| others (singletons) | — | varies | likely course boundary / OB markers | — |

**THIS MAPPING IS LARGELY UNVERIFIED.** It's based on shape and frequency. Most identifications are guesses except cart paths.

---

## 5. The Current Uncertainty (the active question)

After overlaying the decoded polygons on Esri satellite tiles for 黑骑士:

- **Cart paths (0x010b08)** clearly trace the visible cart paths in satellite — strong alignment evidence.
- **But many other polygons cover non-course areas**: warehouses east of the course, the river south of the course. Either:
  - (a) There's a real coordinate offset (Garmin polygons are shifted relative to satellite); or
  - (b) Those polygons aren't course features but rather building/OB/boundary markers Garmin includes for context; or
  - (c) Many of the "fairway/water" type codes I assigned colors to are actually course-level summary polygons (not individual features).

The most likely explanation is **(c) + (b)**: some `ext_type` codes are level-0 overview blobs, others are legitimate context features (clubhouse, OB), and the actual fairway/green/bunker mapping is in different codes than I labeled.

**The cleanest verification**: overlay actual shot lat/lon (which we know are correct since you played them) and see if shots land on the polygons in reasonable ways. Shots should be:
- Mostly inside one of the "playable surface" polygon types
- Distance distribution should match plausible club distances (1W = ~180m median for this user)
- Misses to bunkers/water should show as shots landing inside those polygons

Without this verification we can't confidently say "polygon at X represents bunker Y".

**Files showing the current state**:
- `output/hole_views/31795_satellite.png` — combined polygon + Esri (the "doesn't look perfectly aligned" image)
- `output/hole_views/debug/31795_only_*.png` — per-type renders showing what each `ext_type` covers
- `output/courseview/31795.png` — polygons over plain dark background, no satellite

---

## 6. Map Coordinate System Note

- **Garmin shot data**: WGS84 lat/lon stored as `semicircles × 2³¹` (need to divide by 2³¹ then multiply by 180).
- **Garmin CourseView TRE bbox**: WGS84 lat/lon stored as `s24 semicircles` (scale `360 / 2²⁴`).
- **Garmin subdivision centers**: same s24 format as bbox.
- **Esri World Imagery**: WGS84 → Web Mercator tiles, **safe to overlay Garmin data on directly**.
- **DO NOT** use Apple Maps, AutoNavi (高德), Tencent, Baidu satellite tiles in China — they encode in GCJ-02, which shifts WGS84 coords ~600m SW. We confirmed this experimentally: the user dropped a WGS84 pin (40.027, 116.581) on Apple Maps and saw it ~600m SW of the actual 黑骑士 course.

---

## 7. Known limitations / open questions

1. **Type → feature mapping is unverified**. We need shot-overlay validation before we can claim "bunker at (lat, lon)".
2. **60/591 polygons (~10%) at 黑骑士 are OOB** of the bbox. Not investigated — could be decoder edge cases or legitimate features outside course extent.
3. **Hole boundaries unknown**. We have 19 level-1 subdivisions but don't know which subdivision corresponds to which hole number (1–18). Probable to infer from tee positions once we decode the points sections.
4. **Point sections (tee/pin) not yet decoded**. RGN has two additional sections (511 B + 309 B in 黑骑士) that we identified earlier as "point-like" data. Decoding these would give us tee + pin lat/lon per hole.
5. **Pencil shape of fairway polygons** — even when we filter to small types, fairways aren't traced cleanly. They might be in the level-0 summary types (0x01140e / 0x011409) but those are too smoothed to be useful.

---

## 8. Recent learnings worth preserving

- **Don't trust summaries blindly**. Compaction summary said "shot data has x/y pixel coords directly on 730×730 BirdsEye" — that was true for old probe data (`logs/probe_map_bodies/snapshot_*.json`) but is false for the bulk-fetched `data/shots/*.json` (which only has lat/lon). I built a plan around the wrong fact and burned 2 hours before the user pointed it out. Now: **before any plan that depends on a data property, open one file and verify**.
- **CourseView IMG embeds proprietary format quirks not in any public spec**. Reverse-engineering required byte-level tracing; jGarminImgParser and imgdecode-mb both missed the bit-6 unk trailer + variable-length length code.
- **Filter visualizations one type at a time** when the type-→feature mapping is unknown. Stacking all types with guessed colors produces unverifiable noise.
- **Use WGS84 satellite (Esri) not Chinese map providers** when verifying any geographic data in China; GCJ-02 will shift everything by ~600m.

---

## 9. Suggested next steps

In priority order:

1. **Overlay shots on top of polygons** for 1 round at 黑骑士 (`build_hole_view.py` + extract shots from a `data/shots/{scorecard_id}.json`). This is the next 30–60 min task and immediately validates or refutes the alignment hypothesis.
2. **Decode point sections** in RGN to get tee + pin lat/lon. The point format is much simpler than the polygon bitstream (no delta compression). Should be ~1 hr.
3. **Map subdivisions to hole numbers**. Probably: for each hole, find the subdivision whose bbox contains the tee (from step 2). Once known, we can extract per-hole feature lists.
4. **Identify which `ext_type` is which feature** using shot-overlay frequency (shots-in-polygon counts per type) + known facts (tee is near hole start, green is near hole end).
5. **Fix the remaining ~10% OOB polygons** — likely a small bitstream edge case still missing.
6. **Batch render all 90 courses** once 黑骑士 is verified end-to-end.

---

## 10. Big files in the repo

- `ScreenRecording_05-08-2026 19-00-09_1.mp4` (120 MB, root) — original analysis of a WeChat mini-program UI. Can be deleted/moved; not referenced by any code.
- `output/dashboard/` (≈ 60+ MB) — generated HTML + per-course detail pages; rebuilt by `build_dashboard.py`
- `data/shots/` (17 MB) — raw shot data; needed
- `data/courseview/` (7.4 MB) — IMG files for 90 courses; needed
