"""Player-side authentication for the multiplayer foundation.

Access model (kept consistent across every player-side route):

- A per-player capability token arrives as ``Authorization: Bearer <token>`` or
  ``?key=<token>`` and resolves to a ``player_id`` via ``players.resolve_token``.
- A valid admin token (``x-ai-caddie-admin-token``) on a player-side route is
  treated as the owner ``"me"`` -- backward compatibility with the homeserver
  native app and the W4a web client, which both authenticate with the admin
  token and must keep seeing owner data.
- In an open dev profile (no admin token configured and no security profile),
  requests without any token default to the owner ``"me"`` so local development
  keeps working without auth.
- Otherwise the request is unauthenticated (401).

The global admin gate in ``server_v2.main`` delegates the *bypass* decision to
``is_player_scoped_route`` + ``has_valid_player_token`` so that the existing
admin-token semantics (401 when configured-but-missing, 503 fail-closed under a
private/staging/production profile) stay intact for callers without a player
token.
"""
from __future__ import annotations

import hmac
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ai_caddie.rounds import players
from ai_caddie.rounds.players import OWNER_ID
from server_v2.models import FamilyUserRow, FamilyUsersResponse

logger = logging.getLogger(__name__)

_ADMIN_TOKEN_HEADER = "x-ai-caddie-admin-token"
# Mirrors server_v2.main._security_profile_requires_admin (kept local to avoid a
# circular import: main imports this module for the gate).
_ADMIN_REQUIRED_PROFILES = {"private", "staging", "production"}


def _security_profile_requires_admin() -> bool:
    profile = os.environ.get("AI_CADDIE_SECURITY_PROFILE", "").strip().lower()
    return profile in _ADMIN_REQUIRED_PROFILES


def player_token_from_request(request: Request) -> str | None:
    """Extract a per-player capability token from the request, if present."""
    authorization = request.headers.get("authorization") or ""
    if authorization[:7].lower() == "bearer ":
        token = authorization[7:].strip()
        if token:
            return token
    key = request.query_params.get("key")
    return key or None


def has_valid_player_token(request: Request) -> bool:
    """True iff the request carries a bearer/key token that resolves to a player —
    either a legacy per-player capability token or a Phase-1b Apple session token.

    Used by the global admin gate: a valid player token bypasses the admin
    requirement on player-side routes. Admin-token handling stays in
    ``require_admin_token`` so its 401/503 semantics are preserved untouched.
    """
    token = player_token_from_request(request)
    if not token:
        return False
    # The admin/dev fallback is NOT a player token, so check only the two player-credential types.
    return players.resolve_token(token) is not None or _player_for_session_token(token) is not None


def _admin_token_grants_owner(request: Request) -> bool:
    expected = os.environ.get("AI_CADDIE_ADMIN_TOKEN")
    header = request.headers.get(_ADMIN_TOKEN_HEADER)
    if expected:
        return bool(header) and hmac.compare_digest(header, expected)
    # No admin token configured: open in dev, closed when a profile demands admin.
    return not _security_profile_requires_admin()


def _player_for_session_token(token: str) -> str | None:
    """A Phase-1b Apple session bearer → the user's legacy player_id, or None.

    None when the token is not a live session (unknown/expired/revoked), the user is
    soft-deleted, or the user has no legacy_player_map entry yet."""
    # local imports keep this gate-critical module import-light (no identity-store load at import time)
    from server_v2 import db
    from server_v2 import identity_repo as repo
    from server_v2.identity_models import User
    try:
        with db.session_scope() as session:
            sess = repo.resolve_session_token(session, token)
            if sess is None:
                return None
            if sess.scope != "user":  # only full user sessions authorize player-scoped routes
                return None
            user = session.get(User, sess.user_id)
            if user is None or user.deleted_at is not None:
                return None
            return repo.legacy_player_for_user(session, sess.user_id)
    except Exception:
        logger.warning("identity store error during session-token resolution", exc_info=True)
        return None  # identity store unavailable → fall through to admin/dev/None


def resolve_request_player(request: Request) -> str | None:
    """Resolve the acting ``player_id`` for this request, or ``None`` if unauthenticated.

    Resolution order: (1) a legacy per-player capability token (``players.resolve_token``)
    is authoritative; (2) else a Phase-1b Apple **session token** resolves to the user's
    legacy player_id; (3) else a valid admin token (or an open dev profile) maps to the
    owner ``"me"``.
    """
    token = player_token_from_request(request)
    if token:
        player_id = players.resolve_token(token)
        if player_id is not None:
            return player_id
        session_player = _player_for_session_token(token)  # Phase-1b Apple session token
        if session_player is not None:
            return session_player
        # Token present but unresolved -> fall through to the admin/dev check so
        # the admin token never stops mapping to the owner.
    if _admin_token_grants_owner(request):
        return OWNER_ID
    return None


def current_player_id(request: Request) -> str:
    """FastAPI dependency: the player whose data this request may read/write."""
    player_id = resolve_request_player(request)
    if player_id is None:
        raise HTTPException(status_code=401, detail="valid player token required")
    return player_id


def is_player_scoped_route(method: str, path: str) -> bool:
    """Routes whose access may be granted by a per-player token (not only admin).

    These are the player-side reads keyed by the PLAYER (not by an opaque round_id):
    history, review reports, course prep / prep-tips, and the mobile course-options
    list. Each loads only the caller's own player-scoped HistoryData (or public course
    data), so a family member sees only their own data.

    NOTE: the mobile round/course PACKAGE reads, the reconciliation-GET, and the
    caddie-context read are intentionally NOT here. They aggregate per-round data from
    shared, UNPARTITIONED stores keyed by round_id / source_ref (the mobile event log,
    weather snapshots, the annotation store), so threading player_id isolates only the
    HistoryData half — opening them to members would leak the owner's round data
    (weather, hand-written notes, event activity) by a guessed round_id. They stay
    admin-only until those stores are per-user partitioned (Phase 2).
    """
    if method.upper() != "GET":
        return False
    return (
        path.startswith("/api/v2/history/")
        or path == "/api/v2/reports"
        or path.startswith("/api/v2/reports/")
        or (path.startswith("/api/v2/courses/") and path.endswith("/prep"))
        or (path.startswith("/api/v2/courses/") and path.endswith("/prep-tips"))
        or path == "/api/v2/mobile/courses/options"
    )


# ---------------------------------------------------------------------------
# Owner management API (admin token). Admin-token enforcement is performed by
# the global ``enforce_admin_token_before_body_validation`` gate in
# ``server_v2.main`` for every ``/api/v2/admin/*`` route (these are NOT
# player-scoped, so a per-player token never bypasses the gate). Keeping the
# admin check in the middleware avoids a circular import back into ``main`` and
# preserves the established 401 (configured-but-missing) / 503 (fail-closed
# under a private profile) semantics.
# ---------------------------------------------------------------------------

admin_router = APIRouter(prefix="/api/v2/admin", tags=["admin-players"])


class PlayerCreateRequest(BaseModel):
    name: str
    avatar: str | None = None


class PlayerUpdateRequest(BaseModel):
    name: str | None = None
    avatar: str | None = None


def _public_player(row: dict[str, Any]) -> dict[str, Any]:
    """Registry row → owner-facing view: never any token material, never data."""
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "isOwner": bool(row.get("isOwner", False)),
        "createdAt": row.get("createdAt"),
        "avatar": row.get("avatar"),
        "tokenLast4": row.get("tokenLast4"),
    }


def _player_url(request: Request, token: str) -> str:
    return f"{request.base_url}p/{token}"


@admin_router.get("/players")
def admin_list_players() -> dict[str, Any]:
    reg = players.load_registry()
    return {"players": [_public_player(row) for row in reg["players"]]}


@admin_router.get("/family/users", response_model=FamilyUsersResponse)
def admin_list_family_users() -> FamilyUsersResponse:
    """Owner-facing roster of family Users from the identity DB (admin-gated by the
    /api/v2/admin/* rule). Unlike /admin/players (the file registry), this includes
    map-only members auto-registered via Sign in with Apple. Projects identity fields
    only — never any token material."""
    # local imports keep this module import-light (the gate imports it; see has_valid_player_token)
    from server_v2 import db
    from server_v2 import identity_repo as identity
    from server_v2.identity_models import User

    with db.session_scope() as session:
        owner_uid = identity.user_id_for_legacy_player(session, OWNER_ID)
        if owner_uid is None:
            raise HTTPException(status_code=400, detail="owner user not provisioned (run the identity seeder)")
        family_id = session.get(User, owner_uid).family_id
        users = [
            FamilyUserRow(
                id=user.id,
                displayName=user.display_name,
                role=user.role,
                createdAt=user.created_at.isoformat(),
                deletedAt=user.deleted_at.isoformat() if user.deleted_at is not None else None,
                playerId=pid,
            )
            for user, pid in identity.list_family_users(session, family_id)
        ]
    return FamilyUsersResponse(schema_="ai-caddie-family-users-v1", total=len(users), users=users)


@admin_router.post("/players", status_code=201)
def admin_create_player(body: PlayerCreateRequest, request: Request) -> dict[str, Any]:
    created = players.create_player(body.name, avatar=body.avatar)
    token = created["token"]  # plaintext returned ONCE, never persisted/logged
    return {
        "id": created["id"],
        "name": created["name"],
        "token": token,
        "url": _player_url(request, token),
    }


@admin_router.patch("/players/{player_id}")
def admin_update_player(player_id: str, body: PlayerUpdateRequest) -> dict[str, Any]:
    try:
        row = players.update_player(player_id, name=body.name, avatar=body.avatar)
    except players.PlayerError:
        raise HTTPException(status_code=404, detail="unknown player")
    return _public_player(row)


@admin_router.post("/players/{player_id}/rotate-token")
def admin_rotate_token(player_id: str, request: Request) -> dict[str, Any]:
    try:
        rotated = players.rotate_token(player_id)
    except players.PlayerError:
        raise HTTPException(status_code=404, detail="unknown player")
    token = rotated["token"]
    return {"id": rotated["id"], "token": token, "url": _player_url(request, token)}


@admin_router.delete("/players/{player_id}")
def admin_delete_player(player_id: str) -> dict[str, Any]:
    if player_id == OWNER_ID:
        raise HTTPException(status_code=400, detail="owner cannot be deleted")
    try:
        players.delete_player(player_id)
    except players.PlayerError:
        raise HTTPException(status_code=404, detail="unknown player")
    return {"ok": True, "id": player_id}
