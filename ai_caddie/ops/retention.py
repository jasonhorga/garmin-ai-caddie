"""Private-volume retention maintenance (C10).

The implementation is intentionally introduced behind a small public entry point so the
service can schedule it without coupling startup to filesystem details.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import re
import shutil
import threading

from ai_caddie.core.data import ROOT
from ai_caddie.geometry import topo_render

logger = logging.getLogger(__name__)

_STYLE_VERSION_RE = re.compile(r"(?<![A-Za-z0-9])topo-v\d+(?![A-Za-z0-9])")
_SNAPSHOT_ID_RE = re.compile(r"^garmin_cn_(\d{8}T\d{6}Z)$")
_RETENTION_DISABLED = frozenset(("0", "false", "no", "off", "disabled"))
_CLEANUP_LOCK = threading.Lock()


def _enabled() -> bool:
    return os.environ.get("AI_CADDIE_RETENTION_ENABLED", "1").strip().lower() not in _RETENTION_DISABLED


def _topo_roots(root: Path) -> tuple[Path, ...]:
    roots = [root / "output" / "topo_render_cache"]
    configured = os.environ.get("AI_CADDIE_TOPO_CACHE_DIR")
    if configured:
        roots.append(Path(configured))
    return tuple(dict.fromkeys(path for path in roots))


def _style_version(relative_path: Path) -> str | None:
    for part in relative_path.parts:
        match = _STYLE_VERSION_RE.search(part)
        if match:
            return match.group(0)
    return None


def _clean_topo_cache(cache_root: Path, *, remove_empty: bool = False) -> None:
    if not cache_root.is_dir():
        return
    # Only the current renderer version is ever read or written (``topo_render.cache_dir``);
    # older versions that the API still accepts as a request parameter are served from it too,
    # so their on-disk PNGs are dead weight (C374: topo-v11 held 1.4G a week after v12 shipped).
    current = topo_render.STYLE_VERSION
    try:
        entries = sorted(cache_root.rglob("*"), key=lambda path: len(path.parts), reverse=True)
    except OSError:
        logger.warning("retention could not inspect topo cache", exc_info=True)
        return
    expired_versions: list[Path] = []
    for path in entries:
        try:
            relative = path.relative_to(cache_root)
            version = _style_version(relative)
            if path.is_file() or path.is_symlink():
                if version is not None and version != current:
                    path.unlink()
            elif path.is_dir() and _STYLE_VERSION_RE.fullmatch(path.name):
                # Remove an expired version directory only after recognized files have gone.
                # Its generated detail trees can be empty but have arbitrary names, so drain
                # those empty directories before removing the version root.
                if version is not None and version != current:
                    expired_versions.append(path)
        except OSError:
            logger.warning("retention could not remove topo cache entry", exc_info=True)
    for version_root in sorted(expired_versions, key=lambda path: len(path.parts), reverse=True):
        try:
            children = sorted(version_root.rglob("*"), key=lambda path: len(path.parts), reverse=True)
            for child in children:
                if child.is_dir() and not child.is_symlink():
                    try:
                        child.rmdir()
                    except OSError:
                        # A non-empty or concurrently-written directory remains protected.
                        pass
            version_root.rmdir()
        except OSError:
            logger.warning("retention could not remove topo cache entry", exc_info=True)
    if remove_empty:
        try:
            if not any(cache_root.iterdir()):
                cache_root.rmdir()
        except OSError:
            logger.warning("retention could not remove empty legacy topo cache", exc_info=True)


def _parse_snapshot_time(name: str, manifest: Path) -> datetime | None:
    match = _SNAPSHOT_ID_RE.match(name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _clean_garmin_snapshots(root: Path) -> None:
    snapshot_root = root / "data" / "snapshots"
    if not snapshot_root.is_dir():
        return
    pairs: list[tuple[datetime, str, Path, Path]] = []
    try:
        for directory in snapshot_root.iterdir():
            if not directory.is_dir() or not directory.name.startswith("garmin_cn_"):
                continue
            manifest = snapshot_root / f"{directory.name}.json"
            if not manifest.is_file():
                continue
            timestamp = _parse_snapshot_time(directory.name, manifest)
            if timestamp is not None:
                pairs.append((timestamp, directory.name, directory, manifest))
    except OSError:
        logger.warning("retention could not inspect Garmin snapshots", exc_info=True)
        return

    pairs.sort(key=lambda item: (item[0], item[1]), reverse=True)
    for _timestamp, _name, directory, manifest in pairs[3:]:
        try:
            shutil.rmtree(directory)
        except OSError:
            logger.warning("retention could not remove Garmin snapshot", exc_info=True)
            continue
        try:
            manifest.unlink()
        except OSError:
            logger.warning("retention could not remove Garmin snapshot manifest", exc_info=True)


def cleanup_private_volume(*, root: Path | None = None) -> None:
    """Delete expired private caches while preserving unknown files and service availability."""
    if not _enabled() or not _CLEANUP_LOCK.acquire(blocking=False):
        return
    base = Path(root) if root is not None else ROOT
    try:
        configured = os.environ.get("AI_CADDIE_TOPO_CACHE_DIR")
        legacy_default = base / "output" / "topo_render_cache"
        for cache_root in _topo_roots(base):
            try:
                _clean_topo_cache(
                    cache_root,
                    remove_empty=bool(configured and cache_root == legacy_default and Path(configured) != legacy_default),
                )
            except Exception:
                logger.warning("retention topo cleanup failed", exc_info=True)
        try:
            _clean_garmin_snapshots(base)
        except Exception:
            logger.warning("retention Garmin snapshot cleanup failed", exc_info=True)
    finally:
        _CLEANUP_LOCK.release()


def start_retention_cleanup(*, root: Path | None = None) -> threading.Thread | None:
    """Schedule one cleanup pass without delaying service startup."""
    if not _enabled():
        return None
    thread = threading.Thread(
        target=cleanup_private_volume,
        kwargs={"root": root},
        name="private-volume-retention",
        daemon=True,
    )
    thread.start()
    return thread
