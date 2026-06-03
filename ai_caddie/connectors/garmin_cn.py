from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
import io
from pathlib import Path
from typing import Any, Iterator

from ai_caddie.data import ROOT
from ai_caddie.geometry_sync import ensure_prodgeometry
import fetch as fetch_module
import garmin_auth as garmin_auth_module
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


SECRET_META_KEY_TERMS = ("cookie", "csrf", "token", "secret", "authorization", "password")


def _sanitize_safe_meta(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = str(key)
            if any(term in safe_key.lower() for term in SECRET_META_KEY_TERMS):
                safe_key = "redacted"
            sanitized[safe_key] = _sanitize_safe_meta(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_safe_meta(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_safe_meta(item) for item in value]
    if isinstance(value, str):
        return sanitize_error(value)
    return value


@dataclass(frozen=True)
class GarminCnFetchRun:
    cards: list[dict[str, Any]]
    safe_meta: dict[str, Any]


@contextmanager
def _fetch_runtime(root: Path) -> Iterator[None]:
    """Bind the legacy fetch.py module to the connector root for this run."""

    data_dir = root / "data"
    token_dir = root / ".garmin_tokens"
    fetch_originals = {
        "TOKEN_DIR": fetch_module.TOKEN_DIR,
        "COOKIE_FILE": fetch_module.COOKIE_FILE,
        "CSRF_FILE": fetch_module.CSRF_FILE,
        "DATA_DIR": fetch_module.DATA_DIR,
        "SUMMARY_FILE": fetch_module.SUMMARY_FILE,
        "SCORECARD_DIR": fetch_module.SCORECARD_DIR,
        "SHOT_DIR": fetch_module.SHOT_DIR,
    }
    auth_originals = {
        "TOKEN_DIR": garmin_auth_module.TOKEN_DIR,
        "COOKIE_FILE": garmin_auth_module.COOKIE_FILE,
        "CSRF_FILE": garmin_auth_module.CSRF_FILE,
    }
    try:
        fetch_module.TOKEN_DIR = token_dir
        fetch_module.COOKIE_FILE = token_dir / "web_cookie.txt"
        fetch_module.CSRF_FILE = token_dir / "csrf.txt"
        fetch_module.DATA_DIR = data_dir
        fetch_module.SUMMARY_FILE = data_dir / "summary.json"
        fetch_module.SCORECARD_DIR = data_dir / "scorecards"
        fetch_module.SHOT_DIR = data_dir / "shots"
        garmin_auth_module.TOKEN_DIR = token_dir
        garmin_auth_module.COOKIE_FILE = token_dir / "web_cookie.txt"
        garmin_auth_module.CSRF_FILE = token_dir / "csrf.txt"
        yield
    finally:
        for name, value in fetch_originals.items():
            setattr(fetch_module, name, value)
        for name, value in auth_originals.items():
            setattr(garmin_auth_module, name, value)


class GarminCnFetchTransport:
    """Secret-safe adapter around the legacy Garmin CN fetch.py workflow."""

    def run(
        self,
        *,
        root: Path,
        with_shots: bool,
        force_refresh_auth: bool,
    ) -> GarminCnFetchRun:
        stdout_buffer = io.StringIO()
        stage = "make_session"
        with _fetch_runtime(root), redirect_stdout(stdout_buffer):
            session = make_session(force_refresh_auth=force_refresh_auth)
            stage = "fetch_summary"
            cards = fetch_summary(session)
            stage = "fetch_details"
            fetch_details(session, cards, with_shots=with_shots)
        stdout_text = stdout_buffer.getvalue()
        line_count = len([line for line in stdout_text.splitlines() if line.strip()])
        return GarminCnFetchRun(
            cards=cards,
            safe_meta={
                "transport": "fetch_py_adapter",
                "stdoutCaptured": bool(stdout_text),
                "stdoutLineCount": line_count,
                "lastStage": stage,
            },
        )


class GarminCnWebSessionConnector:
    def __init__(self, *, root: Path = ROOT, transport: GarminCnFetchTransport | None = None) -> None:
        self.root = root
        self.transport = transport or GarminCnFetchTransport()

    def sync(
        self,
        *,
        with_shots: bool,
        force_refresh_auth: bool,
        ensure_geometry: bool = False,
    ) -> ConnectorRunResult:
        try:
            run = self.transport.run(
                root=self.root,
                with_shots=with_shots,
                force_refresh_auth=force_refresh_auth,
            )
            cards = run.cards
            snapshot_id = _snapshot_id()
            manifest = build_snapshot_manifest(root=self.root, snapshot_id=snapshot_id)
            geometry_ensure = None
            if ensure_geometry:
                geometry_ensure = self._ensure_geometry_dependencies(manifest.geometry_dependencies)
                manifest = build_snapshot_manifest(root=self.root, snapshot_id=snapshot_id)
            write_snapshot_manifest(root=self.root, manifest=manifest)
            write_durable_snapshot(root=self.root, manifest=manifest)
            state = "ready" if manifest.scorecard_count else "no_data"
            if state == "ready":
                try:
                    from ai_caddie import course_reference
                    course_reference.build_played_store()
                except Exception:
                    pass  # course-ref is best-effort; never fail the sync on it
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
                safe_meta=_sanitize_safe_meta(
                    {
                        **run.safe_meta,
                        "withShots": with_shots,
                        "forceRefreshAuth": force_refresh_auth,
                        "cardCount": len(cards),
                        "geometryDependencyCount": manifest.geometry_dependency_count,
                        "geometryMissingCount": manifest.geometry_missing_count,
                        **({"geometryEnsure": geometry_ensure} if geometry_ensure is not None else {}),
                    }
                ),
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
                safe_meta=_sanitize_safe_meta({"sourceError": sanitize_error(exc)}),
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
                safe_meta=_sanitize_safe_meta({"sourceError": sanitize_error(exc)}),
            )

    def _ensure_geometry_dependencies(self, dependencies: list[dict[str, object]]) -> dict[str, int]:
        from .snapshot import ensure_geometry_dependencies
        return ensure_geometry_dependencies(dependencies, root=self.root)
