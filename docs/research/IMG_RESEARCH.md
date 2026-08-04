# Garmin CourseView IMG Research

Last updated: 2026-08-04

## Goal

Understand Garmin CourseView IMG enough to extract reliable golf-course geometry
for the AI caddie: green, fairway, bunker, water, paths, tee/pin/markers, and
hole-level grouping.

## 2026-08-04 Deep Mine Findings

### The CourseView payloads are separate products, not one hidden super-map

The current Garmin Golf APK and live endpoints establish three device map paths:

| Garmin map path | Endpoint / asset | What it actually contains |
|---|---|---|
| `MEDIUM` | anonymous `courseData/{buildId},{globalLayoutId},32` | scorecard facts, one ordered route per hole, 30-value green radial outline, typed point anchors and Tee rating/slope |
| `MEDIUM_PLUS` | the same URL plus `/Hazards` | the MEDIUM payload plus typed two-point hazard spans; it does **not** add hazard polygons |
| `INTERMEDIATE` | `coursedata/images/{partNumber}/courses/{globalLayoutId}?unitId=...&version=...` | JSON envelope with base64 `Image`, `Gma` and `Unlock`; in the Cypress sample the decoded `Image` is byte-for-byte the same DSKIMG as protobuf field 3 (`60,416` bytes, SHA-256 `abe7910d...a73e2`) |

`prodgeometry` remains a fourth, separate encrypted per-hole package with the
precise Draco surfaces. Garmin Green Contours are yet another subscription-gated
download. The official support page says they arrive with a course download when
available and require Garmin Golf Membership; neither the anonymous DSKIMG nor
the lightweight `courseData` response should be relabelled as that product.

### Catalogue and contour availability

The anonymous catalogue/release JSON names the previously unknown field directly:
`HasGreenContour`. Positive samples Cypress Point (`3881`) and Mission Hills Els
(`31669`) and negative samples Black Knight B (`31795`) and Sentosa Serapong
(`32235`) reproduce that value in both catalogue and release metadata. DSKIMG
area type `0x01140b` occurred `19/21` times in the two positive packages and zero
times in the two negative packages. That is a useful availability correlation,
not proof that this area type contains the subscription contour surface.

### DSKIMG FAT and DEM facts

The old IMG extractor silently read only the first FAT record. A CourseView FAT
record has at most 240 block pointers (`120 KiB` at 512-byte blocks); larger GMPs
continue in repeated 8.3-name records whose byte `0x11` is the part number. The
parser now joins every contiguous part and fails on missing, duplicate or
out-of-range blocks.

After that fix, real DEM headers give the following course-level grids:

| Course | `HasGreenContour` | Grid | Approximate spacing | Elevation range |
|---|---:|---:|---:|---:|
| Cypress Point `3881` | true | `290×191` | `8–10 m` | `0..282 ft` |
| Mission Hills Els `31669` | true | `211×157` | `28–31 m` | `67..358 ft` |
| Black Knight B `31795` | false | `51×54` | about `30 m` | `49..116 ft` |
| Sentosa Serapong `32235` | false | `112×105` | about `30 m` | `-18..308 ft` |

The default CourseView DEM sample codec is now decoded end-to-end: variable-size
tile descriptors, MSB-first sample streams, adaptive hybrid/length/BigBin
predictors, plateaus and followers, height wrapping, tile assembly and bilinear
sampling. Three independent checks keep this from being a format guess:

- Frank Stinner's public reference stream (`ff` repeated ten times plus `c02e`)
  reproduces its exact `64×64` grid, with only the lower-left sample equal to 3;
- an unmodified mkgmap r4924 `DEMTile` generated a separate `17×9` fixture that
  crosses the 64-value adaptive boundary. The decoder restores the exact source
  matrix (little-endian int16 SHA-256
  `4ab0031280edcc3570410ec406867e86c960fc8b90cf63bd0823306a36e4bda2`),
  consumes 337 bits and leaves 7 padding bits;
- all 26 tiles from the four live Garmin payloads decode to their exact declared
  extrema, and every tile leaves only `0–7` padding bits.

For the current four-course corpus, every DEM has one level, `shrinkValue=0`
(`factor=1`) and `encodingType=0`. Non-default shrink, non-zero encoding types
and multi-level DEMs therefore remain explicit corpus gaps; the decoder rejects
non-default shrink instead of silently treating it as the common form.

Prodgeometry provides a source-independent spatial check. A ground vertex's
absolute height is `position.y + hole.ElevationMinimum`; after converting its
local X/Z position back to WGS84, the DSKIMG grid gives:

| Course | Ground vertices | Median vertical bias | Median error after removing bias | P95 after removing bias |
|---|---:|---:|---:|---:|
| Cypress Point `3881` | 34,751 | `-0.12 m` | `0.98 m` | `3.63 m` |
| Mission Hills Els `31669` | 130,949 | `-0.91 m` | `0.44 m` | `3.60 m` |
| Black Knight B `31795` | 80,190 | `+3.17 m` | `0.28 m` | `4.83 m` |
| Sentosa Serapong `32235` | 239,847 | `+0.84 m` | `0.98 m` | `5.16 m` |

The validator reports the raw bias rather than adjusting production data. The
larger tail on steep ground is expected when comparing a roughly 30 m DEM with
dense per-hole meshes. Its authority-bearing JSON is
`deepmine-output/dem-prodgeometry-crosscheck.json` on the homeserver, SHA-256
`35372f0164b9831e2654d5428cd940a2603076509331059c8a4171a691558808`.
Els still has Green Contours but only a roughly 30 m ordinary DEM, so successful
sample decoding reinforces rather than changes the conclusion that this is not
the push/putt-level subscription contour payload.

### Lightweight `courseData` semantics proven against prodgeometry

`ai_caddie.courses.courseview_core` now fetches and normalizes the anonymous JSON,
binds `BuildId + GlobalLayoutId`, sorts unreliable provider hole order and keeps
all raw numeric codes. Cross-checking 17 real holes from Els, Black Knight and
Sentosa against their matching Draco meshes proved:

- all `12/12` line-code `3241` spans land on `Lake.drc` (median endpoint error
  `0.62 m`), and all `38/38` code `3242` spans land on `Bunker.drc` (`0.16 m`);
- all `7/7` anchor-code `18123` points land on `Lake.drc`, and all `12/12`
  code `18124` points land on `Bunker.drc`;
- for all 50 proven water/bunker spans, point 1 is Tee-side and point 2 is
  green-side. This is a legitimate coarse `到 / 过` fallback;
- codes `3243`, `3244` and `18125` remain unknown and receive no product label.

The route endpoint matches the `hole.json` dogleg/green centre within `0.10 m` in
all 17 holes. The 30 `GreenRadii` samples consistently start at north and run
clockwise (all 17 best fits; median start `89.5°` in an east/north frame). Their
absolute scale versus `Green.drc` is course-dependent (`0.8685–1.0022 m` per raw
unit), so the parser intentionally keeps them unitless until the difference
between the legacy outline and the rendered green/fringe is explained.

The production fetch path was also exercised directly against the anonymous
endpoint on 2026-08-04, rather than only through fixtures. Cypress Point build
`309`, layout `3881` returned 18 holes and 5 tees in both variants. `MEDIUM`
contained 18 route lines (`3240`); `MEDIUM_PLUS` contained 60 lines with raw
codes `3240`, `3242` and `3243`. Both responses passed request/response BuildId
and GlobalLayoutId authority binding.

## Current Position

The IMG files are definitely valuable. They are not random blobs. They are Garmin
GMP-wrapped map files containing TRE/RGN/LBL/DEM subfiles and stable extended
geometry types.

The earlier mismatch was primarily a parser bug: we treated the TRE7
extended-type offset records as if they started at subdivision 0. mkgmap's reader
shows those records begin at the detailed level, so Black Knight's overview
subdivision has no extended geometry span.

There was a second trap: mkgmap will blindly dump private/garbage-looking records
inside the same spans. Some have impossible coordinates, so matching mkgmap's raw
object count is not enough. The safer CourseView read is to keep only types
declared in the TRE extended-type overview table.

After those fixes, the parser is much less noisy, but the bigger conclusion is
also sharper: this IMG is not a complete vector equivalent of the 730 hand-drawn
raster. It contains coarse vector layers and anchors, not every visible tree,
bunker texture, fairway stripe, or green detail.

## Known Container Layout

For `data/courseview/31795.img`:

- Outer file is a Garmin DSKIMG container.
- FAT contains one logical `.GMP` subfile, possibly split across continuation
  records when it exceeds 120 KiB.
- GMP contains:
  - `TRE` at `0x00f0`
  - `RGN` at `0x026f`
  - `LBL` at `0x03e4`
  - `DEM` at `0x068d`
- No `TYP` subfile exists in the IMG or GMP.
- Protobuf wrapper `31795_coursedata.pb` has:
  - field 1: release metadata
  - field 3: embedded DSKIMG bytes
  - no obvious style/type table

The local Memotech Garmin subfile spec says GMP internal offsets are based on the
beginning of the GMP file. That matches the current Python parser's treatment of
TRE/RGN section offsets for this file.

## Current Parser Coverage

[parse_courseview.py](../../tools/courseview/parse_courseview.py) currently decodes:

- complete multi-record FAT/GMP assembly
- Extended polygons
- Extended polylines
- Extended points
- DEM header, level grid, spacing, descriptor spans and min/max elevation

The Garmin DEM tile delta-compression itself is still opaque; the parser does
not fabricate sample heights from the header.

For `31795.img`:

- polygons: 26
- polylines: 9
- points: 11

The decoded `31795.img` type histogram after TRE overview filtering:

- polygon: `0x011407` x10, `0x01140e` x9, `0x011409` x2, plus five singleton types
- line: `0x012e00` x9
- point: `0x013801` x8, `0x013800` x3

For `31795` the TRE extended type overview/table contains:

- line: `0x012e00`
- areas: `0x010b08`, `0x010d01`, `0x011400`, `0x011402`, `0x011403`, `0x011404`,
  `0x011405`, `0x011407`, `0x011409`, `0x01140e`
- points: `0x013800`, `0x013801`

Note: the 3-byte records in the TRE extended type table appear to be
`type, unknown/flags, subtype`, not `type, subtype, unknown`.

## Cross-Course Pattern

The type schema is stable across tested courses:

- Black Knight A/B/C (`31794`, `31795`, `31796`) produce the same bbox, counts,
  and type histogram, which implies Garmin stores the whole club/course complex
  rather than one 9-hole course per global ID.
- 北湖九号 (`41825`) and 龙泉谷 (`39315`) have the same dominant area types:
  `0x011407`, `0x011402`, `0x011405`, `0x011403`, `0x01140e`, `0x011409`,
  `0x011404`, `0x010b08`, plus a few course-specific types.

This strongly suggests CourseView uses a private but consistent golf schema.

## Validation Notes

### 1. Java oracle

Java is now installed. Two Java paths were tested:

- Old JGarminImgParser 1.2 does not handle this GMP-wrapped CourseView IMG via
  its normal entry point; it fails before finding TRE.
- mkgmap r4924 has useful internal TRE/RGN/LBL readers. A local dump tool
  [tools/java/DumpMkgmapCourseView.java](/Users/jason/workspace/garmin/tools/java/DumpMkgmapCourseView.java)
  bypasses the normal FAT reader, feeds the GMP subfile directly, and dumps
  polygons/lines/points as JSONL.

Output files:

- `output/mkgmap_31795.jsonl`
- `output/mkgmap_31795.stderr`

### 2. Black Knight B hole 2 overlay

The shot control-point fit is excellent:

- 37 control points
- mean error around `0.25 px`
- max error around `0.55 px`

Range check against the 730 raster:

- hole02 raster geo bbox:
  `(south=40.0280629, west=116.5752525, north=40.0307740, east=116.5787843)`
- `31795.img` TRE bbox:
  `(south=40.0197172, west=116.5745544, north=40.0341797, east=116.5882444)`
- The 730 raster footprint is fully inside the IMG TRE bbox.
- Decoded valid geometry intersecting the hole02 raster footprint:
  - polygons: 8
  - lines: 3
  - points: 1
  - types: `polygon:0x010d01`, `polygon:0x01140e`, `polygon:0x011409`,
    `line:0x012e00`, `point:0x013801`
- Undeclared mkgmap raw objects do not help: they have implausible coordinates
  and none plausibly intersect hole02.

After the TRE7 offset and type-table fixes, projected IMG geometry still does
not match the 730 raster at feature level. The shot `x/y` points do land on the
raster, so the raster reference frame is real; the mismatch is that this IMG
does not expose all visible 730 features as separate vector geometry. It has
broad hole/background polygons and a few anchors/lines. See:

- `output/img_raster_overlay/gid31795_rasterh02_snapshot_h02_comparison_segmentation_vs_img.png`
- `output/img_raster_overlay/gid31795_rasterh02_snapshot_h02_diagnostics.json`
- `output/img_raster_overlay/gid31795_rasterh02_snapshot_h02_img_range_diagnosis.json`
- `output/img_raster_overlay/gid31795_course_img_vs_730_footprints.png`

### 3. "Maybe a TYP style file in the IMG tells us the type meanings"

No `TYP` subfile/string is present in `31795.img`, `31795.gmp`, or the protobuf
wrapper.

### 4. Prodgeometry route

The Garmin Golf app downloads encrypted `prodgeometry` zip files separately from
the small CourseView IMG payload. The password is not brute-forced; it is derived
through the app's normal token/image-key flow:

1. Refresh the local Connect DI token from `.garmin_tokens/oauth2_token.json`.
2. Exchange it for Golf DI, then Golf IT.
3. Call `https://omt.garmin.cn/CourseViewData/image-key/v2?imageUrl=...` with
   the signed-in player profile id.
4. Decrypt the returned base64 key using the app's AES-CBC/SHA-256 routine and
   append the app's fixed password suffix.

The project now has a repeatable local pipeline:

```bash
node fetch_courseview_geometry_key.js \
  --image-url '<prodgeometry zip URL or path>' \
  --profile-id '<playerProfileId>' \
  --zip data/courseview/prodgeometry/31795/hole02_220542.zip \
  --extract data/courseview/prodgeometry/31795/Hole02_220542_from_script \
  --json

node decode_courseview_geometry.js \
  --geometry-dir data/courseview/prodgeometry/31795/Hole02_220542_from_script

.venv/bin/python overlay_prodgeometry_on_raster.py \
  --mesh-json output/prodgeometry/gid31795_h02_meshes.json \
  --snapshot logs/probe_map_bodies/snapshot_400065_hole.json \
  --hole 2
```

Key outputs from the Black Knight B hole 2 validation:

- `output/prodgeometry/gid31795_h02_stats.json`
- `output/prodgeometry/gid31795_h02_meshes.json`
- `output/prodgeometry_overlay/gid31795_rasterh02_prodgeometry_h02_overlay.png`
- `output/prodgeometry_overlay/gid31795_rasterh02_prodgeometry_h02_diagnostics.json`

Mesh counts from this hole:

- `Fairway.drc`: 488 points / 664 faces
- `Green.drc`: 268 points / 364 faces
- `Bunker.drc`: 716 points / 951 faces
- `Lake.drc`: 5548 points / 10567 faces
- `Rough.drc`: 3391 points / 5435 faces
- `Teebox.drc`: 326 points / 400 faces

## Deep Mine Closure Ledger

Deep Mine is not complete while any row below lacks a terminal result. A
terminal result is either a reproducible semantic mapping, a reproducible proof
that the current Garmin clients do not consume the value as map content, or a
captured external dependency with a working acquisition recipe. An unexplained
`unknown`, a single-course visual guess, or a product-value deferral is not a
terminal result.

| Workstream | Remaining evidence required | Completion gate |
|---|---|---|
| Acquisition and updates | Catalogue, name/city, radius, release, `MEDIUM`, `MEDIUM_PLUS`, `INTERMEDIATE`, prodgeometry, raster and Green Contours request chains; version/check-for-update semantics | Every APK call path is bound to endpoint, identifiers, auth level, pagination, version and cache invalidation behavior |
| Lightweight `courseData` | Codes `3243`, `3244`, `18125`; `InfoMask`, flags and `GreenRadii` scale | Every field is preserved and either named from multi-course evidence or accompanied by a proven non-rendering/opaque classification |
| DSKIMG | Remaining FAT/GMP edge cases; TRE/RGN/LBL private types and labels; real corpus for non-default DEM shrink, non-zero encoding type and multiple levels | Every declared subfile and geometry type is decoded or conclusively classified; the default DEM codec already round-trips independent Garmin-compatible oracles and matches prodgeometry Y, while other variants require real samples or an explicit absence result |
| prodgeometry bundle | All mesh names, `hole.json`, Terrain, foliage, normals/UV/color attributes, coordinate frames and elevation | Corpus inventory has no unclassified asset; every consumed layer has cross-course semantics and every ignored layer has a recorded reason |
| Green Contours | Authenticated membership download request, response package, course/build/part binding and S70 rendering behavior | One positive and one negative course are captured and decoded end-to-end; availability flag alone is not accepted as payload evidence |
| Product package | Source precedence, lightweight-to-precise upgrade, offline cache, integrity/version binding and shared iOS/Watch/Web representation | A newly discovered uncached course opens from factual lightweight data, upgrades without changing round identity, survives offline restart and renders consistently on all three clients |

## Next Work

1. Freeze the reproduced FAT, default DEM codec/cross-check and `courseData`
   findings as a checkpoint; this is not a declaration that Deep Mine is complete.
2. Locate real non-default shrink/encoding/multi-level DEM samples through the
   existing acquisition corpus; do not invent support without a specimen.
3. Resolve the remaining `courseData` codes/flags and DSKIMG TRE/RGN/LBL types
   across the existing multi-region corpus, retaining raw values throughout.
4. Finish the prodgeometry asset/attribute inventory and remove every
   unclassified corpus entry with evidence rather than a filename guess.
5. Trace and capture the membership Green Contours path, including one positive
   and one negative course and its S70-visible result.
6. Productize the proven lightweight facts as a fast fallback and verify their
   in-place upgrade to precise geometry across backend, iOS, Watch and Web.

## Practical Conclusion For Now

IMG remains useful course-level context and a separate research source, but it
is not the best fine per-hole geometry and its ordinary DEM is not Green
Contours. The short-term reliable source for precise surfaces remains Garmin's
encrypted `prodgeometry`; anonymous `courseData` is now the cheap fallback for
route, scorecard, green outline and proven water/bunker near/far spans.

For Black Knight B hole 2, the `prodgeometry` zip decrypts into real assets:

- `hole.json`
- `foliage.json`
- `Terrain.webp`
- Draco meshes such as `Fairway.drc`, `Green.drc`, `Bunker.drc`, `Lake.drc`,
  `Rough.drc`, `Teebox.drc`, and `PlayableBounds.drc`

Those meshes decode cleanly and overlay onto Garmin's own 730x730 raster with a
shot-control fit under 0.6 px max residual. This strongly suggests the
production pipeline should use:

- `prodgeometry` for precise Garmin-authored fairway/green/bunker/water/rough
  meshes
- `courseData` for immediate low-bandwidth fallback facts and hazard spans
- IMG for coarse geospatial context, ordinary DEM and a separate reverse-
  engineering thread, not subscription contours
- raster segmentation only as a fallback or visual sanity check
