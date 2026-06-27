# Phase 0 Findings — CourseView field dictionary + endpoint auth matrix

> **Status:** Done (spike results). Feeds the schema ([design v2](2026-06-26-multi-user-redesign-design.md)) and the Phase-1/2 plans.
> **Date:** 2026-06-26
> Part A run against **real CourseView data** on the homeserver (gids 31791/39315/39247 + 24 decoded courses). Part B's highest-risk claims were **verified against code** (not taken on faith).

---

## Part A — CourseView "彻底探究" (real-data protobuf walk + mesh-`y` validation)

### A1. The anonymous release carries MORE than `inspect_release` parses

A generic field-walk of the release protobuf for 3 real courses surfaced **unparsed but valuable** fields (all **anonymous** — no geometry decode/credential needed):

A self-contained protobuf walk (decoding `fixed32` floats) over 12 real courses **nailed** these (was "likely" in the first pass):

| Field | Observed | **Confirmed meaning** | Evidence |
|---|---|---|---|
| **tee `.3`** (fixed32 float) | 73.83, 71.9, 74.23, 70.56… | ✅ **course rating** (per tee) | values sit in the 67–77 band; **9-hole loops (`The Players Club ~ B`, `Sand River ~ B`) read 37.31 / 35.63 ≈ half of 72** — decisive |
| **tee `.2`** (varint) | 109–121 | ✅ **slope rating** (per tee) | exactly the slope band (standard 113) |
| **tee `.1` / `.4` / `.5`** | "Black"/"Gold", "MEN", 1/2 | ✅ tee name / gender / ordering | (already parsed) |
| **hole `.2`** (nested) | `{f1=par, f2="MEN"}` | ✅ **par, gender-tagged** | hole-1 `{4, "MEN"}` |
| **hole `.3`** (nested) | `{f1=index, f2="MEN", f3="NotSpecified"}` | ✅ **stroke index / handicap, gender-tagged** | par/handicap are **per gender** — today we read only the first (MEN) |
| **f5** (×1–2/course) | `{f1="OUT"/"IN", f2=36/35, f3="MEN"}` | ✅ **front/back-nine definitions** (label + nine-par + gender) | OUT=front, IN=back; a 9-hole course has only one |
| **hole `.7`** | `birdseye…` URL | ✅ anonymous per-hole overhead thumbnail | render in prep with no geometry decode |
| **f12** | =1 on ~half (Mission Hills/Sand River/Dragon Valley yes; Jade Island/Clearwater no) | ⚠️ **boolean flag, meaning still undetermined** | (possibly multi-loop/facility marker — unconfirmed) |
| **f10 `unknown_10`** | 22 / 28 / 29 | ⚠️ **small course int, NOT geographic** | **disproved** the region-code guess: Shenzhen's Mission Hills=28 but Sand River=29 — still genuinely unknown |

**Schema impact (now firm):** the **anonymous catalog carries full tee ratings** — `tee_boxes` += `rating` (float) + `slope` (int); `course_holes` par/handicap are **per gender** (model with a gender discriminator / a `course_hole_pars` child); `f5` yields per-nine par. **None of this needs the credentialed geometry path.** Two fields (`f12`, `unknown_10`) remain genuinely undetermined and are flagged as such — not guessed.

### A2. Mesh-`y` elevation is real and usable (validates decision ③)

`elevation.py` reads mesh `y` as terrain elevation. On real decoded holes (gid31791):

| hole | meshes | points | y range (m) | y spread |
|---|---|---|---|---|
| 01 | 13 | 26,445 | −40.8 … 5.8 | **46.5 m** |
| 07 | 13 | 28,473 | −35.9 … 3.3 | **39.1 m** |
| 11 | 13 | 26,196 | −33.3 … 4.1 | **37.4 m** |

Real terrain (37–46 m relief), not flat/zero → **PlaysLike works on shipped geometry, no external DEM**. **Coverage today: 24 courses / 360 hole-meshes** already decoded. The Phase-0 spike confirmed reliability + coverage (the open question Codex re-framed) — elevation **exists and is good**; the remaining work is wiring/coverage expansion, not sourcing.

---

## Part B — Endpoint auth/route migration matrix (63 routes)

### B1. Current auth distribution

| auth type | count | meaning |
|---|---|---|
| public (no auth) | 4 | `/`, health, settings/product, geometry/coverage |
| conditional (param-dependent) | 5 | readiness, sync/status, weather (persist), geometry hole/map (source_ref) |
| **admin-mw-only** (middleware guards, handler has no own check) | 10 | round/course package GET, events/replay, reconciliation GET, caddie/context, annotations GET×2, media/target GET×2, courses/search |
| admin-both (middleware + handler `require_admin_token`) | 20 | events POST/ack, state, reconciliation/apply, geometry/ensure, caddie/decision+audit, media/annotation writes, 5× report-generate, sync/garmin×2 |
| player-scoped (admin OR player token + `Depends`) | 18 | 9 history GETs, 5 report-read GETs, courses/prep(+tips), mobile/courses/options |
| handler-only (no middleware gate) | 1 | `POST /players/{id}/rounds` |
| admin-router (`/admin/*`) | 5 | player management |

### B2. Verified IDOR risks (must become user-scoped before multi-user) — `[verified against code]`

The root cause is **`load_history_data_for_mode()` called with NO `player_id` → defaults to OWNER**, embedding the owner's bag/shot history for any authenticated caller:

| Route | Vector | Cite | verified |
|---|---|---|---|
| `GET …/mobile/rounds/{id}/package` | owner bag + history in the live package | `mobile.py:49` | ✅ |
| `GET …/mobile/courses/{gid}/package` | owner data in the "start round" package | `mobile.py:76` | ✅ |
| `GET …/caddie/context` | club recs from owner's measured distances | `caddie.py:61` | ✅ |
| `GET …/mobile/rounds/{id}/reconciliation` | owner history in the diff + middleware-only auth | `mobile.py:161` | (matrix) |
| `POST …/reconciliation/apply` | owner history + mutating write | `mobile.py:169` | (matrix) |
| `GET …/geometry/hole/{}/{}?source_ref=` | owner shot routes overlaid when source_ref present | `geometry.py:93` | (matrix) |
| event log routes (`…/events`, `…/replay`, `…/ack`, `…/state`) | `round_id` is a bare string with **no player tag** in the log | `mobile_live.py` | (matrix) |

Already-clean (player-scoped, `[verified]` `data_source` scopes by `player_id`): history/reports reads, `courses/prep`, `mobile/courses/options`.

### B3. Migration priorities (drives Phase 1/2)

1. **Thread `player_id`/`user_id` through `load_history_data_for_mode()`** at the package/context/reconciliation/geometry-source_ref call sites — the single highest-leverage fix (removes the main IDOR class).
2. **Add a player/round-ownership tag to the live event log** (`raw_live_events.user_id` + `round_acl`) so events/replay/state/ack can't cross users.
3. **Move `POST /players/{id}/rounds` into the middleware gate** (today handler-only).
4. **Downgrade `courses/search` to public** (over-gated; no player data) and keep geometry reads public when `source_ref` is absent.
5. Per-player stores for **report/annotation/media/decision** (today global/owner) before non-owner writes.
6. Garmin sync, admin/players, report-generate (LLM) **stay admin-only**.

---

## Net effect on the design

- **§4 schema:** `tee_boxes` += `rating, slope`; `course_holes` par/handicap become **per-tee/gender** (a `course_hole_tees` child or a `gender` discriminator). Elevation needs no new source.
- **Phase 1 (identity):** the IDOR fix is mechanical once `user_id` is resolvable — thread it into the ~6 unscoped data-loader call sites + tag the event log.
- **Phase 4 (catalog):** richer anonymous hydration (rating/slope/per-gender par/raster thumbnails) — no credential.
- **Readiness for Phase-1 plan:** the two blockers Codex named (spike + auth matrix) are now resolved → Phase 1 can be planned.
