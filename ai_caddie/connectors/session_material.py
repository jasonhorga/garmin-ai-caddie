"""Garmin CN web session material storage."""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import shutil
from typing import Any

from ai_caddie.core.data import ROOT

from .snapshot import write_connector_status


SESSION_DIR = ".garmin_tokens"
WEB_SESSION_FILE = "web_cookie.txt"
ANTI_FORGERY_FILE = "csrf.txt"
GENERATIONS_DIR = "generations"
CURRENT_FILE = "current"
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


def _fsync_directory(path: Path) -> None:
    """Make directory entry changes durable on filesystems that support fsync."""
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_generation_file(path: Path, content: bytes) -> None:
    """Create one immutable generation member with private permissions and fsync it."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _valid_generation_name(value: str) -> bool:
    return bool(value) and value not in {".", ".."} and "/" not in value and "\\" not in value


def _current_generation_dir(token_dir: Path) -> Path | None:
    pointer = token_dir / CURRENT_FILE
    if not pointer.is_file():
        return None
    try:
        name = pointer.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    if not _valid_generation_name(name):
        return None
    generation = token_dir / GENERATIONS_DIR / name
    if not generation.is_dir():
        return None
    return generation


def read_session_material(token_dir: Path | str) -> tuple[str, str] | None:
    """Read cookie and CSRF from one immutable generation, with legacy fallback.

    A valid pointer is authoritative: if either member is missing, return no session rather
    than combining a generation member with a legacy file. Older flat layouts remain readable
    until their first successful generation write.
    """
    directory = Path(token_dir)
    generation = _current_generation_dir(directory)
    pointer_exists = (directory / CURRENT_FILE).is_file()
    if pointer_exists and generation is not None:
        cookie_path = generation / WEB_SESSION_FILE
        csrf_path = generation / ANTI_FORGERY_FILE
        if not cookie_path.is_file() or not csrf_path.is_file():
            return None
    elif pointer_exists:
        # A corrupt pointer is authoritative; never mix it with legacy files.
        return None
    else:
        cookie_path = directory / WEB_SESSION_FILE
        csrf_path = directory / ANTI_FORGERY_FILE
    if not cookie_path.is_file() or not csrf_path.is_file():
        return None
    try:
        cookie = cookie_path.read_text(encoding="utf-8").strip()
        csrf = csrf_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not cookie or not csrf:
        return None
    return cookie, csrf


def _publish_generation(token_dir: Path, web_session: str, anti_forgery: str) -> str:
    """Write a complete generation, then atomically publish its pointer."""
    token_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    token_dir.chmod(0o700)
    generations = token_dir / GENERATIONS_DIR
    generations.mkdir(mode=0o700, exist_ok=True)
    generations.chmod(0o700)
    generation_name = f"generation-{os.getpid()}-{secrets.token_hex(12)}"
    generation = generations / generation_name
    generation.mkdir(mode=0o700)
    pointer_tmp: Path | None = None
    pointer_published = False
    try:
        _write_generation_file(generation / WEB_SESSION_FILE, (web_session + "\n").encode("utf-8"))
        _write_generation_file(generation / ANTI_FORGERY_FILE, (anti_forgery + "\n").encode("utf-8"))
        _fsync_directory(generation)

        pointer_tmp = token_dir / f".{CURRENT_FILE}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
        _write_generation_file(pointer_tmp, (generation_name + "\n").encode("ascii"))
        os.replace(pointer_tmp, token_dir / CURRENT_FILE)
        pointer_published = True
        _fsync_directory(token_dir)
        _fsync_directory(generations)
    except Exception:
        if pointer_tmp is not None:
            pointer_tmp.unlink(missing_ok=True)
        if not pointer_published:
            shutil.rmtree(generation, ignore_errors=True)
        raise
    return generation_name


def save_session_material(*, token_dir: Path | str, web_session: str, anti_forgery: str) -> None:
    """Store an already validated cookie/CSRF pair using generation publication."""
    directory = Path(token_dir)
    _publish_generation(directory, web_session, anti_forgery)
    _remove_legacy_files(directory)


def _remove_legacy_files(token_dir: Path) -> None:
    """Drop flat-layout copies after a generation has become authoritative."""
    for name in (WEB_SESSION_FILE, ANTI_FORGERY_FILE):
        try:
            (token_dir / name).unlink(missing_ok=True)
        except OSError:
            continue


def _cleanup_token_dir(token_dir: Path) -> None:
    if not token_dir.is_dir():
        return
    # SIGKILL can leave either a file temp or an unfinished generation behind.
    for path in sorted(token_dir.rglob("*.tmp"), key=lambda item: len(item.parts), reverse=True):
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        except OSError:
            continue
    generations = token_dir / GENERATIONS_DIR
    if not generations.is_dir():
        return
    current = _current_generation_dir(token_dir)
    for child in generations.iterdir():
        if current is not None and child == current:
            continue
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
        except OSError:
            continue


def cleanup_session_material(root: Path | str = ROOT) -> None:
    """Remove session temp files and orphan generations for owner and member partitions."""
    base = Path(root)
    candidates = [base / SESSION_DIR]
    players = base / "data" / "players"
    if players.is_dir():
        candidates.extend(path / SESSION_DIR for path in players.iterdir() if path.is_dir())
    for token_dir in candidates:
        _cleanup_token_dir(token_dir)


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
    pointer = token_dir / CURRENT_FILE
    previous_pointer = pointer.read_bytes() if pointer.exists() else None
    detail = "Garmin CN web session saved for local sync. Run sync to refresh local data."
    try:
        _publish_generation(token_dir, web_session, anti_forgery)

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
        _remove_legacy_files(token_dir)
    except Exception:
        if previous_pointer is None:
            pointer.unlink(missing_ok=True)
            shutil.rmtree(token_dir / GENERATIONS_DIR, ignore_errors=True)
        else:
            _replace_private_file(pointer, previous_pointer)
            _cleanup_token_dir(token_dir)
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
