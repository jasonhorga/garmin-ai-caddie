"""Durable, player-scoped physical identities for live mobile round holes."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from ai_caddie.caddie.mobile_event_store import open_mobile_event_store
from ai_caddie.caddie.mobile_live import mobile_event_log
from ai_caddie.caddie.round_loops import validate_round_identity
from ai_caddie.history.history import OWNER_ID


class MobileRoundIdentityError(ValueError):
    """Stored physical identity is unavailable or contradicts already accepted events."""


def _identity_path(round_id: str, root: Path | str | None, player_id: str) -> Path:
    # Use the same partition as events. Hash arbitrary round ids instead of treating them as paths.
    key = hashlib.sha256(str(round_id).encode()).hexdigest()
    return mobile_event_log(root, player_id=player_id).parent / "round_identity" / f"{key}.json"


def load_mobile_round_identity(
    round_id: str, *, root: Path | str | None = None, player_id: str = OWNER_ID,
) -> dict[str, Any] | None:
    try:
        document = json.loads(_identity_path(round_id, root, player_id).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise MobileRoundIdentityError("mobile_round_identity_unreadable") from exc
    try:
        if document["roundId"] != str(round_id):
            raise ValueError("round id mismatch")
        validate_round_identity(document["roundLoops"], document["loopKey"], document["holes"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MobileRoundIdentityError("mobile_round_identity_invalid") from exc
    return document


def save_mobile_round_identity(
    round_id: str, round_loops: list[dict[str, Any]], loop_key: str,
    holes: list[dict[str, Any]], *, root: Path | str | None = None, player_id: str = OWNER_ID,
) -> None:
    """Save proven package facts, allowing unplayed second-nine additions/reselections.

    Existing legacy events cannot prove which package authored them: never retroactively assign
    a first identity to such a stream. Once an identity exists, every played hole must retain it.
    The record survives finish/restart and contains no package enrichment or player statistics.
    """
    columns = ("number", "sourceGlobalId", "sourceLocalHole", "courseHoleNumber")
    document = {
        "roundId": str(round_id), "roundLoops": round_loops, "loopKey": loop_key,
        "holes": [{key: hole[key] for key in columns} for hole in holes],
    }
    validate_round_identity(round_loops, loop_key, document["holes"])
    path = _identity_path(round_id, root, player_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = load_mobile_round_identity(round_id, root=root, player_id=player_id)
        if previous == document:
            return
        event_path = mobile_event_log(root, player_id=player_id)
        rows = open_mobile_event_store(event_path.parent).read_rows(round_id)
        if previous is None and rows:
            return
        if previous is not None:
            before = {hole["number"]: hole for hole in previous["holes"]}
            after = {hole["number"]: hole for hole in document["holes"]}
            if any(before.get(row.get("event", {}).get("hole")) != after.get(row.get("event", {}).get("hole"))
                   for row in rows):
                raise MobileRoundIdentityError("mobile_round_identity_changes_played_hole")
        descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".identity-")
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
