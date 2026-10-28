"""Durable map derivatives using the existing render pool, one background unit at a time.

Completed units are trusted until a renderer/source version changes or an explicit force scan.
Missing/corrupt files for a journaled ``done`` unit are repaired by the foreground cache path;
this worker deliberately does not revalidate all completed files on every boot.
"""
from __future__ import annotations

import atexit
from concurrent.futures import CancelledError, TimeoutError
from concurrent.futures import process as process_pool
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
import heapq
from io import BytesIO
import itertools
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable

from PIL import Image

from ai_caddie.core.data import MESH_DIR, ROOT
from ai_caddie.core.priority_work import BACKFILL, work_priority
from ai_caddie.geometry import garmin_raster, topo_render

logger = logging.getLogger(__name__)
_MESH_RE = re.compile(r"^gid(?P<gid>\d+)_h(?P<hole>\d+)_meshes\.json$")
_SCHEMA = "ai-caddie-render-backfill-v1"
_DEFAULT_STATE = ROOT / "data" / "render-backfill.json"
_STARTUP_YIELD_SECONDS = 30.0
FOREGROUND_QUIET_SECONDS = 10.0
NETWORK_RASTER_INTERVAL_SECONDS = 2.0
JOURNAL_BATCH_UNITS = 25
JOURNAL_INTERVAL_SECONDS = 10.0
RENDER_TIMEOUT_SECONDS = 180.0
RENDER_RETRY_BACKOFF_SECONDS = 5.0
RENDER_INTERRUPT_LIMIT = 3
WRITER_RETRY_SECONDS = 30.0
WRITER_RETRY_MAX_SECONDS = 600.0

_FOREGROUND_LOCK = threading.Lock()
_FOREGROUND_REQUESTS = 0
_LAST_FOREGROUND_FINISHED = float("-inf")


class _JournalWriterBusy(RuntimeError):
    """Another container still holds the durable writer lease."""


class _RetryRender(RuntimeError):
    """Infrastructure interruption; the map unit remains pending."""


class _RenderTimedOut(RuntimeError):
    """An old child may still be running; never submit this unit again automatically."""


class _ShutdownRender(RuntimeError):
    """A shutdown cancellation preserves the unit's interruption budget."""


def foreground_request_started(path: str) -> bool:
    """Track only map-heavy HTTP requests; status polling must not starve the worker."""
    relevant = (path.endswith(("/package", "/topo.png", "/green.png", "/garmin-raster",
                               "/garmin-raster.jpg", "/garmin-raster.webp")))
    if relevant:
        global _FOREGROUND_REQUESTS
        with _FOREGROUND_LOCK:
            _FOREGROUND_REQUESTS += 1
    return relevant


def foreground_request_finished() -> None:
    global _FOREGROUND_REQUESTS, _LAST_FOREGROUND_FINISHED
    with _FOREGROUND_LOCK:
        _FOREGROUND_REQUESTS -= 1
        _LAST_FOREGROUND_FINISHED = time.monotonic()


def _foreground_busy() -> bool:
    from server_v2 import map_startup
    with _FOREGROUND_LOCK:
        busy = (_FOREGROUND_REQUESTS > 0 or
                time.monotonic() - _LAST_FOREGROUND_FINISHED < FOREGROUND_QUIET_SECONDS)
    return busy or map_startup.nearby_work_blocked() or map_startup.tee_requests_in_flight()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _key(gid: int, hole: int) -> str:
    return f"{int(gid)}:{int(hole)}"


def _default_topo_ready(gid: int, hole: int) -> bool:
    return topo_render.cache_path(gid, hole).is_file()


def _default_raster_ready(gid: int, hole: int, version: str) -> bool:
    return garmin_raster._matte_path(gid, hole, version).is_file()


def _mesh_rows(mesh_root: Path) -> list[tuple[int, int]]:
    return sorted({(int(match["gid"]), int(match["hole"]))
                   for path in mesh_root.glob("gid*_h*_meshes.json")
                   if (match := _MESH_RE.match(path.name)) and path.is_file()})


class RenderBackfill:
    """A single journal writer. Status never waits for IO, foreground gates or rendering.

    Call ``close`` at a manual checkpoint; normal drains flush and release the journal lease.
    A crash replays durable unit events and accounts for unfinished pool submissions.
    """

    def __init__(self, *, state_path: Path | str | None = None,
                 mesh_root: Path | str | None = None, style_version: str | None = None,
                 matte_version: str | None = None,
                 topo_ready: Callable[[int, int], bool] | None = None,
                 raster_version: Callable[[int, int], str | None] | None = None,
                 raster_ready: Callable[[int, int, str], bool] | None = None,
                 render_topo: Callable[[int, int], Any] | None = None,
                 render_garmin: Callable[[int, int, str], Any] | None = None,
                 should_yield: Callable[[], bool] | None = None,
                 wait_seconds: float = .25) -> None:
        self.state_path = Path(state_path or os.environ.get("AI_CADDIE_RENDER_BACKFILL_STATE", _DEFAULT_STATE))
        self._events_path = self.state_path.with_suffix(self.state_path.suffix + ".events.jsonl")
        self.mesh_root = Path(mesh_root or MESH_DIR)
        self.style_version = str(style_version or topo_render.STYLE_VERSION)
        self.matte_version = str(matte_version or garmin_raster.RASTER_MATTE_VERSION)
        self._topo_ready = topo_ready or _default_topo_ready
        self._raster_version = raster_version
        self._raster_ready = raster_ready or _default_raster_ready
        self._render_topo = render_topo or self._default_render_topo
        self._render_garmin = render_garmin or self._default_render_garmin
        self._should_yield = should_yield
        self._wait_seconds = max(0.0, float(wait_seconds))
        self._lock = threading.RLock()
        self._unit_lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._lease = None
        self._dirty = 0
        self._last_saved = time.monotonic()
        self._last_network = float("-inf")
        self._queue_order = itertools.count()
        self._current_unit: tuple[str, str] | None = None
        self._stopping = threading.Event()
        self._writer_state = "idle"
        self._writer_error: str | None = None
        self._state = self._load()
        self._queue: list[tuple[int, int, str, str]] = []
        self._counts: dict[str, int] = {}
        self._failures: dict[tuple[str, str], dict[str, Any]] = {}
        self._index_state()

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            payload = {}
        if not isinstance(payload, dict) or payload.get("schema") != _SCHEMA:
            payload = {}
        tasks = payload.get("tasks") if isinstance(payload.get("tasks"), dict) else {}
        state = {"schema": _SCHEMA, "styleVersion": str(payload.get("styleVersion") or ""),
                 "matteVersion": str(payload.get("matteVersion") or ""),
                 "updatedAt": str(payload.get("updatedAt") or ""), "tasks": tasks,
                 "journalSequence": int(payload.get("journalSequence") or 0)}
        # The small write-ahead log makes submission intent durable without rewriting every
        # hole on every attempt. A snapshot sequence makes checkpoint + log truncation crash safe.
        try:
            with self._events_path.open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.endswith("\n"):
                        break
                    try:
                        event = json.loads(line)
                        if int(event["sequence"]) <= state["journalSequence"]:
                            continue
                        key = event["key"]
                        if key in tasks and event["unit"] in ("topo", "garmin"):
                            tasks[key] = self._apply_unit_event(tasks[key], event)
                        state["journalSequence"] = int(event["sequence"])
                    except (KeyError, ValueError, TypeError):
                        continue
        except OSError:
            pass
        return state

    @staticmethod
    def _apply_unit_event(task: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        unit = event["unit"]
        errors = dict(task.get("errors") or {})
        if event.get("error"):
            errors[unit] = event["error"]
        else:
            errors.pop(unit, None)
        return dict(task, **{unit: event["state"], "errors": errors,
                             "interrupts": dict(task.get("interrupts") or {}, **{unit: event["interrupts"]}),
                             "submitted": dict(task.get("submitted") or {}, **{unit: event["submitted"]})})

    def _record_unit(self, key: str, unit: str, *, state: str = "pending", interrupts: int = 0,
                     submitted: bool = False, error: str | None = None) -> None:
        """Append and fsync before a pool submit or acknowledging a completed attempt."""
        with self._io_lock:
            with self._lock:
                task = self._state["tasks"][key]
                sequence = self._state["journalSequence"] + 1
                event = dict(sequence=sequence, key=key, unit=unit, state=state,
                             interrupts=interrupts, submitted=submitted, error=error)
                updated = self._apply_unit_event(task, event)
                if task[unit] != state:
                    self._counts[task[unit]] -= 1
                    self._counts[state] += 1
                if state == "failed":
                    self._failures[key, unit] = dict(globalId=task["globalId"], localHole=task["localHole"],
                                                     unit=unit, error=error)
                else:
                    self._failures.pop((key, unit), None)
                self._state["tasks"][key] = updated
                self._state["journalSequence"] = sequence
                if not submitted:
                    self._dirty += 1
            with self._events_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

    def _recover_submissions(self) -> None:
        for key, task in list(self._state["tasks"].items()):
            for unit in ("topo", "garmin"):
                if task.get(unit) != "pending" or not task.get("submitted", {}).get(unit):
                    continue
                count = int(task.get("interrupts", {}).get(unit, 0)) + 1
                failed = count >= RENDER_INTERRUPT_LIMIT
                event = dict(unit=unit, state="failed" if failed else "pending", submitted=False,
                             interrupts=0 if failed else count,
                             error=f"render interrupted {count}x: unfinished submission after restart" if failed else None)
                task = self._apply_unit_event(task, event)
                self._state["tasks"][key] = task
                self._dirty += 1

    def _acquire_writer(self) -> None:
        if self._lease is not None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        lease = self.state_path.with_suffix(self.state_path.suffix + ".lock").open("a+")
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lease.close()
            raise _JournalWriterBusy("render backfill journal already has a writer") from exc
        self._lease = lease
        # Another service may have drained the journal since this object was created.
        state = self._load()
        with self._lock:
            self._state = state
            self._recover_submissions()
            if self._events_path.exists():
                self._dirty += 1
            self._index_state()
        self._save(force=True)

    def _wait_for_writer(self) -> None:
        """Allow the previous container to finish without delaying HTTP/status requests."""
        with self._unit_lock:
            with self._lock:
                self._writer_state, self._writer_error = "waiting", None
            deadline = time.monotonic() + WRITER_RETRY_MAX_SECONDS
            while True:
                try:
                    self._acquire_writer()
                    with self._lock:
                        self._writer_state = "running"
                    return
                except _JournalWriterBusy:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise
                    time.sleep(min(WRITER_RETRY_SECONDS, remaining))

    def _save(self, *, force: bool = False) -> None:
        with self._io_lock:
            if self._lease is None:
                return
            with self._lock:
                if not self._dirty or (not force and self._dirty < JOURNAL_BATCH_UNITS and
                                      time.monotonic() - self._last_saved < JOURNAL_INTERVAL_SECONDS):
                    return
                stamp = _now()
                snapshot = dict(self._state, updatedAt=stamp, tasks=dict(self._state["tasks"]))
                dirty = self._dirty
            # Task dictionaries are replaced, never mutated after publication. JSON and disk IO
            # stay outside the status lock, including on a 10k-hole journal.
            temporary = self.state_path.with_name(f".{self.state_path.name}.{os.getpid()}.tmp")
            try:
                with temporary.open("w", encoding="utf-8") as stream:
                    stream.write(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.state_path)
                descriptor = os.open(self.state_path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                    self._events_path.write_text("")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            finally:
                temporary.unlink(missing_ok=True)
            with self._lock:
                self._state["updatedAt"] = stamp
                self._dirty -= dirty
                self._last_saved = time.monotonic()

    def close(self) -> None:
        with self._unit_lock:
            try:
                self._save(force=True)
            finally:
                with self._io_lock:
                    if self._lease is not None:
                        fcntl.flock(self._lease, fcntl.LOCK_UN)
                        self._lease.close()
                        self._lease = None
                with self._lock:
                    if self._writer_state == "running":
                        self._writer_state = "idle"

    @staticmethod
    def _default_should_yield() -> bool:
        from server_v2 import map_startup
        return _foreground_busy() or map_startup.startup_in_flight()

    def _wait_for_foreground(self) -> None:
        from server_v2 import map_startup
        deadline = time.monotonic() + _STARTUP_YIELD_SECONDS
        while True:
            if self._stopping.is_set():
                return
            if self._should_yield is not None:
                busy = self._should_yield()
            else:
                # Only abandoned startup preparation has a deadline. Active rounds, tee work
                # and real HTTP requests can pause the whole backfill for as long as necessary.
                busy = _foreground_busy() or (time.monotonic() < deadline and map_startup.startup_in_flight())
            if not busy:
                return
            self._save()  # flush a partial batch even during a long foreground pause
            time.sleep(self._wait_seconds)

    def _default_render_topo(self, gid: int, hole: int) -> bytes:
        # Never allow the shared renderer's disabled/broken-pool fallback to run CPU work in
        # the API process. Production enables this pool through the existing start script.
        path = topo_render.cache_path(gid, hole)
        if cached := topo_render._read_cached_topo(path):
            return cached
        processes = topo_render._render_process_count()
        if not processes:
            raise RuntimeError("background rendering requires the existing render process pool")
        with self._render_slot():
            # Register only after foreground admission: registering before waiting for active
            # requests would deadlock a foreground follower against its own background leader.
            with topo_render._cache_lock:
                if cached := topo_render._read_cached_topo(path):
                    return cached
                waiter = topo_render._cache_inflight.get(path)
                leader = waiter is None
                if leader:
                    waiter = threading.Event()
                    topo_render._cache_inflight[path] = waiter
            if leader:
                try:
                    png = self._render_in_pool(processes, topo_render._render_in_worker, gid, hole)
                    topo_render._write_cached_topo(path, png)
                    return png
                finally:
                    with topo_render._cache_lock:
                        if topo_render._cache_inflight.get(path) is waiter:
                            topo_render._cache_inflight.pop(path, None)
                        waiter.set()
        # A foreground leader already owns this path. Release our render slot while following.
        if waiter.wait(timeout=RENDER_TIMEOUT_SECONDS):
            if cached := topo_render._read_cached_topo(path):
                return cached
        raise _RenderTimedOut("foreground topo leader unavailable after 180s")

    def _render_in_pool(self, processes: int, fn: Callable, *args: Any) -> bytes:
        key, unit = self._current_unit
        count = int(self._state["tasks"][key].get("interrupts", {}).get(unit, 0))
        self._record_unit(key, unit, interrupts=count, submitted=True)
        if self._stopping.is_set():
            raise _ShutdownRender("service stopping before render submission")
        pool, submitting = None, True
        try:
            pool = topo_render._get_render_pool(processes)
            future = pool.submit(fn, *args)
            submitting = False
            return future.result(timeout=RENDER_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            if pool is not None:
                topo_render._discard_render_pool(pool)
            raise _RenderTimedOut(f"render timed out after {RENDER_TIMEOUT_SECONDS:g}s") from exc
        except CancelledError as exc:
            if pool is not None:
                topo_render._discard_render_pool(pool)
            if self._stopping.is_set() or process_pool._global_shutdown:
                raise _ShutdownRender("render cancelled during shutdown") from exc
            raise _RetryRender(type(exc).__name__) from exc
        except BrokenProcessPool as exc:
            if pool is not None:
                topo_render._discard_render_pool(pool)
            raise _RetryRender(type(exc).__name__) from exc
        except RuntimeError as exc:
            if not submitting:
                raise
            if pool is not None:
                topo_render._discard_render_pool(pool)
            raise _RetryRender(type(exc).__name__) from exc

    @contextmanager
    def _render_slot(self):
        while True:
            self._wait_for_foreground()
            if self._stopping.is_set():
                raise _ShutdownRender("service stopping before render admission")
            with topo_render._cold_render_slot:
                # Admission itself may have waited behind foreground work. Give the slot back
                # throughout a round/cooldown instead of reserving half the foreground capacity.
                busy = self._should_yield() if self._should_yield is not None else _foreground_busy()
                if busy:
                    continue
                yield
                return

    def _default_render_garmin(self, gid: int, hole: int, version: str) -> bool:
        path = garmin_raster._matte_path(gid, hole, version)
        if path.is_file():
            return True
        processes = topo_render._render_process_count()
        if not processes:
            raise RuntimeError("background matting requires the existing render process pool")
        source_path = garmin_raster._raster_path(gid, hole, version)
        source = None
        if source_path.is_file():
            try:
                source = source_path.read_bytes()
                with Image.open(BytesIO(source)) as decoded:
                    decoded.verify()
            except Exception:
                source_path.unlink(missing_ok=True)
                source = None
        if source is None:
            # Resolve only the cached release; never refresh release authority in backfill.
            info = garmin_raster.courseview_release_info(gid, allow_fetch=False) or {}
            row = next((r for r in info.get("holes", []) if int(r.get("hole", 0)) == hole), None)
            if not row or not row.get("raster_url"):
                raise RuntimeError("garmin download failed: source URL unavailable")
            while time.monotonic() - self._last_network < NETWORK_RASTER_INTERVAL_SECONDS:
                self._save()
                time.sleep(self._wait_seconds)
            self._wait_for_foreground()
            self._last_network = time.monotonic()
            reasons: list[str] = []
            source = garmin_raster.fetch_raster(gid, dict(row, geometryAssetVersion=version), on_error=reasons.append)
            if not source:
                reason = reasons[-1] if reasons else "source unavailable"
                raise RuntimeError(f"garmin download failed: {reason}")
        if not source:
            raise RuntimeError("garmin download failed: empty local JPEG")
        try:
            with self._render_slot():
                data = self._render_in_pool(processes, garmin_raster.matte_sky_webp, source)
        except (_RetryRender, _ShutdownRender, _RenderTimedOut):
            raise
        except Exception as exc:
            raise RuntimeError(f"garmin matte failed: {type(exc).__name__}") from exc
        if not data:
            raise RuntimeError("garmin matte failed: empty output")
        # No registration and no cache lock held across a pool wait: foreground requests remain
        # free to read/use their normal cache path. Each writer has a distinct atomic temporary.
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.backfill.tmp")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return True

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

    def _sources(self, rows: list[tuple[int, int]]) -> dict[tuple[int, int], str | None]:
        if self._raster_version is not None:
            return {(gid, hole): self._raster_version(gid, hole) for gid, hole in rows}
        sources = {}
        grouped: dict[int, list[int]] = {}
        for gid, hole in rows:
            grouped.setdefault(gid, []).append(hole)
        for gid, holes in grouped.items():
            self._wait_for_foreground()
            info = garmin_raster.courseview_release_info(gid, allow_fetch=False) or {}
            by_hole = {int(row.get("hole", 0)): row for row in info.get("holes", [])}
            for hole in holes:
                row = by_hole.get(hole)
                version = garmin_raster._geometry_asset_version(info, row, hole) if row else None
                local = version and garmin_raster._raster_path(gid, hole, version).is_file()
                sources[gid, hole] = version if row and (row.get("raster_url") or local) else None
        return sources

    def _index_state(self) -> None:
        self._counts = {"total": 0, "done": 0, "pending": 0, "failed": 0}
        self._failures = {}
        for key, task in self._state["tasks"].items():
            for unit in ("topo", "garmin"):
                value = task.get(unit)
                if value in ("done", "pending", "failed"):
                    self._counts["total"] += 1
                    self._counts[value] += 1
                if value == "failed":
                    self._failures[key, unit] = {"globalId": task["globalId"], "localHole": task["localHole"],
                                                 "unit": unit, "error": task.get("errors", {}).get(unit) or task.get("error")}

    def enqueue_all(self, *, recent: set[tuple[int, int]] | None = None,
                    downloaded: set[tuple[int, int]] | None = None, force: bool = False) -> dict[str, Any]:
        """Scan outside the status lock; only the process-owned worker may mutate the queue."""
        with self._unit_lock:
            self._acquire_writer()
            recent = recent or set()
            downloaded = self._downloaded_holes() if downloaded is None else downloaded
            rows = _mesh_rows(self.mesh_root)
            sources = self._sources(rows)
            with self._lock:
                old = self._state
            style_changed = bool(old["styleVersion"]) and old["styleVersion"] != self.style_version
            matte_changed = bool(old["matteVersion"]) and old["matteVersion"] != self.matte_version
            tasks, queue = {}, []
            for gid, hole in rows:
                self._wait_for_foreground()
                key, source = _key(gid, hole), sources[gid, hole]
                previous = old["tasks"].get(key, {})
                task = dict(previous, globalId=gid, localHole=hole,
                            priority=self._priority(gid, hole, recent, downloaded), assetVersion=source)
                errors = dict(previous.get("errors") or {})
                interrupts = dict(previous.get("interrupts") or {})
                submitted = dict(previous.get("submitted") or {})
                for unit, changed, ready in (
                    ("topo", style_changed, lambda: self._topo_ready(gid, hole)),
                    ("garmin", matte_changed or previous.get("assetVersion") != source,
                     lambda: bool(source) and self._raster_ready(gid, hole, source)),
                ):
                    if not previous or force or changed or (unit == "garmin" and not source):
                        task[unit] = ("skipped" if unit == "garmin" and not source else
                                      "done" if ready() else "pending")
                        errors.pop(unit, None)
                        interrupts[unit], submitted[unit] = 0, False
                    elif task.get(unit) == "pending" and ready():
                        task[unit] = "done"
                        errors.pop(unit, None)
                    if task.get(unit) != "pending":
                        interrupts[unit], submitted[unit] = 0, False
                    else:
                        interrupts.setdefault(unit, 0)
                        submitted.setdefault(unit, False)
                    # Migrate the old shared error field to each failed unit.
                    if task.get(unit) == "failed" and previous.get("error"):
                        errors.setdefault(unit, previous["error"])
                    if task.get(unit) == "pending":
                        network = int(unit == "garmin" and not garmin_raster._raster_path(gid, hole, source).is_file())
                        queue.append((task["priority"], network, key, unit))
                task.pop("error", None)
                task["errors"] = errors
                task["interrupts"], task["submitted"] = interrupts, submitted
                tasks[key] = task
            # Initial JPEG preference is retained. Retries get a fresh order within their
            # priority tier, so a broken cached unit cannot starve network-backed peers.
            queue = [(priority, next(self._queue_order), key, unit)
                     for priority, _network, key, unit in sorted(queue)]
            heapq.heapify(queue)
            with self._lock:
                self._state = dict(old, styleVersion=self.style_version, matteVersion=self.matte_version, tasks=tasks)
                self._queue = queue
                self._dirty += 1
                self._index_state()
            self._save(force=True)
        return self.status()

    def run_once(self) -> bool:
        """Run one asset with at most one pool slot; status locks never cover waits/rendering."""
        with self._unit_lock:
            if self._stopping.is_set():
                return False
            self._acquire_writer()
            self._wait_for_foreground()
            if self._stopping.is_set():
                return False
            with self._lock:
                if not self._queue:
                    return False
                selected = heapq.heappop(self._queue)
                priority, _order, key, unit = selected
                task = self._state["tasks"][key]
                self._current_unit = (key, unit)
            error = None
            try:
                with work_priority(BACKFILL):
                    if unit == "topo":
                        self._render_topo(task["globalId"], task["localHole"])
                    elif not self._render_garmin(task["globalId"], task["localHole"], task["assetVersion"]):
                        raise RuntimeError("garmin source or matte unavailable")
            except _RetryRender as exc:
                count = int(self._state["tasks"][key].get("interrupts", {}).get(unit, 0)) + 1
                if count < RENDER_INTERRUPT_LIMIT:
                    self._record_unit(key, unit, interrupts=count)
                    with self._lock:
                        heapq.heappush(self._queue, (priority, next(self._queue_order), key, unit))
                    logger.warning("render_backfill retry gid=%s hole=%s kind=%s interrupted=%s reason=%s",
                                   task["globalId"], task["localHole"], unit, count, exc)
                    self._save()
                    time.sleep(RENDER_RETRY_BACKOFF_SECONDS)
                    return True
                error = f"render interrupted {count}x: {exc}"
                logger.warning("render_backfill asset=failed gid=%s hole=%s kind=%s reason=%s",
                               task["globalId"], task["localHole"], unit, error)
            except _ShutdownRender:
                count = int(self._state["tasks"][key].get("interrupts", {}).get(unit, 0))
                self._record_unit(key, unit, interrupts=count)
                with self._lock:
                    heapq.heappush(self._queue, (priority, next(self._queue_order), key, unit))
                self._stopping.set()
                return False
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"[:500]
                logger.warning("render_backfill asset=failed gid=%s hole=%s kind=%s reason=%s",
                               task["globalId"], task["localHole"], unit, error)
            finally:
                self._current_unit = None
            self._record_unit(key, unit, state="failed" if error else "done", error=error)
            self._save()
            return True

    def run_to_completion(self) -> None:
        try:
            while self.run_once():
                pass
        finally:
            self.close()

    def status(self, *, detail: bool = False) -> dict[str, Any]:
        with self._lock:
            result = {"schema": _SCHEMA, "styleVersion": self._state["styleVersion"] or self.style_version,
                      "matteVersion": self._state["matteVersion"] or self.matte_version,
                      **self._counts, "updatedAt": self._state["updatedAt"],
                      "writerState": self._writer_state, "lastError": self._writer_error,
                      "failures": [dict(row) for _, row in zip(range(50), self._failures.values())]}
            if detail:
                result["tasks"] = {key: dict(task, errors=dict(task.get("errors") or {}),
                                             interrupts=dict(task.get("interrupts") or {}),
                                             submitted=dict(task.get("submitted") or {}))
                                   for key, task in self._state["tasks"].items()}
            return result


_BACKGROUND_LOCK = threading.Lock()
_BACKGROUND: RenderBackfill | None = None
_BACKGROUND_THREAD: threading.Thread | None = None
_RESCAN = False
_FORCE = False


def _automatic_enabled() -> bool:
    truthy = {"1", "true", "yes", "on"}
    return (os.environ.get("AI_CADDIE_DATA_MODE", "").lower() != "fixture" and
            os.environ.get("AI_CADDIE_FIXTURE_MODE", "").lower() not in truthy and
            os.environ.get("AI_CADDIE_TEST_MODE", "").lower() not in truthy)


def start_background(*, force: bool = False, manual: bool = False) -> RenderBackfill | None:
    """Boot/retrigger the sole writer; fixture startup does not even construct a worker."""
    if not manual and not _automatic_enabled():
        return None
    global _BACKGROUND, _BACKGROUND_THREAD, _RESCAN, _FORCE
    with _BACKGROUND_LOCK:
        if _BACKGROUND is None:
            _BACKGROUND = RenderBackfill()
        _RESCAN = True
        _FORCE = _FORCE or force
        if _BACKGROUND_THREAD is None:
            _BACKGROUND._stopping.clear()
            def worker() -> None:
                global _BACKGROUND_THREAD, _RESCAN, _FORCE
                try:
                    while True:
                        with _BACKGROUND_LOCK:
                            retry = _FORCE
                            _RESCAN, _FORCE = False, False
                        _BACKGROUND._wait_for_writer()
                        _BACKGROUND.enqueue_all(recent=_BACKGROUND._recent_holes(), force=retry)
                        _BACKGROUND.run_to_completion()
                        with _BACKGROUND_LOCK:
                            if not _RESCAN:
                                _BACKGROUND_THREAD = None
                                return
                except _JournalWriterBusy:
                    message = f"journal writer unavailable after {WRITER_RETRY_MAX_SECONDS:g}s; scan request not started"
                    logger.warning("render_backfill %s", message)
                    _BACKGROUND.close()
                    with _BACKGROUND_LOCK:
                        with _BACKGROUND._lock:
                            _BACKGROUND._writer_state, _BACKGROUND._writer_error = "blocked", message
                        _RESCAN, _FORCE = False, False
                        _BACKGROUND_THREAD = None
                except Exception:
                    logger.exception("render_backfill crashed")
                    _BACKGROUND.close()
                    with _BACKGROUND_LOCK:
                        _BACKGROUND_THREAD = None
            _BACKGROUND_THREAD = threading.Thread(target=worker, name="render-backfill", daemon=True)
            _BACKGROUND_THREAD.start()
        return _BACKGROUND


def status(*, detail: bool = False) -> dict[str, Any]:
    with _BACKGROUND_LOCK:
        worker = _BACKGROUND
    # A status-only process never takes the journal lease or creates files.
    return (worker or RenderBackfill()).status(detail=detail)


def enqueue_all(*, force: bool = False) -> dict[str, Any]:
    worker = start_background(force=force, manual=True)
    return {"queued": True, **worker.status()}


def stop_background() -> None:
    """Signal API shutdown without waiting for a running child or taking the unit lock."""
    with _BACKGROUND_LOCK:
        if _BACKGROUND is not None:
            _BACKGROUND._stopping.set()


@atexit.register
def _flush_background() -> None:
    if _BACKGROUND is not None:
        _BACKGROUND._stopping.set()
        _BACKGROUND._save(force=True)


def register_router(router: Any) -> None:
    """Mount on admin_router; the existing global admin middleware supplies authentication."""
    @router.get("/render-backfill")
    def render_backfill_status(detail: bool = False) -> dict[str, Any]:
        return status(detail=detail)

    @router.post("/render-backfill", status_code=202)
    def render_backfill_enqueue(force: bool = True) -> dict[str, Any]:
        return enqueue_all(force=force)
