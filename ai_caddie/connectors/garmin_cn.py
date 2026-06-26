from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
import io
from pathlib import Path
from typing import Any, Iterator

from ai_caddie.core.data import ROOT
from ai_caddie.garmin import fetch as fetch_module
from ai_caddie.garmin import garmin_auth as garmin_auth_module
from ai_caddie.garmin.fetch import GarminAuthExpired

from .base import ConnectorRunResult
from .redaction import sanitize_secret_text
from .snapshot import (
    build_snapshot_manifest,
    write_connector_status,
    write_durable_snapshot,
    write_snapshot_manifest,
)


def sanitize_error(message: object) -> str:
    return sanitize_secret_text(message)


def _snapshot_id() -> str:
    return "garmin_cn_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


SECRET_META_KEY_TERMS = ("cookie", "csrf", "token", "secret", "authorization", "password")


def sanitize_safe_meta(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = str(key)
            if any(term in safe_key.lower() for term in SECRET_META_KEY_TERMS):
                safe_key = "redacted"
            sanitized[safe_key] = sanitize_safe_meta(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_safe_meta(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_safe_meta(item) for item in value]
    if isinstance(value, str):
        return sanitize_error(value)
    return value


_sanitize_safe_meta = sanitize_safe_meta


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


class GarminCnTransportAuthError(GarminAuthExpired):
    def __init__(self, message: str, *, safe_meta: dict[str, Any]) -> None:
        super().__init__(message)
        self.safe_meta = safe_meta


class GarminCnAuthProvider:
    def make_session(self, *, force_refresh_auth: bool):
        return fetch_module.make_session(force_refresh_auth=force_refresh_auth)

    def refresh_session(self, session) -> bool:
        return fetch_module.refresh_session_auth(session)


def _is_auth_failure(exc: BaseException) -> bool:
    if isinstance(exc, GarminAuthExpired):
        return True
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code in (401, 403)


class GarminCnFetchTransport:
    """Secret-safe adapter around the legacy Garmin CN fetch.py workflow."""

    def __init__(self, *, auth_provider: GarminCnAuthProvider | None = None) -> None:
        self.auth_provider = auth_provider or GarminCnAuthProvider()

    def run(
        self,
        *,
        root: Path,
        with_shots: bool,
        force_refresh_auth: bool,
    ) -> GarminCnFetchRun:
        stdout_buffer = io.StringIO()
        safe_meta: dict[str, Any] = {
            "transport": "fetch_py_adapter",
            "forceRefreshAuth": force_refresh_auth,
            "authRefreshAttempted": False,
            "authRefreshSucceeded": False,
            "authRetryCount": 0,
            "lastStage": "make_session",
        }
        with _fetch_runtime(root), redirect_stdout(stdout_buffer):
            session = self.auth_provider.make_session(force_refresh_auth=force_refresh_auth)
            safe_meta["lastStage"] = "fetch_summary"
            cards = self._run_stage(lambda: fetch_module.fetch_summary(session), session=session, safe_meta=safe_meta)
            safe_meta["lastStage"] = "fetch_details"
            self._run_stage(
                lambda: fetch_module.fetch_details(session, cards, with_shots=with_shots),
                session=session,
                safe_meta=safe_meta,
            )
        stdout_text = stdout_buffer.getvalue()
        line_count = len([line for line in stdout_text.splitlines() if line.strip()])
        safe_meta["stdoutCaptured"] = bool(stdout_text)
        safe_meta["stdoutLineCount"] = line_count
        return GarminCnFetchRun(cards=cards, safe_meta=sanitize_safe_meta(safe_meta))

    def _run_stage(self, operation, *, session, safe_meta: dict[str, Any]):
        try:
            return operation()
        except BaseException as exc:
            if not _is_auth_failure(exc):
                raise
            if safe_meta["authRefreshAttempted"]:
                raise GarminCnTransportAuthError(
                    "Garmin CN session still failed after one auth refresh retry.",
                    safe_meta=safe_meta,
                ) from exc
            safe_meta["authRefreshAttempted"] = True
            safe_meta["authRefreshSucceeded"] = bool(self.auth_provider.refresh_session(session))
            if not safe_meta["authRefreshSucceeded"]:
                raise GarminCnTransportAuthError(
                    "Garmin CN auth refresh failed during fetch.",
                    safe_meta=safe_meta,
                ) from exc
            safe_meta["authRetryCount"] = int(safe_meta["authRetryCount"]) + 1
            try:
                return operation()
            except BaseException as retry_exc:
                if _is_auth_failure(retry_exc):
                    raise GarminCnTransportAuthError(
                        "Garmin CN session still failed after one auth refresh retry.",
                        safe_meta=safe_meta,
                    ) from retry_exc
                raise


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
                    from ai_caddie.courses import course_reference
                    course_reference.build_played_store(root=self.root)
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
                safe_meta=sanitize_safe_meta(
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
            safe_meta = {"sourceError": sanitize_error(exc)}
            safe_meta.update(getattr(exc, "safe_meta", {}))
            return ConnectorRunResult(
                connector="garmin_cn_web_session",
                state="reauth_required",
                detail=detail,
                error_code="auth_failed",
                safe_meta=sanitize_safe_meta(safe_meta),
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
                safe_meta=sanitize_safe_meta({"sourceError": sanitize_error(exc)}),
            )

    def _ensure_geometry_dependencies(self, dependencies: list[dict[str, object]]) -> dict[str, int]:
        from .snapshot import ensure_geometry_dependencies
        return ensure_geometry_dependencies(dependencies, root=self.root)
