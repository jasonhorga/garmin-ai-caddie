# Card #438 — Watch hole root: S70 visual parity

#434 got the root's content right: the facts layer, one aim line, the club,
and no full route. The owner compared the root with the S70 hole view and found
ours too rough. S70 draws a yellow disc with a black arrow for the player, a
small square at the landing, an arc through it, and a small caddie icon with
the club. This card is the visual pass.

References (owner-viewed, official Garmin images):
- S70 hole view with caddie recommendation:
  `https://res.garmin.com/it-production/image/upload/v1679492352/Product_Images/en/products/010-02746-02/g/57145-3.jpg`
- S70 Virtual Caddie page (manual; item 3 is the dispersion box):
  `https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/Shared/GUID-77145969-CC31-4EDF-BE22-D211174B14D0-high.jpg`
- `docs/reviews/2026-07-16-s70-virtual-caddie-driver-arc-evidence.md`

Touches: `mobile/ios/AICaddieWatch/Views/WatchHoleMapView.swift`, `mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift`, `mobile/ios/AICaddieWatchTests/**`, `docs/design/2026-09-25-ui-redesign/README.md`, `tests/acceptance/test_card_438_watch_root_s70_visual_parity.py`, `.agent/contracts/card-438.md`

This is a Watch-only change: no backend, phone, web, contract or migration
change, and no pinned file. The PR touches `mobile/ios/**`, so it also needs the
`native-mobile` check green on its head. `tests/test_mobile_contracts.py` needs
no change: none of its assertions reads the code this card replaces.

Acceptance tests: `tests/acceptance/test_card_438_watch_root_s70_visual_parity.py`
has 8 tests, one per goal. G7's test is `# pinned`. The module imports card
#434's Swift lexer and declaration parser, which #434's pinned self-check
covers.

## How this is tested

The Watch app builds only on macOS, and these acceptance tests run on Linux.
Each test runs `git ls-files` in a subprocess and reads the tracked Swift
sources and the README structurally. Comments are ignored, and string contents
are masked wherever code structure is analysed.

The agenthub gate also runs Swift mutants against the real native tests
(`agenthub-native-mutant.yml`). A mutant counts as caught only when a native
test fails. So each goal also requires a native test that renders the
production `WatchHoleMapView` with `ImageRenderer` and samples its pixels at
positions the production seams compute. If a required native test fails on the
new Swift code, fix the code, not the test.

Keep every name below exactly as written; the acceptance module looks for
these names.

## Interface

### `WatchHoleMapView.swift`

1. **`WatchRootShotMarks`** is a new internal `struct WatchRootShotMarks: Equatable`.
   It holds the S70 marks for one shot, in canvas points.

   ```swift
   /// S70 root marks (#438) for one shot, in canvas points. The square's depth along the aim is the
   /// real p10–p90 carry depth. We have no lateral dispersion data, so its width equals its depth: it is
   /// not a lateral dispersion.
   struct WatchRootShotMarks: Equatable {
       static let playerDiscRadius: CGFloat = 7      // 6...8
       static let minimumBoxSide: CGFloat = 14       // 12...16
       static let maximumBoxSide: CGFloat = 28       // 26...30
       static let arcHalfAngleDegrees: CGFloat = 25  // 20...30

       let player: CGPoint
       let landing: CGPoint
       /// Radians, atan2(landing.y - player.y, landing.x - player.x) in canvas space.
       let heading: CGFloat
       /// nil when there is no real p10/p90 (a prepared plan): then there is no square.
       let boxSide: CGFloat?
       let aimStart: CGPoint
       let aimEnd: CGPoint
       let arcRadius: CGFloat

       static func resolve(
           player: CGPoint,
           landing: CGPoint,
           carryP10: CGPoint? = nil,
           carryP90: CGPoint? = nil
       ) -> WatchRootShotMarks?
   }
   ```

   - The stored fields include the seven above. No stored field name contains
     `width`, `depth`, `lateral` or `ellipse`: the square has one side length.
   - `resolve` returns nil when any input is not finite, or when
     `hypot(landing - player) <= 1`.
   - Let `d = hypot(landing - player)` and `u = (landing - player) / d`. Then:
     - `heading = atan2(u.y, u.x)` and `arcRadius = d`;
     - when both carry points are given,
       `boxSide = min(max(hypot(carryP90 - carryP10), minimumBoxSide), maximumBoxSide)`.
       When either is nil, `boxSide` is nil;
     - `aimStart = player + u * playerDiscRadius`;
     - `aimEnd = player + u * max(playerDiscRadius, d - (boxSide ?? 0) / 2)`.
       With a square, the line ends at its near edge; without one, at the
       landing. When the square reaches the disc, the length is 0 and no line
       is drawn.
   - The body of `resolve` names `minimumBoxSide`, `maximumBoxSide`,
     `playerDiscRadius`, `carryP10`, `carryP90` and `hypot(`.
   - A `//` comment block in the file says that the width equals the depth
     because there is no lateral data. It must use the words "lateral",
     "width" and "depth"; the doc comment above does.
   - No string literal in `WatchHoleMapView.swift` or
     `WatchRoundContainerView.swift` contains "lateral" or "横向". Nothing is
     labelled as lateral dispersion.

2. **`func canvasPoint(_ imagePoint: CGPoint, in size: CGSize) -> CGPoint`** is
   a new internal seam on `WatchHoleMapView`. Its body returns
   `anchors(size).t(imagePoint)`, the transform the canvas draws with. Native
   tests use it to find where a mark lands.

3. **`private func drawRootShotMarks(_ context: inout GraphicsContext, marks: WatchRootShotMarks)`**
   is the only place that draws the S70 marks.
   - **Square.** When `marks.boxSide` is non-nil, draw a `Path(roundedRect:`
     square of side `boxSide`. Centre it on `marks.landing` and rotate it so
     one pair of sides is perpendicular to the aim. Use a corner radius of
     about 3 pt.
     - Fill: white, opacity 0.15–0.35 (light and translucent).
     - Outline: white, opacity ≥ 0.85, line width 1.0–1.6.
   - **Arc.** Draw exactly one `.addArc(`:

     ```swift
     arc.addArc(center: marks.player, radius: marks.arcRadius,
                startAngle: .radians(Double(marks.heading) - Double(WatchRootShotMarks.arcHalfAngleDegrees) * .pi / 180),
                endAngle: .radians(Double(marks.heading) + Double(WatchRootShotMarks.arcHalfAngleDegrees) * .pi / 180),
                clockwise: false)
     ```

     Both angle arguments must name `heading` and `arcHalfAngleDegrees`
     directly. Stroke it white, opacity ≥ 0.85, line width 1.0–1.5.
   - **Aim line.** A path with `.move(to: marks.aimStart)` and
     `.addLine(to: marks.aimEnd)`, drawn only when the two points differ. Stroke
     it white, opacity ≥ 0.85, line width 1.2–1.6.
   - The function contains no `caddieGreen`, no `Path(ellipseIn:`, no
     `.addLine(to: marks.landing)` and no `.move(to: marks.player)`. That means
     no green dot, no ellipse, no line through the square and no line from the
     disc centre.

4. **`drawCurrentShot`.** On the resting root (`fullMap == false`), the
   current shot draws only through
   `WatchRootShotMarks.resolve(player: transform(layout.player), landing: transform(layout.target), carryP10: transform(layout.carryP10), carryP90: transform(layout.carryP90))`
   (one call in the function), then `drawRootShotMarks(`.
   - The diagonal p10 → target → p90 polyline, its end dots and the green
     target dot are no longer drawn on the root.
   - Full maps keep today's drawing: Touch Target, and the caddie page with its
     `dispersionOnly` overlay. The caddie page is unchanged.
   - The continuation gate from #434 stays as it is. Do not shadow `fullMap`
     in `drawMap` or `drawCurrentShot` (#434 G1).

5. **`drawPreparedPlan`** (the prepared Tee plan, which has no dispersion data):
   - draw through `WatchRootShotMarks.resolve(player: player, landing: target)`,
     with exactly the `player:` and `landing:` arguments and no carry
     arguments, then `drawRootShotMarks(`;
   - the result is the straight aim line and the arc, with no square;
   - drop the `addQuadCurve` first leg and the green landing dot;
   - keep every `carryP…` token out of the function, because #434's pinned G2
     check requires it.

6. **Player disc.** Add `private func drawPlayerDisc(_ context: inout GraphicsContext, at player: CGPoint, heading: CGFloat)`.
   - It draws a `Path(ellipseIn:` disc of radius
     `WatchRootShotMarks.playerDiscRadius`, filled with `golfYellow` (or
     `AICaddieDesignTokens.hudYellow`).
   - Over the disc goes a filled black (`.black`) navigation arrow, rotated to
     `heading`. Its tip lies at 0.55–0.85 × radius from the centre, and its
     half-width is at most 0.5 × radius.
   - A thin dark rim is allowed. Do not use `youBlue`.
   - In `drawMap`, the `.chevron` branch becomes:

     ```swift
     if !rangeUnavailable, playerMarker == .chevron {
         drawPlayerDisc(&context, at: player, heading: …)
     }
     ```

     Call it as `drawPlayerDisc(`, not `self.drawPlayerDisc(`. The
     `var chevron` path goes. The heading is `marks.heading` when the root
     draws marks (current shot or prepared plan); otherwise it is the
     direction from the player to the pin.
   - The disc is drawn after the marks, so the aim line starts at its edge.
   - `WatchPlayerMarkerStyle` keeps exactly `youDot` and `chevron`. Keep the
     case name `chevron`: #434's acceptance tests and the call sites name it.
     Update its doc comment to "S70 yellow disc with a black navigation arrow".
     `.youDot` is unchanged.

7. **Remaining-yard markers.** In `enum WatchHoleMapReferenceLayout`, add
   `static let remainingMarkerRadius: CGFloat` (4.75–6.0; about 2.5 × 2.1 =
   5.25) and `static let remainingMarkerOutlineWidth: CGFloat` (1.0–2.0).
   - `drawReferenceFacts` uses both constants by their full names
     (`WatchHoleMapReferenceLayout.remainingMarkerRadius`, …).
   - The outline is black (`.black`, opacity ≥ 0.85).
   - No `2.1` literal is left in the function. The colours (red 100 / white
     150 / blue 200) and `remainingYards = [100, 150, 200]` stay.

8. **Caddie chip.** It stays inline in the overlay's
   `if showTextOverlay, showCaddieRecommendation, showsRootCaddieChip {` block,
   and it is the only `"watch-plan-club-tag"` in the file.
   - It is a compact dark chip: a black capsule, opacity ≥ 0.6, with an
     optional thin white outline. Inside go
     `Image(systemName: "figure.golf")` (about 11–12 pt, white) and
     `Text(WatchClubDisplay.shortCode(caddieClub))` (about 13–15 pt, heavy
     rounded, white, `minimumScaleFactor`).
   - It uses no `AICaddieDesignTokens.hudGreen`, `caddieGreen` or `.green`.
   - Keep the `.highPriorityGesture(TapGesture().onEnded { onOpenCaddie() })`,
     `.accessibilityAction { onOpenCaddie() }`, label, value and identifier. It
     stays sized and positioned by `Self.rootCaddieChipFrame(in: size)`.
   - **Placement: the right side, smaller.** The card prefers the bottom centre
     if it fits, but it does not fit. The root's player sits at mid-width,
     level with the rail between the menu (≡) and + controls
     (`rootPlayerAnchorFraction`), so a bottom-centre chip would cover the
     player disc.
   - `rootCaddieChipFrame(in:)` therefore stays right of the player and above
     the rail, as today, but smaller: width 36–48 pt (today 50–56) and height
     20–26 pt (today 36). The existing
     `testRootCaddieChipStaysInsideTheRoundedSafeAreaOnEveryWatchFace` must
     keep passing.

### `WatchRoundContainerView.swift`

9. `holeMapView` keeps `playerMarker: .chevron`, `fullMap: false`,
   `interactionMode: .measure` and `onOpenCaddie: { model.openCaddie() }`.
   - `planTagTapTarget` keeps following
     `WatchHoleMapView.rootCaddieChipFrame(in:`. For a comfortable tap, it may
     expand that frame by up to 6 pt on each side, as long as it stays above
     the rail and right of the player disc.
   - No other container change is expected.

### Not changed

- The F/M/B facts column, Touch Targeting (two ranges), the caddie page
  (`optionMap`, Crown, `clubChain`), `999 码 · 等待定位` / `等待定位`, and the
  lightweight map facts (README §8).
- The Driver-distance arc (`drawReferenceFacts`) remains a separate fact. On
  the tee with a live recommendation, both arcs may show. The reviewer checks
  that they read clearly.
- All of card #434's acceptance tests must keep passing.

## Native tests (Codex writes them; `native-mobile` runs them)

They go under `mobile/ios/AICaddieWatchTests/` (any file), with exactly one
function of each name and no `XCTSkip…` or `XCTExpectFailure`. Mark them
`@MainActor` where `ImageRenderer` needs it. Write each case out, with no loop
over cases, because the checker counts assertions.

**Pixel-test recipe.**
- Render `WatchHoleMapView(` with `ImageRenderer`, `renderer.scale = 2`, dark
  colour scheme and `.watchSnapshotFrame(width: 198, height: 242)`.
- Use a uniform topo image built in the test (for example a 1000 × 1200
  `UIGraphicsImageRenderer` fill of RGB(40, 70, 45)) and a matching
  `WatchHoleMapGeometry`, so every sample has a known background.
- Use `fullMap: false`, `interactionMode: .measure`, `showTextOverlay: false`
  unless stated, and no measurement.
- Map a point with `map.canvasPoint(p, in: size)`, then multiply by the scale
  to get pixel coordinates.
- `Δ(p)` is the largest per-channel difference at `p` between the shown render
  and the same view with `showCaddieRecommendation: false`.
- "Near white" means every channel ≥ 170.
- Anti-aliasing makes single-pixel samples flaky, so each sample point is read
  over a neighbourhood within 1 pt (2 px):
  - a "near white" or colour condition holds for the best pixel in it;
  - a `Δ ≤ 8` condition holds for every pixel in it.
- Keep shots long enough (aim ≥ 50 pt on screen) that the samples named below
  don't overlap other marks.

10. **`testRootShotMarksFollowTheS70Geometry`** (G2, G3, G4; pure, no
    pixels). Use at least five `WatchRootShotMarks.resolve(` calls, written
    out, and at least 10 assertions:
    - **In range.** `player (100,200)`, `landing (100,100)`, `carryP10 (100,111)`,
      `carryP90 (100,91)`:
      - `.boxSide == 20`, `.arcRadius == 100`, `.heading == -π/2`;
      - `.aimStart == (100, 200 - playerDiscRadius)`, `.aimEnd == (100, 110)`.
    - **Clamped low:** `carryP10 == carryP90 == landing` gives
      `.boxSide == minimumBoxSide`.
    - **Clamped high:** a 60 pt spread gives `.boxSide == maximumBoxSide`.
    - **No dispersion:** `carryP10: nil, carryP90: nil` gives a nil `.boxSide`
      and `.aimEnd == landing`.
    - **Angled:** `player (0,0)`, `landing (60,80)`: `.arcRadius == 100` and
      `.heading == atan2(80, 60)`.
    - **Degenerate:** `XCTAssertNil` for `player == landing`, and for a
      non-finite input.
11. **`testHoleRootDrawsTheS70PlayerDisc`** (G1). Use `playerMarker: .chevron`,
    a current shot whose aim is 60°–120° from screen-up (a route that turns
    right) and `showCaddieRecommendation: true`. Let `r` be
    `WatchRootShotMarks.playerDiscRadius`, `c` be
    `canvasPoint(geometry.youPx, in: size)`, `u` the aim unit and `n` its
    normal. At least 4 assertions:
    - **Yellow rim:** at `c ± n·0.8r`, R ≥ 200, G ≥ 150, B ≤ 120;
    - **Arrow follows the aim:** at `c + u·0.4r`, the largest channel ≤ 90
      (black arrow). A fixed screen-up arrow fails here;
    - **999 state:** with `rangeUnavailable: true`, the `c ± n·0.8r` samples
      are not yellow.

    No `fullMap: true`.
12. **`testHoleRootDrawsTheBoxArcAndShortAimLine`** (G2, G3, G4). Build a
    layout with `WatchCurrentShotLayout.resolve(` with real p10/p90, choosing
    carries so the clamped side is between the limits. Resolve
    `m = WatchRootShotMarks.resolve(` from its `canvasPoint`s, with `u` and
    `n` as above and `s = m.boxSide!`. Compare
    `showCaddieRecommendation: true` against `false`, with at least 8
    assertions:
    - **Outline:** near white at `m.landing ± n·s/2` (side edges) and at
      `m.landing + u·s/2` (far edge);
    - **Square, not wider:** `Δ ≤ 8` at `m.landing ± n·(s/2 + 4)`;
    - **Fill:** at `m.landing`, `8 ≤ Δ ≤ 110`, with the three channel deltas
      within 30 of each other (a neutral white tint, not the green dot);
    - **Aim line:** near white at the midpoint of `m.aimStart`–`m.aimEnd`;
    - **The line stops at the near edge:** at `m.landing` and at
      `m.landing + u·s/4`, Δ is at least 40 less than Δ at the aim-line
      midpoint;
    - **Arc:** near white at radius `m.arcRadius`, angle
      `m.heading ± 20°` (below `arcHalfAngleDegrees`); `Δ ≤ 8` at the same
      radius and `m.heading ± 35°`;
    - **Depth follows p10–p90:** a second layout with a wider spread (side
      ≥ 6 pt larger, still ≤ max) is near white at its own `± n·s′/2`.

    The body uses `boxSide`, `aimStart`, `aimEnd`, `arcRadius`, `heading` and
    `arcHalfAngleDegrees`, and contains no `fullMap: true`.
13. **`testPreparedRootDrawsTheAimLineAndArcWithoutABox`** (G2, G3, G4). Use a
    geometry with `layupPx`, `showPreparedPlan: true`,
    `showCaddieRecommendation: true` and no current shot. Resolve the marks
    from `canvasPoint(geometry.youPx…)` and `canvasPoint(geometry.layupPx…)`.
    At least 4 assertions:
    - `XCTAssertNil(m.boxSide)`;
    - near white at the aim-line midpoint, which the old curve through
      `apexPx` misses when the apex is off the line;
    - near white on the arc at `m.heading ± 20°`, radius `m.arcRadius`;
    - `Δ ≤ 8` at `m.landing - u·7 + n·7` (where a minimum square's corner
      would be);
    - no caddie-green pixel (G ≥ 150, G − R ≥ 60, G − B ≥ 40) within 4 pt of
      `m.landing`.

    No `fullMap: true`.
14. **`testRemainingMarkersAreS70Sized`** (G5). Use `showReferenceMarkers: true`
    against `showReferenceMarkers: false`, with a `hazardRoute:` that places
    all three markers. For each marker from
    `WatchHoleMapReferenceLayout.remainingMarkers(`, let `c` be its
    `canvasPoint(` and `r` be `remainingMarkerRadius`. At least 4 assertions:
    - `XCTAssertGreaterThanOrEqual(WatchHoleMapReferenceLayout.remainingMarkerRadius, 4.75)`;
    - at `c + (r − 1.2, 0)`, the marker colour:
      - 100: R ≥ 180 and G, B ≤ 110;
      - 150: every channel ≥ 200;
      - 200: B ≥ 180 and R ≤ 110;
    - at `c + (r + outline/2, 0)`, the channel sum is at least 30 lower than
      with the markers off (the dark outline).

    No `fullMap: true`.
15. **`testRootCaddieChipIsCompactAndClearOfTheControls`** (G6). For
    `CGSize(width: 176, height: 215)`, `CGSize(width: 198, height: 242)` and
    `CGSize(width: 205, height: 251)`, written out like this, with at least 8
    assertions:
    - the frame from `rootCaddieChipFrame(in:` has width 36–48 and height
      20–26, and lies inside `WatchDisplayGeometry.contentRect`;
    - `maxY ≤ rootRailBottom(in:) − WatchDisplayGeometry.instrumentControlSize − 6`;
    - `minX ≥ width/2 + WatchRootShotMarks.playerDiscRadius + 4`;
    - it does not intersect `rootFactsFrame(in:` or
      `WatchPlanLegs.clockLane(in:`.

    Then render the root at 198 × 242 with `showTextOverlay: true` and
    `showCaddieRecommendation: true`. Inside the chip frame, fewer than 2 % of
    pixels are hud-green (G ≥ 180, R ≤ 130, B ≤ 160), and the pixels differ
    from the same render with `showCaddieRecommendation: false` (the chip is
    drawn).
16. **Update `testCurrentShotFootprintHasNoFabricatedLateralDispersion`** (G2;
    keep the name). Its strip check no longer holds, because the root now
    draws a square and an arc.
    - Compute `m` with `WatchRootShotMarks.resolve(`. The allowed footprint
      is:
      - points within 3 pt of the segment `aimStart`–`aimEnd`;
      - within the square of side `m.boxSide` (+3 pt) around `m.landing`;
      - within 3 pt of radius `m.arcRadius` and within
        `arcHalfAngleDegrees + 4°` of `m.heading`;
      - within `playerDiscRadius + 2` of the player.
    - Changed pixels outside the footprint == 0.
    - `m.boxSide` equals the clamped screen p10–p90 distance.
    - The `decorativeEllipse` overlay, moved outside the footprint, is still
      detected (`> 0`).

**Existing native tests to adjust.**
- `testHoleRootDrawsTheAimLineAndRealDispersionOnlyWhenShown` (#434): its
  no-spread layout now draws a 14 pt square. If the real 188–220 m spread also
  clamps to about 14 pt on that geometry, widen the carries (for example
  175–235 m) so the square really differs. Keep every token #434's acceptance
  module checks.
- `testRootCaddieChipStaysInsideTheRoundedSafeAreaOnEveryWatchFace` keeps
  passing unchanged.

**Snapshots.**
- `watch-hole-root-aim-line` keeps #434's arguments. It adds
  `showReferenceMarkers: true` and a `hazardRoute:` (the sample route).
- `watch-hole-page-plan` and `watch-hole-page-plan-measure` render the
  production root: `playerMarker: .chevron`, `restingPlayerAnchorFraction: nil`,
  `showReferenceMarkers: true`, a `hazardRoute:`, `showCaddieRecommendation: true`
  and `showPreparedPlan: true`.
- `watch-container-root-aim-line` is unchanged; production already passes the
  markers.

## Goals and pass conditions

### G1 — The player is a yellow disc with a black navigation arrow along the aim

- `WatchPlayerMarkerStyle` has exactly `youDot` and `chevron`. `drawMap` has
  no `var chevron`. It calls `drawPlayerDisc(` exactly once, inside a block
  whose condition has `playerMarker == .chevron` and `!rangeUnavailable` and
  no `||`.
- `drawPlayerDisc` uses `Path(ellipseIn:`, a yellow token (`golfYellow` /
  `hudYellow`), `.black`, `WatchRootShotMarks.playerDiscRadius` and
  `heading`, and no `youBlue`.
- `canvasPoint(_:in:)` exists once, is internal, and uses `anchors(size).t(`.
- The container root passes `playerMarker: .chevron`.
- Native test 11 exists, with `playerMarker: .chevron`,
  `rangeUnavailable: true`, `canvasPoint(`,
  `WatchRootShotMarks.playerDiscRadius` and at least 4 assertions.

### G2 — The landing is a small square: real p10–p90 depth, width equal to depth, no lateral data

- `WatchRootShotMarks` has the stored fields of item 1, with no
  width/depth/lateral/ellipse field. `boxSide` is `CGFloat?`.
  `minimumBoxSide` is 12–16 and `maximumBoxSide` is 26–30.
- `resolve` matches the signature above, is declared once inside the struct,
  and names the clamp and carry tokens.
- `WatchCurrentShotLayout` still stores exactly `player`, `target`,
  `carryP10`, `carryP90` and `continuation`.
- `drawRootShotMarks` draws a `Path(roundedRect:` with `boxSide` in white,
  with no `caddieGreen` and no `Path(ellipseIn:`.
- `drawCurrentShot` has exactly one `WatchRootShotMarks.resolve(` call,
  passing non-nil `carryP10:` / `carryP90:`, and calls `drawRootShotMarks(`.
- A comment block says "lateral", "width" and "depth". No string literal says
  lateral or 横向.
- Native tests 10, 12 and 16 exist with their tokens, and test 10 has at least
  five `resolve` calls and an `XCTAssertNil`.

### G3 — A thin arc through the landing, centred on the player, about ±25° of the aim

- `arcHalfAngleDegrees` is 20–30. `arcRadius` and `heading` are stored
  `CGFloat`.
- `drawRootShotMarks` has exactly one `.addArc(`, with `center:` naming
  `.player` and `radius:` naming `.arcRadius`. `startAngle:` and `endAngle:`
  each name `heading` and `arcHalfAngleDegrees`.
- `drawPreparedPlan` calls `WatchRootShotMarks.resolve(` once, with only
  `player:` and `landing:`. It calls `drawRootShotMarks(`, and has no
  `addQuadCurve`, no `caddieGreen` and no `carryP…`.
- Native tests 10, 12 and 13 exist with their tokens.

### G4 — The aim line runs from the disc edge to the near edge of the square, not through it

- `aimStart` and `aimEnd` are stored fields. `playerDiscRadius` is 6–8 and
  `resolve` uses it.
- `drawRootShotMarks` moves to `.aimStart` and adds a line to `.aimEnd`. It
  never adds a line to `.landing` and never moves to `.player`.
- Native tests 10 and 12 use `aimStart` / `aimEnd`.

### G5 — Remaining-yard markers are S70-sized with a dark outline

- `remainingMarkerRadius` is 4.75–6.0 and `remainingMarkerOutlineWidth` is
  1.0–2.0, both in `WatchHoleMapReferenceLayout`.
- `drawReferenceFacts` uses both by their full names, contains `.black`, and
  has no `2.1`.
- `remainingYards` is `[100, 150, 200]`, and `remainingMarkerColor` keeps
  cases 100, 150 and 200.
- Native test 14 exists with its tokens.

### G6 — The caddie entry is a compact chip: caddie figure + club, opening the caddie page

- The one `"watch-plan-club-tag"` sits in the overlay block gated by
  `showCaddieRecommendation`.
- That block has `Image(systemName: "figure.golf")`,
  `WatchClubDisplay.shortCode(caddieClub)`, at least two `onOpenCaddie()` and
  `rootCaddieChipFrame(in: size)`, and no `hudGreen`, `caddieGreen` or
  `.green`.
- `planTagTapTarget` still uses `WatchHoleMapView.rootCaddieChipFrame(in:`.
- Native test 15 exists, with the three face sizes, the rail, facts, clock
  lane and disc tokens, `showTextOverlay: true` and at least 8 assertions.
- The tap still opens the caddie page; #434's UI test
  `testTappingThePlanTagOpensTheCaddiePage` keeps passing.

### G7 — The facts column, Touch Targeting, the caddie page, 999 and the fallback are unchanged (pinned)

- The F/M/B `distanceValue(backGreen/centerGreen/frontGreen + d` calls stay.
- `drawMap` keeps `drawLightweightMapFacts(`,
  `WatchTouchTargetDistanceLayout.resolve(` with both ranges, and
  `drawMeasurementRoute(`.
- `centerRangeLabel` and `distanceText` keep `999 码 · 等待定位`, and
  `Text("等待定位")` stays.
- `holeMapDetailView` keeps `.touchTarget` and `fullMap: true`. The root keeps
  `.measure`, `fullMap: false` and `{ model.openCaddie() }`.
- `optionMap` keeps `planLegs: legs` and `fullMap: true`, the Crown and
  `clubChain`.

### G8 — README and snapshots show the S70 root for review

- README §3 item 1 (up to item 2) contains:
  - 黄色圆盘, 黑色箭头, 方框, 宽度等于深度, 没有横向散布数据, 弧线, 球童图标
    and 不画方框;
  - `100 / 150 / 200`;
  - #434's D02, 瞄准线, 球童页 and 不画.

  It no longer contains 点绿色球杆签, 地图画 AI 球童路线 or 点它换方案.

  Suggested replacement of item 1's last sentence, and an indented line under
  it:

  > ……根页不画整洞多杆路线、不画每杆标签和引线；点球童图标进入球童页，整洞方案和换方案都在那里。
  >    - 外观（#438，对照 S70）：球员是黄色圆盘 + 黑色箭头，箭头指向瞄准方向；瞄准线是细白线，从圆盘边缘画到落点方框的近边，不穿过方框；落点是白边、浅色半透明填充的小圆角方框，沿瞄准线摆放，深度是真实 p10–p90 落点深度（屏幕上 14–28 pt）。我们没有横向散布数据，所以方框宽度等于深度，它不表示横向散布。一条以球员为圆心、半径到落点、左右各约 25° 的细白弧线标出推荐球杆的距离。备好的发球台方案没有散布数据：只画瞄准线和弧线，不画方框。剩余码数点（红 / 白 / 蓝 = 100 / 150 / 200）放大到 S70 大小并加深色描边。球童入口是右侧的小号深色胶囊：球童图标 + 球杆（如 3W），点它进入球童页。

- In `WatchDesignSnapshotTests`, the one test rendering
  `watch-hole-root-aim-line` and the one rendering `watch-hole-page-plan` each
  have a `WatchHoleMapView(` call with:
  - `playerMarker: .chevron`, `showReferenceMarkers: true`, a non-empty
    `hazardRoute:`, `restingPlayerAnchorFraction: nil` and
    `showCaddieRecommendation: true`;
  - no `fullMap: true`;
  - for the plan snapshot, `showPreparedPlan: true`.

  `watch-container-root-aim-line` is still rendered.
- Review (no acceptance case): `native-mobile` is green on the PR head. The
  reviewer opens `watch-hole-root-aim-line.png`,
  `watch-container-root-aim-line.png` and `watch-hole-page-plan.png` from
  `watch-snapshots` and compares them side by side with the two Garmin images,
  looking at:
  - the disc and arrow;
  - the square's size and its translucency;
  - the arc's length;
  - the aim line ending at the square;
  - the marker sizes;
  - the chip.

  They also check `watch-caddie-options` (unchanged caddie page).

## Expected results

On `main`, the 7 non-pinned tests fail:
- G1: `var chevron` is still drawn and `drawPlayerDisc` is missing;
- G2–G4: `WatchRootShotMarks` is missing;
- G5: `remainingMarkerRadius` is missing;
- G6: the chip has no `figure.golf`;
- G8: the README has none of the new wording.

The pinned G7 test passes on `main` and after the change.

The sandbox refused to run Python, so I traced these results by hand against
`main` (`7f42195`). The gate is the authority.
