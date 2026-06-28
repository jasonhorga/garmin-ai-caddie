# server_v2/identity_repo.py
"""Repository functions over a SQLAlchemy Session. No FastAPI, no module globals."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from server_v2.identity_models import (
    AuthSession, Family, LegacyPlayerMap, TokenRevocation, User, UserIdentity,
)


class IdentityConflictError(Exception):
    """Raised when linking an Apple sub that is already bound to a different user."""


class PlayerIdInUseError(Exception):
    """Raised when a freshly generated legacy player id collides with an existing map row
    (the caller retries auto-provision with a new id rather than silently re-binding)."""


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
    """Bind a legacy player id ('me'/'p_*') to a user. INSERT-ONLY: re-binding an existing legacy id
    to a DIFFERENT user is refused (a silent rebind would hand one user's isolated data to another);
    re-binding to the SAME user is an idempotent no-op. Matches the insert-only contract that
    provision_member relies on for the LegacyPlayerMap linchpin."""
    row = session.get(LegacyPlayerMap, legacy_player_id)
    if row is None:
        row = LegacyPlayerMap(legacy_player_id=legacy_player_id, user_id=user_id)
        session.add(row)
    elif row.user_id != user_id:
        raise PlayerIdInUseError(legacy_player_id)
    return row


def user_id_for_legacy_player(session: Session, legacy_player_id: str) -> str | None:
    row = session.get(LegacyPlayerMap, legacy_player_id)
    return row.user_id if row else None


def legacy_player_for_user(session: Session, user_id: str) -> str | None:
    """Reverse of user_id_for_legacy_player: the legacy player_id ('me'/'p_*') for a user, if any.

    One-legacy-per-user holds in practice (the map is seeded from Garmin's 'me'/'p_*' slots),
    so .first() is deterministic; if that ever changes, add a UNIQUE on LegacyPlayerMap.user_id."""
    row = session.execute(
        select(LegacyPlayerMap).where(LegacyPlayerMap.user_id == user_id)
    ).scalars().first()
    return row.legacy_player_id if row else None


def list_family_users(session: Session, family_id: str) -> list[tuple[User, str | None]]:
    """Every User in ``family_id`` (including soft-deleted), each paired with its mapped legacy
    player id (or None). LEFT join so a member whose map row is missing still appears in the roster."""
    stmt = (
        select(User, LegacyPlayerMap.legacy_player_id)
        .outerjoin(LegacyPlayerMap, LegacyPlayerMap.user_id == User.id)
        .where(User.family_id == family_id)
        .order_by(User.created_at)
    )
    return [(row[0], row[1]) for row in session.execute(stmt).all()]


def get_user_by_apple_subject(session: Session, subject: str) -> User | None:
    stmt = (
        select(User)
        .join(UserIdentity, UserIdentity.user_id == User.id)
        .where(UserIdentity.provider == "apple", UserIdentity.subject == subject)
    )
    return session.execute(stmt).scalars().first()


def link_apple_identity(
    session: Session, *, user_id: str, subject: str, email: str | None = None
) -> UserIdentity:
    """Link an Apple `sub` to a user. Idempotent for the same user; raises IdentityConflictError
    if the sub is already bound to a DIFFERENT user (one sub = one user, permanently)."""
    existing = session.execute(
        select(UserIdentity).where(UserIdentity.provider == "apple", UserIdentity.subject == subject)
    ).scalars().first()
    if existing is not None:
        if existing.user_id != user_id:
            raise IdentityConflictError(
                f"apple sub already linked to user {existing.user_id!r}, refusing to re-link to {user_id!r}"
            )
        return existing
    identity = UserIdentity(user_id=user_id, provider="apple", subject=subject, email=email)
    session.add(identity)
    try:
        session.flush()
    except IntegrityError as exc:
        # A concurrent first sign-in committed the same (provider, subject) between our SELECT
        # above and this flush → the DB UNIQUE constraint fires. Convert to the semantic
        # conflict the caller already handles (re-resolve + mint for the winner), not a raw 500.
        raise IdentityConflictError(
            f"apple sub {subject!r} was concurrently linked to another user"
        ) from exc
    return identity


def provision_member(
    session: Session, *, family_id: str, display_name: str, pid: str,
    subject: str, email: str | None = None,
) -> User:
    """Auto-register a family member: a new ``member`` User + the linchpin LegacyPlayerMap
    (map-only — no ``players.create_player`` file registry) + the Apple identity link.

    The LegacyPlayerMap(pid, member) row is REQUIRED: it is what gives the member an isolated
    data scope (a missing map silently resolves to OWNER in the open dev/test profile). Raises
    IdentityConflictError if ``subject`` is already linked to a different user (concurrent
    first sign-in) — the caller mints a session for the now-existing user instead."""
    member = add_user(session, family_id=family_id, display_name=display_name, role="member")
    # Insert-only (NOT the upserting map_legacy_player): a pid collision must fail loudly so the
    # caller retries with a fresh id, never silently re-point an existing member's data scope.
    session.add(LegacyPlayerMap(legacy_player_id=pid, user_id=member.id))
    try:
        session.flush()
    except IntegrityError as exc:
        raise PlayerIdInUseError(pid) from exc
    link_apple_identity(session, user_id=member.id, subject=subject, email=email)
    return member


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
