# server_v2/auth_api.py
"""Phase-1b auth endpoints: Sign in with Apple -> short-lived scoped session tokens.

/apple mints a token for an Apple sub: a known sub → its session; a first-time sub →
auto-registers a family member (role="member", in the owner's family) with a fresh isolated
player scope (the auto-create is bounded by the app's Apple bundle-id audience). /apple/link is
the owner-bootstrap link (admin-gated by the main gate in Task 1b-5). /refresh + /logout manage
a live session. Apple verification needs no Apple secret (JWKS signature check only)."""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ai_caddie.rounds.players import OWNER_ID
from server_v2 import apple_auth, db
from server_v2 import identity_repo as repo
from server_v2.identity_models import User

auth_router = APIRouter(prefix="/api/v2/auth", tags=["auth"])


class AppleSignInRequest(BaseModel):
    identityToken: str
    # The user's name is in Apple's first-authorization RESPONSE, not the JWT, so the iOS app
    # passes it on first sign-in. Used as the auto-registered member's display name.
    displayName: str | None = None


class AppleLinkRequest(BaseModel):
    identityToken: str
    userId: str | None = None


def _bundle_id() -> str:
    bundle = os.environ.get("AI_CADDIE_APPLE_BUNDLE_ID")
    if not bundle:
        raise HTTPException(status_code=503, detail="apple sign-in not configured")
    return bundle


def _verify(token: str) -> apple_auth.AppleIdentity:
    """Verify an Apple identity token. The monkeypatch seam for tests (patch server_v2.auth_api._verify)."""
    try:
        return apple_auth.verify_apple_identity_token(token, audience=_bundle_id())
    except apple_auth.AppleAuthError as exc:
        raise HTTPException(status_code=401, detail="invalid apple identity token") from exc


def _session_ttl() -> timedelta:
    try:
        hours = int(os.environ.get("AI_CADDIE_SESSION_TTL_HOURS", "24"))
    except ValueError:
        hours = 24  # a typo'd env value must not 500 every auth call
    return timedelta(hours=hours)


def _admin_apple_emails() -> set[str]:
    """Apple emails that sign in as the OWNER/admin rather than auto-registering as a member.
    Comma-separated env, matched case-insensitively. Apple returns the email only on first
    authorization and only if the user shares it (not Hide-My-Email); after the first owner
    sign-in the sub is linked to the owner, so every later sign-in resolves via the known-sub
    path regardless of email."""
    raw = os.environ.get("AI_CADDIE_ADMIN_APPLE_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _bearer_token(request: Request) -> str:
    authz = request.headers.get("authorization") or ""
    token = authz[7:].strip() if authz[:7].lower() == "bearer " else ""
    if not token:
        raise HTTPException(status_code=401, detail="session token required")
    return token


def _resolve_session(request: Request) -> tuple[str, str]:
    """(session_id, user_id) for a live session bearer; else 401."""
    token = _bearer_token(request)
    with db.session_scope() as session:
        sess = repo.resolve_session_token(session, token)
        if sess is None:
            raise HTTPException(status_code=401, detail="invalid or expired session")
        return sess.id, sess.user_id


def _session_payload(session, *, user_id: str, expires: datetime, player_id: str | None = None) -> dict:
    """Mint a session for ``user_id`` and project the auth response. ``player_id`` is supplied
    on the auto-register path (the freshly created pid); otherwise it is resolved from the map."""
    token, _sess = repo.mint_session_token(session, user_id=user_id, scope="user", expires_at=expires)
    pid = player_id if player_id is not None else repo.legacy_player_for_user(session, user_id)
    return {"token": token, "expiresAt": expires.isoformat(), "userId": user_id, "playerId": pid}


@auth_router.post("/apple")
def apple_sign_in(body: AppleSignInRequest) -> dict:
    ident = _verify(body.identityToken)
    expires = datetime.now(timezone.utc) + _session_ttl()
    # Known sub → mint as before (now also returning the resolved playerId). A soft-deleted
    # account still 403s (it must not silently re-register as a fresh member).
    with db.session_scope() as session:
        user = repo.get_user_by_apple_subject(session, ident.subject)
        if user is not None:
            if user.deleted_at is not None:
                raise HTTPException(status_code=403, detail="apple identity not linked")
            return _session_payload(session, user_id=user.id, expires=expires)
    # An owner/admin allowlist (configured Apple emails) → link this first-time sub to the OWNER
    # and mint an owner session, so the owner signs in with Apple like everyone else yet still lands
    # on the owner's own data. After this first link the sub is known → the path above handles it.
    if ident.email and ident.email.lower() in _admin_apple_emails():
        try:
            with db.session_scope() as session:
                owner_uid = repo.user_id_for_legacy_player(session, OWNER_ID)
                if owner_uid is None:
                    raise HTTPException(status_code=400, detail="owner user not provisioned (run the identity seeder)")
                repo.link_apple_identity(session, user_id=owner_uid, subject=ident.subject, email=ident.email)
                return _session_payload(session, user_id=owner_uid, expires=expires)
        except repo.IdentityConflictError:
            # A concurrent sign-in linked the sub first → mint for the now-existing user.
            with db.session_scope() as session:
                user = repo.get_user_by_apple_subject(session, ident.subject)
                if user is None or user.deleted_at is not None:
                    raise HTTPException(status_code=403, detail="apple identity not linked")
                return _session_payload(session, user_id=user.id, expires=expires)
    # First-time sub → auto-provision a member in the OWNER's family with a fresh isolated scope.
    # Retry on the astronomically rare 64-bit pid collision (a fresh id each attempt).
    for _attempt in range(3):
        try:
            with db.session_scope() as session:
                owner_uid = repo.user_id_for_legacy_player(session, OWNER_ID)
                if owner_uid is None:
                    raise HTTPException(status_code=400, detail="owner user not provisioned (run the identity seeder)")
                family_id = session.get(User, owner_uid).family_id
                pid = "p_" + secrets.token_hex(8)  # 64-bit; provision_member maps insert-only (no silent rebind)
                raw_name = body.displayName or (ident.email.split("@")[0] if ident.email else "Family member")
                display_name = raw_name[:120]  # User.display_name is String(120) — avoid a Postgres DataError 500
                member = repo.provision_member(
                    session, family_id=family_id, display_name=display_name,
                    pid=pid, subject=ident.subject, email=ident.email,
                )
                return _session_payload(session, user_id=member.id, expires=expires, player_id=pid)
        except repo.PlayerIdInUseError:
            continue  # pid collided with an existing map row → retry with a fresh id
        except repo.IdentityConflictError:
            # A concurrent first sign-in of the same sub won the UNIQUE(provider, subject) race
            # (including the real DB-level race, now surfaced as IdentityConflictError); our
            # provisioning rolled back. Mint for the now-existing user (no 500, no orphan).
            with db.session_scope() as session:
                user = repo.get_user_by_apple_subject(session, ident.subject)
                if user is None or user.deleted_at is not None:
                    raise HTTPException(status_code=403, detail="apple identity not linked")
                return _session_payload(session, user_id=user.id, expires=expires)
    raise HTTPException(status_code=503, detail="could not allocate a player id; please retry")


@auth_router.post("/apple/link")
def apple_link(body: AppleLinkRequest) -> dict:
    ident = _verify(body.identityToken)
    with db.session_scope() as session:
        user_id = body.userId or repo.user_id_for_legacy_player(session, OWNER_ID)
        if user_id is None:
            raise HTTPException(status_code=400, detail="owner user not provisioned (run the identity seeder)")
        try:
            repo.link_apple_identity(session, user_id=user_id, subject=ident.subject, email=ident.email)
        except repo.IdentityConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "userId": user_id, "subject": ident.subject}


@auth_router.post("/refresh")
def refresh(request: Request) -> dict:
    token = _bearer_token(request)
    expires = datetime.now(timezone.utc) + _session_ttl()
    # resolve + mint + revoke in ONE transaction so the old session is one-time: a concurrent
    # refresh of the same bearer fails on the duplicate revocation rather than minting a 2nd token.
    with db.session_scope() as session:
        sess = repo.resolve_session_token(session, token)
        if sess is None:
            raise HTTPException(status_code=401, detail="invalid or expired session")
        # Preserve the original session's scope — refresh must NOT launder a non-"user"
        # (e.g. "watch") session into a "user" token, which would bypass the scope=="user"
        # authorization boundary enforced in _player_for_session_token (Phase 1c).
        new_token, _sess = repo.mint_session_token(
            session, user_id=sess.user_id, scope=sess.scope, expires_at=expires, refresh_of=sess.id)
        repo.revoke_session(session, session_id=sess.id, reason="refresh")
        return {"token": new_token, "expiresAt": expires.isoformat()}


@auth_router.post("/logout")
def logout(request: Request) -> dict:
    session_id, _user_id = _resolve_session(request)
    with db.session_scope() as session:
        repo.revoke_session(session, session_id=session_id, reason="logout")
    return {"ok": True}
