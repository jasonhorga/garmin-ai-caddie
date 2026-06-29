# AI Caddie — Product Manual & Design-Implementation Doc

*2026-06-29. Covers the three surfaces (web dashboard, iOS phone app, Apple Watch app), the four user cases, every screen, what's implemented today, and a Garmin-comparison roadmap. Screens are captured reproducibly from the design-snapshot CI (iOS/Watch) and a new web screenshot harness (mock-data, ungated) — see "Test/screenshot environment" below.*

---

## 1. What the product is

A **multi-user / family golf app**: an iOS phone app + an Apple Watch app + a web dashboard, backed by a FastAPI service. It imports the owner's Garmin golf data (CN web cookie) and lets the whole family use it with **isolated per-player data**. The intelligence layer (hole maps, green distances, hazard carries, slope, and an AI caddie) is **course-keyed**, so it serves any player on a course we have geometry for — the caddie/decision engine is arguably richer than Garmin's Virtual Caddie.

### The four user cases
- **(i) Owner with Garmin** — full sync: measured club distances, shot-scatter maps, GIR/FIR stats, Garmin AutoShot tracks, the full caddie. *Strongest experience today.*
- **(ii) Garmin family member (their own Garmin)** — **most under-served**: per-member Garmin binding doesn't exist yet, so their watch data can't be ingested and they fall back to the manual path (looking identical to a non-Garmin member). *Highest-leverage fix.*
- **(iii) Non-Garmin member (manual phone/watch logging)** — functional but lossy: logs rounds + sets a club bag, gets the geometry caddie where coverage exists, but no GIR/FIR, no measured club distances (despite logging shots), no shot scatter, a weaker caddie, and every shot is a manual tap.
- **(iv) Watch-only quick round** — thinnest: clean manual scoring, but course-agnostic (no distances/map/hazards/caddie unless the phone coordinates), no live GPS distance, no AutoShot, no hole map.

---

## 2. Surfaces & screen inventory

*(Screenshots are reproducible — iOS/Watch from the native-mobile design-snapshot CI artifacts; web from the new screenshot harness. Image files referenced are attached alongside this doc / served on the review URL.)*

### Apple Watch (12 screens) — `mobile/ios/AICaddieWatch`
`watch-round-home` (course·nine, hole·par·distance, score, big 记这一洞, prev/next/list/结束 + crown pips) · `watch-caddie-glance` (front/中/back green distances + **坡度+N码 slope** + club rec + hazard avoid + aim + strategy + confidence — *exceeds Garmin's watch*) · `watch-caddie-options` · `watch-hazards` · `watch-hole-select` · `watch-menu` · `watch-score-hole` · `watch-scorecard` · `watch-finish-round` · `watch-start` · `watch-container-home/scoring`.
**Notable:** real, feature-rich AI-caddie glance. **Gaps:** no CoreLocation (no live distance), only an 18-pip ring (no hole/green vector), course data is phone-pushed (dies offline).

### iOS phone (15 screens) — `mobile/ios/AICaddie`
`full-home` / `full-home-active` (round hub) · `full-start` (start a round) · `round-home` · `live-hole` / `full-hole` (in-round: green distance bar, caddie focus card, club strip, save hole) · `caddie-plan` (options table + avoid zones) · `hole-map` (the per-hole map) · `course-detail` / `full-prep-picker` (备战) · `stats` · `recent-review` / `full-review` (round 复盘) · `club-settings` (the club bag editor — *just shipped, with per-club distance*) · `dark-fixed` (dark mode).
**Notable:** the hole-map design-snapshot is schematic (a fairway strip + green circle); the real app renders actual CourseView geometry — the live-hole + caddie screens are the rich surface.

### Web dashboard — `web_v2`
概览(overview) · 历史(history) · 趋势(trends) · 强弱分析(strengths — per-club/per-hole/issues) · 备战(prep landing) + 备战详情(interactive hole map w/ draggable ball + shot dots, hazard labels) · 实战(live caddie sandbox + full tools) · 设置: 同步与数据健康 / 球员管理(members) / **球包管理(the new club-bag editor + member picker)** / 订正 / 后端配置.
**Notable:** owner-admin dashboard. The club-bag editor is owner-only (members can't yet edit on web — see A5). Slope (`playsLike.deltaYd`) now renders on the prep hole card (B7, fixed this pass).

---

## 3. Garmin feature → our status

Surfaces: **BE**=backend · **W**=web · **P**=phone · **⌚**=watch. "Member?" = usable by a non-Garmin member.

| Garmin feature | What we have | Surfaces | Member? |
|---|---|---|---|
| Course view / hole map | Top-down render from CourseView meshes (`hole_render.render_hole`); web interactive map w/ draggable ball + shot dots; phone Canvas route+pin | BE,W,P | **Yes** (course-keyed) |
| Green F/M/B + pin | F/M/B computed **from the tee** (static, not live); phone header + watch glance; web shows only single "到果岭"; **no pin selection** | BE,P,⌚ | Yes |
| Hazard carry / layup | water-carry + bunker intervals, carryToFront/Clear, avoidZones; web labels; watch hazard view; **no explicit "layup-to-X"** | BE,W,P,⌚ | Yes |
| GPS rangefinder (live) | only haversine on client-supplied GPS; phone GPS **geotags shots at save only**; F/M/B never recomputed; **watch has no CoreLocation** | BE math only | **No live recompute** |
| AutoShot / shot tracking | stores Garmin's autoShotType; owner shot-scatter; manual per-shot tap log; post-round map. **No auto swing detection** | BE,W,P | scatter=**owner-only**; manual=yes |
| Club bag + per-club distances | effective bag manual>garmin>empty; ladder from history medians (**owner-only**) or typed/catalog default (member); phone+web editors | BE,W,P | bag=yes; measured dist=**owner-only** |
| Digital scorecard (FIR/GIR/putts) | Garmin → fir/gir/putts; **manual ingest = strokes+putts only**; web grid, phone steppers, watch scorecard | BE,W,P,⌚ | scores=yes; **GIR/FIR=owner-only** |
| Round stats / SG | WHS handicap, per-club p10/p90, per-hole, per-course, trends; **no true strokes-gained-to-baseline** | BE,W,P | Yes (limited) |
| Practice / driving range | **none** | — | n/a |
| PlaysLike (slope/wind) | slope ±yd from mesh (no DEM); phone+watch tile + **now web** (B7); **wind: no carry math** | BE,W,P,⌚ | slope=yes; wind=owner/none |
| Caddie / Virtual Caddie | deterministic decision engine (landing windows, risk, sequences, expected strokes) + LLM context; safe/stock/attack; **exceeds Garmin** | BE,W,P,⌚ | Yes (weaker: no weather/vision) |
| Manual round ingest | per-player events → Garmin-isomorphic scorecards+shots; captures per-shot club+GPS; web/phone/watch | BE,W,P,⌚ | **Yes** (primary member path) |

---

## 4. Roadmap — prioritized gaps

### Type A — multi-user-exposed ("the club-bag pattern repeating")
| ID | Gap | User case | Severity | Effort | What's needed |
|---|---|---|---|---|---|
| **A1** | **Per-member Garmin self-binding / sync** | (ii) | HIGH | LARGE | Per-member Garmin connect (deferred Phase B) writing into `data/players/<id>/{scorecards,shots,club_bag}`; couples to Sign-in-with-Apple. Root cause that makes (ii) collapse into (iii). |
| **A2** | GIR / fairway absent for manual rounds | (iii),(iv) | MED-HIGH | MED | Derive GIR/fairway server-side from the already-logged per-shot GPS + green/fairway geometry, or add explicit taps. |
| **A3** | Measured per-club distances owner-only | (iii) | MED | MED | Player-scope `build_club_profiles`/`scorecard_files`/`load_shot_file` to read `data/players/<id>/shots`; feed member medians into `effective_club_ladder`. |
| **A4** | Shot scatter owner-only in prep | (iii) | MED | MED | Same player-scoping as A3 (shared fix) for `shot_projection.shots_for_hole`. |
| **A5** | Web club bag blocks members | (iii) on web | MED | SMALL | Wire the web editor to the member bearer for their own id (the API already allows self-or-admin). |
| **A6** | Weather/wind + vision owner-only → weaker member caddie | (iii) | LOW-MED | MED | Make weather per-player/course-cached; allow member vision findings. |
| **A7** | Legacy `/history/clubs/bag` dead for members | (iii) | LOW | SMALL | Retire/redirect to the effective-bag endpoint. |

> **The throughline:** A2+A3+A4 are ONE change family — player-scope the legacy shot/profile loaders so a member's logged data finally feeds their own distances, stats, and maps. Highest value-per-effort of the Type-A set.

### Type B — missing Garmin features
| ID | Gap | Severity | Effort | What's needed |
|---|---|---|---|---|
| **B1** | **Live GPS rangefinder** (continuous F/M/B) | HIGH | MED(phone)/LARGE(watch) | Recompute F/M/B from live GPS vs green geometry; add CoreLocation to the watch. *The defining Garmin-watch behavior.* |
| **B2** | **AutoShot** (auto swing detection) | HIGH | LARGE | Watch accelerometer swing-detection → auto GPS waypoint → shot event into the existing ingest pipeline (matches the roadmap's auto-shot-tracking vision). |
| **B3** | Watch hole map / green shape | MED | MED | Render a simplified hole/green vector on the watch from the GeoJSON DTO we already produce. |
| **B4** | Wind-adjusted PlaysLike + live wind | MED | MED | wind→carry-yards math in the decision engine + auto weather fetch in live play. |
| **B5** | Watch standalone course data (offline) | MED | MED-LARGE | Download course geometry/prep to the watch at round start. |
| **B6** | Pin position selection | LOW-MED | SMALL | Front/center/back pin toggle → one adjusted target (data present). |
| **B7** | Slope not on web | LOW | SMALL ✅ **(done this pass)** | ~~Render the existing `playsLike.deltaYd` in the web prep hole card.~~ Shipped — `坡度 +N码 · 上坡/下坡`. |
| **B8** | Strokes-gained analysis | LOW-MED | LARGE | A baseline model (OTT/APP/ATG/Putt). |
| **B9** | Practice / driving-range mode | LOW | LARGE | New feature; lowest priority. |

---

## 5. Fixes done in this pass

I screenshotted **every** screen (web 15 / iOS 15 / watch 12) and compared page-by-page to Garmin. The product is in good shape — most screens are clean; the apparent "empty" web charts (one-point trend line, one-bubble course map) are **mock-data artifacts** of the test harness, not product bugs (real data fills them). Two safe, page-level fixes shipped; the big Type-A/B items in §4 stay roadmap items for you to greenlight.

**Shipped:**
- **B7 — Slope now on the web prep hole card.** The per-hole `playsLike.deltaYd` (already in the prep payload, already shown on phone + watch) now renders on web 备战→逐洞攻略 as `坡度 +N码 · 上坡/下坡`, matching the other surfaces. *(this PR — `web_v2/src/components/PrepHoleCard.tsx`, `types.ts`)*
- **Watch de-English / localization.** The screenshot review caught raw English on the Apple Watch: the caddie glance rendered confidence as **`high`** and pin status as **`pin ready`** (closed enums leaking straight through). Localized to Chinese across the watch caddie glance, the phone-pushed companion glance, and the quick-input screen — `高/中/低把握`, `旗位就绪 / 待选旗位`, `手机已连/未连`, `待传/已同步`, `距/杆/推/罚/球杆/保存/输入` — mirroring the phone's `zhCaddieConfidence`. *(PR #188 — `mobile/ios/AICaddieWatch/*` + contract sync)*

**Reviewed and intentionally NOT changed (logged, not blind-fixed):**
- **Web hole-map hazard labels can overlap** on tightly-spaced hazards (in the mock geometry, `沙49y` sits over the green and water/bunker labels stack). The SVG labels have no collision-avoidance. Deferred rather than speculatively repositioned, because the mock geometry likely exaggerates it vs the real CourseView render — wants verification on real data, then possibly a small "labels → legend below the map" relabel. *On the exact "看球洞的位置" surface you flagged, so first candidate for the next pass.*
- **Watch distance unit `m` vs the app-wide `码`.** Round-home / hole / input show meters while the caddie glance (and the whole rest of the app) use yards. A real inconsistency, but flipping it touches input semantics and is a product call (CN golfers often read meters) — deferred to a focused PR. `Par` (a cross-surface convention) and `AI Caddie` (brand) were left as-is by design.

> **Net:** the safe fixes are in; the remaining "该修的" are either strategic (the §4 roadmap, needs your greenlight) or want real-data verification before touching (the two items above).

---

## 6. Test / screenshot environment (so this is reproducible)

- **iOS phone:** `mobile/ios/AICaddieTests/DesignSnapshotTests.swift` renders each screen via ImageRenderer → `design-snapshots` CI artifact (15 screens).
- **Apple Watch:** `mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift` → `watch-snapshots` CI artifact (12 screens).
- **Web:** a new Playwright harness (`web_v2/e2e/screenshots.spec.ts`) on the **ungated :5174 dev server with mocked API** — renders every web page to a screenshot without the production link-gate or a live backend. **Runs on the homeserver only** (never the 2GB dev box). This is the environment that lets every page be reviewed + compared to Garmin repeatably.
