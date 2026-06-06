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

from ai_caddie import course_reference
from ai_caddie.data import ROOT, SCORECARD_DIR, SHOT_DIR


@dataclass
class SyncResult:
    auth_ok: bool
    rounds: int = 0
    scorecards: int = 0
    shots: int = 0
    course_nines: int = 0
    notes: list[str] = field(default_factory=list)


def _ensure_auth(force_refresh: bool) -> bool:
    """Ensure a usable web session, refreshing (Playwright fallback on a server) if needed."""
    try:
        from garmin_auth import ensure_web_auth, validate_web_auth

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
    import fetch

    session = fetch.make_session(force_refresh_auth=force_refresh_auth)
    cards = fetch.fetch_summary(session)
    fetch.fetch_details(session, cards, with_shots=with_shots)
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
    from ai_caddie.stats_cache import cached_load_history_data

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
    store = course_reference.build_played_store()
    scs, shots = _on_disk()
    notes: list[str] = []
    if not shots:
        notes.append("shots not fetched (run with --shots for shot maps / decision evidence)")
    if geometry.get("failed"):
        notes.append(f"{geometry['failed']} hole(s) missing geometry (will retry on demand)")
    return SyncResult(
        auth_ok=True,
        rounds=rounds,
        scorecards=scs,
        shots=shots,
        course_nines=len(store),
        notes=notes,
    )


def main(argv: list[str] | None = None) -> int:
    import json
    import sys

    argv = sys.argv[1:] if argv is None else argv
    geometry_limit = _int_arg(argv, "--geometry-limit")
    result = sync(with_shots="--shots" in argv, force_refresh="--refresh-auth" in argv, geometry_limit=geometry_limit)
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
