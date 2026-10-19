"""Card #435: phone 开始一场 in two pages; on the Watch, tapping a tee starts the round.

The change is native SwiftUI, and Linux CI has no Swift toolchain. These tests check the Swift
sources and the Swift tests that `native-mobile` runs against the interface in
`.agent/contracts/card-435.md`. Each goal also runs the repository's native-source contract
tests (`tests/test_mobile_contracts.py`) as a real `python -m unittest` subprocess. Behaviour
on the simulator is proven by `native-mobile` and the reviewed snapshots; on a device, by the
owner.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
IOS = REPO_ROOT / "mobile" / "ios"
START_VIEW = IOS / "AICaddie" / "Views" / "StartRoundView.swift"
PRESENTATION = IOS / "AICaddie" / "Models" / "StartRoundPresentation.swift"
WATCH_SETUP = IOS / "AICaddieWatch" / "Views" / "WatchRoundSetupView.swift"
DISCOVERY_TESTS = IOS / "AICaddieTests" / "StartRoundDiscoveryTests.swift"
PHONE_SNAPSHOTS = IOS / "AICaddieTests" / "DesignSnapshotTests.swift"
WATCH_SNAPSHOTS = IOS / "AICaddieWatchTests" / "WatchDesignSnapshotTests.swift"
DESIGN_README = REPO_ROOT / "docs" / "design" / "2026-09-25-ui-redesign" / "README.md"
PHONE_PIN = "tests.test_mobile_contracts.MobileContractTests.test_ios_start_round_has_course_and_setup_pages"
WATCH_PIN = "tests.test_mobile_contracts.MobileContractTests.test_watch_round_setup_tee_tap_starts_round"


def _read(path: Path) -> str:
    # G1 G2 G3 G4 G5: a required source file.
    if not path.is_file():
        raise AssertionError(f"missing {path.relative_to(REPO_ROOT)}")
    return path.read_text(encoding="utf-8")


def _skip_string(text: str, index: int) -> int:
    # G1 G2 G3 G4: index just past the Swift string literal starting at `index` (raw and multi-line too).
    hashes = 0
    while text[index] == "#":
        hashes += 1
        index += 1
    closing_hashes = "#" * hashes
    if text.startswith('"""', index):
        end = text.find('"""' + closing_hashes, index + 3)
        return len(text) if end < 0 else end + 3 + hashes
    index += 1
    while index < len(text):
        char = text[index]
        if char == "\\" and hashes == 0:
            index += 2
            continue
        if char == '"' and text.startswith(closing_hashes, index + 1):
            return index + 1 + hashes
        if char == "\n":
            return index
        index += 1
    return index


def _block_after(text: str, start: int) -> str:
    # G1 G2 G3 G4: the `{ ... }` block opening at the first brace at or after `start`.
    open_at = text.find("{", start)
    if open_at < 0:
        raise AssertionError("no block after declaration")
    depth = 0
    index = open_at
    while index < len(text):
        char = text[index]
        if text.startswith("//", index):
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline
            continue
        if char == '"' or (char == "#" and re.match(r'#+"', text[index:])):
            index = _skip_string(text, index)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[open_at : index + 1]
        index += 1
    raise AssertionError("unbalanced block")


def _body(text: str, declaration: str) -> str:
    # G1 G2 G3 G4: body of the first declaration matching the regex `declaration`.
    match = re.search(declaration, text)
    if match is None:
        raise AssertionError(f"missing declaration matching {declaration!r}")
    return _block_after(text, match.end())


def _capture(text: str, name: str) -> str:
    # G4: the `captureScreen(` call that writes snapshot `name`.
    marker = f'named: "{name}"'
    at = text.find(marker)
    if at < 0:
        raise AssertionError(f"no snapshot named {name}")
    start = text.rfind("captureScreen(", 0, at)
    if start < 0:
        raise AssertionError(f"snapshot {name} is not a captureScreen call")
    return text[start : at + len(marker)]


def _run_unittest(*ids: str) -> tuple[int, str]:
    # G1 G2 G3 G4 G5: the repository's own unittest entry point, offline in fixture mode.
    env = dict(os.environ)
    env["AI_CADDIE_DATA_MODE"] = "fixture"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("AI_CADDIE_PRIVATE_ROOT", None)
    env["PYTHONPATH"] = os.pathsep.join(part for part in (str(REPO_ROOT), env.get("PYTHONPATH", "")) if part)
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "-v", *ids],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return proc.returncode, proc.stdout + proc.stderr


class StartRoundPagesTests(unittest.TestCase):
    # G1 — phone two pages

    def test_phone_declares_course_and_setup_pages(self) -> None:
        # G1: Page enum, initialPage fixture parameter and the opening-page rule.
        source = _read(START_VIEW)
        page_enum = _body(source, r"\benum Page\b[^{]*")
        self.assertRegex(page_enum, r"\bcase\s+course\b")
        self.assertRegex(page_enum, r"\bcase\s+(course\s*,\s*)?setup\b")
        self.assertIn("initialPage: Page? = nil", source)
        self.assertRegex(
            source,
            r"static func openingPage\(\s*initialPage: Page\?,\s*defaultCourseGlobalId: Int\?\s*\) -> Page",
        )

    def test_phone_course_page_holds_only_the_course_list(self) -> None:
        # G1: page 1 is search + one course list; no loop, tee or start action.
        source = _read(START_VIEW)
        page = _body(source, r"\bvar coursePage\s*:\s*some View")
        for required in ("searchEntry", "courseList", '"start-round-course-page"'):
            self.assertIn(required, page)
        for forbidden in ("loopSection", "teeSection", "startCard", "start-round-primary-action"):
            self.assertNotIn(forbidden, page)

    def test_phone_setup_page_holds_loop_tee_and_start(self) -> None:
        # G1: page 2 is loop + tee + the pinned start band; no course list or search.
        source = _read(START_VIEW)
        page = _body(source, r"\bvar setupPage\s*:\s*some View")
        for required in ("loopSection", "teeSection", "startCard", '"start-round-setup-page"', '"start-round-pinned-actions"'):
            self.assertIn(required, page)
        for forbidden in ("courseList", "searchEntry"):
            self.assertNotIn(forbidden, page)
        self.assertEqual(source.count('"start-round-primary-action"'), 1, "one start action, on page 2")

    def test_phone_explicit_course_picks_open_page_two_and_back_returns(self) -> None:
        # G1: a row tap or a search pick opens page 2; automatic selection never does; page 2 has a back.
        source = _read(START_VIEW)
        _body(source, r"func showSetupPage\(\)")
        for explicit in (r"func selectCourseRow\(", r"func selectSearchResult\("):
            self.assertIn("showSetupPage()", _body(source, explicit), explicit)
        for automatic in (r"func ensureDefaultSelection\(", r"func selectVenue\(", r"func discoverNearbyCourses\("):
            self.assertNotIn("showSetupPage()", _body(source, automatic), automatic)
        self.assertTrue(
            ".navigationDestination(isPresented:" in source or '"start-round-back-to-courses"' in source,
            "page 2 needs the system back (pushed) or a start-round-back-to-courses control",
        )

    def test_phone_native_test_pins_the_opening_page(self) -> None:
        # G1: the Swift unit test that native-mobile runs covers the opening-page rule.
        body = _body(_read(DISCOVERY_TESTS), r"func testOpeningPageIsTheCoursePageUnlessACourseIsCarried\(\)")
        self.assertGreaterEqual(body.count("openingPage("), 4)
        self.assertIn(".course", body)
        self.assertIn(".setup", body)

    def test_repository_pin_for_the_phone_pages_passes(self) -> None:
        # G1 G2: the repository's phone pin runs and passes through `python -m unittest`.
        code, output = _run_unittest(PHONE_PIN)
        self.assertEqual(code, 0, output[-4000:])
        self.assertRegex(output, r"Ran 1 test\b")

    # G2 — page 2 preselection

    def test_presentation_declares_loop_and_tee_preselection(self) -> None:
        # G2: last used loop / tee, else the course default, as pure presentation rules.
        source = _read(PRESENTATION)
        self.assertRegex(
            source,
            r"static func preselectedLoop\(\s*in row: StartCourseListRow,\s*current: MobileCourseOption\?,\s*"
            r"recent: MobileCourseOption\?\s*\) -> MobileCourseOption\?",
        )
        self.assertRegex(
            source,
            r"static func preselectedTee\(\s*lastUsed: \[String\?\],\s*offered: \[String\],\s*"
            r"defaultTee: String\?\s*\) -> String",
        )

    def test_phone_view_uses_the_preselection_rules(self) -> None:
        # G2: a row tap picks the last used loop; selection and the /tees refresh pick the tee.
        source = _read(START_VIEW)
        self.assertIn("StartRoundPresentation.preselectedLoop(", _body(source, r"func selectCourseRow\("))
        self.assertGreaterEqual(source.count("StartRoundPresentation.preselectedTee("), 2)

    def test_phone_native_tests_cover_the_preselection_cases(self) -> None:
        # G2: the Swift tables for loop and tee preselection exist (native-mobile runs them).
        tests = _read(DISCOVERY_TESTS)
        loop = _body(tests, r"func testTappingAVenuePreselectsItsLastUsedLoop\(\)")
        self.assertGreaterEqual(loop.count("preselectedLoop("), 4)
        tee = _body(tests, r"func testSetupPagePreselectsTheLastUsedTeeElseTheCourseDefault\(\)")
        self.assertGreaterEqual(tee.count("preselectedTee("), 9)

    # G3 — Watch tee tap starts

    def test_watch_setup_has_no_start_button(self) -> None:
        # G3: the separate start button is gone; tapping a tee is the only start.
        source = _read(WATCH_SETUP)
        self.assertNotIn("watch-setup-start", source)
        self.assertNotRegex(source, r"\bvar startAction\b")
        self.assertEqual(len(re.findall(r"\bonStart\(", source)), 1, "onStart is called only from start(teeBox:)")
        start = _body(source, r"func start\(teeBox: String\)")
        self.assertIn("!isPreparing", start)
        self.assertIn("!didSubmitStart", start)
        self.assertIn("didSubmitStart = true", start)
        self.assertIn("onStart(startSelection(teeBox: teeBox))", start)

    def test_watch_tee_rows_start_the_round_default_first(self) -> None:
        # G3: tee rows call start(teeBox:), the default tee is ordered first and highlighted.
        source = _read(WATCH_SETUP)
        self.assertRegex(source, r"func startSelection\(teeBox: String\) -> WatchCourseSelection")
        self.assertRegex(
            source,
            r"static func orderedTeeChoices\(\s*_ tees: \[WatchCourseTee\],\s*preselected: String\s*\)\s*"
            r"-> \[WatchRoundSetupChoicePresentation\]",
        )
        self.assertIn("orderedTeeChoices(", _body(source, r"\bvar teeChoices\s*:\s*\[WatchRoundSetupChoicePresentation\]"))
        content = _body(source, r"\bvar teeSelectionContent\s*:\s*some View")
        self.assertIn("start(teeBox:", content)
        self.assertIn('"watch-setup-tee-\\(', source)
        self.assertIn('"watch-setup-tee-default"', source)
        self.assertIn(".disabled(isPreparing || didSubmitStart)", source)

    def test_watch_native_tests_cover_order_and_selection(self) -> None:
        # G3: Swift tests for the default-first order and for what a tee tap submits.
        tests = _read(WATCH_SNAPSHOTS)
        order = _body(tests, r"func testRoundSetupListsTheDefaultTeeFirstAndHighlighted\(\)")
        self.assertIn("orderedTeeChoices(", order)
        self.assertIn("isSelected", order)
        selection = _body(tests, r"func testTeeTapSelectionCarriesTheChosenLoopHalfAndTee\(\)")
        self.assertGreaterEqual(selection.count("startSelection(teeBox:"), 2)
        self.assertIn("firstHalf", selection)
        self.assertIn("loopKey", selection)

    def test_repository_pin_for_the_watch_tee_tap_passes(self) -> None:
        # G3: the repository's Watch pin runs and passes through `python -m unittest`.
        code, output = _run_unittest(WATCH_PIN)
        self.assertEqual(code, 0, output[-4000:])
        self.assertRegex(output, r"Ran 1 test\b")

    # G4 — snapshot evidence

    def test_phone_snapshots_capture_both_pages(self) -> None:
        # G4: page 1 (course checked) and page 2 (黑骑士 B, loop-B tees) are captured.
        source = _read(PHONE_SNAPSHOTS)
        course = _capture(source, "full-start-page-course")
        self.assertIn("initialPage: .course", course)
        self.assertIn("defaultCourseGlobalId: 31795", course)
        setup = _capture(source, "full-start-page-setup")
        self.assertIn("initialPage: .setup", setup)
        self.assertIn("defaultCourseGlobalId: 31795", setup)
        self.assertIn("initialCourseTees: loopBTees", setup)

    def test_watch_snapshot_captures_the_tee_list(self) -> None:
        # G4: the Watch tee list renders with the default (White) first.
        body = _body(_read(WATCH_SNAPSHOTS), r"func testRenderWatchCourseSetupTees\(\)")
        self.assertIn("teeSelectionContent", body)
        self.assertIn('named: "watch-course-setup-tees"', body)
        self.assertIn('"tee:white", "tee:blue", "tee:red"', body)

    def test_repository_pins_for_both_screens_pass_together(self) -> None:
        # G4: both repository pins (which name the snapshots) pass in one unittest run.
        code, output = _run_unittest(PHONE_PIN, WATCH_PIN)
        self.assertEqual(code, 0, output[-4000:])
        self.assertRegex(output, r"Ran 2 tests\b")

    # G5 — loop rules and scope unchanged

    def test_nine_hole_loop_rules_are_unchanged(self) -> None:
        # G5: first loop only at start; the second loop at the turn; README §8 untouched.
        # pinned: README §8 and the first-loop-only start already hold on main and must stay.
        readme = _read(DESIGN_README)
        for line in (
            "选第一个 9 洞环（A / B / C 大块）",
            "第二个环打到中途再选（见下面的 9 洞环规则）",
            "开始时只选**第一个环**（A / B / C 直接选）",
            "开打第二个环的第一洞之前都能改选，开打后锁定",
        ):
            self.assertIn(line, readme)
        start = _read(START_VIEW)
        for removed in ("onPrepareCompositeRound", "backGlobalIdText", "secondNineCard"):
            self.assertNotIn(removed, start)
        self.assertIn("StartRoundPresentation.startLoops(selected: course, half: startHalf)", start)
        watch = _read(WATCH_SETUP)
        self.assertIn('"watch-setup-half-', watch)
        self.assertRegex(watch, r"firstHalf: Self\.playsHalves\(front\) \? selectedHalf : nil")

    def test_repository_native_source_tests_stay_green(self) -> None:
        # G5: the full native-source contract modules still pass after stale pins are updated.
        # pinned: these modules are green on main and must stay green.
        code, output = _run_unittest("tests.test_mobile_contracts", "tests.test_native_visual_parity")
        self.assertEqual(code, 0, output[-6000:])
        self.assertRegex(output, r"Ran [1-9]\d* tests?\b")


if __name__ == "__main__":
    unittest.main()
