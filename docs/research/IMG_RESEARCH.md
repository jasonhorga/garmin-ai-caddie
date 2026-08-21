# Garmin CourseView IMG Research

Last updated: 2026-08-05

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
- all 26 tiles from the four cross-check payloads decode to their exact declared
  extrema, and every tile leaves only `0–7` padding bits;
- an anonymous 12-region sample added 48 courses and 96 live tiles. All 48
  strict inventories decode without an error or header-extrema mismatch. The
  sample manifest is `deepmine-output/dem-corpus-20260804/manifest.json`,
  SHA-256 `1b9473e4e4b6a5d5061f2ffbd5866ea877b13d67fd61e3b6ba6a746ef64f44de`.

Across the 52-course, 122-tile inspected set, every CourseView DEM has one
level, `shrinkValue=0` (`factor=1`) and `encodingType=0`. This is now the
product decision for the CourseView distribution we consume: decode that proven
variant and explicitly reject a future non-default descriptor behind the map
package version gate. Generic Garmin multi-level/shrunk DEM variants are not
guessed into this parser merely because they may exist in other Garmin products.

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
- line code `3243` and anchor code `18125` are the paired third Garmin hazard
  category, but the matched meshes do not support a stable water, bunker,
  beach, ocean, cliff, rough or cart-path label. They are terminally classified
  as opaque: preserve the raw code and never expose a guessed surface name;
- line code `3244` is not a cart path. Every observed row is a forward subspan
  of the code-`3240` route and adds no independent 2D surface.

A second read-only audit binds the complete captured fetch manifest to 114
`MEDIUM_PLUS` responses: 114 layouts, 1,701 holes and ten Garmin BuildIds. All
114 filename `layout + build` pairs match the response body, and every manifest
URL, byte count and hole count matches its file. Across that full corpus:

- every hole has exactly one code-`3240` route;
- `InfoMask == ((uint32(route.Flags) >> 28) & 0xF)` for `1,701/1,701`
  holes. It is a duplicate view of the route flags high nibble, not a separate
  map layer;
- the low 28 route flag bits equal the bitset of route points whose `Flag=1`
  for `1,701/1,701` holes, using bit `PointNumber - 1`;
- all 17,273 line points have `Closure=0`, and all point flags are either zero
  or one. This is an observed absence result; a future non-zero closure remains
  raw and must trigger a new format review rather than receiving a guessed
  meaning;
- the low two hazard flag bits have stable route-relative direction:
  `1=right`, `2=left`, `3=centre/crossing/mixed`. Of 4,649 single-side line and
  anchor records, 4,646 agree geometrically (`99.935%`). The three disagreeing
  Garmin rows are retained as raw exceptions. Higher flag bits are opaque
  subtype bits;
- all 105 code-`3244` lines across 61 courses have flags `3`, two points in
  Tee-to-green order, maximum route cross-track `0.123901 m` and maximum
  declared-length delta `0.984911 m`;
- code `3243` occurs 14 times across 3 courses and code `18125` 18 times across
  2 courses. Their structural pairing and side flags are reproducible, while a
  specific surface label is not.

The authority report is
`report/course-data-corpus-1701-audit.json` on the homeserver, SHA-256
`a519f9772cdd4dba2eebb72c5b128e18dd5856631d1ad44d3b67816438064372`.
`tools/courseview/audit_course_data_corpus.py` regenerates it and fails closed on
binding, field, type-code or geometric drift.

`GreenRadii` is now closed against 166 strictly authority-bound holes. The
binding chain is `courseData layout + BuildId → release layout + version +
CourseGenVersion → exact hole geometry URL stem + ZIP digest → extracted asset
directory → hole.json GlobalId + HoleNumber + internal version pair`; holes are
joined by `HoleNumber`, because Garmin's `Holes` array order is not stable. The 30 values are sampled
from north clockwise in 12° steps in an angular coordinate plane before the
longitude latitude correction. For sample angle `theta` and endpoint latitude
`lat`, the exact local display offset is:

A 2026-08-21 cold-install check against an anonymized, previously uncached
18-hole layout corrected one authority assumption in that chain. The external
ZIP stem is not universally the decimal concatenation of decoded
`CourseGenVersion` and `Version`: 3 holes in this layout matched that historical
formula, while 15 used a newer external namespace even though download,
decryption, Draco decode and every derivative succeeded. Current authority
therefore binds the exact release URL stem to the exact extracted directory and
real ZIP SHA-256, then independently requires `GlobalId + HoleNumber` and the
internal version pair to agree across mesh and hazard outputs. It never invents
an external asset version by concatenating the two internal fields.

```text
east  = rawRadius × sin(theta) × cos(lat)
north = rawRadius × cos(theta)
```

Across 4,980 outline samples, 2,690 fall directly inside the selected VFX mesh;
distance-to-mesh is P95 `0.355094 m`, P99 `0.432155 m`, maximum `1.443006 m`
and RMSE `0.155755 m`. These values are therefore decoded for the lightweight
display outline, but are still not used as front/middle/back distance or green
slope evidence; precise F/M/B and slope continue to come from the selected
`Green.drc` component.

Layout `38059` proved to be a real A/B dual-green course, not a version mismatch.
The selected VFX split is A for holes `1,2,3,4,6,10,13,15` and B for holes
`5,7,8,9,11,12,14,16,17,18`. The chosen VFX centre is at most `1.666442 m`
from the `courseData` route endpoint, while the alternate green is at least
`24.587815 m` away. Its `hole.json Doglegs` endpoint always remains on A, so the
release-bound `courseData` endpoint is the layout-selection authority whenever
the two differ by more than `10 m`. Production now applies that rule once for
the route, target distances, topo marker, F/M/B component and slope component;
old hazard exports are rebound read-only, while new exports are generated from
the selected endpoint. The 18-hole product audit preserved the observed
`hole.json=8 / courseData=10` split with maximum route/target residual
`0.020981 m` and maximum selected `Green.drc` centre residual `1.105364 m`.

The reproducible report is
`report/green-radii-vfx-166-audit.json` on the homeserver, SHA-256
`9f5524c80780d6d30357cdefc484a6a766294b18174a46d2178d93544b4675a8`.
`tools/courseview/audit_green_radii.py` regenerates both the 166-hole coordinate
proof and the real 18-hole production-consumer gate.

The production fetch path was also exercised directly against the anonymous
endpoint on 2026-08-04, rather than only through fixtures. Cypress Point build
`309`, layout `3881` returned 18 holes and 5 tees in both variants. `MEDIUM`
contained 18 route lines (`3240`); `MEDIUM_PLUS` contained 60 lines with raw
codes `3240`, `3242` and `3243`. Both responses passed request/response BuildId
and GlobalLayoutId authority binding.

### DSKIMG vector semantics closed against prodgeometry

The private TRE/RGN vector-type workstream is now closed. The final replay
uses 13 release-bound DSKIMG artifacts representing 11 unique embedded images,
14 bound `courseData` layouts and all 184 unique prodgeometry holes in the
current corpus. Of those holes, 166 bind to an available DSKIMG. The other 18
are exactly the nine holes of layout `31636` and nine holes of `31637`, whose
anonymous release requests are reproducible HTTP 404s; there are no extra or
stale exceptions. Every one of the 15 area, 3 line and 2 point types has a
terminal decision:

| Kind / type | Objects | Terminal semantic | Permitted product use |
|---|---:|---|---|
| area `0x010b01` | 10 | ocean context | coarse/offline display fallback only |
| area `0x010b08` | 169 | opaque mixed context area | preserve raw; do not consume |
| area `0x010d01` | 11 | course/complex boundary | structural framing only |
| area `0x011400` | 13 | opaque singleton context area | preserve raw; do not consume |
| area `0x011402` | 1,345 | tee area | coarse/offline display fallback only |
| area `0x011403` | 351 | fairway area | coarse/offline display fallback only |
| area `0x011404` | 324 | green area | coarse/offline display fallback only |
| area `0x011405` | 1,489 | bunker area | coarse/offline display fallback only |
| area `0x011406` | 38 | opaque coastal-terrain area | preserve raw; do not consume |
| area `0x011407` | 1,493 | tree area | coarse/offline display fallback only |
| area `0x011409` | 324 | inner hole corridor | structural clipping only |
| area `0x01140a` | 13 | stream/water area | coarse/offline display fallback only |
| area `0x01140b` | 825 | teebox surface | coarse/offline display fallback only |
| area `0x01140d` | 16 | opaque small context area | preserve raw; do not consume |
| area `0x01140e` | 324 | outer hole domain | structural clipping only |
| line `0x010a00` | 13 | stream/water edge | coarse/offline display fallback only |
| line `0x012e00` | 324 | hole route | fallback route only |
| line `0x012e05` | 261 | cart path | coarse/offline display fallback only |
| point `0x013800` | 5 | course/layout label anchor | metadata anchor only |
| point `0x013801` | 88 | tee/route-start anchor | fallback position anchor only |

The important corrections are cross-source, not visual guesses. Line
`0x012e05` overlaps decoded `Cartpath.drc` by `80.563920%` across seven
observed images, so it is the cart path; area `0x010b08` is mixed and remains
opaque. Line `0x010a00` overlaps `Lake.drc` by `99.056604%` and
`VfxStream.drc` by `85.849057%`. All 159 of its vertices bind to the boundary
of area `0x01140a`, with median residual `0 m`, P95 `0.645269 m` and `100%`
within 2 m. The two 324-object hole layers are nested rather than playable
surfaces: `95.944526%` of inner-`0x011409` vertices fall inside outer
`0x01140e`, while the reverse coverage is only `56.001678%`.

These mappings do not change source precedence. DSKIMG fairway, green, bunker,
water and tree geometry is deliberately coarse and may support lightweight or
offline display when prodgeometry has not arrived. Exact distance, lie,
obstacle and penalty decisions continue to use release-bound prodgeometry and
`courseData`. Opaque types remain losslessly available for a future format
version review but cannot enter current UI or scoring logic.

The frozen authority report is
`/home/jason/codex-runs/garmin-search-deepmine-20260804-root/deepmine-output/dskimg-vector-semantics-184-final.json`,
SHA-256 `ff271c6bddc67de3bebfdee7609e774ac7849527c1db489a9bb7c983c688e8a3`.
`tools/courseview/audit_dskimg_vector_semantics.py` regenerates the report and
fails closed on strict decode, source binding, hole accounting or an observed
type without a terminal classification.

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
- TRE subdivisions and declared extended area/line/point types
- extended polygons, polylines and points, including CourseView's distinct
  private subtype-bit-6 polygon (`02 02 LL ...`) and line (`41 LL ...`) trailers
- direct LBL offsets, text pools and declared CP1252/CP932/CP936 decoding
- DEM header, descriptors, default compressed samples, tile assembly and
  bilinear elevation sampling

For `31795.img`:

- polygons: 591
- polylines: 27
- points: 11

The old `26 / 9 / 11` result was a parser-abort fallback: an unconsumed private
trailer shifted the cursor and silently discarded the rest of each subdivision.
Strict mode now turns any such abort into a corpus error. The corrected
`31795.img` type histogram after TRE overview filtering is:

- polygon: `0x011407` x258, `0x011402` x103, `0x011405` x100,
  `0x011403` x30, `0x011404` x27, `0x011409` x27, `0x01140e` x27,
  `0x010b08` x17 and three singleton types
- line: `0x012e00` x27
- point: `0x013801` x8, `0x013800` x3

For `31795` the TRE extended type overview/table contains:

- line: `0x012e00`
- areas: `0x010b08`, `0x010d01`, `0x011400`, `0x011402`, `0x011403`, `0x011404`,
  `0x011405`, `0x011407`, `0x011409`, `0x01140e`
- points: `0x013800`, `0x013801`

Note: the 3-byte records in the TRE extended type table appear to be
`type, unknown/flags, subtype`, not `type, subtype, unknown`.

The strict 48-course inventory decodes 26,106 areas, 1,503 lines and 312
points; every one of the 15 area, 3 line and 2 point types declared by TRE has
at least one real object, with zero subdivision aborts. Its authority report is
`deepmine-output/courseview-corpus-48-inventory.json`, SHA-256
`36b729e160dd6b78782bb3903708b5c7c9e41d36a68ea5c579745a1dd9e1550e`.

The same corpus resolves 809 LBL strings: all 48 headers are length 681,
encoding type 9 and multiplier 1; code pages are CP1252 x46, CP936 x1 and
CP932 x1. Feature label references are sparse rather than a hidden surface
legend: 48 labeled `0x011407` areas say `Unknown Area Type`, while the 16
labeled `0x013800` points carry course/layout names. The remaining pool is Tee
names, addresses, phone numbers, designer/grass metadata and copyright text.

## Cross-Course Pattern

The type schema is stable across tested courses:

- Black Knight A/B/C (`31794`, `31795`, `31796`) produce the same bbox, counts,
  and type histogram, which implies Garmin stores the whole club/course complex
  rather than one 9-hole course per global ID.
- 北湖九号 (`41825`) and 龙泉谷 (`39315`) have the same dominant area types:
  `0x011407`, `0x011402`, `0x011405`, `0x011403`, `0x01140e`, `0x011409`,
  `0x011404`, `0x010b08`, plus a few course-specific types.

This strongly suggests CourseView uses a private but consistent golf schema.

Two geometries now have direct cross-source meaning. Line `0x012e00` is the
hole-centre route and tracks lightweight `3240` within roughly `0.3–0.9 m`.
Area `0x010d01` is the whole course/complex boundary; `0x011409` and
`0x01140e` form nested hole-domain/corridor layers. The remaining small vector
types still do not prove a replacement for exact prodgeometry hazard surfaces,
so production does not relabel them from visual resemblance alone.

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

### Prodgeometry bundle and Draco attributes are now corpus-classified

The earlier single-hole listing was not enough to close this workstream. A
read-only pass now covers 184 extracted holes from 15 unique course IDs, three
`CourseGenVersion` families (`22`, `28`, `29`), the `Grassland`, `Savanna` and
`Tropical` biomes, and 35 holes with ocean features. One sixteenth acquisition
directory (`31796`) contained only encrypted ZIPs and is not counted as a decoded
course. The authority report is
`deepmine-output/prodgeometry-corpus-184-inventory.json` on the homeserver,
SHA-256 `cdf931f4c77896ffb1b95d123aa265bfd67dced57fc173c24382f58f965c44cc`.

All 2,545 Draco meshes decode, and every attribute is a standard declared Draco
semantic rather than an unnamed/custom payload:

- 2,177 material or VFX meshes have `POSITION/FLOAT32x3`,
  `TEX_COORD/FLOAT32x2`, `NORMAL/FLOAT32x3` and normalized `COLOR/UINT8x3`;
- all 184 `PhysicsMesh.drc` files have position, UV and normal, but no vertex
  color;
- all 184 `PlayableBounds.drc` files have position only;
- there are no generic/unknown semantics, unknown data types, attribute metadata
  entries or mesh records missing an attribute schema.

This makes the product boundary explicit. Position is factual geometry. Its
`(-mesh_x, mesh_z)` plane is the `hole.json (X, Y)` east/north frame; mesh Y plus
`ElevationMinimum` is the absolute elevation already cross-checked against the
independent DSKIMG DEM. UV, vertex normal and vertex color are renderer inputs,
not extra hazards, scorecard facts or subscription contours, so the shared map
package does not promote them into domain fields.

The non-mesh assets are also terminally classified:

- `hole.json` is the authority for course/hole identity, WGS84 reference,
  relative elevation range, Tee locations and ordered dogleg/target lines. All
  184 carry the core fields; `DoglegOrder` and `HasTargets` occur on 148 and are
  therefore version-conditional rather than required package fields.
- `foliage.json` contains 157,478 foliage and 12,051 tree instances. Their
  `x/y/z`, quaternion, scale and model/variant IDs are decorative scene
  instances. The 2D renderer may consume category and position; model identity,
  rotation and scale do not become scoring or lie facts. No rocks were present
  in this corpus, so the raw category remains preserved without invented
  behavior.
- Every hole has a distinct `1024x1024` lossy `Terrain.webp`. It is not an
  aerial/color map: across all 184 images median RGB is approximately
  `(127.9, 127.7, 248.3)`, blue is dominant in `99.4%–100%` of sampled pixels,
  and RGB-to-normal decoding has median vector length `0.95`. It is a
  hole-specific tangent-space normal/bump texture used with the mesh UVs. It
  can support a future lit iPhone/Web 3D renderer, but adds no new 2D surface,
  hazard or Green Contours authority and is intentionally excluded from the
  Watch factual package.

All 24 observed mesh names now have a product disposition:

| Mesh group | Product disposition |
|---|---|
| `Fairway`, `Fringe`, `Green`, `Rough`, `Teebox`, `TreeArea`, `Bunker`, `Beach`, `Lake`, `LakeSide`, `Ocean`, `OceanSide` | Factual surface/edge geometry; consumed for the matching visual, lie or hazard role where the client needs it |
| `PhysicsMesh` | Continuous terrain, outline and relative elevation authority; consumed for clipping, hillshade and PlaysLike |
| `PlayableBounds` | Flat generous scene extent; fallback framing only, never a hazard or the visible hole outline |
| `Cartpath`, `Bridge` | Factual structural landmarks; optional map decoration, not scoring hazards |
| `Cliff`, `CliffUV2`, `IslandExt` | Terrain skirt/material support for the 3D scene; no independent scoring surface, excluded from canonical hazard facts |
| `VfxGreenA`, `VfxGreenB`, `VfxOcean`, `VfxStream` | Visual-effect duplicates around already authoritative green/water meshes; excluded from semantic geometry |

The corpus contains zero unclassified mesh names and zero unclassified non-mesh
assets. `decode_courseview_geometry.js` now records the attribute schema and
component ranges in its ordinary compact stats output, so a future Garmin
package that introduces a new channel becomes an explicit version-gate event
instead of being silently ignored.

### APK acquisition, update and cache authority ledger

The non-membership acquisition path is now closed against Garmin Golf Android
`1.29.6` (APK SHA-256
`261b6661760cdcd97310742bd01e2e6f155a2eb8ba87cd2796ae71393531bea7`).
The decisive decompiled call sites are `GolfCourseApiCaller`,
`GolfCourseMediumMapTypeUpdateCheckOperation`,
`GolfCourseIntermediateMapTypeUpdateCheckOperation`,
`FetchIntermediateMapTypeCourseImageTask`, `IntlGolfProtoRequestHandler` and
`OMTGolfAPIEndpoint`. The two Garmin version chains are deliberately kept
separate:

- course payloads: `BuildId + GlobalLayoutId + Version`;
- image payloads: `PartNumber + GlobalLayoutId + Version`.

They are not interchangeable aliases. `BuildId` selects `MEDIUM` /
`MEDIUM_PLUS`; `PartNumber` selects `INTERMEDIATE` DSKIMG and its unit-bound
unlock material.

| Product / purpose | Request and pagination | Access and response binding | Update decision in Garmin | This product's cache rule |
|---|---|---|---|---|
| Name search | `GET /CourseViewData/Courses?courseName=...&bits=23&pageSize=50&page=N&languageCode=...` | Anonymous protobuf catalogue; each row carries `BuildId`, `GlobalLayoutId`, location, hole count and Green Contour availability | Search is live catalogue metadata, not an installed map | Fetch every page, dedupe by `GlobalLayoutId`, stop on a short or repeated page; never require downloading every course |
| Location + name | `GET /CourseViewData/Boundaries/{lonSC},{latSC},32/Courses?courseName=...&pageSize=50&page=N...` | Anonymous; path coordinates and returned coordinates use 32-bit semicircles | Same catalogue authority | Same complete pagination and dedupe; rank the complete result by true distance then name similarity |
| Nearby radius | `GET /CourseViewData/Boundaries/{lonSC},{latSC},{radiusMetres},32/Courses?pageSize=50&page=N...` | Anonymous provider-wide catalogue | Same catalogue authority | All pages through the bounded 100-page safety gate; a provider error is not disguised as an empty nearby list |
| Same club / loop assembly | `GET /CourseViewData/getCoursesInSameClub/{buildId},{globalLayoutId}` with optional semicircle location and `numberOfHoles` | Anonymous catalogue relation in the APK | Relation is tied to the requested build and layout | Preserve distinct loop `GlobalLayoutId`s; never collapse A/B or front/back layouts merely because the venue name matches |
| Latest / explicit release | `GET /CourseViewData/course-layouts/{globalLayoutId}/releases` or `/releases/{buildId}` | Anonymous protobuf; binds release `BuildId`, release/part id, `CourseGenVersion`, per-hole raster URL and prodgeometry URL | A newer course `BuildId` or `Version` is an update | Refresh latest metadata at most hourly, validate before atomic replacement, fall back to the last complete release offline; `courseData` then selects a cache file containing the exact new BuildId |
| Historical round layout | `GET /CourseViewData/course-layouts/{globalLayoutId}/date/{epochMs}` | Anonymous historical layout; used only when latest is withdrawn/404 and a stored round supplies its play time | It is an as-of authority, not evidence that the withdrawn layout became current again | Bind the canonical per-hole asset path/version returned by that dated response; do not overwrite a valid current release record with the differently-shaped date payload |
| `MEDIUM` | `GET /CourseViewData/courseData/{buildId},{globalLayoutId},32` | APK may add `Garmin-UnitId`; endpoint is also proven anonymously. Response body must repeat request `BuildId + GlobalLayoutId` | Installed COMPLETE record wins when its DB BuildId or Version is newer than the device; otherwise `POST /CourseViewData/checkForCourseUpdates` receives `[{BuildId,GlobalLayoutId,Version}]` | Normalized cache filename is `{layout}_course_data_{build}_medium.json`; a mismatched body is rejected, so a new release cannot be installed under an old identity |
| `MEDIUM_PLUS` | Same request plus `/Hazards` | Same binding; map type is DB value `1` rather than `0` | Same course update chain | Separate `medium-plus` cache identity; never infer that a cached MEDIUM body includes hazard spans |
| `INTERMEDIATE` DSKIMG | `GET /CourseViewData/coursedata/images/{partNumber}/courses/{globalLayoutId}?unitId={unitId}&version={version}` | Caller adds no bearer token, but request and response are device-bound. Response is accepted only with matching `UnitId`, `CourseIdentifier.{GlobalLayoutId,PartNumber,Version}`, `Image`, `UnlockGma.Gma` and `UnlockGma.Unlock` | DB PartNumber numeric suffix or Version newer than the device means update; absent DB record calls `POST /CourseViewData/checkForImageUpdates` with `[{PartNumber,GlobalLayoutId,Version}]` | Preserve Image/GMA/UNL together under the complete device + layout + part + version identity. The current app uses decoded DSKIMG only as coarse/offline fallback, never as precise scoring authority |
| Garmin raster | Signed `raster3d/.../gid..._hole..._{assetVersion}.jpg?garmindlm=...` URL from the release | URL is anonymously supplied; query is an expiring delivery signature | A changed canonical asset path/version is new content; a changed signature alone is not | There is no production raster cache today. Any future cache must key the canonical path/version and must not use the signed query as content identity |
| Precise `prodgeometry` | Signed per-hole ZIP URL from the release, then authenticated `GET /CourseViewData/image-key/v2?imageUrl={canonicalPath}` | ZIP delivery signature is not identity. `image-key/v2` uses Connect DI → Golf DI → Golf IT, bearer IT and `3D-Account-Id`; the returned key must decrypt the exact ZIP | Current release's canonical geometry path/version is the content authority | Sidecar `garmin-prodgeometry-authority-v1` binds release, `CourseGenVersion`, canonical geometry/raster paths, embedded asset version and ZIP SHA-256. Decode/export occurs in staging; canonical outputs are replaced only after all essential steps pass. Pre-sidecar files are reused only when both mesh and hazard metadata prove the same embedded version |
| Derived topo shared by Web / iPhone / Watch | `GET /api/v2/courses/{gid}/holes/{hole}/topo.png?v=topo-v8` | Public derivative of the bound prodgeometry, with no player data | Geometry content token or renderer style change invalidates it | Disk key and HTTP ETag contain `style + geometry authority token`; `Cache-Control: public, no-cache` allows storage but forces revalidation. Web/iPhone/Watch use the same style URL. iPhone caches below `course_topo/topo-v8/`, Watch below `hole-images/topo-v8/`, and phone→Watch file metadata carries the same style; a queued old-style transfer is rejected instead of repopulating the current cache |
| Green Contours | Membership course-download path, still awaiting the user's positive/negative capture | Must prove membership state, course/build/part binding and actual contour payload | Cannot be inferred from `HasGreenContour`, ordinary DEM or DSKIMG type correlation | External capture dependency remains isolated in the Green Contours row below; it does not weaken or block the now-closed ordinary map acquisition/cache chain |

The corresponding product correction is intentionally small. Release bytes are
validated before an atomic refresh; stale bytes remain usable offline. Existing
precise geometry no longer returns merely because `gid + hole` files exist: it
must bind to the current canonical Garmin asset, while a release metadata change
that points to the identical asset reuses the decoded content. The topo cache no
longer asserts that a `gid + hole` can never change, including on already-installed
iPhone and Watch clients. Signed `garmindlm` values,
OAuth material, image keys and ZIP passwords are never written into the
authority sidecar or client package.

## Deep Mine Closure Ledger

Deep Mine is not complete while any row below lacks a terminal result. A
terminal result is either a reproducible semantic mapping, a reproducible proof
that the current Garmin clients do not consume the value as map content, or a
captured external dependency with a working acquisition recipe. An unexplained
`unknown`, a single-course visual guess, or a product-value deferral is not a
terminal result.

| Workstream | Remaining evidence required | Completion gate |
|---|---|---|
| Acquisition and updates | **CLOSED for ordinary maps:** catalogue/name/radius/same-club, release/date, `MEDIUM`, `MEDIUM_PLUS`, `INTERMEDIATE`, raster, prodgeometry and both update-check chains are bound to endpoint, identifiers, access level, pagination and cache invalidation. Membership Green Contours is tracked separately below | Every non-membership APK call path has a terminal acquisition and cache decision; name and location search now consume all provider pages, and release/geometry/topo cannot silently mix versions |
| Lightweight `courseData` | **CLOSED:** manifest-bound 114-course / 1,701-hole field/code audit plus 166-hole GreenRadii authority and A/B-selection audit; `InfoMask`, route bitset, Closure absence, hazard sides, `3244`, opaque `3243/18125` and the latitude-corrected 30-vector outline all have terminal decisions | Every field is preserved and either named from multi-course evidence or accompanied by a proven non-rendering/opaque classification |
| DSKIMG | **CLOSED:** FAT/GMP/TRE/RGN/LBL/default DEM plus all 15 area, 3 line and 2 point types have terminal decisions; the final vector audit accounts for 184/184 prodgeometry holes, with 166 source-bound and exactly 18 release-unavailable holes on layouts `31636/31637` | Strict 48-package structure and 52-course DEM results remain green; the 184-hole cross-source audit has zero unclassified types, zero unexpected unavailable layouts and explicit consume/fallback/preserve-raw decisions |
| prodgeometry bundle | **CLOSED:** 184 holes / 2,545 meshes across 15 courses; all mesh/static assets, JSON fields and Draco attributes classified; coordinate/elevation frame independently cross-checked | Zero unclassified mesh, static asset, attribute semantic or data type; every consumed and ignored layer has a recorded product reason, with future unknown channels rejected by the package version gate |
| Green Contours | Authenticated membership download request, response package, course/build/part binding and S70 rendering behavior | One positive and one negative course are captured and decoded end-to-end; availability flag alone is not accepted as payload evidence |
| Product package | **CLOSED for current sources:** source precedence, lightweight-to-precise upgrade, offline cache and shared iOS/Watch/Web representation are integrated; dual-green route/component authority is included | A newly discovered uncached course opens from factual lightweight data, upgrades without changing round identity, survives offline restart and renders consistently on all three clients |

## Next Work

1. Trace and capture the membership Green Contours path, including one positive
   and one negative course and its S70-visible result.

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
