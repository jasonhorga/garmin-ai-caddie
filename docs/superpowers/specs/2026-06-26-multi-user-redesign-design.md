# Multi-User AI Caddie — Architecture Design

> **Status:** Design, for review (not yet a plan)
> **Date:** 2026-06-26
> **Decided:** Sign in with Apple (identity) · PostgreSQL (storage)
> **Inputs:** owner product direction (this conversation) + an independent Codex (gpt-5.5) architecture review grounded in the current repo. Where Codex corrected the first-pass proposal, the correction is folded in and marked `[Codex]`.

---

## 1. Goal

Turn AI Caddie from a **single-owner, filesystem-backed** personal tool into a **family-scale multi-user system** where each member's golf data — whether **synced from Garmin** or **recorded natively on Apple Watch** — is partitioned per-user and unified in a **Postgres** database. Our database becomes the **superset source of truth** (it holds rounds Garmin never sees). The course/map catalog is a **separate, shared, versioned** domain.

This is a multi-subsystem program. This document is the **top-level architecture + decomposition**; each phase in §10 gets its own spec → plan → implementation.

## 2. Users & scenarios

| Type | Who | Data flow |
|---|---|---|
| (a) Garmin user | owner, daughter | Garmin watch → sync into our system; view richer stats/prep on iOS |
| (b) Hybrid round | any Garmin user, no-Garmin day | played on **Apple Watch only** → recorded in **our DB**, **not** pushed back to Garmin ⇒ our data ⊇ Garmin's |
| (c) Non-Garmin user | wife, son | Apple Watch + our app only; **never** touch Garmin |

Trusted **family** scale, **not** public SaaS. The owner is the **admin super-user**.

## 3. Architecture: three domains

1. **Identity & tenancy** — who is who; family membership; roles; devices; sessions.
2. **Per-user activity** — rounds / shots / events, partitioned by `user_id`; the unified golf record.
3. **Shared course catalog** — courses / holes / tees / geometry; **global, versioned, not per-user**.

`[Codex]` **Caveat on domain 3:** lightweight CourseView metadata (search + release fields) is anonymous, but **decoding the heavy prodgeometry needs a Garmin credential** (`ai_caddie/geometry/fetch_courseview_geometry_key.js` needs a `playerProfileId`). So the catalog is only *partly* decoupled from Garmin — see §7.

## 4. Data model — raw → canonical (core principle)

`[Codex]` The current code already silently merges sources (owner Garmin + manual rounds are merged by date/course with **Garmin winning**, `ai_caddie/history/history.py:342`). A single table with a `source` column is **too thin**. Instead:

- **Raw inputs are immutable, append-only, idempotent.** They are never overwritten.
- **Canonical rows are derived projections** carrying **provenance**. Garmin must **not** silently clobber Apple-native data; duplicate candidates are **linked and resolved by policy or review**.

**Raw tables (immutable):**

```
raw_garmin_scorecards(id, garmin_account_id, garmin_scorecard_id,
                      payload_jsonb, payload_hash, fetched_at,
                      unique(garmin_account_id, garmin_scorecard_id))
raw_garmin_shots(id, garmin_account_id, garmin_scorecard_id, payload_jsonb, payload_hash)
raw_live_events(id, user_id, device_id, client_id, client_round_id,
                event_id, idempotency_key, server_sequence,
                kind, payload_jsonb, observed_at,
                unique(user_id, client_id, event_id))   -- the iOS/watch offline event log
```

**Canonical golf model (derived + provenance):**

```
rounds(id, user_id, course_id, course_version_id,
       started_at, ended_at, status, primary_source,
       external_garmin_scorecard_id, created_by_device_id, finalized_at)
round_sources(round_id, source, raw_source_id, role, confidence)   -- provenance + dedup linkage
round_holes(round_id, hole_number, course_hole_id, par, handicap,
            tee_box_id, score, putts, penalties)
shots(id, round_id, hole_number, sequence, source, club_id,
      start_geom, end_geom, distance_m, lie_start, lie_end,
      raw_event_id, raw_garmin_shot_id, excluded_from_stats)
```

Source of truth = **immutable raw inputs + explicit user corrections**; canonical rows are recomputable from them.

## 5. Identity & authorization

- **Sign in with Apple** → user identity (frictionless on their devices; App-Store-required if ever public). Owner = admin super-user.
- Tables: `families`, `users`, `family_members(role)`, `devices`, `user_sessions`.
- `[Codex]` **Identity ≠ authorization.** Still need: family membership + roles, **sharing** (one member must not see another's data unless shared), account **deletion**, token **revocation**, owner-access **audit**.
- **Per-user backend addressing & tokens:** the iOS app must address a **per-user scope**, not one global admin token. Device sessions issue **short-lived scoped tokens**. `[Codex]` The **watch** must receive a **short-lived, round/user-scoped device token — never the global admin token** (replaces today's phone→watch admin-token push in `WatchEventBridge.swift`; this is the same hole flagged as **P1-1** during the remediation arc).

## 6. Garmin integration — per-account, refactored

- **Today:** process-global single-owner. The connector mutates **module globals** for token/data paths (`ai_caddie/connectors/garmin_cn.py`), and the server holds a **global sync lock** because concurrent syncs would cross-contaminate paths (`server_v2/main.py`). `[Codex]` This **cannot** safely become N users as-is.
- **New:**
  - `garmin_accounts` + `garmin_session_secrets` (cookies/tokens **encrypted per account**, not the global `.garmin_tokens`) + `sync_jobs` / `sync_runs`.
  - Refactor the fetch code to **accept an explicit session object** and **emit raw payloads** (→ `raw_garmin_*`), **not** write `data/scorecards` / `data/shots` files.
  - A **job worker**: one advisory lock **per `garmin_account_id`**, jittered schedules, backoff, states `connected | reauth_required | rate_limited | disabled`.
  - Per-account Playwright profiles (`profiles/garmin/<garmin_account_id>`) only as a **fallback**, concurrency-limited.
  - `[Codex]` Prefer **user-assisted login / cookie capture** (from the iOS app or a web auth flow) over storing Garmin **passwords** server-side. CN re-auth may need SMS/captcha → surface `reauth_required` to the user.

## 7. Course catalog — shared, versioned, two-tier

- **Lightweight catalog (anonymous → Postgres):** course identity, province/city, **lat/lon**, holes, tees, par, handicap, yardage, `release_version` / `release_id`. Crawl **regionally** (their provinces) — `[Codex]` not all-CN — via a **rate-limited queue + backoff**, ToS-aware (the only entry is a name-query search, `ai_caddie/courses/course_search.py`, not a clean bulk endpoint). **Enables "start a round near me"** by lat/lon — fixing today's played-courses-only list.
- **Heavy geometry (artifacts on disk/object store + DB metadata):** decoded meshes, hazard extracts, rasters. `[Codex]` Decode is a heavy node/Draco subprocess **and needs a Garmin credential** (`playerProfileId`). **On-demand** for nearby / played / explicitly-prepared courses — not bulk-all.
- **Version model:** `course_versions(course_id, release_version, release_id, fetched_at, raw_pb_artifact_id)`; `course_holes`, `tee_boxes`, `geometry_artifacts(course_version_id, hole_number, kind, storage_uri, sha256, status)`. **Rounds reference `course_version_id`** so a new Garmin map never reinterprets old rounds. A **cron freshness check** by `release_version` re-pulls on bump and can surface "map updated" like the Garmin watch does.
- **彻底探究 — exploration spike (prerequisite):** BEFORE finalizing the course schema, dump the **full** CourseView release protobuf + the decoded mesh into a **field data dictionary** — catalog every field (incl. the parsed-but-unused `release_version`, `course lat/lon`, the explicit `unknown_10`, tee ratings/slopes/per-tee yardages, green contours, hazard polygon types) and, crucially, **whether elevation / 3D exists** (plays-like distance hinges on it). If Garmin has **no** elevation → a separate DEM decision (out of scope here).

## 8. Migration — strangler (not indefinite dual-write)

1. Stand up the DB (raw + canonical + course tables).
2. **Backfill** existing filesystem data → raw + canonical, preserving original path/source as **provenance**.
3. Switch read APIs to the DB **behind a feature flag**; **compare** DB vs filesystem output (parity check).
4. **Bridge:** keep the old Garmin CLI writing files for a short window, then **import** those files into the DB; **new** Apple/watch ingest writes **DB-first**.
5. `[Codex]` If legacy engines still need Garmin-shaped files, **generate compat files from the DB** — do **not** make clients dual-write.
6. Cut reads over to the DB; retire filesystem writes.

**Blobs** (geometry / media / reports / raw protobufs) stay **outside** Postgres, but every blob gets a DB row: checksum, owner-or-course-version, privacy class, decoder/generator version, storage URI, byte size, lifecycle state.

## 9. Cross-cutting concerns

- `[Codex]` **iOS offline store** is today single-user local state → needs **per-user namespaces**, else switching accounts uploads the **wrong** event log.
- `[Codex]` **Round IDs must be user-scoped UUIDs** — a course-derived id collides when family members play the same course (the generalized form of the iOS **P1-3** fix from the remediation arc).
- `[Codex]` **Conflict handling:** keep live-event reconciliation conflict-detecting, but **persist conflicts** and **require review** for score / penalty / putt / club disagreements across the watch ↔ phone ↔ Garmin three-way.
- `[Codex]` **Observability** (not optional): per-account sync status, auth failures, Garmin HTTP errors, geometry-decode queue health, migration parity, event-finalization failures, artifact cache hit rates.
- `[Codex]` **Backups & deletion — design now.** Postgres backup alone is insufficient because media + course artifacts live **outside** the DB; per-user deletion is a hard requirement (account deletion).

## 10. Phasing (sequenced per Codex)

`[Codex]` "Apple ingest first" creates an immediate re-migration if identity / course-versions / canonical rules don't exist yet. Revised order:

1. **Identity / family / device / session** model.
2. **Postgres schema**: raw sources + canonical projections + course versions.
3. **Backfill** existing filesystem data → DB.
4. **Lightweight course catalog** + location-based "start a round."
5. **Apple-Watch-native multi-user ingest** → DB (round finalization, conflict persistence).
6. **Refactor Garmin sync → per-account worker** (owner first).
7. **Add family Garmin accounts.**
8. **Heavy course-geometry crawl/refresh** (last) — gated by the §7 exploration spike.

Each phase is its own spec → plan → implementation; phases 1–3 are the foundation and must land before 4+.

## 11. Open decisions (need owner input)

1. **Geometry-key credential:** a **dedicated course-data Garmin account** for geometry decode (recommended — isolates it from family users) vs. borrowing a user's credential.
2. **Crawl region scope:** confirm which provinces/cities.
3. **Elevation / DEM:** deferred until the spike answers whether Garmin carries elevation.
4. **Apple-native rounds → Garmin:** owner said one-way (our DB only, never pushed back) — confirm this is permanent (it simplifies the model: Garmin is import-only).

## 12. Out of scope (for now)

Public/stranger SaaS; non-Apple identity (Google); DEM/elevation sourcing; pushing Apple-native rounds back to Garmin; the in-flight remediation debt items (God-unit decomposition, marker-anchored `repo_root()`) which are independent of this redesign.
