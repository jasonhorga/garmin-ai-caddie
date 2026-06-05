# Course Prep On Device — Phone + Watch Design

Date: 2026-05-30
Status: design (for review before implementation)

## Can phone + watch be used now? (honest state)

The apps are **real and build green in CI**, the backend now serves **real data**, and the
phone↔watch↔server contract is **complete** — but they are not yet **installed on your devices
or pointed at a live backend**, and the pretty pre-round hole maps are **not wired into them yet**.

What exists today:
- **iOS app** (`mobile/ios/AICaddie`, SwiftUI): `StartRoundView`, `CurrentHoleView`, `CaddiePlanView`,
  `RoundHomeView`, `RecentRoundReviewView`, `MediaCaptureView`, Garmin session capture; services for
  offline store, sync, **offline caddie-decision evaluator**, location, watch bridge, media upload.
- **Watch app** (`AICaddieWatch`): `WatchHoleView`, `WatchCaddieGlanceView`, `WatchInputView`, sync client.
- **Backend**: `/api/v2/mobile/courses/{gid}/package`, `…/rounds/{id}/package`, live events
  (post/replay/ack), reconciliation. The `LiveRoundPackage` already carries per-hole `{hole, par,
  target, strategyMode ∈ protect_score|stock|attack, distanceToPinM, geometry}`.
- CI compiles + unit-tests both on macOS (`xcodegen generate` → `AICaddieNative.xcodeproj` →
  `xcodebuild test` on iOS/watch simulators). Linux verifies the JSON contracts.

The three gaps before you can actually use them on the course:
1. **Install (no Mac needed — via CI/CD).** GitHub `macos-15` runners + **fastlane** + an
   **App Store Connect API key** (GitHub secrets) build, sign, and ship to **TestFlight** — exactly
   how the sibling `gomoku` repo does it (`macos-cd.yml` + `signing-bootstrap.yml`, `fastlane` sign/
   notarize/distribute). This repo already builds native on macOS CI (green); it only needs the
   **sign + TestFlight CD job added**. You install from TestFlight on your phone/watch.
2. **Reachable backend (deployable directly).** `server_v2` has `fly.toml` / `render.yaml` /
   `Dockerfile` — deploy it so the phone can reach `/api/v2/...`.
3. **Course prep content** — the package isn't yet populated with the real **route / hazard carries /
   styled hole map / club+target** from the prototype; that is the feature work below (Phase 4).

So: **the plumbing is ready; the pre-round caddie experience, the iOS CD job, and the backend deploy
are what remain.** Phase 4 closes all three (feature + CD + deploy) with no physical Mac.

## Goal

The pre-round course review (per-hole par, styled hole map, route + hazard carries, recommended
club/target using the player's real distances) usable **on the phone** to browse all holes before a
round (offline), and **on the watch** as a per-hole on-course card. Fed by real Garmin geometry +
the player's own scorecards/club model. One source of truth, three surfaces (web/phone/watch).

## Key decision: how the hole map reaches the device

Two options for the styled top-down hole image (currently `/tmp/render_hole.py`, PIL):

- **A — server-rendered image (recommended).** Engine renders the hole (meshes → styled PNG/SVG) and
  the prep DTO carries an image URL/bytes + a small overlay model (route polyline, tee/green, hazard
  carries, landing) in normalized coords. Phone/web just display the image + draw the interactive
  overlay (draggable ball, club chips) from the overlay model. **Why:** the render logic already
  exists and is correct (corridor clip, mirror fix, water/trees); SwiftUI/React only do the light
  interactive layer; identical look on all three surfaces; offline = cache the image + overlay JSON.
- **B — ship geometry, draw natively.** Send raw meshes; SwiftUI/React redraw the hole. Prettier
  vector zoom, but reimplements the renderer twice (Swift + Canvas) — high cost, drift risk. **Rejected** for now.

Recommendation: **A**. Reuse the proven renderer server-side; keep clients thin.

## Architecture

```
ai_caddie/ (engine)
  course_prep.py        per-hole prep facts: par (course_reference), playing route, hazard carries,
                        recommended club + target/landing (decision.py + club model), difficulty
  hole_render.py        port of render_hole.py: meshes -> styled image + overlay model (route/haz/landing)
server_v2/
  /api/v2/mobile/courses/{gid}/package   <- enrich LiveRoundPackage with prep + map image/overlay
  /api/v2/geometry/hole/{gid}/{h}/map    <- already exists; returns image + overlay
  /api/v2/courses/{key}/prep             <- web prep DTO (all holes of a nine)
web_v2/ (React)         CoursePrepPage: nine selector -> per-hole card (image + interactive overlay + strategy)
mobile/ios/AICaddie/
  Views/CourseReviewView.swift           browse all holes (image + overlay + strategy), offline via OfflineStore
  (reuse CurrentHoleView/CaddiePlanView for the single-hole detail)
mobile/ios/AICaddieWatch/
  WatchHoleView                          per-hole card: par, target yds, club, carry, avoid (from synced package)
```

Data flow: `pipeline sync` → real scorecards/shots + `course_reference` par + geometry. Prep DTO =
par (played→official→estimate, labeled) + route/hazards (geometry) + club/target (decision + the
player's median distances) + rendered map. Cached on device for offline play.

### Reuse, don't rebuild
- `LiveRoundPackage` already has per-hole par/target/strategyMode → extend, don't replace.
- `OfflineStore` + the offline caddie evaluator already cache a package and decide without signal.
- `CaddiePlanView` already renders safe/stock/attack plans → feed it the real prep.
- The watch already has per-hole + glance views → feed `WatchHoleView` the prep card fields.

## Phasing
1. **Engine** — `course_prep.py` + `hole_render.py` (port the /tmp logic with tests on cached geometry).
2. **API** — enrich `/mobile/courses/{gid}/package` + add `/courses/{key}/prep`; contract tests.
3. **web_v2** — `CoursePrepPage` (folds the standalone `course_review/*.html` prototype in).
4. **iOS** — `CourseReviewView` (offline browse-all-holes) + wire into `StartRoundView`.
5. **Watch** — per-hole prep card fields in `WatchHoleView`.
6. **Deploy + CD (no Mac).** (a) Deploy `server_v2` via `fly.toml`/`render.yaml` so the phone can
   reach it. (b) Add an iOS **CD job** mirroring gomoku's `macos-cd.yml`: `macos-15` runner →
   `xcodegen` → `xcodebuild archive`/`exportArchive` → `fastlane` sign + TestFlight upload, using
   App Store Connect API-key GitHub secrets + a one-time `signing-bootstrap`. User installs via TestFlight.

## Non-goals
- Rebuilding the iOS/Watch apps (they exist) or the renderer (reuse server-side).
- Full live-scoring redesign (live capture already exists).
- App Store distribution (TestFlight/dev-install is enough for the user's own use).
