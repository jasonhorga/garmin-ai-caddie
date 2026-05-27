from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ConnectorName = Literal["garmin_cn_web_session", "garmin_oauth_feasibility"]
ConnectorState = Literal["ready", "no_data", "reauth_required", "error", "not_available"]


@dataclass(frozen=True)
class SnapshotManifest:
    snapshot_id: str
    scorecard_count: int
    shot_file_count: int
    summary_present: bool
    files: list[str]
    geometry_dependencies: list[dict[str, Any]] = field(default_factory=list)
    geometry_dependency_count: int = 0
    geometry_ready_count: int = 0
    geometry_missing_count: int = 0


@dataclass(frozen=True)
class ConnectorRunResult:
    connector: ConnectorName
    state: ConnectorState
    detail: str
    snapshot: SnapshotManifest | None = None
    error_code: str | None = None
    safe_meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.state == "ready"
