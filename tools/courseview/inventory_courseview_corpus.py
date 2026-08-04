#!/usr/bin/env python3
"""Inventory the CourseView bytes we already own before inventing another decoder.

This is deliberately a small, read-only DeepMine pass. It scans release protobufs and
extracted prodgeometry directories, reports every observed mesh/JSON/protobuf field, and
separates product-consumed, known structural, and genuinely unclassified mesh names.
It never downloads, decrypts, rewrites, or publishes course data.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ai_caddie.geometry.export_prodgeometry_hazards import FEATURES, KNOWN_NON_HAZARD
from ai_caddie.geometry.inspect_courseview_release import parse_fields


SCHEMA = "ai-caddie-courseview-corpus-inventory-v1"

# topo-v5's factual drawing inputs. Other decoded meshes may still feed semantic export.
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


def inventory_courseview(root: Path) -> dict[str, Any]:
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
            errors.append({"artifact": path.name, "error": type(exc).__name__})

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

    hole_json_paths = sorted((root / "prodgeometry").glob("*/*/hole.json"))
    for hole_path in hole_json_paths:
        directory = hole_path.parent
        for asset in directory.iterdir():
            if not asset.is_file():
                continue
            asset_files[asset.name] += 1
            if asset.suffix.lower() == ".drc":
                mesh_files[asset.name] += 1

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
            errors.append({"artifact": str(hole_path.relative_to(root)), "error": type(exc).__name__})

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
            errors.append({"artifact": str(foliage_path.relative_to(root)), "error": type(exc).__name__})

    observed_meshes = set(mesh_files)
    semantic_meshes = set(FEATURES)
    structural_meshes = set(KNOWN_NON_HAZARD)
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
        "prodgeometry": {
            "courseCount": len(course_ids),
            "holeCount": len(hole_json_paths),
            "assetNames": _counter(asset_files),
            "meshNames": _counter(mesh_files),
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
        },
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="directory containing *_releases.pb and prodgeometry/")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = inventory_courseview(args.root)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
