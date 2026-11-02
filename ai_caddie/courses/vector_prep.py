"""Release-bound persistent factual vectors, shared across players and API restarts."""

from __future__ import annotations

from contextlib import nullcontext
from concurrent.futures import Future
import copy
import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from uuid import uuid4

from ai_caddie.core.data import ROOT
from ai_caddie.courses import course_prep, prep_cache
from ai_caddie.geometry.geometry_evidence import geometry_coverage_for_hole
from ai_caddie.core.priority_work import PriorityExecutor

logger = logging.getLogger(__name__)
_CACHE_DIR = ROOT / "output" / "vector-prep"
_VERSION = "vector-prep-v1"
_LOCKS = [threading.Lock() for _ in range(32)]
_REQUESTED_TEES: dict[tuple[str, int, int], set[int]] = {}
_REQUESTED_TEES_LOCK = threading.Lock()
# Selected-Tee supplements use a separate one-worker lane. The shared geometry install pool is
# reserved for foreground hole preparation; a vector job may wait for the background slot without
# occupying either of those workers.
_BACKGROUND_VECTOR_POOL = PriorityExecutor(max_workers=1, name="selected-tee-vector-background")
_VECTOR_FUTURES: dict[tuple[str, int, int, int], Future] = {}
_VECTOR_FUTURES_LOCK = threading.Lock()
# A failed selected-Tee build must not be restarted by every 30-second map poll. Keep the
# backoff in memory alongside the single-flight table; a changed geometry revision creates a new
# attempt budget because it may have fixed the source data that caused the previous failures.
_VECTOR_RETRY_LIMIT = 3
_VECTOR_RETRY_BASE_SECONDS = 30.0
_VECTOR_RETRY_STATE: dict[tuple[str, int, int, int], dict[str, object]] = {}


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
    from ai_caddie.geometry.topo_render import _run_render_cpu

    return _run_render_cpu(
        course_prep.precise_route_seed_hole,
        int(global_id),
        int(local_hole),
        par_record=par_record,
        coverage=coverage,
        tee_set=tee_set,
        include_facts=include_facts,
    )


def request_vector_tee(global_id: int, local_hole: int, tee_set: int | None) -> None:
    """Remember requested variants until the asynchronous supplements finish."""
    if tee_set is None:
        return
    with _REQUESTED_TEES_LOCK:
        key = (str(_CACHE_DIR), int(global_id), int(local_hole))
        if key not in _REQUESTED_TEES and len(_REQUESTED_TEES) >= 2048:
            _REQUESTED_TEES.pop(next(iter(_REQUESTED_TEES)))
        _REQUESTED_TEES.setdefault(key, set()).add(int(tee_set))


def _vector_revision(global_id: int, local_hole: int) -> str:
    try:
        evidence = geometry_coverage_for_hole(
            int(global_id), int(local_hole), require_current_authority=True, refresh_release=False,
        )
    except Exception:
        return ""
    return str(evidence.get("geometryRevision") or "") if isinstance(evidence, dict) else ""


def enqueue_vector_hole(
    global_id: int, local_hole: int, tee_set: int, *, revision: str | None = None,
) -> bool:
    """Queue a selected-Tee supplement; never build mesh facts on the package caller.

    Reuse the existing bounded work queue, foreground admission and CPU process pool. Keyed
    submission coalesces package retries while one physical hole/Tee is queued or running.
    """
    from ai_caddie.core.priority_work import SELECTED_COURSE, background_work

    request_vector_tee(global_id, local_hole, tee_set)

    key = (str(_CACHE_DIR), int(global_id), int(local_hole), int(tee_set))
    revision = _vector_revision(global_id, local_hole) if revision is None else str(revision)
    now = time.monotonic()
    with _VECTOR_FUTURES_LOCK:
        active = _VECTOR_FUTURES.get(key)
        if active is not None and not active.done():
            return False
        state = _VECTOR_RETRY_STATE.get(key)
        if state is None or state.get("revision") != revision:
            state = {"revision": revision, "failures": 0, "retryAfter": None, "unavailable": False}
            _VECTOR_RETRY_STATE[key] = state
        if bool(state.get("unavailable")):
            return False
        retry_after = state.get("retryAfter")
        if retry_after is not None and now < float(retry_after):
            return False

    def build():
        with background_work():
            return cached_vector_hole(
                global_id, local_hole, tee_set=tee_set, use_process_pool=True,
            )

    future = _BACKGROUND_VECTOR_POOL.submit_keyed(
        ("selected-tee-vector",) + key, build, priority=SELECTED_COURSE,
    )
    with _VECTOR_FUTURES_LOCK:
        _VECTOR_FUTURES[key] = future
    future.add_done_callback(
        lambda completed, key=key, revision=revision: _forget_vector_future(
            key, completed, revision,
        )
    )
    return True


def _forget_vector_future(
    key: tuple[str, int, int, int], completed: Future, revision: str,
) -> None:
    with _VECTOR_FUTURES_LOCK:
        if _VECTOR_FUTURES.get(key) is not completed:
            return
        _VECTOR_FUTURES.pop(key, None)
        state = _VECTOR_RETRY_STATE.get(key)
        if state is None or state.get("revision") != revision:
            return
        try:
            succeeded = completed.result() is not None
        except Exception:
            succeeded = False
        if succeeded:
            _VECTOR_RETRY_STATE.pop(key, None)
            return
        failures = int(state.get("failures") or 0) + 1
        state["failures"] = failures
        if failures >= _VECTOR_RETRY_LIMIT:
            state["unavailable"] = True
            state["retryAfter"] = None
        else:
            state["retryAfter"] = time.monotonic() + (
                _VECTOR_RETRY_BASE_SECONDS * (2 ** (failures - 1))
            )


def selected_vector_plan(global_id: int, local_hole: int) -> dict[str, object] | None:
    """Expose queued/running selected-Tee work to the package state classifier."""
    gid, hole, root = int(global_id), int(local_hole), str(_CACHE_DIR)
    with _VECTOR_FUTURES_LOCK:
        matching = [
            (key, future) for key, future in _VECTOR_FUTURES.items()
            if key[0] == root and key[1] == gid and key[2] == hole
        ]
        if any(not future.done() for _key, future in matching):
            return {"state": "in_flight", "retryAfterEpoch": None}
        now = time.monotonic()
        # Expired retries are not queued work: only a request selecting that Tee can
        # enqueue them again. An abandoned Tee must not keep a terminal selection pending.
        states = [
            state for key, state in _VECTOR_RETRY_STATE.items()
            if key[0] == root and key[1] == gid and key[2] == hole
            and (state.get("retryAfter") is None or float(state["retryAfter"]) > now)
        ]
        if not states:
            return None
        retry_after = [
            time.time() + max(0.0, float(state["retryAfter"]) - now)
            for state in states
            if state.get("retryAfter") is not None and not state.get("unavailable")
        ]
        if retry_after:
            return {"state": "scheduled", "retryAfterEpoch": min(retry_after)}
        if all(bool(state.get("unavailable")) for state in states):
            return {"state": "unavailable", "retryAfterEpoch": None}
    return None


def _register_hole_plan_provider() -> None:
    # Keep this domain module independent of the API at import time.
    from ai_caddie.caddie.mobile_live import add_hole_plan_provider

    add_hole_plan_provider(selected_vector_plan)


_register_hole_plan_provider()


def warm_requested_vectors(global_id: int, local_hole: int) -> None:
    cached_vector_hole(global_id, local_hole)
    with _REQUESTED_TEES_LOCK:
        tees = tuple(_REQUESTED_TEES.get((str(_CACHE_DIR), int(global_id), int(local_hole)), ()))
    for tee_set in tees:
        cached_vector_hole(global_id, local_hole, tee_set=tee_set)


def cached_map_vector_hole(global_id: int, local_hole: int, *, coverage: dict,
                           preferred_tee: int | None = None) -> dict | None:
    """Read existing variants in one directory pass, sharing one authority/signature lookup.

    Only callers stripping Tee-dependent facts may use this fallback. Do not probe every Tee
    in the release: a cold first package normally has no entries at all for this physical hole.
    """
    gid, hole = int(global_id), int(local_hole)
    revision = str(coverage.get("geometryRevision") or "")
    if coverage.get("coverage") != "ready" or not revision:
        return None
    paths = list((_CACHE_DIR / str(gid)).glob(f"h{hole:02d}-*.json"))
    if not paths:
        return None
    geometry_sig = prep_cache._requested_geometry_sig(gid, [hole])
    course_sig = prep_cache._course_data_sig(gid)
    candidates = []
    for path in paths:
        try:
            stored = json.loads(path.read_text())
            row = stored["hole"]
            tee_set = row.get("teeSet")
            signature = (_VERSION, revision, tee_set, geometry_sig, course_sig)
            token = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:32]
            if (stored.get("schema") == _VERSION and stored.get("geometryRevision") == revision
                    and path.name == f"h{hole:02d}-{token}.json"):
                candidates.append(row)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    if not candidates:
        return None
    # Do not reuse a row if authority changed while the batch was being read.
    if (prep_cache._requested_geometry_sig(gid, [hole]) != geometry_sig
            or prep_cache._course_data_sig(gid) != course_sig):
        return None
    return min(candidates, key=lambda row: (row.get("teeSet") != preferred_tee,
                                            str(row.get("teeSet"))))


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
