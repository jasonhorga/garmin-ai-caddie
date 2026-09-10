# Multi-User AI Caddie — Architecture Design (v2)

> **Status:** Design, for review (not yet a plan)
> **Date:** 2026-06-26
> **Decided:** Sign in with Apple (identity) · PostgreSQL (storage)
> **Grounded in:** [Current Data Inventory](2026-06-26-current-data-inventory.md) (real field/key analysis of all six stores).
> **Reviewed by Codex** (independent, repo-grounded) — its corrections are folded in and marked `[Codex]`; corrections I additionally **verified against code** are marked `[verified]`.

---

## 1. Goal

Turn AI Caddie from a **single-owner, filesystem-backed** tool (with a thin **read-only** player-share model) into a **family-scale multi-user system** where each member's golf data — **synced from Garmin** or **recorded natively on Apple Watch** — is partitioned per-user and unified in **Postgres**. Our DB is the **superset source of truth** (it holds Apple-Watch rounds Garmin never sees). The course/map catalog is a **separate, shared, versioned** domain.

Multi-subsystem program → this is the **top-level architecture + decomposition**; each phase (§10) gets its own spec → plan → implementation.

## 2. Users & scenarios

| Type | Who | Data flow |
|---|---|---|
| (a) Garmin user | owner, daughter | Garmin watch → sync into our system; richer stats/prep on iOS |
| (b) Hybrid round | a Garmin user, no-Garmin day | played on **Apple Watch only** → **our DB**, **not** pushed to Garmin ⇒ our data ⊇ Garmin's |
| (c) Non-Garmin user | wife, son | Apple Watch + our app only; **never** touch Garmin |

Trusted **family** scale, **not** public SaaS. Owner = **admin super-user**.

`[Codex][verified]` The repo is **not pure single-owner**: it already has owner-minted **read-only player tokens** (`players.py`) and per-player file roots (`data/players/<id>/`). Phase 1 must **migrate this legacy `me`/`p_*` model**, not greenfield it.

## 3. Architecture: three domains

1. **Identity & tenancy** — users, families, roles, devices, sessions, sharing.
2. **Per-user activity** — rounds / shots / events / media, partitioned by `user_id`.
3. **Shared course catalog** — courses / versions / holes / tees / geometry; **global, versioned**.

`[Codex][verified]` **Domain-3 anonymity is partial:** the **search + release metadata is anonymous — including per-hole and course GPS** (`course_lat/lon` f8/f9, per-hole `lat/lon` f7.f4/f5), so rangefinder distances and map pins need **no credential**. Only **decoding the geometry zip** (meshes, hazards, elevation) needs a Garmin credential chain (Connect DI → Golf DI → IT token + `playerProfileId`). See §7.

## 4. Data model — raw → canonical (grounded)

`[Codex]` **Principle:** raw inputs are **immutable, append-only, idempotent**; canonical rows are **derived projections carrying provenance**. The current engine already does a soft "Garmin-wins" supersede (`history.py:331`, manual round flagged `supersededBy`, kept on disk) — `[verified]` so the instinct exists, but it is **automatic and not reviewable**. The new model makes the supersede an **explicit, recorded, reviewable** decision. Keys/fields below come from the [inventory](2026-06-26-current-data-inventory.md).

### Identity & tenancy
```
families(id, name, owner_user_id, created_at)
users(id, family_id, display_name, role, avatar, created_at, deleted_at)
user_identities(id, user_id, provider='apple', subject, email?, created_at)        -- Apple `sub`
legacy_player_map(legacy_player_id, user_id)                                        -- 'me' / 'p_*' → users
devices(id, user_id, install_uuid, platform, created_at, last_seen)                -- per-install UUID (NEW — fixes the clientId collision)
sessions(id, user_id, device_id, scope, issued_at, expires_at, refresh_of?)
token_revocations(session_id, revoked_at, reason)
access_audit(id, actor_user_id, action, target_user_id, target_kind, at)           -- esp. owner/admin cross-user access
round_acl(round_id, user_id, access)                                               -- 'owner' | 'shared_read'; default private
```

### Raw inputs (immutable)
```
garmin_accounts(id, user_id, garmin_login_ref, status, created_at)                 -- status: connected|reauth_required|rate_limited|disabled
garmin_session_secrets(garmin_account_id, enc_cookie, enc_tokens, profile_id, updated_at)   -- ENCRYPTED, per-account (not the global .garmin_tokens)
raw_garmin_scorecards(id, garmin_account_id, garmin_scorecard_id, payload_jsonb, payload_hash, fetched_at,
                      unique(garmin_account_id, garmin_scorecard_id))
raw_garmin_shots(id, garmin_account_id, garmin_scorecard_id, garmin_shot_id, payload_jsonb,
                 unique(garmin_account_id, garmin_shot_id))
raw_garmin_clubs(id, garmin_account_id, garmin_club_id, club_type_id, payload_jsonb, fetched_at,
                 unique(garmin_account_id, garmin_club_id))                         -- `[Codex]` clubs are a real dependency, not derived from shots
raw_live_events(id, user_id, device_id, client_round_id, client_id, event_id, idempotency_key,
                server_sequence, kind, payload_jsonb, observed_at,
                unique(user_id, device_id, client_round_id, event_id))             -- `[Codex]` stronger key than today's (roundId,clientId,eventId)
raw_media_assets(id, user_id, asset_local_id, media_kind, storage_uri, sha256, byte_size,
                 mime_type, duration_s?, captured_at, privacy_state, created_at)   -- `[Codex]` media ownership/deletion was unmodeled
```

### Canonical (projections + provenance)
```
rounds(id uuid, user_id, started_at, ended_at, status, primary_source, finalized_at, created_by_device_id)  -- `[Codex]` user-scoped UUID, not scorecard.id
round_external_ids(round_id, source, account_id, external_id,
                   unique(source, account_id, external_id))                        -- `[Codex]` Garmin scorecard.id scoped under account, not a bare column
round_sources(round_id, source, raw_kind, raw_id, role, confidence)               -- provenance + dedup linkage; role: primary|secondary|superseded
round_course_segments(round_id, hole_from, hole_to, course_id, course_version_id) -- `[Codex][verified]` composite front/back (two gids) needs per-segment links
round_holes(round_id, hole_number, par, handicap, tee_box_id?, score, putts, penalties, gir?, fairway?, course_version_id)
shots(id uuid, round_id, hole_number, sequence, source, club_id?, start_lat, start_lon, start_lie,
      end_lat, end_lon, end_lie, distance_m, shot_type, shot_source, raw_event_id?, raw_garmin_shot_id?, excluded_from_stats)
user_clubs(id, user_id, garmin_club_id?, club_type_id, custom_name, type_name, loft_angle, retired, deleted)
```

### Conflicts / corrections (durable — net-new)
`[Codex][verified]` today conflicts are computed at request time and never persisted (`mobile_live.py:2398`). Make them durable workflow state:
```
round_conflicts(id, round_id, hole_number, field, status, detected_at)            -- status: open|resolved
conflict_candidates(conflict_id, source, client_or_account, value, server_sequence?)
conflict_reviews(conflict_id, reviewed_by_user_id, chosen_value, reviewed_at)
user_corrections(id, user_id, round_id, hole_number?, field, value, source, created_at)  -- the explicit source-of-truth overlay
```

### Course catalog (shared)
```
courses(id, garmin_global_id, name, holes, province, city, course_lat, course_lon)  -- lat/lon from release f8/f9 (anonymous)
course_versions(id, course_id, release_version, release_id, fetched_at, raw_pb_artifact_id?,
                unique(course_id, release_id))                                       -- `[verified]` version key = (course_id, release_id)
course_holes(course_version_id, hole_number, par, handicap, yardage, hole_lat, hole_lon, raster_url, geometry_url)  -- per-hole GPS anonymous
tee_boxes(course_version_id, name, gender, ordering, rating?, slope?)
geometry_artifacts(course_version_id, hole_number, kind, storage_uri, sha256, decoder_version, status, decoded_at)  -- mesh|hazards|elevation; ON DISK, DB holds metadata
```

**Indexes:** the `unique(...)` above, plus `rounds(user_id, started_at)`, `shots(round_id, hole_number)`, `geometry_artifacts(course_version_id, hole_number, kind)`, `round_acl(user_id)`.

**Blobs** (geometry meshes, media, raw protobufs, reports) stay **outside Postgres**; every blob has a row (sha256, owner/course-version, privacy class, decoder/generator version, storage URI, byte size, lifecycle).

## 5. Identity & authorization

- **Sign in with Apple** → `user_identities(provider='apple', subject=<sub>)`. Owner = admin super-user. Family members may also be **owner-provisioned** (a one-time login replacing today's `p_*` link).
- **Migration:** `legacy_player_map` maps `me` → owner user, each `p_*` → a user; their per-player file trees backfill into that user's partition.
- `[Codex]` **Authorization ≠ identity:** `families` + `family_members(role)` + `round_acl` (default **private**; explicit shares) + `access_audit` for owner cross-user reads + account **deletion** + session/token **revocation**.
- **Per-user backend addressing & scoped tokens:** the iOS app addresses a **per-user scope** (not one global admin token). `sessions` issue **short-lived scoped tokens** (TTL + refresh + revocation). `[Codex][verified]` The **watch** gets a **short-lived round/user-scoped device token — never the global admin token** (today `WatchEventBridge.swift:333` pushes `config["adminToken"]` to the watch; this is the **P1-1** hole). `[Codex]` `devices.install_uuid` replaces the role-string `clientId` so two phones don't collide.

## 6. Garmin integration — per-account, refactored

`[Codex][verified]` Today the connector **mutates module globals** to bind paths per run (`garmin_cn.py:67` rebinds `fetch_module.TOKEN_DIR/COOKIE_FILE/DATA_DIR`), and a **global lock** serialises all syncs (`main.py:1016`) because concurrent runs would cross-contaminate. This cannot become N users as-is.

- `garmin_accounts` + `garmin_session_secrets` (encrypted per account).
- Refactor fetch to **accept an explicit session object** and **emit raw payloads** → `raw_garmin_*`, **not** write `data/scorecards`.
- A **job worker**: one advisory lock **per `garmin_account_id`**, jittered schedules, backoff, the `garmin_accounts.status` states.
- Per-account Playwright profiles (`profiles/garmin/<account_id>`) only as a **fallback**, concurrency-limited.
- `[Codex]` Prefer **user-assisted login / cookie capture** (iOS or web flow) over storing Garmin passwords. CN re-auth may need SMS/captcha → surface `reauth_required`.

## 7. Course catalog — shared, versioned, two-tier

- **Lightweight catalog (anonymous → Postgres):** from search (`course_search.py`: globalId/name/holes/province/city) **+ a per-course release hydration** (`inspect_courseview_release.py`) for `course_lat/lon`, per-hole `lat/lon/par/handicap/yardage`, `raster_url`, `release_version/id`. `[Codex][verified]` lat/lon is **not** in the search — it needs the release fetch (still anonymous, one cheap call/course). Crawl **China-wide (`中国境内`)** for the lightweight catalog (owner decision) — a **rate-limited, incremental, resumable queue** with backoff (the search is name-query only, no clean bulk endpoint), ToS-aware. **Enables "start a round near me"** by `course_lat/lon`.
- **Heavy geometry (artifacts on disk + DB metadata):** Draco meshes, hazards, elevation. Decode = heavy node/Draco subprocess **+ a Garmin credential**. **On-demand** for nearby / played / prepared courses.
- **Version model:** rounds reference `course_version_id` (per **segment** for composite); a new Garmin map never reinterprets old rounds. Cron freshness by `release_version`/`release_id` → re-pull on bump → surface "map updated".
- `[Codex][verified]` **Elevation already exists.** `ai_caddie/geometry/elevation.py` reads mesh `y` (terrain elevation, metres) for PlaysLike (±yd) with **no external DEM**, wired into `course_prep.py`. The **Phase-0 spike validates the existing mesh-`y` reliability/coverage** (and the 8 unused CourseView fields — GPS, `unknown_10`, tee gender/index, raster thumbnails, Rough/PlayableBounds, foliage) — it does **not** ask whether elevation exists.

## 8. Migration — strangler (not indefinite dual-write)

1. Stand up the DB (identity + raw + canonical + course + conflict tables).
2. **Backfill** filesystem → raw + canonical, preserving original path/source as **provenance** (`round_sources`). `[Codex]` hydrate **minimal/placeholder course_versions first** so canonical rounds can reference one.
3. Read APIs → DB **behind a feature flag**; **parity-compare** DB vs filesystem output.
4. **Bridge:** old Garmin CLI keeps writing files briefly, then import → DB; **new** Apple/watch ingest writes **DB-first**.
5. `[Codex][verified]` Legacy engines still want Garmin-shaped files (`round_ingest.py` writes them) → **generate compat files from the DB**, don't dual-write from clients.
6. Cut reads to DB; retire filesystem writes.

## 9. Cross-cutting (designed, not just named)

- `[Codex][verified]` **iOS offline store** is one namespace (`OfflineStore.swift:124`, single `events.jsonl` + one pending-media index) → **per-user namespaces** keyed by `user_id`+`install_uuid`, else account-switch uploads the wrong log.
- `[Codex][verified]` **Round IDs = user-scoped UUIDs** (today `scorecard.id` / client-chosen `roundId` collide across players — the generalized iOS **P1-3**).
- **Conflicts** persisted (the §4 tables) + reviewed for score/penalty/putt/club across watch↔phone↔Garmin.
- **Observability:** per-`garmin_account` sync status/auth-failures/HTTP errors, geometry-decode queue health, migration parity, event-finalization failures, artifact cache hit rate, `access_audit`.
- **Backups & deletion (designed now):** Postgres backup **+** the blob store (geometry/media/raw protobufs); **per-user deletion** spans Postgres rows, blobs, `garmin_session_secrets`, media, logs, backups.

## 10. Phasing

`[Codex]` resolved the spike/schema contradiction (old v1 finalized course schema in Phase 2 but gated the spike to Phase 8) by adding **Phase 0**, and expanded Phases 1–2:

0. **Spike + inventories:** CourseView/elevation field dictionary (validate mesh-`y`) **+ an endpoint-by-endpoint auth/route migration matrix** (every mobile/history/media/report/Garmin route).
1. **Identity:** Apple sign-in + `families/users/devices/sessions/round_acl/access_audit` + **legacy `me`/`p_*` migration** + scoped device/watch tokens.
2. **Schema:** raw + canonical + course_versions **+ conflicts/corrections/ACL/media/clubs/segments** + projection-run metadata.
3. **Backfill** filesystem → DB (placeholder course_versions first).
4. **Lightweight course catalog** + location-based "start a round."
5. **Apple-Watch-native ingest** → DB (finalization + conflict persistence; emits compat files).
6. **Garmin → per-account worker** (owner first).
7. **Add family Garmin accounts.**
8. **Heavy geometry crawl/refresh** (last).

Each phase = its own spec → plan → implementation; 0–3 are the foundation.

## 11. Decisions (resolved 2026-06-26)

1. **Geometry-key credential:** ✅ **a dedicated course-data Garmin account** (family creds only as explicit break-glass). *Registration is a Phase-6/8 prerequisite and needs a CN phone + SMS OTP (+ Turnstile) — cannot be fully self-served; either a spare CN number is provided to drive the xvfb/Playwright registration on the homeserver, or the owner registers it once and hands over the credential.*
2. **Crawl scope:** ✅ **China-wide (`中国境内`) first** — but applies to the **lightweight catalog only** (anonymous search + per-course release hydration is cheap enough to crawl CN-wide with a rate-limited, incremental, resumable queue). **Heavy geometry stays on-demand** (nearby / played / prepared), never bulk-all-CN. International is out of scope for now.
3. **Elevation/DEM:** ✅ **investigate the data structures first** (Phase 0). Defer any external DEM; do **not** defer the mesh-`y` validation spike — the field dictionary + mesh-`y` reliability/coverage are part of Phase 0.
4. **Apple-native rounds → Garmin:** ✅ **strictly one-way (no write-back)** for now — Garmin is import-only. Revisit a future write-back only if explicitly needed later.

## 12. Out of scope (now)

Public/stranger SaaS · non-Apple identity (Google) · external DEM sourcing · pushing Apple rounds back to Garmin · the in-flight remediation debt (God-unit decomposition, marker-anchored `repo_root()`).
