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

Touches: `mobile/ios/AICaddieWatch/Views/WatchHoleMapView.swift`, `mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift`, `mobile/ios/AICaddieWatch/Views/WatchCaddieOptionsView.swift`, `mobile/ios/AICaddieWatch/Views/WatchUITestRoot.swift`, `mobile/ios/AICaddieWatch/Models/WatchRoundState.swift`, `mobile/ios/AICaddieWatchTests/**`, `mobile/ios/AICaddieWatchUITests/WatchHolePagesUITests.swift`, `docs/design/2026-09-25-ui-redesign/README.md`, `tests/test_mobile_contracts.py`, `tests/acceptance/test_card_434_watch_root_one_aim_line.py`, `.agent/contracts/card-434.md`

The card's own Touches line leaves out `WatchRoundContainerView.swift`, and the
change needs it: that file builds the root and passes `planLegs` to it. The
other additions are:
- the native tests that must change and, if the UI-test fixture needs it,
  `WatchUITestRoot.swift`;
- `tests/test_mobile_contracts.py`, a necessary test-only touch: three existing
  contract tests there assert the behaviour this card removes (see "Existing
  contract tests to update").

`WatchRoundState.swift` is on the card's line, but this contract needs no
change there.

Acceptance tests: `tests/acceptance/test_card_434_watch_root_one_aim_line.py`
(12 tests; 4 of them are `# pinned`). Three pinned tests check behaviour that
must stay as it is. The fourth is a self-check of the Swift declaration parser
the other tests use.

Watch only: no backend, phone, web, contract or migration changes. A PR that
touches `mobile/ios/**` also needs the `native-mobile` check green on its head.

Dependency on #435: none. This contract needs no #435 work. If #435 touches any
path on the Touches line above, the scheduler orders the two cards; #434 does
not wait for it.

## Revision 2 (after Codex's implementation 8b3e6d3b)

Codex reported that the published acceptance module was still byte-identical
to the one with the parser bug: the previous revision's fix did not reach the
branch. This revision writes the corrected module onto the current base. The
goals, the interface and every behavioural and pinned assertion are unchanged.

1. **Parser fix, in the module itself.** `_body` (the helper that finds a
   declaration's `{ }` body):
   - starts from the number of `(` and `[` the pattern match leaves open, so a
     pattern that consumes the parameter list's `(` (such as
     `func\s+example\s*\(`) no longer drives the depth negative;
   - returns `None` when a `)`, `]` or `}` closes an enclosing scope before a
     body opens;
   - new: returns `None` when, outside brackets, the next declaration starts
     (`func`, `var`, `let`, `init`, `struct`, `case`, an access modifier, …)
     before a body opens, so a bodiless declaration never borrows the next
     member's body. `async`, `throws`, `rethrows`, `->` types and `where`
     clauses are skipped as part of the signature.

   This makes the G2 `showsRootRecommendation` check, the G6 rule-test lookup,
   snapshot discovery (`_test_functions`) and the UI-test lookup work.
2. **Parser self-check, extended.** The pinned test
   `SwiftBodyParserTests.test_body_is_found_whether_or_not_the_pattern_consumes_the_parenthesis`
   runs `_body` and `_test_functions` on inline Swift (`PARSER_SAMPLE`,
   `PARSER_TESTS_SAMPLE`). Each declaration is found with a name-only pattern,
   a pattern that consumes `(`, and patterns that consume part of the
   parameter list:
   - empty arguments: `func example() { … }`;
   - typed arguments with brackets and a closure default:
     `func other(_ a: [Int], b: (Int) -> Int = { $0 }) -> Bool { … }`;
   - typed arguments that throw: `func typed(_ shot: Shot, at index: Int) throws -> Int { … }`;
   - a multi-line signature with a `")"` string default and `async throws -> [Leg]`;
   - a bodiless `func bare()` followed by `var tail: Int { 1 }` (no body), and
     `var tail` itself (found);
   - test discovery: `testA()`, `testB() throws`,
     `testC(_ unused: Int = 0) async throws` and `testAB()` are all found, in
     order, with their own bodies (`testA` never takes `testAB`'s).

   The G6 test still asserts that more than five snapshot test functions are
   discovered, so a parser failure cannot pass silently.
3. **`tests/test_mobile_contracts.py`** is recorded on the Touches line as a
   necessary test-only touch. Codex's update of the three obsolete assertions
   follows "Existing contract tests to update".

## Revision 3 (after the adversarial gate on 42b4f19)

The gate's adversarial check failed on head `42b4f19`. Its report was not
available to this contract job, so this revision closes every weak spot found by
reading the acceptance module against the interface. In each of them, a change
that breaks D02 could still have passed. The goals, the interface, the test
count (11, 4 `# pinned`) and the pinned tests are unchanged. By hand tracing,
the implementation on `42b4f19` already meets every stricter condition. No
Swift change is expected from this revision.

1. **Gates cannot be bypassed** (G1).
   - A condition counts as gated only when it contains no `||`.
   - The rule may not be compared (`== false`, `!=`) or used in a ternary.
   - A rule-bound local may not be compared either.
   - A `guard` counts only at the top level of the function body, not inside a
     nested block.
2. **No drawing moves elsewhere** (G1). Every `drawFullPlan(` and
   `drawFactualRoute(` call in `WatchHoleMapView.swift` must sit in `drawMap`
   and be gated. The other way to pass is for the callee to start with
   `guard Self.drawsRouteAndPlan(fullMap: fullMap) else { return }`.
   `drawMap` and `drawCurrentShot` must not shadow `fullMap`.
3. **The root's arguments are exact** (G2, G3).
   - `showCaddieRecommendation:` is exactly
     `showsRootRecommendation(s, geometry: geometry)`.
   - `onOpenCaddie:` is exactly `{ model.openCaddie() }`.
4. **The helper is the two gates and nothing else** (G2).
   `showsRootRecommendation` contains:
   - `currentShotLayout(for: s, geometry: geometry) != nil`;
   - `model.preparedRootCaddieLayerAvailable(at: shotLocation)`;
   - `preparedRootGeometry(for: s, base: geometry) != nil`;
   - exactly one `||` and at least one `&&`.

   It contains no `true`, no prefix `!`, and no `caddieOption`, `.plan`,
   `optionId`, `.count` or legs.
5. **The tap target only opens the caddie page** (G3). In `planTagTapTarget`:
   - the condition calls `showsRootRecommendation(s, geometry: geometry)`, with
     no `||` and no options or count;
   - its only `.onTapGesture` closure is exactly `model.openCaddie()`.

   `selectedPlanId` is gone from the container.

## Revision 4 (after the adversarial gate on 4f38424)

The adversarial gate failed again, on head `4f38424`. Its report was not
available to this contract job either. Since card #440 / #445, that gate also
judges Swift mutants with the real native tests (`agenthub-native-mutant.yml`):
a mutant counts as caught only when a native test fails. On `4f38424` the only
native test of the D02 rule is the rule's truth table. Every Swift mutant that
bypasses the rule therefore passes `native-mobile`, whatever the Python checks
say:
- `drawsFullPlan` without `Self.drawsRouteAndPlan(fullMap: fullMap) &&`;
- `} else if Self.drawsRouteAndPlan(fullMap: fullMap) {` back to `} else {`
  (the route over the topo image on the root);
- the continuation gate dropped from `drawCurrentShot`;
- `showsRootRecommendation` widened (`|| !currentCaddieOptions(s).isEmpty`,
  `&&` for `||`, the prepared branch dropped, `true`);
- the root's `showCaddieRecommendation:` replaced by `true`.

The snapshots are rendered but not compared, so none of these changes fails a
native test. Revision 4 asks for three native tests that observe the rules, and
the acceptance module checks that they exist (new test
`test_native_tests_observe_the_root_rules`, so now 12 tests, still 4 pinned).
The goals and every earlier condition are unchanged, apart from two points:
- `showsRootRecommendation` is now **internal** (not `private` or
  `fileprivate`), so that `@testable import AICaddieWatch` can call it;
- G1.6 gains one exception: the pixel-invariance test may give the resting root
  `planLegs`, because that is how it shows that they are not drawn.

**Swift change expected from Codex:** drop `private` from
`showsRootRecommendation`, then add the three native tests under G6 items 15–17.
Nothing else changes. If a native test fails on the current Swift code, the
code breaks D02. Fix the code, not the test.

**Known survivors (the native tests cannot see them; the Python checks do):**
- `onOpenCaddie:` on the root changed to another closure. The tap target above
  the pager takes the tap first, so the chip's own closure never runs in the
  UI journey.
- `planTagTapTarget` shown under a wider condition. The target is clear and
  hidden from accessibility, so it can't be seen and a UI test can't find it.
- `planLegs:` passed to the root again while the rule holds. Nothing is drawn,
  so no pixel changes.

If the gate names a survivor that is not on this list, I will pin it or record
it here as equivalent.

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

5. Add a new helper. It is internal (revision 4: no `private` or `fileprivate`)
   so that the native truth-table test can call it:

   ```swift
   /// D02: the root recommendation layer (club tag + one aim line) is real and allowed.
   func showsRootRecommendation(_ s: WatchRoundState, geometry: WatchHoleMapGeometry) -> Bool
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

## Existing contract tests to update (`tests/test_mobile_contracts.py`)

Change only the assertions named below. Keep every other check in these tests
as it is. Only these three tests in this file change.

1. `MobileContractTests.test_watch_b6_score_screen_shot_undo_and_hole_end`:
   - in the token list checked against `container`, replace
     `"onOpenCaddie: { cyclePlan(s) }"` with
     `"onOpenCaddie: { model.openCaddie() }"`;
   - add `self.assertNotIn("cyclePlan", container)`;
   - change the comment "tap the club tag for the next plan" to say that
     tapping the club tag opens the caddie page (#434, D02).
2. `WatchHolePagesContractTests.test_whole_plan_real_outline_and_crown_only_zooms`:
   - replace
     `self.assertIn("let legs = planLegs(s, geometry: geometry)", ...container...)`
     with both of these, on the container source:
     - `assertNotIn("planLegs(s, geometry: geometry)", container)`;
     - `assertNotIn("WatchPlanLegs.resolve(", container)`;
   - keep the hazard, phone `CurrentHoleView` and green checks unchanged.
3. `WatchHolePagesContractTests.test_a_current_plan_drives_the_club_tag_and_the_caddie_detail_draws_every_leg`:
   - rename it to
     `test_a_real_recommendation_drives_the_club_tag_and_the_caddie_detail_draws_every_leg`;
   - replace the `showCaddieRecommendation: currentShot != nil || preparedRootCaddieLayerAvailable || !legs.isEmpty`
     assertion with:
     - `assertIn("showCaddieRecommendation: showsRootRecommendation(s, geometry: geometry)", container)`;
     - `assertNotIn("!legs.isEmpty", container)`;
   - keep the four `WatchCaddieOptionsView` checks (`let legs = mappedGeometry.map …`,
     `planLegs: legs`, the framing `points:` line and `fullMapFocusImagePx:`)
     unchanged;
   - in the UI part, replace `assertIn("standalone-course-page-plan-after-tee", ui)`
     and `assertIn("tag.tap()", ui)` with:
     - `assertIn("func testTappingThePlanTagOpensTheCaddiePage", ui)`;
     - `assertIn('"watch-plan-club-tag"', ui)`;
     - `assertIn('"watch-caddie-instrument"', ui)`;
     - `assertNotIn("SwitchesPlans", ui)`.

`test_green_page_yields_paging_and_flag_slides_along_the_edge` counts
`swipe(up: true)` (exactly 2) and `swipe(up: false)` in `WatchHolePagesUITests`.
Do not add swipes to the new UI test, so that count stays right.

The `standalone-course-page-plan-after-tee` fixture in `WatchUITestRoot.swift`
may stay: `.github/workflows/watch-runtime.yml` still captures it, and that
workflow is not on the Touches line. It now shows the root without a club tag
(D02 option B) unless a gate holds.

### G1 — The hole root draws the facts layer and at most one aim line

1. `WatchHoleMapView.drawsRouteAndPlan(fullMap:)`:
   - is declared `static func drawsRouteAndPlan(fullMap: Bool) -> Bool`, on
     `WatchHoleMapView`;
   - has the body `fullMap`;
   - every call in `WatchHoleMapView.swift` passes exactly `fullMap: fullMap`.
2. Every `drawFullPlan(` call in the file is gated by the rule. That means
   either a guard at the top level of `drawFullPlan`, or a call inside
   `drawMap` under a condition (or top-level guard) that uses the rule, with no
   `||`, negation or comparison. At least one call exists in `drawMap`.
3. `drawFactualRoute` is either removed entirely, or each call is gated by the
   rule in the same way.
4. In `drawCurrentShot`, every `layout.continuation` use is gated by the rule.
   Neither `drawMap` nor `drawCurrentShot` shadows `fullMap`.
5. The root `WatchHoleMapView(` call in `holeMapView`:
   - has no `planLegs` argument;
   - has `fullMap: false`;
   - and the container contains no `WatchPlanLegs.resolve(`.
6. No `WatchHoleMapView(` call in the tracked Watch app, unit test or UI test
   sources passes `planLegs:` without `fullMap: true`. This covers production,
   the UI-test root and the snapshot tests. This test also covers G6. The one
   exception (revision 4) is a call inside the body of the unit test
   `testHoleRootPixelsIgnoreTheRouteThePlanAndTheContinuation` (G6 item 15).

### G2 — The recommendation layer appears only when it is real and allowed, with real dispersion only

7. `showsRootRecommendation(_:geometry:)`:
   - exists in the container, and is not `private` or `fileprivate`;
   - is `currentShotLayout(for: s, geometry: geometry) != nil || (model.preparedRootCaddieLayerAvailable(at: shotLocation) && preparedRootGeometry(for: s, base: geometry) != nil)`
     (exactly one `||`, at least one `&&`);
   - never reads plan legs, `caddieOption(s)`, `caddieOptions`, `.plan`,
     `optionId` or `.count`, and has no `true` or prefix `!`.

   The root call passes exactly
   `showCaddieRecommendation: showsRootRecommendation(s, geometry: geometry)`.
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
9. Pinned parser self-check (G2 and G6 depend on it):
   - `_body` finds the body of empty-argument, typed-argument, throwing, async
     and multi-line declarations, whether or not the pattern consumes the `(`;
   - it returns `None` for a declaration without a body, also when another
     member follows it;
   - `_test_functions` discovers every `func test…`, each with its own body.

### G3 — Tapping the recommended club opens the caddie page, which holds the multi-shot plan

10. On the root:
    - `onOpenCaddie` is exactly `{ model.openCaddie() }`;
    - `planTagTapTarget` is gated by
      `showsRootRecommendation(s, geometry: geometry)`, with no `||`, no
      `count > 1` and no options lookup. Its only `.onTapGesture` closure is
      `model.openCaddie()`;
    - `cyclePlan` and `selectedPlanId` no longer exist in the container.
11. Pinned:
    - the caddie page's `WatchHoleMapView(` call passes `planLegs: legs`,
      `fullMap: true` and `showCaddieRecommendation: true`;
    - `drawMap` still calls `drawFullPlan(`;
    - the caddie page keeps its Crown (`digitalCrownRotation(`) and
      `clubChain`.

### G4 — Touch Targeting, the map fallback and the 999 / waiting-for-location state are unchanged

12. Pinned:
    - `drawMap` still calls `drawLightweightMapFacts(`, not gated by the rule;
    - `drawMap` still resolves `WatchTouchTargetDistanceLayout.resolve(` and
      draws both `playerToTargetYards` and `targetToPinYards`;
    - `WatchHoleMapRouteOverlay.resolve` still returns `.measurement` first;
    - `holeMapDetailView` keeps `interactionMode: .touchTarget` and
      `fullMap: true`, and the root keeps `interactionMode: .measure`;
    - `centerRangeLabel` and the container's `distanceText` still say
      `999 码 · 等待定位`, and the root still shows `Text("等待定位")`.

### G5 — README §3 item 1 agrees with D02

13. In `docs/design/2026-09-25-ui-redesign/README.md` §3, the 本洞 list item
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

14. Native tests (Codex writes them; `native-mobile` runs them):
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

    Revision 4 adds three native unit tests under `mobile/ios/AICaddieWatchTests/`
    (any file, exactly one function of each name). They must observe the D02
    rules, so that a Swift mutant that bypasses a gate fails a native test.
    Build each view and state inside the test body; a local closure or nested
    function inside the body is fine. None of them may use `XCTSkip…` or
    `XCTExpectFailure`. Mark them `@MainActor` where `ImageRenderer` needs it.
    The acceptance module checks the tokens named below.

15. **`func testHoleRootPixelsIgnoreTheRouteThePlanAndTheContinuation`** (G1).
    Render with `ImageRenderer` (the same file uses `ImageRenderer(`) and
    compare raw pixels, for example the RGBA bytes of `cgImage` at a fixed size,
    scale and dark colour scheme.
    - **Base.** A resting root on the sample topo image: `WatchHoleMapView(` with
      `fullMap: false`, `interactionMode: .measure`, `showCaddieRecommendation: true`,
      and a `currentShotLayout` with real p10/p90 and no continuation. Its
      geometry has `routePx: []`. There is no measurement.
    - **The same pixels (`XCTAssertEqual`)** when, one at a time, the root also
      gets:
      - (a) a geometry with the sample route as `routePx:`;
      - (b) non-empty `planLegs:` (for example from `WatchPlanLegs.resolve`);
      - (c) a `currentShotLayout` resolved with a non-empty `continuation:`.
    - **Positive control (`XCTAssertNotEqual`).** Each of (a), (b) and (c)
      changes the pixels of the same view with `fullMap: true`, compared with
      that full map's own base. This shows the comparison can see each layer.
      If `drawFactualRoute` is deleted (allowed by item 3), drop the (a) control
      only.
    - The body contains `WatchHoleMapView(`, `planLegs:`, `continuation:`,
      `routePx:`, `fullMap: false`, `fullMap: true`, `XCTAssertEqual(` and
      `XCTAssertNotEqual(`. It does not mention `drawsRouteAndPlan`.
16. **`func testRootRecommendationNeedsALiveOrPreparedTeeGateNotAPlan`** (G2).
    Build `WatchRoundContainerView(` values over seeded models, as
    `testRenderWatchContainerRootAimLine` does. The prepared fixture in
    `WatchRoundModelTests` (around `preparedRootCaddieLayerAvailable`) shows a
    prepared Tee state. Then call `showsRootRecommendation(state, geometry:)`
    directly:
    - `XCTAssertTrue`: a live `rootCaddieRecommendation` that passes the gate,
      with a matching qualified fix;
    - `XCTAssertTrue`: a prepared Tee plan, no live recommendation, and a
      qualified fix on the tee;
    - `XCTAssertFalse`: a multi-shot plan (at least two
      `WatchCaddiePlanStep(`) with no live recommendation and the fix off the
      tee;
    - `XCTAssertFalse`: the same prepared plan with the fix off the tee.

    The checker counts the `XCTAssertTrue(` and `XCTAssertFalse(` calls whose
    arguments contain `showsRootRecommendation(`, and needs at least two of
    each.
17. **`func testContainerRootWithoutAGateDrawsNoPlanAndNoClubTag`** (G2, G3).
    Render the real container root (`WatchRoundContainerView(` …
    `.snapshottingHoleRoot()`) with `ImageRenderer`, on the sample topo image
    and with a qualified fix off the tee:
    - `XCTAssertEqual`: a state with a multi-shot plan (at least two
      `WatchCaddiePlanStep(`) and no live recommendation renders the same pixels
      as the same state with `caddieOptions: []`;
    - `XCTAssertNotEqual`: the same state with a live `rootCaddieRecommendation`
      that passes the gate renders differently: the club tag and one aim line
      appear;
    - no `openHoleMap()` or `openCaddie()` call.

    Use a fresh `WatchRoundModel` (its own store directory) for each state.

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

## Expected results

All 8 non-pinned tests fail on `main`, because the rule, the helper and the
native tests don't exist there and the root still passes `planLegs`. The 4
pinned tests pass on `main` and after the change.

On `4f38424`, `test_native_tests_observe_the_root_rules` and
`test_root_recommendation_shows_only_when_real_and_allowed` (the helper is still
`private`) fail until Codex finishes the revision-4 work. The other ten tests
pass there, by hand tracing.

The sandbox again refused to run Python, so these results come from tracing
the code by hand:
- every self-check case through the corrected `_body` and `_test_functions`;
- every declaration the pinned tests read on `main` (`holeMapView`,
  `holeMapDetailView`, `currentShotLayout`, `distanceText`, `optionInstrument`,
  `drawMap`, `drawCurrentShot`, `drawFullPlan`, `drawPreparedPlan`,
  `centerRangeLabel`, `WatchHoleMapView`, `WatchCurrentShotLayout`,
  `WatchHoleMapRouteOverlay.resolve`). None of them has a declaration keyword
  between its name and its body outside brackets.

The gate is the authority.
