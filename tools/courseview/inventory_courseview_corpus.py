#!/usr/bin/env python3
"""Inventory the CourseView bytes we already own before inventing another decoder.

This is deliberately a small, read-only DeepMine pass. It scans release protobufs,
DSKIMG wrappers and extracted prodgeometry directories; inventories DEM variants and
every observed mesh/JSON/protobuf field; and separates product-consumed, known
structural, and genuinely unclassified mesh names. It never downloads, decrypts,
rewrites, or publishes course data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ai_caddie.geometry.export_prodgeometry_hazards import FEATURES, KNOWN_NON_HAZARD
from ai_caddie.geometry.inspect_courseview_release import parse_fields
from tools.courseview.parse_courseview import (
    _unwrap_pb_img,
    decode_dem_level,
    extract_gmp,
    parse_dem_header,
    parse_gmp_header,
    parse_lbl_header,
    parse_points,
    parse_polygons,
    parse_polylines,
    parse_rgn_header,
    parse_tre,
)


SCHEMA = "ai-caddie-courseview-corpus-inventory-v1"

KNOWN_STATIC_ASSETS = {"hole.json", "foliage.json", "Terrain.webp"}

# topo-v6's factual drawing inputs. Other decoded meshes may still feed semantic export.
TOPO_MESHES = {
    "PhysicsMesh.drc",
    "Rough.drc",
    "TreeArea.drc",
    "Fairway.drc",
    "Fringe.drc",
    "Bunker.drc",
    "Lake.drc",
    "Teebox.drc",
    "Green.drc",
}

KNOWN_RELEASE_TOP = {
    "1:0", "2:0", "3:2", "4:2", "5:2", "6:2", "7:2", "8:0", "9:0", "10:0", "12:0",
}
KNOWN_RELEASE_TEE = {"1:2", "2:0", "3:5", "4:2", "5:0"}
KNOWN_RELEASE_HOLE = {"1:0", "2:2", "3:2", "4:0", "5:0", "6:0", "7:2", "8:2"}


def _counter(counter: Counter[Any]) -> dict[str, int]:
    return {str(key): counter[key] for key in sorted(counter, key=lambda value: str(value))}


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def _webp_info(path: Path) -> tuple[int, int, str]:
    data = path.read_bytes()
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("invalid WebP RIFF header")
    chunk = data[12:16]
    payload = 20
    if chunk == b"VP8X":
        width = int.from_bytes(data[payload + 4:payload + 7], "little") + 1
        height = int.from_bytes(data[payload + 7:payload + 10], "little") + 1
    elif chunk == b"VP8 ":
        if data[payload + 3:payload + 6] != b"\x9d\x01\x2a":
            raise ValueError("invalid VP8 frame header")
        width = int.from_bytes(data[payload + 6:payload + 8], "little") & 0x3FFF
        height = int.from_bytes(data[payload + 8:payload + 10], "little") & 0x3FFF
    elif chunk == b"VP8L":
        if data[payload] != 0x2F:
            raise ValueError("invalid VP8L frame header")
        packed = int.from_bytes(data[payload + 1:payload + 5], "little")
        width = (packed & 0x3FFF) + 1
        height = ((packed >> 14) & 0x3FFF) + 1
    else:
        raise ValueError(f"unsupported WebP chunk {chunk!r}")
    if width <= 0 or height <= 0:
        raise ValueError("invalid WebP dimensions")
    return width, height, chunk.decode("ascii").strip()


def _attribute_signature(attributes: list[dict[str, Any]]) -> str:
    return " | ".join(
        ":".join(
            (
                str(row.get("semantic", "missing")),
                str(row.get("dataType", "missing")),
                str(row.get("components", "missing")),
                "normalized" if row.get("normalized") else "raw",
            )
        )
        for row in attributes
    )


def _merge_bounds(
    target: dict[str, list[float | None]],
    minimum: Any,
    maximum: Any,
) -> None:
    if not isinstance(minimum, list) or not isinstance(maximum, list):
        return
    if len(minimum) != len(maximum):
        return
    if not target:
        target["minimum"] = [None for _ in minimum]
        target["maximum"] = [None for _ in maximum]
    if len(target["minimum"]) != len(minimum):
        return
    for index, value in enumerate(minimum):
        if not isinstance(value, (int, float)):
            continue
        current = target["minimum"][index]
        target["minimum"][index] = value if current is None else min(current, value)
    for index, value in enumerate(maximum):
        if not isinstance(value, (int, float)):
            continue
        current = target["maximum"][index]
        target["maximum"][index] = value if current is None else max(current, value)


def _draco_stats_inventory(
    stats_root: Path | None,
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    paths = sorted(stats_root.glob("**/*_stats.json")) if stats_root else []
    mesh_records = 0
    missing_schema = 0
    schema_by_mesh: dict[str, Counter[str]] = {}
    bounds_by_mesh: dict[str, dict[str, dict[str, list[float | None]]]] = {}
    semantic_counts: Counter[str] = Counter()
    data_type_counts: Counter[str] = Counter()
    metadata_entries: Counter[str] = Counter()
    unique_ids: dict[str, Counter[str]] = {}
    unknown_semantics: Counter[str] = Counter()
    unknown_data_types: Counter[str] = Counter()

    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for mesh in payload.get("meshes") or []:
                if not isinstance(mesh, dict):
                    continue
                mesh_records += 1
                mesh_name = str(mesh.get("file") or "missing")
                attributes = mesh.get("attributeSchema")
                if not isinstance(attributes, list):
                    missing_schema += 1
                    continue
                schema_by_mesh.setdefault(mesh_name, Counter())[_attribute_signature(attributes)] += 1
                mesh_bounds = bounds_by_mesh.setdefault(mesh_name, {})
                for row in attributes:
                    if not isinstance(row, dict):
                        continue
                    semantic = str(row.get("semantic") or "missing")
                    data_type = str(row.get("dataType") or "missing")
                    semantic_counts[semantic] += 1
                    data_type_counts[data_type] += 1
                    if semantic.startswith("UNKNOWN_") or semantic in {"GENERIC", "missing"}:
                        unknown_semantics[semantic] += 1
                    if data_type.startswith("UNKNOWN_") or data_type in {"INVALID", "missing"}:
                        unknown_data_types[data_type] += 1
                    unique_ids.setdefault(semantic, Counter())[str(row.get("uniqueId"))] += 1
                    for entry in row.get("metadataEntries") or []:
                        metadata_entries[str(entry)] += 1
                    key = f"{row.get('index')}:{semantic}"
                    _merge_bounds(
                        mesh_bounds.setdefault(key, {}),
                        row.get("minimum"),
                        row.get("maximum"),
                    )
        except Exception as exc:
            errors.append(
                {
                    "artifact": str(path),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    return {
        "artifactCount": len(paths),
        "meshRecordCount": mesh_records,
        "meshRecordsWithoutAttributeSchema": missing_schema,
        "attributeSchemaCountsByMesh": {
            key: _counter(value) for key, value in sorted(schema_by_mesh.items())
        },
        "attributeBoundsByMesh": bounds_by_mesh,
        "semanticCounts": _counter(semantic_counts),
        "dataTypeCounts": _counter(data_type_counts),
        "uniqueIdCountsBySemantic": {
            key: _counter(value) for key, value in sorted(unique_ids.items())
        },
        "metadataEntryCounts": _counter(metadata_entries),
        "unclassifiedSemanticCounts": _counter(unknown_semantics),
        "unclassifiedDataTypeCounts": _counter(unknown_data_types),
    }


def _wire_inventory(path: Path) -> tuple[Counter[str], Counter[str], Counter[str]]:
    top: Counter[str] = Counter()
    tees: Counter[str] = Counter()
    holes: Counter[str] = Counter()
    for field_no, wire_type, _value, raw in parse_fields(path.read_bytes()):
        top[f"{field_no}:{wire_type}"] += 1
        target = tees if field_no == 6 else holes if field_no == 7 else None
        if target is not None and wire_type == 2 and raw is not None:
            for sub_no, sub_wire, _sub_value, _sub_raw in parse_fields(raw):
                target[f"{sub_no}:{sub_wire}"] += 1
    return top, tees, holes


def _dem_encoding_types(gmp: bytes, level: Any) -> list[int]:
    offset_size = (level.record_descriptor & 0x03) + 1
    base_size = ((level.record_descriptor & 0x04) >> 2) + 1
    delta_size = ((level.record_descriptor & 0x08) >> 3) + 1
    has_encoding_type = bool(level.record_descriptor & 0x10)
    cursor_offset = offset_size + base_size + delta_size
    values: set[int] = set()
    for index in range(level.tiles_lon * level.tiles_lat):
        start = level.tile_descriptor_offset + index * level.tile_descriptor_size
        values.add(gmp[start + cursor_offset] if has_encoding_type else 0)
    return sorted(values)


def _lbl_texts(gmp: bytes, lbl: Any) -> list[str]:
    texts: list[str] = []
    cursor = lbl.label_start + lbl.offset_multiplier
    end = lbl.label_start + lbl.label_size + 1
    while cursor < end:
        terminator = gmp.find(b"\0", cursor, end)
        if terminator < 0:
            raise ValueError("Garmin LBL pool has unterminated text")
        if terminator > cursor:
            offset = (cursor - lbl.label_start) // lbl.offset_multiplier
            texts.append(lbl.text_at(gmp, offset))
        cursor = terminator + 1
        relative = cursor - lbl.label_start
        remainder = relative % lbl.offset_multiplier
        if remainder:
            cursor += lbl.offset_multiplier - remainder
    return texts


def _vector_kind(
    objects: list[Any],
    declared_types: set[int],
    *,
    gmp: bytes,
    lbl: Any,
) -> dict[str, Any]:
    observed = Counter(f"0x{item.ext_type:06x}" for item in objects)
    referenced = Counter(
        (
            f"0x{item.ext_type:06x}",
            item.label_off,
            lbl.text_at(gmp, item.label_off),
        )
        for item in objects
        if item.has_label
    )
    declared = sorted(f"0x{value:06x}" for value in declared_types)
    return {
        "objectCount": len(objects),
        "declaredTypes": declared,
        "observedTypeCounts": _counter(observed),
        "declaredWithoutDecodedObject": sorted(set(declared) - set(observed)),
        "labeledObjectCount": sum(referenced.values()),
        "referencedLabels": [
            {"type": kind, "offset": offset, "text": text, "count": count}
            for (kind, offset, text), count in sorted(referenced.items())
        ],
    }


def _dskimg_inventory(path: Path) -> dict[str, Any]:
    source = path.read_bytes()
    image = source if source[0x10:0x16] == b"DSKIMG" else _unwrap_pb_img(source)
    gmp = extract_gmp(image)
    offsets = parse_gmp_header(gmp)
    dem = parse_dem_header(gmp, offsets.dem)
    levels: list[dict[str, Any]] = []
    for level_index, level in enumerate(dem.levels):
        item: dict[str, Any] = {
            "levelIndex": level_index,
            "zoomLevel": level.zoom_level,
            "columns": level.columns,
            "rows": level.rows,
            "tileCount": level.tiles_lon * level.tiles_lat,
            "shrinkValue": level.shrink_value,
            "shrinkFactor": level.shrink_factor,
            "recordDescriptor": level.record_descriptor,
            "encodingTypes": _dem_encoding_types(gmp, level),
            "headerMinimum": level.min_elevation,
            "headerMaximum": level.max_elevation,
        }
        try:
            decoded = decode_dem_level(gmp, dem, level_index)
            elevations = [
                value
                for row in decoded.elevations
                for value in row
                if value is not None
            ]
            item["decode"] = {
                "status": "ok",
                "minimum": min(elevations) if elevations else None,
                "maximum": max(elevations) if elevations else None,
                "minimumPaddingBits": min(tile.padding_bits for tile in decoded.tiles),
                "maximumPaddingBits": max(tile.padding_bits for tile in decoded.tiles),
            }
        except Exception as exc:
            item["decode"] = {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
        levels.append(item)
    lbl = parse_lbl_header(gmp, offsets.lbl)
    lbl_texts = _lbl_texts(gmp, lbl)
    tre = parse_tre(gmp, offsets.tre)
    rgn = parse_rgn_header(gmp, offsets.rgn)
    vectors = {
        "area": _vector_kind(
            parse_polygons(gmp, rgn, tre, strict=True),
            tre.ext_area_types,
            gmp=gmp,
            lbl=lbl,
        ),
        "line": _vector_kind(
            parse_polylines(gmp, rgn, tre, strict=True),
            tre.ext_line_types,
            gmp=gmp,
            lbl=lbl,
        ),
        "point": _vector_kind(
            parse_points(gmp, rgn, tre, strict=True),
            tre.ext_point_types,
            gmp=gmp,
            lbl=lbl,
        ),
    }
    return {
        "artifact": path.name,
        "sourceSha256": hashlib.sha256(source).hexdigest(),
        "embeddedImageSha256": hashlib.sha256(image).hexdigest(),
        "sourceBytes": len(source),
        "elevationUnit": dem.elevation_unit,
        "levelCount": len(levels),
        "levels": levels,
        "lbl": {
            "headerLength": lbl.header_length,
            "labelSize": lbl.label_size,
            "offsetMultiplier": lbl.offset_multiplier,
            "encodingType": lbl.encoding_type,
            "codePage": lbl.code_page,
            "textCount": len(lbl_texts),
            "texts": lbl_texts,
        },
        "vector": vectors,
    }


def inventory_courseview(root: Path, *, mesh_stats_root: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    release_top: Counter[str] = Counter()
    release_tees: Counter[str] = Counter()
    release_holes: Counter[str] = Counter()
    errors: list[dict[str, str]] = []

    release_paths = sorted(root.glob("*_releases.pb"))
    for path in release_paths:
        try:
            top, tees, holes = _wire_inventory(path)
            release_top.update(top)
            release_tees.update(tees)
            release_holes.update(holes)
        except Exception as exc:  # keep the rest of the corpus inspectable
            errors.append(
                {
                    "artifact": path.name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    dem_artifacts: list[dict[str, Any]] = []
    dem_paths = sorted(set(root.glob("*coursedata.pb")) | set(root.glob("*.img")))
    for path in dem_paths:
        try:
            dem_artifacts.append(_dskimg_inventory(path))
        except Exception as exc:
            errors.append(
                {
                    "artifact": path.name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    dem_levels = [
        level
        for artifact in dem_artifacts
        for level in artifact["levels"]
    ]
    vector_kinds = ("area", "line", "point")
    declared_vector_types = {
        kind: Counter(
            declared
            for artifact in dem_artifacts
            for declared in artifact["vector"][kind]["declaredTypes"]
        )
        for kind in vector_kinds
    }
    observed_vector_types = {
        kind: Counter(
            {
                observed: sum(
                    artifact["vector"][kind]["observedTypeCounts"].get(observed, 0)
                    for artifact in dem_artifacts
                )
                for observed in {
                    value
                    for artifact in dem_artifacts
                    for value in artifact["vector"][kind]["observedTypeCounts"]
                }
            }
        )
        for kind in vector_kinds
    }

    mesh_files: Counter[str] = Counter()
    asset_files: Counter[str] = Counter()
    hole_fields: Counter[str] = Counter()
    tee_fields: Counter[str] = Counter()
    dogleg_fields: Counter[str] = Counter()
    dogleg_line_fields: Counter[str] = Counter()
    hole_values: dict[str, Counter[str]] = {
        key: Counter()
        for key in ("Biome", "CourseGenVersion", "DEMProviderId", "HasOceanFeatures", "DrivingRange")
    }
    foliage_categories: Counter[str] = Counter()
    foliage_item_fields: dict[str, Counter[str]] = {}
    foliage_ids: dict[str, Counter[str]] = {}
    course_ids: set[int] = set()
    terrain_dimensions: Counter[str] = Counter()
    terrain_chunks: Counter[str] = Counter()
    terrain_bytes: list[int] = []
    terrain_content_hashes: set[str] = set()

    hole_json_paths = sorted((root / "prodgeometry").glob("*/*/hole.json"))
    for hole_path in hole_json_paths:
        directory = hole_path.parent
        for asset in directory.iterdir():
            if not asset.is_file():
                continue
            asset_files[asset.name] += 1
            if asset.suffix.lower() == ".drc":
                mesh_files[asset.name] += 1
            elif asset.name == "Terrain.webp":
                try:
                    width, height, chunk = _webp_info(asset)
                    terrain_dimensions[f"{width}x{height}"] += 1
                    terrain_chunks[chunk] += 1
                    terrain_bytes.append(asset.stat().st_size)
                    terrain_content_hashes.add(hashlib.sha256(asset.read_bytes()).hexdigest())
                except Exception as exc:
                    errors.append(
                        {
                            "artifact": str(asset.relative_to(root)),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

        try:
            hole = json.loads(hole_path.read_text(encoding="utf-8"))
            if isinstance(hole.get("GlobalId"), int):
                course_ids.add(hole["GlobalId"])
            for key, value in hole.items():
                hole_fields[f"{key}:{_type_name(value)}"] += 1
            for key, values in hole_values.items():
                values[json.dumps(hole.get(key), ensure_ascii=False, sort_keys=True)] += 1
            for tee in hole.get("TeeLocations") or []:
                if isinstance(tee, dict):
                    for key, value in tee.items():
                        tee_fields[f"{key}:{_type_name(value)}"] += 1
            for dogleg in hole.get("Doglegs") or []:
                if not isinstance(dogleg, dict):
                    continue
                for key, value in dogleg.items():
                    dogleg_fields[f"{key}:{_type_name(value)}"] += 1
                for point in dogleg.get("Line") or []:
                    if isinstance(point, dict):
                        for key, value in point.items():
                            dogleg_line_fields[f"{key}:{_type_name(value)}"] += 1
        except Exception as exc:
            errors.append(
                {
                    "artifact": str(hole_path.relative_to(root)),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

        foliage_path = directory / "foliage.json"
        if not foliage_path.exists():
            continue
        try:
            foliage = json.loads(foliage_path.read_text(encoding="utf-8"))
            for category, rows in foliage.items():
                foliage_categories[category] += len(rows) if isinstance(rows, list) else 0
                field_counter = foliage_item_fields.setdefault(category, Counter())
                id_counter = foliage_ids.setdefault(category, Counter())
                for row in rows if isinstance(rows, list) else []:
                    if not isinstance(row, dict):
                        continue
                    for key, value in row.items():
                        field_counter[f"{key}:{_type_name(value)}"] += 1
                    if "id" in row:
                        id_counter[str(row["id"])] += 1
        except Exception as exc:
            errors.append(
                {
                    "artifact": str(foliage_path.relative_to(root)),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    observed_meshes = set(mesh_files)
    observed_assets = set(asset_files)
    semantic_meshes = set(FEATURES)
    structural_meshes = set(KNOWN_NON_HAZARD)
    draco_stats = _draco_stats_inventory(mesh_stats_root, errors)
    return {
        "schema": SCHEMA,
        "rootLabel": root.name,
        "releaseProtobuf": {
            "artifactCount": len(release_paths),
            "topLevelWireFields": _counter(release_top),
            "teeWireFields": _counter(release_tees),
            "holeWireFields": _counter(release_holes),
            "uninterpretedTopLevelWireFields": sorted(set(release_top) - KNOWN_RELEASE_TOP),
            "uninterpretedTeeWireFields": sorted(set(release_tees) - KNOWN_RELEASE_TEE),
            "uninterpretedHoleWireFields": sorted(set(release_holes) - KNOWN_RELEASE_HOLE),
        },
        "dskimgDem": {
            "artifactCount": len(dem_artifacts),
            "levelCountHistogram": _counter(
                Counter(artifact["levelCount"] for artifact in dem_artifacts)
            ),
            "shrinkValueHistogram": _counter(
                Counter(level["shrinkValue"] for level in dem_levels)
            ),
            "encodingTypeHistogram": _counter(
                Counter(
                    encoding
                    for level in dem_levels
                    for encoding in level["encodingTypes"]
                )
            ),
            "recordDescriptorHistogram": _counter(
                Counter(level["recordDescriptor"] for level in dem_levels)
            ),
            "tileCount": sum(level["tileCount"] for level in dem_levels),
            "decodeStatusHistogram": _counter(
                Counter(level["decode"]["status"] for level in dem_levels)
            ),
            "decodedExtremaMismatchCount": sum(
                level["decode"].get("minimum") != level["headerMinimum"]
                or level["decode"].get("maximum") != level["headerMaximum"]
                for level in dem_levels
                if level["decode"]["status"] == "ok"
            ),
            "artifacts": dem_artifacts,
        },
        "dskimgVector": {
            "objectCountByKind": {
                kind: sum(
                    artifact["vector"][kind]["objectCount"]
                    for artifact in dem_artifacts
                )
                for kind in vector_kinds
            },
            "declaredTypeArtifactCounts": {
                kind: _counter(declared_vector_types[kind])
                for kind in vector_kinds
            },
            "observedTypeObjectCounts": {
                kind: _counter(observed_vector_types[kind])
                for kind in vector_kinds
            },
            "declaredNeverObserved": {
                kind: sorted(
                    set(declared_vector_types[kind]) - set(observed_vector_types[kind])
                )
                for kind in vector_kinds
            },
            "labeledObjectCountByKind": {
                kind: sum(
                    artifact["vector"][kind]["labeledObjectCount"]
                    for artifact in dem_artifacts
                )
                for kind in vector_kinds
            },
        },
        "dskimgLbl": {
            "headerLengthHistogram": _counter(
                Counter(artifact["lbl"]["headerLength"] for artifact in dem_artifacts)
            ),
            "offsetMultiplierHistogram": _counter(
                Counter(
                    artifact["lbl"]["offsetMultiplier"] for artifact in dem_artifacts
                )
            ),
            "encodingTypeHistogram": _counter(
                Counter(artifact["lbl"]["encodingType"] for artifact in dem_artifacts)
            ),
            "codePageHistogram": _counter(
                Counter(artifact["lbl"]["codePage"] for artifact in dem_artifacts)
            ),
            "textCount": sum(artifact["lbl"]["textCount"] for artifact in dem_artifacts),
        },
        "prodgeometry": {
            "courseCount": len(course_ids),
            "holeCount": len(hole_json_paths),
            "assetNames": _counter(asset_files),
            "meshNames": _counter(mesh_files),
            "knownStaticAssetNames": sorted(observed_assets & KNOWN_STATIC_ASSETS),
            "unclassifiedNonMeshAssetNames": sorted(
                name
                for name in observed_assets - KNOWN_STATIC_ASSETS
                if not name.lower().endswith(".drc")
            ),
            "topoConsumedMeshNames": sorted(observed_meshes & TOPO_MESHES),
            "semanticConsumedMeshNames": sorted(observed_meshes & semantic_meshes),
            "knownStructuralOrCosmeticMeshNames": sorted(observed_meshes & structural_meshes),
            "presentButNotTopoMeshNames": sorted(observed_meshes - TOPO_MESHES),
            "unclassifiedMeshNames": sorted(observed_meshes - semantic_meshes - structural_meshes),
            "holeFields": _counter(hole_fields),
            "teeLocationFields": _counter(tee_fields),
            "doglegFields": _counter(dogleg_fields),
            "doglegLineFields": _counter(dogleg_line_fields),
            "metadataValues": {key: _counter(values) for key, values in hole_values.items()},
            "foliageItemCounts": _counter(foliage_categories),
            "foliageItemFields": {key: _counter(value) for key, value in sorted(foliage_item_fields.items())},
            "foliageAssetIds": {key: _counter(value) for key, value in sorted(foliage_ids.items())},
            "terrain": {
                "artifactCount": len(terrain_bytes),
                "dimensionCounts": _counter(terrain_dimensions),
                "encodingChunkCounts": _counter(terrain_chunks),
                "minimumBytes": min(terrain_bytes) if terrain_bytes else None,
                "maximumBytes": max(terrain_bytes) if terrain_bytes else None,
                "uniqueContentCount": len(terrain_content_hashes),
            },
            "dracoStats": draco_stats,
        },
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="directory containing *_releases.pb and prodgeometry/")
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--mesh-stats-root",
        type=Path,
        help="optional directory containing decoder *_stats.json files with Draco attribute schemas",
    )
    args = parser.parse_args()
    result = inventory_courseview(args.root, mesh_stats_root=args.mesh_stats_root)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
