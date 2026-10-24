"""Release-bound persistent factual vectors, shared across players and API restarts."""

from __future__ import annotations

from contextlib import nullcontext
import copy
import hashlib
import json
import logging
import threading
from pathlib import Path
from uuid import uuid4

from ai_caddie.core.data import ROOT
from ai_caddie.courses import course_prep, prep_cache
from ai_caddie.geometry.geometry_evidence import geometry_coverage_for_hole

logger = logging.getLogger(__name__)
_CACHE_DIR = ROOT / "output" / "vector-prep"
_VERSION = "vector-prep-v1"
_LOCKS = [threading.Lock() for _ in range(32)]


_REQUESTED_TEES: dict[tuple[int, int], set[int]] = {}
_REQUESTED_TEES_LOCK = threading.Lock()


def request_vector_tee(global_id: int, local_hole: int, tee_set: int | None) -> None:
    """Remember requested variants until the asynchronous supplements finish."""
    if tee_set is None:
        return
    with _REQUESTED_TEES_LOCK:
        key = (int(global_id), int(local_hole))
        if key not in _REQUESTED_TEES and len(_REQUESTED_TEES) >= 2048:
            _REQUESTED_TEES.pop(next(iter(_REQUESTED_TEES)))
        _REQUESTED_TEES.setdefault(key, set()).add(int(tee_set))


def warm_requested_vectors(global_id: int, local_hole: int) -> None:
    cached_vector_hole(global_id, local_hole)
    with _REQUESTED_TEES_LOCK:
        tees = tuple(_REQUESTED_TEES.get((int(global_id), int(local_hole)), ()))
    for tee_set in tees:
        cached_vector_hole(global_id, local_hole, tee_set=tee_set)


def cached_vector_hole(global_id: int, local_hole: int, *, tee_set: int | None = None,
                       coverage: dict | None = None, build_if_missing: bool = True) -> dict | None:
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
        row = course_prep.precise_route_seed_hole(gid, hole, tee_set=tee_set, coverage=evidence, include_facts=True)
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
