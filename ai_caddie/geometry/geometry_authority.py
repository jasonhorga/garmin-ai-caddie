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
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ai_caddie.core.data import atomic_write_json, safe_read_json

SCHEMA = "garmin-prodgeometry-authority-v1"
_AUTHORITY_WRITE_LOCK = threading.RLock()


def authority_path(mesh_file: Path) -> Path:
    """Sidecar next to one canonical ``*_meshes.json`` output."""
    suffix = "_meshes.json"
    name = mesh_file.name
    stem = name[: -len(suffix)] if name.endswith(suffix) else mesh_file.stem
    return mesh_file.with_name(f"{stem}_authority.json")


def derivatives_status_path(mesh_file: Path) -> Path:
    """Durable status for the deferred distance/obstacle exporters."""
    suffix = "_meshes.json"
    name = mesh_file.name
    stem = name[: -len(suffix)] if name.endswith(suffix) else mesh_file.stem
    return mesh_file.with_name(f"{stem}_derivatives_status.json")


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
    # Some CourseView layouts expose a route asset/signature alongside the raster.  Preserve it
    # when present, while keeping older release rows valid; ``cache_token`` also derives a route
    # identity from the installed mesh/cache for releases that omit these optional fields.
    route_identity = next(
        (
            hole.get(key)
            for key in (
                "routeIdentity",
                "route_identity",
                "route",
                "routePoints",
                "routeId",
                "route_id",
                "routeVersion",
                "route_version",
                "routeUrl",
                "route_url",
                "routeAssetPath",
                "routeAssetVersion",
                "routeSha256",
                "routeDigest",
                "routeHash",
            )
            if hole.get(key) is not None
        ),
        None,
    )
    if (
        isinstance(route_identity, str)
        and route_identity.startswith(("http://", "https://"))
    ):
        route_identity = canonical_asset_path(route_identity)
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
        "routeIdentity": route_identity,
        "geometryZipSha256": geometry_zip_sha256,
        "meshReady": True,
        "releaseSource": str(release_source),
        "boundAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def load_authority(path: Path) -> dict[str, Any] | None:
    value = safe_read_json(path)
    return value if isinstance(value, dict) and value.get("schema") == SCHEMA else None


def write_authority(path: Path, value: Mapping[str, Any]) -> None:
    with _AUTHORITY_WRITE_LOCK:
        updated = dict(value)
        previous = load_authority(path) or {}
        if (previous.get("globalId") == updated.get("globalId")
                and previous.get("localHole") == updated.get("localHole")
                and "cachedCourseDataRoute" not in updated
                and previous.get("cachedCourseDataRoute")):
            updated["cachedCourseDataRoute"] = previous["cachedCourseDataRoute"]
        atomic_write_json(path, updated)


def load_derivatives_status(mesh_file: Path) -> dict[str, Any] | None:
    value = safe_read_json(derivatives_status_path(mesh_file))
    return value if isinstance(value, dict) else None


def write_derivatives_status(mesh_file: Path, value: Mapping[str, Any]) -> None:
    atomic_write_json(derivatives_status_path(mesh_file), dict(value))


def files_ready(mesh_file: Path, hazard_file: Path | None = None) -> bool:
    """Whether the release-bound mesh input is installed.

    The mesh is the first independently usable derivative.  ``hazard_file`` remains an accepted
    compatibility argument for callers from the old all-files install path, but authority and topo
    identity deliberately do not depend on it.  Full obstacle readiness is checked by
    :func:`derivatives_ready` where a consumer actually needs it.
    """
    del hazard_file
    return mesh_file.is_file()


def derivatives_ready(mesh_file: Path, hazard_file: Path) -> bool:
    """Whether the mesh and obstacle/distance export are both installed."""
    return mesh_file.is_file() and hazard_file.is_file()


def authority_is_bound(
    value: Mapping[str, Any] | None,
    *,
    global_id: int,
    local_hole: int,
    mesh_file: Path,
    hazard_file: Path | None = None,
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
        and files_ready(mesh_file)
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
            "routeIdentity",
        )
    )


def authority_matches_release(
    value: Mapping[str, Any] | None,
    *,
    global_id: int,
    local_hole: int,
    mesh_file: Path,
    hazard_file: Path | None = None,
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


def _embedded_hole_identity(hole: Mapping[str, Any]) -> tuple[int, int] | None:
    """Return the version pair declared inside one decoded geometry payload.

    Garmin does not use one universal string encoding for this pair in the
    external ZIP filename. Older assets happened to look like
    ``CourseGenVersion + zero-padded Version``; newer assets use a different
    namespace. The exact release URL/extracted directory binds the external
    asset, while this pair binds the independently generated mesh and hazard
    projections to each other.
    """
    try:
        course_gen = int(hole["CourseGenVersion"])
        version = int(hole["Version"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return course_gen, version


def legacy_outputs_match(
    expected: Mapping[str, Any],
    *,
    mesh_file: Path,
    hazard_file: Path,
) -> bool:
    """Bind decoded outputs to the exact release asset and matching internal identity."""
    if not derivatives_ready(mesh_file, hazard_file):
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
    mesh_identity = _embedded_hole_identity(hole)
    hazard_identity = _embedded_hole_identity(
        {
            "CourseGenVersion": hazard.get("courseGenVersion"),
            "Version": hazard.get("version"),
        }
    )
    if mesh_identity is None or hazard_identity != mesh_identity:
        return False
    # The decoder records the directory created directly from the selected
    # release URL. Match its complete filename stem, including optional format
    # tags (for example ``Hole01_280661_f3``). This is the external asset
    # identity; do not derive it from the payload's separate version pair.
    source_name = Path(str(mesh.get("sourceDir") or "")).name
    expected_source_name = Path(str(expected.get("geometryAssetPath") or "")).stem
    expected_asset_version = asset_version(expected.get("geometryAssetPath"))
    return (
        bool(expected_source_name)
        and bool(expected_asset_version)
        and expected.get("geometryAssetVersion") == expected_asset_version
        and source_name.casefold() == expected_source_name.casefold()
    )


def mesh_output_matches(expected: Mapping[str, Any], *, mesh_file: Path) -> bool:
    """Validate the first installable derivative against release and embedded mesh identity."""
    if not files_ready(mesh_file):
        return False
    mesh = safe_read_json(mesh_file)
    if not isinstance(mesh, dict):
        return False
    hole = mesh.get("hole")
    if not isinstance(hole, dict):
        return False
    try:
        ids_match = (
            int(hole.get("GlobalId")) == int(expected["globalId"])
            and int(hole.get("HoleNumber")) == int(expected["localHole"])
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    if not ids_match:
        return False
    source_name = Path(str(mesh.get("sourceDir") or "")).name
    expected_source_name = Path(str(expected.get("geometryAssetPath") or "")).stem
    expected_asset_version = asset_version(expected.get("geometryAssetPath"))
    return (
        bool(expected_source_name)
        and bool(expected_asset_version)
        and expected.get("geometryAssetVersion") == expected_asset_version
        and source_name.casefold() == expected_source_name.casefold()
    )


def _route_identity(
    manifest: Mapping[str, Any] | None,
    *,
    mesh_file: Path,
    global_id: int,
    local_hole: int,
) -> dict[str, Any] | None:
    """Return the cache-only identity of the route selected by topo rendering.

    Garmin release metadata does not carry one stable route field on every observed layout.  Use
    any explicit route asset/signature when present, then include the cached CourseView route
    (which is read-only and never fetched here).  The decoded mesh itself is represented by the
    mesh asset identity, so this helper does not parse a potentially large mesh JSON on the request
    path.  The obstacle export is deliberately absent: adding hazards cannot invalidate an already
    rendered mesh+route bitmap.
    """
    route: dict[str, Any] = {}
    if isinstance(manifest, Mapping):
        for key in (
            "routeIdentity",
            "route_identity",
            "route",
            "routeId",
            "route_id",
            "routeVersion",
            "route_version",
            "routeAssetPath",
            "routeAssetVersion",
            "routeSha256",
            "routeDigest",
            "routeHash",
            "routeUrl",
            "route_url",
            # The raster is the fallback map/route authority for older releases.
            "rasterAssetPath",
        ):
            value = manifest.get(key)
            if key in {"routeUrl", "route_url"}:
                value = canonical_asset_path(value)
            if value is not None and value != "":
                route[key] = value

    # CourseView route points may select a different A/B green than the decoder's fallback.  This
    # import is intentionally local to avoid a geometry/course-reference import cycle and remains
    # cache-only by contract.
    if manifest is not None:
        try:
            from ai_caddie.courses.courseview_core import load_cached_hole_route

            cached_route = load_cached_hole_route(int(global_id), int(local_hole))
            if not cached_route:
                cached_route = manifest.get("cachedCourseDataRoute")
            if cached_route:
                route["courseData.route"] = cached_route
                # Retain the last selected route across a release refresh whose new courseData
                # has not arrived yet. Only the route points enter the token, never its build id.
                if json.dumps(cached_route) != json.dumps(manifest.get("cachedCourseDataRoute")):
                    with _AUTHORITY_WRITE_LOCK:
                        current = load_authority(authority_path(mesh_file))
                        if current == manifest:
                            write_authority(authority_path(mesh_file), {
                                **manifest, "cachedCourseDataRoute": cached_route,
                            })
        except Exception:  # Optional cache/write failures must preserve the last selected route.
            if "courseData.route" not in route and manifest.get("cachedCourseDataRoute"):
                route["courseData.route"] = manifest["cachedCourseDataRoute"]
    return route or None


def cache_token(
    *,
    global_id: int,
    local_hole: int,
    mesh_file: Path,
    hazard_file: Path | None = None,
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
            # Topo is derived from the installed mesh and the selected route/raster authority.
            # Release bookkeeping may be refreshed without changing either input, so it stays out
            # of this identity; adding obstacles later must not make a phone download the same topo
            # bitmap again.
            "meshes": {
                "geometryAssetPath": manifest.get("geometryAssetPath"),
                "geometryAssetVersion": manifest.get("geometryAssetVersion"),
                "geometryZipSha256": manifest.get("geometryZipSha256"),
            },
            "route": _route_identity(
                manifest,
                mesh_file=mesh_file,
                global_id=global_id,
                local_hole=local_hole,
            ),
        }
        raw = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    else:
        rows: list[tuple[str, int, int]] = []
        # A topo bitmap is derived from the mesh and its route.  Arrival of the slower hazard
        # derivative must therefore leave its cache identity untouched, including for legacy
        # unbound files that have no authority sidecar yet.
        for path in (mesh_file,):
            try:
                stat = path.stat()
            except OSError:
                continue
            rows.append((path.name, stat.st_size, stat.st_mtime_ns))
        raw = json.dumps(
            {
                "meshes": rows,
                "route": _route_identity(
                    manifest,
                    mesh_file=mesh_file,
                    global_id=global_id,
                    local_hole=local_hole,
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    return hashlib.sha256(raw).hexdigest()[:16]
