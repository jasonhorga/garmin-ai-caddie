# Phase 2 — per-user evidence isolation (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans, task-by-task. Steps are TDD.

**Goal:** Make every EVIDENCE read player-aware so a non-owner family member sees NONE of the owner's evidence (annotations, weather snapshots, reports, decision audits/ledger, vision findings, mobile event log), while the owner's behaviour is **byte-for-byte unchanged**. All evidence is owner-generated (members write none), so "non-owner → empty scope" is the complete fix. Also fix two latent evidence bugs that affect even the owner. Implements `docs/superpowers/specs/2026-06-28-phase2-evidence-isolation-design.md`. Does NOT build physical per-user evidence dirs and does NOT reopen the 4 admin-only aggregator routes (both deferred per the spec).

**Architecture:** A single leaf-module helper resolves a caller's evidence scope:
`evidence_root(player_id, *, root=None) -> Path | None`  (owner → `Path(root or ".")`; non-owner → `None`).
Every evidence READ loader gains keyword `player_id: str = OWNER_ID`, computes `er = evidence_root(player_id, root=root)`, short-circuits `if er is None: return []/None` for a non-owner, else reads from `er` exactly as today. Default `OWNER_ID` keeps every existing call site byte-for-byte until a caller threads a member id. Member-reachable engine functions (`resolve_history_ref`, `build_history_stats`, `_round_ids_with_reports`, `build_hole_report_facts`) + their player-scoped handlers thread the real `current_player_id` down. Writes untouched (admin-only → owner). Admin-only aggregator call sites stay on the loader default (= OWNER) — not member-reachable this phase; threading them is the deferred aggregator-reopening phase. Generalizes the existing `_event_cursor(round_id, *, player_id=OWNER_ID)` precedent.

**Tech stack:** Python 3.12, FastAPI, `uv`, stdlib `unittest` (CI runs `unittest discover` — never rely on pytest). Helper in `ai_caddie/core/data.py` (leaf — imports nothing from `ai_caddie`; verified).

**Per-task rule:** TDD (failing test → see it fail → minimal impl → see it pass → commit). Absolute paths. Commit trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. After every task the full suite stays green (`AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests`); loader tasks 2–7 are backward-compatible (default OWNER_ID). Do NOT touch geometry (`geometry_coverage_for_hole`, `output/prodgeometry*`) or sync snapshots (`data/sync`, `data/snapshots`). Owner byte-for-byte in every task except the two latent-bug tasks (8, 9).

**Verified facts:** `ai_caddie/core/data.py` is a leaf and has no `OWNER_ID` yet (3 `OWNER_ID="me"` defs exist in players.py/history.py/round_ingest.py). Every loader resolves via a `*_file(root)` of shape `Path(root or ".")/"data"/<store>/<file>` → owner `evidence_root` result is idempotent. `cached_build_history_stats` carries `player_id` and the cache key includes it, but does NOT pass it to `_build_history_stats` (stats_cache.py:217). Player-scoped routes already inject `player_id=Depends(current_player_id)` (main.py:468,498,506,515,537,637,955); admin token → "me", capability token → member id. `load_history_data_for_mode` local_or_fixture: owner with no rounds → fixture (900001/2/3), non-owner with no rounds → empty — the combo the isolation suite uses.

---

## Task 1 — `evidence_root` helper + `OWNER_ID` in `ai_caddie/core/data.py`

**Create** `tests/test_evidence_root.py`:
```python
from __future__ import annotations
import unittest
from pathlib import Path
from ai_caddie.core.data import OWNER_ID, evidence_root


class EvidenceRootTests(unittest.TestCase):
    def test_owner_resolves_to_flat_root_default(self) -> None:
        self.assertEqual(evidence_root(OWNER_ID), Path("."))

    def test_owner_passes_through_explicit_root(self) -> None:
        self.assertEqual(evidence_root(OWNER_ID, root="/tmp/x"), Path("/tmp/x"))
        self.assertEqual(evidence_root(OWNER_ID, root=Path("/tmp/x")), Path("/tmp/x"))
        self.assertEqual(evidence_root(OWNER_ID, root=""), Path("."))

    def test_non_owner_is_none_regardless_of_root(self) -> None:
        self.assertIsNone(evidence_root("p_alice"))
        self.assertIsNone(evidence_root("p_alice", root="/tmp/x"))

    def test_owner_root_matches_loader_file_helpers_byte_for_byte(self) -> None:
        from ai_caddie.reports.annotations import annotation_file
        self.assertEqual(annotation_file(evidence_root(OWNER_ID)), annotation_file(None))
        self.assertEqual(annotation_file(evidence_root(OWNER_ID, root="/d")), annotation_file("/d"))
```
Run to fail (ImportError). **Modify** `ai_caddie/core/data.py` — after the constants block (~line 22), before `class HoleRef:`:
```python
OWNER_ID = "me"


def evidence_root(player_id: str, *, root: Path | str | None = None) -> Path | None:
    """Owner -> flat shared root (Path(root or ".") — what every *_file(root) helper computes);
    non-owner -> None (signal for a read loader to short-circuit to empty). root ignored for non-owner."""
    if player_id != OWNER_ID:
        return None
    return Path(root or ".")
```
Run to pass. **Commit:** `feat(evidence): add evidence_root scope helper (owner -> flat root, non-owner -> empty)`.

---

## Tasks 2–7 — make each evidence READ loader player-aware (default OWNER_ID)

Pattern for every loader: add keyword `player_id: str = OWNER_ID`; at the top
`evidence = evidence_root(player_id, root=root); if evidence is None: return []/None`; else use `<file>(evidence)` exactly as today. `latest_*`/`*_for_target`/`*_for_time` thread `player_id` into their internal `list_*`/`latest_*` calls. New test file `tests/test_evidence_player_scope.py` (one class per store): seed via the store's `store_*`/`add_*` under a TemporaryDirectory root, assert `list_*(root=tmp, player_id="me")` non-empty and `... player_id="p_x"` empty, and that the default (no player_id) equals the `"me"` result.

- **Task 2 — annotations** `ai_caddie/reports/annotations.py`: import `from ai_caddie.core.data import OWNER_ID, evidence_root`; update `list_annotations` (153), `annotations_for_target` (171). Commit `feat(evidence): make annotation reads player-aware (default owner)`.
- **Task 3 — weather** `ai_caddie/llm/weather_context.py`: `list_weather_snapshots` (241), `latest_weather_snapshot` (261), `weather_snapshot_for_time` (278, thread into its internal latest_/list_ calls at 288/291/296). Commit `feat(evidence): make weather-snapshot reads player-aware (default owner)`.
- **Task 4 — reports** `ai_caddie/reports/reports.py`: import from core.data (leaf, no cycle); `list_report_records` (1821), `latest_report_record` (1835). Commit `feat(evidence): make report-record reads player-aware (default owner)`.
- **Task 5 — decision audits/ledger** `ai_caddie/caddie/decision.py`: `list_decision_audits` (526), `list_decision_records` (540), `latest_decision_record` (554), `latest_decision_audit` (562). Commit `feat(evidence): make decision audit/ledger reads player-aware (default owner)`.
- **Task 6 — vision** `ai_caddie/llm/vision_context.py`: `list_vision_findings` (218), `list_findings_for_target` (232). Leave the confirm/rewrite internal read (259) on default (admin write-adjacent). Commit `feat(evidence): make vision-findings reads player-aware (default owner)`.
- **Task 7 — mobile event log** `ai_caddie/caddie/mobile_live.py` (`OWNER_ID` already imported; add `evidence_root`): short-circuit in `_event_log_rows` (2191, the single root reader) covers downstream; thread `player_id` through `_latest_event_sequence` (2215), `_pending_event_count` (2222), `replay_event_log` (2501→2518,2532), `ack_event_cursor` (2547→2557,2573). Do NOT touch `_event_cursor` (already correct). Commit `feat(evidence): make mobile event-log reads player-aware (default owner)`.

(Full per-store test bodies: see the spec + the worker writes them following the pattern above; each asserts owner-nonempty / non-owner-empty / default==owner.)

---

## Task 8 — Latent bug #1: drilldown attaches evidence to missing refs + whole-store weather dump

`resolve_history_ref` runs `_attach_evidence` even on a not-found ref (no `found` guard), and `_matching_weather_snapshots` leaves `round_id=None` on a miss → returns the ENTIRE weather store. `_base_detail` (328) already seeds evidence keys to `[]`, so gating is safe; corrects owner behaviour too.

**Test** (`tests/test_history_drilldown.py`, append `DrilldownMissingRefEvidenceGuardTests`): seed annotation+report+decision-audit+weather for 900001 under tmp; assert `resolve_history_ref(fixture, "999999", ...roots=tmp)` → `found False`, `weatherSnapshots/reports/decisionAudits/annotations == []`; assert `_matching_weather_snapshots({"refType":"round","round":{}}, tmp) == []`; assert a found 900001 still attaches its 1 weather snapshot.

**Modify** `ai_caddie/history/history_drilldown.py`:
- `_attach_evidence` (410): add at top `if not detail.get("found"): return detail`.
- `_matching_weather_snapshots` (500): after the `round_id`/`hole_number` computation (after ~511), add `if round_id is None: return []`.
Commit `fix(drilldown): no evidence on missing refs; no whole-store weather dump`.

---

## Task 9 — Latent bug #2: `_data_quality` annotation counts/ids not joined to caller rounds

`_data_quality` (3639) counts ALL annotations regardless of the caller's rounds. Join to the caller's round set (reuse `_round_id` (25) + `_ref_round_id` (988)).

**Test** (`tests/test_history_data_quality.py`, append `DataQualityAnnotationJoinTests`): an annotation for a foreign round (555555) → `dataQuality.annotations.total==0`, `refs==[]`; an annotation for a real fixture round (900001) → `total==1`, id in `refs`.

**Modify** `ai_caddie/history/history_stats.py` `_data_quality`: build `caller_round_ids` from `data.raw_rounds`/`data.rounds` (+ each row's `ids`); `scoped_annotations = [r for r in (annotations or []) if _ref_round_id(r.get("targetId")) in caller_round_ids]`; derive `annotation_count`/`corrections`/the two `refs`/`readyRefs` comprehensions (3676-3677) from `scoped_annotations`. Commit `fix(stats): join dataQuality annotation counts/ids to the caller's rounds`.

---

## Tasks 10–13 — thread the real `player_id` through the member-reachable engine functions

Each: add `player_id: str = OWNER_ID` to the engine fn + pass it to the now-player-aware loaders; the player-scoped handler (already has `current_player_id`) passes it down. Unit-test owner-nonempty / member-empty on the engine fn.

- **Task 10 — drilldown:** `resolve_history_ref` (122; extend its `from ai_caddie.history.history import HistoryData` to include `OWNER_ID`) → thread `player_id` into every `_attach_evidence(...)` call (137,143,148,153,160,162); `_attach_evidence` (410) threads into `_attach_annotations`/`_matching_reports`/`_matching_weather_snapshots`/`_matching_decision_audits` (each gains `*, player_id` + passes `root=..., player_id=...` to its loader). Handler `server_v2/history_drilldown.py:18` passes `player_id=player_id`. Commit `feat(evidence): scope drilldown evidence by player_id`.
- **Task 11 — stats (+ all four roots):** `build_history_stats` (3808) gains `player_id` (extend `from ai_caddie.history.history import ...` with `OWNER_ID`) + threads into all four loaders (3818-3821). `cached_build_history_stats` (stats_cache.py:217) passes `player_id=player_id` to `_build_history_stats`. `server_v2/history_stats.py` adds `ANNOTATION_ROOT/WEATHER_ROOT/REPORTS_ROOT=Path(".")` beside `DECISION_AUDIT_ROOT` and passes all four + `player_id` in `load_history_stats_response` (22) and `load_mobile_stats_response` (52). `server_v2/prep_tips.py` adds the same three constants + passes all four (48) so it shares the same cache key. (Owner byte-for-byte: all roots = `Path(".")`; one cold recompute on deploy, identical response.) Commit `feat(evidence): scope all four stats evidence roots by player_id`.
- **Task 12 — `/history/rounds?hasReport=`:** `server_v2/history_rounds.py` adds `from pathlib import Path` + `REPORTS_ROOT=Path(".")`; `_round_ids_with_reports(player_id=OWNER_ID)` → `list_report_records(root=REPORTS_ROOT, player_id=player_id)`; `load_history_rounds_response` passes `player_id`. Commit `feat(evidence): scope /history/rounds hasReport filter by player_id`.
- **Task 13 — hole-report vision:** `reports.py` `_confirmed_vision_findings_for_refs` (1061) + `build_hole_report_facts` (1114) gain `player_id` → `list_findings_for_target(..., player_id=player_id)`. `server_v2/reports.py` `load_hole_report_response` (179) passes `player_id`; the admin `generate_hole_report_response` keeps default; the already-owner-guarded report loaders (143,158,182,212,229,246) stay on default. Commit `feat(evidence): scope hole-report vision findings by player_id`.

---

## Task 14 — Route-level isolation suite

**Create** `tests/test_evidence_isolation.py`: patch `players.ROOT`, `history.ROOT`, every handler ROOT constant (`history_drilldown`/`history_stats`/`prep_tips` ANNOTATION/WEATHER/REPORTS/DECISION_AUDIT_ROOT; `history_rounds.REPORTS_ROOT`; `reports.REPORT_ROOT`/`MEDIA_ROOT`) + `stats_cache._PLAYERS_DIR` to a tmp tree; patch `data_source.load_latest_snapshot_history` → None; patch `course_prep.available_prep_holes`/`prep_nine` → []; env `ADMIN_ENV={"AI_CADDIE_ADMIN_TOKEN":"admin-secret","AI_CADDIE_DATA_MODE":"local_or_fixture"}`; `get_settings.cache_clear()`+`stats_cache.clear()`+`prep_cache.clear()` in setUp+addCleanup. Create member "Alice"; seed owner evidence (annotation/weather/report/decision-audit on 900001 with unique SENTINEL strings). Assert: owner (admin header) sees the sentinels + non-empty evidence on `/history/drilldown/900001`, `/history/stats`, `/history/stats/mobile`, `/history/rounds?hasReport=true`, `/reports`; member (capability token) gets 200 with NO sentinel anywhere and empty evidence / `dataQuality.annotations.total==0` / `rounds.total==0` on each of those + `/history/summary` + `/courses/31795/prep-tips`; and `/history/drilldown/999999` (guessed missing ref) returns `found False` + empty weather for BOTH (latent bug #1). Commit `test(evidence): route-level per-user evidence isolation suite`.

(The worker VERIFIES the exact `dataQuality` response shape + `build_mobile_stats` carry-through and adjusts the `_annotations_dq` lookups; debug per superpowers:systematic-debugging if a ROOT patch or the owner fixture fallback misbehaves.)

---

## Task 15 — Green gate, self-review, PR

1. Full suite `AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests` → 0 fail/err (see the summary line; superpowers:verification-before-completion).
2. `uv run python -m py_compile $(git diff --name-only origin/integration/v2...HEAD -- '*.py')`; `uv sync --frozen`.
3. Self-review: all six stores' READ loaders player-aware; [M] reads thread the real `current_player_id`; two latent bugs fixed; geometry/sync untouched; aggregators NOT reopened; no physical dirs; every loader param is keyword `player_id: str = OWNER_ID`; cache key still carries `player_id`; owner byte-for-byte except the two latent fixes; admin-only [A] sites intentionally left on default (member-unreachable — documented).
4. Push; `gh pr create --base integration/v2 --head superpowers/phase2-data-partition` (NO `--delete-branch`). Body: the seam, the six stores, the two latent fixes, the explicit deferrals (aggregators + physical dirs).
5. Independent **Codex whole-branch review + final Claude review**; address via verify-then-fix. **Merge only on green CI + reviews clear**, to integration/v2, no branch deletion.

### Intentional deviations (reviewer visibility)
- [M] cross-module threading grouped by engine function (Tasks 10–13), not repeated per store — edits each shared fn once, keeps the suite green after every task.
- `history_stats`/`prep_tips`/`history_rounds` gain patchable root constants (all `Path(".")` = prior default → owner byte-for-byte) so owner evidence is seedable + stats/prep-tips keep sharing one cache entry.
- Admin-only [A] call sites left on loader default (= `OWNER_ID`, byte-for-byte; member-unreachable) — threading them is the deferred aggregator-reopening phase.
