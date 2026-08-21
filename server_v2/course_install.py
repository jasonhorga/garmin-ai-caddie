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

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any

from ai_caddie.core.data import ROOT

_LOCK = threading.RLock()
_ACTIVE: set[str] = set()
_RESUME_BACKLOG: list[str] = []
# A transient Garmin authority outage must not turn a queued job into a hot loop.  Timers are
# deliberately process-local: the journal remains the durable source of truth, and a restart will
# perform one normal resume pass before applying the same bounded backoff again.
_RETRY_TIMERS: dict[str, threading.Timer] = {}
_RETRY_ATTEMPTS: dict[str, int] = {}
# A persistent authority/provider outage should become an actionable failed row rather than
# consuming a worker forever. An explicit enqueue/retry resets this counter below.
_MAX_RETRY_ATTEMPTS = 8
# One job coordinator at a time keeps a four-core shared homeserver from multiplying the existing
# two-hole geometry pool and one-hole topo pipeline across simultaneous course selections.
_WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="course-install-job")


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
    nine: str,
    player_id: str,
    back_global_id: int | None = None,
) -> str:
    # Preserve the pre-composite id format for ordinary courses so queued jobs from an older
    # process remain resumable. A composite 9+9 selection must include its second physical loop;
    # otherwise two different back-nine choices would share one journal and leak progress.
    raw = f"{int(global_id)}|{tee_box.strip().lower()}|{nine.strip().lower() or 'all'}|{_player_key(player_id)}"
    if back_global_id is not None and int(back_global_id) > 0:
        raw = f"{int(global_id)}|back:{int(back_global_id)}|{tee_box.strip().lower()}|{nine.strip().lower() or 'all'}|{_player_key(player_id)}"
    return "course-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _path(identifier: str) -> Path:
    return _root() / f"{identifier}.json"


def _write(state: dict[str, Any]) -> None:
    path = _path(str(state["jobId"]))
    path.parent.mkdir(parents=True, exist_ok=True)
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
    seen: set[tuple[int, int]] = set()
    for raw in refs:
        if not isinstance(raw, dict):
            continue
        gid = int(raw.get("globalId") or 0)
        hole = int(raw.get("localHole") or raw.get("hole") or 0)
        display = int(raw.get("displayHole") or raw.get("number") or hole)
        if gid <= 0 or hole <= 0 or (gid, hole) in seen:
            continue
        seen.add((gid, hole))
        result.append({
            "globalId": gid,
            "localHole": hole,
            "displayHole": max(1, display),
            "geometryRevision": _normalise_revision(raw.get("geometryRevision")),
            "geometryAuthorityObservation": str(
                raw.get("geometryAuthorityObservation") or "unknown"
            ).strip().lower(),
        })
    return result


def _initial_state(
    *,
    identifier: str,
    global_id: int,
    tee_box: str,
    nine: str,
    player_id: str,
    refs: list[dict[str, Any]],
    requested: dict[int, list[int]],
    ready: dict[int, list[int]],
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
        "nine": nine,
        "playerKey": _player_key(player_id),
        "phase": "queued",
        "stage": "queued",
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


def _all_assets_ready(state: dict[str, Any]) -> bool:
    rows = [row for row in (state.get("holes") or {}).values() if isinstance(row, dict)]
    return bool(rows) and all(
        _geometry_ready(row) and _topo_ready(row)
        for row in rows
    )


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
        _ACTIVE.add(identifier)
    _WORKER.submit(_run, identifier)


def _schedule_retry(identifier: str) -> None:
    """Hand a queued job back to the coordinator after bounded exponential backoff.

    ``unknown`` authority is expected to recover (for example while a Garmin release sidecar is
    being atomically replaced), so it must remain queued rather than failed.  A timer keeps the
    single worker available for other courses and prevents a rapid status poll from consuming all
    CPU/IO.  At most one timer exists per job.
    """
    with _LOCK:
        state = _read(identifier)
        if not state or not _has_queued_work(state) or identifier in _ACTIVE:
            return
        if identifier in _RETRY_TIMERS:
            return
        attempt = _RETRY_ATTEMPTS.get(identifier, 0)
        if attempt >= _MAX_RETRY_ATTEMPTS:
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
        _RETRY_ATTEMPTS[identifier] = attempt + 1
        delay = min(60.0, float(2 ** attempt))

        def relaunch() -> None:
            with _LOCK:
                _RETRY_TIMERS.pop(identifier, None)
            _launch(identifier)

        timer = threading.Timer(delay, relaunch)
        timer.daemon = True
        _RETRY_TIMERS[identifier] = timer
        timer.start()


def enqueue(
    *,
    global_id: int,
    tee_box: str,
    nine: str,
    player_id: str,
    refs: list[dict[str, Any]],
    requested: dict[int, list[int]],
    ready: dict[int, list[int]],
    back_global_id: int | None = None,
) -> dict[str, Any]:
    tee = tee_box.strip().lower() or "blue"
    selected_nine = nine.strip().lower() or "all"
    # Derive the second physical loop as a compatibility guard for callers that only know the
    # package refs. The HTTP route passes it explicitly, but an older internal caller should not
    # silently collapse a composite job into the ordinary primary-course journal.
    source_ids = {
        int(row.get("globalId") or 0)
        for row in refs
        if isinstance(row, dict) and int(row.get("globalId") or 0) > 0
    }
    resolved_back_global_id = (
        int(back_global_id)
        if back_global_id is not None and int(back_global_id) > 0
        else next((source_id for source_id in sorted(source_ids) if source_id != int(global_id)), None)
    )
    identifier = job_id(
        global_id=global_id,
        tee_box=tee,
        nine=selected_nine,
        player_id=player_id,
        back_global_id=resolved_back_global_id,
    )
    # Keep the launch decision outside the journal lock.  A repeated enqueue may find a
    # completely-installed record (in which case no worker is needed), while a queued or
    # newly-unblocked record must be handed to the single coordinator after its durable write.
    should_launch = True
    with _LOCK:
        state = _read(identifier)
        if state is None:
            state = _initial_state(
                identifier=identifier,
                global_id=global_id,
                tee_box=tee,
                nine=selected_nine,
                player_id=player_id,
                refs=refs,
                requested=requested,
                ready=ready,
            )
        else:
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

                if row_work_changed:
                    work_changed = True
                updated_rows[key] = {
                    **row,
                    **old,
                    "displayHole": row["displayHole"],
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
            if state.get("phase") in {"ready", "failed"} and not _all_assets_ready(state):
                state["phase"] = "queued"
                state["stage"] = "queued"
                state["error"] = None
        _recount(state)
        if _all_assets_ready(state):
            state["phase"] = "ready"
            state["stage"] = "complete"
            state["error"] = None
            should_launch = False
        state["updatedAt"] = _now()
        _write(state)
    if should_launch:
        _launch(identifier)
    return public_state(state)


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
    return {
        "schema": "ai-caddie-course-install-v1",
        "jobId": state.get("jobId"),
        "globalId": int(state.get("globalId") or 0),
        "teeBox": state.get("teeBox"),
        "nine": state.get("nine"),
        "phase": state.get("phase"),
        "stage": state.get("stage"),
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
    nine: str,
    player_id: str,
    back_global_id: int | None = None,
) -> dict[str, Any] | None:
    identifier = job_id(
        global_id=global_id,
        tee_box=tee_box,
        nine=nine,
        player_id=player_id,
        back_global_id=back_global_id,
    )
    with _LOCK:
        state = _read(identifier)
    return public_state(state) if state else None


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
        state["updatedAt"] = _now()
        _write(state)
    return True


def _run(identifier: str) -> None:
    relaunch = False
    initial_progress = (0, 0)
    try:
        with _LOCK:
            state = _read(identifier)
            if state is None:
                return
            initial_progress = (
                int(state.get("geometryReady") or 0),
                int(state.get("topoReady") or 0),
            )
            state["phase"] = "running"
            state["stage"] = "geometry"
            state["error"] = None
            state["updatedAt"] = _now()
            _write(state)
        # Import only after the worker starts: main imports this module during app construction and
        # importing it back at module load would create a circular import.
        from .main import run_course_install_job

        run_course_install_job(identifier)
    except Exception:  # noqa: BLE001 - a job failure must be durable and retryable
        # Keep traceback details in the server log, never in the durable journal that may be
        # inspected/backed up independently of the process.
        update(identifier, phase="failed", stage="error", error="course install failed")
    finally:
        with _LOCK:
            _ACTIVE.discard(identifier)
            state = _read(identifier)
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
            relaunch = bool(state and _has_queued_work(state))
        if relaunch:
            _schedule_retry(identifier)
        else:
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
        _launch(identifier)
        return


def resume_pending_jobs() -> None:
    global _RESUME_BACKLOG
    root = _root()
    try:
        paths = list(root.glob("course-*.json"))
    except OSError:
        return
    pending: list[tuple[float, str]] = []
    terminal_cutoff = datetime.now(UTC) - timedelta(days=_retention_days())
    for path in paths:
        identifier = path.stem
        with _LOCK:
            state = _read(identifier)
            if not state:
                continue
            phase = str(state.get("phase") or "")
            updated_timestamp = _state_timestamp(state, path)
            if phase in {"ready", "failed"} and updated_timestamp < terminal_cutoff.timestamp():
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
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
            state["phase"] = "queued"
            state["stage"] = "queued"
            state["updatedAt"] = _now()
            _write(state)
            pending.append((updated_timestamp, identifier))
    with _LOCK:
        # Only the newest recovered job enters the single-worker executor now. The rest are handed
        # off one-by-one after completion, so a course explicitly selected after restart is queued
        # ahead of old recovery work rather than behind an unbounded executor backlog.
        _RESUME_BACKLOG = [identifier for _stamp, identifier in sorted(pending, reverse=True)]
    _launch_next_resumed_job()


def state_for_worker(identifier: str) -> dict[str, Any] | None:
    with _LOCK:
        return _read(identifier)
