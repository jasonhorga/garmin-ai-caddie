#!/usr/bin/env python3
"""Audit captured Garmin MEDIUM_PLUS ``courseData`` files without mutating them."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


NAME = re.compile(r"^(?P<layout>\d+)_(?P<build>\d+)_medium-plus\.json$")
SEMICIRCLE_DEGREES = 180.0 / (1 << 31)
EARTH_RADIUS_M = 6_371_008.8
KNOWN_LINES = {3240, 3241, 3242, 3243, 3244}
KNOWN_ANCHORS = {18123, 18124, 18125}
HAZARD_LINES = {3241, 3242, 3243}
SIDE_MIN_AGREEMENT = 0.998
CENTER_M = 0.5


def _int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"expected integer, got {value!r}")
    return value


def _u32(value: Any) -> int:
    raw = _int(value)
    if not -(1 << 31) <= raw <= (1 << 32) - 1:
        raise ValueError(f"not a signed-or-unsigned uint32: {raw}")
    return raw & 0xFFFFFFFF


def _counts(counter: Counter[Any]) -> dict[str, int]:
    return {str(key): counter[key] for key in sorted(counter, key=str)}


def _sample(rows: list[dict[str, Any]], row: dict[str, Any]) -> None:
    if len(rows) < 20:
        rows.append(row)


def _degrees(point: dict[str, Any]) -> tuple[float, float]:
    latitude = _int(point["Latitude"]) * SEMICIRCLE_DEGREES
    longitude = _int(point["Longitude"]) * SEMICIRCLE_DEGREES
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("point is outside WGS84")
    return latitude, longitude


def _xy(
    point: dict[str, Any], ref_latitude: float, ref_longitude: float
) -> tuple[float, float]:
    latitude, longitude = _degrees(point)
    return (
        math.radians(longitude - ref_longitude)
        * math.cos(math.radians(ref_latitude))
        * EARTH_RADIUS_M,
        math.radians(latitude - ref_latitude) * EARTH_RADIUS_M,
    )


def _route_frame(
    points: list[dict[str, Any]],
) -> tuple[list[tuple[float, float]], float, float]:
    coordinates = [_degrees(point) for point in points]
    ref_latitude = sum(row[0] for row in coordinates) / len(coordinates)
    ref_longitude = sum(row[1] for row in coordinates) / len(coordinates)
    return (
        [_xy(point, ref_latitude, ref_longitude) for point in points],
        ref_latitude,
        ref_longitude,
    )


def _nearest(
    point: tuple[float, float], route: list[tuple[float, float]]
) -> tuple[float, float]:
    """Signed cross-track (+left/-right) and station on a tee-to-green route."""
    best = (math.inf, 0.0, 0.0)
    cumulative = 0.0
    for start, end in zip(route, route[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        squared = dx * dx + dy * dy
        length = math.sqrt(squared)
        if not squared:
            continue
        t = max(
            0.0,
            min(
                1.0,
                ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
                / squared,
            ),
        )
        projected = start[0] + t * dx, start[1] + t * dy
        distance = math.hypot(point[0] - projected[0], point[1] - projected[1])
        cross = dx * (point[1] - start[1]) - dy * (point[0] - start[0])
        signed = 0.0 if not distance else (distance if cross > 0 else -distance)
        if distance < best[0]:
            best = distance, signed, cumulative + t * length
        cumulative += length
    if not math.isfinite(best[0]):
        raise ValueError("route has no non-zero segment")
    return best[1], best[2]


def _side(signed: float) -> str:
    if signed < -CENTER_M:
        return "right"
    if signed > CENTER_M:
        return "left"
    return "center"


def _distribution(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "rightCount": sum(value < -CENTER_M for value in values),
        "centerCount": sum(abs(value) <= CENTER_M for value in values),
        "leftCount": sum(value > CENTER_M for value in values),
        "medianSignedCrossTrackMetres": round(statistics.median(values), 6),
    }


def audit_course_data_corpus(root: Path, *, fetch_manifest: Path) -> dict[str, Any]:
    paths = sorted(Path(root).glob("*_medium-plus.json"), key=lambda path: path.name)
    artifacts: dict[tuple[int, int], dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    filename_errors: list[dict[str, Any]] = []
    digest = hashlib.sha256()

    for path in paths:
        raw = path.read_bytes()
        digest.update(path.name.encode() + b"\0" + hashlib.sha256(raw).digest())
        try:
            match = NAME.fullmatch(path.name)
            if not match:
                raise ValueError("filename has no layout/build binding")
            payload = json.loads(raw)
            layout, build = _int(payload["GlobalLayoutId"]), _int(payload["BuildId"])
            key = layout, build
            if key in artifacts:
                raise ValueError(f"duplicate layout/build {key}")
            if key != (int(match["layout"]), int(match["build"])):
                filename_errors.append({"artifact": path.name, "payload": list(key)})
            artifacts[key] = {
                "name": path.name,
                "bytes": len(raw),
                "payload": payload,
                "holes": len(payload["Holes"]),
            }
        except Exception as exc:
            errors.append({"artifact": path.name, "error": f"{type(exc).__name__}: {exc}"})

    manifest_raw = b""
    manifest_rows: dict[tuple[int, int], dict[str, Any]] = {}
    manifest_errors: list[dict[str, Any]] = []
    try:
        manifest_raw = Path(fetch_manifest).read_bytes()
        for row in json.loads(manifest_raw):
            key = _int(row["gid"]), _int(row["build"])
            if key in manifest_rows:
                _sample(manifest_errors, {"kind": "duplicate", "key": list(key)})
            manifest_rows[key] = row
            artifact = artifacts.get(key)
            suffix = f"/courseData/{key[1]},{key[0]},32/Hazards"
            if row.get("status") != "ok" or not str(row.get("url", "")).endswith(suffix):
                _sample(manifest_errors, {"kind": "status-or-url", "key": list(key)})
            if not artifact:
                _sample(manifest_errors, {"kind": "missing-artifact", "key": list(key)})
            elif (row.get("bytes"), row.get("holes")) != (
                artifact["bytes"],
                artifact["holes"],
            ):
                _sample(manifest_errors, {"kind": "bytes-or-holes", "key": list(key)})
        for key in set(artifacts) - set(manifest_rows):
            _sample(manifest_errors, {"kind": "missing-manifest-row", "key": list(key)})
    except Exception as exc:
        manifest_errors.append({"kind": "read", "error": f"{type(exc).__name__}: {exc}"})

    line_codes: Counter[int] = Counter()
    anchor_codes: Counter[int] = Counter()
    closures: Counter[int] = Counter()
    point_flags: Counter[int] = Counter()
    build_counts: Counter[int] = Counter()
    route_count_bad: list[dict[str, Any]] = []
    info_bad: list[dict[str, Any]] = []
    bitset_bad: list[dict[str, Any]] = []
    side_bad: list[dict[str, Any]] = []
    invalid_sides: list[dict[str, Any]] = []
    side_values: dict[tuple[str, int, int], list[float]] = defaultdict(list)
    side_checked = side_agreed = hole_count = info_checked = bitset_checked = 0
    subspan_count = subspan_forward = subspan_bad_points = 0
    subspan_courses: set[int] = set()
    subspan_flags: Counter[int] = Counter()
    subspan_cross_track = subspan_length_delta = 0.0
    opaque_line_courses: set[int] = set()
    opaque_anchor_courses: set[int] = set()

    for (layout, build), artifact in artifacts.items():
        build_counts[build] += 1
        seen_holes: set[int] = set()
        for hole in artifact["payload"]["Holes"]:
            hole_number = _int(hole["HoleNumber"])
            if hole_number in seen_holes:
                errors.append({"artifact": artifact["name"], "error": "duplicate hole"})
                continue
            seen_holes.add(hole_number)
            hole_count += 1
            ref = {"layoutId": layout, "holeNumber": hole_number}
            lines, anchors = hole["Line"], hole["Hazards"]
            for line in lines:
                code = _int(line["LineCode"])
                line_codes[code] += 1
                for point in line["Points"]:
                    closures[_int(point["Closure"])] += 1
                    point_flags[_int(point["Flag"])] += 1
            for anchor in anchors:
                anchor_codes[_int(anchor["Code"])] += 1

            routes = [line for line in lines if line["LineCode"] == 3240]
            if len(routes) != 1:
                _sample(route_count_bad, {**ref, "count": len(routes)})
                continue
            route = routes[0]
            route_flags = _u32(route["Flags"])
            route_points = sorted(route["Points"], key=lambda point: _int(point["PointNumber"]))
            projected_route, ref_latitude, ref_longitude = _route_frame(route_points)

            info_checked += 1
            if _int(hole["InfoMask"]) != (route_flags >> 28) & 0xF:
                _sample(info_bad, ref)
            expected = 0
            for point in route_points:
                number, flag = _int(point["PointNumber"]), _int(point["Flag"])
                if flag == 1 and 1 <= number <= 28:
                    expected |= 1 << (number - 1)
            bitset_checked += 1
            if route_flags & 0x0FFFFFFF != expected:
                _sample(bitset_bad, ref)

            def record_side(source: str, code: int, flags: int, point: tuple[float, float]) -> None:
                nonlocal side_checked, side_agreed
                bits = flags & 3
                if bits not in {1, 2, 3}:
                    _sample(invalid_sides, {**ref, "source": source, "code": code, "flags": flags})
                    return
                signed, _ = _nearest(point, projected_route)
                side_values[(source, code, bits)].append(signed)
                if bits in {1, 2}:
                    side_checked += 1
                    matches = (bits == 1 and _side(signed) == "right") or (
                        bits == 2 and _side(signed) == "left"
                    )
                    side_agreed += int(matches)
                    if not matches:
                        _sample(
                            side_bad,
                            {
                                **ref,
                                "source": source,
                                "code": code,
                                "flags": flags,
                                "signedCrossTrackMetres": round(signed, 6),
                            },
                        )

            for line in lines:
                code, flags = _int(line["LineCode"]), _int(line["Flags"])
                points = sorted(line["Points"], key=lambda point: _int(point["PointNumber"]))
                projected = [_xy(point, ref_latitude, ref_longitude) for point in points]
                if code in HAZARD_LINES:
                    if code == 3243:
                        opaque_line_courses.add(layout)
                    midpoint = (
                        sum(point[0] for point in projected) / len(projected),
                        sum(point[1] for point in projected) / len(projected),
                    )
                    record_side("line", code, flags, midpoint)
                elif code == 3244:
                    subspan_count += 1
                    subspan_courses.add(layout)
                    subspan_flags[flags] += 1
                    if line["CoordinateCount"] != 2 or len(projected) != 2:
                        subspan_bad_points += 1
                        continue
                    first = _nearest(projected[0], projected_route)
                    second = _nearest(projected[1], projected_route)
                    subspan_forward += int(first[1] < second[1])
                    subspan_cross_track = max(subspan_cross_track, abs(first[0]), abs(second[0]))
                    subspan_length_delta = max(
                        subspan_length_delta,
                        abs((second[1] - first[1]) - float(line["Length"])),
                    )
            for anchor in anchors:
                code, flags = _int(anchor["Code"]), _int(anchor["Flags"])
                if code == 18125:
                    opaque_anchor_courses.add(layout)
                if code in KNOWN_ANCHORS:
                    record_side(
                        "anchor",
                        code,
                        flags,
                        _xy(anchor, ref_latitude, ref_longitude),
                    )

    agreement = side_agreed / side_checked if side_checked else 0.0
    subspan_closed = (
        subspan_count > 0
        and not subspan_bad_points
        and subspan_forward == subspan_count
        and set(subspan_flags) == {3}
        and subspan_cross_track <= 0.25
        and subspan_length_delta <= 1.1
    )
    gates = {
        "artifactsReadable": bool(paths) and not errors,
        "fetchManifestBound": bool(manifest_raw)
        and not manifest_errors
        and set(manifest_rows) == set(artifacts),
        "filenameAuthorityBound": not filename_errors,
        "oneRoutePerHole": not route_count_bad and info_checked == hole_count,
        "infoMaskEqualsRouteFlagsHighNibble": not info_bad and info_checked == hole_count,
        "routePointFlagsEqualFlagsLow28Bitset": not bitset_bad and bitset_checked == hole_count,
        "closuresObservedOnlyZero": bool(closures) and set(closures) == {0},
        "pointFlagsObservedOnlyZeroOrOne": bool(point_flags) and set(point_flags) <= {0, 1},
        "knownLineCodesOnly": set(line_codes) <= KNOWN_LINES,
        "knownAnchorCodesOnly": set(anchor_codes) <= KNOWN_ANCHORS,
        "hazardSideBitsSupported": not invalid_sides,
        "hazardSideSemanticsCrossChecked": side_checked > 0 and agreement >= SIDE_MIN_AGREEMENT,
        "routeSubspan3244StructurallyClosed": subspan_closed,
        "opaqueThirdHazardCategoryObserved": line_codes[3243] > 0 and anchor_codes[18125] > 0,
    }
    return {
        "schema": "garmin-course-data-corpus-audit-v1",
        "corpus": {
            "artifactCount": len(paths),
            "courseCount": len(artifacts),
            "holeCount": hole_count,
            "buildCounts": _counts(build_counts),
            "artifactSetSha256": digest.hexdigest(),
            "fetchManifestSha256": hashlib.sha256(manifest_raw).hexdigest()
            if manifest_raw
            else None,
        },
        "authorityBinding": {
            "manifestRowCount": len(manifest_rows),
            "manifestErrors": manifest_errors,
            "filenameErrors": filename_errors,
            "artifactErrors": errors,
        },
        "rawInventory": {
            "lineCodeCounts": _counts(line_codes),
            "anchorCodeCounts": _counts(anchor_codes),
            "closureCounts": _counts(closures),
            "pointFlagCounts": _counts(point_flags),
            "unexpectedLineCodes": sorted(set(line_codes) - KNOWN_LINES),
            "unexpectedAnchorCodes": sorted(set(anchor_codes) - KNOWN_ANCHORS),
        },
        "routeFlags": {
            "routeCountChecked": info_checked,
            "routeCountMismatchCount": len(route_count_bad),
            "infoMaskChecked": info_checked,
            "infoMaskMismatchCount": len(info_bad),
            "pointFlagBitsetChecked": bitset_checked,
            "pointFlagBitsetMismatchCount": len(bitset_bad),
            "infoMaskRelationship": "InfoMask == ((uint32(route.Flags) >> 28) & 0xF)",
            "pointFlagBitsetRelationship": (
                "route.Flags & 0x0fffffff == OR(1 << (PointNumber - 1) for Flag == 1)"
            ),
        },
        "hazardSideFlags": {
            "semantic": {"1": "right", "2": "left", "3": "center-crossing-or-mixed"},
            "highBitsPolicy": "preserve as opaque subtype bits",
            "singleSideChecked": side_checked,
            "singleSideAgreed": side_agreed,
            "singleSideAgreementRatio": round(agreement, 9),
            "mismatchCount": len(side_bad),
            "mismatchSamples": side_bad,
            "invalidSideBitCount": len(invalid_sides),
            "distributions": {
                f"{source}:{code}:{bits}": _distribution(values)
                for (source, code, bits), values in sorted(side_values.items())
            },
        },
        "routeSubspan3244": {
            "lineCount": subspan_count,
            "courseCount": len(subspan_courses),
            "flagCounts": _counts(subspan_flags),
            "orderedTeeToGreenCount": subspan_forward,
            "maximumCrossTrackMetres": round(subspan_cross_track, 6),
            "maximumDeclaredLengthDeltaMetres": round(subspan_length_delta, 6),
            "classification": "opaque-route-subspan",
            "productDecision": "retain raw line; render no guessed cart path or surface",
        },
        "opaqueThirdHazardCategory": {
            "lineCode": 3243,
            "lineCount": line_codes[3243],
            "lineCourseCount": len(opaque_line_courses),
            "anchorCode": 18125,
            "anchorCount": anchor_codes[18125],
            "anchorCourseCount": len(opaque_anchor_courses),
            "classification": "garmin-third-opaque-hazard-category",
            "productDecision": "retain raw codes and side bits; expose no guessed surface label",
        },
        "gates": {**gates, "passed": all(gates.values())},
    }


def report_bytes(report: dict[str, Any]) -> bytes:
    return (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--fetch-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = audit_course_data_corpus(args.root, fetch_manifest=args.fetch_manifest)
    payload = report_bytes(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"{hashlib.sha256(payload).hexdigest()}  {args.output}")
    if not report["gates"]["passed"]:
        print("courseData corpus audit gates failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
