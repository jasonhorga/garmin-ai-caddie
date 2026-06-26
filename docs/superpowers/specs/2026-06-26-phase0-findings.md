# Phase 0 Findings — CourseView field dictionary + endpoint auth matrix

> **Status:** Done (spike results). Feeds the schema ([design v2](2026-06-26-multi-user-redesign-design.md)) and the Phase-1/2 plans.
> **Date:** 2026-06-26
> Part A run against **real CourseView data** on the homeserver (gids 31791/39315/39247 + 24 decoded courses). Part B's highest-risk claims were **verified against code** (not taken on faith).

---

## Part A — CourseView "彻底探究" (real-data protobuf walk + mesh-`y` validation)

### A1. The anonymous release carries MORE than `inspect_release` parses

A generic field-walk of the release protobuf for 3 real courses surfaced **unparsed but valuable** fields (all **anonymous** — no geometry decode/credential needed):

| Field | Observed | Meaning (likely) | Action |
|---|---|---|---|
| **tee `.3`** (wire 5, fixed32 float) | float | **course rating** per tee | parse → `tee_boxes.rating` |
| **tee `.2`** (varint) | 119 / 120 | **slope** per tee | parse → `tee_boxes.slope` |
| **hole `.2` / `.3`** | nested + `"MEN"` / `"MENNotSpecified"` | par / handicap are **per-tee-gender** (we only read the first nested f1 today) | model par/handicap **per tee/gender**, not a single value |
| **f5** (×2/course) | `…IN$MEN` strings | tee-set / gender-set definitions | decode in the spike's full dictionary |
| **f10 `unknown_10`** | 22 / 28 / 29 (玉岛 & Players 都=22) | small int, **clusters by course** → likely a province/region code | sample more courses to confirm |
| **f12** | present (=1) on some courses | course-level flag | sample to confirm |
| **hole `.7` raster_url** | `birdseye…` | per-hole overhead thumbnail (anonymous) | render in prep without geometry |

**Schema impact:** the **lightweight (anonymous) catalog is richer than "province/city"** — `tee_boxes` gets **rating + slope**, and `course_holes` par/handicap should be modeled **per tee/gender**. None of this needs the credentialed geometry path.

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
