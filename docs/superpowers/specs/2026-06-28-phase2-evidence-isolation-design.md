# Phase 2 — per-user evidence isolation (design)

**Status:** design, pending approval. Branch `superpowers/phase2-data-partition` off integration/v2 @ 5e17093 (post Phase 1c). Part of the [multi-user / family redesign](2026-06-26-phase0-findings.md) — Phase 1 (identity) is complete; this is the first slice of Phase 2 (data isolation).

## Goal

Close the member→owner **evidence-layer** leak that Phase 1c surfaced and documented
(`docs/superpowers/notes/2026-06-27-phase2-data-isolation-deferrals.md`). Phase 1c isolated
rounds/shots (`HistoryData`) per user, but the **evidence** stores — annotations, weather
snapshots, reports, decision-audits, the mobile event log, vision findings — are shared,
owner-only, and read by member-reachable routes, so a family member can read the owner's
evidence. This phase makes **every evidence read player-aware**: the owner reads the current
shared store; a non-owner reads an empty scope.

## Key facts that shape the design (from the architecture map)

- **All evidence is owner-generated.** Every write to every evidence store is admin-only
  (`is_player_scoped_route` rejects non-GET; the write routes are in the admin allowlist).
  Members write only their own rounds/shots, which already go to `data/players/<id>/`. So a
  non-owner's correct evidence is **empty**, and "non-owner → empty reads" is a *complete*
  fix for the current product — no physical per-user evidence directory is needed yet.
- **The owner ("me") is not a `data/players/me/` tree.** Owner rounds/shots = flat
  `data/scorecards`+`data/shots` (Garmin) merged with `data/players/me/` (manual), plus a
  snapshot/fixture fallback. **All evidence lives only at the flat `./data/<store>/`.** So the
  owner's evidence root is the current flat root; a non-owner's evidence root is a per-player
  location that is empty today (and becomes their real evidence dir if/when members ever
  generate evidence).
- **A precedent already exists:** `_event_cursor(round_id, *, player_id=OWNER_ID)` already
  short-circuits `if player_id != OWNER_ID: return empty` (added in Phase 1c). This phase
  generalizes that pattern across all evidence loaders.

## Architecture

A single helper resolves a caller's evidence scope:

```
evidence_root(player_id) -> Path        # owner  -> the flat shared root (current behaviour)
                                        # non-owner -> a per-player path with no evidence (empty)
```

Every evidence read is parameterized by the caller's `player_id` (threaded from the
player-scoped route handler, through the engine, to the loader). Concretely, the player-scoped
handlers compute the per-store evidence roots from `player_id` and pass them down; the loaders
read from the resolved root (owner = `./data/<store>/…` as today; non-owner = empty). Owner
behaviour is **byte-for-byte unchanged**. Writes are untouched (admin-only → always the owner
scope).

The exact loader/call-site set to thread is enumerated in the architecture map; it covers the
read functions for annotations, weather snapshots, reports, decision-audits, vision findings,
and the mobile event log, and every member-reachable call site that reaches them
(`history_drilldown`, `build_history_stats`/`build_mobile_stats`, `history_rounds`'
`hasReport`, the reports build path, prep-tips). The admin-only aggregator call sites
(`caddie_context`, mobile package, reconciliation) are threaded for uniformity but keep
owner behaviour (they remain admin-only this phase — see Out of scope).

## The two latent bugs to fix alongside (affect even the owner)

1. **Drilldown attaches evidence to missing refs.** `resolve_history_ref` runs
   `_attach_evidence` even on a not-found ref (no `found` guard, unlike
   `history_round_detail`), and `_matching_weather_snapshots` leaves `round_id=None` on a miss,
   so the round filter is skipped and it returns the **entire** weather store. Fix: gate
   evidence attachment on `detail["found"]` (mirror `history_round_detail`) AND make
   `_matching_weather_snapshots` return nothing when there is no concrete `round_id`. (The
   player-scoping already closes the member leak; this hardens the miss path and is correct
   for the owner too.)
2. **`_data_quality` reports un-joined annotation counts/IDs** that are not joined to the
   caller's round set. Player-scoping the annotation root fixes the member leak; additionally
   ensure the counts/IDs reflect only the caller's rounds.

## Components / files (high level — the plan enumerates exact edits)

- New: `evidence_root(player_id)` helper (in a shared module, e.g. `ai_caddie/core/data.py`
  or `ai_caddie/history/history.py` next to `_player_data_dir`).
- Read loaders gain player-awareness (via a scoped root or a `player_id` param):
  `ai_caddie/reports/annotations.py`, `ai_caddie/llm/weather_context.py`,
  `ai_caddie/reports/reports.py`, `ai_caddie/caddie/decision.py`,
  `ai_caddie/llm/vision_context.py`, `ai_caddie/caddie/mobile_live.py` (event readers).
- Engine functions thread the scope: `ai_caddie/history/history_drilldown.py`,
  `ai_caddie/history/history_stats.py` (+ `mobile_stats.py`), the reports build,
  `server_v2/prep_tips.py`, `server_v2/history_rounds.py`.
- Server handlers compute `evidence_root(player_id)` from `current_player_id` and pass it down:
  `server_v2/history_stats.py`, `server_v2/history_drilldown.py`, `server_v2/reports.py`,
  `server_v2/prep_tips.py`, `server_v2/history_rounds.py` (and the admin-only
  `server_v2/caddie.py`, `server_v2/mobile.py` for uniformity).

## Do NOT touch

- **Geometry** (`output/prodgeometry*`, `geometry_coverage_for_hole`) — public course data
  keyed by globalId/hole, intentionally shared.
- **Sync snapshots** (`data/sync`, `data/snapshots`) — owner recovery data, already
  owner-gated behind admin-only sync routes (`data_source.py:29-30`).

## Out of scope (deferred)

- **Reopening the 4 aggregator routes** (mobile round/course package, reconciliation-GET,
  caddie-context) to members — coupled to member mobile-client onboarding; once evidence reads
  are player-aware this becomes a small `is_player_scoped_route` flip + tests, done in that
  phase. They stay admin-only here.
- **Physical per-user evidence directories** — premature (members generate no evidence). The
  `evidence_root(player_id)` seam is where that lands later: the non-owner branch resolves to
  a real `data/players/<id>/…` evidence subtree instead of empty, and the (future) member
  write paths write there.

## Testing

A dedicated isolation suite that **seeds owner evidence** (annotations, a weather snapshot, a
report, a decision-audit for a fixture round) and asserts:
- a family-member capability token on every member-reachable read
  (`/history/drilldown/{ref}`, `/history/stats`, `/history/stats/mobile`, `/history/summary`,
  `/history/rounds?hasReport=`, `/reports`, `/courses/*/prep-tips`) sees **none** of it
  (no owner weather, annotation counts, report rows, audit rows) — including the drilldown
  guessed-ref path that was the worst leak;
- the **owner** (admin) still sees all of it (proves scoping, not a dead read);
- unit tests for `evidence_root` (owner → shared root; non-owner → empty) and for the two
  latent-bug fixes (missing-ref → no evidence; no-round_id → no weather dump).
Full backend suite stays green (`AI_CADDIE_DATA_MODE=fixture unittest discover`); CI green.

## Review

Subagent-driven build (per-task spec + quality review) + the independent **Codex whole-branch
review + a final Claude review** before merge — the same cross-model pass that caught the real
defects throughout Phase 1c. Merge only on green CI + reviews clear, to integration/v2 (no
`--delete-branch`).
