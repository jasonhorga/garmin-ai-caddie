"""Garmin CN web session material storage."""

from __future__ import annotations

import os
from pathlib import Path
import secrets
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


def _replace_private_file(path: Path, content: bytes) -> None:
    """Install ``content`` at ``path`` via a sibling temp file created 0600, fsynced, then ``os.replace``d."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _restore_session_files(previous: dict[Path, bytes | None]) -> None:
    # Best effort per file: one failed restore must not leave the other file replaced.
    for path, content in previous.items():
        try:
            if content is None:
                path.unlink(missing_ok=True)
            else:
                _replace_private_file(path, content)
        except Exception:
            continue


def save_garmin_cn_web_session(
    *,
    web_session_header: str,
    anti_forgery_value: str,
    source: str = "manual_paste",
    root: Path | str = ROOT,
    data_dir: Path | str | None = None,
) -> dict[str, Any]:
    # The cookie/csrf land at ``root/.garmin_tokens``. ``data_dir`` is the data partition
    # for the connector-status write (defaults to ``root/data`` for the owner, byte-for-byte);
    # a member passes their partition so binding never clobbers the owner's status.
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
    # A failure after validation must leave the previously working session byte-for-byte.
    previous = {path: path.read_bytes() if path.exists() else None for path in (web_session_path, anti_forgery_path)}
    detail = "Garmin CN web session saved for local sync. Run sync to refresh local data."
    try:
        _replace_private_file(web_session_path, (web_session + "\n").encode("utf-8"))
        _replace_private_file(anti_forgery_path, (anti_forgery + "\n").encode("utf-8"))

        write_connector_status(
            root=base,
            state="no_data",
            detail=detail,
            snapshot_id=None,
            # `no_data` is also the terminal state for a successful empty sync. Keep the import-only
            # state distinguishable so clients do not mark a freshly captured cookie as verified.
            error_code="session_stored",
            data_dir=Path(data_dir) if data_dir is not None else None,
        )
    except Exception:
        _restore_session_files(previous)
        raise
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
