from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from ai_caddie.data import ROOT

from .base import ConnectorState, SnapshotManifest

SYNC_DIR = Path("data") / "sync"
SNAPSHOT_DIR = Path("data") / "snapshots"
STATUS_FILE = SYNC_DIR / "garmin_cn_status.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _json_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(item for item in path.glob("*.json") if item.is_file())


def build_snapshot_manifest(*, root: Path = ROOT, snapshot_id: str) -> SnapshotManifest:
    data_dir = root / "data"
    summary = data_dir / "summary.json"
    scorecards = _json_files(data_dir / "scorecards")
    shots = _json_files(data_dir / "shots")
    files: list[str] = []
    if summary.exists():
        files.append(_relative(summary, root))
    files.extend(_relative(path, root) for path in scorecards)
    files.extend(_relative(path, root) for path in shots)
    return SnapshotManifest(
        snapshot_id=snapshot_id,
        scorecard_count=len(scorecards),
        shot_file_count=len(shots),
        summary_present=summary.exists(),
        files=files,
    )


def write_snapshot_manifest(*, root: Path = ROOT, manifest: SnapshotManifest) -> Path:
    out_dir = root / SNAPSHOT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{manifest.snapshot_id}.json"
    payload = {
        "schema": "ai-caddie-raw-snapshot-v1",
        "snapshotId": manifest.snapshot_id,
        "createdAt": _utc_now(),
        "scorecardCount": manifest.scorecard_count,
        "shotFileCount": manifest.shot_file_count,
        "summaryPresent": manifest.summary_present,
        "files": manifest.files,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def write_connector_status(
    *,
    root: Path = ROOT,
    state: ConnectorState,
    detail: str,
    snapshot_id: str | None,
    error_code: str | None = None,
) -> Path:
    out_dir = root / SYNC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = root / STATUS_FILE
    payload = {
        "schema": "ai-caddie-connector-status-v1",
        "connector": "garmin_cn_web_session",
        "state": state,
        "detail": detail,
        "snapshotId": snapshot_id,
        "errorCode": error_code,
        "updatedAt": _utc_now(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def read_connector_status(*, root: Path = ROOT) -> dict[str, Any] | None:
    path = root / STATUS_FILE
    if not path.exists():
        return None
    return json.loads(path.read_text())


def snapshot_to_payload(manifest: SnapshotManifest) -> dict[str, Any]:
    data = asdict(manifest)
    return {
        "snapshotId": data["snapshot_id"],
        "scorecardCount": data["scorecard_count"],
        "shotFileCount": data["shot_file_count"],
        "summaryPresent": data["summary_present"],
        "files": data["files"],
    }
