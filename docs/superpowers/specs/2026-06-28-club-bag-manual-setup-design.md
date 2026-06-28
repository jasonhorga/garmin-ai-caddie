# Club-bag manual setup — design

**Status:** design, approved-shape (2026-06-28). Branch `superpowers/club-bag-manual-backend` off `integration/v2` @ 0a2a7d9. Part of the [multi-user / family redesign](2026-06-26-phase0-findings.md).

## Goal

Let any player **set up their own club bag** (modeled on the Garmin app) instead of being limited to the Garmin-synced bag. The driving need: **non-Garmin family members** (no Garmin sync) currently have no bag at all — the caddie falls back to a generic 13-club `DEFAULT_LADDER` with no personalized distances. A manual bag lets them pick their clubs and (optionally) enter a carry distance per club, so the caddie's club selection is personalized for them too. Garmin members can also manually override/tweak their synced bag.

## Context / current state (reconnaissance)

- **Backend bag is read-only.** `GET /api/v2/history/clubs/bag` → `build_club_bag_response` (owner-only; non-owner → `found=false`). The bag JSON (`ai-caddie-club-bag-v1`: `id, clubTypeId, customName, typeName, loftAngle, retired, deleted`) is written **only** by the Garmin sync pipeline (`fetch.fetch_clubs`). There is **no write/edit endpoint**. Per-player isolation IS in place: owner `data/club_bag.json`, member `data/players/<id>/club_bag.json` (`core/data.load_club_bag(player_id)`).
- **iOS already has a club-selection UI** — `ClubSettingsView` (toggle list over `ClubCatalog.all` ~30 clubs, grouped 木/混合/铁/挖起/推, shows per-club distance from history, "用 Garmin 球包重置"). But its edits are **local-only** (`ClubBagStore` UserDefaults), never persisted to the server. iOS taxonomy: `garminClubTypeZh` (1–23 → zh), `zhClubName`, degree wedges + 七号木 as catalog entries.
- **Web has no club-bag UI** (its "clubs" page is a shot-history stats view) and the web client only speaks the admin token (no member-bearer path).
- **Caddie distances** come from shot history (`build_club_profiles` → `club_ladder`), restricted to the in-use bag (`restrict_to_bag` → `in_use_canonical_names` → `load_club_bag`). A non-owner with no history gets the generic `DEFAULT_LADDER` (`course_prep.py`: `1W..58°`, 13 clubs).

## Key reality that shapes phasing

The multi-user **backend** is live + deployed, but **neither client has member sign-in yet** — iOS and web both currently authenticate as the OWNER (admin token). Member Apple sign-in is a separate deferred iOS slice. **Therefore:**
- The backend write endpoint is **member-scoped** (`acting == OWNER_ID or acting == {id}`), so the **OWNER can set up any family member's bag now** (acts-for-any), which delivers the "non-Garmin members get clubs" goal **without** waiting on member sign-in.
- Members editing their **own** bag unlocks when the deferred sign-in slice lands (no backend change needed then).

## Decomposition (each slice = its own plan → PR)

1. **Backend slice (THIS design's first implementation cycle):** manual-bag storage + read/write endpoints + caddie consumption of the effective bag. Foundational, independently testable + deployable; usable immediately by the owner (admin token) for self and any member.
2. **iOS slice:** wire the existing `ClubSettingsView` to persist via the backend (replace UserDefaults-only) + add the optional per-club distance field. (macOS CI.)
3. **Web slice:** new club-bag editor page in settings + an owner-only member picker (so the owner sets up family bags from web). (web.)

The rest of this doc is the full-feature design; the backend slice is implemented first.

## Data model

### Manual bag (new, per player, parallel to the synced bag)

Stored at `data/players/<id>/club_bag_manual.json` (member) / `data/club_bag_manual.json` (owner) — a resolver `manual_club_bag_file(player_id)` mirroring `load_club_bag`'s owner/member split.

```json
{
  "schema": "ai-caddie-club-bag-manual-v1",
  "clubs": [
    {"token": "driver",  "customName": null,   "distanceM": 205},
    {"token": "iron7",   "customName": null,   "distanceM": 130},
    {"token": "wedge54", "customName": "54度", "distanceM": null}
  ],
  "updatedAt": "2026-06-28T10:00:00Z"
}
```

- **`token`** — a stable canonical token (NOT the Garmin numeric instance id, which non-Garmin clubs lack). The token vocabulary is a shared backend **`CLUB_CATALOG`** that mirrors iOS `ClubCatalog.all`: the `_CLUBTYPE_CANON` values (`driver, wood3, wood5, hybrid1..6, iron1..9, pw, gw, sw, lw, putter`) plus `wood7` and degree wedges (`wedge50, wedge52, wedge54, wedge56, wedge58, wedge60`). These are exactly the tokens `canonical_club_name()` already emits, so the manual bag plugs into the existing intersection logic with no new normalization. Each catalog entry carries `{token, zhName, category, defaultDistanceM}`.
- **`customName`** — optional display override (e.g. a club's nickname). Does not affect caddie logic.
- **`distanceM`** — optional carry distance in metres. `null` = use the catalog default / shot history. The UI prefills the catalog `defaultDistanceM` (derived once from `DEFAULT_LADDER` via `canonical_club_name`, e.g. `1W→driver→200`); tokens with no `DEFAULT_LADDER` entry prefill `null` (user enters).

### Effective bag resolution (mirrors iOS `effectiveBag`)

`effective_club_bag(player_id)` → **manual bag if present, else the Garmin-synced bag, else empty.** This single resolver is what the served response and the caddie both read.

## Backend API (member-scoped, mirrors `POST /api/v2/players/{id}/sync/garmin`)

- **`GET /api/v2/players/{id}/clubs/bag`** — returns the **effective** bag: `{schema, source: "manual"|"garmin"|"none", found, clubs: [{token, zhName, customName, clubTypeId|null, distanceM, distanceSource: "manual"|"history"|"default"|null}]}`. Member-scoped read (`acting == OWNER_ID or acting == {id}`; else 403).
- **The legacy `GET /api/v2/history/clubs/bag` stays UNCHANGED** — owner-self, the **synced Garmin bag only** (schema `ai-caddie-club-bag-v1`, no manual). It is the "real Garmin bag" source the iOS app's real-vs-manual distinction (`ClubBagStore.realBag` / "用 Garmin 球包重置") depends on, so it must NOT start returning the manual/effective bag. Clients read the synced bag from this legacy endpoint and the effective/manual bag from the new per-player endpoint.
- **`PUT /api/v2/players/{id}/clubs/bag`** — write the player's **manual** bag. Body = the manual-bag clubs (`[{token, customName?, distanceM?}]`). Validates every `token` against `CLUB_CATALOG` (422 on unknown token) and `distanceM` is a sane positive number or null. Guard: `acting = Depends(current_player_id); if acting != OWNER_ID and acting != {id}: 403` — so the owner (admin token) may write any player's bag, a member only their own. Writes atomically to that player's partition; invalidates that player's caches (`stats_cache.clear(player_id)` + `prep_cache`). A `DELETE` (or `PUT` with empty clubs) clears the manual bag → effective falls back to the synced bag ("reset to Garmin").

## Caddie consumption (the payoff — personalized ladder for manual bags)

- `in_use_canonical_names(player_id)` and `restrict_to_bag(..., player_id)` read the **effective** bag (so a manual bag's selected tokens drive the filter), via `effective_club_bag`.
- **Ladder:** a new `effective_club_ladder(player_id)` returns, when the player has a manual bag, a ladder built **from the manual bag**: for each selected token, distance = `distanceM` ?? `CLUB_CATALOG[token].defaultDistanceM` ?? skip, sorted descending. The member-route ladder gating (`server_v2/prep_tips.py`, `mobile_live._course_prep_package`, the `/course/{id}/prep` route) becomes: **manual-bag ladder if the player has one, else** the current behavior (owner → `club_ladder()` from history; other non-owner → generic `DEFAULT_LADDER`). This closes the "members always get DEFAULT_LADDER" gap once they've set a manual bag, and stays byte-for-byte for players with no manual bag.

## Error handling / validation

- Unknown `token` → 422 (never silently dropped, so the client surfaces a real error).
- `distanceM` out of range (≤0 or absurd, e.g. >400m) → 422.
- Corrupt/missing manual file → treated as "no manual bag" (falls back to synced), never a 500 (mirror `load_club_bag`'s defensive read).
- Owner byte-for-byte: a player with NO manual bag sees identical behavior to today (served bag = synced; ladder = history/default).

## Storage / isolation

Manual bag lives in the player's existing partition (`data/players/<id>/`), so it inherits the multi-user isolation already in place. The owner's manual bag at `data/club_bag_manual.json` is distinct from the synced `data/club_bag.json`. No new volume/migration; it is a JSON file like the synced bag.

## Backend testing (stdlib unittest, `AI_CADDIE_DATA_MODE=fixture` gate)

- **Storage round-trip:** PUT a manual bag → `manual_club_bag_file(player_id)` written; GET returns it with `source="manual"`.
- **Effective resolution:** manual present → manual wins; manual absent + synced present → synced (`source="garmin"`); neither → `found=false` (`source="none"`).
- **Member-scoped auth:** a member writes/reads only their own `{id}`; member→other/owner `{id}` → 403; owner (admin) writes/reads any `{id}` (the acts-for-any path).
- **Validation:** unknown token → 422; bad `distanceM` → 422; corrupt file → falls back, no 500.
- **Caddie payoff:** a non-Garmin member with a manual bag (selected clubs + distances) gets a ladder built from the manual bag (not `DEFAULT_LADDER`), restricted to the selected clubs; assert the personalized distances appear and non-selected clubs are excluded.
- **Owner byte-for-byte:** a player with no manual bag → served bag + ladder identical to today; existing `test_club_bag` / `test_prep_tips_api` / aggregator-isolation tests stay green.
- **Catalog:** every `DEFAULT_LADDER` key normalizes to a `CLUB_CATALOG` token; catalog defaults derive from `DEFAULT_LADDER` deterministically.

## Out of scope (this slice)

- iOS UI + web UI (separate slices, above).
- Member Apple sign-in in the clients (deferred iOS slice) — until then the owner acts-for-any.
- Per-club richer modeling (loft, multiple shafts) — keep to type/name/distance, matching the Garmin app's basic bag.
- Auto-learning manual distances from rounds (the synced/history path already does this; manual distance is a user-set value).

## Review

Subagent-driven backend implementation + the independent Codex whole-branch review + a final Claude review (auth scoping, the effective-bag resolver, owner byte-for-byte, and the catalog/token validation are the scrutiny points). Merge only on green CI + reviews clear → `integration/v2` (no `--delete-branch`); then deploy to the homeserver and re-verify, before starting the iOS/web slices.
