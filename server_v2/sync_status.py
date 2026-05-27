from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ai_caddie.config import DataMode, get_settings
from ai_caddie.connectors.garmin_oauth import build_oauth_feasibility_status
from ai_caddie.connectors.redaction import sanitize_secret_text
from ai_caddie.connectors.snapshot import discover_geometry_dependencies, read_connector_status
from ai_caddie.data import ROOT

from .models import ConnectorStatus, SnapshotStatus, SyncLastRunStatus, SyncStatusResponse


def _count_json_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.glob("*.json") if item.is_file())


def _last_sync_at(paths: list[Path]) -> str | None:
    existing: list[Path] = []
    for path in paths:
        if path.is_dir():
            existing.extend(item for item in path.glob("*.json") if item.is_file())
        elif path.exists():
            existing.append(path)
    if not existing:
        return None
    newest = max(existing, key=lambda path: path.stat().st_mtime)
    return (
        datetime.fromtimestamp(newest.stat().st_mtime, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _next_action(state: str) -> str | None:
    return {
        "no_data": "connect_garmin",
        "ready": "review_history",
        "reauth_required": "reauthenticate_garmin",
        "error": "inspect_sync_error",
    }.get(state)


def build_sync_status_response(
    *, root: Path = ROOT, data_mode: DataMode | None = None
) -> SyncStatusResponse:
    selected_mode = data_mode or get_settings().data_mode
    data_dir = root / "data"
    scorecard_dir = data_dir / "scorecards"
    shot_dir = data_dir / "shots"
    summary = data_dir / "summary.json"
    scorecard_count = _count_json_files(scorecard_dir)
    shot_file_count = _count_json_files(shot_dir)
    geometry_dependencies = discover_geometry_dependencies(root=root)
    has_data = scorecard_count > 0
    persisted = read_connector_status(root=root)
    persisted_state = persisted.get("state") if persisted else None
    if persisted_state in {"reauth_required", "error"}:
        state = persisted_state
        detail = sanitize_secret_text(persisted.get("detail") or "Garmin connector needs attention.")
    else:
        state = "ready" if has_data else "no_data"
        detail = (
            "Local Garmin snapshots are available."
            if has_data
            else "No local Garmin snapshots are loaded. Connect Garmin or use fixture mode."
        )
    resolved_mode = (
        "fixture"
        if selected_mode == "fixture"
        or (selected_mode == "local_or_fixture" and not has_data)
        else "local"
    )
    connector = ConnectorStatus(
        name="garmin_cn_web_session",
        state=state,
        detail=detail,
        canSync=state != "reauth_required",
        reauthRequired=state == "reauth_required",
        nextAction=_next_action(state),
    )
    oauth_connector = ConnectorStatus(**build_oauth_feasibility_status())
    last_run = None
    if persisted:
        last_run = SyncLastRunStatus(
            state=str(persisted.get("state") or "error"),
            detail=sanitize_secret_text(persisted.get("detail") or ""),
            snapshotId=persisted.get("snapshotId"),
            errorCode=persisted.get("errorCode"),
            updatedAt=persisted.get("updatedAt"),
        )
    return SyncStatusResponse(
        schema="ai-caddie-sync-status-v2",
        connector=connector,
        connectors=[connector, oauth_connector],
        snapshot=SnapshotStatus(
            dataMode=resolved_mode,
            scorecardCount=scorecard_count,
            shotFileCount=shot_file_count,
            summaryPresent=summary.exists(),
            lastSuccessfulSyncAt=_last_sync_at([summary, scorecard_dir, shot_dir]),
            geometryDependencyCount=len(geometry_dependencies),
            geometryReadyCount=sum(1 for row in geometry_dependencies if row.get("status") == "ready"),
            geometryMissingCount=sum(1 for row in geometry_dependencies if row.get("status") == "missing"),
            geometryDependencies=geometry_dependencies,
        ),
        lastRun=last_run,
    )


def load_sync_status_response() -> SyncStatusResponse:
    return build_sync_status_response()
