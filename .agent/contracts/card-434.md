# Card #434 — Watch hole root: back to D02 (S70 parity), one aim line only

The Watch hole root draws, all at once:
- the green OSM tee-to-green line (`drawFactualRoute`);
- the whole remaining plan: every leg, every landing, the "D 224" / "3W 205"
  labels and their leader lines (`drawFullPlan`, fed by the container's
  `planLegs`);
- the current-shot overlay.

The owner says this is too busy, and S70 does not do it. Owner decision D02 (C′,
`docs/reviews/2026-07-15-watch-decision-and-task-tracker.md`) and the S70
evidence (`docs/reviews/2026-07-16-s70-virtual-caddie-driver-arc-evidence.md`)
set the rules:
- the root keeps the facts layer;
- only when the current-shot recommendation is real and allowed, it adds one aim
  line, the recommended club and the real dispersion;
- the full plan lives behind a tap on the club;
- the root never draws a deterministic multi-shot route.

Touches: `mobile/ios/AICaddieWatch/Views/WatchHoleMapView.swift`, `mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift`, `mobile/ios/AICaddieWatch/Views/WatchCaddieOptionsView.swift`, `mobile/ios/AICaddieWatch/Views/WatchUITestRoot.swift`, `mobile/ios/AICaddieWatch/Models/WatchRoundState.swift`, `mobile/ios/AICaddieWatchTests/**`, `mobile/ios/AICaddieWatchUITests/WatchHolePagesUITests.swift`, `docs/design/2026-09-25-ui-redesign/README.md`, `tests/acceptance/test_card_434_watch_root_one_aim_line.py`, `.agent/contracts/card-434.md`

The card's own Touches line leaves out `WatchRoundContainerView.swift`, and the
change needs it: that file builds the root and passes `planLegs` to it. The
other additions are the native tests that must change and, if the UI-test
fixture needs it, `WatchUITestRoot.swift`. `WatchRoundState.swift` is on the
card's line, but this contract needs no change there.

Acceptance tests: `tests/acceptance/test_card_434_watch_root_one_aim_line.py`
(10 tests; 3 of them are `# pinned` and check behaviour that must stay as it
is).

Watch only: no backend, phone, web, contract or migration changes. A PR that
touches `mobile/ios/**` also needs the `native-mobile` check green on its head.

Dependency on #435: none. This contract needs no #435 work. No branch or file
in the checkout contains any #435 code, contract or acceptance test. If #435
touches any path on the Touches line above, the scheduler orders the two cards;
#434 does not wait for it.

## How this is tested

The Watch app runs only on macOS. These acceptance tests run on Linux in the
backend job.

- Each acceptance test runs `git ls-files` in a subprocess, so only tracked
  files count, then checks the tracked Swift sources and the README
  structurally. Comments are ignored, and string contents are masked when the
  test analyses code structure.
- The native XCTests and snapshots listed under G6 run in `native-mobile` CI.
- The reviewer compares the `watch-snapshots` artifact against the S70 evidence
  document, not only against the README.

So the interface below is named exactly. Keep these names.

## Interface

### `WatchHoleMapView.swift`

1. A pure rule on `WatchHoleMapView` (in the struct or in an
   `extension WatchHoleMapView`):

   ```swift
   /// D02 (#434, S70 parity): the resting hole root (not a full map) draws the facts layer and at
   /// most this shot. The tee-to-green route line and the multi-shot plan (legs, landing labels,
   /// leader lines, current-shot continuation) are drawn only on full-map instruments.
   static func drawsRouteAndPlan(fullMap: Bool) -> Bool { fullMap }
   ```

   The body is exactly `fullMap` (or `return fullMap`). Inside
   `WatchHoleMapView.swift`, every call is written
   `Self.drawsRouteAndPlan(fullMap: fullMap)` (`WatchHoleMapView.` instead of
   `Self.` is fine).
2. In `drawMap`:
   - **`drawFullPlan(...)`**: draw it only under a condition that uses the rule,
     for example `let drawsFullPlan = Self.drawsRouteAndPlan(fullMap: fullMap) && !planLegs.isEmpty`
     followed by `if drawsFullPlan {`. A
     `guard Self.drawsRouteAndPlan(fullMap: fullMap) else { return }` at the top
     of `drawFullPlan` also counts. At least one `drawFullPlan(` call stays in
     `drawMap`, because the caddie page uses it.
   - **`drawFactualRoute(...)`** (topo image ready): draw it only under a
     condition that uses the rule, for example
     `} else if Self.drawsRouteAndPlan(fullMap: fullMap) {`, or with the same
     guard inside the function. You may delete `drawFactualRoute` entirely
     instead; then Touch Target and the caddie page lose the green line too.
     Either is accepted.
   - **The lightweight map-facts fallback** (`drawLightweightMapFacts`, used
     when the topo image is not ready) is **not** gated. It is the map
     degradation contract in README §8.
3. In `drawCurrentShot`, every use of `layout.continuation` is gated by the
   rule, for example
   `if Self.drawsRouteAndPlan(fullMap: fullMap), !layout.continuation.isEmpty {`.
   The aim line, the p10–p90 depth marks and the target dot are not gated.
4. Do not change these:
   - `WatchCurrentShotLayout`: the stored fields stay `player`, `target`,
     `carryP10`, `carryP90` and `continuation`. There is no lateral radius and
     no ellipse;
   - `drawPreparedPlan`: one first-shot leg, with no dispersion;
   - `WatchHoleMapRouteOverlay.resolve`: measurement first, then current shot,
     then prepared plan, so at most one aim line;
   - Touch Target and measure drawing.

   Update the doc comments that call `planLegs` the root's "方案 page".

### `WatchRoundContainerView.swift`

5. Add a new private helper:

   ```swift
   /// D02: the root recommendation layer (club tag + one aim line) is real and allowed.
   private func showsRootRecommendation(_ s: WatchRoundState, geometry: WatchHoleMapGeometry) -> Bool
   ```

   - It returns true only when either:
     - `currentShotLayout(for: s, geometry: geometry) != nil` (the live gate,
       `model.rootCaddieLayerAvailable(at:)`); or
     - `model.preparedRootCaddieLayerAvailable(at: shotLocation)` holds and
       `preparedRootGeometry(for: s, base: geometry) != nil` (the prepared Tee
       plan, with the player on the tee).
   - Its body never reads plan legs, `caddieOptions` or option counts.
6. In `holeMapView` (the hole root), the `WatchHoleMapView(` call:
   - passes **no** `planLegs:` argument;
   - keeps `fullMap: false` and `interactionMode: .measure`;
   - passes `showCaddieRecommendation: showsRootRecommendation(s, geometry: geometry)`.
     The `|| !legs.isEmpty` goes: the chip no longer appears just because a plan
     exists. When neither gate holds, the whole layer disappears and the root is
     the plain facts view (D02 option B);
   - passes `onOpenCaddie: { model.openCaddie() }`.

   Also:
   - the container no longer calls `WatchPlanLegs.resolve(`, so its private
     `planLegs(_:geometry:)` goes;
   - `cyclePlan` goes, and the identifier `cyclePlan` no longer appears in the
     file;
   - `selectedPlanId` and `nextPlanId(after:in:)` go if nothing else uses them.
     Update `WatchHolePagesTests` to match.
7. `planTagTapTarget` (the tap overlay above the pager):
   - it is shown when `showsRootRecommendation(...)` holds, instead of
     `currentCaddieOptions(s).count > 1`;
   - its tap calls `model.openCaddie()`.
8. The root's `currentShotLayout(for:geometry:)` keeps passing no
   `continuation:` (unchanged).

### `WatchCaddieOptionsView.swift`

9. The caddie page (`optionInstrument`) keeps `fullMap: true`,
   `showCaddieRecommendation: true` and `planLegs: legs`: the full multi-shot
   plan, landings, labels and leader lines. The Crown still switches 稳妥 / 标准 /
   进攻. This is the page that opens when the player taps the recommended club
   on the root (for example 3W). It needs no functional change.

### Not changed

- Touch Targeting (`holeMapDetailView`, `interactionMode: .touchTarget`,
  `fullMap: true`) and the root's measure ring still show "player to target"
  and "target to green" (`WatchTouchTargetDistanceLayout`).
- The "999+ / waiting for location" state: `999 码 · 等待定位`, `等待定位` and the
  hidden player marker without a qualified fix.
- `drawLightweightMapFacts` (README §8).

### G1 — The hole root draws the facts layer and at most one aim line

1. `WatchHoleMapView.drawsRouteAndPlan(fullMap:)`:
   - is declared `static func drawsRouteAndPlan(fullMap: Bool) -> Bool`, on
     `WatchHoleMapView`;
   - has the body `fullMap`;
   - every call in `WatchHoleMapView.swift` passes exactly `fullMap: fullMap`.
2. In `drawMap`, each `drawFullPlan(` call is gated by the rule, either at the
   call site or by a guard inside `drawFullPlan`, and at least one call exists.
3. In `drawMap`, `drawFactualRoute` is either removed entirely, or each call is
   gated by the rule in the same way.
4. In `drawCurrentShot`, every `layout.continuation` use is gated by the rule.
5. The root `WatchHoleMapView(` call in `holeMapView`:
   - has no `planLegs` argument;
   - has `fullMap: false`;
   - and the container contains no `WatchPlanLegs.resolve(`.
6. No `WatchHoleMapView(` call in the tracked Watch app, unit test or UI test
   sources passes `planLegs:` without `fullMap: true`. This covers production,
   the UI-test root and the snapshot tests. This test also covers G6.

### G2 — The recommendation layer appears only when it is real and allowed, with real dispersion only

7. `showsRootRecommendation(_:geometry:)`:
   - exists in the container;
   - reads `currentShotLayout(` and `preparedRootCaddieLayerAvailable`;
   - never reads plan legs, `caddieOptions` or `.count`.

   The root call passes
   `showCaddieRecommendation: showsRootRecommendation(...)`, which does not
   depend on legs.
8. Pinned (unchanged behaviour):
   - `WatchCurrentShotLayout` holds exactly `player`, `target`, `carryP10`,
     `carryP90` and `continuation`, and still requires
     `carryP10M <= aimCarryM <= carryP90M`;
   - the root's `currentShotLayout(for:geometry:)` is gated by
     `model.rootCaddieLayerAvailable(at: shotLocation)` and passes no
     `continuation`;
   - `drawPreparedPlan` draws no p10/p90;
   - `WatchHoleMapRouteOverlay.resolve` returns measurement first, then current
     shot, then prepared plan.

### G3 — Tapping the recommended club opens the caddie page, which holds the multi-shot plan

9. On the root:
   - `onOpenCaddie` calls `model.openCaddie()`;
   - `planTagTapTarget` is gated by `showsRootRecommendation(` and calls
     `model.openCaddie()`, with no `count > 1`;
   - `cyclePlan` no longer exists in the container.
10. Pinned:
    - the caddie page's `WatchHoleMapView(` call passes `planLegs: legs`,
      `fullMap: true` and `showCaddieRecommendation: true`;
    - `drawMap` still calls `drawFullPlan(`;
    - the caddie page keeps its Crown (`digitalCrownRotation(`) and
      `clubChain`.

### G4 — Touch Targeting, the map fallback and the 999 / waiting-for-location state are unchanged

11. Pinned:
    - `drawMap` still calls `drawLightweightMapFacts(`, not gated by the rule;
    - `drawMap` still resolves `WatchTouchTargetDistanceLayout.resolve(` and
      draws both `playerToTargetYards` and `targetToPinYards`;
    - `WatchHoleMapRouteOverlay.resolve` still returns `.measurement` first;
    - `holeMapDetailView` keeps `interactionMode: .touchTarget` and
      `fullMap: true`, and the root keeps `interactionMode: .measure`;
    - `centerRangeLabel` and the container's `distanceText` still say
      `999 码 · 等待定位`, and the root still shows `Text("等待定位")`.

### G5 — README §3 item 1 agrees with D02

12. In `docs/design/2026-09-25-ui-redesign/README.md` §3, the 本洞 list item
    `1.` (up to item `2.`):
    - no longer contains `地图画 AI 球童路线` or `点它换方案`;
    - contains `D02`, `瞄准线`, `球童页` and `不画`.

    It should say:
    - the root keeps the facts;
    - only a real, allowed current-shot recommendation adds one aim line from
      the player to this shot's landing, the club tag and the real dispersion;
    - there is no decorative ellipse without real dispersion data;
    - the root does not draw the whole-hole route or per-shot labels;
    - tapping the club tag opens the caddie page, which holds the full plan and
      plan switching.

    Suggested wording:

    > 1. 方案（D02 / S70）：根页常驻事实层；只有当前一杆建议真实、可信、新鲜且模式允许时，才加一条从球员到本杆落点的瞄准线、推荐杆签和真实散布（没有真实散布数据就不画装饰椭圆）。根页不画整洞多杆路线、不画每杆标签和引线；点绿色球杆签进入球童页，整洞方案和换方案都在那里。

    Keep the other §3 items. Line 64's "方案路线" may become "瞄准线".

### G6 — Native tests and snapshots show the new root for review

13. Native tests (Codex writes them; `native-mobile` runs them):
    - **Unit test.** Under `mobile/ios/AICaddieWatchTests/`,
      `func testHoleRootNeverDrawsTheRouteOrTheMultiShotPlan` asserts both of
      these:
      - `XCTAssertFalse(WatchHoleMapView.drawsRouteAndPlan(fullMap: false))`;
      - `XCTAssertTrue(WatchHoleMapView.drawsRouteAndPlan(fullMap: true))`.
    - **Snapshot `watch-hole-root-aim-line`.** In `WatchDesignSnapshotTests`, a
      test renders it from a `WatchHoleMapView(` set up like the production
      root:
      - `interactionMode: .measure`, `playerMarker: .chevron`;
      - no `fullMap: true`, no `planLegs`;
      - `showCaddieRecommendation: true`, and a non-nil `currentShotLayout`
        with real p10/p90 on the sample topo.
    - **Snapshot `watch-container-root-aim-line`.** In
      `WatchDesignSnapshotTests`, a test renders it through
      `WatchRoundContainerView(` on the root:
      - no `openHoleMap()` or `openCaddie()` call;
      - `holeGeometry:` from the sample topo image;
      - a hole state with a live `rootCaddieRecommendation` that passes the
        gate (the same shape as
        `testRootCaddieLayerAppearsForACompleteCurrentLiveRecommendation`, with
        a matching fix);
      - a multi-shot plan (`"plan"` or at least two `WatchCaddiePlanStep(`).

      It shows one aim line and dispersion, and no labels.
    - **Existing snapshots stay.** `watch-hole-page-plan`,
      `watch-hole-page-plan-measure`, `watch-caddie-options`,
      `watch-holemap-measured` and `watch-holemap-current-shot` are still
      rendered. The two `watch-hole-page-plan*` snapshots now draw the root
      without `planLegs`; the measure one still shows the yellow ring and both
      ranges.
    - **UI test.** In `WatchHolePagesUITests`:
      - `testAfterTheTeeShotThePlanTagShowsTheNextClubAndSwitchesPlans` is
        gone, and nothing asserts that tapping the tag switches plan;
      - a new `func testTappingThePlanTagOpensTheCaddiePage` taps
        `watch-plan-club-tag` and waits for `watch-caddie-instrument`. The
        `standalone-course-page-plan` fixture puts the player on its tee, so
        the prepared layer shows the tag there. If the caddie instrument's
        identifier is not queryable, fix that in the view, for example with
        `.accessibilityElement(children: .contain)`.

- `native-mobile` is green on the PR head.
- The reviewer opens `watch-snapshots` and checks these against the S70
  evidence document:
  - `watch-hole-root-aim-line`, `watch-container-root-aim-line`,
    `watch-hole-page-plan`: one aim line, no full route, no per-shot labels,
    no leader lines;
  - `watch-hole-page-plan-measure`, `watch-holemap-measured`: two distances;
  - `watch-caddie-options`, `watch-caddie-options-prepared`: the full plan.

  There is no acceptance case for this check.

## Not in scope

- No backend, phone, web, contract, migration or auth change.
- No pinned file.
- No change to `tests/acceptance/`; Codex must not edit it.
- No change to the 999 / waiting-for-location state, to Touch Targeting, to
  `drawLightweightMapFacts` (README §8) or to the D02 / S70 review documents.

All 7 non-pinned tests fail on `main`, because the rule, the helper and the
native tests don't exist there and the root still passes `planLegs`. The 3
pinned tests pass on `main` and after the change.

I could not run Python in the contract sandbox, so these results come from
reading the code, not from running it. I checked each pinned assertion by hand
against the current `main` sources, which match the tree this contract was
first written against.
