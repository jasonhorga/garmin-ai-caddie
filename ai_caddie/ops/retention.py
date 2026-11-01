"""Private-volume retention maintenance (C10).

The implementation is intentionally introduced behind a small public entry point so the
service can schedule it without coupling startup to filesystem details.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import shutil
import threading

from ai_caddie.core.data import ROOT
from ai_caddie.geometry import topo_render

logger = logging.getLogger(__name__)

_STYLE_VERSION_RE = re.compile(r"topo-v\d+")
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


def _clean_topo_cache(cache_root: Path) -> None:
    if not cache_root.is_dir():
        return
    supported = topo_render.SUPPORTED_STYLE_VERSIONS
    try:
        entries = sorted(cache_root.rglob("*"), key=lambda path: len(path.parts), reverse=True)
    except OSError:
        logger.warning("retention could not inspect topo cache %s", cache_root, exc_info=True)
        return
    for path in entries:
        try:
            relative = path.relative_to(cache_root)
            version = _style_version(relative)
            if path.is_file() or path.is_symlink():
                if version is not None and version not in supported:
                    path.unlink()
            elif path.is_dir() and _STYLE_VERSION_RE.fullmatch(path.name):
                # Remove an expired version directory only after recognized files have gone;
                # unknown files inside it remain protected by the same rule as loose files.
                if version is not None and version not in supported and not any(path.iterdir()):
                    path.rmdir()
        except OSError:
            logger.warning("retention could not remove topo cache entry %s", path, exc_info=True)


def _parse_snapshot_time(name: str, manifest: Path) -> datetime | None:
    match = _SNAPSHOT_ID_RE.match(name)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        value = payload.get("createdAt") if isinstance(payload, dict) else None
        if value:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
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
        logger.warning("retention could not inspect Garmin snapshots %s", snapshot_root, exc_info=True)
        return

    pairs.sort(key=lambda item: (item[0], item[1]), reverse=True)
    for _timestamp, _name, directory, manifest in pairs[3:]:
        try:
            shutil.rmtree(directory)
        except OSError:
            logger.warning("retention could not remove Garmin snapshot %s", directory, exc_info=True)
            continue
        try:
            manifest.unlink()
        except OSError:
            logger.warning("retention could not remove Garmin snapshot manifest %s", manifest, exc_info=True)


def cleanup_private_volume(*, root: Path | None = None) -> None:
    """Delete expired private caches while preserving unknown files and service availability."""
    if not _enabled() or not _CLEANUP_LOCK.acquire(blocking=False):
        return
    base = Path(root) if root is not None else ROOT
    try:
        for cache_root in _topo_roots(base):
            try:
                _clean_topo_cache(cache_root)
            except Exception:
                logger.warning("retention topo cleanup failed for %s", cache_root, exc_info=True)
        try:
            _clean_garmin_snapshots(base)
        except Exception:
            logger.warning("retention Garmin snapshot cleanup failed for %s", base, exc_info=True)
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
