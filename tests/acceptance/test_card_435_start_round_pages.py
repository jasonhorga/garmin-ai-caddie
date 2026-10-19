"""Card #435: 开始一场 in fewer taps — phone two pages, Watch tap a tee to start.

Linux CI has no Swift toolchain, so these tests read the Swift sources and the Swift tests that the
`native-mobile` check runs (contract `.agent/contracts/card-435.md` names each one), and run the
Python source pins Codex adds to `tests/test_mobile_contracts.py` as a real `python -m unittest`
subprocess. The behaviour itself is proven by `native-mobile` and by the reviewer reading the
`full-start-page-course`, `full-start-page-setup` and `watch-course-setup-tees` snapshots.
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
PHONE_PIN = "test_ios_start_round_has_course_and_setup_pages"
WATCH_PIN = "test_watch_round_setup_tee_tap_starts_round"
PIN_CLASS = "tests.test_mobile_contracts.MobileContractTests"


def _read(path: Path) -> str:
    # G1 G2 G3 G4 G5: one checkout source file.
    return path.read_text(encoding="utf-8")


def _block_after(source: str, start: int) -> str:
    # G1 G2 G3 G4: the `{ … }` body opening at the first `{` from `start`, skipping strings/comments.
    open_at = source.index("{", start)
    depth = 0
    i = open_at
    n = len(source)
    while i < n:
        if source.startswith("//", i):
            end = source.find("\n", i)
            i = n if end < 0 else end
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        raw = re.match(r'(#+)("""|")', source[i : i + 12])
        if raw:
            closing = raw.group(2) + raw.group(1)
            end = source.find(closing, i + len(raw.group(0)))
            i = n if end < 0 else end + len(closing)
            continue
        if source.startswith('"""', i):
            end = source.find('"""', i + 3)
            i = n if end < 0 else end + 3
            continue
        char = source[i]
        if char == '"':
            i += 1
            while i < n and source[i] not in '"\n':
                i += 2 if source[i] == "\\" else 1
            i += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[open_at + 1 : i]
        i += 1
    raise AssertionError("unbalanced Swift braces")


def _swift_body(testcase: unittest.TestCase, source: str, header: str) -> str:
    # G1 G2 G3 G4: the body of the declaration matched by regex `header`; fails when it is missing.
    match = re.search(header, source)
    testcase.assertIsNotNone(match, f"missing Swift declaration matching {header!r}")
    return _block_after(source, match.end() - 1 if source[match.end() - 1] == "{" else match.end())


def _var_body(testcase: unittest.TestCase, source: str, name: str) -> str:
    # G1 G3 G4: `var <name>: some View { … }` (any access level / @ViewBuilder).
    return _swift_body(testcase, source, rf"\bvar {re.escape(name)}\s*:\s*some View\s*\{{")


def _func_body(testcase: unittest.TestCase, source: str, name: str) -> str:
    # G1 G2 G3 G4: `func <name>(…) … { … }`.
    return _swift_body(testcase, source, rf"\bfunc {re.escape(name)}\(")


def _capture_segment(snapshots: str, name: str) -> str:
    # G4: the `try captureScreen(` call that names snapshot `name`, as the existing pins slice it.
    marker = f'named: "{name}"'
    if marker not in snapshots:
        raise AssertionError(f"no snapshot named {name}")
    return snapshots.split(marker, 1)[0].rsplit("try captureScreen(", 1)[1]


def _run_unittest(*targets: str) -> tuple[int, str]:
    # G1 G2 G3 G4 G5: the repository's own unittest entry point in a real subprocess, fixture mode.
    env = dict(os.environ)
    env["AI_CADDIE_DATA_MODE"] = "fixture"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("AI_CADDIE_PRIVATE_ROOT", None)
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "-v", *targets],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return proc.returncode, proc.stdout + proc.stderr


class StartRoundPagesAcceptanceTests(unittest.TestCase):
    # G1 — phone: two pages

    def test_phone_start_round_declares_course_and_setup_pages(self) -> None:
        # G1: Page (course / setup), the snapshot-only initialPage and the pure opening-page rule.
        source = _read(START_VIEW)
        page = re.search(r"\benum Page\b[^{]*\{(?P<body>[^}]*)\}", source)
        self.assertIsNotNone(page, "StartRoundView must declare enum Page")
        self.assertRegex(page.group("body"), r"\bcourse\b")
        self.assertRegex(page.group("body"), r"\bsetup\b")
        self.assertRegex(source, r"\binitialPage:\s*Page\?\s*=\s*nil")
        self.assertRegex(
            source,
            r"static func openingPage\(\s*initialPage:\s*Page\?\s*,\s*defaultCourseGlobalId:\s*Int\?\s*\)\s*->\s*Page",
        )
        self.assertRegex(source, r"@State private var page:\s*Page\b")

    def test_phone_page_one_lists_courses_and_page_two_holds_loop_tee_and_start(self) -> None:
        # G1: page 1 = search + course list only; page 2 = loop tiles, tees, pinned start and a way back.
        source = _read(START_VIEW)
        course_page = _var_body(self, source, "coursePage")
        setup_page = _var_body(self, source, "setupPage")
        body = _var_body(self, source, "body")
        for name in ("searchEntry", "courseList"):
            self.assertRegex(course_page, rf"\b{name}\b", f"page 1 must show {name}")
        for name in ("loopSection", "teeSection", "startCard"):
            self.assertNotRegex(course_page, rf"\b{name}\b", f"page 1 must not show {name}")
            self.assertRegex(setup_page, rf"\b{name}\b", f"page 2 must show {name}")
        self.assertNotIn("start-round-pinned-actions", course_page)
        self.assertIn("start-round-pinned-actions", setup_page)
        self.assertIn(".safeAreaInset(edge: .bottom, spacing: 0) {", setup_page)
        self.assertRegex(body, r"\bcoursePage\b")
        self.assertRegex(body, r"\bsetupPage\b")
        self.assertIn('.navigationTitle("开始一场")', body)
        for identifier in ("start-round-page-course", "start-round-page-setup", "start-round-back-to-courses"):
            self.assertIn(f'"{identifier}"', source, identifier)
        self.assertIn(".navigationBarBackButtonHidden(", source)

    def test_picking_a_course_opens_page_two_but_gps_selection_does_not(self) -> None:
        # G1: a tapped row (also the already-selected venue) or a search pick opens page 2; automatic
        # GPS selection and its clearing never change the page.
        source = _read(START_VIEW)
        self.assertRegex(source, r"private func showSetupPage\(\)")
        for name in ("selectCourseRow", "selectSearchResult"):
            self.assertIn("showSetupPage()", _func_body(self, source, name), name)
        for name in ("ensureDefaultSelection", "selectVenue", "discoverNearbyCourses", "clearAutomaticSelection"):
            self.assertNotIn("showSetupPage()", _func_body(self, source, name), name)
        self.assertNotIn(
            "Self.samePhysicalVenue(current, first) { return }",
            _func_body(self, source, "selectCourseRow"),
            "tapping the selected venue must still open page 2",
        )

    def test_phone_swift_tests_cover_the_opening_page(self) -> None:
        # G1: the native suite exercises every opening-page case.
        tests = _read(DISCOVERY_TESTS)
        body = _func_body(self, tests, "testOpeningPageIsCourseUnlessACourseIsPassed")
        self.assertGreaterEqual(body.count("StartRoundView.openingPage("), 4)
        self.assertIn(".setup", body)
        self.assertIn(".course", body)

    # G2 — phone: preselection

    def test_presentation_declares_loop_and_tee_preselection_rules(self) -> None:
        # G2: the two pure rules page 2 uses, with the contract's signatures.
        source = _read(PRESENTATION)
        self.assertRegex(
            source,
            r"static func preselectedLoop\(\s*in loops:\s*\[MobileCourseOption\]\s*,\s*current:\s*MobileCourseOption\?\s*,"
            r"\s*recent:\s*MobileCourseOption\?\s*\)\s*->\s*MobileCourseOption\?",
        )
        self.assertRegex(
            source,
            r"static func preselectedTee\(\s*lastUsed:\s*String\?\s*,\s*offered:\s*\[String\]\s*,"
            r"\s*defaultTee:\s*String\?\s*\)\s*->\s*String\b",
        )

    def test_start_round_uses_the_preselection_rules(self) -> None:
        # G2: a tapped row keeps the current / last used loop; the /tees default row beats the guess
        # unless the player tapped a tee.
        source = _read(START_VIEW)
        self.assertIn("StartRoundPresentation.preselectedLoop(", _func_body(self, source, "selectCourseRow"))
        tee_calls = []
        for match in re.finditer(r"StartRoundPresentation\.preselectedTee\(", source):
            depth, i = 1, match.end()
            while i < len(source) and depth:
                depth += {"(": 1, ")": -1}.get(source[i], 0)
                i += 1
            tee_calls.append(source[match.end() : i])
        self.assertTrue(tee_calls, "StartRoundView must use StartRoundPresentation.preselectedTee")
        self.assertTrue(
            any("isDefault" in call for call in tee_calls),
            "the /tees default row must be the defaultTee of a preselectedTee call",
        )
        load_tees = _func_body(self, source, "loadTees")
        self.assertTrue(
            "preselectedTee(" in load_tees or "teeAfterRefresh(" in load_tees,
            "the /tees answer must go through the preselection rule",
        )
        self.assertRegex(source, r"@State private var userPickedTee\b")

    def test_swift_tests_cover_every_preselection_case(self) -> None:
        # G2: one native assertion per rule case in the contract's tables.
        tests = _read(DISCOVERY_TESTS)
        loop = _func_body(self, tests, "testPreselectedLoopPrefersCurrentThenRecentThenFirst")
        self.assertGreaterEqual(loop.count("StartRoundPresentation.preselectedLoop("), 4)
        tee = _func_body(self, tests, "testPreselectedTeePrefersLastUsedThenCourseDefault")
        self.assertGreaterEqual(tee.count("StartRoundPresentation.preselectedTee("), 10)
        self.assertIn('"Gold"', tee)
        self.assertIn('"silver"', tee)

    # G3 — Watch: tap a tee to start

    def test_watch_tee_tap_is_the_only_start(self) -> None:
        # G3: start(teeBox:) is the single onStart call; the separate start button is gone.
        source = _read(WATCH_SETUP)
        self.assertRegex(source, r"\bfunc selection\(teeBox:\s*String\)\s*->\s*WatchCourseSelection")
        start = _swift_body(self, source, r"\bfunc start\(teeBox:\s*String\)[^{]*\{")
        self.assertEqual(source.count("onStart("), 1, "onStart must be called exactly once")
        self.assertIn("onStart(selection(teeBox: teeBox))", start)
        self.assertIn("didSubmitStart", start)
        self.assertIn("isPreparing", start)
        self.assertNotIn("watch-setup-start", source)
        self.assertNotRegex(source, r"\bvar startAction\s*:")

    def test_watch_tee_list_puts_default_first_and_always_offers_a_tee(self) -> None:
        # G3: ordered tee rows (default first), each row starts; a default row when no tee data.
        source = _read(WATCH_SETUP)
        self.assertRegex(source, r"\bvar orderedTeeChoices\s*:\s*\[WatchRoundSetupChoicePresentation\]")
        content = _var_body(self, source, "teeSelectionContent")
        self.assertIn("orderedTeeChoices", content)
        self.assertIn("start(teeBox:", content)
        self.assertIn('"watch-setup-tee-\\(', source)
        self.assertIn('"watch-setup-tee-default"', source)
        self.assertIn("球场默认 T", source)
        self.assertIn('return "unknown"', source)
        self.assertEqual(source.count(".ignoresSafeArea(edges: .top)"), 2)
        self.assertRegex(_var_body(self, source, "teeSelection"), r"\bteeSelectionContent\b")

    def test_watch_swift_tests_cover_tee_order_and_tap_start(self) -> None:
        # G3: native tests pin the default-first order and that a tap submits that tee.
        tests = _read(WATCH_SNAPSHOTS)
        order = _func_body(self, tests, "testTeeChoicesListTheDefaultTeeFirstAndHighlighted")
        self.assertIn("orderedTeeChoices", order)
        self.assertIn('["白 T", "蓝 T", "红 T"]', order)
        self.assertIn("[true, false, false]", order)
        tap = _func_body(self, tests, "testTappingATeeStartsTheRoundWithThatTee")
        self.assertIn(".start(teeBox:", tap)
        self.assertIn('"Red"', tap)
        self.assertIn("firstHalf", tap)

    # G4 — snapshots

    def test_phone_snapshots_capture_both_pages(self) -> None:
        # G4: one capture per page; page 2 carries the loop-B tee rows so its chips show yards.
        snapshots = _read(PHONE_SNAPSHOTS)
        self.assertIn("initialPage: .course", _capture_segment(snapshots, "full-start-page-course"))
        setup = _capture_segment(snapshots, "full-start-page-setup")
        self.assertIn("initialPage: .setup", setup)
        self.assertIn("initialCourseTees:", setup)

    def test_watch_snapshot_captures_the_tee_list(self) -> None:
        # G4: the tee stage content (no ScrollView) rendered with the White-default fixture.
        tests = _read(WATCH_SNAPSHOTS)
        body = _func_body(self, tests, "testRenderWatchCourseSetupTees")
        self.assertIn("teeSelectionContent", body)
        self.assertIn('"watch-course-setup-tees"', body)
        self.assertIn('["白 T", "蓝 T", "红 T"]', body)

    # G5 — nine-hole loop rules unchanged

    def test_nine_hole_loop_rules_stay_unchanged(self) -> None:
        # G5
        # pinned: README §8 and the one-loop start must keep today's behaviour; this passes on main.
        readme = _read(DESIGN_README)
        self.assertIn("选第一个 9 洞环（A / B / C 大块）", readme)
        self.assertIn("开始时只选**第一个环**", readme)
        self.assertIn("第二个环打到中途再选", readme)
        start_view = _read(START_VIEW)
        self.assertIn("StartRoundPresentation.startLoops(selected: course, half: startHalf)", start_view)
        watch = _read(WATCH_SETUP)
        self.assertIn('"watch-setup-half-\\(half)"', watch)
        self.assertRegex(watch, r"\bvar halfChoices\s*:")
        self.assertRegex(watch, r"\bvar holeSelectionContent\s*:\s*some View")

    # Real entry point: the repository's unittest runner

    def test_phone_contract_pin_passes(self) -> None:
        # G1 G2 G5: Codex's phone source pin runs and passes through `python -m unittest`.
        code, output = _run_unittest(f"{PIN_CLASS}.{PHONE_PIN}")
        self.assertEqual(code, 0, output)
        self.assertRegex(output, r"Ran 1 test\b")
        self.assertRegex(output, rf"{PHONE_PIN} \(.*\) \.\.\. ok")

    def test_watch_contract_pin_passes(self) -> None:
        # G3 G4 G5: Codex's Watch source pin runs and passes through `python -m unittest`.
        code, output = _run_unittest(f"{PIN_CLASS}.{WATCH_PIN}")
        self.assertEqual(code, 0, output)
        self.assertRegex(output, r"Ran 1 test\b")
        self.assertRegex(output, rf"{WATCH_PIN} \(.*\) \.\.\. ok")

    def test_mobile_source_pin_modules_stay_green(self) -> None:
        # G1 G2 G3 G4 G5: the whole mobile pin modules pass with both new pins included.
        code, output = _run_unittest("tests.test_mobile_contracts", "tests.test_native_visual_parity")
        self.assertEqual(code, 0, output[-6000:])
        for name in (PHONE_PIN, WATCH_PIN):
            self.assertRegex(output, rf"{name} \(.*\) \.\.\. ok", name)


if __name__ == "__main__":
    unittest.main()
