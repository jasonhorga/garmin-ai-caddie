"""Player registry + per-player capability tokens (private, owner-issued)."""
from __future__ import annotations
import hashlib, json, secrets, shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_caddie.data import ROOT  # repo root; data/ lives under it

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


def load_registry(root: Path | str | None = None) -> dict[str, Any]:
    path = _registry_path(root)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    reg = {
        "schema": "ai-caddie-players-v1",
        "players": [
            {"id": OWNER_ID, "name": "我", "isOwner": True, "createdAt": _now(),
             "avatar": None, "tokenHash": None, "tokenLast4": None},
        ],
    }
    _save_registry(reg, root)
    return reg


def _save_registry(reg: dict[str, Any], root: Path | str | None) -> None:
    path = _registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _find(reg: dict[str, Any], player_id: str) -> dict[str, Any]:
    for row in reg["players"]:
        if row["id"] == player_id:
            return row
    raise PlayerError(f"unknown player {player_id}")
