# Member onboarding — Apple sign-in auto-register (Phase A) — plan

> **For agentic workers:** TDD, one commit per task. Implements `docs/superpowers/specs/2026-06-28-member-onboarding-apple-design.md` exactly.

**Goal:** First-time Apple sign-in (unknown sub) auto-provisions a member account + a fresh isolated player scope + mints a session (today it 403s). See the spec for the security rationale (aud-bound + Phase 1c/2 isolation), the linchpin (`LegacyPlayerMap` row, map-only), and all decisions.

**Tech:** Python 3.12, FastAPI, `uv`, stdlib `unittest`. Tests follow `tests/test_auth_api.py` (Alembic-migrated tmp SQLite, `_verify` monkeypatch seam, open-dev profile) + `tests/test_identity_repo.py` (in-memory repo units). Per task: failing test → see it fail → minimal impl → see it pass → commit (trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`). Full suite green after each task (`AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests`). NEVER start uvicorn/chromium.

---

## Task 1 — `provision_member` repo helper (`server_v2/identity_repo.py`)

Compose the provisioning into one unit-testable helper (keeps the endpoint thin).
- **Test** (`tests/test_identity_repo.py`, append): on an in-memory DB with a seeded owner family, `provision_member(session, family_id=fam, display_name="Kid", pid="p_abcd1234", subject="sub-x", email="k@e.com")` returns the new `User` (role="member", family_id=fam); `legacy_player_for_user(member.id) == "p_abcd1234"`; `get_user_by_apple_subject("sub-x").id == member.id`. A second call with the SAME subject (different pid) raises `IdentityConflictError`.
- **Impl:** `def provision_member(session, *, family_id, display_name, pid, subject, email=None) -> User:` → `member = add_user(family_id=family_id, display_name=display_name, role="member")` → `map_legacy_player(legacy_player_id=pid, user_id=member.id)` → `link_apple_identity(user_id=member.id, subject=subject, email=email)` → return `member`. (No `players.create_player` — map-only.)
- Commit `feat(identity): provision_member helper (user + legacy map + apple link)`.

## Task 2 — `/auth/apple` auto-provision + displayName + playerId (`server_v2/auth_api.py`, `server_v2/models.py`)

- **Tests** (`tests/test_auth_api.py`): (a) REVERSE `test_unknown_apple_sub_is_403_not_autocreated` → `test_unknown_apple_sub_autoregisters`: fresh sub → 200 + `{token, userId, playerId}`; `_resolves_to(token)` is a NEW user id ≠ `self.owner_id`; the resolved player_id (assert via `legacy_player_for_user`) is a fresh `p_*` ≠ `"me"`; `GET /api/v2/history/rounds` with `Bearer <token>` → 200 with empty rounds (isolation; **must assert player_id ≠ "me" AND empty**, per the open-dev-profile missing-map=OWNER gotcha). (b) known sub → 200, same user, returns its existing playerId. (c) `displayName` in the body → the new `User.display_name`; absent → email local-part / placeholder. (d) owner family missing (no `me` map) → 400.
- **Impl:** add `displayName: str | None = None` to `AppleSignInRequest` (models.py). In `apple_sign_in`, when `get_user_by_apple_subject` is None/deleted: resolve owner family (`user_id_for_legacy_player("me")` → `User.family_id`; None → 400 like `apple_link`); `pid = "p_" + secrets.token_hex(4)`; `display_name = body.displayName or (ident.email.split("@")[0] if ident.email else "Family member")`; `provision_member(...)`; mint session; return `{token, expiresAt, userId, playerId: pid}`. On `IdentityConflictError` (concurrent first sign-in) → re-`get_user_by_apple_subject` and mint for that user (no 500). For the KNOWN-sub path, also return `playerId = legacy_player_for_user(user.id)`. Update the response model if one is used.
- Commit `feat(auth): /auth/apple auto-registers a member on first sign-in`.

## Task 3 — `GET /api/v2/admin/family/users` roster (`server_v2/players_api.py` admin_router or a new module; `server_v2/identity_repo.py`)

- **Tests:** repo unit — `list_family_users(session, family_id)` returns the owner + member rows with `legacy_player_id` joined. Route — admin token → 200 lists the seeded owner + an added member (id/displayName/role/createdAt/deletedAt/playerId); a player/member token → 401 (admin-only via the `/api/v2/admin/*` gate). Reuse the `test_auth_api`/`test_server_v2_admin_protection` patterns.
- **Impl:** `list_family_users(session, family_id)` (select Users where family_id, left-join LegacyPlayerMap for playerId). Route on the existing admin router: `@admin_router.get("/family/users")` → resolve owner family → project. Response model in models.py.
- Commit `feat(family): admin GET /api/v2/admin/family/users roster`.

## Task 4 — member isolation + manual-round round-trip (integration test only)

- **Test** (`tests/test_member_onboarding_isolation.py`, new — follow `test_auth_api` setup but seed owner FIXTURE data like `test_evidence_isolation`/`test_idor_route_isolation` so the owner has rounds): a fresh member auto-registers → with their bearer, `GET /api/v2/history/rounds` and `/api/v2/history/stats` show **none** of the owner's rounds/data (empty); then `POST /api/v2/players/{playerId}/rounds` with a minimal manual round succeeds (their pid) and `GET /api/v2/history/rounds` now shows THAT round (their own) — proving the member has a working, isolated scope. (Confirm the manual-round ingest contract from `main.py ingest_player_round` + an existing round-ingest test.)
- Commit `test(onboarding): member isolated scope + manual round round-trip`.

## Task 5 — green gate + PR

Full suite `AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests` (0 fail), `py_compile` changed files, `uv sync --frozen`. Self-review (spec coverage; auto-create only creates role=member; the linchpin map always created; owner byte-for-byte; admin endpoint gated). Push; `gh pr create --base integration/v2` (no `--delete-branch`); body: the auto-register flow, the security posture (aud-bound + isolation, reversing 1b), the playerId/displayName/admin-roster additions, and the deferrals (Garmin self-bind Phase B; currentPlayer:null polish). Then the independent **Codex whole-branch review + final Claude review** (scrutinize the auto-create reversal); merge only on green + reviews clear.
