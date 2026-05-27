from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ai_caddie.data import ROOT
from ai_caddie.geometry_sync import ensure_prodgeometry
from fetch import GarminAuthExpired, fetch_details, fetch_summary, make_session

from .base import ConnectorRunResult
from .redaction import sanitize_secret_text
from .snapshot import (
    build_snapshot_manifest,
    geometry_player_profile_id,
    write_connector_status,
    write_durable_snapshot,
    write_snapshot_manifest,
)


def sanitize_error(message: object) -> str:
    return sanitize_secret_text(message)


def _snapshot_id() -> str:
    return "garmin_cn_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class GarminCnWebSessionConnector:
    def __init__(self, *, root: Path = ROOT) -> None:
        self.root = root

    def sync(
        self,
        *,
        with_shots: bool,
        force_refresh_auth: bool,
        ensure_geometry: bool = False,
    ) -> ConnectorRunResult:
        try:
            session = make_session(force_refresh_auth=force_refresh_auth)
            cards = fetch_summary(session)
            fetch_details(session, cards, with_shots=with_shots)
            snapshot_id = _snapshot_id()
            manifest = build_snapshot_manifest(root=self.root, snapshot_id=snapshot_id)
            geometry_ensure = None
            if ensure_geometry:
                geometry_ensure = self._ensure_geometry_dependencies(manifest.geometry_dependencies)
                manifest = build_snapshot_manifest(root=self.root, snapshot_id=snapshot_id)
            write_snapshot_manifest(root=self.root, manifest=manifest)
            write_durable_snapshot(root=self.root, manifest=manifest)
            state = "ready" if manifest.scorecard_count else "no_data"
            detail = (
                f"Synced {manifest.scorecard_count} scorecards and {manifest.shot_file_count} shot files."
                if state == "ready"
                else "Garmin sync completed, but no scorecards were returned."
            )
            write_connector_status(
                root=self.root,
                state=state,
                detail=detail,
                snapshot_id=snapshot_id,
            )
            return ConnectorRunResult(
                connector="garmin_cn_web_session",
                state=state,
                detail=detail,
                snapshot=manifest,
                safe_meta={
                    "withShots": with_shots,
                    "cardCount": len(cards),
                    "geometryDependencyCount": manifest.geometry_dependency_count,
                    "geometryMissingCount": manifest.geometry_missing_count,
                    **({"geometryEnsure": geometry_ensure} if geometry_ensure is not None else {}),
                },
            )
        except (GarminAuthExpired, SystemExit) as exc:
            detail = "Garmin CN session expired or missing. Reconnect Garmin and retry."
            write_connector_status(
                root=self.root,
                state="reauth_required",
                detail=detail,
                snapshot_id=None,
                error_code="auth_failed",
            )
            return ConnectorRunResult(
                connector="garmin_cn_web_session",
                state="reauth_required",
                detail=detail,
                error_code="auth_failed",
                safe_meta={"sourceError": sanitize_error(exc)},
            )
        except Exception as exc:
            detail = "Garmin CN sync failed before a complete snapshot was written."
            write_connector_status(
                root=self.root,
                state="error",
                detail=detail,
                snapshot_id=None,
                error_code="sync_failed",
            )
            return ConnectorRunResult(
                connector="garmin_cn_web_session",
                state="error",
                detail=detail,
                error_code="sync_failed",
                safe_meta={"sourceError": sanitize_error(exc)},
            )

    def _ensure_geometry_dependencies(self, dependencies: list[dict[str, object]]) -> dict[str, int]:
        profile_id = geometry_player_profile_id(root=self.root)
        summary = {"attempted": 0, "cached": 0, "downloaded": 0, "failed": 0, "skipped": 0}
        for row in dependencies:
            if row.get("status") == "ready":
                summary["cached"] += 1
                continue
            global_id = row.get("globalId")
            local_hole = row.get("localHole")
            if profile_id is None or global_id is None or local_hole is None:
                summary["skipped"] += 1
                continue
            summary["attempted"] += 1
            result = ensure_prodgeometry(int(global_id), int(local_hole), profile_id=profile_id, force=False)
            status = str(result.get("status") or "failed")
            if status == "cached":
                summary["cached"] += 1
            elif status == "downloaded":
                summary["downloaded"] += 1
            else:
                summary["failed"] += 1
        return summary
