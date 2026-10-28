"""Durable, idempotent server-side course asset install jobs.

The mobile package endpoint used to attach a best-effort ``BackgroundTasks`` callback to the
request.  That was enough for a warm process, but a restart lost the work and the iOS client had to
guess by polling geometry coverage.  This module is deliberately small: one atomic JSON record per
selected course, a bounded worker, and no player data in the public status payload.  The heavy work
still lives in :mod:`server_v2.main` so the existing geometry/topo single-flight boundaries remain
the only execution authority.

The job tracks public geometry/topo preparation.  Player-specific prep facts are still installed and
verified by the iOS ``OfflineStore``; they are not written to this shared job journal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any

from ai_caddie.core.data import ROOT
from ai_caddie.core.priority_work import SELECTED_COURSE, PriorityExecutor

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_ACTIVE: set[str] = set()
_CURRENT_COURSE_IDS: set[int] = set()
_RESUME_BACKLOG: list[str] = []
# A transient Garmin authority outage must not turn a queued job into a hot loop.  Timers are
# deliberately process-local: the journal remains the durable source of truth, and a restart will
# perform one normal resume pass before applying the same bounded backoff again.
_RETRY_TIMERS: dict[str, threading.Timer] = {}
_RETRY_ATTEMPTS: dict[str, int] = {}
_DERIVATIVE_LOG_SIGNATURES: dict[str, dict[str, tuple]] = {}
# A persistent authority/provider outage should become an actionable failed row rather than
# consuming a worker forever. An explicit enqueue/retry resets this counter below.
_MAX_RETRY_ATTEMPTS = 8
_HEARTBEAT_INTERVAL_SECONDS = 5.0
_TERMINAL_PHASES = frozenset({"ready", "failed", "cancelled"})
# A hole's optional distance/obstacle exports run in the derivative lane after its mesh and topo
# are installed.  Until they are installed the job is not complete: ``derivatives`` on the row is
# ``queued`` (to be scheduled), ``running`` (in the lane) or ``retrying`` (failed, due at
# ``derivativesRetryAfterEpoch``).  A missing field is a settled/legacy row.
_DERIVATIVE_WAITING = frozenset({"queued", "running", "retrying"})
# Fallback re-check while an export is in flight; the lane's listener normally reports sooner.
# Each export has two subprocess stages bounded by 180 s.
_DERIVATIVE_POLL_SECONDS = 60.0
_MIN_DERIVATIVE_DELAY_SECONDS = 1.0
# A pass that yields for resources (nearby work during play) or for missing release metadata
# re-checks after this interval, exactly as the queued-work branch does for ``deferred``.
_DEFERRED_RETRY_SECONDS = 60.0
_DEFERRED_STAGES = frozenset({"deferred", "metadata"})
# hole key "gid:hole" -> job ids whose rows wait for that hole's exports (process-local; a restart
# rebuilds it from the journal on the next pass).
_DERIVATIVE_WAITERS: dict[str, set[str]] = {}
_DERIVATIVE_FIELDS = (
    "derivatives", "derivativesRetryAfterEpoch", "derivativesFailureCount", "derivativesLastErrorType",
)
# One job coordinator at a time keeps a four-core shared homeserver from multiplying the existing
# two-hole geometry pool and one-hole topo pipeline across simultaneous course selections.
_WORKER = PriorityExecutor(max_workers=1, name="course-install-job")


def set_current_course_ids(global_ids: set[int] | list[int] | tuple[int, ...]) -> None:
    """Update the live-play course set used when resuming durable install jobs."""
    with _LOCK:
        _CURRENT_COURSE_IDS.clear()
        for value in global_ids:
            try:
                gid = int(value)
            except (TypeError, ValueError):
                continue
            if gid > 0:
                _CURRENT_COURSE_IDS.add(gid)


def _root() -> Path:
    override = os.environ.get("AI_CADDIE_COURSE_INSTALL_DIR")
    return Path(override).expanduser() if override else ROOT / "data" / "course-installs"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _player_key(player_id: str) -> str:
    # The journal is local/private, but keeping the raw Apple/Garmin identity out of it makes
    # accidental log or backup exposure harmless.
    return hashlib.sha256(str(player_id).encode("utf-8")).hexdigest()[:16]


def job_id(
    *,
    global_id: int,
    tee_box: str,
    loop_key: str,
    player_id: str,
) -> str:
    # The ordered loop key (B4b-2) is the selection identity: 前→前, 前→后, 后→前 and 后→后 of
    # one 18-hole course, and every A/B/C pairing, each own a separate journal.
    raw = f"{int(global_id)}|loops:{loop_key.strip()}|{tee_box.strip().lower()}|{_player_key(player_id)}"
    return "course-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _path(identifier: str) -> Path:
    return _root() / f"{identifier}.json"


def _write(state: dict[str, Any]) -> None:
    path = _path(str(state["jobId"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    # ``heartbeatAt`` is durable evidence that a worker is still alive.  Keep it separate from
    # ``progress``: a provider can be slow for one hole without making the UI claim that work has
    # stopped.  Every journal write is a heartbeat, including terminal transitions.
    now = _now()
    state["heartbeatAt"] = now
    state["updatedAt"] = now
    if state.get("phase") in _TERMINAL_PHASES:
        # Every terminal transition goes through this durable write path.  Clear process-local
        # observability state and any stale wake-up epoch regardless of which caller reached it.
        identifier = str(state["jobId"])
        _DERIVATIVE_LOG_SIGNATURES.pop(identifier, None)
        state.pop("nextAttemptEpoch", None)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def _read(identifier: str) -> dict[str, Any] | None:
    try:
        value = json.loads(_path(identifier).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _normalise_revision(value: Any) -> str | None:
    revision = str(value or "").strip().lower()
    return revision or None


def _normalise_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for raw in refs:
        if not isinstance(raw, dict):
            continue
        gid = int(raw.get("globalId") or 0)
        hole = int(raw.get("localHole") or raw.get("hole") or 0)
        display = int(raw.get("displayHole") or raw.get("number") or hole)
        if gid <= 0 or hole <= 0:
            continue
        display_holes: list[int] = []
        raw_display_holes = raw.get("displayHoles")
        if isinstance(raw_display_holes, (list, tuple)):
            for raw_display in raw_display_holes:
                try:
                    parsed_display = int(raw_display)
                except (TypeError, ValueError):
                    continue
                if parsed_display > 0 and parsed_display not in display_holes:
                    display_holes.append(parsed_display)
        if display > 0 and display not in display_holes:
            display_holes.insert(0, display)
        key = (gid, hole)
        existing = by_key.get(key)
        if existing is not None:
            for display_hole in display_holes:
                if display_hole not in existing["displayHoles"]:
                    existing["displayHoles"].append(display_hole)
            continue
        row = {
            "globalId": gid,
            "localHole": hole,
            "displayHole": max(1, display),
            "displayHoles": display_holes or [max(1, display)],
            "geometryRevision": _normalise_revision(raw.get("geometryRevision")),
            "geometryAuthorityObservation": str(
                raw.get("geometryAuthorityObservation") or "unknown"
            ).strip().lower(),
        }
        by_key[key] = row
        result.append(row)
    return result


def _initial_state(
    *,
    identifier: str,
    global_id: int,
    tee_box: str,
    loop_key: str,
    player_id: str,
    refs: list[dict[str, Any]],
    requested: dict[int, list[int]],
    ready: dict[int, list[int]],
    priority_hole: int = 1,
) -> dict[str, Any]:
    holes = _normalise_refs(refs)
    requested_holes = {
        int(gid): {int(hole) for hole in holes}
        for gid, holes in requested.items()
    }
    ready_holes = {
        int(gid): {int(hole) for hole in holes}
        for gid, holes in ready.items()
    }
    return {
        "schema": "ai-caddie-course-install-v1",
        "jobId": identifier,
        "globalId": int(global_id),
        "teeBox": tee_box,
        "loopKey": loop_key,
        "playerKey": _player_key(player_id),
        "priorityHole": max(1, int(priority_hole or 1)),
        "phase": "queued",
        "stage": "queued",
        "progress": 0,
        "heartbeatAt": _now(),
        "cancelRequested": False,
        "cancelRequestedAt": None,
        "terminalReason": None,
        "retryCount": 0,
        "generation": 1,
        "cancellable": True,
        "totalHoles": len(holes),
        "geometryReady": 0,
        "topoReady": 0,
        "requested": {str(k): sorted({int(h) for h in v}) for k, v in requested.items()},
        "ready": {str(k): sorted({int(h) for h in v}) for k, v in ready.items()},
        "workRevision": 1,
        "holes": {
            f"{row['globalId']}:{row['localHole']}": {
                **row,
                "geometry": (
                    "ready"
                    if row["localHole"] in ready_holes.get(row["globalId"], set())
                    and row.get("geometryRevision")
                    else "queued"
                ),
                # A ready geometry file is not a ready install: the immutable topo bytes still
                # have to be rendered and made available to the client.  Keeping this explicit is
                # what prevents a package response from accidentally opening prep early.
                "topo": "queued",
                "topoRevision": None,
                "workRevision": 1,
            }
            for row in holes
        },
        "createdAt": _now(),
        "updatedAt": _now(),
        "error": None,
    }


def _geometry_ready(row: dict[str, Any]) -> bool:
    return row.get("geometry") == "ready" and bool(
        _normalise_revision(row.get("geometryRevision"))
    )


def _topo_ready(row: dict[str, Any]) -> bool:
    geometry_revision = _normalise_revision(row.get("geometryRevision"))
    return bool(
        geometry_revision
        and row.get("topo") == "ready"
        and _normalise_revision(row.get("topoRevision")) == geometry_revision
    )


def _recount(state: dict[str, Any]) -> None:
    rows = [row for row in state.get("holes", {}).values() if isinstance(row, dict)]
    state["totalHoles"] = len(rows)
    state["geometryReady"] = sum(_geometry_ready(row) for row in rows)
    state["topoReady"] = sum(_topo_ready(row) for row in rows)
    total_units = max(1, len(rows) * 2)
    completed_units = int(state["geometryReady"]) + int(state["topoReady"])
    computed = min(100, int(round(completed_units * 100 / total_units)))
    # Progress is monotonic inside a generation. A release rebind or explicit retry increments
    # ``generation`` and may intentionally reset it before new work starts.
    state["progress"] = max(0, min(100, max(int(state.get("progress") or 0), computed)))


def _derivatives_waiting(row: dict[str, Any]) -> bool:
    return str(row.get("derivatives") or "") in _DERIVATIVE_WAITING


def _all_assets_ready(state: dict[str, Any]) -> bool:
    rows = [row for row in (state.get("holes") or {}).values() if isinstance(row, dict)]
    return bool(rows) and all(
        _geometry_ready(row) and _topo_ready(row) and not _derivatives_waiting(row)
        for row in rows
    )


def _has_derivative_work(state: dict[str, Any]) -> bool:
    return any(
        _geometry_ready(row) and _derivatives_waiting(row)
        for row in (state.get("holes") or {}).values()
        if isinstance(row, dict)
    )


def _only_derivatives_remain(state: dict[str, Any]) -> bool:
    """A live job whose mesh/topo are all installed and only owes supplement exports."""
    rows = [row for row in (state.get("holes") or {}).values() if isinstance(row, dict)]
    return (
        state.get("phase") in {"queued", "running"}
        and not state.get("cancelRequested")
        and bool(rows)
        and all(_geometry_ready(row) and _topo_ready(row) for row in rows)
        and _has_derivative_work(state)
    )


def _derivative_delay(state: dict[str, Any]) -> float:
    """Seconds until the earliest derivative row is due (its persisted plan, never a guess).

    Never below ``_MIN_DERIVATIVE_DELAY_SECONDS``: a pass that cannot act on a due row (for
    example a deferred nearby pass) must not turn into a zero-delay timer loop.
    """
    rows = [
        row for row in (state.get("holes") or {}).values()
        if isinstance(row, dict) and _geometry_ready(row) and _derivatives_waiting(row)
    ]
    delay = _DERIVATIVE_POLL_SECONDS
    if any(row.get("derivatives") == "queued" for row in rows):
        delay = 0.0
    else:
        plans = []
        for row in rows:
            if row.get("derivatives") != "retrying":
                continue
            try:
                plans.append(float(row.get("derivativesRetryAfterEpoch")))
            except (TypeError, ValueError):
                plans.append(0.0)
        if plans:
            delay = max(0.0, min(plans) - time.time())
            if any(row.get("derivatives") == "running" for row in rows):
                delay = min(delay, _DERIVATIVE_POLL_SECONDS)
    return max(_MIN_DERIVATIVE_DELAY_SECONDS, delay)


def _apply_derivative_state(row: dict[str, Any], observed: dict[str, Any]) -> None:
    """Copy the derivative lane's durable observation onto a journal row."""
    state = str(observed.get("state") or "none")
    if state in {"ready", "none"}:
        # ``none``: the mesh itself is gone; the geometry flow owns that row again.
        for field in _DERIVATIVE_FIELDS:
            row.pop(field, None)
        if state == "ready":
            row["derivatives"] = "ready"
        return
    row["derivatives"] = {"due": "queued"}.get(state, state)
    row["derivativesRetryAfterEpoch"] = observed.get("retryAfterEpoch") if state == "retrying" else None
    row["derivativesFailureCount"] = int(observed.get("failureCount") or 0)
    row["derivativesLastErrorType"] = observed.get("lastErrorType")


def _register_derivative_waiter(identifier: str, key: str, waiting: bool) -> None:
    with _LOCK:
        if waiting:
            _DERIVATIVE_WAITERS.setdefault(key, set()).add(identifier)
        else:
            waiters = _DERIVATIVE_WAITERS.get(key)
            if waiters is not None:
                waiters.discard(identifier)
                if not waiters:
                    _DERIVATIVE_WAITERS.pop(key, None)


def reconcile_derivatives(identifier: str, *, schedule: bool = True) -> None:
    """Bring every installed row's supplement state into the journal.

    A row whose mesh is installed but whose exports are missing is waiting: due work is handed to
    the derivative lane (``schedule``), a failed attempt keeps its persisted due time and an
    in-flight attempt is observed.  Rows with no mesh on disk carry no derivative state.
    """
    from ai_caddie.geometry.geometry_sync import derivative_state, schedule_derivatives

    state = state_for_worker(identifier)
    if not state:
        return
    keys = [
        key for key, row in (state.get("holes") or {}).items()
        if isinstance(row, dict) and _geometry_ready(row)
    ]
    observed: dict[str, dict[str, Any]] = {}
    for key in keys:
        row = state["holes"][key]
        gid, hole = int(row.get("globalId") or 0), int(row.get("localHole") or 0)
        # Register before observing: an export settling in between must still find this job.
        _register_derivative_waiter(identifier, key, True)
        try:
            result = derivative_state(gid, hole)
            if schedule and result.get("state") == "due":
                result = schedule_derivatives(gid, hole)
                # A failed snapshot/read can leave the lane in ``due`` without creating a
                # worker.  Persist a bounded poll plan so the coordinator cannot spin at its
                # one-second minimum while repeatedly attempting the same impossible submission.
                if result.get("state") == "due":
                    result = {
                        **result,
                        "state": "retrying",
                        "retryAfterEpoch": time.time() + _DERIVATIVE_POLL_SECONDS,
                        "lastErrorType": "ScheduleUnavailable",
                    }
        except Exception:  # noqa: BLE001 - observation is best effort; keep the row as it is
            logger.exception("course_install stage=derivatives gid=%s hole=%s", gid, hole)
            continue
        observed[key] = result
    with _LOCK:
        current = _read(identifier)
        if not current:
            return
        for key, result in observed.items():
            row = (current.get("holes") or {}).get(key)
            if isinstance(row, dict):
                _apply_derivative_state(row, result)
        _recount(current)
        _write(current)
        settled = [
            key for key in observed
            if not _derivatives_waiting((current.get("holes") or {}).get(key) or {})
        ]
    for key in settled:
        _register_derivative_waiter(identifier, key, False)


def derivatives_settled(global_id: int, local_hole: int) -> None:
    """Derivative-lane listener: an export attempt for this hole recorded its result."""
    key = f"{int(global_id)}:{int(local_hole)}"
    with _LOCK:
        identifiers = sorted(_DERIVATIVE_WAITERS.get(key, ()))
    for identifier in identifiers:
        reconcile_derivatives(identifier, schedule=False)
        with _LOCK:
            state = _read(identifier)
            if not state or state.get("phase") in {"failed", "cancelled"} or identifier in _ACTIVE:
                continue
            # A derivative callback must not consume the geometry/provider retry budget.  If
            # another hole already owns a queued pass, leave its existing timer untouched.
            if _has_queued_work(state):
                if identifier not in _RETRY_TIMERS:
                    _launch(identifier)
                continue
            timer = _RETRY_TIMERS.pop(identifier, None)
            if timer is not None:
                timer.cancel()
            if _all_assets_ready(state):
                state["phase"] = "ready"
                state["stage"] = "complete"
                state["error"] = None
                state["cancellable"] = False
                state.pop("nextAttemptEpoch", None)
                _write(state)
                continue
            # Replace any poll timer with one due at the newly persisted plan.
        _schedule_retry(identifier)


def _has_queued_work(state: dict[str, Any]) -> bool:
    return any(
        row.get("geometry") == "queued"
        or (_geometry_ready(row) and row.get("topo") == "queued")
        for row in (state.get("holes") or {}).values()
        if isinstance(row, dict)
    )


def _public_error(value: Any) -> str | None:
    """Keep internal exception text (which may contain paths/provider details) off the API."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if "topo" in text:
        return "topo render failed"
    if "geometry" in text or "prodgeometry" in text:
        return "geometry download failed"
    if text in {"course has no holes", "course install incomplete", "asset unavailable"}:
        return text
    return "course install failed"


def _launch(identifier: str) -> None:
    with _LOCK:
        # An explicit enqueue/retry supersedes a pending delayed hand-off.  Timer callbacks remove
        # themselves before calling us, so cancelling here is harmless in that path as well.
        timer = _RETRY_TIMERS.pop(identifier, None)
        if timer is not None:
            timer.cancel()
        if identifier in _ACTIVE:
            return
        state = _read(identifier)
        if not state or state.get("phase") in _TERMINAL_PHASES or state.get("cancelRequested"):
            return
        _ACTIVE.add(identifier)
        # Startup recovery and generation retries reuse the persisted priority.  A job for a
        # different course must yield to live play even when its old row said foreground (10).
        try:
            gid = int(state.get("globalId") or 0)
        except (TypeError, ValueError):
            gid = 0
        if gid and gid not in _CURRENT_COURSE_IDS:
            state["priority"] = max(int(state.get("priority", SELECTED_COURSE)), 20)
            _write(state)
        launch_priority = int(state.get("priority", SELECTED_COURSE))
    _WORKER.submit(_run, identifier, priority=launch_priority)


def _schedule_retry(identifier: str) -> None:
    """Hand a queued job back to the coordinator after bounded exponential backoff.

    ``unknown`` authority is expected to recover (for example while a Garmin release sidecar is
    being atomically replaced), so it must remain queued rather than failed.  A timer keeps the
    single worker available for other courses and prevents a rapid status poll from consuming all
    CPU/IO.  At most one timer exists per job.
    """
    with _LOCK:
        state = _read(identifier)
        if (
            not state
            or state.get("phase") in _TERMINAL_PHASES
            or state.get("cancelRequested")
            or not (_has_queued_work(state) or _has_derivative_work(state))
            or identifier in _ACTIVE
        ):
            return
        if identifier in _RETRY_TIMERS:
            return
        if not _has_queued_work(state):
            # Only supplement exports remain.  Their backoff is owned and persisted by the
            # derivative lane (uncapped, at most six hours apart), so wake exactly at the next
            # persisted due time and never spend the provider-outage budget below.  A pass that
            # yielded without observing them (nearby work during play, missing metadata) keeps
            # the normal deferral cadence instead of re-running an overdue plan immediately.
            if state.get("stage") in _DEFERRED_STAGES:
                delay = _DEFERRED_RETRY_SECONDS
            else:
                delay = _derivative_delay(state)
            logged = _DERIVATIVE_LOG_SIGNATURES.get(identifier, {})
            current: dict[str, tuple] = {}
            for key, row in (state.get("holes") or {}).items():
                if isinstance(row, dict) and _geometry_ready(row) and _derivatives_waiting(row):
                    failures = int(row.get("derivativesFailureCount") or 0)
                    signature = (row.get("derivatives"), failures, row.get("derivativesRetryAfterEpoch"))
                    current[key] = signature
                    # INFO only when a hole's export state changes: a plan deferred while playing
                    # nearby re-runs every minute with nothing new to say.
                    logger.log(
                        logging.DEBUG if logged.get(key) == signature else logging.INFO,
                        "course_install stage=derivatives job=%s hole=%s state=%s failures=%s "
                        "retry_after_epoch=%s next_attempt_in_s=%.0f",
                        identifier, key, signature[0], failures, signature[2], delay,
                    )
            _DERIVATIVE_LOG_SIGNATURES[identifier] = current
            _arm_retry_timer(identifier, state, delay)
            return
        attempt = _RETRY_ATTEMPTS.get(identifier, 0)
        deferred = state.get("stage") == "deferred"
        if not deferred and attempt >= _MAX_RETRY_ATTEMPTS:
            for row in (state.get("holes") or {}).values():
                if not isinstance(row, dict):
                    continue
                if row.get("geometry") == "queued":
                    row["geometry"] = "failed"
                if row.get("topo") == "queued":
                    row["topo"] = "failed"
                if row.get("geometry") == "failed" or row.get("topo") == "failed":
                    row["error"] = "asset unavailable"
            state["phase"] = "failed"
            state["stage"] = "error"
            state["error"] = "asset unavailable"
            _recount(state)
            state["updatedAt"] = _now()
            _write(state)
            _RETRY_ATTEMPTS.pop(identifier, None)
            return
        if not deferred:
            _RETRY_ATTEMPTS[identifier] = attempt + 1
        delay = _DEFERRED_RETRY_SECONDS if deferred else min(60.0, float(2 ** attempt))
        _arm_retry_timer(identifier, state, delay)


def _arm_retry_timer(identifier: str, state: dict[str, Any], delay: float) -> None:
    """Start the job's single retry timer and persist when it is due (caller holds ``_LOCK``).

    ``nextAttemptEpoch`` lets a package read tell a client the real time the queued work will run
    again instead of a synthetic poll interval.
    """

    timer: threading.Timer | None = None

    def relaunch() -> None:
        with _LOCK:
            if _RETRY_TIMERS.get(identifier) is not timer:
                return
            _RETRY_TIMERS.pop(identifier, None)
            # Reacquire the active ownership before releasing the lock.  A package plan observed
            # from another thread therefore sees either the timer or the newly submitted worker.
            _launch(identifier)

    timer = threading.Timer(delay, relaunch)
    timer.daemon = True
    _RETRY_TIMERS[identifier] = timer
    state["nextAttemptEpoch"] = time.time() + float(delay)
    _write(state)
    timer.start()


def enqueue(
    *,
    global_id: int,
    tee_box: str,
    loop_key: str,
    player_id: str,
    refs: list[dict[str, Any]],
    requested: dict[int, list[int]],
    ready: dict[int, list[int]],
    priority: int = SELECTED_COURSE,
    priority_hole: int | None = None,
    current_hole: int | None = None,
) -> dict[str, Any]:
    tee = tee_box.strip().lower() or "blue"
    identifier = job_id(
        global_id=global_id,
        tee_box=tee,
        loop_key=loop_key,
        player_id=player_id,
    )
    # ``current_hole`` is an additive spelling for callers that describe the signal directly;
    # package clients use the existing ``priority_hole`` request field. A missing signal means
    # “keep the journal's current hole” on repeated enqueue, with hole 1 only for a new journal.
    requested_start_hole = priority_hole if priority_hole is not None else current_hole
    # A package row that is drawable but still names missing obstacles asks for its exports. This
    # is how a journal completed before supplements were tracked heals on the next package read.
    lacking_derivatives = {
        f"{int(raw.get('globalId') or 0)}:{int(raw.get('localHole') or raw.get('hole') or 0)}"
        for raw in refs
        if isinstance(raw, dict) and any(
            isinstance(item, dict) and item.get("label") == "hazards"
            for item in raw.get("missingData") or []
        )
    }
    # Keep the launch decision outside the journal lock.  A repeated enqueue may find a
    # completely-installed record (in which case no worker is needed), while a queued or
    # newly-unblocked record must be handed to the single coordinator after its durable write.
    should_launch = True
    should_reprioritize = False
    with _LOCK:
        state = _read(identifier)
        if state is None:
            start_hole = max(1, int(requested_start_hole or 1))
            state = _initial_state(
                identifier=identifier,
                global_id=global_id,
                tee_box=tee,
                loop_key=loop_key,
                player_id=player_id,
                refs=refs,
                requested=requested,
                ready=ready,
                priority_hole=start_hole,
            )
        else:
            previous_start_hole = max(1, int(state.get("priorityHole") or 1))
            start_hole = (
                max(1, int(requested_start_hole))
                if requested_start_hole is not None
                else previous_start_hole
            )
            should_reprioritize = requested_start_hole is not None and start_hole != previous_start_hole
            # Keep the stable job id and union the durable hole set: a composite package can reveal
            # its second source course on a later request, and an idempotent retry must never throw
            # away a hole that already finished. For keys present in this request, the new release
            # observation still invalidates a different revision before any old topo is reused.
            incoming_rows = _normalise_refs(refs)
            old_rows = state.get("holes") if isinstance(state.get("holes"), dict) else {}
            incoming_by_key = {
                f"{row['globalId']}:{row['localHole']}": row for row in incoming_rows
            }
            old_normalised = _normalise_refs(list(old_rows.values()))
            old_by_key = {
                f"{row['globalId']}:{row['localHole']}": row for row in old_normalised
            }
            merged_keys = list(dict.fromkeys([*old_by_key.keys(), *incoming_by_key.keys()]))
            requested_by_gid = {
                int(k): {int(h) for h in v}
                for k, v in (requested or {}).items()
            }
            ready_by_gid = {
                int(k): {int(h) for h in v}
                for k, v in (ready or {}).items()
            }
            state_revision = max(1, int(state.get("workRevision") or 1))
            next_revision = state_revision + 1
            work_changed = False
            updated_rows: dict[str, dict[str, Any]] = {}
            for key in merged_keys:
                row = incoming_by_key.get(key) or old_by_key.get(key)
                if not row:
                    continue
                old = old_rows.get(key)
                old = old if isinstance(old, dict) else {}
                geometry = str(old.get("geometry") or "queued")
                topo = str(old.get("topo") or "queued")
                old_revision = _normalise_revision(old.get("geometryRevision"))
                incoming_revision = _normalise_revision(row.get("geometryRevision"))
                is_incoming = key in incoming_by_key
                is_requested = is_incoming and row["localHole"] in requested_by_gid.get(row["globalId"], set())
                is_ready_observation = (
                    is_incoming
                    and row["localHole"] in ready_by_gid.get(row["globalId"], set())
                    and bool(incoming_revision)
                )
                row_work_changed = not bool(old)

                # A package is a release-bound observation.  If it says this hole is pending, an
                # old ready row is not reusable: the usual reason is that Garmin published a new
                # release and the previous topo is now stale.  Likewise, a changed revision must
                # invalidate both geometry-derived facts and the bitmap atomically.
                revision_changed = bool(
                    incoming_revision and old_revision and incoming_revision != old_revision
                )
                authority_observation = str(
                    row.get("geometryAuthorityObservation") or "unknown"
                ).strip().lower()
                observation_is_conclusive = authority_observation != "unknown"
                needs_rebind = revision_changed or (
                    is_requested
                    and not is_ready_observation
                    # Full package coverage can remain partial while distance/obstacles retry.
                    # An unchanged, current mesh revision still proves this topo install ready.
                    and not (incoming_revision and incoming_revision == old_revision
                             and authority_observation == "current")
                    and observation_is_conclusive
                    and (
                        geometry in {"ready", "failed"}
                        or topo in {"ready", "failed"}
                        or old_revision is not None
                    )
                )
                if needs_rebind:
                    geometry = "queued"
                    topo = "queued"
                    old_revision = None
                    row_work_changed = True
                elif is_ready_observation:
                    geometry = "ready"
                    # A ready observation without the same revision cannot preserve old topo bytes.
                    if old_revision != incoming_revision:
                        topo = "queued"
                        row_work_changed = True
                    elif topo not in {"ready", "running"}:
                        topo = "queued"
                    if not _geometry_ready(old):
                        row_work_changed = True
                elif geometry == "failed" or topo == "failed":
                    # A repeated enqueue is an explicit retry for a failed hole.
                    geometry = "queued"
                    topo = "queued"
                    old_revision = None
                    row_work_changed = True

                merged_display_holes: list[int] = []
                for display_hole in [
                    *(old.get("displayHoles") or []),
                    *(row.get("displayHoles") or []),
                ]:
                    try:
                        display_hole = int(display_hole)
                    except (TypeError, ValueError):
                        continue
                    if display_hole > 0 and display_hole not in merged_display_holes:
                        merged_display_holes.append(display_hole)
                if not merged_display_holes:
                    merged_display_holes = [max(1, int(row.get("displayHole") or 1))]

                if row_work_changed:
                    work_changed = True
                updated = {
                    **row,
                    **old,
                    "displayHole": row["displayHole"],
                    "displayHoles": merged_display_holes,
                    "geometry": geometry,
                    "topo": topo,
                    "geometryRevision": incoming_revision or old_revision,
                    "topoRevision": (
                        _normalise_revision(old.get("topoRevision"))
                        if old_revision
                        and (
                            old_revision == incoming_revision
                            or (not incoming_revision and authority_observation == "unknown")
                        )
                        else None
                    ),
                    "workRevision": (
                        next_revision
                        if row_work_changed
                        else int(old.get("workRevision") or state_revision)
                    ),
                    "error": None if row_work_changed else old.get("error"),
                }
                if needs_rebind:
                    # A new mesh gets a fresh supplement observation on the next pass.
                    for field in _DERIVATIVE_FIELDS:
                        updated.pop(field, None)
                elif (
                    is_incoming
                    and key in lacking_derivatives
                    and geometry == "ready"
                    and not _derivatives_waiting(updated)
                ):
                    updated["derivatives"] = "queued"
                updated_rows[key] = updated
            state["holes"] = updated_rows
            merged_requested: dict[int, set[int]] = {
                int(k): {int(h) for h in v}
                for k, v in (state.get("requested") or {}).items()
            }
            for gid, holes in requested.items():
                merged_requested.setdefault(int(gid), set()).update(int(h) for h in holes)
            state["requested"] = {str(k): sorted(v) for k, v in merged_requested.items()}
            merged_ready: dict[int, set[int]] = {
                int(k): {int(h) for h in v}
                for k, v in (state.get("ready") or {}).items()
            }
            for gid, holes in ready.items():
                merged_ready.setdefault(int(gid), set()).update(int(h) for h in holes)
            state["ready"] = {str(k): sorted(v) for k, v in merged_ready.items()}
            if work_changed:
                state["workRevision"] = next_revision
                # A new enqueue is an explicit retry after a prior terminal or stale attempt.
                _RETRY_ATTEMPTS.pop(identifier, None)
            supplements_only = state.get("phase") == "ready" and all(
                _geometry_ready(row) and _topo_ready(row)
                for row in state["holes"].values()
                if isinstance(row, dict)
            )
            if supplements_only and not _all_assets_ready(state):
                # Installed mesh/topo stay valid: only the obstacle exports are owned again, so
                # this is the same generation and its progress is kept.
                state["phase"] = "queued"
                state["stage"] = "derivatives"
                state["error"] = None
                state["cancellable"] = True
            elif state.get("phase") in {"ready", "failed", "cancelled"} and not _all_assets_ready(state):
                state["phase"] = "queued"
                state["stage"] = "queued"
                state["error"] = None
                state["cancelRequested"] = False
                state["cancelRequestedAt"] = None
                state["terminalReason"] = None
                state["cancellable"] = True
                state["generation"] = max(1, int(state.get("generation") or 1)) + 1
                state["progress"] = 0
        # The package route's current hole is a process-local scheduling signal. It changes the
        # order of future passes and, after the journal write, reprioritises queued topo work. A
        # currently running renderer is intentionally left alone.
        state["priorityHole"] = start_hole
        # A user selecting a course promotes its queued work. Regional discovery can never
        # demote an existing foreground job or change its player/loop/Tee identity.
        state["priority"] = min(int(state.get("priority", priority)), int(priority))
        _recount(state)
        if _all_assets_ready(state):
            state["phase"] = "ready"
            state["stage"] = "complete"
            state["error"] = None
            should_launch = False
        state["cancellable"] = state.get("phase") not in _TERMINAL_PHASES
        _write(state)
        scheduling_state = state
    if should_reprioritize:
        _reprioritize_topo_queue(scheduling_state)
    if should_launch:
        _launch(identifier)
    return public_state(state)


def _reprioritize_topo_queue(state: dict[str, Any]) -> None:
    """Ask the shared topo lane to reorder queued rows after a current-hole signal.

    The import is intentionally lazy: ``server_v2.main`` imports this module while constructing the
    FastAPI application.  If a small unit test uses the journal without importing the API, the durable
    state still records the signal and the next install pass applies it.
    """
    try:
        from server_v2.main import _reprioritize_course_topo_queue

        _reprioritize_course_topo_queue(
            list((state.get("holes") or {}).values()),
            current_hole=int(state.get("priorityHole") or 1),
            base_priority=int(state.get("priority", SELECTED_COURSE)),
        )
    except Exception:
        # Scheduling is best effort; the durable priorityHole remains authoritative for the next
        # coordinator pass and must never make an enqueue request fail.
        logger.exception("course install topo reprioritization failed")
        return


def public_state(state: dict[str, Any]) -> dict[str, Any]:
    """Return a response-safe copy; never expose the player hash or internal requested maps."""
    rows = []
    for row in (state.get("holes") or {}).values():
        if not isinstance(row, dict):
            continue
        rows.append({
            "globalId": int(row.get("globalId") or 0),
            "localHole": int(row.get("localHole") or 0),
            "displayHole": int(row.get("displayHole") or row.get("localHole") or 0),
            "geometry": str(row.get("geometry") or "queued"),
            "geometryRevision": _normalise_revision(row.get("geometryRevision")),
            "topo": str(row.get("topo") or "queued"),
            "topoRevision": _normalise_revision(row.get("topoRevision")),
            "error": _public_error(row.get("error")),
        })
    rows.sort(key=lambda row: (row["displayHole"], row["globalId"], row["localHole"]))
    phase, stage = state.get("phase"), state.get("stage")
    if _only_derivatives_remain(state):
        # Every hole's mesh and topo are installed: the course is usable and clients must stop
        # waiting on it.  Internally the journal stays queued and keeps retrying the optional
        # obstacle exports (the job is not complete); that is reported as this stage.
        phase, stage = "ready", "derivatives"
    return {
        "schema": "ai-caddie-course-install-v1",
        "jobId": state.get("jobId"),
        "globalId": int(state.get("globalId") or 0),
        "teeBox": state.get("teeBox"),
        "loopKey": str(state.get("loopKey") or ""),
        "phase": phase,
        "stage": stage,
        "progress": max(0, min(100, int(state.get("progress") or 0))),
        "heartbeatAt": state.get("heartbeatAt"),
        "cancelRequested": bool(state.get("cancelRequested")),
        "cancelRequestedAt": state.get("cancelRequestedAt"),
        "terminalReason": state.get("terminalReason"),
        "retryCount": max(0, int(state.get("retryCount") or 0)),
        "generation": max(1, int(state.get("generation") or 1)),
        "cancellable": bool(state.get("cancellable")) and phase not in _TERMINAL_PHASES,
        "totalHoles": int(state.get("totalHoles") or 0),
        "geometryReady": int(state.get("geometryReady") or 0),
        "topoReady": int(state.get("topoReady") or 0),
        "updatedAt": state.get("updatedAt"),
        "error": _public_error(state.get("error")),
        "holes": rows,
    }


def status(
    *,
    global_id: int,
    tee_box: str,
    loop_key: str,
    player_id: str,
) -> dict[str, Any] | None:
    identifier = job_id(
        global_id=global_id,
        tee_box=tee_box,
        loop_key=loop_key,
        player_id=player_id,
    )
    with _LOCK:
        state = _read(identifier)
    return public_state(state) if state else None


def state_for_player(identifier: str, player_id: str) -> dict[str, Any] | None:
    """Read a job by its opaque id while enforcing the journal's player partition."""
    with _LOCK:
        state = _read(identifier)
    if state is None or str(state.get("playerKey") or "") != _player_key(player_id):
        return None
    return state


def status_by_job(identifier: str, *, player_id: str) -> dict[str, Any] | None:
    state = state_for_player(identifier, player_id)
    return public_state(state) if state else None


def _remove_from_resume_backlog(identifier: str) -> None:
    global _RESUME_BACKLOG
    _RESUME_BACKLOG = [item for item in _RESUME_BACKLOG if item != identifier]


def cancel(identifier: str, *, player_id: str) -> dict[str, Any] | None:
    """Request cancellation and publish a terminal state immediately.

    The current geometry/provider call is cooperative and may finish in the background, but all
    callbacks are generation/phase guarded and can no longer change the public result.
    """
    with _LOCK:
        state = _read(identifier)
        if state is None or str(state.get("playerKey") or "") != _player_key(player_id):
            return None
        timer = _RETRY_TIMERS.pop(identifier, None)
        if timer is not None:
            timer.cancel()
        _remove_from_resume_backlog(identifier)
        if state.get("phase") not in _TERMINAL_PHASES:
            now = _now()
            state["phase"] = "cancelled"
            state["stage"] = "cancelled"
            state["cancelRequested"] = True
            state["cancelRequestedAt"] = now
            state["terminalReason"] = "user_cancelled"
            state["cancellable"] = False
            state["error"] = None
        _write(state)
        return public_state(state)


def retry(identifier: str, *, player_id: str) -> dict[str, Any] | None:
    """Start a fresh generation for a failed/cancelled job, preserving completed assets."""
    with _LOCK:
        state = _read(identifier)
        if state is None or str(state.get("playerKey") or "") != _player_key(player_id):
            return None
        if state.get("phase") == "ready":
            raise ValueError("course install is already ready")
        if state.get("phase") not in {"failed", "cancelled"}:
            raise ValueError("course install is still running")
        timer = _RETRY_TIMERS.pop(identifier, None)
        if timer is not None:
            timer.cancel()
        state["generation"] = max(1, int(state.get("generation") or 1)) + 1
        state["retryCount"] = max(0, int(state.get("retryCount") or 0)) + 1
        state["phase"] = "queued"
        state["stage"] = "queued"
        state["cancelRequested"] = False
        state["cancelRequestedAt"] = None
        state["terminalReason"] = None
        state["cancellable"] = True
        state["error"] = None
        # Keep ready geometry/topo rows; every incomplete row gets another cooperative pass.
        for row in (state.get("holes") or {}).values():
            if not isinstance(row, dict):
                continue
            if not (_geometry_ready(row) and _topo_ready(row)):
                row["geometry"] = "queued"
                row["topo"] = "queued"
                row["error"] = None
                row["workRevision"] = max(1, int(row.get("workRevision") or 1)) + 1
        completed = sum(
            1
            for row in (state.get("holes") or {}).values()
            if isinstance(row, dict) and _geometry_ready(row) and _topo_ready(row)
        )
        total = max(1, len(state.get("holes") or {}) * 2)
        state["progress"] = min(100, int(round(completed * 200 / total)))
        _recount(state)
        _write(state)
        result = public_state(state)
    _launch(identifier)
    return result


def heartbeat(identifier: str) -> bool:
    with _LOCK:
        state = _read(identifier)
        if state is None or state.get("phase") in _TERMINAL_PHASES:
            return False
        _write(state)
        return True


def cancellation_requested(identifier: str) -> bool:
    with _LOCK:
        state = _read(identifier)
    return bool(state and (state.get("cancelRequested") or state.get("phase") == "cancelled"))


def update(
    identifier: str,
    *,
    phase: str | None = None,
    stage: str | None = None,
    global_id: int | None = None,
    local_hole: int | None = None,
    geometry: str | None = None,
    geometry_revision: str | None = None,
    topo: str | None = None,
    topo_revision: str | None = None,
    expected_work_revision: int | None = None,
    error: str | None = None,
    clear_error: bool = False,
) -> bool:
    with _LOCK:
        state = _read(identifier)
        if state is None:
            return False
        if state.get("phase") == "cancelled" and phase != "cancelled":
            # A provider callback from a pre-cancel generation must never resurrect a cancelled job.
            return False
        guarded_row: dict[str, Any] | None = None
        if global_id is not None and local_hole is not None:
            key = f"{int(global_id)}:{int(local_hole)}"
            guarded_row = state.setdefault("holes", {}).setdefault(key, {
                "globalId": int(global_id),
                "localHole": int(local_hole),
                "displayHole": int(local_hole),
                "geometry": "queued",
                "geometryRevision": None,
                "topo": "queued",
                "topoRevision": None,
                "workRevision": max(1, int(state.get("workRevision") or 1)),
            })
            if (
                expected_work_revision is not None
                and int(guarded_row.get("workRevision") or 0) != int(expected_work_revision)
            ):
                # A Garmin release changed while an older geometry/topo future was still finishing.
                # Its bytes must not overwrite the newly queued row or its phase.
                return False
        if phase is not None:
            state["phase"] = phase
            if phase == "ready":
                # A later derivative plan is a new observable transition, even when its tuple
                # happens to match the plan that preceded the completed generation.
                _DERIVATIVE_LOG_SIGNATURES.pop(identifier, None)
        if stage is not None:
            state["stage"] = stage
        if clear_error:
            state["error"] = None
        elif error is not None:
            state["error"] = error[:240]
        if guarded_row is not None:
            row = guarded_row
            if geometry is not None:
                row["geometry"] = geometry
            if geometry_revision is not None:
                row["geometryRevision"] = _normalise_revision(geometry_revision)
            if topo is not None:
                row["topo"] = topo
            if topo_revision is not None:
                row["topoRevision"] = _normalise_revision(topo_revision)
            if clear_error:
                row["error"] = None
            elif error is not None:
                row["error"] = error[:240]
        _recount(state)
        _write(state)
    return True


def _run(identifier: str) -> None:
    relaunch = False
    initial_progress = (0, 0)
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    try:
        with _LOCK:
            state = _read(identifier)
            if state is None:
                return
            if state.get("phase") in _TERMINAL_PHASES or state.get("cancelRequested"):
                return
            initial_progress = (
                int(state.get("geometryReady") or 0),
                int(state.get("topoReady") or 0),
            )
            state["phase"] = "running"
            state["stage"] = "geometry"
            state["error"] = None
            _write(state)

        def publish_heartbeat() -> None:
            while not heartbeat_stop.wait(_HEARTBEAT_INTERVAL_SECONDS):
                if not heartbeat(identifier):
                    return

        heartbeat_thread = threading.Thread(
            target=publish_heartbeat,
            name=f"course-install-heartbeat-{identifier[-8:]}",
            daemon=True,
        )
        heartbeat_thread.start()
        # Import only after the worker starts: main imports this module during app construction and
        # importing it back at module load would create a circular import.
        from .main import run_course_install_job

        run_course_install_job(identifier)
    except Exception:  # noqa: BLE001 - a job failure must be durable and retryable
        # Keep traceback details in the server log, never in the durable journal that may be
        # inspected/backed up independently of the process.
        update(identifier, phase="failed", stage="error", error="course install failed")
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None and heartbeat_thread is not threading.current_thread():
            heartbeat_thread.join(timeout=0.2)
        with _LOCK:
            _ACTIVE.discard(identifier)
            state = _read(identifier)
            if state and (state.get("phase") == "cancelled" or state.get("cancelRequested")):
                relaunch = False
                _RETRY_ATTEMPTS.pop(identifier, None)
            else:
                made_progress = bool(state) and (
                    int(state.get("geometryReady") or 0),
                    int(state.get("topoReady") or 0),
                ) > initial_progress
                if made_progress:
                    # A slow course that completes some holes on each pass is healthy progress; do not
                    # spend its entire retry budget merely because other holes are still waiting.
                    _RETRY_ATTEMPTS.pop(identifier, None)
                # ``enqueue`` can append/rebind a hole while the worker is in its final topo wait. It
                # sees the active worker and therefore cannot launch a second one; hand the queued row
                # off after releasing the active slot so it is never stranded.
                relaunch = bool(state and (_has_queued_work(state) or _has_derivative_work(state)))
                if (
                    state
                    and not relaunch
                    and state.get("phase") in {"queued", "running"}
                    and _all_assets_ready(state)
                ):
                    # The last export settled while this worker still held the active slot; its
                    # listener left the phase decision to us.
                    state["phase"] = "ready"
                    state["stage"] = "complete"
                    state["error"] = None
                    state["cancellable"] = False
                    state.pop("nextAttemptEpoch", None)
                    _write(state)
            if relaunch:
                if made_progress and state and state.get("phase") == "queued" and _has_queued_work(state):
                    # Keep ownership continuous while handing the next window to the worker.
                    _launch(identifier)
                else:
                    # Arm the timer before releasing the journal lock so hole_plan never sees
                    # an unowned interval between the worker and its retry hand-off.
                    _schedule_retry(identifier)
        if not relaunch and (not state or state.get("phase") != "cancelled"):
            with _LOCK:
                _RETRY_ATTEMPTS.pop(identifier, None)
        # A terminal retry or a delayed retry must not strand other jobs recovered after restart.
        _launch_next_resumed_job()


def _retention_days() -> int:
    try:
        return min(3650, max(1, int(os.environ.get("AI_CADDIE_COURSE_INSTALL_RETENTION_DAYS", "30"))))
    except (TypeError, ValueError):
        return 30


def _state_timestamp(state: dict[str, Any], path: Path) -> float:
    raw = str(state.get("updatedAt") or "").strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.timestamp()
        except (TypeError, ValueError, OverflowError):
            pass
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _requeue_missing_derivatives(state: dict[str, Any]) -> bool:
    """Mark installed rows whose exports are missing on disk; True when any row changed."""
    try:
        from ai_caddie.geometry.geometry_sync import derivative_state
    except Exception:  # noqa: BLE001 - a scan must never prevent resuming other journals
        return False
    changed = False
    for row in (state.get("holes") or {}).values():
        if not isinstance(row, dict) or not _geometry_ready(row) or _derivatives_waiting(row):
            continue
        try:
            observed = derivative_state(int(row.get("globalId") or 0), int(row.get("localHole") or 0))
        except Exception:  # noqa: BLE001
            continue
        if observed.get("state") in {"due", "retrying", "running"}:
            row["derivatives"] = "queued"
            changed = True
    return changed


def _launch_next_resumed_job() -> None:
    """Submit one restart backlog item at a time so a newly selected course can cut in next."""
    while True:
        with _LOCK:
            if not _RESUME_BACKLOG:
                return
            identifier = _RESUME_BACKLOG.pop(0)
            if identifier in _ACTIVE:
                continue
            state = _read(identifier)
            if not state or state.get("phase") not in {"queued", "running"}:
                continue
            # Submit while the lock is still held; otherwise popping the first backlog item
            # briefly makes it invisible to hole_plan while the next item is still waiting.
            _launch(identifier)
            return


def resume_pending_jobs() -> None:
    global _RESUME_BACKLOG
    root = _root()
    try:
        paths = list(root.glob("course-*.json"))
    except OSError:
        return
    pending: list[tuple[int, float, str]] = []
    # Publish the scan candidates before taking the journal lock; a package observer must never
    # see the empty staging state as an unowned hand-off point while individual files are read.
    _RESUME_BACKLOG = [path.stem for path in paths]
    terminal_cutoff = datetime.now(UTC) - timedelta(days=_retention_days())
    for path in paths:
        identifier = path.stem
        with _LOCK:
            state = _read(identifier)
            if not state:
                continue
            if identifier in _ACTIVE:
                continue
            phase = str(state.get("phase") or "")
            updated_timestamp = _state_timestamp(state, path)
            if phase in {"ready", "failed"} and updated_timestamp < terminal_cutoff.timestamp():
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            if phase == "ready" and _requeue_missing_derivatives(state):
                # A journal completed while a hole's exports were still missing (and, before
                # supplements were tracked, with nobody left to retry them): own them again.
                phase = "queued"
                state["cancellable"] = True
            if phase not in {"queued", "running"}:
                continue
            rows = state.get("holes") if isinstance(state.get("holes"), dict) else {}
            for row in rows.values():
                if not isinstance(row, dict):
                    continue
                if row.get("geometry") == "running":
                    row["geometry"] = "queued"
                if row.get("topo") == "running":
                    row["topo"] = "queued"
                if row.get("derivatives") == "running":
                    # The in-memory export lane died with the process; the persisted plan in the
                    # derivative status (if any) is re-read on the next pass.
                    row["derivatives"] = "queued"
            state["phase"] = "queued"
            state["stage"] = "queued"
            state["updatedAt"] = _now()
            # Publish recovered ownership while the scan is still rewriting later journals.  This
            # closes the package-plan gap between the first durable rewrite and final backlog sort.
            if identifier not in _RESUME_BACKLOG:
                _RESUME_BACKLOG.append(identifier)
            _write(state)
            pending.append((int(state.get("priority", SELECTED_COURSE)), updated_timestamp, identifier))
    with _LOCK:
        # Only the newest recovered job enters the single-worker executor now. The rest are handed
        # off one-by-one after completion, so a course explicitly selected after restart is queued
        # ahead of old recovery work rather than behind an unbounded executor backlog.
        _RESUME_BACKLOG = [identifier for _priority, _stamp, identifier in
                           sorted(pending, key=lambda row: (row[0], -row[1]))]
    _launch_next_resumed_job()


def state_for_worker(identifier: str) -> dict[str, Any] | None:
    with _LOCK:
        return _read(identifier)


def bind_nearby_holes(identifier: str, published_holes: list[int]) -> None:
    """Replace a provider catalogue's approximate hole count with the actual release table.

    Only the dedicated public nearby journal may shrink this way. Player-selected loop journals
    keep their proven ordered identity and union/rebind behavior untouched.
    """
    with _LOCK:
        state = _read(identifier)
        if not state or not str(state.get("loopKey") or "").endswith(":nearby-assets"):
            return
        gid = int(state["globalId"])
        numbers = sorted({int(h) for h in published_holes if 0 < int(h) <= 36})
        old = state.get("holes") or {}
        state["holes"] = {
            f"{gid}:{h}": old.get(f"{gid}:{h}") or {
                "globalId": gid, "localHole": h, "displayHole": h,
                "geometry": "queued", "topo": "queued", "geometryRevision": None,
                "topoRevision": None, "workRevision": int(state.get("workRevision") or 1),
            } for h in numbers
        }
        state["requested"] = {str(gid): numbers}
        _recount(state)
        _write(state)


def hole_plan(global_id: int, local_hole: int) -> dict[str, Any] | None:
    """Background geometry/topo work this process really owns for one physical hole.

    Only live jobs are considered: running or submitted (``_ACTIVE``), recovered and waiting for
    the worker (``_RESUME_BACKLOG``) or waiting on a retry timer (``_RETRY_TIMERS``).  A failed or
    cancelled journal, or a queued journal nobody will run, is not a plan.  Returns
    ``{"state": "in_flight"}``, ``{"state": "scheduled", "retryAfterEpoch": <timer due>}`` or
    ``None``.
    """
    key = f"{int(global_id)}:{int(local_hole)}"
    scheduled: list[float] = []
    with _LOCK:
        in_flight = set(_ACTIVE) | set(_RESUME_BACKLOG)
        timed = set(_RETRY_TIMERS) - in_flight
        for identifier in sorted(in_flight | timed):
            state = _read(identifier)
            if not state or state.get("phase") in {"failed", "cancelled"} or state.get("cancelRequested"):
                continue
            row = (state.get("holes") or {}).get(key)
            if not isinstance(row, dict):
                continue
            # Nearby warming uses these shared journals, but a deferred nearby journal must not
            # make a player's failed install look retryable after that player lost ownership.
            if (
                str(state.get("loopKey") or "").endswith(":nearby-assets")
                and state.get("stage") in _DEFERRED_STAGES
            ):
                continue
            owed = row.get("geometry") in {"queued", "running"} or (
                _geometry_ready(row) and row.get("topo") in {"queued", "running"}
            )
            if not owed:
                continue
            if identifier in in_flight:
                return {"state": "in_flight", "retryAfterEpoch": None}
            try:
                scheduled.append(float(state.get("nextAttemptEpoch")))
            except (TypeError, ValueError):
                return {"state": "in_flight", "retryAfterEpoch": None}
    if scheduled:
        return {"state": "scheduled", "retryAfterEpoch": min(scheduled)}
    return None


def _register_derivative_listener() -> None:
    # The geometry library reports settled export attempts and the package builder asks which
    # holes have background work; neither imports this module.
    from ai_caddie.caddie.mobile_live import add_hole_plan_provider
    from ai_caddie.geometry.batch_prodgeometry_course import add_derivative_listener

    add_derivative_listener(derivatives_settled)
    add_hole_plan_provider(hole_plan)


_register_derivative_listener()
