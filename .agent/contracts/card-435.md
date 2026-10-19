# Card #435 — Start round: phone two pages, Watch tap tee to start

Make starting a round take fewer taps on the phone and the Watch, matching the
S70: picking the tee box starts the round.

Touches: `mobile/ios/AICaddie/Views/StartRoundView.swift`, `mobile/ios/AICaddie/Models/StartRoundPresentation.swift`, `mobile/ios/AICaddieWatch/Views/WatchRoundSetupView.swift`, `mobile/ios/AICaddieTests/StartRoundDiscoveryTests.swift`, `mobile/ios/AICaddieTests/DesignSnapshotTests.swift`, `mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift`, `mobile/ios/AICaddieUITests/**`, `tests/test_mobile_contracts.py`, `tests/test_native_visual_parity.py`, `tests/acceptance/test_card_435_start_round_pages.py`, `.agent/contracts/card-435.md`

Acceptance tests: `tests/acceptance/test_card_435_start_round_pages.py` (20 tests).

## Revision 3: acceptance hardened after the adversarial gate

The gate's adversarial check failed on head `2ec3485`. The revision-2 tests
were too weak. They matched text anywhere in a file, comments included. They
checked only the signatures of the pure rules, and they counted the Swift test
calls without checking the expected values. So a broken rule, or a Swift test
whose expected values were changed to match a broken rule, still passed.

Reading the head turned up a real G2 defect, and those tests did not catch it.
`loadTees` runs
`Self.teeAfterRefresh(current: teeBox, rows: tees)`, so the tee *guessed* when
the course was selected (blue/white) becomes `lastUsed`. That guess is always
offered, so the `/tees` default row never wins, and the card's behaviour change
does not happen. Revision 3 keeps the design and the page/Watch interface. It
changes four things:

- **The `/tees` refresh gets the real last used tee.** There is a new pure rule,
  `StartRoundPresentation.lastUsedTee(...)`, and
  `StartRoundView.teeAfterRefresh` takes a new signature,
  `(current:userPicked:lastUsed:rows:)`. The two-argument form goes. See
  "Phone — preselection rules".
- **Comments never count.** Every source check runs on the Swift text with
  `//` and `/* */` comments removed. Identifiers must sit in the modifier or
  body that uses them, not just somewhere in the file.
- **The Swift test tables are checked value by value.** The acceptance tests
  parse every `XCTAssertEqual` / `XCTAssertNil` call of the pure rules in the
  named Swift tests. They evaluate each call with a Python model of the rule
  in this contract and fail when the Swift expectation differs or a required
  case is missing. `native-mobile` then proves that the Swift rule meets those
  expectations.
- **More structure is pinned:**
  - `page` is assigned in exactly two places;
  - `showSetupPage()` has exactly two callers;
  - `selectCourseRow` has a single `return`;
  - the Watch `start(teeBox:)` guard and the order of its statements;
  - `selection(teeBox:)` never reads `selectedTee`;
  - the tee rows start the round through `teeChoices`;
  - the snapshot fixtures.

Relaxed: a `ProgressView` on the tapped Watch row only is no longer required.
While a start is pending, every tee row is disabled and shows a spinner, as the
head already does.

Implementation work still needed on top of `2ec3485`:
- phone: `lastUsedTee`, the new `teeAfterRefresh`, and the `loadTees` call;
- Swift tests: the new and extended Swift tests listed below;
- pins: update the existing pin line in `test_mobile_contracts.py` that quotes
  the old `teeAfterRefresh(current: teeBox, rows: tees)`, and the two Codex
  pins.

Codex must not edit `tests/acceptance/`.

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

#435 does not depend on #434, and #434 does not depend on #435. #435 touches no
README and no backend file. If #434's `Touches:` line names any file listed
above, the scheduler runs the two one after the other; otherwise they can run in
parallel. The README §8 follow-up comes last, after both have merged. I could
not read #434 from this checkout, so this order rests on #435's own card text.

## Interface

All source conditions below are checked on the Swift text with comments
removed.

### Phone — `StartRoundView` (G1)

- `public enum Page: Equatable { case course, setup }`, nested in
  `StartRoundView`, with exactly those two cases.
- New init parameter `initialPage: Page? = nil` (snapshots and tests only; the
  app passes nothing).
- `static func openingPage(initialPage: Page?, defaultCourseGlobalId: Int?) -> Page`:
  - `initialPage` when it is non-nil;
  - otherwise `.setup` when `defaultCourseGlobalId != nil` (换球场或组合, a
    resumed deep link);
  - otherwise `.course`.
- `@State private var page: Page`, initialised in `init` with
  `_page = State(initialValue: Self.openingPage(initialPage: initialPage, defaultCourseGlobalId: defaultCourseGlobalId))`.
  The two pages swap in place inside the existing navigation destination; there
  is no nested `navigationDestination`.
- **Page 1**, `private var coursePage: some View`:
  - contains `searchEntry` and `courseList`, and has
    `.accessibilityIdentifier("start-round-page-course")`;
  - contains no `loopSection`, `teeSection`, `startCard` or
    `start-round-pinned-actions`.
- **Page 2**, `private var setupPage: some View`:
  - `.accessibilityIdentifier("start-round-page-setup")`;
  - `selectedVenueName` as the page heading;
  - `loopSection` and `teeSection`;
  - the pinned `startCard` in `.safeAreaInset(edge: .bottom, spacing: 0) { … }`
    with `start-round-pinned-actions` (the existing pin
    `test_ui_tests_never_tap_rows_under_the_pinned_start_band` must stay green);
  - a back control with
    `.accessibilityIdentifier("start-round-back-to-courses")` whose action is
    `page = .course`.
- `body`:
  - shows `coursePage` or `setupPage` depending on `page` (`if page == …` or
    `switch page`);
  - carries `.navigationBarBackButtonHidden(page == .setup)` (or
    `page != .course`), so on page 2 Back returns to page 1 and never to the
    home;
  - keeps `.navigationTitle("开始一场")`, `.task(id: courseGlobalIdText)`,
    `.task(id: nearbyDiscoveryTaskKey)` and
    `.sheet(isPresented: $showingCourseSearch)`. These modifiers are not
    repeated inside `coursePage` / `setupPage`, so nearby discovery, tee
    loading and course search run on both pages.
- `page` is assigned in exactly two places in the file:
  - `page = .setup` inside `private func showSetupPage()`;
  - `page = .course` inside `setupPage` (the back control).
- `showSetupPage()` has exactly two callers:
  - `selectCourseRow(_:)`, also when the tapped row is the venue already
    selected;
  - `selectSearchResult(_:_:)`, after `applySelectedCourse(`.

  `ensureDefaultSelection()`, `selectVenue(_:userInitiated:)`,
  `discoverNearbyCourses()`, `clearAutomaticSelection()`, `selectLoop(_:)` and
  `loadTees()` never call it. A course that GPS auto-selects shows its checkmark
  on page 1, but the player still taps it.
- `selectCourseRow` contains exactly one `return`: the `else { return }` of its
  opening `guard let … = StartRoundPresentation.preselectedLoop(` (an empty
  row). The old early return for the venue already selected is gone.
- Back on page 1 keeps the selection: the row is checked, and tapping another
  row opens page 2 with that course.

### Phone — preselection rules (G2)

Three pure rules in `enum StartRoundPresentation`
(`mobile/ios/AICaddie/Models/StartRoundPresentation.swift`):

```swift
static func preselectedLoop(
    in loops: [MobileCourseOption],
    current: MobileCourseOption?,
    recent: MobileCourseOption?
) -> MobileCourseOption?

static func preselectedTee(lastUsed: String?, offered: [String], defaultTee: String?) -> String

static func lastUsedTee(
    selectedVenue: String,
    recentVenue: String?,
    recentTee: String?,
    callerVenue: String?,
    callerTee: String?
) -> String?
```

And one in `StartRoundView`, which replaces `teeAfterRefresh(current:rows:)`:

```swift
static func teeAfterRefresh(current: String, userPicked: Bool, lastUsed: String?, rows: [CourseTee]) -> String
```

A tee is *known* when, after trimming whitespace, it is non-empty and not
`unknown` (case-insensitive). Tees match case-insensitively after trimming. A
matched tee is returned in the spelling of the offered list or row.

**`preselectedLoop`**: the first rule that matches wins.
1. `current` is in `loops` (same `globalId`): return that element of `loops`.
2. `recent` is in `loops`: return that element of `loops`.
3. Otherwise `loops.first`. An empty `loops` gives `nil`.

**`preselectedTee`**: the first rule that matches wins.
1. `lastUsed` is known and in `offered`: return the offered spelling.
2. `lastUsed` is known and `offered` is empty: return `lastUsed`, trimmed.
3. `defaultTee` is known and in `offered`: return the offered spelling.
4. `defaultTee` is known and `offered` is empty: return `defaultTee`, trimmed.
5. The first tee in `offered` order that is `blue` or `white`. This is the old
   guess, now used only when nothing better is known.
6. `offered.first`, else `""`.

| # | lastUsed | offered | defaultTee | result |
|---|---|---|---|---|
| T1 | `"white"` | `["Gold","Blue","White"]` | `"blue"` | `"White"` |
| T2 | `"red"` | `["Gold","Blue","White"]` | `"blue"` | `"Blue"` |
| T3 | `nil` | `["Gold","Blue","White"]` | `"gold"` | `"Gold"` (the course default beats the guess: the behaviour change) |
| T4 | `"unknown"` | `["Gold","Blue","White"]` | `"gold"` | `"Gold"` |
| T5 | `nil` | `["Gold","Blue","White"]` | `"silver"` | `"Blue"` (a default the course does not offer is ignored) |
| T6 | `"  "` | `["Gold","Blue","White"]` | `nil` | `"Blue"` |
| T7 | `nil` | `["Gold","Red"]` | `nil` | `"Gold"` |
| T8 | `"white"` | `[]` | `"blue"` | `"white"` |
| T9 | `nil` | `[]` | `"blue"` | `"blue"` |
| T10 | `nil` | `[]` | `nil` | `""` |

**`lastUsedTee`**: the tee the player last used at the selected venue. Two
venues match when both are non-empty after trimming and are equal ignoring
case.
1. `recentVenue` matches `selectedVenue` and `recentTee` is known: return
   `recentTee`, trimmed.
2. `callerVenue` matches `selectedVenue` and `callerTee` is known: return
   `callerTee`, trimmed.
3. Otherwise `nil`.

| # | selectedVenue | recentVenue | recentTee | callerVenue | callerTee | result |
|---|---|---|---|---|---|---|
| L1 | `"黑骑士"` | `"黑骑士"` | `"white"` | `"黑骑士"` | `"blue"` | `"white"` |
| L2 | `"黑骑士"` | `"北湖"` | `"white"` | `"黑骑士"` | `"blue"` | `"blue"` |
| L3 | `"黑骑士"` | `"黑骑士"` | `"unknown"` | `"黑骑士"` | `"blue"` | `"blue"` |
| L4 | `"黑骑士"` | `"北湖"` | `"white"` | `nil` | `nil` | `nil` |
| L5 | `"黑骑士"` | `" 黑骑士 "` | `" Red "` | `nil` | `nil` | `"Red"` |
| L6 | `"黑骑士"` | `nil` | `nil` | `"黑骑士"` | `"unknown"` | `nil` |
| L7 | `""` | `""` | `"white"` | `nil` | `nil` | `nil` |

**`teeAfterRefresh`**: what the tee becomes when `/tees` answers with `rows`.
1. `userPicked` is true, `current` is known and `rows` offer it: return that
   row's `teeBox`.
2. Otherwise
   `StartRoundPresentation.preselectedTee(lastUsed: lastUsed, offered: rows.map(\.teeBox), defaultTee: rows.first(where: \.isDefault)?.teeBox)`.

`current` is never passed as `lastUsed`. That is the head's defect: the tee
guessed on selection would always win.

Fixtures (`CourseTee(teeBox:name:…:isDefault:)`, lowercase `teeBox` values, in
this order): `goldDefault` = `gold` (`isDefault: true`), `blue`, `white`;
`noDefault` = `gold`, `blue`, `white` with no default.

| # | current | userPicked | lastUsed | rows | result |
|---|---|---|---|---|---|
| R1 | `"blue"` | `false` | `nil` | goldDefault | `"gold"` (the guessed Blue no longer wins) |
| R2 | `"white"` | `true` | `nil` | goldDefault | `"white"` |
| R3 | `"red"` | `true` | `nil` | goldDefault | `"gold"` (a tapped tee the rows don't offer falls back) |
| R4 | `"blue"` | `false` | `"White"` | goldDefault | `"white"` |
| R5 | `""` | `false` | `"red"` | goldDefault | `"gold"` |
| R6 | `"gold"` | `false` | `nil` | noDefault | `"blue"` |

How `StartRoundView` uses them:
- **Loop.** `selectCourseRow` opens with
  `guard let … = StartRoundPresentation.preselectedLoop(in: row.segments, current: selectedSegment, recent: recentResolvedCourseOption) else { return }`.
  A 换球场或组合 entry keeps the caller's loop, because that loop is the
  current selection. An 18-hole course still opens on 前九.
- **Caller inputs.** `init` stores `defaultCourseGlobalId` and `defaultTeeBox`
  in `private let callerCourseGlobalId: Int?` and
  `private let callerTeeBox: String`.
- **Last used tee.** `private var lastUsedTee: String?` returns `nil` without a
  `selectedSegment`. Otherwise it returns
  `StartRoundPresentation.lastUsedTee(selectedVenue:recentVenue:recentTee:callerVenue:callerTee:)`
  with:
  - `selectedVenue`: `Self.courseVenueName(selectedSegment)`;
  - the recent pair: from the raw `recentCourseOption` (its `teeBox` is the
    tee of the last start; the resolved option takes the catalogue's tee);
  - the caller pair: the venue of the option with `callerCourseGlobalId`
    (looked up as `init` does), and `callerTeeBox`.

  `recentTee:` and `callerTee:` are not the literal `nil`.
- **Tee after `/tees` answers.** `loadTees` sets
  `teeBox = Self.teeAfterRefresh(current: teeBox, userPicked: userPickedTee, lastUsed: lastUsedTee, rows: tees)`.
  It no longer wraps that line in `if !userPickedTee`, because the rule
  handles it. No `teeAfterRefresh(current:rows:)` remains, in the view or in
  the Swift tests.
- **Tapped tee.** `@State private var userPickedTee` is set to `true` in
  `teeChip`'s action and to `false` in `applySelectedCourse`, so selecting
  another course resets it.
- **Tee on selection** is unchanged from the head:
  - `selectionState(for:currentTeeBox:)` / `initialTee(callerTee:offered:courseTee:)`
    remain thin wrappers over `preselectedTee`;
  - a manual search with no tee authority keeps its `unknown` request;
  - when `/tees` answers, the refresh rule above decides.
- `testChangeCourseKeepsTheCardsLastTeeWhenTheCourseOffersIt` keeps its
  behaviour: the card's last tee, White, still wins over the Blue default row,
  now through `teeAfterRefresh(current:userPicked:lastUsed: "white", rows:)`.
  Update the existing pin line in
  `test_ios_lands_on_hub_with_choices_and_keeps_dark_chrome_live_only`, which
  quotes `teeBox = Self.teeAfterRefresh(current: teeBox, rows: tees)`, to the
  new call.

### Watch — `WatchRoundSetupView` (G3)

- The holes stage (`holeSelection` / `holeSelectionContent`, loop choices and
  前九 / 后九) is unchanged. Picking a holes choice still moves to the tee stage.
- `var teeSelectionContent: some View` is the tee stage without its
  `ScrollView`; `teeSelection` wraps it. The file keeps exactly two
  `.ignoresSafeArea(edges: .top)`.
- `var orderedTeeChoices: [WatchRoundSetupChoicePresentation]`:
  - first the default tee: the `teeOptions` row with `isDefault`, else the row
    matching the course's `teeBox`, else the first row;
  - then the other tees in `teeOptions` order;
  - `isSelected` (the highlight) is `true` for the first row only. Empty when
    there are no tee options.
- `var teeChoices: [WatchRoundSetupChoicePresentation]` is `orderedTeeChoices`.
  When that is empty, it is one row titled `球场默认 T`, with `isSelected: true`.
- `teeSelectionContent` lists `teeChoices` in a `ForEach`. Each row's action
  calls `start(teeBox:)`. The default row starts with the current `selectedTee`
  (`unknown` = the server's course default), so a round can always start, also
  while tees are loading; the loading line stays above the rows. The
  availability line (`availabilityText`) stays under the rows. Keep the
  `return "unknown"` in `initialTee(for:)`.
- Row identifiers are set with `.accessibilityIdentifier(`:
  - `"watch-setup-tee-\(…)"` (the lowercased tee) for a tee row;
  - `"watch-setup-tee-default"` for the default row.

  The highlighted row has a fill and a checkmark.
- `func selection(teeBox: String) -> WatchCourseSelection` builds what a start
  submits for that tee:
  - it passes `teeBox: teeBox` and sets `firstHalf` from `selectedHalf` for an
    18-hole course;
  - it never reads `selectedTee` (the `withTees(…, selectedTee: teeBox)`
    argument label is fine).

  `var startSelection` is `selection(teeBox: selectedTee)`.
- `func start(teeBox: String)`:
  - opens with `guard !isPreparing, !didSubmitStart else { return }` (or
    `&&`);
  - then sets `selectedTee = teeBox` and `didSubmitStart = true`;
  - then calls `onStart(selection(teeBox: teeBox))`.

  `onStart(` appears exactly once in the file, there.
- While `isPreparing || didSubmitStart`, the tee rows are disabled
  (`.disabled(isPreparing || didSubmitStart)`) and show a `ProgressView`. A new
  `errorMessage` re-enables them (the existing `onChange`).
- Removed: `var startAction`, the `watch-setup-start` identifier and any start
  button. `startActionLabel` may go.

### Swift tests Codex adds or updates

`mobile/ios/AICaddieTests/StartRoundDiscoveryTests.swift`. Every rule call
below is written inline, with literal arguments, as
`XCTAssertEqual(<Type>.<rule>(<labelled args>), <expected>)`, or as
`XCTAssertNil(<Type>.<rule>(…))` for a `nil` result:
- `testOpeningPageIsCourseUnlessACourseIsPassed`: the four
  `StartRoundView.openingPage(` cases:
  - `nil` / `nil` gives `.course`;
  - `nil` / `31795` gives `.setup`;
  - `.course` / `31795` gives `.course`;
  - `.setup` / `nil` gives `.setup`.
- `testPreselectedLoopPrefersCurrentThenRecentThenFirst`:
  `let loops = [blackKnight(31794, "A"), blackKnight(31795, "B"), blackKnight(31796, "C")]`
  and these five assertions:
  - `preselectedLoop(in: loops, current: loops[2], recent: loops[1])?.globalId` is `31796`;
  - `preselectedLoop(in: loops, current: nil, recent: loops[1])?.globalId` is `31795`;
  - `preselectedLoop(in: loops, current: otherVenue, recent: loops[1])?.globalId` is `31795`;
  - `preselectedLoop(in: loops, current: otherVenue, recent: nil)?.globalId` is `31794`;
  - `XCTAssertNil(StartRoundPresentation.preselectedLoop(in: [], current: nil, recent: otherVenue))`.
- `testPreselectedTeePrefersLastUsedThenCourseDefault`: T1–T10.
- `testLastUsedTeeIsTheRecentThenTheCallerTeeAtThisVenue`: L1–L7, calling
  `StartRoundPresentation.lastUsedTee(`.
- `testTeeAfterRefreshPrefersTheDefaultRowOverTheGuess`: declares
  `let goldDefault = [CourseTee(…), …]` and `let noDefault = [CourseTee(…), …]`
  with literal `teeBox:` / `isDefault:` values, and asserts R1–R6 with
  `StartRoundView.teeAfterRefresh(current:userPicked:lastUsed:rows:)`. Rows
  are passed by those names.

Every asserted call of these rules in those functions must agree with the
tables. Extra cases are welcome, as long as they follow the rules.

`mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift`:
- `testTeeChoicesListTheDefaultTeeFirstAndHighlighted`, with
  `tees: ["Blue", "White", "Red"]` throughout:
  - `teeBox: "White"` gives `orderedTeeChoices` titles
    `["白 T", "蓝 T", "红 T"]` and `isSelected` `[true, false, false]`;
  - `teeBox: "Red"` gives `["红 T", "蓝 T", "白 T"]`;
  - no `teeBox` gives `["蓝 T", "白 T", "红 T"]` (`map(\.title)` and
    `map(\.isSelected)` assertions).
- `testATeeLessCourseOffersTheCourseDefaultRow`: a course with no tees and no
  `teeBox` gives `teeChoices.map(\.title)` `["球场默认 T"]` and
  `teeChoices.map(\.isSelected)` `[true]`.
- `testTappingATeeStartsTheRoundWithThatTee`:
  - calls `.start(teeBox: "Red")` on a view whose `onStart` records the
    selection;
  - asserts `teeBox` `"Red"` and `firstHalf` (nil for a 9-hole row).
- `testRenderWatchCourseSetupTees` (G4).
- Update the existing Watch tests that read `startActionLabel` or the start
  button, and the UI journeys (`TeeSelectionUITests`, `RealFlowUITests`), so
  they go through page 2. A journey that changes course taps
  `start-round-back-to-courses` first. These journeys run only on
  `workflow_dispatch`, not on the PR check; say so in the PR body.

### Python source pins Codex keeps (`tests/test_mobile_contracts.py`, class `MobileContractTests`)

- `test_ios_start_round_has_course_and_setup_pages`: the phone interface above,
  now including `lastUsedTee` and the new `teeAfterRefresh` call.
- `test_watch_round_setup_tee_tap_starts_round`: the Watch interface above.

Both must pass, and `tests.test_mobile_contracts` and
`tests.test_native_visual_parity` must stay green as whole modules, including
these existing pins:
- `test_ios_lands_on_hub_with_choices_and_keeps_dark_chrome_live_only`;
- `test_ui_tests_never_tap_rows_under_the_pinned_start_band`;
- `test_watch_unknown_tee_does_not_fabricate_blue`;
- `test_watch_scroll_surfaces_keep_horizontal_content_inside_the_rounded_display`.

### G1 — The phone 开始一场 has two pages: pick the course, then loop + tee + start

1. `enum Page` has exactly `course` and `setup`. The file has the
   `initialPage: Page? = nil` parameter, the `openingPage` signature,
   `@State private var page: Page` and the `_page = State(initialValue: Self.openingPage(…))`
   initialisation.
2. Page bodies, identifiers and the back control: `coursePage` and `setupPage`
   hold exactly what is listed above. `body` switches on `page`, hides the
   system back button on page 2 and keeps the shared modifiers, which are not
   repeated inside the pages.
3. Page changes and callers: `page` is assigned only in `showSetupPage`
   (`.setup`) and in `setupPage` (`.course`). `showSetupPage()` has exactly two
   callers, `selectCourseRow` and `selectSearchResult` (after
   `applySelectedCourse(`), and none of the six automatic functions calls it.
   `selectCourseRow` has a single `return`, in its `preselectedLoop` guard.
4. `testOpeningPageIsCourseUnlessACourseIsPassed` asserts the four opening
   cases, and each agrees with the rule.
5. A subprocess run of
   `MobileContractTests.test_ios_start_round_has_course_and_setup_pages` exits
   0 (also covers G2 and G5).
6. A subprocess run of the whole `tests.test_mobile_contracts` and
   `tests.test_native_visual_parity` modules exits 0. Its output names as `ok`
   both new pins and the four existing pins listed above (also covers G2–G5).

### G2 — Page 2 preselects the last used loop and tee, else the course default

7. `StartRoundPresentation` declares `preselectedLoop`, `preselectedTee` and
   `lastUsedTee` with the signatures above. `StartRoundView` declares the new
   `teeAfterRefresh`. Its body calls `StartRoundPresentation.preselectedTee(`
   with `lastUsed: lastUsed` and `isDefault`, never with `lastUsed: current`,
   and reads `userPicked`. No two-argument `teeAfterRefresh(current:rows:)`
   remains in the view or the Swift tests.
8. `StartRoundView` wiring:
   - the `preselectedLoop` guard opens `selectCourseRow`;
   - `private var lastUsedTee: String?` calls
     `StartRoundPresentation.lastUsedTee(` with a non-`nil` `recentTee:` and
     `callerTee:`;
   - `loadTees` runs the exact `teeAfterRefresh(current: teeBox, userPicked: userPickedTee, lastUsed: lastUsedTee, rows: tees)`
     assignment, with no `if !userPickedTee`;
   - `userPickedTee` is set to `true` in `teeChip` and to `false` in
     `applySelectedCourse`.
9. The four Swift preselection tests above exist. Every asserted rule call in
   them agrees with the contract's model of the rule, and every required case
   (loop ×5, T1–T10, L1–L7, R1–R6) is present.

- `native-mobile` runs these Swift tests. Green on the exact head proves the
  Swift rules match the tables.

### G3 — On the Watch, tapping a tee starts the round; the default tee is first and highlighted; no start button

10. `start(teeBox:)` has the guard first, then `selectedTee = teeBox` and
    `didSubmitStart = true`, then `onStart(selection(teeBox: teeBox))`. It is
    the file's only `onStart(`. `selection(teeBox:)` passes `teeBox: teeBox`,
    uses `selectedHalf` for `firstHalf`, and never reads `selectedTee`.
    `startSelection` is `selection(teeBox: selectedTee)`. `watch-setup-start`
    and `var startAction` are gone.
11. Tee rows:
    - `orderedTeeChoices` reads `isDefault`, and `teeChoices` reads
      `orderedTeeChoices` and has the `球场默认 T` row;
    - `teeSelectionContent` has a `ForEach` over `teeChoices` whose row action
      calls `start(teeBox:`, and it shows `availabilityText`;
    - both `.accessibilityIdentifier(` forms exist;
    - the rows are disabled while a start is pending;
    - `return "unknown"` is kept, and the file has exactly two
      `.ignoresSafeArea(edges: .top)`.
12. The three Watch Swift tests assert the three orders, the default row and
    the tap start as listed above.
13. A subprocess run of
    `MobileContractTests.test_watch_round_setup_tee_tap_starts_round` exits 0
    (also covers G4 and G5).

### G4 — Snapshots show both phone pages and the Watch tee list

14. `DesignSnapshotTests` captures:
    - `full-start-page-course` with `initialPage: .course`;
    - `full-start-page-setup` with `initialPage: .setup`,
      `defaultCourseGlobalId: 31795`, `initialCourseTees: loopBTees` and
      `onLoadCourseTees: { _ in loopBTees }`.
15. `testRenderWatchCourseSetupTees` builds the White-default fixture
    (`teeBox: "White"`, `tees: ["Blue", "White", "Red"]`), asserts the order
    `["白 T", "蓝 T", "红 T"]`, and renders `teeSelectionContent` as
    `watch-course-setup-tees`.

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
    pins.

## Not run

Python was denied in this contract sandbox, so I have not run the acceptance
tests; the results below come from reading the code.
- On `main`, cases 1–15 fail (no `Page`, no preselection rules, no
  `start(teeBox:)`, no new Swift tests or pins).
- Case 16 passes on `main` and is marked `# pinned`.
- On head `2ec3485`, these cases fail until the remaining work above lands:
  - 7 and 8 (`lastUsedTee`, the new `teeAfterRefresh`);
  - 9 (the new Swift tests and the fifth loop case);
  - 12 (the extra Watch orders and the default-row test).
- Case 6 stays green only if the existing pin line that quotes the old
  `teeAfterRefresh(current: teeBox, rows: tees)` call is updated together with
  `loadTees`.
