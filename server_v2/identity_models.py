# server_v2/identity_models.py
"""Identity & tenancy tables (design §4). Portable across SQLite and Postgres."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Family(Base):
    __tablename__ = "families"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    # no FK: avoids the families<->users circular dependency at insert time (repo sets it after both flush)
    owner_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    family_id: Mapped[str] = mapped_column(String(32), ForeignKey("families.id"))
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), default="member")  # admin|member
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_identity_provider_subject"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(32), default="apple")
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class LegacyPlayerMap(Base):
    __tablename__ = "legacy_player_map"
    legacy_player_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 'me' | 'p_*'
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    install_uuid: Mapped[str] = mapped_column(String(64), unique=True)
    platform: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AuthSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    device_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("devices.id"), nullable=True)
    scope: Mapped[str] = mapped_column(String(32), default="user")  # user|watch
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 hex of the bearer
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    refresh_of: Mapped[str | None] = mapped_column(String(32), nullable=True)  # prior session id; no FK so revocation never cascades


class TokenRevocation(Base):
    __tablename__ = "token_revocations"
    session_id: Mapped[str] = mapped_column(String(32), ForeignKey("sessions.id"), primary_key=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AccessAudit(Base):
    __tablename__ = "access_audit"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    actor_user_id: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64))
    target_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_kind: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class RoundAcl(Base):
    __tablename__ = "round_acl"
    round_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # file-backed round id (no rounds table → no FK)
    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)  # no FK to users.id by choice; ACL integrity enforced at the repo layer
    access: Mapped[str] = mapped_column(String(32), default="owner")  # owner|shared_read
