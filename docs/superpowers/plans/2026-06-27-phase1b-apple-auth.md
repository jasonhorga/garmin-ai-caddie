# Phase 1b — Apple Sign-in + Scoped Session Tokens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let an Apple-authenticated user obtain a short-lived scoped bearer token that the backend resolves to their identity — wired into the existing `resolve_request_player` seam **alongside** (never replacing) the admin-token and legacy per-player-token paths.

**Architecture:** A new `server_v2/apple_auth.py` verifies Apple identity tokens (RS256 via Apple JWKS, checks `aud`/`iss`/`exp`). A new `server_v2/auth_api.py` router exposes `POST /auth/apple` (linked sub → session), `POST /auth/apple/link` (admin-bootstrapped linking), `POST /auth/refresh`, `POST /auth/logout`. `resolve_request_player` gains a session-token branch: bearer → `resolve_session_token` (1a) → user → `legacy_player_for_user` → legacy `player_id`. Reuses the 1a identity layer (`db.py`, `identity_models.AuthSession/UserIdentity`, `identity_repo.mint/resolve/revoke_session`, `get_user_by_apple_subject`, `legacy_player_map`).

**Tech Stack:** PyJWT[crypto] (RS256 + Apple JWKS), FastAPI, SQLAlchemy (1a), uv, unittest. Tests sign tokens with a **generated RSA keypair** + inject the public key — no live Apple calls.

**Scope boundary (1 of: 1a done · 1b this · 1c next):** 1b = Apple auth + scoped-token machinery + resolution wiring. **1c** (separate) threads the resolved `user_id`/`player_id` into the ~6 IDOR `load_history_data_for_mode()` call sites + `round_acl`/`access_audit` enforcement. 1b changes the auth *resolution* but **adds no new data exposure** — a session token resolves to the SAME legacy `player_id` the owner/member already had.

**Product model (grounded in spec §5 — trusted family, NOT public SaaS):**
- **No auto-create.** `POST /auth/apple` mints a session ONLY for an Apple `sub` already linked to a user; an unknown `sub` gets **403** (never silently creates an account).
- **Owner bootstrap:** the owner links their own Apple `sub` to the `me` user via `POST /auth/apple/link` authenticated with the **existing admin token** (the homeserver/web owner already holds it). `?user_id=` lets the owner link a member's user too.
- **Member self-onboarding UX (invite/claim) is DEFERRED** (needs product input) — 1b proves the owner end-to-end + provides the linking mechanism.

**Grounding (verified against current code, integration/v2 @ d1cd7dd):**
- Resolution seam: `server_v2/players_api.py` — `player_token_from_request:45`, `resolve_request_player:78` (token→`players.resolve_token`→player_id; else admin/dev→`OWNER_ID`; else None), `current_player_id:96`. `OWNER_ID="me"`.
- Gate: `server_v2/main.py` — `_requires_admin_token:234` is an **allowlist** (unlisted paths are NOT admin-gated → public); middleware `enforce_admin_token_before_body_validation:298`; routers included at `main.py:159` (`app.include_router(admin_router)`).
- 1a identity layer present: `server_v2/identity_repo.py` (`create_family_with_owner`, `add_user`, `map_legacy_player`, `user_id_for_legacy_player`, `get_user_by_apple_subject`, `mint_session_token`, `resolve_session_token`, `revoke_session`), `identity_models.py` (`AuthSession`, `UserIdentity`, `User`, `LegacyPlayerMap`), `db.py` (`session_scope`, `get_engine`). Seeder `identity_seed.py`. Migrations under `migrations/`.
- `tests/` flat unittest; route-policy guardrail in `tests/test_codex_sec2.py` imports `_requires_admin_token`; auth tests mirror `tests/test_players_api_auth.py`.

**Conventions:** every commit message ends with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. All datetime comparisons normalise naive (SQLite) datetimes to UTC before comparing (the `if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)` pattern from 1a `resolve_session_token`). DB-level `DateTime(timezone=True)` migration stays a deferred follow-up.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` / `uv.lock` | Modify: add `pyjwt[crypto]`. |
| `server_v2/apple_auth.py` | Create: `verify_apple_identity_token(token, *, audience, signing_key_resolver=...)` → `AppleIdentity(subject, email)`; `AppleAuthError`. Injectable key resolver for tests. |
| `server_v2/identity_repo.py` | Modify: add `legacy_player_for_user(session, user_id)` and `link_apple_identity(session, *, user_id, subject, email)` (idempotent). |
| `server_v2/auth_api.py` | Create: `auth_router` (`/api/v2/auth/*`) + a `current_session` dependency. |
| `server_v2/players_api.py` | Modify: `resolve_request_player` gains a session-token branch (session → user → legacy player_id, rejecting soft-deleted users). |
| `server_v2/main.py` | Modify: `app.include_router(auth_router)`; add `/api/v2/auth/apple/link` to the `_requires_admin_token` POST allowlist. |
| `.env.example` | Modify: document `AI_CADDIE_APPLE_BUNDLE_ID` + `AI_CADDIE_SESSION_TTL_HOURS`. |
| `tests/test_apple_auth.py`, `tests/test_identity_repo_apple.py`, `tests/test_auth_api.py`, `tests/test_session_resolution.py` | Create. |
| `tests/test_codex_sec2.py` | Modify: assert `/auth/apple/link` is admin-gated and `/auth/apple` is not. |

---

## Task 1: Add the JWT dependency

**Files:** `pyproject.toml`, `uv.lock`, `tests/test_apple_auth_deps.py`

- [ ] **Step 1: failing test** — `tests/test_apple_auth_deps.py`:
```python
import unittest


class JwtDepImportableTests(unittest.TestCase):
    def test_pyjwt_with_crypto_imports(self):
        import jwt  # noqa: F401
        from jwt import PyJWKClient  # noqa: F401
        from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: F401 (the [crypto] extra)
```
- [ ] **Step 2:** `uv run python -m unittest tests.test_apple_auth_deps -v` → FAIL (`No module named 'jwt'`).
- [ ] **Step 3:** `uv add 'pyjwt[crypto]>=2.8'`
- [ ] **Step 4:** test passes.
- [ ] **Step 5:** `uv sync --frozen` → no drift.
- [ ] **Step 6:** commit `build(auth): add pyjwt[crypto] for Apple identity-token verification`.

---

## Task 2: Apple identity-token verification module

**Files:** Create `server_v2/apple_auth.py`; Test `tests/test_apple_auth.py`

- [ ] **Step 1: failing test** — `tests/test_apple_auth.py` (signs tokens with a generated keypair; injects the public key as the resolver, so no live Apple call):
```python
import time
import unittest

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from server_v2.apple_auth import AppleAuthError, verify_apple_identity_token

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUB = _KEY.public_key()
AUD = "com.example.aicaddie"
ISS = "https://appleid.apple.com"


def _token(**overrides):
    claims = {"iss": ISS, "aud": AUD, "sub": "000123.abc.456",
              "email": "x@privaterelay.appleid.com",
              "iat": int(time.time()), "exp": int(time.time()) + 600}
    claims.update(overrides)
    return jwt.encode(claims, _KEY, algorithm="RS256")


class AppleAuthTests(unittest.TestCase):
    def _resolver(self, _token):
        return _PUB

    def test_valid_token_returns_identity(self):
        ident = verify_apple_identity_token(_token(), audience=AUD, signing_key_resolver=self._resolver)
        self.assertEqual(ident.subject, "000123.abc.456")
        self.assertEqual(ident.email, "x@privaterelay.appleid.com")

    def test_wrong_audience_rejected(self):
        with self.assertRaises(AppleAuthError):
            verify_apple_identity_token(_token(aud="com.attacker.app"), audience=AUD, signing_key_resolver=self._resolver)

    def test_wrong_issuer_rejected(self):
        with self.assertRaises(AppleAuthError):
            verify_apple_identity_token(_token(iss="https://evil.example"), audience=AUD, signing_key_resolver=self._resolver)

    def test_expired_rejected(self):
        with self.assertRaises(AppleAuthError):
            verify_apple_identity_token(_token(exp=int(time.time()) - 5), audience=AUD, signing_key_resolver=self._resolver)

    def test_missing_sub_rejected(self):
        with self.assertRaises(AppleAuthError):
            verify_apple_identity_token(_token(sub=""), audience=AUD, signing_key_resolver=self._resolver)
```
- [ ] **Step 2:** run → FAIL (no module).
- [ ] **Step 3: implement `server_v2/apple_auth.py`:**
```python
# server_v2/apple_auth.py
"""Verify a 'Sign in with Apple' identity token (native flow). No Apple secret needed —
we only verify the RS256 signature against Apple's public JWKS + the standard claims."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import jwt
from jwt import PyJWKClient

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"


class AppleAuthError(Exception):
    """Raised when an Apple identity token fails verification."""


@dataclass(frozen=True)
class AppleIdentity:
    subject: str  # Apple `sub` — the stable per-user id
    email: str | None


_jwks_client: PyJWKClient | None = None


def _default_signing_key(token: str):
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(APPLE_JWKS_URL)  # caches keys internally
    return _jwks_client.get_signing_key_from_jwt(token).key


def verify_apple_identity_token(
    token: str, *, audience: str,
    signing_key_resolver: Callable[[str], object] = _default_signing_key,
) -> AppleIdentity:
    """Verify signature + aud/iss/exp; return the Apple identity. Raise AppleAuthError on any failure."""
    if not audience:
        raise AppleAuthError("apple audience (bundle id) not configured")
    try:
        key = signing_key_resolver(token)
        claims = jwt.decode(
            token, key, algorithms=["RS256"], audience=audience, issuer=APPLE_ISSUER,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except AppleAuthError:
        raise
    except Exception as exc:  # PyJWT errors, key fetch errors, etc.
        raise AppleAuthError(f"apple token verification failed: {exc}") from exc
    subject = claims.get("sub")
    if not subject:
        raise AppleAuthError("apple token missing sub")
    return AppleIdentity(subject=subject, email=claims.get("email"))
```
- [ ] **Step 4:** run → PASS (5 tests).
- [ ] **Step 5:** commit `feat(auth): Apple identity-token verification (RS256 + aud/iss/exp)`.

---

## Task 3: Repo — reverse legacy lookup + Apple-identity linking

**Files:** Modify `server_v2/identity_repo.py`; Test `tests/test_identity_repo_apple.py`

- [ ] **Step 1: failing test** — `tests/test_identity_repo_apple.py`:
```python
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server_v2 import identity_repo as repo
from server_v2.identity_models import Base, UserIdentity


class AppleRepoTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def test_legacy_player_for_user_roundtrips(self):
        with self.Session() as s:
            _f, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            repo.map_legacy_player(s, legacy_player_id="me", user_id=owner.id)
            s.commit()
            self.assertEqual(repo.legacy_player_for_user(s, owner.id), "me")
            self.assertIsNone(repo.legacy_player_for_user(s, "no_such_user"))

    def test_link_apple_identity_is_idempotent_and_resolvable(self):
        with self.Session() as s:
            _f, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            repo.link_apple_identity(s, user_id=owner.id, subject="A.sub.1", email="a@b.c")
            repo.link_apple_identity(s, user_id=owner.id, subject="A.sub.1", email="a@b.c")  # idempotent
            s.commit()
            self.assertEqual(s.query(UserIdentity).count(), 1)
            self.assertEqual(repo.get_user_by_apple_subject(s, "A.sub.1").id, owner.id)
```
- [ ] **Step 2:** run → FAIL (`legacy_player_for_user` missing).
- [ ] **Step 3: add to `server_v2/identity_repo.py`** (use the existing imports; add `LegacyPlayerMap` is already imported):
```python
def legacy_player_for_user(session: Session, user_id: str) -> str | None:
    """Reverse of user_id_for_legacy_player: the legacy player_id ('me'/'p_*') for a user, if any."""
    row = session.execute(
        select(LegacyPlayerMap).where(LegacyPlayerMap.user_id == user_id)
    ).scalars().first()
    return row.legacy_player_id if row else None


def link_apple_identity(session: Session, *, user_id: str, subject: str, email: str | None = None) -> UserIdentity:
    """Idempotently link an Apple `sub` to a user. If the sub already exists, return it (no duplicate)."""
    existing = session.execute(
        select(UserIdentity).where(UserIdentity.provider == "apple", UserIdentity.subject == subject)
    ).scalars().first()
    if existing is not None:
        return existing
    identity = UserIdentity(user_id=user_id, provider="apple", subject=subject, email=email)
    session.add(identity)
    session.flush()
    return identity
```
- [ ] **Step 4:** run → PASS. Also run `tests.test_identity_repo tests.test_identity_repo_sessions` → still PASS (no regression).
- [ ] **Step 5:** commit `feat(auth): repo — legacy_player_for_user + idempotent link_apple_identity`.

---

## Task 4: Auth endpoints (`/api/v2/auth/*`)

**Files:** Create `server_v2/auth_api.py`; Test `tests/test_auth_api.py`

**Context for the implementer:** Build a FastAPI `APIRouter(prefix="/api/v2/auth")`. The audience comes from `os.environ["AI_CADDIE_APPLE_BUNDLE_ID"]` (raise 503 if unset, like the admin-not-configured pattern). Session TTL from `AI_CADDIE_SESSION_TTL_HOURS` (default 24). Use `db.session_scope()` for DB work, `apple_auth.verify_apple_identity_token`, and the 1a repo. The Apple-token verification's `signing_key_resolver` must be **overridable in tests** — read it from a module-level hook `apple_auth.verify_apple_identity_token` and let the test monkeypatch a thin wrapper; cleanest: `auth_api` calls a small local `_verify(token)` that the test patches. Endpoints:
- `POST /api/v2/auth/apple` (public) — body `{identityToken}`. Verify → `get_user_by_apple_subject`; if found and not `deleted_at`, `mint_session_token` (TTL), return `{token, expiresAt, userId}`. If unknown sub → 403 `{"detail": "apple identity not linked"}`.
- `POST /api/v2/auth/apple/link` (admin-gated by the main gate — Task 5) — body `{identityToken, userId?}`. Verify → `link_apple_identity(user_id=userId or OWNER_ID, subject, email)`. Return `{ok, userId, subject}`.
- `POST /api/v2/auth/refresh` (needs a live session bearer) — mint a new session (`refresh_of`=old id), revoke the old, return `{token, expiresAt}`.
- `POST /api/v2/auth/logout` (needs a live session bearer) — `revoke_session(old)`, return `{ok: true}`.

A `current_session(request) -> AuthSession` dependency resolves `Authorization: Bearer` via `resolve_session_token`; raise 401 if absent/invalid.

- [ ] **Step 1: failing test** — `tests/test_auth_api.py` (patches the verifier; drives endpoints via `TestClient`; uses a temp sqlite + migrates it; seeds an owner + link). Full test:
```python
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from server_v2 import db
from server_v2.apple_auth import AppleIdentity

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "com.example.aicaddie"


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(db.reset_engine_for_tests)
        self._tmp = tempfile.TemporaryDirectory(); self.addCleanup(self._tmp.cleanup)
        url = f"sqlite:///{Path(self._tmp.name) / 'identity.db'}"
        self._env = mock.patch.dict(os.environ, {
            "AI_CADDIE_DATABASE_URL": url, "AI_CADDIE_APPLE_BUNDLE_ID": BUNDLE,
            "AI_CADDIE_DATA_MODE": "fixture", "AI_CADDIE_SECURITY_PROFILE": "", "AI_CADDIE_ADMIN_TOKEN": "",
        }); self._env.start(); self.addCleanup(self._env.stop)
        db.reset_engine_for_tests()
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        # seed an owner user mapped to 'me'
        from server_v2 import identity_repo as repo
        with db.session_scope() as s:
            _f, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            repo.map_legacy_player(s, legacy_player_id="me", user_id=owner.id)
            self.owner_id = owner.id
        from server_v2.main import app
        self.client = TestClient(app)

    def _patch_verify(self, subject="A.sub.1", email="a@b.c"):
        return mock.patch("server_v2.auth_api._verify", return_value=AppleIdentity(subject=subject, email=email))

    def test_unknown_apple_sub_is_403_not_autocreated(self):
        with self._patch_verify(subject="UNKNOWN"):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 403)

    def test_link_then_signin_mints_resolvable_session(self):
        # owner links their Apple sub (admin path is open in this dev profile)
        with self._patch_verify(subject="A.sub.1"):
            r = self.client.post("/api/v2/auth/apple/link", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 200, r.text)
        with self._patch_verify(subject="A.sub.1"):
            r = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"})
        self.assertEqual(r.status_code, 200, r.text)
        token = r.json()["token"]
        self.assertTrue(token)
        # the minted session token now authorizes a player-scoped read as the owner
        h = self.client.get("/api/v2/history/summary", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(h.status_code, 200)

    def test_logout_revokes(self):
        with self._patch_verify(subject="A.sub.1"):
            self.client.post("/api/v2/auth/apple/link", json={"identityToken": "t"})
            token = self.client.post("/api/v2/auth/apple", json={"identityToken": "t"}).json()["token"]
        out = self.client.post("/api/v2/auth/logout", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(out.status_code, 200)
        again = self.client.get("/api/v2/history/summary", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(again.status_code, 401)  # revoked → no longer resolves
```
*(Note: `test_link_then_signin...` and `test_logout...` also exercise Task 6's resolution wiring; they will go green only after Tasks 5+6. The implementer should get `test_unknown_apple_sub_is_403_not_autocreated` + the endpoint shapes green here, then the cross-cutting two pass after Task 6. This is intentional — flag it, don't delete the assertions.)*
- [ ] **Step 2:** run → FAIL (no `auth_api`).
- [ ] **Step 3: implement `server_v2/auth_api.py`** with the four endpoints + `current_session` + a module-level `_verify(token)` wrapper that reads `AI_CADDIE_APPLE_BUNDLE_ID` and calls `apple_auth.verify_apple_identity_token`. Return 503 if the bundle id is unset. Use `db.session_scope()`. On `/auth/apple`: reject (403) unknown sub and soft-deleted users.
- [ ] **Step 4:** `test_unknown_apple_sub_is_403_not_autocreated` PASSES (the cross-cutting two await Task 6).
- [ ] **Step 5:** commit `feat(auth): /auth/apple (+ link/refresh/logout) session endpoints`.

---

## Task 5: Wire the router + gate `/auth/apple/link` as admin

**Files:** Modify `server_v2/main.py`; Modify `tests/test_codex_sec2.py`

- [ ] **Step 1:** add a failing assertion to `tests/test_codex_sec2.py` (or the route-policy test): `_requires_admin_token("POST", "/api/v2/auth/apple/link", QueryParams())` is `True`, and `_requires_admin_token("POST", "/api/v2/auth/apple", QueryParams())` is `False`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** in `server_v2/main.py`: `from .auth_api import auth_router` and `app.include_router(auth_router)` next to the admin_router include (~line 159); add `"/api/v2/auth/apple/link"` to the `exact_paths` POST set in `_requires_admin_token` (~line 268).
- [ ] **Step 4:** run the route-policy test → PASS.
- [ ] **Step 5:** commit `feat(auth): mount auth router; gate /auth/apple/link as admin-only`.

---

## Task 6: Resolve session tokens in `resolve_request_player`

**Files:** Modify `server_v2/players_api.py`; Test `tests/test_session_resolution.py`

- [ ] **Step 1: failing test** — `tests/test_session_resolution.py`: build two users (owner→'me', member→'p_xxx'), mint a session for each via the repo, assert `resolve_request_player` with `Bearer <ownerToken>` → 'me', with `<memberToken>` → 'p_xxx' (**isolation**), a revoked/expired token → None, a soft-deleted user's token → None, and that an admin token still → 'me' and a legacy player token still resolves (no regression). Use a temp sqlite + migrate; build raw `Request` objects (mirror `tests/test_players_api_auth.py`).
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** in `server_v2/players_api.py`, add a helper and a branch in `resolve_request_player`:
```python
def _player_for_session_token(token: str) -> str | None:
    """A Phase-1b Apple session bearer → the user's legacy player_id, or None.

    None when the token is not a live session, the user is soft-deleted, or the user
    has no legacy_player_map entry yet."""
    from datetime import datetime, timezone  # local import: keep module import-light
    from server_v2 import db
    from server_v2 import identity_repo as repo
    from server_v2.identity_models import User
    try:
        with db.session_scope() as session:
            sess = repo.resolve_session_token(session, token)
            if sess is None:
                return None
            user = session.get(User, sess.user_id)
            if user is None or user.deleted_at is not None:
                return None
            return repo.legacy_player_for_user(session, sess.user_id)
    except Exception:
        return None  # identity store unavailable → fall through to admin/dev/None
```
Then in `resolve_request_player`, after the `players.resolve_token` miss and before the admin check:
```python
    if token:
        player_id = players.resolve_token(token)
        if player_id is not None:
            return player_id
        session_player = _player_for_session_token(token)   # NEW: Phase-1b Apple session token
        if session_player is not None:
            return session_player
    if _admin_token_grants_owner(request):
        return OWNER_ID
    return None
```
- [ ] **Step 4:** run `tests.test_session_resolution` → PASS; run `tests.test_players_api_auth tests.test_auth_api` → PASS (the Task-4 cross-cutting assertions now go green).
- [ ] **Step 5:** commit `feat(auth): resolve Apple session tokens to the user's legacy player_id`.

---

## Task 7: Document config

**Files:** Modify `.env.example`

- [ ] **Step 1:** add to `.env.example` (near the Database section): `AI_CADDIE_APPLE_BUNDLE_ID=` (commented guidance: the iOS app's bundle id — the Apple identity-token `aud`) and `AI_CADDIE_SESSION_TTL_HOURS=24`. Confirm `tests/test_deployment_manifests.py` still passes (only add if its placeholder test doesn't require these; if it does enumerate every key, add them to the allowlist not the required list).
- [ ] **Step 2:** commit `docs(auth): document AI_CADDIE_APPLE_BUNDLE_ID + session TTL`.

---

## Task 8: Phase-1b green gate + PR

**Files:** none (verification)

- [ ] **Step 1:** full suite — `AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests` → all PASS. **(Run on the homeserver or a fresh box if the local box is memory-pressured — never leave uvicorn servers running; this gate uses TestClient, not a live server.)**
- [ ] **Step 2:** `uv run python -m py_compile $(git ls-files '*.py')` → exit 0.
- [ ] **Step 3:** `uv sync --frozen` → no drift.
- [ ] **Step 4:** push `superpowers/phase1b-apple-auth`; open PR to `integration/v2` (body: what 1b adds, the no-auto-create model, the deferred member-onboarding UX, and that 1c threads the resolved id into the IDOR sites). **No `--delete-branch`.**
- [ ] **Step 5:** confirm CI (backend+frontend+docker) green; then the independent **Codex whole-branch review** + a **final Claude review** before merge (per the 1a process). Merge only on green + reviews clear.

---

## Self-Review

**Spec coverage (§5):** Apple sign-in → `user_identities` ✅ (Task 3 link + Task 4 endpoints); owner = admin super-user ✅ (admin-bootstrapped link); scoped session tokens with TTL + refresh + revocation ✅ (Tasks 4/6, reusing 1a mint/resolve/revoke); resolution into the per-user addressing ✅ (Task 6). Deferred by design: member self-onboarding UX, watch device-scoped token, DB-level `DateTime(timezone=True)`.

**Security checks:** no auto-create (unknown sub → 403, Task 4); `/auth/apple/link` admin-gated (Task 5); session resolution rejects revoked/expired (1a) + soft-deleted users (Task 6); existing admin-token + legacy player-token paths untouched (Task 6 keeps them first/last; regression-tested). The new `/auth/apple` is public **by necessity** (it is the authentication entry point) and only *mints* a token for an already-linked identity — it grants no data by itself.

**No placeholders:** every code step is complete. The Task-4 test deliberately includes two assertions that go green after Task 6 — called out, not hidden.

**Consistency:** `_verify` (Task 4) is the monkeypatch seam used by `tests/test_auth_api.py`; `legacy_player_for_user`/`link_apple_identity` names match between Task 3 impl and Tasks 4/6 consumers; `resolve_session_token`/`mint_session_token`/`revoke_session` are the 1a repo functions (unchanged).
