# Phase 2 data-isolation deferrals (surfaced by the Phase 1c cross-review)

**Context.** Phase 1c set out to "close the history IDOR" by threading the resolved
`player_id` into `load_history_data_for_mode()`. Five iterations of independent cross-model
review (Codex ×4 + a Claude whole-branch review) converged on a deeper structural fact:

> Member data isolation is **not** achievable by threading `player_id` into the rounds/shots
> loader alone. The engine reads many **shared, owner-only, NOT-per-user-partitioned** stores
> by `round_id` / `source_ref`: the mobile event log, weather snapshots, the annotation
> store, the report store, and decision-audits. Threading `player_id` isolates only the
> `HistoryData` (rounds/shots) half; the **evidence layer** is still shared.

Real per-user isolation therefore requires **partitioning all of those stores per user**
(or scoping every evidence read by player ownership). That is **Phase 2** work.

## What Phase 1c DID close (shipped)
- Identity hardening: `UNIQUE(legacy_player_map.user_id)` + migration `0002` (+ dup
  preflight); `_player_for_session_token` rejects non-`user` scope; `/auth/refresh` preserves
  `sess.scope`.
- Clear member→owner leaks closed by owner-gating: `/api/v2/sync/status` and
  `/api/v2/readiness` (both now require `player_id == OWNER_ID`; members + anon get a liveness
  stub).
- The four mobile/caddie **aggregator** reads (mobile round package, mobile course package,
  reconciliation-GET, caddie-context) are kept **admin-only** (removed from
  `is_player_scoped_route`) — they aggregate the unpartitioned stores by `round_id`/
  `source_ref` and cannot be member-isolated until those stores are partitioned.

## What is DEFERRED to Phase 2 (member-reachable evidence-layer leak)
The genuinely player-keyed reads that remain member-accessible
(`/api/v2/history/*`, `/api/v2/reports[/*]`, `/api/v2/courses/*/prep` + `/prep-tips`,
`/api/v2/mobile/courses/options`) isolate the **rounds/shots** correctly but still read the
shared **evidence layer**. Concretely (file:line from the review):

- **History drilldown** — `ai_caddie/history/history_drilldown.py`: `_attach_evidence`
  (≈395–421) attaches annotations / reports / weather / decision-audits even for a ref not in
  the caller's scope; `_matching_weather_snapshots` (≈500–531) appends **every** owner weather
  snapshot when the (guessed) ref has no `round_id`. Member-reachable via `/api/v2/history/drilldown/*`.
- **History stats / summary** — `ai_caddie/history/history_stats.py`: `build_history_stats`
  (≈3818–3824) reads global annotations / weather / reports / decision-audits; `dataQuality`
  (≈3651–3678) exposes global annotation counts/IDs; corrections applied by `targetId`
  (≈128–163, ≈177–200). Flows into `/api/v2/history/stats`, `/summary`, and via
  `server_v2/reports.py` + `server_v2/prep_tips.py`. `history/rounds?hasReport=` also reads the
  shared report store (`server_v2/history_rounds.py` ≈107–122).
- The four **aggregator** routes above (reopen to members once the stores are partitioned).
- **Geometry** `source_ref` reads (`server_v2/geometry.py` ≈93/117) — currently admin-only.

**Severity / threat model.** The product is **family** multi-user (household members), and the
leaked data is golf evidence metadata (weather snapshots, annotation counts, report
existence) — low-threat in that context, and largely **pre-existing** (`history/*` was
player-scoped before Phase 1c). The owner explicitly chose to ship Phase 1c now and treat the
evidence-layer isolation as a Phase 2 item.

## Phase 2 task (data isolation, proper)
Partition per user — or ownership-scope every read of — the annotation store, weather
snapshots, the report store, decision-audits, and the mobile event log. Then re-enable member
access to the four aggregator routes and make the evidence attached by history stats /
drilldown / reports / prep-tips strictly the caller's own. Add member-vs-owner isolation tests
that seed owner evidence and assert a member sees none of it.
