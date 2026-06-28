from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
import io
from pathlib import Path
from typing import Any, Iterator

import requests

from ai_caddie.core.data import ROOT
from ai_caddie.garmin import fetch as fetch_module
from ai_caddie.garmin import garmin_auth as garmin_auth_module
from ai_caddie.garmin.fetch import GarminAuthExpired
from ai_caddie.rounds.players import OWNER_ID

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
                # P1-9: a key NAMED cookie/token/secret/… means the VALUE is the secret.
                # Redact the value (not the key) so the meta stays legible without leaking it.
                sanitized[safe_key] = "[redacted]"
            else:
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


def garmin_token_dir(player_id: str | None, root: Path = ROOT) -> Path:
    """The directory holding a player's captured Garmin cookie/csrf.

    Owner ("me", or ``None``) keeps the flat ``ROOT/.garmin_tokens`` (byte-for-byte). A
    family member gets ``ROOT/data/players/<id>/.garmin_tokens`` — INSIDE their data
    partition, so their cookie is never read by the owner's sync and vice-versa.
    """
    if player_id is None or player_id == OWNER_ID:
        return root / ".garmin_tokens"
    return root / "data" / "players" / player_id / ".garmin_tokens"


def _player_data_dir(player_id: str | None, root: Path = ROOT) -> Path:
    """The per-data-source partition for a player's scorecards/shots/summary.

    Owner → ``ROOT/data`` (byte-for-byte). Member → ``ROOT/data/players/<id>`` (NO extra
    ``data/`` level), matching ``history._player_data_dir`` / ``round_ingest`` so the
    sync lands where the player's history readers look."""
    if player_id is None or player_id == OWNER_ID:
        return root / "data"
    return root / "data" / "players" / player_id


@contextmanager
def _fetch_runtime(*, token_dir: Path, data_dir: Path, allow_self_heal: bool = True) -> Iterator[None]:
    """Bind the legacy fetch.py module to an EXPLICIT cookie dir + data dir for this run.

    The cookie store (``token_dir``) and the data store (``data_dir``) are decoupled so a
    member sync can read its OWN cookie (``data/players/<id>/.garmin_tokens``) and write to
    its OWN partition (``data/players/<id>``) while the owner keeps ``ROOT/.garmin_tokens``
    + ``ROOT/data`` unchanged. ALL data files are repointed at ``data_dir`` — including
    ``CLUBS_BAG_FILE`` (frozen at import to ``ROOT/data/club_bag.json``), or a member's
    ``fetch_clubs`` would clobber the OWNER's bag.

    ``allow_self_heal=False`` (members) also neutralises the legacy fetch internals' browser/
    Playwright self-heal: every fetch stage retries a mid-sync 401/403 via the module-level
    ``refresh_session_auth`` -> ``ensure_web_auth(force=True)``, which is owner-only (it pulls
    from the machine browser / owner Playwright creds). A member must NEVER trigger it, so for
    the duration of the run we replace it with a clean ``GarminAuthExpired`` ("re-bind"), which
    the transport maps to ``reauth_required`` — never an owner re-auth, never a 500.
    """

    fetch_originals = {
        "TOKEN_DIR": fetch_module.TOKEN_DIR,
        "COOKIE_FILE": fetch_module.COOKIE_FILE,
        "CSRF_FILE": fetch_module.CSRF_FILE,
        "DATA_DIR": fetch_module.DATA_DIR,
        "SUMMARY_FILE": fetch_module.SUMMARY_FILE,
        "SCORECARD_DIR": fetch_module.SCORECARD_DIR,
        "SHOT_DIR": fetch_module.SHOT_DIR,
        "CLUBS_BAG_FILE": fetch_module.CLUBS_BAG_FILE,
        "refresh_session_auth": fetch_module.refresh_session_auth,
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
        fetch_module.CLUBS_BAG_FILE = data_dir / "club_bag.json"
        garmin_auth_module.TOKEN_DIR = token_dir
        garmin_auth_module.COOKIE_FILE = token_dir / "web_cookie.txt"
        garmin_auth_module.CSRF_FILE = token_dir / "csrf.txt"
        if not allow_self_heal:
            def _member_no_self_heal(_session) -> bool:
                raise GarminAuthExpired(
                    "Garmin session expired for this player. Re-bind your Garmin."
                )

            fetch_module.refresh_session_auth = _member_no_self_heal
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


class MemberGarminCnAuthProvider(GarminCnAuthProvider):
    """Auth for a family member: read ONLY the member's captured cookie, NEVER self-heal.

    The owner self-heal (``ensure_web_auth`` → browser_cookie3 / headed-Playwright login)
    uses the single global owner profile + credentials, so a member must never trigger it:
    a member with a missing/expired cookie fails with a clear ``GarminAuthExpired``
    ("re-bind your Garmin"), and we never fall back to the owner's cookie or browser
    profile. The cookie/csrf files are scoped to the member's token dir by ``_fetch_runtime``.
    """

    def make_session(self, *, force_refresh_auth: bool):
        # force_refresh_auth is intentionally ignored — members have no stored creds to
        # re-mint with, and self-healing would mean using the owner's profile.
        cookie_file = garmin_auth_module.COOKIE_FILE
        csrf_file = garmin_auth_module.CSRF_FILE
        cookie = cookie_file.read_text().strip() if cookie_file.exists() else ""
        csrf = csrf_file.read_text().strip() if csrf_file.exists() else ""
        if not cookie or not csrf:
            raise GarminAuthExpired(
                "Garmin session missing or expired for this player. Re-bind your Garmin."
            )
        auth = garmin_auth_module.GarminWebAuth(cookie, csrf, "member-cache", cookie.count("="))
        session = requests.Session()
        session.headers.update(garmin_auth_module.auth_headers(auth))
        return session

    def refresh_session(self, session) -> bool:
        return False  # members never self-heal (no stored member credentials)


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
        token_dir: Path,
        data_dir: Path,
        with_shots: bool,
        force_refresh_auth: bool,
        allow_self_heal: bool = True,
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
        with _fetch_runtime(
            token_dir=token_dir, data_dir=data_dir, allow_self_heal=allow_self_heal
        ), redirect_stdout(stdout_buffer):
            session = self.auth_provider.make_session(force_refresh_auth=force_refresh_auth)
            safe_meta["lastStage"] = "fetch_summary"
            cards = self._run_stage(lambda: fetch_module.fetch_summary(session), session=session, safe_meta=safe_meta)
            safe_meta["lastStage"] = "fetch_details"
            self._run_stage(
                lambda: fetch_module.fetch_details(session, cards, with_shots=with_shots),
                session=session,
                safe_meta=safe_meta,
            )
            # Best-effort club-bag refresh — mirrors the CLI _fetch_history (P1-5): the in-app Sync
            # used to run summary+details only, leaving a stale bag (the documented club 401). Reuses
            # the same session; a club-fetch failure must NEVER fail the sync (summary/details are the
            # critical path), so it is swallowed + recorded and lastStage stays on the critical path.
            try:
                fetch_module.fetch_clubs(session)
                safe_meta["clubFetchOk"] = True
            except BaseException as exc:  # noqa: BLE001 — best-effort enrichment
                safe_meta["clubFetchOk"] = False
                safe_meta["clubFetchError"] = sanitize_error(str(exc))
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
    def __init__(
        self,
        *,
        root: Path = ROOT,
        player_id: str | None = None,
        transport: GarminCnFetchTransport | None = None,
    ) -> None:
        self.root = root
        self.player_id = player_id or OWNER_ID
        self.is_owner = self.player_id == OWNER_ID
        # Cookie store + data partition are decoupled (see _fetch_runtime): owner keeps the
        # flat ROOT layout (byte-for-byte); a member is scoped to data/players/<id>.
        self.token_dir = garmin_token_dir(self.player_id, root)
        self.data_dir = _player_data_dir(self.player_id, root)
        if transport is None:
            # The owner self-heals (browser/Playwright); a member never does (no stored creds).
            provider = None if self.is_owner else MemberGarminCnAuthProvider()
            transport = GarminCnFetchTransport(auth_provider=provider)
        self.transport = transport

    def sync(
        self,
        *,
        with_shots: bool,
        force_refresh_auth: bool,
        ensure_geometry: bool = False,
    ) -> ConnectorRunResult:
        try:
            run = self.transport.run(
                token_dir=self.token_dir,
                data_dir=self.data_dir,
                with_shots=with_shots,
                force_refresh_auth=force_refresh_auth,
                # Members never browser/Playwright self-heal (owner-only); a rejected member
                # cookie surfaces as reauth_required, never an owner re-auth.
                allow_self_heal=self.is_owner,
            )
            cards = run.cards
            snapshot_id = _snapshot_id()
            manifest = build_snapshot_manifest(root=self.root, snapshot_id=snapshot_id, data_dir=self.data_dir)
            geometry_ensure = None
            # Geometry ensure + the durable normalized snapshot + the shared course-ref store are
            # the OWNER's mechanisms (the durable snapshot is read owner-only; geometry uses the
            # owner profile id; course geometry/par is shared public data). A member reads their
            # flat per-player scorecards/shots directly, so we skip them and never touch owner state.
            if ensure_geometry and self.is_owner:
                geometry_ensure = self._ensure_geometry_dependencies(manifest.geometry_dependencies)
                manifest = build_snapshot_manifest(root=self.root, snapshot_id=snapshot_id, data_dir=self.data_dir)
            if self.is_owner:
                write_snapshot_manifest(root=self.root, manifest=manifest)
                write_durable_snapshot(root=self.root, manifest=manifest)
            state = "ready" if manifest.scorecard_count else "no_data"
            if state == "ready" and self.is_owner:
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
                data_dir=self.data_dir,
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
                data_dir=self.data_dir,
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
                data_dir=self.data_dir,
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
