# Cross-Review Remediation Plan — 2026-06-26

## What this is
Two independent whole-repo reviews of `integration/v2 @ df6a45d`:
- **Opus** — 5 parallel area agents (backend engine / API+security / web / mobile / tests+ops+infra).
- **Codex** (gpt-5.5) — one holistic pass.

Then a **cross-validation round**: each side read the other's findings, **confirmed or refuted them against the actual code**, and **extrapolated (举一反三)** to analogous bugs neither caught. Three systemic patterns were swept into **complete inventories** (appendix).

**Validation tags:** `[BOTH]` both reviews independently · `[codex✓opus]` codex-found, Opus-verified · `[opus✓codex]` Opus-found, codex-verified · `[NEW]` surfaced only in the cross/extrapolation round.

**Headline:** the package reorg is sound (clean boundaries, no cycles, all production path-roots correct + Docker-safe). The real exposure is **operational/security posture**, not structure: a fail-open default, a few unauthenticated owner-data surfaces, brittle file persistence, several data-loss bugs, and an over-broad admin token — almost all of which **fail silently** and are **not exercised by CI**.

---

## P0 — fix before any wider/public exposure

### P0-1 `[BOTH]` Fail-open default auth
`server_v2/players_api.py:69-92` — with no `AI_CADDIE_ADMIN_TOKEN` and no explicit `AI_CADDIE_SECURITY_PROFILE`, `require_admin_token` is a no-op **and** anonymous callers resolve to `OWNER_ID` → full owner read **+ write** + player-admin (create/rotate/delete tokens), on a `0.0.0.0`-bound service, with **no startup guard**. Security depends on one unchecked env var.
**Fix:** invert to fail-closed — require admin/player token unless an explicit `…SECURITY_PROFILE=open|dev`; add a startup assertion refusing a non-loopback bind when neither token nor open-profile is set.

### P0-2 `[BOTH]` Public `/readiness` + `/sync/status` leak owner data (and `/readiness` is a DoS amplifier)
`server_v2/main.py:392-394, 977-979` (ungated) → `readiness.py:935-1078`, `sync_status.py:79-178`. Anonymous callers get owner round counts, a real `roundId`, sync error codes, snapshotId, and the **course global-IDs the owner plays**; `/readiness` also **rebuilds the owner live-round package + history stats + trend report per anonymous hit** with no cache/rate-limit (CPU/IO flood on a 2 GB box).
**Fix:** gate both behind admin, or return a minimal `{status}` to anon and move the evidence/package build behind auth; cache the heavy probes.

### P0-3 `[BOTH]` Unguarded `json.loads` on non-atomically-written stores → one torn line = endpoint outage
The only atomicity primitive in the repo is one `fcntl.flock` (event-log append); **every** writer is non-atomic (no temp+`os.replace`). Highest-blast-radius unguarded readers (full inventory in Appendix A):
- `ai_caddie/rounds/players.py:37,102,131` — **player registry; corrupts → 500 on EVERY token-auth request AND owner `GET /history/overview` AND all `/admin/players`**.
- `ai_caddie/connectors/snapshot.py:1192` (`read_connector_status`) → **500 on the PUBLIC `/sync/status`**.
- `ai_caddie/core/data.py:74` (`clubs.json`), `data.py:385-499` (manual-round read-modify-write), `ai_caddie/history/history.py:55`.
- 9 JSONL line-readers (`mobile_live.py:2192,2336`, `mobile_reconciliation.py:23`, `decision.py:533,544`, `reports.py:1828`, `annotations.py:161`, `media.py:276`, `vision_context.py:225`, `weather_context.py:248`).
- Geometry request path: `geometry_evidence.py:119`, `hole_render.py:40`.
**Fix:** per-line `try/except JSONDecodeError: continue` for JSONL readers; guarded fallback for single-file readers; atomic write (temp+`os.replace`) for the single-file stores (registry, status, clubs, manual rounds, summary). Add a truncated-final-line regression test.

### P0-4 `[BOTH]` Web round idempotency collision → distinct rounds dropped
`web_v2/src/components/RecordRoundPage.tsx:128-143` sets `clientRoundId = web-${playerId}-${totalShots}-${scoredHoles}`; server uses it as the idempotency key (`server_v2/main.py:419-424`) and `round_ingest.py:459-462` returns the prior round **without writing** if the key exists. Two real rounds with the same player + shot count + scored-hole count silently merge.
**Fix:** UUID / content-hash / timestamped unique client id + a collision regression test.

### P0-5 `[opus✓codex]` iOS scoring data-loss via blanket state-restore
`mobile/ios/AICaddie/Views/CurrentHoleView.swift:255-257,864-886` — `applyRestoredState` blanket-overwrites `@State` (score/putts/penalty/club) from the log snapshot on **any** `liveRoundState` change. Score is persisted only on explicit Save (`:889-911`), but club-select emits immediately (`:459-469`). `[NEW]` (X3 + codex): the same clobber fires on **any incoming Watch event or remote sync pull** (`pullAndApplyRemoteEvents`/`acceptWatchEvent` → restore), so it is broader than club-select.
**Fix:** diff field-by-field and skip actively-edited fields; or fold current score/putts/penalty into every emitted event; or make per-hole live state a single source of truth in the model.

---

## P1 — should-fix

### P1-1 `[codex✓opus]` + `[NEW]` Over-broad admin token (root cause = unscoped write routes)
Codex: the global admin token is a portable client capability — URL `?admin=` (`adminTokenStore.ts:43`), baked Vite token (`:59`), localStorage (`:13-31`), and **pushed to the Apple Watch** (`WatchEventBridge.swift:333-351`). **`[NEW]` root cause (X1 N1):** the live-round **write** routes (events/ack/state/reconciliation, package GET — `main.py:818-877,775`) have **no per-player scoped path** (`is_player_scoped_route` covers only GET reads), so every recording client (web, iOS, watch) must hold the **global** admin token — which also grants `/admin/players` + Garmin sync.
**Fix:** mint a scoped per-round/per-player write capability (or extend `is_player_scoped_route` to the mobile event/state routes, ownership-checked) so recorders never need the global token; `[NEW N2]` keep a URL `?admin=` token in memory only (don't auto-persist to localStorage); `[NEW N3]` give the watch a scoped token, not the global one.

### P1-2 `[NEW codex]` iOS remote replay acks events that were never persisted
`AICaddieApp.swift:608-623` — `try? offlineStore.appendEvent(...)` swallows a write failure but still sets `appliedAny = true` and **acks the cursor**, permanently skipping those events on disk error.
**Fix:** only advance the ack cursor for events whose local append succeeded.

### P1-3 `[NEW X3]` iOS round id not unique → local round merge
`roundId = live-{globalId}` is reused across rounds on the same course; the event log is cleared only on explicit discard, so replaying a course merges two real rounds locally and posts to the same backend round (the iOS analog of P0-4).
**Fix:** unique round id per round (uuid/time-seeded).

### P1-4 `[codex✓opus]` Web geometry helpers omit the admin token
`web_v2/src/api.ts:347-364,382-393` (`fetchHoleGeometryEvidence`, `fetchHoleMap`) never send the admin token, but the backend admin-gates `/geometry/hole/...` whenever `source_ref` is present (`main.py:258`), which the app always passes → owner per-hole drilldown 401s. `api.test.ts:1655` locks the broken behavior. **Bounded (X1 N6): these are the only two offenders** — every other gated helper threads the token.
**Fix:** thread `adminToken` into both helpers + invert the tests.

### P1-5 `[codex✓opus]` In-app Garmin "Sync" refreshes neither club bag nor geometry
`ai_caddie/connectors/garmin_cn.py:146-155` runs summary+details only; the CLI `pipeline.py:63,99` also does `fetch_clubs` **and** `_ensure_geometry` (`[NEW X1 N4]`). The cron uses the CLI (so prod is fine) but the in-app button uses the connector → stale bag/geometry. (This already bit once — see `Dockerfile.sync` header.)
**Fix:** connector mirrors the CLI (clubs + geometry, best-effort/non-fatal) + connector tests mirroring `test_pipeline.py`.

### P1-6 `[BOTH]` Geometry subprocess: no timeout, held under the global lock
`geometry/batch_prodgeometry_course.py:36-47` `subprocess.run(..., cwd=ROOT)` has **no `timeout=`** for the network-bound `node` children; `geometry_sync.py:67` calls `process_hole` while holding `_LOCK` across the whole download+subprocess. One hung `node` wedges all geometry until restart.
**Fix:** add `timeout=` (handle `TimeoutExpired`); hold `_LOCK` only around the cache check/write, not the subprocess/network.

### P1-7 `[BOTH]` CI never builds the Docker images or exercises the runtime footguns
No workflow runs `docker build`; `Dockerfile.sync` is wholly ungated; the geometry node-subprocess chain, the Playwright auth-refresh, and `ROOT` resolution are never executed (tests mock above them / `skipTest`). This is the exact class behind the documented 10-day sync-image drift.
**Fix:** a CI (or scheduled) job that builds both images + runs `/api/v2/health` + a geometry-ensure smoke; a test asserting `(ROOT/"pyproject.toml").exists()`; `uv sync --frozen` in CI for lockfile parity.

### P1-8 `[opus]` No request body-size cap
No transport/body limit in middleware or uvicorn; `LiveRoundEventBatchRequest.events` has `min_length` but no `max_length` (`models.py:953-956`). (Nuance/codex: protected POSTs *are* gated pre-body today, so this is hardening, not an open anon-parse hole.)
**Fix:** ASGI body-size guard + `max_length` on event batches.

### P1-9 `[opus✓codex]` `sanitize_safe_meta` redacts the key, keeps the value
`ai_caddie/connectors/garmin_cn.py:36-43` renames a secret key to `"redacted"` but preserves the value. Audience is admin (sync), so impact is limited, but it's the opposite of intent.
**Fix:** replace the **value**, not the key name.

### P1-10 `[opus✓codex]` Provider correctness
`llm/llm_providers.py:390-397` Gemini OAuth token cached forever → 401 after ~1 h until restart (re-check expiry); `:651-660` `AnthropicProvider.chat` double-iterates `messages`, dropping the system prompt if a generator is passed (`list(messages)` first).

### P1-11 `[opus]` iOS observability blind spot
`AICaddieApp.swift` `LiveRoundAppModel` swallows all sync/save/**decode** errors into a status string with no `os.Logger` (the service layer logs; the orchestration doesn't) → on-course failures + any contract drift are undiagnosable. Watch target has no logging at all.
**Fix:** log every `catch` (esp. around `decoder.decode`) via `AICaddieLog`; add a watch logger.

### P1-12 `[NEW codex+X3]` Watch↔phone state overwrite race
Phone snapshots overwrite the watch's `currentState`/persisted state with no dirty-merge while the watch keeps unsaved score/club edits → lost watch edits.
**Fix:** dirty-field merge on snapshot apply.

---

## P2 — debt / polish
- **God-units (all 3 layers)** `[BOTH]` — backend `history_stats.py` 3846 / `decision.py` 3687 / `mobile_live.py` 2557 / `reports.py` 2624; web `App.tsx`/`CaddiePage`/`CorrectionsPage`; iOS `CurrentHoleView.swift` 1002. The reorg fixed package boundaries, not intra-unit decomposition. Extract audit/event-log/offline-seed (backend), view-models + panels (web/iOS).
- **ROOT depth-coupling** `[BOTH]` — `Path(__file__).resolve().parents[N]` replicated in 11 files (broke twice); tests `skipTest` instead of failing → false CI confidence. Centralize to a marker-anchored `repo_root()`.
- `[NEW X2]` **tools/ dev scripts ROOT broken after reorg** — `tools/{courseview,prototype,reports}/*` use `ROOT = Path(__file__).parent` (was repo-root at top level; now points at `tools/<sub>/`). Host-only (not shipped), no prod impact, but broken dev tooling; the reorg codemods didn't rewrite these.
- `[NEW codex]` **pending media JSONL** has the truncation pattern the iOS event log already fixed (`OfflineStore.swift:457-469`).
- `[opus✓codex]` backup omits the live `data/decisions` ledger (`ops/export_snapshot.py:11-24`) → data loss on restore.
- `[opus✓codex]` `analysis.py:441` `tees[0]["position"]` KeyError; `course_reference.py:166` `CoursePar(**payload)` unguarded; `round_shot_map.py:43` back-nine geometry never resolves for single-GID.
- `[opus]` **contract Swift↔schema validated only Python-side** (schema already stale: `nine` missing); add a Swift↔schema round-trip test.
- `[opus]` brittle meta-tests (grep iOS Swift signatures; pin ~80 doc substrings); `[codex]` legacy `tools/legacy/ai_caddie_web.py` 143 KB kept for one test constant; empty `ai_caddie/scrapers/`; web fetch-layer hardening (error bodies, regex-401, abort/timeout, `refreshRoundsState` seq guard); `ScoreStrip` mixed-language `aria-label`.
- `[codex-only — verify]` non-owner mobile package: course options are player-scoped but the package builder loads owner/default history (`main.py:775-792`); reconcile against the verified "no cross-player read" result below.
- `[codex-only]` player tokens appear in `?key=`/`/p/{token}` URLs; geometry shot/route evidence lacks the mesh-ref fallback that hole-map has.

---

## Verified SOUND (no action — checked and cleared)
- **No cross-player IDOR** — non-owner history/club-bag/reports return empty/own-scoped; `data_source.load_history_data_for_mode` refuses the owner snapshot/fixture for non-owners.
- **Auth matrix has no actual unauthenticated-write or cross-player-read hole** (Appendix B) — the only real public-data gap is `/sync/status` (P0-2); the rest is *fragility* (11 MW-only routes, query-param gate, exact-string entries saved by `redirect_slashes`).
- Timing-safe admin compare (`hmac.compare_digest`); player tokens stored only as SHA-256; media upload pre-decode size cap + filename flatten + `..` escape blocked; geometry `source_ref` gate **not** bypassable via duplicate query params; iOS admin token at-rest in **Keychain**; `Referrer-Policy: no-referrer` set.
- **All production/request-path roots correct + Docker-safe** (Appendix C) — every anchor flows from `core/data.py:13` `parents[2]` = `/app`.

---

## Appendix A — json.loads inventory (condensed)
**Unguarded + non-atomic + live-endpoint (fix first):** players.py:37/102/131 (auth path); snapshot.py:1192 (public /sync/status); data.py:74 (clubs.json); data.py:385-499 (manual rounds); history.py:55; geometry_evidence.py:119; hole_render.py:40; JSONL: mobile_live.py:2192/2336, mobile_reconciliation.py:23, decision.py:533/544, reports.py:1828, annotations.py:161, media.py:276, vision_context.py:225, weather_context.py:248.
**Already guarded (safe):** data.py:93/185/247/444/513, round_ingest.py:83/397, history.py:324/490/499, shot_projection.py:90, course_reference.py:133/163, course_prep.py:243, mobile_live.py:2225, snapshot.py:184…929, readiness.py:125…590.

## Appendix B — auth gating (gaps only)
Real gap: `GET /sync/status` public→owner data. Defense-in-depth gap: `POST /players/{id}/rounds` (write) not in the middleware matrix (handler-dep only). Fragility: 11 owner-data routes MW-only (caddie/context, annotations/target/*, media/target/*+findings, mobile/rounds/*/package, mobile/courses/*/package, events/replay, reconciliation); `/geometry/hole` gate keys on the `source_ref` query param; exact-string entries rely on `redirect_slashes`. Over-gated (usability): `GET /courses/search` admin-only.

## Appendix C — path roots
All production anchors (`core/data.py:13` + 10 depth-coupled `parents[2]` siblings + `ops/*` `parents[1]`) resolve correctly to repo root / `/app`. Only `tools/{courseview,prototype,reports}/*` (`Path(__file__).parent`) are wrong post-reorg (host-only).
