"""End-to-end local data pipeline — the single "service runs itself" entrypoint.

Runs idempotently and ties the backbone together:

  ensure auth  ->  fetch history (scorecards [+ shots])  ->  ensure missing geometry  ->  build played course-ref store

Auth refresh self-heals on a server via the Playwright fallback in
``garmin_auth.refresh_web_auth`` (see Phase 2); per-hole geometry is synced on demand
elsewhere, so the pipeline reports coverage rather than bulk-downloading. The heavy
steps are module-level functions so they can be patched in tests (no network in CI).

Run:  ``uv run python -m ai_caddie.pipeline [--shots] [--refresh-auth] [--geometry-limit N]``
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from ai_caddie.courses import course_reference
from ai_caddie.core.data import ROOT, SCORECARD_DIR, SHOT_DIR


@dataclass
class SyncResult:
    auth_ok: bool
    rounds: int = 0
    scorecards: int = 0
    shots: int = 0
    course_nines: int = 0
    geometry_attempted: int = 0
    geometry_failed: int = 0
    course_reference_total: int = 0
    course_reference_ready: int = 0
    course_reference_missing: int = 0
    course_reference_coverage_pct: float = 0.0
    remote_round_count: int | None = None
    remote_latest_round_id: str | None = None
    remote_latest_round_at: str | None = None
    new_round_count: int | None = None
    notes: list[str] = field(default_factory=list)


def _summary_observation(*, root: Path = ROOT) -> dict[str, Any]:
    """Read safe freshness facts from the latest Garmin summary response."""
    path = Path(root) / "data" / "summary.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"count": 0, "ids": set(), "latestId": None, "latestAt": None}
    rows = payload.get("scorecardSummaries") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        rows = []

    def row_id(row: object) -> str | None:
        if not isinstance(row, dict):
            return None
        value = row.get("id") or row.get("scorecardId")
        return str(value) if value is not None else None

    def parsed_time(row: object) -> datetime:
        if not isinstance(row, dict):
            return datetime.min.replace(tzinfo=timezone.utc)
        value = row.get("startTime") or row.get("formattedStartTime") or ""
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return datetime.min.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    ids = {value for row in rows if (value := row_id(row)) is not None}
    latest = max((row for row in rows if isinstance(row, dict)), key=parsed_time, default=None)
    latest_at: str | None = None
    latest_id = row_id(latest)
    if latest is not None:
        parsed = parsed_time(latest)
        if parsed != datetime.min.replace(tzinfo=timezone.utc):
            latest_at = parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {"count": len(rows), "ids": ids, "latestId": latest_id, "latestAt": latest_at}


def _persist_sync_observability(result: SyncResult, *, root=ROOT) -> bool:
    """Persist cron outcome without claiming a durable connector snapshot exists.

    The cron entrypoint historically called this module directly, so scorecards and shots were
    refreshed while ``/sync/status`` kept serving the previous run's metadata. A raw-snapshot
    manifest is intentionally NOT written here: connector snapshots include durable copies of all
    referenced data/geometry, and copying those every hour would be both expensive and dishonest
    unless the matching durable tree were created too. ``sync_status`` recognizes a newer ready
    status without a snapshot id and reports the live files while retaining the last durable id.
    """
    from ai_caddie.connectors.snapshot import write_connector_status

    if not result.auth_ok:
        write_connector_status(
            root=root,
            state="reauth_required",
            detail="Garmin CN web session is unavailable. Reconnect Garmin and retry.",
            snapshot_id=None,
            error_code="auth_failed",
        )
        return True

    state = "ready" if result.scorecards else "no_data"
    detail = (
        f"Synced {result.scorecards} scorecards and {result.shots} shot files."
        if state == "ready"
        else "Garmin sync completed, but no scorecards were returned."
    )
    write_connector_status(
        root=root,
        state=state,
        detail=detail,
        snapshot_id=None,
        error_code=None,
        remote_round_count=result.remote_round_count,
        remote_latest_round_id=result.remote_latest_round_id,
        remote_latest_round_at=result.remote_latest_round_at,
        new_round_count=result.new_round_count,
    )
    return True


def _ensure_auth(force_refresh: bool) -> bool:
    """Ensure a usable web session, refreshing (Playwright fallback on a server) if needed."""
    try:
        from ai_caddie.garmin.garmin_auth import ensure_web_auth, validate_web_auth

        auth = ensure_web_auth(force=force_refresh, validate=False)
        ok, _status = validate_web_auth(auth)
        if ok:
            return True
        ensure_web_auth(force=True, validate=True)  # cached invalid -> refresh
        return True
    except Exception:
        return False


def _fetch_history(with_shots: bool, *, force_refresh_auth: bool = False) -> int:
    """Fetch summary + details (+ shots). Returns the number of rounds in the summary."""
    from ai_caddie.garmin import fetch

    session = fetch.make_session(force_refresh_auth=force_refresh_auth)
    cards = fetch.fetch_summary(session)
    fetch.fetch_details(session, cards, with_shots=with_shots)
    # The player's real club bag (names) — reuses the same session. Non-fatal: a club-fetch failure
    # must never block the history sync, which is the critical path.
    try:
        fetch.fetch_clubs(session)
    except Exception as exc:  # noqa: BLE001 - best-effort enrichment
        print(f"[!!] club bag fetch failed (non-fatal): {exc}")
    return len(cards)


def _on_disk() -> tuple[int, int]:
    scs = len(list(SCORECARD_DIR.glob("*.json"))) if SCORECARD_DIR.exists() else 0
    shots = len(list(SHOT_DIR.glob("*.json"))) if SHOT_DIR.exists() else 0
    return scs, shots


def _ensure_geometry(*, limit: int | None = None) -> dict[str, int]:
    """Idempotently download missing prodgeometry for played courses (skips already-ready)."""
    from ai_caddie.connectors.snapshot import (
        discover_geometry_dependencies,
        discover_played_geometry_dependencies,
        ensure_geometry_dependencies,
    )
    from ai_caddie.history.stats_cache import cached_load_history_data

    data = cached_load_history_data()
    if data.shots:
        dependencies = discover_played_geometry_dependencies(data, root=ROOT, limit=limit)
    else:
        dependencies = discover_geometry_dependencies(root=ROOT)
        if limit is not None:
            dependencies = [row for row in dependencies if row.get("status") != "ready"][: max(0, int(limit))]
    return ensure_geometry_dependencies(dependencies, root=ROOT)


def sync(*, with_shots: bool = False, force_refresh: bool = False, geometry_limit: int | None = None) -> SyncResult:
    """Run the full local sync idempotently and return a coverage summary."""
    if not _ensure_auth(force_refresh):
        return SyncResult(auth_ok=False, notes=["auth unavailable; cannot fetch"])
    before = _summary_observation()
    rounds = _fetch_history(with_shots, force_refresh_auth=force_refresh)
    after = _summary_observation()
    geometry = _ensure_geometry(limit=geometry_limit)
    notes: list[str] = []
    course_nines = 0
    course_reference_total = 0
    course_reference_ready = 0
    course_reference_missing = 0
    course_reference_coverage_pct = 0.0
    try:
        store = course_reference.build_played_store()
        course_nines = len(store)
        coverage = course_reference.course_reference_coverage()
        course_reference_total = int(coverage.get("total") or 0)
        course_reference_ready = int(coverage.get("ready") or 0)
        course_reference_missing = int(coverage.get("missing") or 0)
        course_reference_coverage_pct = float(coverage.get("pct") or 0.0)
    except Exception:
        notes.append("course-reference ingest failed (will retry on next sync)")
    scs, shots = _on_disk()
    if not shots:
        notes.append("shots not fetched (run with --shots for shot maps / decision evidence)")
    if geometry.get("failed"):
        notes.append(f"{geometry['failed']} hole(s) missing geometry (will retry on demand)")
    return SyncResult(
        auth_ok=True,
        rounds=rounds,
        scorecards=scs,
        shots=shots,
        course_nines=course_nines,
        geometry_attempted=int(geometry.get("attempted") or 0),
        geometry_failed=int(geometry.get("failed") or 0),
        course_reference_total=course_reference_total,
        course_reference_ready=course_reference_ready,
        course_reference_missing=course_reference_missing,
        course_reference_coverage_pct=course_reference_coverage_pct,
        remote_round_count=int(after["count"]),
        remote_latest_round_id=after["latestId"],
        remote_latest_round_at=after["latestAt"],
        new_round_count=(
            len(after["ids"] - before["ids"])
            if before["ids"]
            else int(after["count"])
        ),
        notes=notes,
    )


def main(argv: list[str] | None = None) -> int:
    import json
    import sys

    argv = sys.argv[1:] if argv is None else argv
    geometry_limit = _int_arg(argv, "--geometry-limit")
    result = sync(with_shots="--shots" in argv, force_refresh="--refresh-auth" in argv, geometry_limit=geometry_limit)
    try:
        _persist_sync_observability(result)
    except Exception:  # noqa: BLE001 - status persistence must not hide the sync result
        result.notes.append("sync status persistence failed (data sync result is still valid)")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.auth_ok else 1


def _int_arg(argv: list[str], name: str) -> int | None:
    prefix = f"{name}="
    for index, arg in enumerate(argv):
        if arg.startswith(prefix):
            return int(arg.split("=", 1)[1])
        if arg == name and index + 1 < len(argv):
            return int(argv[index + 1])
    return None


if __name__ == "__main__":
    raise SystemExit(main())
