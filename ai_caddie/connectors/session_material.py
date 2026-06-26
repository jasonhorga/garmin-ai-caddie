"""Garmin CN web session material storage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_caddie.core.data import ROOT

from .snapshot import write_connector_status


SESSION_DIR = ".garmin_tokens"
WEB_SESSION_FILE = "web_cookie.txt"
ANTI_FORGERY_FILE = "csrf.txt"
ALLOWED_SESSION_SOURCES = {"manual_paste", "web_secure_paste", "ios_secure_input", "ios_keychain_replay", "ios_web_login"}


def _single_line(value: str, field: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field} is required")
    if "\n" in cleaned or "\r" in cleaned:
        raise ValueError(f"{field} must be a single line")
    return cleaned


def _strip_header_prefix(value: str, prefix: str) -> str:
    name, separator, rest = value.partition(":")
    if separator and name.strip().lower() == prefix.lower():
        return rest.strip()
    return value


def _session_field_count(web_session_header: str) -> int:
    return len([part for part in web_session_header.split(";") if "=" in part])


def _session_source(value: str | None) -> str:
    source = str(value or "manual_paste").strip()
    if source not in ALLOWED_SESSION_SOURCES:
        raise ValueError("session source is not supported")
    return source


def save_garmin_cn_web_session(
    *,
    web_session_header: str,
    anti_forgery_value: str,
    source: str = "manual_paste",
    root: Path | str = ROOT,
) -> dict[str, Any]:
    web_session = _strip_header_prefix(_single_line(web_session_header, "web session header"), "cookie")
    anti_forgery = _strip_header_prefix(_single_line(anti_forgery_value, "anti-forgery value"), "connect-csrf-token")
    import_source = _session_source(source)
    web_session = _single_line(web_session, "web session header")
    anti_forgery = _single_line(anti_forgery, "anti-forgery value")
    if "=" not in web_session:
        raise ValueError("web session header must include at least one name=value field")

    base = Path(root)
    token_dir = base / SESSION_DIR
    token_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    token_dir.chmod(0o700)
    web_session_path = token_dir / WEB_SESSION_FILE
    anti_forgery_path = token_dir / ANTI_FORGERY_FILE
    web_session_path.write_text(web_session + "\n", encoding="utf-8")
    anti_forgery_path.write_text(anti_forgery + "\n", encoding="utf-8")
    web_session_path.chmod(0o600)
    anti_forgery_path.chmod(0o600)

    detail = "Garmin CN web session saved for local sync. Run sync to refresh local data."
    write_connector_status(
        root=base,
        state="no_data",
        detail=detail,
        snapshot_id=None,
        error_code=None,
    )
    return {
        "schema": "ai-caddie-garmin-session-import-v1",
        "connector": "garmin_cn_web_session",
        "state": "stored",
        "detail": detail,
        "sessionFieldCount": _session_field_count(web_session),
        "antiForgeryPresent": bool(anti_forgery),
        "source": import_source,
        "acceptedSources": sorted(ALLOWED_SESSION_SOURCES),
    }
