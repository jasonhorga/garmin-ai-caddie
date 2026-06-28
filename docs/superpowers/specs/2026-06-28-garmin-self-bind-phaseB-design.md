# Garmin self-binding (Phase B) — backend slice — design

**Status:** design, owner-goal-directed. Branch `superpowers/garmin-self-bind` off integration/v2 @ 82a55aa. Part of the [multi-user / family redesign](2026-06-26-phase0-findings.md). This is the **backend** slice; the iOS UI (Sign-in-with-Apple + member-scoping the existing Garmin WebView bind client) is a separate iOS slice (macOS CI).

## Goal

Let a Garmin family member **bind their own Garmin** and sync **their** account into **their** partition (`data/players/<id>/`). Non-Garmin members skip this. Reuses the EXISTING cookie-capture pipeline (the iOS `WKWebView` already captures the garmin.cn cookie and POSTs it to `/api/v2/sync/garmin/session`, which accepts `ios_web_login`) — Phase B **generalizes that owner path to per-member**. No stored Garmin passwords (captured-cookie model, not the headed-playwright credential model); the server does NOT self-heal a member's expired cookie (they re-bind via the WebView when it expires).

## Key facts (from the architecture map)

- Sync is single-owner today: `GarminCnWebSessionConnector(root=ROOT).sync(...)` (`ai_caddie/connectors/garmin_cn.py`), driven by `POST /api/v2/sync/garmin` (admin-only). The bind endpoint `POST /api/v2/sync/garmin/session` → `save_garmin_cn_web_session(..., root=SESSION_ROOT=ROOT)` (`server_v2/session.py`).
- **`_fetch_runtime(root)`** (`garmin_cn.py:67-96`) monkeypatches process-global path constants for the run: `token_dir = root/.garmin_tokens` (cookie/csrf) and `data_dir = root/data` (scorecards/shots/summary). Both hang off ONE `root` with a FIXED sub-layout → you cannot target `data/players/<id>/` by just changing root (you'd get `data/players/<id>/data/...`). **Decoupling cookie-dir from data-dir is THE core seam.**
- A player's data is read from `data/players/<id>/{scorecards,shots,...}` (`_player_data_dir`, `_load_dirs`). Manual ingest already writes there (`round_ingest.ingest_round`). So a member's Garmin sync must land in `data/players/<id>/{scorecards,shots,summary.json,club_bag.json}`.
- `save_garmin_cn_web_session(root=)` already takes a root; `ALLOWED_SESSION_SOURCES` already includes `ios_web_login`. Token resolution already accepts member Apple session tokens (`resolve_request_player` / `_player_for_session_token`, scope=="user").
- The global `_SYNC_LOCK` serializes syncs (the connector mutates process-global module state).

## Design

**1. Per-player cookie store.** A member's captured cookie/csrf is stored under their partition: `data/players/<id>/.garmin_tokens/{web_cookie.txt,csrf.txt}` (chmod 600, reusing `save_garmin_cn_web_session`'s existing write + the partition convention). Owner stays at the flat `.garmin_tokens/` (byte-for-byte). A small resolver `garmin_token_dir(player_id)` (owner → `ROOT/.garmin_tokens`; member → `ROOT/data/players/<id>/.garmin_tokens`).

**2. Connector path decoupling.** Change `_fetch_runtime` to accept an explicit **`token_dir`** and **`data_dir`** (instead of deriving both from one `root`), keeping the current owner values as defaults (token=`ROOT/.garmin_tokens`, data=`ROOT/data`) so the owner path is byte-for-byte. `GarminCnWebSessionConnector` gains an optional `player_id` (or explicit token_dir/data_dir): owner → current; member → token=`data/players/<id>/.garmin_tokens`, data=`data/players/<id>` (so scorecards land at `data/players/<id>/scorecards`, matching the readers — NO extra `data/` level). The course-ref/snapshot writes likewise target the member partition (or stay owner-shared if course-ref is global public data — decide per the connector's snapshot step; course geometry/par is public, so course-ref can stay shared).

**3. Per-player sync + no member self-heal.** A member sync uses the member's stored cookie; `force_refresh_auth`/the headed-playwright self-heal is **owner-only** (no member creds stored) — a member sync with an expired/missing cookie fails with a clear "re-bind your Garmin" error, not a 500, and never falls back to the owner's cookie/profile. After a member sync, invalidate THAT player's stats cache (mirror `round_ingest._invalidate_cache`).

**4. Member-scoped routes** (mirror `POST /api/v2/players/{id}/rounds`):
- `POST /api/v2/players/{id}/sync/garmin/session` — bind a captured web session for player `{id}`. Body = the existing session payload (webSessionHeader/antiForgeryValue/source). Guard: `acting = Depends(current_player_id); if acting != OWNER_ID and acting != id: 403`. Stores under the player's token dir.
- `POST /api/v2/players/{id}/sync/garmin` — run the sync for player `{id}` (owner or self). Same guard. Writes to the player's partition; `_SYNC_LOCK` (optionally per-player keyed). Owner-only self-heal.
- Both are **GET-allowlist-irrelevant** (they're POST) and must NOT be in the admin `exact_paths` (so a member token reaches them via `current_player_id`). The legacy admin `/api/v2/sync/garmin[/session]` stays owner-only, unchanged.

## Out of scope (deferred to the iOS slice / later)

- **iOS UI**: Sign-in-with-Apple login screen (net-new; backend ready) + switching the existing `GarminSessionClient` from the admin token to a SiwA **bearer** + a member-scoped bind/sync entry in onboarding. Needs macOS CI.
- **Member unattended/cron sync** (would need stored member creds — explicitly rejected for secret posture). Members sync on-demand after binding; re-bind when the cookie expires.
- Per-player `_SYNC_LOCK` keying (optional optimization; the global lock is correct, just serializes).

## Testing (backend, stdlib unittest, `AI_CADDIE_DATA_MODE=fixture` for the gate)

- **Path decoupling**: `_fetch_runtime(token_dir=…, data_dir=…)` sets the module globals to exactly those (owner defaults unchanged); a member connector resolves token=`data/players/<id>/.garmin_tokens`, data=`data/players/<id>` (NO double `data/`).
- **Bind (member-scoped)**: `POST /players/<member>/sync/garmin/session` with a captured payload → writes `data/players/<member>/.garmin_tokens/web_cookie.txt` (chmod 600), NOT the owner's; a member binding for `me` or another player → 403; owner can bind for any.
- **Sync (member-scoped)**: with the connector's network fetch MOCKED to return a couple of scorecards/shots, `POST /players/<member>/sync/garmin` → rounds land in `data/players/<member>/scorecards`, the member's `GET /api/v2/history/rounds` shows them, and they are isolated from the owner (and vice-versa); the member's stats cache is invalidated. A member with no bound cookie → a clear 4xx "re-bind", not a 500; never reads the owner cookie.
- **Owner byte-for-byte**: the existing `/api/v2/sync/garmin` + `/api/v2/sync/garmin/session` tests (`tests/test_server_v2_sync_run.py`, `tests/test_server_v2_sync_session.py`) still pass unchanged; owner token_dir/data_dir resolve to the current flat paths.
- Reuse harness patterns from `tests/test_member_onboarding_isolation.py` + `tests/test_round_ingest_api.py`.

## Review

Subagent-driven + the independent Codex whole-branch + final Claude review (Garmin cookie handling + the path-decoupling + member isolation + no-cross-cookie-fallback are the scrutiny points). Merge only on green CI + reviews clear → integration/v2 (no `--delete-branch`).
