from __future__ import annotations

from pathlib import Path

from ai_caddie.config import DataMode, get_settings
from ai_caddie.data import ROOT

from .models import ConnectorStatus, SnapshotStatus, SyncStatusResponse


def _count_json_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.glob("*.json") if item.is_file())


def _last_sync_at(paths: list[Path]) -> str | None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    newest = max(existing, key=lambda path: path.stat().st_mtime)
    return str(newest.stat().st_mtime_ns)


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
    has_data = scorecard_count > 0
    resolved_mode = (
        "fixture"
        if selected_mode == "fixture"
        or (selected_mode == "local_or_fixture" and not has_data)
        else "local"
    )
    connector = ConnectorStatus(
        name="garmin_cn_web_session",
        state="ready" if has_data else "no_data",
        detail=(
            "Local Garmin snapshots are available."
            if has_data
            else "No local Garmin snapshots are loaded. Connect Garmin or use fixture mode."
        ),
        canSync=False,
        reauthRequired=False,
    )
    return SyncStatusResponse(
        schema="ai-caddie-sync-status-v2",
        connector=connector,
        snapshot=SnapshotStatus(
            dataMode=resolved_mode,
            scorecardCount=scorecard_count,
            shotFileCount=shot_file_count,
            summaryPresent=summary.exists(),
            lastSuccessfulSyncAt=_last_sync_at([summary, scorecard_dir, shot_dir]),
        ),
    )


def load_sync_status_response() -> SyncStatusResponse:
    return build_sync_status_response()
