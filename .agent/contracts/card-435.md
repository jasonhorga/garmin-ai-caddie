# Card #435 — Start round: two phone pages, Watch tee tap starts

The goal is fewer taps to start a round on phone and Watch, matching S70 (picking the
tee box starts the hole). This card changes only the native iPhone and Watch UI: no
backend, migration, contract or README edits.

Touches: `mobile/ios/AICaddie/Views/StartRoundView.swift`, `mobile/ios/AICaddie/Models/StartRoundPresentation.swift`, `mobile/ios/AICaddieWatch/Views/WatchRoundSetupView.swift`, `mobile/ios/AICaddieWatch/Views/WatchUITestRoot.swift`, `mobile/ios/AICaddieTests/StartRoundDiscoveryTests.swift`, `mobile/ios/AICaddieTests/DesignSnapshotTests.swift`, `mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift`, `mobile/ios/AICaddieUITests/*.swift`, `tests/test_mobile_contracts.py`, `tests/test_native_visual_parity.py`, `tests/acceptance/test_card_435_start_round_pages.py`, `.agent/contracts/card-435.md`

Acceptance tests: `tests/acceptance/test_card_435_start_round_pages.py`

## How this card is accepted

Linux CI has no Swift toolchain, so the Python acceptance suite cannot run the SwiftUI
views. Acceptance has three layers:

1. **Python acceptance (offline, `backend` job).** These tests read the Swift sources and
   Swift tests and check the interface below. Each goal also runs the repository's
   native-source contract tests (`tests/test_mobile_contracts.py`) as a subprocess.
2. **`native-mobile` CI (macOS).** It runs the Swift unit and snapshot tests named
   below. It must be green on the PR head (the native acceptance gate).
3. **Review of the artifacts.** The reviewer opens `design-snapshots`
   (`full-start-page-course.png`, `full-start-page-setup.png`) and `watch-snapshots`
   (`watch-course-setup-tees.png`). In the review, they say what they checked: page 1
   is the course list only; page 2 shows the loop, the tee and the start button; on the
   Watch, the default tee is first and highlighted and there is no start button.

Real-device behaviour is the owner's evidence. Simulator or CI results never stand in
for it.

## Interface

### Phone — `StartRoundView` (two pages)

- `public enum Page: Equatable { case course, setup }` is nested in `StartRoundView`
  (`StartRoundView.Page`).
- New trailing init parameter: `initialPage: Page? = nil` (for snapshot fixtures; the app
  passes nothing).
- `static func openingPage(initialPage: Page?, defaultCourseGlobalId: Int?) -> Page`:
  - when `initialPage` is given, return it, but `.setup` without a course
    (`defaultCourseGlobalId == nil`) gives `.course`;
  - otherwise `.setup` when the caller passes a course (the home's 换球场或组合 carries the
    course here, so its loop and tee are one tap away), else `.course`.
- **Page 1 (course page):** `private var coursePage: some View` (a `@ViewBuilder` is
  allowed). It holds the search entry (`searchEntry`) and the one course list
  (`courseList`), with the waiting line and the nearby-retry icon unchanged. The root
  has `.accessibilityIdentifier("start-round-course-page")`. Page 1 has no loop tiles,
  no tees and no start button. The navigation title stays 开始一场. The current
  selection is still checked in the list.
- **Page 2 (setup page):** `private var setupPage: some View`. It holds the loop section
  (`loopSection`, including 前九 / 后九 for an 18-hole course), the tee section
  (`teeSection`) and the start card (`startCard`), pinned in the bottom band exactly as
  today (`.safeAreaInset(edge: .bottom, spacing: 0)`, identifier
  `start-round-pinned-actions`). The root has
  `.accessibilityIdentifier("start-round-setup-page")`. Page 2 has no course list and
  no search entry. Suggested title: the selected venue's name.
- `start-round-primary-action` exists once in the file, on page 2 only. Its label and
  rules are unchanged (`startActionTitle`, `canStart`, one loop via
  `StartRoundPresentation.startLoops(selected: course, half: startHalf)`).
- **Navigation.**
  - `private func showSetupPage()` moves to page 2. It is called from
    `selectCourseRow` (a row tap, including a tap on the already-selected venue) and
    from `selectSearchResult` (a pick in the search sheet).
  - Automatic selection never changes the page: `ensureDefaultSelection`,
    `selectVenue` and `discoverNearbyCourses` do not call `showSetupPage()`.
  - Back from page 2 returns to page 1 with the selection kept. Either:
    - page 2 is pushed with `.navigationDestination(isPresented:)`, so the system back
      button and the swipe work; or
    - page 2 replaces page 1 and shows a back control with the identifier
      `start-round-back-to-courses`.
  - After Start, the Hub still replaces the path with the live hole, as today.

### Phone — page 2 preselection (`StartRoundPresentation`)

`static func preselectedLoop(in row: StartCourseListRow, current: MobileCourseOption?, recent: MobileCourseOption?) -> MobileCourseOption?`
returns the first of these:

1. `current`, when it is at the row's physical venue (`StartRoundView.samePhysicalVenue`).
   Tapping the selected venue keeps its loop;
2. the row segment whose `globalId` is `recent?.globalId` (the last used loop);
3. `row.segments.first`.

It returns `nil` only for a row with no segments. `selectCourseRow` uses it.

`static func preselectedTee(lastUsed: [String?], offered: [String], defaultTee: String?) -> String`:

- Known tee = trimmed, non-empty and not `unknown` (case-insensitive).
- Returns the first of these:
  1. the first known `lastUsed` entry, in order, that `offered` contains
     (case-insensitive), using `offered`'s spelling. When `offered` is empty, the first
     known `lastUsed` entry as given;
  2. a known `defaultTee` (the course default), when `offered` is empty or contains it,
     using `offered`'s spelling;
  3. the first `offered` tee that is blue or white, else `offered.first`;
  4. `""`.

How the view calls it:

- `lastUsed` is, in order:
  1. a tee the player tapped on page 2 during this visit;
  2. the selected course row's stored `teeBox`;
  3. the caller's `defaultTeeBox` (the home card's last tee).
- `offered` is the `/tees` rows' `teeBox` once they arrive, else the course's own tee
  names.
- `defaultTee` is the `/tees` row with `isDefault`, and `nil` before the rows arrive.
- The view recomputes on course or loop change and when `/tees` answers. A tee the
  player chose stays if it is offered. A blue/white guess gives way to the course
  default when the rows arrive.
- `StartRoundView.swift` calls `StartRoundPresentation.preselectedTee(` at least
  twice: on selection and on the `/tees` refresh. `initialTee`, `selectionState` and
  `teeAfterRefresh` may delegate to it or be removed.
- A manual search with no tee authority still falls back to `unknown`, as today.

### Watch — `WatchRoundSetupView` (tap a tee to start)

- The course and the holes / which-9 stage are unchanged. This includes the 前九 / 后九
  tiles (`watch-setup-half-*`) and today's loop choices.
- **No start button.** The `startAction` view and the `watch-setup-start` identifier
  are removed.
- `func startSelection(teeBox: String) -> WatchCourseSelection` returns what a tap on
  that tee submits:
  - the selected loop(s) or half;
  - `teeBox`;
  - `ensureGeometry`, passed through.

  The existing `startSelection` property may remain as `startSelection(teeBox: selectedTee)`.
- `private func start(teeBox: String)`:
  - guards `!isPreparing, !didSubmitStart`;
  - sets `selectedTee` and `didSubmitStart = true`;
  - calls `onStart(startSelection(teeBox: teeBox))`.

  This is the only `onStart(` call in the file. An `errorMessage` re-enables the rows,
  as today.
- `static func orderedTeeChoices(_ tees: [WatchCourseTee], preselected: String) -> [WatchRoundSetupChoicePresentation]`:
  - the default tee is listed first and highlighted (`isSelected == true`). The
    default is the first match of:
    1. the tee equal to `preselected` (case-insensitive);
    2. the `isDefault` tee;
    3. the first tee;
  - the others follow in input order, not selected;
  - exactly one choice is selected when `tees` is non-empty. Empty input gives `[]`;
  - `teeChoices` returns `Self.orderedTeeChoices(teeOptions, preselected: selectedTee)`.
- `var teeSelectionContent: some View` is the tee stage without its ScrollView, for
  snapshots, like `holeSelectionContent`. The tee stage's ScrollView wraps it. Each row
  is a button:
  - its action calls `start(teeBox:)`;
  - its identifier is `watch-setup-tee-<teeBox lowercased>`;
  - it has `.disabled(isPreparing || didSubmitStart)`.

  While a start is being prepared, the tapped row shows a small progress indicator.
- **No tee rows.** While loading, or with no tee data, the loading line or the
  "发球台资料稍后补齐" line stays. Under it, one row 球场默认 T (identifier
  `watch-setup-tee-default`) starts with the current `selectedTee`, so a round can
  always start without a separate button.
- The availability line (已有离线版本 / 可立即开局 …) may stay as a small caption.
  `startActionLabel` may be removed; update its Swift tests if it is.

## Required native tests (run by `native-mobile`)

`mobile/ios/AICaddieTests/StartRoundDiscoveryTests.swift`:

- `func testOpeningPageIsTheCoursePageUnlessACourseIsCarried()`: `openingPage`
  returns:
  - `(nil, nil)` → `.course`;
  - `(nil, 31795)` → `.setup`;
  - `(.course, 31795)` → `.course`;
  - `(.setup, nil)` → `.course`.
- `func testTappingAVenuePreselectsItsLastUsedLoop()`: `preselectedLoop` with 黑骑士
  A/B/C:
  - recent B, current nil → B;
  - current C (same venue), recent B → C;
  - current at another venue, recent nil → A;
  - recent at another venue → A.
- `func testSetupPagePreselectsTheLastUsedTeeElseTheCourseDefault()`: `preselectedTee`
  returns:
  - `(["white"], [gold, blue, white, red], "blue")` → `white`;
  - `(["WHITE"], ["White"], nil)` → `White`;
  - `(["black"], [gold, blue, white], "blue")` → `blue`;
  - `([nil, "unknown", ""], [gold, blue, white], "white")` → `white`;
  - `([], [gold, blue, white], nil)` → `blue`;
  - `([], [gold, red], nil)` → `gold`;
  - `(["red", "white"], [white, blue], nil)` → `white`;
  - `(["blue"], [], nil)` → `blue`;
  - `([], [], nil)` → `""`.

`mobile/ios/AICaddieTests/DesignSnapshotTests.swift`:

- `captureScreen(... named: "full-start-page-course")`: `StartRoundView` with
  `defaultCourseGlobalId: 31795`, `initialPage: .course` and the 黑骑士 catalogue.
  Page 1 shows the list with 黑骑士 checked.
- `captureScreen(... named: "full-start-page-setup")`: `StartRoundView` with
  `defaultCourseGlobalId: 31795`, `defaultTeeBox: "blue"`, `initialCourseTees: loopBTees`
  and `initialPage: .setup`. Page 2 shows the A/B/C tiles with B selected, the tee dots
  with yards and 从 B 场 开始 · 蓝 T.
- The existing `full-start*` captures stay, on whichever page their inputs open.

`mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift`:

- `func testRoundSetupListsTheDefaultTeeFirstAndHighlighted()`:
  - `orderedTeeChoices` with tees Blue, White, Red and `preselected: "white"` →
    ids `tee:white, tee:blue, tee:red`, selected `[true, false, false]`;
  - `preselected: "unknown"` with Red `isDefault` → Red first and selected;
  - no match and no default → input order, first selected;
  - empty → `[]`.
- `func testTeeTapSelectionCarriesTheChosenLoopHalfAndTee()`: `startSelection(teeBox:)`
  carries the given tee and `ensureGeometry`:
  - for a nine-hole loop: `loopKey` `301:all`, no back, no `firstHalf`;
  - for a normal 18-hole row: `firstHalf` `front` and `loopKey` `31795:front`.
- `func testRenderWatchCourseSetupTees()`: front `黑骑士 ~ A` (globalId 301, 9 holes,
  `teeBox: "White"`, tees `["Blue", "White", "Red"]`). It asserts
  `setup.teeChoices.map(\.id) == ["tee:white", "tee:blue", "tee:red"]` and renders
  `setup.teeSelectionContent` as `watch-course-setup-tees` (198 × 242, black background).

UI journeys (`mobile/ios/AICaddieUITests/*`, workflow_dispatch only): update the
TeeSelection and RealFlow journeys. Tap a venue row, then wait for
`start-round-setup-page` before using loop tiles, tees or `start-round-primary-action`.
They cannot run in PR CI; the PR body says so.

## Repository pins (Codex, `tests/test_mobile_contracts.py`, class `MobileContractTests`)

- `test_ios_start_round_has_course_and_setup_pages` pins the phone interface above
  (pages, navigation, preselection calls) and the two phone snapshot names.
- `test_watch_round_setup_tee_tap_starts_round` pins the Watch interface above (no
  start button, tee rows start, ordered choices) and the Watch snapshot name.

Existing pins that the split makes stale are updated in the same PR, not deleted
wholesale. `python -m unittest tests.test_mobile_contracts tests.test_native_visual_parity`
stays green.

### G1 — Phone 开始一场 is two pages: course, then loop + tee + start

1. `StartRoundView` declares `Page` (`course`, `setup`), `initialPage: Page? = nil`
   and `openingPage(initialPage:defaultCourseGlobalId:)`.
2. `coursePage` contains `searchEntry`, `courseList` and `start-round-course-page`. It
   contains none of `loopSection`, `teeSection`, `startCard` or
   `start-round-primary-action`.
3. `setupPage` contains `loopSection`, `teeSection`, `startCard`,
   `start-round-setup-page` and `start-round-pinned-actions`. It contains neither
   `courseList` nor `searchEntry`.
4. `start-round-primary-action` occurs once in the file.
5. `showSetupPage()` exists. It is called in `selectCourseRow` and
   `selectSearchResult`, and not in `ensureDefaultSelection`, `selectVenue` or
   `discoverNearbyCourses`.
6. Page 2 has a way back: `.navigationDestination(isPresented:` or
   `start-round-back-to-courses`.
7. `testOpeningPageIsTheCoursePageUnlessACourseIsCarried` exists and calls `openingPage`.
8. Subprocess: `python -m unittest -v tests.test_mobile_contracts.MobileContractTests.test_ios_start_round_has_course_and_setup_pages`
   exits 0 and runs 1 test.

### G2 — Phone page 2 preselects the last used loop and tee, else the course default

1. `StartRoundPresentation` declares `preselectedLoop(in:current:recent:)` and
   `preselectedTee(lastUsed:offered:defaultTee:)` with the signatures above.
2. `selectCourseRow` calls `StartRoundPresentation.preselectedLoop(`.
   `StartRoundView.swift` calls `StartRoundPresentation.preselectedTee(` at least twice.
3. `testTappingAVenuePreselectsItsLastUsedLoop` and
   `testSetupPagePreselectsTheLastUsedTeeElseTheCourseDefault` exist and call the
   functions; the tee test has at least 9 calls (the cases above).
4. Subprocess: the G1 repository pin passes (it pins the preselection calls).

### G3 — Watch: tapping a tee starts the round; default tee first and highlighted; no start button

1. `WatchRoundSetupView.swift`:
   - has no `watch-setup-start` and no `startAction` view;
   - has `start(teeBox:)` with the guard, `didSubmitStart = true` and
     `onStart(startSelection(teeBox: teeBox))`;
   - contains exactly one `onStart(` call.
2. It declares:
   - `startSelection(teeBox:)`;
   - `orderedTeeChoices(_:preselected:)`, with `teeChoices` using it;
   - `teeSelectionContent`, whose rows call `start(teeBox:)`;
   - the identifiers `watch-setup-tee-\(` and `watch-setup-tee-default`;
   - `.disabled(isPreparing || didSubmitStart)`.
3. The 前九 / 后九 stage is unchanged: `watch-setup-half-` is present, and the
   selection still carries `firstHalf` from `selectedHalf`.
4. `testRoundSetupListsTheDefaultTeeFirstAndHighlighted` and
   `testTeeTapSelectionCarriesTheChosenLoopHalfAndTee` exist and call the new API.
5. Subprocess: `...MobileContractTests.test_watch_round_setup_tee_tap_starts_round`
   exits 0 and runs 1 test.

### G4 — Snapshot evidence for both start screens

1. `DesignSnapshotTests.swift` captures:
   - `full-start-page-course` with `initialPage: .course` and `defaultCourseGlobalId: 31795`;
   - `full-start-page-setup` with `initialPage: .setup`, `defaultCourseGlobalId: 31795`
     and `initialCourseTees: loopBTees`.
2. `testRenderWatchCourseSetupTees`:
   - renders `teeSelectionContent` as `watch-course-setup-tees`;
   - asserts the order `"tee:white", "tee:blue", "tee:red"`.
3. Subprocess: both repository pins pass in one run.
4. Not mechanical: `native-mobile` is green on the head, and the reviewer inspects the
   three PNGs as described above.

### G5 — Nine-hole loop rules and scope unchanged (pinned)

1. The design README §8 bullets for 开始一场 and the 9-hole loop rule are unchanged
   (`docs/design/2026-09-25-ui-redesign/README.md`).
2. The phone still starts one loop only:
   - no `onPrepareCompositeRound`, `backGlobalIdText` or `secondNineCard`;
   - Start uses `StartRoundPresentation.startLoops(selected: course, half: startHalf)`.
3. Subprocess: `python -m unittest tests.test_mobile_contracts tests.test_native_visual_parity`
   exits 0.
4. Reviewer: the diff touches no `server_v2/`, `ai_caddie/`, `migrations/`,
   `contracts/`, `web_v2/` or `README.md` path, and no pinned file.

## Not in scope

- Backend, migrations, canonical contracts, web.
- README §8 (a follow-up after #434).
- The Watch course picker (`WatchStartView`) and the Watch holes / which-9 choices.
  Today they still offer A + B pairings at start, which differs from README §8's
  "first loop only". That is a separate card if the owner wants it.
- Codex must not edit `tests/acceptance/`.
