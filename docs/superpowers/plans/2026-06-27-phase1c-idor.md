# Phase 1c — Close the History IDOR + Identity Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Thread the resolved caller's `player_id` into the data-loader call sites that today default to the OWNER, and make the four core mobile/caddie GET reads player-scoped — so a family member's session/legacy token reaches them and gets **their own** history (closing the high-severity "any authenticated caller silently gets the owner's full history + bag" IDOR). Plus two identity-hardening items the 1a/1b reviews deferred.

**Architecture:** Mirror the already-correct `mobile_course_options` pattern exactly: the response builder takes `player_id`, the route handler supplies it via `Depends(current_player_id)`, and the route is listed in BOTH the admin gate (already true) and `is_player_scoped_route` (the new part). `player_id` flows into `load_history_data_for_mode(player_id=...)`, which is already player-partitioned (`data_source.py` / `history.py`).

**Tech Stack:** FastAPI, SQLAlchemy/Alembic (identity), uv, unittest. Tests on SQLite + `TestClient` through the real middleware.

**Scope (1c of: 1a✅ 1b✅ 1c-this), owner-confirmed:**
- IN: UNIQUE on `legacy_player_map.user_id` (makes session→player isolation structural); enforce `scope=="user"` on player-route session resolution; thread `player_id` + player-scope the **four GET reads** — `mobile_round_package`, `mobile_course_package`, `mobile_round_reconciliation`, `caddie_context`; member-isolation tests.
- **DEFERRED to Phase 2 (per-user store partitioning), explicitly:** the `round_id`-addressed live event log (`MOBILE_ROOT`) + `source_ref`-addressed annotations (`ANNOTATION_ROOT`) are NOT per-user-partitioned, so a member who knows another member's opaque `round_id` could still read that round's events/annotations. **Accepted as a LOW-severity residual for the trusted-family model; Phase 2 closes it by partitioning those stores.** Also deferred: `POST .../reconciliation/apply` (mutating; `is_player_scoped_route` is GET-only + the handler has its own `require_admin_token`), `geometry/hole` source_ref reads (route scope is query-param-conditional — needs a param-aware mechanism the path allowlist can't express), and `DateTime(timezone=True)` (the inline naive→UTC guards from 1a/1b already work).

**Grounding (verified by the Phase-1c code map, integration/v2 @ 6e81d15):**
- The IDOR: `data_source.py:14 load_history_data_for_mode(mode=None, *, player_id=OWNER_ID)`. Calls WITHOUT `player_id` (default OWNER): `mobile.py:49` (`build_mobile_round_package_response`), `mobile.py:76` (`build_mobile_course_package_response`), `mobile.py:161` (`reconcile_mobile_round_response`), `caddie.py:61` (`build_caddie_context_response`). (Also `mobile.py:169` reconcile-apply + `geometry.py:93/117` — DEFERRED.)
- Clean reference (already correct): `mobile.py:100 build_mobile_course_options_response(player_id=OWNER_ID)` → `load_history_data_for_mode(player_id=player_id)`; handler `main.py:824 mobile_course_options(player_id: str = Depends(current_player_id))`; route is in the admin gate (`main.py:255`) AND `is_player_scoped_route` (`players_api.py:151`).
- Handlers (NO `current_player_id` dep today): `mobile_round_package` `main.py:809-821`, `mobile_course_package` `main.py:829-849`, `mobile_round_reconciliation` `main.py:899-901`, `caddie_context` `main.py:678-712`. `current_player_id` already imported (`main.py:66`).
- `is_player_scoped_route` `players_api.py:137` (GET-only allowlist, 6 prefixes). `_requires_admin_token` `main.py:236` already admin-gates these four GETs (`:254 :256 :247 :266`). So **only the allowlist + the `player_id` threading change** — the admin gate already lists them.
- `_player_for_session_token` `players_api.py:78` resolves a session token; `AuthSession.scope` exists (`identity_models.py`) but isn't checked.
- Tests to update (assert the OLD auth/scope): `test_server_v2_admin_protection.py:509-541` (package/reconcile/course-options 401 when admin configured), `:619-645` (200 without admin + `assert_called_once_with(player_id="me")` — the threaded-value model), `:379-391` (caddie/context 401); `test_players_api_auth.py:111-121` (line 120 asserts caddie/context `is_player_scoped_route` is **False** → must flip to True; add the new routes). Isolation models: `test_player_side_isolation.py` (best), `test_history_player_scope.py:42-88`, `test_server_v2_data_source.py:65-90`.

**Conventions:** commit trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`; tests on SQLite; don't push (controller handles PR); **2GB box — never run standalone uvicorn; use TestClient**.

---

## Task 1: Migration 0002 — UNIQUE on legacy_player_map.user_id

**Files:** `server_v2/identity_models.py`, `migrations/versions/0002_*.py`, `tests/test_identity_migration_0002.py`

Makes the session→player isolation structural: one user maps to exactly one legacy player (the seeder already guarantees it; `legacy_player_for_user` uses `.first()` and relies on this invariant).

- [ ] **Step 1: failing test** — `tests/test_identity_migration_0002.py`: build the schema via `Base.metadata.create_all` on sqlite, insert two `LegacyPlayerMap` rows with the SAME `user_id` (different legacy ids), assert the second raises `IntegrityError` (the unique constraint). Also assert `alembic upgrade head` on a temp sqlite produces a schema where that insert fails.
```python
import tempfile, unittest
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from server_v2.identity_models import Base, LegacyPlayerMap, User, Family

REPO_ROOT = Path(__file__).resolve().parents[1]


class Migration0002Tests(unittest.TestCase):
    def test_user_id_is_unique_in_legacy_map(self):
        engine = create_engine("sqlite://", future=True)
        Base.metadata.create_all(engine)
        with Session(engine) as s:
            s.add(Family(id="f1", name="F")); s.add(User(id="u1", family_id="f1", display_name="A"))
            s.add(LegacyPlayerMap(legacy_player_id="me", user_id="u1"))
            s.add(LegacyPlayerMap(legacy_player_id="p_x", user_id="u1"))  # same user → must fail
            with self.assertRaises(IntegrityError):
                s.commit()

    def test_alembic_head_enforces_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{Path(tmp) / 'm.db'}"
            cfg = Config(str(REPO_ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
            cfg.set_main_option("sqlalchemy.url", url)
            command.upgrade(cfg, "head")
            eng = create_engine(url, future=True)
            with Session(eng) as s:
                s.add(Family(id="f1", name="F")); s.add(User(id="u1", family_id="f1", display_name="A"))
                s.add(LegacyPlayerMap(legacy_player_id="me", user_id="u1"))
                s.add(LegacyPlayerMap(legacy_player_id="p_x", user_id="u1"))
                with self.assertRaises(IntegrityError):
                    s.commit()
```
- [ ] **Step 2:** run → FAIL (no unique constraint; both rows commit).
- [ ] **Step 3:** in `server_v2/identity_models.py`, add a unique constraint to `LegacyPlayerMap` — add `__table_args__ = (UniqueConstraint("user_id", name="uq_legacy_map_user"),)` (import `UniqueConstraint` if not already imported). Then autogenerate the migration:
```bash
AI_CADDIE_DATABASE_URL="sqlite:///$(pwd)/.tmp0002.db" uv run alembic -c alembic.ini revision --autogenerate -m "legacy_map_user_unique" --rev-id 0002_legacy_map_user_unique
rm -f .tmp0002.db
```
Open the generated `migrations/versions/0002_*.py`; confirm `upgrade()` uses `op.create_unique_constraint("uq_legacy_map_user", "legacy_player_map", ["user_id"])` (with batch mode for SQLite if autogen wrapped it — `render_as_batch=True` is already set in env.py). `down_revision = "0001_identity"`.
- [ ] **Step 4:** run → PASS (both tests).
- [ ] **Step 5:** regression: `uv run python -m unittest tests.test_identity_migration tests.test_identity_seed tests.test_identity_repo` → PASS (the seeder maps one legacy id per user, so the constraint holds).
- [ ] **Step 6:** commit `feat(identity): UNIQUE legacy_player_map.user_id — structural session→player isolation`.

---

## Task 2: Enforce `scope == "user"` on player-route session resolution

**Files:** `server_v2/players_api.py`, `tests/test_session_resolution_scope.py`

Today only `scope="user"` is minted, but `_player_for_session_token` doesn't check scope — a future watch/device-scoped token would otherwise grant full player-route access. Restrict player-route resolution to `scope="user"`.

- [ ] **Step 1: failing test** — `tests/test_session_resolution_scope.py`: mint a session with `scope="watch"` for a mapped owner, assert `resolve_request_player(_request(bearer=watch_token))` is `None` (a non-user scope does NOT grant player access); a `scope="user"` token still resolves to `"me"`. (Mirror `tests/test_session_resolution.py`'s setup — temp sqlite migrated + private profile + raw `Request`.)
- [ ] **Step 2:** run → FAIL (the watch-scoped token currently resolves to "me").
- [ ] **Step 3:** in `_player_for_session_token` (`players_api.py:78`), after resolving `sess` and before mapping the user, add:
```python
            if sess.scope != "user":  # only full user sessions authorize player-scoped routes
                return None
```
(place it right after the `if sess is None: return None` guard).
- [ ] **Step 4:** run → PASS. Regression: `uv run python -m unittest tests.test_session_resolution tests.test_session_route_access tests.test_auth_api` → PASS.
- [ ] **Step 5:** commit `feat(auth): only scope="user" sessions authorize player-scoped routes`.

---

## Task 3: Thread player_id + open the two mobile **package** reads

**Files:** `server_v2/mobile.py`, `server_v2/main.py`, `server_v2/players_api.py`, `tests/test_server_v2_admin_protection.py`

- [ ] **Step 1:** write/extend a failing test: with NO admin configured but a private profile + a member's legacy token, `GET /api/v2/mobile/rounds/{id}/package` and `GET /api/v2/mobile/courses/{gid}/package` return 200 and the builder is called with the member's `player_id` (not `"me"`). Patch the builders (`build_mobile_round_package_response`, `build_mobile_course_package_response`) to assert the `player_id` kwarg (mirror `test_server_v2_admin_protection.py:643`'s `assert_called_once_with(player_id="me")`).
- [ ] **Step 2:** run → FAIL (routes 401 a player token / builders called without player_id).
- [ ] **Step 3:**
  - `server_v2/mobile.py`: add `player_id: str = OWNER_ID` to `build_mobile_round_package_response` (`:49` enclosing fn) and `build_mobile_course_package_response` (`:76`); change their `load_history_data_for_mode()` to `load_history_data_for_mode(player_id=player_id)`. (Import `OWNER_ID` from `ai_caddie.rounds.players` if not present.)
  - `server_v2/main.py`: add `player_id: str = Depends(current_player_id)` to `mobile_round_package` (`:809`) and `mobile_course_package` (`:829`); pass `player_id=player_id` to the builder calls.
  - `server_v2/players_api.py`: add to `is_player_scoped_route` (`:145` return expression): `or (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/package"))` and `or (path.startswith("/api/v2/mobile/courses/") and path.endswith("/package"))`.
  - Update `tests/test_server_v2_admin_protection.py:509-541` + `:619-645`: the package reads now accept a player token (200 + threaded player_id) — adjust the assertions that expected admin-only 401 for a player-token request; keep the no-token / wrong-token → 401 (admin configured) cases.
- [ ] **Step 4:** run the new + updated tests → PASS.
- [ ] **Step 5:** commit `feat(auth): player-scope the mobile round/course package reads (thread player_id)`.

---

## Task 4: Thread player_id + open reconciliation-GET + caddie-context

**Files:** `server_v2/mobile.py`, `server_v2/caddie.py`, `server_v2/main.py`, `server_v2/players_api.py`, `tests/test_server_v2_admin_protection.py`, `tests/test_players_api_auth.py`

- [ ] **Step 1:** failing test: a member's token on `GET /api/v2/mobile/rounds/{id}/reconciliation` and `GET /api/v2/caddie/context?...` returns 200 with the builder called with the member's `player_id`. Also assert `is_player_scoped_route("GET", "/api/v2/caddie/context")` is now **True** (flips `test_players_api_auth.py:120`).
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:**
  - `server_v2/mobile.py`: add `player_id: str = OWNER_ID` to `reconcile_mobile_round_response` (`:161`); `load_history_data_for_mode(player_id=player_id)`.
  - `server_v2/caddie.py`: add `player_id: str = OWNER_ID` to `build_caddie_context_response` (`:61`); `load_history_data_for_mode(player_id=player_id)`. (Import `OWNER_ID`.)
  - `server_v2/main.py`: add `player_id: str = Depends(current_player_id)` to `mobile_round_reconciliation` (`:899`) and `caddie_context` (`:678`); pass it through.
  - `server_v2/players_api.py` `is_player_scoped_route`: add `or (path.startswith("/api/v2/mobile/rounds/") and path.endswith("/reconciliation"))` and `or path == "/api/v2/caddie/context"`.
  - Update `test_players_api_auth.py:111-121` (flip caddie/context to True, add the new routes) and `test_server_v2_admin_protection.py:379-391` (caddie/context now accepts a player token).
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(auth): player-scope mobile reconciliation-read + caddie context (thread player_id)`.

---

## Task 5: Member-isolation integration test (through the real gate)

**Files:** `tests/test_idor_route_isolation.py`

The high-severity property: a MEMBER's token on these four routes must get THEIR history (empty/own), never the owner's. Drive it through the REAL middleware in a PRIVATE profile (where the gate is active), using the `test_player_side_isolation.py` pattern (a `players.create_player` member + a populated owner).

- [ ] **Step 1:** write `tests/test_idor_route_isolation.py`: private profile + an admin token configured; create a member via `players.create_player` (patch `players.ROOT`/`history.ROOT` per `test_player_side_isolation.py`); give the OWNER some history (fixture) and the member none. For each of the 4 routes, assert: (a) the member's token → 200, (b) the response does NOT contain the owner's bag/history markers (the member gets empty/own data), (c) the owner (admin token) still sees the owner's data, (d) no-token → 401. Use the isolation assertions from `test_player_side_isolation.py:49-187` as the model for "does not leak owner data".
- [ ] **Step 2:** run → it must PASS on the code from Tasks 3–4 (this is the proof, not new behavior). If it fails, the threading is incomplete — fix the offending route.
- [ ] **Step 3:** commit `test(auth): member-token isolation on the four player-scoped reads`.

---

## Task 6: Phase-1c green gate + PR

- [ ] **Step 1:** full suite — `AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests` → all PASS. (TestClient only; never a live uvicorn — the 2GB box OOMs.)
- [ ] **Step 2:** `uv run python -m py_compile $(git ls-files '*.py')` → 0. `uv sync --frozen` → no drift.
- [ ] **Step 3:** push `superpowers/phase1c-idor`; open PR to `integration/v2` (body: closes the high-severity history IDOR on the four reads + the two hardening items; **explicitly** notes the deferred round_id/source_ref store residual → Phase 2, and the deferred reconcile-apply POST / geometry source_ref). **No `--delete-branch`.**
- [ ] **Step 4:** CI green → the independent **Codex whole-branch review** + a **final Claude review** (per 1a/1b). Merge only on green + reviews clear. **Pay special attention** in review to: does any of the four routes now leak owner data to a member (run the isolation lens), and is the residual correctly limited to the round_id/source_ref stores (not the history/bag)?

---

## Self-Review

**Spec coverage (Phase-0 B3.1 + the deferred hardening):** the highest-leverage IDOR fix (thread `player_id` into the OWNER-defaulting loaders) ✅ for the four reads; UNIQUE(legacy_player_map.user_id) ✅; scope enforcement ✅. Deferred (documented): reconcile-apply POST, geometry source_ref, the round_id/source_ref store partitioning (Phase 2), DateTime(timezone=True).

**Security checks:** each opened route gets `player_id` threaded BEFORE it's added to the allowlist (no window where it's reachable but unscoped); the admin/owner path is unchanged (owner → "me" → owner data); the member-isolation integration test (Task 5) proves no owner-history leak through the real gate. The residual (round_id/source_ref stores) is explicitly bounded + accepted for the trusted-family model + scheduled for Phase 2.

**Consistency:** `player_id: str = OWNER_ID` default on every builder (matches `build_mobile_course_options_response`); `Depends(current_player_id)` on every handler (matches `mobile_course_options`); the four routes are added to `is_player_scoped_route` AND were already in the admin gate (mirror of `mobile/courses/options`).

**No placeholders:** every step is concrete; the only autogen step (migration 0002) has an explicit verify + the constraint name `uq_legacy_map_user`.
