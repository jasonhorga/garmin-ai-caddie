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


def assert_admin_security_config() -> None:
    """Boot-time validation of the admin/owner authorization configuration (called from app startup).

    The per-request path already fail-closes — ``require_admin_token`` answers 503 and
    ``_admin_token_grants_owner`` stays closed under a require-admin profile with no token — but that
    surfaces only as repeated 503s at runtime. This makes the SAME misconfiguration loud at boot:

    - A require-admin profile (``private``/``staging``/``production``) with NO ``AI_CADDIE_ADMIN_TOKEN``
      raises immediately (fail fast instead of serving nothing but 503s).
    - The open-dev owner-grant — no admin token AND a non-require-admin profile, where an
      unauthenticated request is silently treated as the owner — logs a prominent WARNING so a real
      deploy can never enable it by accident.

    Local dev / tests run without a profile and without a token: that is exactly the open-dev case, so
    they keep working (a single WARNING line, never a raise)."""
    profile = os.environ.get("AI_CADDIE_SECURITY_PROFILE", "").strip().lower()
    admin_token_set = bool(os.environ.get("AI_CADDIE_ADMIN_TOKEN"))
    if _security_profile_requires_admin():
        if not admin_token_set:
            raise RuntimeError(
                f"AI_CADDIE_SECURITY_PROFILE={profile!r} requires AI_CADDIE_ADMIN_TOKEN to be set; "
                "admin routes fail closed (503) until it is configured."
            )
        return  # properly secured: the profile demands admin and a token is configured
    if not admin_token_set:
        logger.warning(
            "open-dev owner-grant ACTIVE: AI_CADDIE_ADMIN_TOKEN is unset and "
            "AI_CADDIE_SECURITY_PROFILE=%r is not in {private,staging,production} -> unauthenticated "
            "requests are treated as the owner. Set AI_CADDIE_ADMIN_TOKEN and a private/staging/"
            "production profile before any shared/public deploy.",
            profile,
        )


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


def _valid_admin_header_present(request: Request) -> bool:
    """True iff the request carries a literal admin token header that MATCHES the configured token.

    Distinct from the open-dev grant (no token configured): this means the caller explicitly presented
    a valid admin credential, so on an admin route it must not be allowed to silently elevate a member
    bearer sent alongside it."""
    expected = os.environ.get("AI_CADDIE_ADMIN_TOKEN")
    if not expected:
        return False
    header = request.headers.get(_ADMIN_TOKEN_HEADER)
    return bool(header) and hmac.compare_digest(header, expected)


def _admin_token_grants_owner(request: Request) -> bool:
    if os.environ.get("AI_CADDIE_ADMIN_TOKEN"):
        return _valid_admin_header_present(request)
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


def admin_request_disposition(request: Request) -> str:
    """Authorization decision for a genuinely-admin (non-player-scoped) route. One of:

    - ``"allow"``  — a valid admin token OR an open-dev profile (``_admin_token_grants_owner``),
      OR an OWNER credential (a bearer that resolves to ``OWNER_ID`` — the owner's Apple session or
      legacy capability token). This is the (2) addition: the owner authorizes /admin/* and the sync
      trigger from the iOS app without the literal admin token.
    - ``"forbid"`` — a bearer that resolves to a MEMBER (``player_id != OWNER_ID``). Authenticated,
      but not the owner → the caller must answer 403, never silently fall through to the admin token.
    - ``"fallback"`` — nothing resolved; defer to the literal admin-token semantics (401 when
      configured-but-missing/mismatched, 503 fail-closed under a private/staging/production profile).

    The literal admin token stays the always-on DEBUG/CI/owner-homeserver fallback, EXCEPT it must not
    silently elevate a MEMBER bearer presented alongside it: a valid admin header paired with a member
    bearer is forbidden (the request is owned by an authenticated non-owner, so it answers 403)."""
    if _valid_admin_header_present(request):
        # A literal, valid admin token authorizes admin routes — but a member bearer sent with it must
        # never ride the admin header into owner scope. An owner bearer (or no/unresolved bearer) is fine.
        token = player_token_from_request(request)
        if token:
            bearer_player = players.resolve_token(token) or _player_for_session_token(token)
            if bearer_player is not None and bearer_player != OWNER_ID:
                return "forbid"
        return "allow"
    if _admin_token_grants_owner(request):
        return "allow"  # open-dev (no admin token configured) — the always-on local fallback wins
    token = player_token_from_request(request)
    if token:
        # An OWNER credential authorizes; a MEMBER credential is explicitly forbidden (not 401).
        player_id = players.resolve_token(token) or _player_for_session_token(token)
        if player_id == OWNER_ID:
            return "allow"
        if player_id is not None:
            return "forbid"
    return "fallback"


def is_player_scoped_route(method: str, path: str) -> bool:
    """Routes whose access may be granted by a per-player token (not only admin).

    These are the player-side GET reads: history, review reports, course catalogue search,
    course prep / prep-tips, the mobile course-options list, AND the four mobile/caddie aggregator
    reads — the mobile round package, the mobile course package, the reconciliation-GET,
    and the caddie-context read. Each loads only the caller's own data (or public,
    course-keyed geometry), so a family member sees only their own data.

    The aggregator reads were admin-only in Phase 1c because they also draw on shared,
    UNPARTITIONED evidence stores keyed by round_id / source_ref (the mobile event log,
    weather snapshots, the annotation store). Phase 2 made every evidence READ loader
    player-aware: each short-circuits to empty for a non-owner via ``evidence_root``, and
    the response builders now thread the resolved ``player_id`` down to every one — so a
    member who guesses an owner round_id gets a 200 with NO owner evidence (empty event
    cursor / reconciliation, no weather, no hand-written notes). They are therefore safe
    to open to members here.

    The live-round event log + ack store are now PER-PLAYER PARTITIONED
    (``mobile_live.mobile_event_log(player_id=…)``), so a member's in-round events write AND read
    to their OWN partition only — isolation by construction (the path differs), no ownership check.
    That makes the live-event WRITES (events POST + ack POST) safe to open to a per-player token
    too — the handlers thread ``current_player_id`` so each player only ever touches their own log.

    The same partitioning (``ai_caddie.core.data.evidence_root(player_id)``) now backs every EVIDENCE
    WRITE — caddie decision, decision audit, weather-persist, annotation, and report generation —
    so those POSTs (and the weather-persist GET) are likewise member-scoped: a member generates THEIR
    own caddie/weather/annotation/report in THEIR partition (the handlers thread current_player_id),
    isolated from the owner and every other member. The reconciliation/APPLY POST stays admin-only
    (it mutates the owner's shared round-reconciliation) — it does not match here.
    """
    m = method.upper()
    if m == "GET":
        return (
            path.startswith("/api/v2/history/")
            or path == "/api/v2/reports"
            or path.startswith("/api/v2/reports/")
            or (path.startswith("/api/v2/courses/") and path.endswith("/prep"))
            or (path.startswith("/api/v2/courses/") and path.endswith("/prep-tips"))
            or (path.startswith("/api/v2/courses/") and path.endswith("/tees"))
            or path == "/api/v2/courses/search"
            or path == "/api/v2/courses/nearby"
            or path == "/api/v2/mobile/courses/options"
            # Annotation READS — the annotation store is now per-player partitioned (the handlers thread
            # current_player_id into list_annotations/annotations_for_target via evidence_root), so a
            # member lists ONLY their own notes; opening them to a per-player token is safe.
            or path == "/api/v2/annotations"
            or path.startswith("/api/v2/annotations/target/")
            or path == "/api/v2/caddie/context"
            # Decision-audit READS use the same evidence_root(player_id) partition as both writes.
            or (path.startswith("/api/v2/caddie/decisions/") and path.endswith("/audit/latest"))
            or (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/package"))
            or (path.startswith("/api/v2/mobile/courses/") and path.endswith("/package"))
            or (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/reconciliation"))
            # Live-round event READS (per-player partitioned) — a member sees only their own.
            or (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/events/replay"))
            or (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/state"))
            # The member-scoped manual club-bag READ; the handler enforces owner/own-player. The PUT is
            # not a GET so it never matches here — it is handler-authed (like POST /players/{id}/rounds).
            or (path.startswith("/api/v2/players/") and path.endswith("/clubs/bag"))
            # Media + vision-findings READS — the media store is now per-player partitioned
            # (``server_v2.media._media_root(player_id)``), so a member sees only their own.
            or path.startswith("/api/v2/media/target/")
            # Weather-persist is a GET with ?persist=true. It only reaches the gate (and thus this
            # classifier) when persist is truthy (see _requires_admin_token), and the handler writes
            # the snapshot to the caller's evidence partition — so it is member-scoped like the others.
            or path == "/api/v2/weather/snapshot"
        )
    if m == "POST":
        # Live-round event WRITES are per-player partitioned, so a member writes ONLY to their own
        # log — safe for a per-player token (the handler threads current_player_id).
        return (
            (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/events"))
            or (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/events/ack"))
            or (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/finish"))
            # Media WRITES — the media store is per-player partitioned, so a member writes ONLY to
            # their own media (the handlers thread current_player_id).
            or path == "/api/v2/media"
            or (path.startswith("/api/v2/media/") and (path.endswith("/analyze") or path.endswith("/redact")))
            or (path.startswith("/api/v2/media/findings/") and path.endswith("/confirmation"))
            # Evidence WRITES — each resolves its write dir via evidence_root(player_id), so a member
            # writes ONLY to their own partition (the handlers thread current_player_id).
            or path == "/api/v2/caddie/decision"
            or (path.startswith("/api/v2/caddie/decisions/") and path.endswith("/audit"))
            or path == "/api/v2/annotations"
            or (path.startswith("/api/v2/reports/") and path.endswith("/generate"))
            # 复盘修改 WRITE — corrections 存在调用者自己的分区(data/players/<id>/corrections/),
            # 成员只写自己的(handler 线程 current_player_id)。路径无 target-player → 天然自限,
            # 分类同 POST /api/v2/annotations。
            or (path.startswith("/api/v2/history/rounds/") and path.endswith("/corrections"))
            # 「打开即用」准备最近一盘:fire-and-forget 预热调用者自己的缓存,无 target-player
            # → 自限,分类同 POST /api/v2/annotations。
            or path == "/api/v2/history/prepare-recent"
        )
    return False


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
