# server_v2/identity_seed.py
"""One-shot, idempotent backfill: JSON player registry -> families/users/legacy_player_map.

Phase 1a: identity rows only. No file data is moved (that is Phase 3 backfill).
Run as: python -m server_v2.identity_seed
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_caddie.rounds import players
from server_v2 import identity_repo as repo
from server_v2.db import session_scope
from server_v2.identity_models import Family, User

_FAMILY_NAME = "Family"


def seed_from_registry(session: Session, *, root: Path | None = None) -> dict[str, str]:
    """Create one family + a user per registry player + legacy map. Idempotent.

    Returns {legacy_player_id: user_id}.
    """
    registry = players.load_registry(root=root)
    rows = registry.get("players", [])
    owner_row = next((p for p in rows if p.get("isOwner")), {"id": players.OWNER_ID, "name": "我"})

    # Family + owner (only if the owner is not already mapped).
    owner_user_id = repo.user_id_for_legacy_player(session, owner_row["id"])
    if owner_user_id is None:
        existing_family = session.execute(select(Family)).scalars().first()
        if existing_family is None:
            family, owner = repo.create_family_with_owner(
                session, family_name=_FAMILY_NAME, owner_display_name=owner_row.get("name") or "我",
            )
        else:
            family = existing_family
            owner = repo.add_user(
                session, family_id=family.id,
                display_name=owner_row.get("name") or "我", role="admin",
            )
        repo.map_legacy_player(session, legacy_player_id=owner_row["id"], user_id=owner.id)
        owner_user_id = owner.id
    else:
        family = session.execute(select(Family)).scalars().first()
        assert family is not None, "owner is mapped but no family row exists"

    result = {owner_row["id"]: owner_user_id}

    for p in rows:
        if p.get("isOwner"):
            continue
        legacy_id = p["id"]
        mapped = repo.user_id_for_legacy_player(session, legacy_id)
        if mapped is None:
            member = repo.add_user(
                session, family_id=family.id,
                display_name=p.get("name") or legacy_id, role="member",
            )
            repo.map_legacy_player(session, legacy_player_id=legacy_id, user_id=member.id)
            mapped = member.id
        result[legacy_id] = mapped

    return result


def main() -> None:
    with session_scope() as session:
        mapping = seed_from_registry(session)
    print(f"seeded {len(mapping)} legacy players -> users")


if __name__ == "__main__":
    main()
