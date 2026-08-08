"""Version identity for decoded Garmin ``prodgeometry`` artifacts.

Garmin's release URLs contain short-lived ``garmindlm`` query signatures.  The
stable content identity is the release-bound asset path (whose filename embeds
the CourseGen/hole version), not that signature.  This module keeps the decoded
mesh/hazard pair and every derived topo bitmap tied to that stable identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ai_caddie.core.data import atomic_write_json, safe_read_json

SCHEMA = "garmin-prodgeometry-authority-v1"


def authority_path(mesh_file: Path) -> Path:
    """Sidecar next to one canonical ``*_meshes.json`` output."""
    suffix = "_meshes.json"
    name = mesh_file.name
    stem = name[: -len(suffix)] if name.endswith(suffix) else mesh_file.stem
    return mesh_file.with_name(f"{stem}_authority.json")


def canonical_asset_path(url: object) -> str | None:
    """Drop regional host and expiring query signature from a Garmin asset URL."""
    value = str(url or "").strip()
    if not value:
        return None
    path = urlsplit(value).path
    return path or None


def asset_version(path: object) -> str | None:
    """Embedded version from Garmin's geometry filename.

    CourseView currently publishes both ``hole02_220542.zip`` and format-tagged
    variants such as ``hole02_220542_f3.zip``.  The numeric segment is the
    ``CourseGenVersion`` + per-hole ``Version`` identity encoded in the decoded
    payload; the optional ``fN`` tag remains part of ``geometryAssetPath`` so two
    distinct provider assets never collapse to one authority.
    """
    name = Path(str(path or "")).stem
    match = re.fullmatch(r"hole\d+_(\d+)(?:_f\d+)?", name, flags=re.IGNORECASE)
    return match.group(1) if match else None


def valid_geometry_zip_sha256(value: object) -> bool:
    """Whether an authority records a real canonical SHA-256, not a placeholder.

    Older decoded geometry predates the ZIP digest field and some planning fixtures used an
    all-zero value.  Neither proves which provider bytes produced the installed derivatives, so
    neither may become current online authority.
    """
    digest = str(value or "")
    return (
        len(digest) == 64
        and digest == digest.lower()
        and all(character in "0123456789abcdef" for character in digest)
        and any(character != "0" for character in digest)
    )


def build_authority(
    *,
    global_id: int,
    local_hole: int,
    release: Mapping[str, Any],
    hole: Mapping[str, Any],
    release_source: str,
    geometry_zip_sha256: str | None = None,
) -> dict[str, Any]:
    geometry_path = canonical_asset_path(hole.get("geometry_url"))
    raster_path = canonical_asset_path(hole.get("raster_url"))
    return {
        "schema": SCHEMA,
        "globalId": int(global_id),
        "localHole": int(local_hole),
        "releaseVersion": release.get("release_version"),
        "releaseId": release.get("release_id"),
        "courseGenVersion": release.get("course_gen_version"),
        "geometryAssetPath": geometry_path,
        "geometryAssetVersion": asset_version(geometry_path),
        "rasterAssetPath": raster_path,
        "geometryZipSha256": geometry_zip_sha256,
        "releaseSource": str(release_source),
        "boundAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def load_authority(path: Path) -> dict[str, Any] | None:
    value = safe_read_json(path)
    return value if isinstance(value, dict) and value.get("schema") == SCHEMA else None


def write_authority(path: Path, value: Mapping[str, Any]) -> None:
    atomic_write_json(path, dict(value))


def files_ready(mesh_file: Path, hazard_file: Path) -> bool:
    return mesh_file.is_file() and hazard_file.is_file()


def authority_is_bound(
    value: Mapping[str, Any] | None,
    *,
    global_id: int,
    local_hole: int,
    mesh_file: Path,
    hazard_file: Path,
) -> bool:
    return bool(
        value
        and value.get("schema") == SCHEMA
        and value.get("globalId") == int(global_id)
        and value.get("localHole") == int(local_hole)
        and value.get("geometryAssetPath")
        and value.get("geometryAssetVersion")
        == asset_version(value.get("geometryAssetPath"))
        and valid_geometry_zip_sha256(value.get("geometryZipSha256"))
        and files_ready(mesh_file, hazard_file)
    )


def same_geometry_content(
    current: Mapping[str, Any], expected: Mapping[str, Any]
) -> bool:
    """Whether decoded bytes may be reused under refreshed release metadata."""
    return all(
        current.get(key) == expected.get(key)
        for key in (
            "globalId",
            "localHole",
            "courseGenVersion",
            "geometryAssetPath",
            "geometryAssetVersion",
        )
    )


def same_release_binding(
    current: Mapping[str, Any], expected: Mapping[str, Any]
) -> bool:
    """Whether the sidecar already records the complete current release binding."""
    return all(
        current.get(key) == expected.get(key)
        for key in (
            "globalId",
            "localHole",
            "releaseVersion",
            "releaseId",
            "courseGenVersion",
            "geometryAssetPath",
            "geometryAssetVersion",
            "rasterAssetPath",
        )
    )


def authority_matches_release(
    value: Mapping[str, Any] | None,
    *,
    global_id: int,
    local_hole: int,
    mesh_file: Path,
    hazard_file: Path,
    release: Mapping[str, Any],
) -> bool:
    """Whether installed precise geometry is bound to the cached current release.

    A mesh/hazard pair can predate the authority sidecar or belong to an older Garmin
    release while still being perfectly readable.  Such bytes remain an offline fallback,
    but an online course package must treat them as pending until ``ensure_prodgeometry``
    validates or replaces them.  This comparison is cache-only; the caller decides when to
    refresh Garmin's small release document.
    """
    if not authority_is_bound(
        value,
        global_id=global_id,
        local_hole=local_hole,
        mesh_file=mesh_file,
        hazard_file=hazard_file,
    ):
        return False
    hole = next(
        (
            row
            for row in release.get("holes", [])
            if isinstance(row, Mapping)
            and int(row.get("hole") or -1) == int(local_hole)
        ),
        None,
    )
    if hole is None:
        return False
    expected = build_authority(
        global_id=global_id,
        local_hole=local_hole,
        release=release,
        hole=hole,
        release_source=str(value.get("releaseSource") or "cache"),
        geometry_zip_sha256=value.get("geometryZipSha256"),
    )
    return same_release_binding(value, expected)


def _combined_hole_version(hole: Mapping[str, Any]) -> str | None:
    try:
        course_gen = int(hole["CourseGenVersion"])
        version = int(hole["Version"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return f"{course_gen}{version:04d}"


def legacy_outputs_match(
    expected: Mapping[str, Any],
    *,
    mesh_file: Path,
    hazard_file: Path,
) -> bool:
    """Bind pre-sidecar outputs only when both decoded files prove the asset version."""
    if not files_ready(mesh_file, hazard_file):
        return False
    mesh = safe_read_json(mesh_file)
    hazard = safe_read_json(hazard_file)
    if not isinstance(mesh, dict) or not isinstance(hazard, dict):
        return False
    hole = mesh.get("hole")
    if not isinstance(hole, dict):
        return False
    try:
        ids_match = (
            int(hole.get("GlobalId")) == int(expected["globalId"])
            and int(hole.get("HoleNumber")) == int(expected["localHole"])
            and int(hazard.get("globalId")) == int(expected["globalId"])
            and int(hazard.get("holeNumber")) == int(expected["localHole"])
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    if not ids_match:
        return False
    version = _combined_hole_version(hole)
    if version != expected.get("geometryAssetVersion"):
        return False
    if (
        _combined_hole_version(
            {
                "CourseGenVersion": hazard.get("courseGenVersion"),
                "Version": hazard.get("version"),
            }
        )
        != version
    ):
        return False
    # The extracted directory preserves the complete provider filename stem,
    # including optional format tags (for example ``Hole01_280661_f3``).  Match
    # that exact identity case-insensitively instead of requiring the directory
    # to end at the numeric version, which rejected every tagged Garmin asset
    # after it had already downloaded and decoded successfully.
    source_name = Path(str(mesh.get("sourceDir") or "")).name
    expected_source_name = Path(str(expected.get("geometryAssetPath") or "")).stem
    return (
        bool(expected_source_name)
        and source_name.casefold() == expected_source_name.casefold()
    )


def cache_token(
    *,
    global_id: int,
    local_hole: int,
    mesh_file: Path,
    hazard_file: Path,
    sidecar: Path | None = None,
) -> str:
    """Short identity for derivatives; legacy files fall back to stat fingerprints."""
    manifest = load_authority(sidecar or authority_path(mesh_file))
    if authority_is_bound(
        manifest,
        global_id=global_id,
        local_hole=local_hole,
        mesh_file=mesh_file,
        hazard_file=hazard_file,
    ):
        stable = {
            "globalId": manifest.get("globalId"),
            "localHole": manifest.get("localHole"),
            # A release can change its selected layout/route or raster while reusing the same
            # prodgeometry zip.  Those facts influence the rendered hole envelope, so derivatives
            # must follow the complete release binding rather than geometry bytes alone.
            "releaseVersion": manifest.get("releaseVersion"),
            "releaseId": manifest.get("releaseId"),
            "courseGenVersion": manifest.get("courseGenVersion"),
            "geometryAssetPath": manifest.get("geometryAssetPath"),
            "geometryAssetVersion": manifest.get("geometryAssetVersion"),
            "rasterAssetPath": manifest.get("rasterAssetPath"),
            "geometryZipSha256": manifest.get("geometryZipSha256"),
        }
        raw = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    else:
        rows: list[tuple[str, int, int]] = []
        for path in (mesh_file, hazard_file):
            try:
                stat = path.stat()
            except OSError:
                continue
            rows.append((path.name, stat.st_size, stat.st_mtime_ns))
        raw = repr(rows).encode()
    return hashlib.sha256(raw).hexdigest()[:16]
