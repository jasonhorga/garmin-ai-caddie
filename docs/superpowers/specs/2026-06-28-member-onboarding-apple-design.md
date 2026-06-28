# Member onboarding — Apple sign-in auto-register (Phase A) — design

**Status:** design, owner-approved direction (chosen interactively). Branch `superpowers/member-onboarding-apple` off integration/v2 @ ce6d6e3 (post Phase 1+2). Part of the [multi-user / family redesign](2026-06-26-phase0-findings.md). This is the identity-onboarding slice; **per-member Garmin self-binding is a SEPARATE later phase (Phase B)**.

## Goal

Let a family member sign in with Apple and **auto-register on first sign-in**, immediately getting their OWN isolated (empty) data scope — so non-Garmin members (wife/son) are fully usable at once (log manual / Apple-Watch rounds), and Garmin members (daughter) get an account now and self-bind their Garmin later (Phase B). Reverses 1b's "no auto-create / owner bootstrap" stance.

## Why auto-create is safe here (security posture)

- **Audience binding:** `apple_auth.verify_apple_identity_token` requires `aud == AI_CADDIE_APPLE_BUNDLE_ID` (apple_auth.py; asserted by `test_apple_auth.py::test_wrong_audience_rejected`). Only a token minted by Sign-in-with-Apple **for this app's bundle id** verifies — so registration is bounded by **who has the app** (TestFlight/App Store distribution the owner controls), not open to the internet.
- **Isolation:** a freshly provisioned member gets a brand-new empty `data/players/<pid>/` partition; Phase 1c/2 ensure they read NO owner data (player-scoped reads glob only their own dir; the round-keyed aggregators stay admin-only). A stranger who somehow installs the app and signs in gets an inert empty account the owner can see and delete.

A future tightening (allowlist / approval) is easy to add if distribution widens — out of scope now (YAGNI).

## The linchpin (from the architecture map)

A session resolves to a data scope via `legacy_player_for_user` → a `LegacyPlayerMap` row. **No map row ⇒ resolution returns None ⇒ a secured-profile member gets 401; in the open dev/test profile it silently falls through to `OWNER_ID` (a leak surface).** Therefore **every auto-registered member MUST get a `LegacyPlayerMap(legacy_player_id=<fresh p_*>, user_id=<member>)` row.** That single row is **required and sufficient** for the member to log a manual round (`POST /api/v2/players/{pid}/rounds` creates the partition on demand) and read it back (`GET /api/v2/history/*`). The file-registry `players.create_player` is NOT used (avoids a two-store non-atomic orphan; the identity DB is the source of truth).

## Design

On `POST /api/v2/auth/apple`, when `get_user_by_apple_subject` returns None (today's 403), AUTO-PROVISION inside one `db.session_scope()`:
1. **Owner family lookup:** `owner_uid = user_id_for_legacy_player("me")`; if None → **400** "owner not provisioned" (mirrors `apple_link`). `family_id = User(owner_uid).family_id`.
2. **Fresh player id:** `pid = "p_" + secrets.token_hex(8)` (64-bit; map-only — no file registry). The endpoint retries with a new id if it collides (see step 4).
3. `member = add_user(family_id=family_id, display_name=<name>, role="member")`.
4. The linchpin map, **insert-only** (NOT the upserting `map_legacy_player`): `session.add(LegacyPlayerMap(legacy_player_id=pid, user_id=member.id)); flush()` — a PK collision raises `PlayerIdInUseError` so the endpoint retries with a fresh id, never silently re-pointing an existing member's scope.
5. `link_apple_identity(user_id=member.id, subject=ident.subject, email=ident.email)`.
6. `token, _ = mint_session_token(user_id=member.id, scope="user", expires_at=now+ttl)`.
7. Return `{"token", "expiresAt", "userId": member.id, "playerId": pid}`.

**Display name:** add optional `displayName: str | None` to `AppleSignInRequest` (the iOS app gets the user's name from Apple's first-authorization *response* — it is NOT in the JWT — and sends it on first sign-in). `<name>` = `displayName` or the email local-part or a placeholder ("Family member").

**Response shape:** both the known-sub and auto-register paths now also return `"playerId"` (the resolved/created legacy player id) — the iOS app needs it to address `POST /api/v2/players/{pid}/rounds`. (For a known sub, resolve it via `legacy_player_for_user`.)

**Concurrency:** two simultaneous first sign-ins of the same sub race on `UNIQUE(provider, subject)`; the loser's `link_apple_identity` raises `IdentityConflictError` → catch it and re-resolve as a now-known sub (mint a session for the existing user) rather than 500.

**Owner footgun (documented):** the owner MUST link via `/auth/apple/link` (admin bootstrap) BEFORE ever signing in with `/auth/apple`, else their sub auto-registers a spurious member account. Note this is **not** cleanly recoverable through the current APIs — `/auth/apple/link` refuses to move a sub already bound to a different user (`IdentityConflictError`), so undoing a mistaken owner auto-register today needs a manual DB correction (delete the spurious member + its identity/map). The owner's real `"me"` scope is never reassigned, so no data is exposed. A future admin re-link / delete-user endpoint would automate the recovery (deferred).

## Admin visibility (new)

There is no endpoint listing family USERS from the identity DB (only the legacy `/api/v2/admin/players` file registry, which map-only members won't appear in). Add **`GET /api/v2/admin/family/users`** (admin-gated by the `/api/v2/admin/*` rule): lists `User` rows in the owner's family, projecting `id / displayName / role / createdAt / deletedAt / playerId` (the mapped legacy id, if any). Lets the owner see who registered (and, in Phase B, pick who to bind to Garmin data).

## Out of scope (deferred)

- **Per-member Garmin self-binding + sync (Phase B)** — the big follow-on (the current Garmin sync is single-owner-cookie).
- **Member profile in their own overview:** a map-only member has `currentPlayer: null` in `/history/overview` (the profile block reads the file registry). Accepted for Phase A (history loads fine); a later polish can fall back to the identity `User.display_name`.
- **Allowlist / approval gate**, unifying `/admin/players` with the DB roster.

## Components / files

- `server_v2/auth_api.py` — `apple_sign_in` auto-provision branch; `AppleSignInRequest` + `displayName`; `playerId` in the response; a small provisioning helper (in `auth_api.py` or `identity_repo.py`).
- `server_v2/identity_repo.py` — possibly a `provision_member(session, *, family_id, display_name, pid, subject, email)` helper composing add_user+map+link (keeps the endpoint thin + unit-testable); reuse existing fns.
- `server_v2/players_api.py` (or a new `family_api.py`) — `GET /api/v2/admin/family/users`.
- `server_v2/models.py` — response/request model updates.

## Testing

- **Auto-register (integration, reverse the existing 403 test):** fresh sub → 200 + `{token, userId, playerId}`; the token resolves to a NEW user ≠ owner; a `LegacyPlayerMap` to a fresh `p_*` exists for that user; `GET /api/v2/history/rounds` with the new bearer returns **empty**. **Gotcha:** the suite runs the open-dev profile where a *missing* map resolves to OWNER — so assert the resolved player_id is **not** `"me"` AND history is empty (catches a missing-map regression).
- **Known sub** → same user, returns its existing playerId.
- **Concurrency** → simulate the second link raising IdentityConflictError → still returns a session for the existing user (no 500).
- **Owner family missing** → 400.
- **Member isolation** → the new member sees none of the owner's seeded fixture data; can log a manual round to their pid and read it back.
- **Admin family users list** → owner (admin) sees the registered member; a member token is 401 (admin-only).
- **displayName** → used when provided; email/placeholder fallback.
- Unit tests for the provisioning helper (mirror `test_identity_repo.py`). Full backend suite green; CI green.

## Review

Subagent-driven build + the independent **Codex whole-branch review + a final Claude review** (the auto-create reversal of 1b's posture must be scrutinized). Merge only on green CI + reviews clear → integration/v2 (no `--delete-branch`).
