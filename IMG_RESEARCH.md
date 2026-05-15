# Garmin CourseView IMG Research

Last updated: 2026-05-15

## Goal

Understand Garmin CourseView IMG enough to extract reliable golf-course geometry
for the AI caddie: green, fairway, bunker, water, paths, tee/pin/markers, and
hole-level grouping.

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
- FAT entry contains one `.GMP` subfile.
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

[parse_courseview.py](/Users/jason/workspace/garmin/parse_courseview.py) currently decodes:

- Extended polygons
- Extended polylines
- Extended points

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

## Open Questions

1. Which private CourseView type codes correspond to fairway, green, bunker,
   water, rough/tree, path, and hole-level blobs?
2. Are the 730 rasters generated from a richer internal Garmin source that is
   not present in this small public CourseView IMG payload?
3. Can point records such as `0x013800` and `0x013801` be mapped to
   tees/pins/hole anchors
   across many courses?

## Next Work

1. Render IMG geometry by subdivision index and type, not just by hole image
   bbox, to identify which subdivisions are overview vs detail.
2. Decode LBL enough to resolve nonzero point labels, even if polygons and
   lines are unlabeled.
3. Build cross-course type statistics and shape descriptors:
   - count per type
   - mean vertex count
   - area distribution
   - centroid relation to shot tee/pin positions
4. Infer semantic roles from multi-course evidence, not one hole:
   - hole overview blobs
   - cart/path lines
   - tee/green anchor points
   - tiny markers
   - possible hazard/terrain surfaces

## Practical Conclusion For Now

IMG remains worth investigating. It likely contains course-level vector layers
and anchor metadata, but the short-term reliable source for fine per-hole
geometry is Garmin's encrypted `prodgeometry` CourseView payload.

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
- IMG for coarse geospatial context, anchors, and as a separate reverse-
  engineering thread
- raster segmentation only as a fallback or visual sanity check
