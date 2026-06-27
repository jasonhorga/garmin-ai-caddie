# server_v2/identity_repo.py
"""Repository functions over a SQLAlchemy Session. No FastAPI, no module globals."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from server_v2.identity_models import (
    Family, LegacyPlayerMap, User, UserIdentity,
)


def create_family_with_owner(session: Session, *, family_name: str, owner_display_name: str) -> tuple[Family, User]:
    family = Family(name=family_name)
    session.add(family)
    session.flush()  # assign family.id
    owner = User(family_id=family.id, display_name=owner_display_name, role="admin")
    session.add(owner)
    session.flush()
    family.owner_user_id = owner.id
    return family, owner


def add_user(session: Session, *, family_id: str, display_name: str, role: str = "member") -> User:
    user = User(family_id=family_id, display_name=display_name, role=role)
    session.add(user)
    session.flush()
    return user


def map_legacy_player(session: Session, *, legacy_player_id: str, user_id: str) -> LegacyPlayerMap:
    row = session.get(LegacyPlayerMap, legacy_player_id)
    if row is None:
        row = LegacyPlayerMap(legacy_player_id=legacy_player_id, user_id=user_id)
        session.add(row)
    else:
        row.user_id = user_id
    return row


def user_id_for_legacy_player(session: Session, legacy_player_id: str) -> str | None:
    row = session.get(LegacyPlayerMap, legacy_player_id)
    return row.user_id if row else None


def get_user_by_apple_subject(session: Session, subject: str) -> User | None:
    stmt = (
        select(User)
        .join(UserIdentity, UserIdentity.user_id == User.id)
        .where(UserIdentity.provider == "apple", UserIdentity.subject == subject)
    )
    return session.execute(stmt).scalars().first()
