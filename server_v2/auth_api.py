# server_v2/auth_api.py
"""Phase-1b auth endpoints: Sign in with Apple -> short-lived scoped session tokens.

/apple mints a token ONLY for an already-linked Apple sub (no auto-create). /apple/link is the
owner-bootstrap link (admin-gated by the main gate in Task 1b-5). /refresh + /logout manage a
live session. Apple verification needs no Apple secret (JWKS signature check only)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ai_caddie.rounds.players import OWNER_ID
from server_v2 import apple_auth, db
from server_v2 import identity_repo as repo

auth_router = APIRouter(prefix="/api/v2/auth", tags=["auth"])


class AppleSignInRequest(BaseModel):
    identityToken: str


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


def _resolve_session(request: Request) -> tuple[str, str]:
    """(session_id, user_id) for a live session bearer; else 401."""
    authz = request.headers.get("authorization") or ""
    token = authz[7:].strip() if authz[:7].lower() == "bearer " else ""
    if not token:
        raise HTTPException(status_code=401, detail="session token required")
    with db.session_scope() as session:
        sess = repo.resolve_session_token(session, token)
        if sess is None:
            raise HTTPException(status_code=401, detail="invalid or expired session")
        return sess.id, sess.user_id


@auth_router.post("/apple")
def apple_sign_in(body: AppleSignInRequest) -> dict:
    ident = _verify(body.identityToken)
    expires = datetime.now(timezone.utc) + _session_ttl()
    with db.session_scope() as session:
        user = repo.get_user_by_apple_subject(session, ident.subject)
        if user is None or user.deleted_at is not None:
            raise HTTPException(status_code=403, detail="apple identity not linked")
        token, _sess = repo.mint_session_token(session, user_id=user.id, scope="user", expires_at=expires)
        return {"token": token, "expiresAt": expires.isoformat(), "userId": user.id}


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
    session_id, user_id = _resolve_session(request)
    expires = datetime.now(timezone.utc) + _session_ttl()
    with db.session_scope() as session:
        token, _sess = repo.mint_session_token(
            session, user_id=user_id, scope="user", expires_at=expires, refresh_of=session_id)
        repo.revoke_session(session, session_id=session_id, reason="refresh")
        return {"token": token, "expiresAt": expires.isoformat()}


@auth_router.post("/logout")
def logout(request: Request) -> dict:
    session_id, _user_id = _resolve_session(request)
    with db.session_scope() as session:
        repo.revoke_session(session, session_id=session_id, reason="logout")
    return {"ok": True}
