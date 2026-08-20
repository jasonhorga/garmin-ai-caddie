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
    notes: list[str] = field(default_factory=list)


def _sync_snapshot_id() -> str:
    return "garmin_cn_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _persist_sync_observability(result: SyncResult, *, root=ROOT) -> bool:
    """Persist the same small manifest/status contract used by API-triggered Garmin sync.

    The cron entrypoint historically called this module directly, so scorecards and shots were
    refreshed while ``/sync/status`` kept serving the previous run's metadata. Keep the legacy
    fetch path, but close that observability gap without copying the potentially large durable
    snapshot on every cron run.
    """
    from ai_caddie.connectors.snapshot import (
        build_snapshot_manifest,
        write_connector_status,
        write_snapshot_manifest,
    )

    if not result.auth_ok:
        write_connector_status(
            root=root,
            state="reauth_required",
            detail="Garmin CN web session is unavailable. Reconnect Garmin and retry.",
            snapshot_id=None,
            error_code="auth_failed",
        )
        return True

    snapshot_id = _sync_snapshot_id()
    manifest = build_snapshot_manifest(root=root, snapshot_id=snapshot_id)
    write_snapshot_manifest(root=root, manifest=manifest)
    state = "ready" if manifest.scorecard_count else "no_data"
    detail = (
        f"Synced {manifest.scorecard_count} scorecards and {manifest.shot_file_count} shot files."
        if state == "ready"
        else "Garmin sync completed, but no scorecards were returned."
    )
    write_connector_status(
        root=root,
        state=state,
        detail=detail,
        snapshot_id=snapshot_id,
        error_code=None,
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
    rounds = _fetch_history(with_shots, force_refresh_auth=force_refresh)
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
