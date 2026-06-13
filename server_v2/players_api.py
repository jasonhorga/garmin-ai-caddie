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
import os

from fastapi import HTTPException, Request

from ai_caddie import players
from ai_caddie.players import OWNER_ID

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
    """True iff the request carries a bearer/key token that resolves to a player.

    Used by the global admin gate: a valid player token bypasses the admin
    requirement on player-side routes. Admin-token handling stays in
    ``require_admin_token`` so its 401/503 semantics are preserved untouched.
    """
    token = player_token_from_request(request)
    if not token:
        return False
    return players.resolve_token(token) is not None


def _admin_token_grants_owner(request: Request) -> bool:
    expected = os.environ.get("AI_CADDIE_ADMIN_TOKEN")
    header = request.headers.get(_ADMIN_TOKEN_HEADER)
    if expected:
        return bool(header) and hmac.compare_digest(header, expected)
    # No admin token configured: open in dev, closed when a profile demands admin.
    return not _security_profile_requires_admin()


def resolve_request_player(request: Request) -> str | None:
    """Resolve the acting ``player_id`` for this request, or ``None`` if unauthenticated.

    A valid per-player token is authoritative. Otherwise a valid admin token (or
    an open dev profile) maps to the owner ``"me"``.
    """
    token = player_token_from_request(request)
    if token:
        player_id = players.resolve_token(token)
        if player_id is not None:
            return player_id
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

    These are the player-side reads: history, review reports, course prep /
    prep-tips, and the mobile course options list.
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
