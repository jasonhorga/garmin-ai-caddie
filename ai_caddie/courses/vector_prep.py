"""Release-bound persistent factual vectors, shared across players and API restarts."""

from __future__ import annotations

from contextlib import nullcontext
import copy
import atexit
import hashlib
import json
import logging
import multiprocessing
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from uuid import uuid4

from ai_caddie.core.data import ROOT
from ai_caddie.courses import course_prep, prep_cache
from ai_caddie.geometry.geometry_evidence import geometry_coverage_for_hole

logger = logging.getLogger(__name__)
_CACHE_DIR = ROOT / "output" / "vector-prep"
_VERSION = "vector-prep-v1"
_LOCKS = [threading.Lock() for _ in range(32)]
_VECTOR_POOL: ProcessPoolExecutor | None = None
_VECTOR_POOL_LOCK = threading.Lock()
_VECTOR_TASKS_PER_PROCESS = 64


_REQUESTED_TEES: dict[tuple[str, int, int], set[int]] = {}
_REQUESTED_TEES_LOCK = threading.Lock()


def _vector_process_count() -> int:
    raw = os.environ.get("AI_CADDIE_VECTOR_PREP_PROCESSES", "").strip()
    try:
        if raw:
            return max(1, int(raw))
    except ValueError:
        pass
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text(encoding="ascii").split()[:2]
        cpus = (os.cpu_count() or 1) if quota == "max" else max(1, int(int(quota) / int(period)))
    except (OSError, ValueError, ZeroDivisionError):
        try:
            cpus = len(os.sched_getaffinity(0))
        except (AttributeError, OSError):
            cpus = os.cpu_count() or 1
    return max(1, cpus - 1)


def _get_vector_pool() -> ProcessPoolExecutor:
    """Return the bounded child pool used only by non-current package vector seeds."""
    global _VECTOR_POOL
    with _VECTOR_POOL_LOCK:
        if _VECTOR_POOL is None:
            methods = multiprocessing.get_all_start_methods()
            method = "forkserver" if "forkserver" in methods else "spawn"
            context = multiprocessing.get_context(method)
            if method == "forkserver":
                context.set_forkserver_preload(["ai_caddie.courses.course_prep"])
            _VECTOR_POOL = ProcessPoolExecutor(
                max_workers=_vector_process_count(),
                mp_context=context,
                max_tasks_per_child=_VECTOR_TASKS_PER_PROCESS,
            )
        return _VECTOR_POOL


def _shutdown_vector_pool() -> None:
    pool = _VECTOR_POOL
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


atexit.register(_shutdown_vector_pool)


def precise_route_seed_hole_in_process(
    global_id: int,
    local_hole: int,
    *,
    par_record=None,
    coverage: dict | None = None,
    tee_set: int | None = None,
    include_facts: bool = True,
) -> dict | None:
    """Build one factual vector outside the API interpreter's GIL."""
    future = _get_vector_pool().submit(
        course_prep.precise_route_seed_hole,
        int(global_id),
        int(local_hole),
        par_record=par_record,
        coverage=coverage,
        tee_set=tee_set,
        include_facts=include_facts,
    )
    return future.result()


def request_vector_tee(global_id: int, local_hole: int, tee_set: int | None) -> None:
    """Remember requested variants until the asynchronous supplements finish."""
    if tee_set is None:
        return
    with _REQUESTED_TEES_LOCK:
        key = (str(_CACHE_DIR), int(global_id), int(local_hole))
        if key not in _REQUESTED_TEES and len(_REQUESTED_TEES) >= 2048:
            _REQUESTED_TEES.pop(next(iter(_REQUESTED_TEES)))
        _REQUESTED_TEES.setdefault(key, set()).add(int(tee_set))


def warm_requested_vectors(global_id: int, local_hole: int) -> None:
    cached_vector_hole(global_id, local_hole)
    with _REQUESTED_TEES_LOCK:
        tees = tuple(_REQUESTED_TEES.get((str(_CACHE_DIR), int(global_id), int(local_hole)), ()))
    for tee_set in tees:
        cached_vector_hole(global_id, local_hole, tee_set=tee_set)


def cached_vector_hole(global_id: int, local_hole: int, *, tee_set: int | None = None,
                       coverage: dict | None = None, build_if_missing: bool = True,
                       use_process_pool: bool = False) -> dict | None:
    """No history, weather or rendering. A cache hit is still checked against current authority.

    Each Tee has its own playing route/distances, all in the same Tee-independent raster frame.
    Fingerprint both the physical hole and CourseView route authority; installing another hole
    never invalidates this one. Unknown/stale authority cannot promote a cached vector to ready.
    """
    gid, hole = int(global_id), int(local_hole)
    if tee_set is None:
        from ai_caddie.caddie.analysis import tee_set_for_box
        tee_set = tee_set_for_box(gid, "blue", colour_fallback=False)
    evidence = coverage if coverage is not None else geometry_coverage_for_hole(
        gid, hole, require_current_authority=True, refresh_release=False,
    )
    revision = str(evidence.get("geometryRevision") or "")
    if evidence.get("coverage") != "ready" or not revision:
        return None

    def signature():
        return (_VERSION, revision, tee_set,
                prep_cache._requested_geometry_sig(gid, [hole]), prep_cache._course_data_sig(gid))

    before = signature()
    token = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()[:32]
    path = _CACHE_DIR / str(gid) / f"h{hole:02d}-{token}.json"
    with (_LOCKS[hash((gid, hole, tee_set)) % len(_LOCKS)] if build_if_missing else nullcontext()):
        try:
            stored = json.loads(path.read_text())
            if stored.get("schema") == _VERSION and stored.get("geometryRevision") == revision:
                if signature() == before:
                    return copy.deepcopy(stored["hole"])
                return None
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        if not build_if_missing:
            return None
        if use_process_pool:
            row = precise_route_seed_hole_in_process(
                gid, hole, tee_set=tee_set, coverage=evidence, include_facts=True,
            )
        else:
            row = course_prep.precise_route_seed_hole(
                gid, hole, tee_set=tee_set, coverage=evidence, include_facts=True,
            )
        if row is None or signature() != before:
            return None
        # The prep stays partial until the personalized planner enriches it. Its physical geometry
        # revision is nevertheless authoritative and the full factual map is immediately drawable.
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps({"schema": _VERSION, "geometryRevision": revision, "hole": row},
                                           ensure_ascii=False, separators=(",", ":")))
            temporary.replace(path)
        except OSError:
            # Read-only/offline deployments can still return the freshly computed factual map.
            logger.warning("vector_prep cache_write_failed gid=%s hole=%s", gid, hole)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        return row
