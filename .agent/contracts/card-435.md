# Card #435 — Start round: phone two pages, Watch tap tee to start

Make starting a round take fewer taps on the phone and the Watch, matching the
S70: picking the tee box starts the round.

Touches: `mobile/ios/AICaddie/Views/StartRoundView.swift`, `mobile/ios/AICaddie/Models/StartRoundPresentation.swift`, `mobile/ios/AICaddieWatch/Views/WatchRoundSetupView.swift`, `mobile/ios/AICaddieTests/StartRoundDiscoveryTests.swift`, `mobile/ios/AICaddieTests/DesignSnapshotTests.swift`, `mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift`, `mobile/ios/AICaddieUITests/**`, `tests/test_mobile_contracts.py`, `tests/test_native_visual_parity.py`, `tests/acceptance/test_card_435_start_round_pages.py`, `.agent/contracts/card-435.md`

Acceptance tests: `tests/acceptance/test_card_435_start_round_pages.py` (16 tests).

## Scope

In scope: phone and Watch UI, the pure presentation rules behind them, and
their Swift and Python source tests. No backend, migration, contract registry,
web, workflow or README change.

- The 9-hole loop rules in the design README §8
  (`docs/design/2026-09-25-ui-redesign/README.md`) stay unchanged. At the start,
  the phone picks only the first loop; the second loop is chosen at the turn.
  The Watch keeps its 前九 / 后九 tiles and its holes step as they are today.
- Do not edit any README in this PR. README §8 "开始一场" gets its update in a
  follow-up card after #434 merges.
- The PR touches `mobile/ios/**`, so the native acceptance gate applies:
  `native-mobile` must be green on the exact head, and the reviewer checks the
  `design-snapshots` and `watch-snapshots` artifacts (G4).

### Order relative to #434

#435 does not depend on #434, and #434 does not depend on #435. They can be
implemented in either order or at the same time. #435 touches no README and no
backend file. If #434's `Touches:` line names any file listed above, the
scheduler runs the two one after the other; otherwise they run in parallel. The
README §8 follow-up comes last, after both have merged, and describes the
two-page phone flow and the Watch tee tap. I could not read #434 from this
checkout, so this order rests on #435's own card text.

## Interface

### Phone — `StartRoundView` (G1, G2)

- `public enum Page: Equatable { case course, setup }`, nested in
  `StartRoundView`.
- New init parameter `initialPage: Page? = nil` (snapshots and tests only; the
  app passes nothing).
- `static func openingPage(initialPage: Page?, defaultCourseGlobalId: Int?) -> Page`:
  - `initialPage` when it is non-nil;
  - otherwise `.setup` when `defaultCourseGlobalId != nil` (换球场或组合, a
    resumed deep link);
  - otherwise `.course`.
- `@State private var page: Page`, initialised from `openingPage`. The two
  pages swap in place inside the existing navigation destination. There is no
  nested `navigationDestination`, because the hub's path-driven stack replaces
  the path when the round starts.
- **Page 1**, `private var coursePage: some View` (identifier
  `start-round-page-course`): `searchEntry` and `courseList` only. No loop
  tiles, no tees and no start button.
- **Page 2**, `private var setupPage: some View` (identifier
  `start-round-page-setup`):
  - `loopSection`, `teeSection`, and the pinned `startCard` in the existing
    `.safeAreaInset(edge: .bottom, spacing: 0) { … }` band with
    `start-round-pinned-actions` (the existing pin
    `test_ui_tests_never_tap_rows_under_the_pinned_start_band` must stay green);
  - the selected venue's name as the page heading;
  - a back control: a toolbar leading button with identifier
    `start-round-back-to-courses` that sets `page = .course`. While page 2 is
    shown, the system back button is hidden (`.navigationBarBackButtonHidden(`),
    so Back returns to page 1 and never to the home.
- `body` switches on `page` and shows `coursePage` or `setupPage`. The
  `.task`, `.sheet`, `.onAppear` and `.navigationTitle("开始一场")` modifiers
  stay on the outer view, so nearby discovery, tee loading and course-intent
  prefetch run on both pages.
- `private func showSetupPage()` sets `page = .setup`. These call it:
  - `selectCourseRow(_:)`, also when the tapped row is the venue already
    selected. The old early `return` for the same venue goes; the loop is kept
    through `preselectedLoop` (below);
  - `selectSearchResult(_:_:)`, after the selection is written.

  These never call it: `ensureDefaultSelection()`, `selectVenue(_:userInitiated:)`,
  `discoverNearbyCourses()`, `clearAutomaticSelection()`. A course that GPS
  auto-selects shows its checkmark on page 1, but the player still taps it.
- Back on page 1 keeps the selection: the row is checked, and tapping another
  row opens page 2 with that course.

### Phone — preselection rules, `StartRoundPresentation` (G2)

```swift
static func preselectedLoop(
    in loops: [MobileCourseOption],
    current: MobileCourseOption?,
    recent: MobileCourseOption?
) -> MobileCourseOption?

static func preselectedTee(lastUsed: String?, offered: [String], defaultTee: String?) -> String
```

`preselectedLoop`: the first rule that matches wins.
1. `current` is in `loops` (same `globalId`): return the element of `loops`.
2. `recent` is in `loops`: return that element of `loops` (the loop row, not
   the recent record).
3. Otherwise `loops.first`. An empty `loops` gives `nil`.

`preselectedTee`. A tee is *known* when, after trimming, it is non-empty and
not `unknown` (case-insensitive). Matching is case-insensitive, and a matched
tee is returned in the spelling `offered` uses. The first rule that matches
wins:
1. `lastUsed` is known and in `offered`: return it.
2. `lastUsed` is known and `offered` is empty: return `lastUsed` as given,
   trimmed.
3. `defaultTee` is known and in `offered`: return it.
4. `defaultTee` is known and `offered` is empty: return `defaultTee`, trimmed.
5. `offered` has a `blue`, else a `white`: return the first such tee in
   `offered` order. This is the old guess, now used only when nothing better is
   known.
6. `offered.first`, else `""`.

| # | lastUsed | offered | defaultTee | result |
|---|---|---|---|---|
| 1 | `"white"` | `["Gold","Blue","White"]` | `"blue"` | `"White"` |
| 2 | `"red"` | `["Gold","Blue","White"]` | `"blue"` | `"Blue"` |
| 3 | `nil` | `["Gold","Blue","White"]` | `"gold"` | `"Gold"` (the course default beats the blue/white guess; this is the behaviour change) |
| 4 | `"unknown"` | `["Gold","Blue","White"]` | `"gold"` | `"Gold"` |
| 5 | `nil` | `["Gold","Blue","White"]` | `"silver"` | `"Blue"` (a default the course does not offer is ignored) |
| 6 | `"  "` | `["Gold","Blue","White"]` | `nil` | `"Blue"` |
| 7 | `nil` | `["Gold","Red"]` | `nil` | `"Gold"` |
| 8 | `"white"` | `[]` | `"blue"` | `"white"` |
| 9 | `nil` | `[]` | `"blue"` | `"blue"` |
| 10 | `nil` | `[]` | `nil` | `""` |

How `StartRoundView` uses them:
- **Loop.** `selectCourseRow` picks the loop with
  `StartRoundPresentation.preselectedLoop(in: row.segments, current: selectedSegment, recent: recentResolvedCourseOption)`
  instead of `row.segments.first`. A 换球场或组合 entry keeps the caller's loop,
  because that loop is the current selection. An 18-hole course still opens on
  前九.
- **Last used tee** for the selected venue, in this order:
  - the tee of `recentCourseOption`, when it is at the same physical venue;
  - else the caller's `defaultTeeBox`, when the selection is the caller's
    `defaultCourseGlobalId` venue;
  - else `nil`.
- **Tee on selection.** When a course is selected (row, loop tile, search
  result), the tee is
  `preselectedTee(lastUsed:, offered: segment.tees ?? [], defaultTee: segment.teeBox)`.
  A manual search with no tee authority keeps its existing `unknown` request.
- **Tee after `/tees` answers.** The tee is
  `preselectedTee(lastUsed:, offered: rows.map(\.teeBox), defaultTee: rows.first(where: \.isDefault)?.teeBox)`,
  unless the player has tapped a tee chip on page 2 since this course was
  selected (`@State private var userPickedTee`). In that case a tee the rows
  offer is kept. A tapped tee the rows don't offer falls back to the rule.
  Selecting another course resets `userPickedTee`.
- `initialTee(callerTee:offered:courseTee:)`, `teeAfterRefresh(current:rows:)`
  and `selectionState(for:currentTeeBox:)` may stay as thin wrappers that call
  `preselectedTee`, or they may go. Update `StartRoundDiscoveryTests` and the
  existing pin lines in
  `test_ios_lands_on_hub_with_choices_and_keeps_dark_chrome_live_only` (which
  quote `Self.initialTee(` and `Self.teeAfterRefresh(`) to match. Do not delete
  the behaviour they protect: the card's last tee still wins when it is
  offered.

### Watch — `WatchRoundSetupView` (G3)

- The holes stage (`holeSelection` / `holeSelectionContent`, loop choices and
  前九 / 后九) is unchanged. Picking a holes choice still moves to the tee stage.
- `var teeSelectionContent: some View` is the tee stage without its
  `ScrollView`, as `holeSelectionContent` is. `teeSelection` wraps it. The file
  keeps exactly two `.ignoresSafeArea(edges: .top)`, as
  `test_watch_scroll_surfaces_keep_horizontal_content_inside_the_rounded_display`
  requires.
- `var orderedTeeChoices: [WatchRoundSetupChoicePresentation]`:
  - the default tee first. The default is the loaded `/tees` row with
    `isDefault`, else the course's own `teeBox`, else the first tee;
  - then the other tees in `teeOptions` order;
  - `isSelected` (the highlight) is `true` for the first row only.

  Titles and details come from `teeChoice(for:isSelected:)`.
- Each tee row is a button with identifier
  `watch-setup-tee-\(teeBox.lowercased())`. Its action is `start(teeBox:)`. The
  default row is visibly highlighted (fill and checkmark, as the selected style
  today).
- **The round can always start.** When there are no tee choices (no tee data,
  or tees still loading), one row with identifier `watch-setup-tee-default`,
  titled `球场默认 T`, starts with the current `selectedTee` (`unknown` = the
  server's course default). While tees load, the progress line stays above that
  row. Keep the `return "unknown"` in `initialTee(for:)` (pinned by
  `test_watch_unknown_tee_does_not_fabricate_blue`).
- `func selection(teeBox: String) -> WatchCourseSelection` builds what a start
  submits, for that tee (front/back/half as `startSelection` does today).
  `startSelection` becomes `selection(teeBox: selectedTee)`.
- `func start(teeBox: String)`:
  - guards `!isPreparing && !didSubmitStart`;
  - sets `didSubmitStart = true` and `selectedTee = teeBox`;
  - calls `onStart(selection(teeBox: teeBox))`.

  It builds the selection from its argument, never from `@State`, so a unit
  test can call it on an unmounted view. It is the only call to `onStart` in
  the file.
- While `isPreparing || didSubmitStart`, the tee rows are disabled, and the
  tapped row shows a `ProgressView`. A new `errorMessage` re-enables them (the
  existing `onChange`).
- Remove the start button: `private var startAction`, the `watch-setup-start`
  identifier, and the button inside `setupFooter`. The availability line
  (`availabilityText · availabilityDetail`) stays under the tee rows.
  `startActionLabel` may go, along with its Swift test assertions.

### Swift tests Codex adds or updates

- `mobile/ios/AICaddieTests/StartRoundDiscoveryTests.swift`:
  - `func testOpeningPageIsCourseUnlessACourseIsPassed()` calls
    `StartRoundView.openingPage(` for: nil/nil → `.course`; nil/31795 →
    `.setup`; `.course`/31795 → `.course`; `.setup`/nil → `.setup`;
  - `func testPreselectedLoopPrefersCurrentThenRecentThenFirst()` has at least
    4 `StartRoundPresentation.preselectedLoop(` calls: current in loops; recent
    in loops; neither (first); empty (nil);
  - `func testPreselectedTeePrefersLastUsedThenCourseDefault()` has one
    `StartRoundPresentation.preselectedTee(` call per table row (at least 10).
- `mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift`:
  - `func testTeeChoicesListTheDefaultTeeFirstAndHighlighted()`: a course with
    `teeBox: "White"`, `tees: ["Blue", "White", "Red"]` gives
    `orderedTeeChoices` titles `["白 T", "蓝 T", "红 T"]` and `isSelected`
    `[true, false, false]`;
  - `func testTappingATeeStartsTheRoundWithThatTee()`: calls
    `.start(teeBox: "Red")` on a view whose `onStart` records the selection,
    and asserts one call with `teeBox == "Red"`. Also, for an 18-hole row,
    `firstHalf == "front"`;
  - `func testRenderWatchCourseSetupTees()` (G4).
- Update the existing Watch tests that read `startActionLabel` or the start
  button, and the UI journeys (`TeeSelectionUITests`, `RealFlowUITests`), so
  they go through page 2. A journey that taps a course row is now on page 2. A
  journey that changes course taps `start-round-back-to-courses` first. These
  journeys run only on `workflow_dispatch`, not on the PR check; say so in the
  PR body.

### Python source pins Codex adds (`tests/test_mobile_contracts.py`, class `MobileContractTests`)

- `test_ios_start_round_has_course_and_setup_pages`: pins the phone interface
  above (Page, `openingPage`, the two page bodies, `showSetupPage()` callers and
  non-callers, the back control, the preselection rules in use, and the
  one-loop start `StartRoundPresentation.startLoops(selected: course, half: startHalf)`).
- `test_watch_round_setup_tee_tap_starts_round`: pins the Watch interface above
  (`start(teeBox:)` as the only `onStart`, `orderedTeeChoices`, the row
  identifiers, the default row, no `watch-setup-start`, `teeSelectionContent`,
  the 前九 / 后九 tiles kept).

Both must pass, and `tests.test_mobile_contracts` and
`tests.test_native_visual_parity` must stay green as whole modules.

### G1 — The phone 开始一场 has two pages: pick the course, then loop + tee + start

1. `StartRoundView` declares `enum Page` with `course` and `setup`, the
   `initialPage: Page? = nil` init parameter, and
   `static func openingPage(initialPage: Page?, defaultCourseGlobalId: Int?) -> Page`.
2. `coursePage` holds `searchEntry` and `courseList`, and has no `loopSection`,
   `teeSection`, `startCard` or `start-round-pinned-actions`. `setupPage` holds
   `loopSection`, `teeSection`, `startCard` and `start-round-pinned-actions`.
   `body` shows both by `page`. The identifiers `start-round-page-course`,
   `start-round-page-setup` and `start-round-back-to-courses` exist, and the
   system back button is hidden on page 2.
3. `showSetupPage()` is called from `selectCourseRow` and `selectSearchResult`,
   and never from `ensureDefaultSelection`, `selectVenue`,
   `discoverNearbyCourses` or `clearAutomaticSelection`. `selectCourseRow` no
   longer returns early for the venue already selected.
4. `StartRoundDiscoveryTests` has `testOpeningPageIsCourseUnlessACourseIsPassed`
   with at least 4 `StartRoundView.openingPage(` calls.
5. The subprocess run of
   `MobileContractTests.test_ios_start_round_has_course_and_setup_pages` exits
   0 (also covers G2 and G5).
6. The subprocess run of the whole `tests.test_mobile_contracts` and
   `tests.test_native_visual_parity` modules exits 0, and its output names both
   new pins as `ok` (also covers G2–G5).

### G2 — Page 2 preselects the last used loop and tee, else the course default

7. `StartRoundPresentation` declares `preselectedLoop(in:current:recent:)` and
   `preselectedTee(lastUsed:offered:defaultTee:)` with the signatures above.
8. `StartRoundView`:
   - calls `StartRoundPresentation.preselectedLoop(` inside `selectCourseRow`;
   - has a `StartRoundPresentation.preselectedTee(` call whose arguments use
     `isDefault`;
   - calls `preselectedTee(` or the `teeAfterRefresh(` wrapper from
     `loadTees`;
   - keeps a `userPickedTee` state.
9. `StartRoundDiscoveryTests` has
   `testPreselectedLoopPrefersCurrentThenRecentThenFirst` (at least 4 calls)
   and `testPreselectedTeePrefersLastUsedThenCourseDefault` (at least 10
   calls).
- The `native-mobile` check runs these Swift tests. Green on the head is the
  pass condition for the rule table.

### G3 — On the Watch, tapping a tee starts the round; the default tee is first and highlighted; no start button

10. `WatchRoundSetupView` declares `func start(teeBox: String)` and
    `func selection(teeBox: String) -> WatchCourseSelection`. `onStart(` appears
    exactly once, inside `start(teeBox:)`. `watch-setup-start` and
    `var startAction` are gone.
11. `orderedTeeChoices` is declared. `teeSelectionContent` is declared and its
    rows call `start(teeBox:`. The identifiers `watch-setup-tee-\(` and
    `watch-setup-tee-default` and the title `球场默认 T` exist.
    `return "unknown"` is kept, and the file has exactly two
    `.ignoresSafeArea(edges: .top)`.
12. `WatchDesignSnapshotTests` has
    `testTeeChoicesListTheDefaultTeeFirstAndHighlighted` (asserting
    `["白 T", "蓝 T", "红 T"]` and `[true, false, false]`) and
    `testTappingATeeStartsTheRoundWithThatTee` (calling `.start(teeBox:`).
13. The subprocess run of
    `MobileContractTests.test_watch_round_setup_tee_tap_starts_round` exits 0
    (also covers G4 and G5).

### G4 — Snapshots show both phone pages and the Watch tee list

14. `DesignSnapshotTests` captures `full-start-page-course` with
    `initialPage: .course`, and `full-start-page-setup` with
    `initialPage: .setup` and the loop-B tee rows (`initialCourseTees:`).
15. `WatchDesignSnapshotTests` has `testRenderWatchCourseSetupTees`, which
    renders `teeSelectionContent` as `watch-course-setup-tees`, using the
    White-default fixture and asserting its order `["白 T", "蓝 T", "红 T"]`.
- Reviewer checks: `native-mobile` green on the exact head. In
  `design-snapshots`:
  - `full-start-page-course` shows only the search box and the course list;
  - `full-start-page-setup` shows the venue heading, the back control, the
    A/B/C tiles with B selected, tee dots with yards, and the pinned
    "从 B 场 开始 · 蓝 T".

  In `watch-snapshots`, `watch-course-setup-tees` shows 白 T first and
  highlighted, then 蓝 T and 红 T, and no start button.

### G5 — The 9-hole loop rules are unchanged (pinned)

16. Pinned:
    - the design README §8 still says that the start picks only the first loop
      and the second loop is chosen at the turn;
    - the phone start still prepares
      `StartRoundPresentation.startLoops(selected: course, half: startHalf)`;
    - the Watch still has `halfChoices` with `watch-setup-half-` and
      `holeSelectionContent`.

    This passes on `main` too. Cases 5, 6 and 13 run the same rules through the
    Codex pins.

## Not run

Python and shell commands were denied in this contract sandbox. The acceptance
tests have not been run. The expected results come from reading the code:
cases 1–15 fail on `main` (no `Page`, no preselection rules, no
`start(teeBox:)`, no new Swift tests or pins), and case 16 passes there and is
marked `# pinned`.
