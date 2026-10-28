"""Durable, low-priority backfill for versioned course render assets.

The normal request/install paths remain the source of truth for one hole.  This worker only scans
decoded meshes already on disk, records each asset unit before doing work, and uses the existing
``PriorityExecutor``/``work_priority`` lanes so foreground topo renders overtake queued backfill.
The journal is deliberately a small JSON file: it is crash safe, inspectable, and does not need a
database migration for renderer-only versions.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable

from ai_caddie.core.data import MESH_DIR, ROOT, atomic_write_json
from ai_caddie.core.priority_work import NEARBY, work_priority
from ai_caddie.geometry import garmin_raster, topo_render

logger = logging.getLogger(__name__)

_MESH_RE = re.compile(r"^gid(?P<gid>\d+)_h(?P<hole>\d+)_meshes\.json$")
_SCHEMA = "ai-caddie-render-backfill-v1"
_DEFAULT_STATE = ROOT / "data" / "render-backfill.json"
_MAX_YIELD_SECONDS = 30.0


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _key(gid: int, hole: int) -> str:
    return f"{int(gid)}:{int(hole)}"


def _default_topo_ready(gid: int, hole: int) -> bool:
    return topo_render.cache_path(int(gid), int(hole)).is_file()


def _default_raster_ready(gid: int, hole: int, version: str) -> bool:
    return garmin_raster._matte_path(int(gid), int(hole), version).is_file()


def _mesh_rows(mesh_root: Path) -> list[tuple[int, int]]:
    rows: list[tuple[int, int]] = []
    try:
        paths = mesh_root.glob("gid*_h*_meshes.json")
    except OSError:
        return rows
    for path in paths:
        match = _MESH_RE.match(path.name)
        if match and path.is_file():
            rows.append((int(match.group("gid")), int(match.group("hole"))))
    return sorted(set(rows))


class RenderBackfill:
    """One durable scan/worker instance.

    ``render_topo`` and ``render_garmin`` are injectable so the queue's ordering, persistence and
    yielding can be tested without PIL, Garmin bytes, or a real geometry directory.
    """

    def __init__(
        self,
        *,
        state_path: Path | str | None = None,
        mesh_root: Path | str | None = None,
        style_version: str | None = None,
        matte_version: str | None = None,
        topo_ready: Callable[[int, int], bool] | None = None,
        raster_version: Callable[[int, int], str | None] | None = None,
        raster_ready: Callable[[int, int, str], bool] | None = None,
        render_topo: Callable[[int, int], Any] | None = None,
        render_garmin: Callable[[int, int, str], Any] | None = None,
        should_yield: Callable[[], bool] | None = None,
        wait_seconds: float = 0.25,
    ) -> None:
        self.state_path = Path(state_path or os.environ.get("AI_CADDIE_RENDER_BACKFILL_STATE", _DEFAULT_STATE))
        self.mesh_root = Path(mesh_root or MESH_DIR)
        self.style_version = str(style_version or topo_render.STYLE_VERSION)
        self.matte_version = str(matte_version or garmin_raster.RASTER_MATTE_VERSION)
        self._topo_ready = topo_ready or _default_topo_ready
        self._raster_version = raster_version or (
            lambda gid, hole: garmin_raster.raster_asset_version(gid, hole, allow_fetch=False)
        )
        self._raster_ready = raster_ready or _default_raster_ready
        self._render_topo = render_topo or topo_render.render_hole_topo_cached
        self._render_garmin = render_garmin or self._default_render_garmin
        self._should_yield = should_yield or self._default_should_yield
        self._wait_seconds = max(0.0, float(wait_seconds))
        self._lock = threading.RLock()
        self._state = self._load()

    def _default_render_garmin(self, gid: int, hole: int, version: str) -> bool:
        """Use the existing bounded Garmin prefetch pool, including its startup yield hook."""
        from server_v2.garmin_raster import prefetch_holes

        futures = prefetch_holes([(gid, hole)], should_yield=self._should_yield)
        results = [future.result() for future in futures]
        return bool(any(results)) or self._raster_ready(gid, hole, version)

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            payload = {}
        if not isinstance(payload, dict) or payload.get("schema") != _SCHEMA:
            payload = {}
        tasks = payload.get("tasks") if isinstance(payload.get("tasks"), dict) else {}
        return {
            "schema": _SCHEMA,
            "styleVersion": str(payload.get("styleVersion") or ""),
            "matteVersion": str(payload.get("matteVersion") or ""),
            "updatedAt": str(payload.get("updatedAt") or ""),
            "tasks": tasks,
        }

    def _save(self) -> None:
        self._state["updatedAt"] = _now()
        atomic_write_json(self.state_path, self._state)

    @staticmethod
    def _default_should_yield() -> bool:
        try:
            from server_v2 import map_startup

            return map_startup.startup_in_flight()
        except Exception:
            return False

    def _priority(self, gid: int, hole: int, recent: set[tuple[int, int]], downloaded: set[tuple[int, int]]) -> int:
        if (gid, hole) in recent:
            return 0
        if (gid, hole) in downloaded:
            return 10
        return 20

    def _downloaded_holes(self) -> set[tuple[int, int]]:
        """Use durable install journals as the downloaded/offline priority source."""
        result: set[tuple[int, int]] = set()
        try:
            from server_v2 import course_install

            for path in course_install._root().glob("*.json"):
                try:
                    state = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    continue
                for row in (state.get("holes") or {}).values():
                    if isinstance(row, dict) and row.get("geometry") == "ready":
                        result.add((int(row.get("globalId") or 0), int(row.get("localHole") or 0)))
        except Exception:
            logger.debug("render_backfill downloaded priority scan unavailable", exc_info=True)
        return {(gid, hole) for gid, hole in result if gid > 0 and hole > 0}

    def _recent_holes(self) -> set[tuple[int, int]]:
        """Return the latest round's physical holes when the history store is available."""
        try:
            from ai_caddie.history.stats_cache import cached_load_history_data
            from ai_caddie.rounds.prepare_recent import recent_round_topo_targets

            data = cached_load_history_data()
            return {
                (int(gid), int(hole))
                for gid, holes in recent_round_topo_targets(data)
                for hole in holes
                if int(gid) > 0 and int(hole) > 0
            }
        except Exception:
            logger.debug("render_backfill recent priority scan unavailable", exc_info=True)
            return set()

    def enqueue_all(
        self,
        *,
        recent: set[tuple[int, int]] | None = None,
        downloaded: set[tuple[int, int]] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Discover all installed meshes and queue missing/current-version derivatives."""
        recent = {(int(g), int(h)) for g, h in (recent or set())}
        downloaded = self._downloaded_holes() if downloaded is None else {
            (int(g), int(h)) for g, h in downloaded
        }
        with self._lock:
            old_style = self._state.get("styleVersion")
            old_matte = self._state.get("matteVersion")
            style_changed = bool(old_style) and old_style != self.style_version
            matte_changed = bool(old_matte) and old_matte != self.matte_version
            tasks = self._state["tasks"]
            seen: set[str] = set()
            for gid, hole in _mesh_rows(self.mesh_root):
                key = _key(gid, hole)
                seen.add(key)
                source = self._raster_version(gid, hole)
                task = tasks.get(key) if isinstance(tasks.get(key), dict) else None
                if task is None:
                    task = {
                        "globalId": gid,
                        "localHole": hole,
                        "priority": self._priority(gid, hole, recent, downloaded),
                        "topo": "done" if self._topo_ready(gid, hole) else "pending",
                        "garmin": "skipped" if not source else (
                            "done" if self._raster_ready(gid, hole, str(source)) else "pending"
                        ),
                        "assetVersion": str(source) if source else None,
                        "error": None,
                    }
                    tasks[key] = task
                else:
                    task["priority"] = min(int(task.get("priority", 20)), self._priority(gid, hole, recent, downloaded))
                    source_changed = task.get("assetVersion") != (str(source) if source else None)
                    if style_changed or force:
                        if task.get("topo") in {"done", "failed", "skipped"}:
                            task["topo"] = "pending"
                    if matte_changed or force or source_changed:
                        task["garmin"] = "skipped" if not source else "pending"
                    task["assetVersion"] = str(source) if source else None
                    if task.get("topo") == "pending" and self._topo_ready(gid, hole):
                        task["topo"] = "done"
                    if source and task.get("garmin") == "pending" and self._raster_ready(gid, hole, str(source)):
                        task["garmin"] = "done"
                    task["error"] = None if force or style_changed or matte_changed or source_changed else task.get("error")
            for key in list(tasks):
                if key not in seen:
                    tasks.pop(key, None)
            self._state["styleVersion"] = self.style_version
            self._state["matteVersion"] = self.matte_version
            self._save()
            return self.status()

    def _wait_for_foreground(self) -> None:
        deadline = time.monotonic() + _MAX_YIELD_SECONDS
        while True:
            try:
                busy = bool(self._should_yield())
            except Exception:
                return
            if not busy or time.monotonic() >= deadline:
                if busy:
                    logger.warning("render_backfill yield timeout; resuming low-priority work")
                return
            time.sleep(self._wait_seconds)

    def _next_task(self) -> tuple[str, dict[str, Any]] | None:
        candidates = []
        for key, task in self._state["tasks"].items():
            if task.get("topo") == "pending" or task.get("garmin") == "pending":
                candidates.append((int(task.get("priority", 20)), key, task))
        if not candidates:
            return None
        _priority, key, task = min(candidates, key=lambda item: item[:2])
        return key, task

    def run_once(self) -> bool:
        """Render one hole's pending units. Failed units are durable and never spin-retried."""
        with self._lock:
            selected = self._next_task()
            if selected is None:
                return False
            key, task = selected
            gid, hole = int(task["globalId"]), int(task["localHole"])
            unit = "topo" if task.get("topo") == "pending" else "garmin"
            self._wait_for_foreground()
            try:
                with work_priority(NEARBY):
                    if unit == "topo":
                        self._render_topo(gid, hole)
                    else:
                        version = str(task.get("assetVersion") or "")
                        if not version or not self._render_garmin(gid, hole, version):
                            raise RuntimeError("garmin source or matte unavailable")
                task[unit] = "done"
                task["error"] = None
                logger.info("render_backfill asset=ready gid=%s hole=%s kind=%s", gid, hole, unit)
            except Exception as exc:  # noqa: BLE001 - persist the failure and continue the queue
                task[unit] = "failed"
                task["error"] = f"{type(exc).__name__}: {exc}"[:500]
                logger.warning("render_backfill asset=failed gid=%s hole=%s kind=%s reason=%s", gid, hole, unit, task["error"])
            self._save()
            return True

    def run_to_completion(self) -> None:
        while self.run_once():
            pass

    def status(self) -> dict[str, Any]:
        with self._lock:
            tasks = deepcopy(self._state["tasks"])
            units = [task[field] for task in tasks.values() for field in ("topo", "garmin") if task.get(field) != "skipped"]
            return {
                "schema": _SCHEMA,
                "styleVersion": self._state.get("styleVersion") or self.style_version,
                "matteVersion": self._state.get("matteVersion") or self.matte_version,
                "total": len(units),
                "done": sum(value == "done" for value in units),
                "pending": sum(value == "pending" for value in units),
                "failed": sum(value == "failed" for value in units),
                "updatedAt": self._state.get("updatedAt"),
                "tasks": tasks,
            }


_BACKGROUND_LOCK = threading.Lock()
_BACKGROUND: RenderBackfill | None = None
_BACKGROUND_THREAD: threading.Thread | None = None


def start_background() -> RenderBackfill:
    """Scan and drain once after boot; the durable failed state prevents infinite retries."""
    global _BACKGROUND, _BACKGROUND_THREAD
    with _BACKGROUND_LOCK:
        if _BACKGROUND is None:
            _BACKGROUND = RenderBackfill()
        if _BACKGROUND_THREAD is None or not _BACKGROUND_THREAD.is_alive():
            def worker() -> None:
                try:
                    _BACKGROUND.enqueue_all(recent=_BACKGROUND._recent_holes())
                    _BACKGROUND.run_to_completion()
                except Exception:
                    logger.exception("render_backfill crashed")

            _BACKGROUND_THREAD = threading.Thread(target=worker, name="render-backfill", daemon=True)
            _BACKGROUND_THREAD.start()
        return _BACKGROUND


def status() -> dict[str, Any]:
    with _BACKGROUND_LOCK:
        return (_BACKGROUND or RenderBackfill()).status()


def enqueue_all(*, force: bool = False) -> dict[str, Any]:
    return start_background().enqueue_all(force=force)


def register_router(router: Any) -> None:
    """Attach the read-only admin status endpoint to an already-mounted server router."""
    @router.get("/api/v2/admin/render-backfill")
    def render_backfill_status() -> dict[str, Any]:
        return status()
