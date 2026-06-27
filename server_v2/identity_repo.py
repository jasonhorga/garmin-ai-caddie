# server_v2/identity_repo.py
"""Repository functions over a SQLAlchemy Session. No FastAPI, no module globals."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from server_v2.identity_models import (
    AuthSession, Family, LegacyPlayerMap, TokenRevocation, User, UserIdentity,
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


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint_session_token(
    session: Session, *, user_id: str, scope: str, expires_at: datetime,
    device_id: str | None = None, refresh_of: str | None = None,
) -> tuple[str, AuthSession]:
    """Create a session row; return (plaintext_token, row). Plaintext is shown ONCE."""
    token = secrets.token_urlsafe(32)
    row = AuthSession(
        user_id=user_id, device_id=device_id, scope=scope,
        token_hash=_hash_token(token), expires_at=expires_at, refresh_of=refresh_of,
    )
    session.add(row)
    session.flush()
    return token, row


def resolve_session_token(session: Session, token: str) -> AuthSession | None:
    """Return the live session for a bearer token, or None (unknown/expired/revoked)."""
    row = session.execute(
        select(AuthSession).where(AuthSession.token_hash == _hash_token(token))
    ).scalars().first()
    if row is None:
        return None
    expires = row.expires_at
    if expires.tzinfo is None:  # SQLite returns naive datetimes
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        return None
    if session.get(TokenRevocation, row.id) is not None:
        return None
    return row


def revoke_session(session: Session, *, session_id: str, reason: str | None = None) -> None:
    if session.get(TokenRevocation, session_id) is None:
        session.add(TokenRevocation(session_id=session_id, reason=reason))
