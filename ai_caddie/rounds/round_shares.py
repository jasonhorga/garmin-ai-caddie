"""Crash-safe, hashed capabilities for anonymous read-only round shares.

The share token is deliberately a capability rather than a player credential.  Only its
SHA-256 digest is persisted; the clear token is returned once by the create endpoint and is
never recoverable from the data directory.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import fcntl
import hashlib
import json
from pathlib import Path
import re
import secrets
import threading
from typing import Any, Iterable, Iterator

from ai_caddie.core.data import atomic_write_json, safe_read_json
from ai_caddie.rounds import players


SCHEMA = "ai-caddie-round-shares-v1"
DEFAULT_TTL = timedelta(days=30)
MAX_ACTIVE_PER_ROUND = 20
TOKEN_BYTES = 32
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")

_LOCKS: dict[Path, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _path(root: Path | str | None = None) -> Path:
    # Resolve the players root at call time.  Tests and local deployments patch players.ROOT,
    # and a module-level Path would otherwise silently write to the repository.
    return players._players_dir(root) / "round_shares.json"


def _lock_path(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


def _thread_lock(path: Path) -> threading.RLock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(path, threading.RLock())


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    lock = _thread_lock(path)
    with lock:
        lock_file = _lock_path(path)
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        with lock_file.open("a+", encoding="ascii") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def hash_token(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_format_ok(token: str | None) -> bool:
    return bool(_TOKEN_RE.fullmatch(str(token or "")))


def _empty() -> dict[str, Any]:
    return {"schema": SCHEMA, "shares": {}}


def _load(path: Path) -> dict[str, Any]:
    raw = safe_read_json(path, _empty())
    if not isinstance(raw, dict) or not isinstance(raw.get("shares"), dict):
        return _empty()
    return {"schema": SCHEMA, "shares": dict(raw["shares"])}


def _write(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(path, payload)


def _active(row: dict[str, Any], now: datetime) -> bool:
    if row.get("revokedAt"):
        return False
    expires = _parse_time(row.get("expiresAt"))
    return expires is not None and expires > now


def _prune_for_write(payload: dict[str, Any], now: datetime) -> None:
    shares = payload["shares"]
    payload["shares"] = {
        key: value for key, value in shares.items()
        if isinstance(value, dict) and _active(value, now)
    }


def create_share(
    player_id: str,
    round_ref: str,
    *,
    round_refs: Iterable[str] | None = None,
    root: Path | str | None = None,
    ttl: timedelta = DEFAULT_TTL,
    max_active: int = MAX_ACTIVE_PER_ROUND,
) -> dict[str, Any] | None:
    """Create a fresh share and return its clear token plus its persisted metadata.

    ``None`` means the per-round active-link cap has been reached.  Callers should map this
    to HTTP 429, keeping the same response for every cap/rate-limit rejection.
    """
    path = _path(root)
    now = _now()
    ref_set = {str(value) for value in (round_refs or (round_ref,))}
    ref_set.add(str(round_ref))
    with _file_lock(path):
        payload = _load(path)
        _prune_for_write(payload, now)
        active_for_round = [
            row for row in payload["shares"].values()
            if isinstance(row, dict) and row.get("playerId") == player_id
            and str(row.get("roundRef")) in ref_set and _active(row, now)
        ]
        if len(active_for_round) >= max_active:
            return None
        token = secrets.token_urlsafe(TOKEN_BYTES)
        # token_urlsafe(32) is 43 characters.  Keep the guard in case an alternate secrets
        # implementation is injected by a test or a future runtime.
        while not token_format_ok(token):
            token = secrets.token_urlsafe(TOKEN_BYTES)
        created = _iso(now)
        expires = _iso(now + ttl)
        share_id = secrets.token_hex(16)
        row = {
            "shareId": share_id,
            "tokenHash": hash_token(token),
            "tokenLast4": token[-4:],
            "playerId": str(player_id),
            "roundRef": str(round_ref),
            "createdAt": created,
            "expiresAt": expires,
            "revokedAt": None,
        }
        payload["shares"][row["tokenHash"]] = row
        _write(path, payload)
    return {"token": token, **row}


def find_share(token: str, *, root: Path | str | None = None) -> dict[str, Any] | None:
    """Resolve a token without changing storage; expired/revoked rows remain until a write."""
    if not token_format_ok(token):
        return None
    path = _path(root)
    if not path.exists():
        return None
    # Reads intentionally take the same lock as writers so a replacement cannot be observed
    # halfway through a JSON read, while still re-reading on every request for instant revoke.
    with _file_lock(path):
        payload = _load(path)
        row = payload["shares"].get(hash_token(token))
        if not isinstance(row, dict) or not _active(row, _now()):
            return None
        return dict(row)


def revoke_round(
    player_id: str,
    round_ref: str,
    *,
    round_refs: Iterable[str] | None = None,
    root: Path | str | None = None,
) -> int:
    """Revoke every active link for a round.  The operation is idempotent."""
    path = _path(root)
    now = _now()
    ref_set = {str(value) for value in (round_refs or (round_ref,))}
    ref_set.add(str(round_ref))
    count = 0
    with _file_lock(path):
        payload = _load(path)
        before_keys = set(payload["shares"])
        _prune_for_write(payload, now)
        changed = set(payload["shares"]) != before_keys
        for row in payload["shares"].values():
            if not isinstance(row, dict) or row.get("revokedAt"):
                continue
            if row.get("playerId") != str(player_id) or str(row.get("roundRef")) not in ref_set:
                continue
            if not _active(row, now):
                continue
            row["revokedAt"] = _iso(now)
            count += 1
            changed = True
        if changed:
            _write(path, payload)
    return count


def load_rows(*, root: Path | str | None = None) -> dict[str, Any]:
    """Small test/support hook returning the sanitized persisted payload."""
    path = _path(root)
    with _file_lock(path):
        return _load(path)
