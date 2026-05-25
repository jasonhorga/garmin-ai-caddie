from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from ai_caddie.data import ROOT
from fetch import fetch_details, fetch_summary, make_session

from .base import ConnectorRunResult
from .snapshot import build_snapshot_manifest, write_connector_status, write_snapshot_manifest

SECRET_PATTERNS = [
    re.compile(r"cookie[^\s]*\s*[^,;\n]*", re.IGNORECASE),
    re.compile(r"csrf[^\s]*\s*[^,;\n]*", re.IGNORECASE),
    re.compile(r"token[^\s]*\s*[^,;\n]*", re.IGNORECASE),
    re.compile(r"secret[^\s]*\s*[^,;\n]*", re.IGNORECASE),
    re.compile(r"authorization[^\s]*\s*[^,;\n]*", re.IGNORECASE),
]


def sanitize_error(message: object) -> str:
    text = str(message).replace(".garmin_tokens", "<credential-dir>")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("<redacted>", text)
    return text[:240]


def _snapshot_id() -> str:
    return "garmin_cn_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class GarminCnWebSessionConnector:
    def __init__(self, *, root: Path = ROOT) -> None:
        self.root = root

    def sync(self, *, with_shots: bool, force_refresh_auth: bool) -> ConnectorRunResult:
        try:
            session = make_session(force_refresh_auth=force_refresh_auth)
            cards = fetch_summary(session)
            fetch_details(session, cards, with_shots=with_shots)
            snapshot_id = _snapshot_id()
            manifest = build_snapshot_manifest(root=self.root, snapshot_id=snapshot_id)
            write_snapshot_manifest(root=self.root, manifest=manifest)
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
                safe_meta={"withShots": with_shots, "cardCount": len(cards)},
            )
        except SystemExit as exc:
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
