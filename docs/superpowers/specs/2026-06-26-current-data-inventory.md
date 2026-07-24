# Current Data Inventory — AI Caddie (pre-redesign)

> **Status:** Reference (grounded field dictionary)
> **Date:** 2026-06-26
> **Purpose:** Ground the multi-user Postgres schema ([2026-06-26-multi-user-redesign-design.md](2026-06-26-multi-user-redesign-design.md)) in the **actual** data shapes. Derived from the code that reads/writes each store (`data/` files are gitignored). Every claim is traceable to `file:line`.

The data lives in **six logical stores**, all on the filesystem today, all single-owner-oriented.

---

## A. Identity / players  (`ai_caddie/rounds/players.py`, `server_v2/players_api.py`)

**`data/players/registry.json`** → `{schema:"ai-caddie-players-v1", players:[PlayerRow]}`

| PlayerRow field | type | notes |
|---|---|---|
| `id` | str | `"me"` (owner, `players.py:14`) or `"p_<hex8>"` |
| `name`, `avatar`, `createdAt` | str | owner default name `"我"` |
| `isOwner` | bool | true only for `"me"` |
| `tokenHash` | str\|null | `"sha256:<hex64>"`; **null for owner** (owner uses admin header) |
| `tokenLast4` | str\|null | visual confirm; null for owner |

- **Token resolution** (`players.py:112`): hash the bearer, scan rows with `compare_digest`. Owner resolved separately via admin header / open-dev (`players_api.py:69`).
- **On-disk partitioning** (the legacy multi-tenant model Phase 1 must migrate):
  - owner Garmin → flat `data/scorecards/*.json` + `data/shots/*.json`
  - owner manual → `data/players/me/{scorecards,shots,summary.json,rounds_index.json}`
  - non-owner → `data/players/<id>/…` (one tree)
- **Players are READ-only shares** today; non-owners have no Garmin, no write path. Owner can't be deleted (`players.py:125`).

---

## B. Garmin import  (`ai_caddie/garmin/fetch.py`, read by `history.py`/`data.py`)

**Scorecard** `data/scorecards/{id}.json` → `scorecardDetails[0]` + `courseSnapshots[0]`. **Dedup key = `scorecard.id` (int)**.
- `scorecard`: `id`, `formattedStartTime`/`startTime`, `strokes`, `holesCompleted`, `courseGlobalId`, `frontNineGlobalCourseId`, `backNineGlobalCourseId`, `courseSnapshotId`, `teeBox`/`teeBoxRating`/`teeBoxSlope`, `holes[]`.
- `holes[]`: `number`, `strokes` (null=not played), `handicapScore`, `putts?`, `penalties?`, `fairwayShotOutcome?`, `pinPositionLat/Lon?` (semicircle). **No `par` / no hole handicap** — par comes from `courseSnapshots[0].holePars` (digit string), handicap from `tees[].holeHandicaps`.
- `scorecardStats.round`: fairwaysHit/Left/Right/Recorded, greensInRegulation, putts, holes{UnderPar,Par,Bogey,OverBogey,Birdie,Eagle}.
- `statsComparison`: driveRating/approachRating/chipRating. `scorecardDetails[0].longestShotInMeters`.
- `courseSnapshots[0]`: `name` (may contain `" ~ "` tee/loop variant), `holePars` (digit str/list), `roundPar`/`frontNinePar`/`backNinePar`, `lat`/`lon` (**millionths of a degree**), `city`, `country`.

**Shots** `data/shots/{scorecardId}.json` → `clubDetails[]` + `holeShots[]`. **Dedup key = `shot.id` (int)**.
- `shots[]`: `id`, `scorecardId`, `playerProfileId`, `holeNumber`, `shotOrder`, `shotType` (TEE/APPROACH/PUTT/CHIP/PENALTY), `shotSource` (`DEVICE_AUTO`=GPS), `clubId`, `meters`, `excludeFromStats`, `shotTime`, `startLoc`/`endLoc` `{lat,lon (semicircle), lie, lieSource, x?, y?}`.
- `holeShots[]`: `holeNumber`, `holeImageUrl`, `pinPosition{lat,lon,x,y}`.
- `clubDetails[]`: `id`, `clubTypeId` (1–23), `name`, `shaftLength`, `averageDistance`, `retired`, `deleted`.
- `_no_data:true` when Garmin has no AutoShot data (old round).

**Club bag** `data/club_bag.json` (`fetch_clubs`): `clubs[]` `{id, clubTypeId, customName, typeName, loftAngle, shaftLength, retired, deleted}`. **Bag-entry key = `club.id`; type dict key = `clubTypeId`**.

**Dedup keys:** `garmin_rounds`=scorecard.id · `garmin_shots`=shot.id · `bag`=club.id · `club_types`=clubTypeId.

---

## C. Live-round events  (iOS/watch offline log → `ai_caddie/caddie/mobile_live.py`)

**`LiveRoundEvent`** (`models.py:923`, `live_round_event.schema.json`): `schema`, `eventId`, `roundId`, `timestamp`, `hole`, `kind`, `payload`, `clientId`. Per-kind payload:

| kind | payload |
|---|---|
| `score` | `{strokes}` |
| `putt` / `penalty` | `{putts}` / `{penalties}` |
| `club` | `{clubName, shotType(tee/approach/recovery), strategyMode(protect_score/stock/attack), lie, distanceToPinM, offlineOptionId, decisionId, decision{}, actualShot{}}` |
| `location` | `{latitude, longitude, horizontalAccuracyM, altitudeM, targetLatitude, targetLongitude, targetKind(pin/target/green_center)}` (WGS84) |
| `note` | `{note}` |
| `photo`/`video` | `{assetLocalId, mediaType, fileURL(REDACTED), mediaId, note, durationS?}` |
| `sync_marker` | `{status, acceptedEventIds[], duplicateEventIds[], serverSequence}` |

**Backend storage** (`mobile_live.py:30`): **single global `data/mobile_events/events.jsonl`** (ALL rounds, **no player_id**), per-line `{roundId, idempotencyKey, serverSequence (monotonic across ALL rounds), event}`; ack store `client_acks.json` keyed `f"{roundId}\n{clientId}"`; flock on append.

**clientId values:** `"ios-phone"` (default, hardcoded in `LiveRoundEvent.swift:83`/`SyncClient.swift:100`), `"apple-watch"` (hardcoded `WatchEventBridge.swift:428`), `""` (legacy). ⚠️ **two users on two phones both emit `"ios-phone"` → events would wrongly collapse.**

**Dedup:** event = `(roundId, clientId, eventId)`; batch = `(roundId, idempotencyKey)`.

**Manual ingest** (`round_ingest.py`): writes **Garmin-isomorphic** files under `data/players/<player_id>/{scorecards,shots,summary.json,rounds_index.json}`; `round_id = int(sha256(idempotency_key)[:12])`; idempotency = `Idempotency-Key` header → `clientRoundId` → content-hash (`"auto:"+sha256(...)`). Consumes `club/location/score/putt/penalty/note`; **skips `photo/video/sync_marker`**. `location` pairs with the preceding `club`.

**Reconciliation / conflicts:**
- `build_round_state` (`mobile_live.py:2398`): project per-hole state, **last-write-wins by serverSequence**; conflict `{hole, field, clients[]}` emitted when ≥2 distinct clientIds wrote a field — **computed at request time, NOT persisted**.
- Garmin reconciliation (`mobile_reconciliation.py:333`): event-vs-Garmin diff `{eventId, kind, hole, localValue, garminValue}` → suggestions (score/putt/club/penalty corrections, hole_note, caddie_feedback) → written to the **annotation store only on `…/reconciliation/apply`** (idempotent via `sourceSuggestionId`).

**Multi-user gaps:** no player_id in the log · clientId is a static role-string (collision) · mobile-events POST is admin-gated not user-scoped (`main.py:853`) · replay endpoint has **no auth** (`main.py:857`) · ack store + `MOBILE_ROOT=Path(".")` are global · **no per-install device UUID**.

---

## D. Canonical engine model  (`ai_caddie/history/history.py`)

`HistoryData{raw_rounds, rounds(merged), shots}`. The engine projects raw files into:

**Round dict** (`_scorecard_to_round`, `history.py:271`): `id`(=scorecard.id), `ids[]`, `date`, `strokes`, `holesCompleted`, `course`, `courseCanonical`, **`courseKey="c_"+sha1(canonicalName)[:10]`** (⚠️ **name-derived, not a gid** → same-name courses spuriously merge), `courseId`/`frontNineGlobalCourseId`/`backNineGlobalCourseId`, `lat`/`lon`, `par`, `holePars`, `holes[]`, fairway/GIR/putt/distribution stats, `rating`/`slope`, `source`(garmin/manual), `merged`, **`supersededBy`**.
- **`_merge_owner_sources`** (`history.py:331`): collision key `(date[:10], courseKey)`; Garmin wins, manual gets `supersededBy` (kept on disk, excluded from raw_rounds/stats). ← *already a soft raw→canonical supersede, but automatic + not reviewable.*
- **`merge_same_day_halves`** (`history.py:363`): two 9-hole rounds same `(date, courseCanonical)` → synthetic 18 (`id="merged_<f>_<b>"`, holes 10–18 renumbered). ⚠️ merge key collides if you genuinely play 1–9 twice in a day.
- **Composite hole→geometry** (`round_hole_ref`, `data.py:229`): 1–9→`(frontGid, hole)`; 10–18→`(backGid, hole−9)` or `(courseGlobalId, hole)`.

**Shot dict** (`load_shot_history`, `history.py:504`): `id`, `scorecardId`, `hole`, `globalId`, `localHole`, `order`, `clubId`, `clubName`, `type`, `meters`, `start`/`end`{lat,lon,lie}, `_globalIndex`.

**Round identity today = `scorecard.id`** (Garmin opaque int / manual hash) — **collides across players** (no player_id in file body; attribution is by directory path only).

---

## E. Course catalog / geometry  (`ai_caddie/geometry/`, `ai_caddie/courses/course_search.py`)

**Anonymous** (no auth, `omt.garmin.cn`):
- **Search** (`course_search.py:29`): per record `global_id`(f7), `name`(f12), `holes`(f13), `province`(f16), `city`(f21). *No lat/lon.*
- **Release protobuf** (`inspect_courseview_release.py:80`): `course_id`(f1), **`release_version`(f2)**, `release_id`(f3), `course_name`(f4), **tees**(f6: name/gender/index), **holes**(f7), **`course_lat/lon`**(f8/f9, raw semicircle ×180/2³¹), **`unknown_10`**(f10). Per-hole: `hole`, `lat/lon`(raw), `par`, `handicap`, `yardage_or_length`, `raster_url`, `geometry_url`.
- ⇒ **per-hole + course GPS are anonymous** → rangefinder + map pins need **no** geometry decode/credential.

**Credentialed** (Connect DI OAuth2 → Golf DI → IT token + `playerProfileId` as `3D-Account-Id`, `fetch_courseview_geometry_key.js`): only the **encrypted geometry zip content** — Draco meshes, `hole.json` (RefLat/RefLon, TeeLocations, Doglegs), hazards, **elevation**.

**Mesh** `output/prodgeometry/gid{N}_h{HH}_meshes.json` (`decode_courseview_geometry.js`): `meshes[].positions=[[x,y,z]]` where **`y`=terrain elevation (m)**; 2D frame east=−x, north=z. Hazard kinds (Bunker/Lake/Green/Fairway/Teebox/TreeArea/Rough/PlayableBounds). **`elevation.py` already computes PlaysLike (±yd) from mesh `y` — no external DEM**, gated by "geometry ready" coverage.

**Course version key = `(course_id, release_id)`** (+ `release_version` counter). **Unused-but-useful fields** (Phase-0 spike seed): course/hole GPS (f8/f9, f7.f4/f5), `yardage_or_length`, `unknown_10`, tee gender/index, `raster_url` thumbnail, Rough/PlayableBounds boundaries, foliage tree positions.

---

## F. Media & decisions

- **Media** `data/media/media_index.jsonl` (`media.py:217`, append-only, last-write-wins per id): `{id, createdAt, targetType(round/hole/shot), targetId, mediaKind(photo/video), localPath, capturedAt, privacyState(private_local/synced/redacted), source, uploadStatus, contentByteSize, mimeType, durationS}`. Limits: photo ≤12MB, video ≤80MB/≤180s.
- **Decisions** `data/decisions/decisions.jsonl` (`decision.py:502`): `{id, storedAt, decisionId(roundId:hole:shotOrder), sourceRef, shotType, selectedOptionId(safe/stock/attack), evidenceRefs[], decision{}}`. **Audits** `data/decision_audits/decision_audits.jsonl`: `{id, decisionId, plannedOptionId, actualOptionId, actualShotRefs[], classification, audit{}}`.

---

## Cross-cutting facts that drive the schema

1. **Stable external IDs exist** for Garmin raw (scorecard.id, shot.id, club.id) → clean raw-table unique keys.
2. **Round identity is broken for multi-user**: `scorecard.id` collides across players; `courseKey` is name-derived; live `roundId` is client-chosen with no user namespace; `clientId` is a role-string.
3. **Composite courses are real** (two gids / a `merged_*` synthetic round) → a round needs **per-segment/per-hole** course-version linkage, not one `course_version_id`.
4. **Par/handicap are course-derived**, not in the scorecard hole → they belong in `course_holes`, joined in.
5. **Course + per-hole GPS is anonymous**; only geometry-zip content is credentialed → catalog vs geometry split is real and the catalog is richer than "province/city".
6. **Elevation already exists** (mesh `y`) → the spike validates reliability/coverage, not existence.
7. **Conflicts are computed, never persisted** → durable conflict/correction tables are net-new.
8. **Manual ingest writes Garmin-shaped files** → the strangler bridge must keep generating them from the DB.
