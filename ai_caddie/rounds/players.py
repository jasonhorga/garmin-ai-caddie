"""Player registry + per-player capability tokens (private, owner-issued)."""
from __future__ import annotations
import hashlib, json, secrets, shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import logging

from ai_caddie.core.data import ROOT, atomic_write_json, safe_read_json  # repo root; data/ lives under it

logger = logging.getLogger(__name__)

OWNER_ID = "me"


class PlayerError(Exception):
    pass


def _players_dir(root: Path | str | None) -> Path:
    base = Path(root) if root is not None else ROOT
    return base / "data" / "players"


def _registry_path(root: Path | str | None) -> Path:
    return _players_dir(root) / "registry.json"


def _hash_token(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_registry() -> dict[str, Any]:
    return {
        "schema": "ai-caddie-players-v1",
        "players": [
            {"id": OWNER_ID, "name": "我", "isOwner": True, "createdAt": _now(),
             "avatar": None, "tokenHash": None, "tokenLast4": None},
        ],
    }


def load_registry(root: Path | str | None = None) -> dict[str, Any]:
    path = _registry_path(root)
    if path.exists():
        reg = safe_read_json(path)
        if isinstance(reg, dict) and "players" in reg:
            return reg
        # Corrupt/torn registry (e.g. a crash mid-write): never 500 the auth path.
        # Serve an owner-only fallback in memory and leave the file intact for
        # recovery. Player tokens stop resolving until it is fixed; the owner
        # (admin token) is unaffected — it never reads this file.
        logger.error("player registry at %s unreadable; serving owner-only fallback", path)
        return _default_registry()
    reg = _default_registry()
    _save_registry(reg, root)
    return reg


def _save_registry(reg: dict[str, Any], root: Path | str | None) -> None:
    atomic_write_json(_registry_path(root), reg)


def _issue_token() -> str:
    return secrets.token_urlsafe(32)


def create_player(name: str, *, avatar: str | None = None, root: Path | str | None = None) -> dict[str, Any]:
    reg = load_registry(root)
    pid = "p_" + secrets.token_hex(4)
    token = _issue_token()
    row = {"id": pid, "name": name, "isOwner": False, "createdAt": _now(),
           "avatar": avatar, "tokenHash": _hash_token(token), "tokenLast4": token[-4:]}
    reg["players"].append(row)
    _save_registry(reg, root)
    return {"id": pid, "name": name, "token": token}  # plaintext returned ONCE


def rotate_token(player_id: str, *, root: Path | str | None = None) -> dict[str, Any]:
    reg = load_registry(root)
    row = _find(reg, player_id)
    token = _issue_token()
    row["tokenHash"] = _hash_token(token)
    row["tokenLast4"] = token[-4:]
    _save_registry(reg, root)
    return {"id": player_id, "token": token}


def update_player(
    player_id: str,
    *,
    name: str | None = None,
    avatar: str | None = None,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Rename / re-avatar a player. ``None`` fields are left unchanged."""
    reg = load_registry(root)
    row = _find(reg, player_id)  # raises PlayerError if missing
    if name is not None:
        row["name"] = name
    if avatar is not None:
        row["avatar"] = avatar
    _save_registry(reg, root)
    return row


def resolve_token(token: str | None, *, root: Path | str | None = None) -> str | None:
    if not token:
        return None
    target = _hash_token(token)
    for row in load_registry(root)["players"]:
        stored = row.get("tokenHash")
        if stored and secrets.compare_digest(stored, target):
            return row["id"]
    return None


def delete_player(player_id: str, *, root: Path | str | None = None) -> None:
    if player_id == OWNER_ID:
        raise PlayerError("owner cannot be deleted")
    reg = load_registry(root)
    _find(reg, player_id)  # raises if missing
    reg["players"] = [p for p in reg["players"] if p["id"] != player_id]
    _save_registry(reg, root)
    pdir = _players_dir(root) / player_id
    if pdir.exists():
        shutil.rmtree(pdir)


def get_player(player_id: str, *, root: Path | str | None = None) -> dict[str, Any] | None:
    """Public profile (no token material) for one player, or ``None`` if unknown.

    Read-only on purpose: unlike :func:`load_registry` it never seeds/writes the
    registry, so it is safe to call on hot read paths (e.g. the history
    overview). When the registry has not been created yet only the implicit
    owner ``"me"`` is known.
    """
    path = _registry_path(root)
    if path.exists():
        reg = safe_read_json(path)
        if not isinstance(reg, dict):
            logger.error("player registry at %s unreadable in get_player", path)
            reg = _default_registry()
        for row in reg.get("players", []):
            if row.get("id") == player_id:
                return {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "isOwner": bool(row.get("isOwner", False)),
                    "avatar": row.get("avatar"),
                }
        return None
    if player_id == OWNER_ID:
        return {"id": OWNER_ID, "name": "我", "isOwner": True, "avatar": None}
    return None


def _find(reg: dict[str, Any], player_id: str) -> dict[str, Any]:
    for row in reg["players"]:
        if row["id"] == player_id:
            return row
    raise PlayerError(f"unknown player {player_id}")
