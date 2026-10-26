"""Card #435: 开始一场 in fewer taps — phone two pages, Watch tap a tee to start.

Linux CI has no Swift toolchain. These tests read the Swift sources with comments removed, so a
comment can never satisfy a check, and pin their structure. They evaluate every asserted call of the
pure rules in the named Swift tests with a Python model of the rule in
`.agent/contracts/card-435.md`, so a Swift expectation that drifts from the contract fails here,
while `native-mobile` proves the Swift rule meets those expectations. The repository's own source
pins run as a real `python -m unittest` subprocess. The reviewer reads the `full-start-page-course`,
`full-start-page-setup` and `watch-course-setup-tees` snapshots.
"""

from __future__ import annotations

import functools
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
KEPT_PINS = (
    "test_ios_lands_on_hub_with_choices_and_keeps_dark_chrome_live_only",
    "test_ui_tests_never_tap_rows_under_the_pinned_start_band",
    "test_watch_unknown_tee_does_not_fabricate_blue",
    "test_watch_scroll_surfaces_keep_horizontal_content_inside_the_rounded_display",
)

OFFERED = ("Gold", "Blue", "White")
TEE_TABLE = (
    (("white", OFFERED, "blue"), "White"),
    (("red", OFFERED, "blue"), "Blue"),
    ((None, OFFERED, "gold"), "Gold"),
    (("unknown", OFFERED, "gold"), "Gold"),
    ((None, OFFERED, "silver"), "Blue"),
    (("  ", OFFERED, None), "Blue"),
    ((None, ("Gold", "Red"), None), "Gold"),
    (("white", (), "blue"), "white"),
    ((None, (), "blue"), "blue"),
    ((None, (), None), ""),
)
LAST_USED_TABLE = (
    (("黑骑士", "黑骑士", "white", "黑骑士", "blue"), "white"),
    (("黑骑士", "北湖", "white", "黑骑士", "blue"), "blue"),
    (("黑骑士", "黑骑士", "unknown", "黑骑士", "blue"), "blue"),
    (("黑骑士", "北湖", "white", None, None), None),
    (("黑骑士", " 黑骑士 ", " Red ", None, None), "Red"),
    (("黑骑士", None, None, "黑骑士", "unknown"), None),
    (("", "", "white", None, None), None),
)
GOLD_DEFAULT = (("gold", True), ("blue", False), ("white", False))
NO_DEFAULT = (("gold", False), ("blue", False), ("white", False))
REFRESH_TABLE = (
    (("blue", False, None, GOLD_DEFAULT), "gold"),
    (("white", True, None, GOLD_DEFAULT), "white"),
    (("red", True, None, GOLD_DEFAULT), "gold"),
    (("blue", False, "White", GOLD_DEFAULT), "white"),
    (("", False, "red", GOLD_DEFAULT), "gold"),
    (("gold", False, None, NO_DEFAULT), "blue"),
)
OPENING_TABLE = (
    ((None, None), ".course"),
    ((None, "31795"), ".setup"),
    ((".course", "31795"), ".course"),
    ((".setup", None), ".setup"),
)

_RAW_STRING = re.compile(r'(#+)("""|")')
_PAIRS = {"(": ")", "[": "]", "{": "}"}


class _Ident(str):
    """An unquoted Swift token: an identifier, a number or a `.case`."""


class _Unevaluable(Exception):
    """A Swift test argument the Python rule model cannot evaluate (a variable)."""


# Swift source reading


def _string_end(source: str, i: int) -> int | None:
    # G1 G2 G3 G4 G5: index just past the Swift string literal that starts at `i`, else None.
    raw = _RAW_STRING.match(source, i)
    if raw:
        closing = raw.group(2) + raw.group(1)
        end = source.find(closing, raw.end())
        return len(source) if end < 0 else end + len(closing)
    if source.startswith('"""', i):
        end = source.find('"""', i + 3)
        return len(source) if end < 0 else end + 3
    if i < len(source) and source[i] == '"':
        j = i + 1
        while j < len(source) and source[j] not in '"\n':
            if source[j] == "\\" and j + 1 < len(source) and source[j + 1] == "(":
                j = _matching(source, j + 1) + 1
            elif source[j] == "\\":
                j += 2
            else:
                j += 1
        return j + 1
    return None


def _matching(source: str, open_at: int) -> int:
    # G1 G2 G3 G4 G5: index of the bracket that closes `source[open_at]`, skipping string literals.
    opener = source[open_at]
    closer = _PAIRS[opener]
    depth = 0
    j = open_at
    while j < len(source):
        end = _string_end(source, j)
        if end is not None:
            j = end
            continue
        char = source[j]
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise AssertionError(f"unbalanced Swift {opener!r} at offset {open_at}")


def _strip_comments(source: str) -> str:
    # G1 G2 G3 G4 G5: Swift source without `//` and `/* */` comments; string literals are kept.
    out: list[str] = []
    i, n = 0, len(source)
    while i < n:
        if source.startswith("//", i):
            end = source.find("\n", i)
            i = n if end < 0 else end
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = n if end < 0 else end + 2
            out.append(" ")
            continue
        end = _string_end(source, i)
        if end is not None:
            out.append(source[i:end])
            i = end
            continue
        out.append(source[i])
        i += 1
    return "".join(out)


@functools.lru_cache(maxsize=None)
def _code(path: Path) -> str:
    # G1 G2 G3 G4: one checkout Swift file, comments removed.
    return _strip_comments(path.read_text(encoding="utf-8"))


def _squash(text: str) -> str:
    # G2 G3 G4: whitespace-free form for comparing Swift fragments.
    return re.sub(r"\s+", "", text)


def _body_at(code: str, open_at: int) -> str:
    # G1 G2 G3 G4: the text inside the `{ … }` opening at `open_at`.
    return code[open_at + 1 : _matching(code, open_at)]


def _var_body(testcase: unittest.TestCase, code: str, name: str) -> str:
    # G1 G2 G3 G4: body of `var <name>: <type> { … }` (any access level / attributes).
    match = re.search(rf"\bvar {re.escape(name)}\s*:[^{{=\n]*\{{", code)
    testcase.assertIsNotNone(match, f"missing `var {name}`")
    return _body_at(code, match.end() - 1)


def _func_body(testcase: unittest.TestCase, code: str, name: str) -> str:
    # G1 G2 G3 G4: body of the first `func <name>(…) … { … }`.
    match = re.search(rf"\bfunc {re.escape(name)}\s*\(", code)
    testcase.assertIsNotNone(match, f"missing `func {name}(`")
    close = _matching(code, match.end() - 1)
    return _body_at(code, code.index("{", close))


def _call_args(code: str, callee_regex: str) -> list[str]:
    # G1 G2 G3: the argument text of every call `callee(…)`.
    out = []
    for match in re.finditer(callee_regex + r"\s*\(", code):
        open_at = match.end() - 1
        out.append(code[open_at + 1 : _matching(code, open_at)])
    return out


def _split_top(text: str) -> list[str]:
    # G1 G2 G3: split Swift arguments on top-level commas.
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    j = 0
    while j < len(text):
        end = _string_end(text, j)
        if end is not None:
            current.append(text[j:end])
            j = end
            continue
        char = text[j]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        j += 1
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _labelled(text: str) -> dict[str, str]:
    # G1 G2 G3: `label: value` arguments of one call.
    args: dict[str, str] = {}
    for part in _split_top(text):
        match = re.match(r"([A-Za-z_]\w*)\s*:\s*(.*)\Z", part, re.S)
        if match:
            args[match.group(1)] = match.group(2).strip()
    return args


def _literal(text: str):
    # G1 G2: a Swift literal as Python (nil, Bool, String, array → tuple); anything else is an _Ident.
    value = text.strip()
    if value == "nil":
        return None
    if value in ("true", "false"):
        return value == "true"
    match = re.fullmatch(r'"((?:[^"\\]|\\.)*)"', value)
    if match:
        return match.group(1)
    if value.startswith("[") and value.endswith("]"):
        return tuple(_literal(item) for item in _split_top(value[1:-1]))
    return _Ident(value)


def _assert_cases(body: str, callee: str) -> list[tuple[dict[str, str], object]]:
    # G1 G2: (labelled args, expected) of each `XCTAssertEqual(callee(…), expected)` and
    # `XCTAssertNil(callee(…))` in a Swift test body.
    cases: list[tuple[dict[str, str], object]] = []
    for kind in ("XCTAssertEqual", "XCTAssertNil"):
        for args in _call_args(body, rf"\b{kind}"):
            parts = _split_top(args)
            if not parts or not parts[0].startswith(callee + "("):
                continue
            first = parts[0]
            close = _matching(first, len(callee))
            if first[close + 1 :].strip():
                continue
            labelled = _labelled(first[len(callee) + 1 : close])
            if kind == "XCTAssertNil":
                cases.append((labelled, None))
            elif len(parts) >= 2:
                cases.append((labelled, _literal(parts[1])))
    return cases


def _literal_args(*keys: str):
    # G1 G2: converter from labelled Swift args to the rule's literal inputs, in `keys` order.
    def convert(args: dict[str, str]) -> tuple:
        missing = [key for key in keys if key not in args]
        if missing:
            raise AssertionError(f"a rule call without {missing}: {args}")
        return tuple(_literal(args[key]) for key in keys)

    return convert


def _course_tee_rows(text: str) -> tuple | None:
    # G2: ((teeBox, isDefault), …) of the `CourseTee(…)` calls in `text`; None when not literal.
    rows = []
    for args in _call_args(text, r"\bCourseTee"):
        labelled = _labelled(args)
        tee = _literal(labelled.get("teeBox", "nil"))
        is_default = _literal(labelled.get("isDefault", "false"))
        if not isinstance(tee, str) or isinstance(tee, _Ident) or not isinstance(is_default, bool):
            return None
        rows.append((tee, is_default))
    return tuple(rows)


def _course_tee_fixtures(body: str) -> dict[str, tuple | None]:
    # G2: `let name = [CourseTee(…), …]` fixtures declared in a Swift test body.
    fixtures: dict[str, tuple | None] = {}
    for match in re.finditer(r"\blet (\w+)\s*(?::\s*\[CourseTee\]\s*)?=\s*\[", body):
        open_at = match.end() - 1
        fixtures[match.group(1)] = _course_tee_rows(body[open_at : _matching(body, open_at) + 1])
    return fixtures


# Python models of the contract's rules


def _text(value):
    # G2: a literal string (or nil) input; a Swift variable cannot be evaluated here.
    if isinstance(value, _Ident):
        raise _Unevaluable(value)
    return value


def _known(value) -> bool:
    # G2: trimmed, non-empty and not `unknown`.
    return value is not None and value.strip() != "" and value.strip().lower() != "unknown"


def _rule_opening_page(initial_page, default_course_global_id):
    # G1: StartRoundView.openingPage(initialPage:defaultCourseGlobalId:).
    if initial_page is not None:
        return initial_page
    return ".course" if default_course_global_id is None else ".setup"


def _rule_preselected_tee(last_used, offered, default_tee):
    # G2: StartRoundPresentation.preselectedTee(lastUsed:offered:defaultTee:).
    last_used, default_tee = _text(last_used), _text(default_tee)
    if isinstance(offered, _Ident):
        raise _Unevaluable(offered)
    offered = [_text(tee) for tee in offered]
    for candidate in (last_used, default_tee):
        if _known(candidate):
            wanted = candidate.strip()
            if not offered:
                return wanted
            for tee in offered:
                if tee.strip().lower() == wanted.lower():
                    return tee
    for tee in offered:
        if tee.strip().lower() in ("blue", "white"):
            return tee
    return offered[0] if offered else ""


def _same_venue(lhs, rhs) -> bool:
    # G2: both non-empty after trimming and equal ignoring case.
    return lhs is not None and rhs is not None and lhs.strip() != "" and lhs.strip().lower() == rhs.strip().lower()


def _rule_last_used_tee(selected_venue, recent_venue, recent_tee, caller_venue, caller_tee):
    # G2: StartRoundPresentation.lastUsedTee(selectedVenue:recentVenue:recentTee:callerVenue:callerTee:).
    selected_venue, recent_venue, recent_tee, caller_venue, caller_tee = (
        _text(value) for value in (selected_venue, recent_venue, recent_tee, caller_venue, caller_tee)
    )
    if _same_venue(recent_venue, selected_venue) and _known(recent_tee):
        return recent_tee.strip()
    if _same_venue(caller_venue, selected_venue) and _known(caller_tee):
        return caller_tee.strip()
    return None


def _rule_tee_after_refresh(current, user_picked, last_used, rows):
    # G2: StartRoundView.teeAfterRefresh(current:userPicked:lastUsed:rows:).
    current, last_used = _text(current), _text(last_used)
    if not isinstance(user_picked, bool):
        raise _Unevaluable(user_picked)
    offered = [tee for tee, _ in rows]
    if user_picked and _known(current):
        for tee in offered:
            if tee.strip().lower() == current.strip().lower():
                return tee
    default = next((tee for tee, is_default in rows if is_default), None)
    return _rule_preselected_tee(last_used, tuple(offered), default)


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


def _capture_segment(snapshots: str, name: str) -> str:
    # G4: the `try captureScreen(` call that names snapshot `name`, as the existing pins slice it.
    marker = f'named: "{name}"'
    if marker not in snapshots:
        raise AssertionError(f"no snapshot named {name}")
    return snapshots.split(marker, 1)[0].rsplit("try captureScreen(", 1)[1]


class StartRoundPagesAcceptanceTests(unittest.TestCase):
    def _check_rule_table(self, cases, convert, rule, required, label: str) -> None:
        # G1 G2: every asserted Swift call agrees with the rule model; every contract case is asserted.
        self.assertTrue(cases, f"{label}: no asserted rule calls found")
        seen = set()
        for args, expected in cases:
            try:
                inputs = convert(args)
                want = rule(*inputs)
            except _Unevaluable:
                continue
            self.assertEqual(
                expected, want, f"{label}{inputs}: the Swift test expects {expected!r}; the contract rule gives {want!r}"
            )
            seen.add(inputs)
        for inputs, result in required:
            self.assertEqual(rule(*inputs), result, f"{label}: contract table self-check {inputs}")
            self.assertIn(inputs, seen, f"{label}: the Swift test lacks the contract case {inputs} -> {result!r}")

    # G1 — phone: two pages

    def test_phone_declares_page_enum_and_opening_rule(self) -> None:
        # G1: Page has exactly course/setup; the snapshot-only initialPage seeds @State page via openingPage.
        code = _code(START_VIEW)
        page = re.search(r"\benum Page\b[^{]*\{", code)
        self.assertIsNotNone(page, "StartRoundView must declare enum Page")
        names: set[str] = set()
        for match in re.finditer(r"\bcase\s+([^\n]+)", _body_at(code, page.end() - 1)):
            names.update(name.strip() for name in match.group(1).split(","))
        self.assertEqual(names, {"course", "setup"})
        self.assertRegex(code, r"\binitialPage:\s*Page\?\s*=\s*nil")
        self.assertRegex(
            code,
            r"\bstatic func openingPage\(\s*initialPage:\s*Page\?\s*,\s*defaultCourseGlobalId:\s*Int\?\s*\)\s*->\s*Page\b",
        )
        self.assertRegex(code, r"@State\s+private\s+var\s+page\s*:\s*Page\b")
        self.assertRegex(
            code,
            r"\b_page\s*=\s*State\(\s*initialValue:\s*Self\.openingPage\(\s*initialPage:\s*initialPage\s*,"
            r"\s*defaultCourseGlobalId:\s*defaultCourseGlobalId\s*\)\s*\)",
        )

    def test_phone_page_bodies_identifiers_and_back_control(self) -> None:
        # G1: page 1 = search + course list only; page 2 = heading, loop, tees, pinned start, back.
        code = _code(START_VIEW)
        course_page = _var_body(self, code, "coursePage")
        setup_page = _var_body(self, code, "setupPage")
        body = _var_body(self, code, "body")
        for name in ("searchEntry", "courseList"):
            self.assertRegex(course_page, rf"\b{name}\b", f"page 1 must show {name}")
        for name in ("loopSection", "teeSection", "startCard"):
            self.assertNotRegex(course_page, rf"\b{name}\b", f"page 1 must not show {name}")
            self.assertRegex(setup_page, rf"\b{name}\b", f"page 2 must show {name}")
        self.assertRegex(setup_page, r"\bselectedVenueName\b", "page 2 is headed by the venue")
        self.assertNotIn("start-round-pinned-actions", course_page)
        self.assertRegex(course_page, r'\.accessibilityIdentifier\(\s*"start-round-page-course"\s*\)')
        self.assertRegex(setup_page, r'\.accessibilityIdentifier\(\s*"start-round-page-setup"\s*\)')
        self.assertRegex(setup_page, r'\.accessibilityIdentifier\(\s*"start-round-back-to-courses"\s*\)')
        self.assertRegex(setup_page, r"(?<![\w.])page\s*=(?!=)\s*\.course\b", "the back control returns to page 1")
        inset = re.search(r"\.safeAreaInset\(\s*edge:\s*\.bottom\s*,\s*spacing:\s*0\s*\)\s*\{", setup_page)
        self.assertIsNotNone(inset, "page 2 pins the start band with .safeAreaInset(edge: .bottom, spacing: 0)")
        band = _body_at(setup_page, inset.end() - 1)
        self.assertRegex(band, r"\bstartCard\b")
        self.assertRegex(band, r'\.accessibilityIdentifier\(\s*"start-round-pinned-actions"\s*\)')
        self.assertRegex(body, r"\bcoursePage\b")
        self.assertRegex(body, r"\bsetupPage\b")
        self.assertRegex(body, r"\bswitch\s+page\b|\bpage\s*[!=]=\s*\.(course|setup)\b")
        self.assertRegex(
            body, r"\.navigationBarBackButtonHidden\(\s*(page\s*==\s*\.setup|page\s*!=\s*\.course)\s*\)"
        )
        for modifier in (
            r'\.navigationTitle\(\s*"开始一场"\s*\)',
            r"\.task\(\s*id:\s*courseGlobalIdText\s*\)",
            r"\.task\(\s*id:\s*nearbyDiscoveryTaskKey\s*\)",
            r"\.sheet\(\s*isPresented:\s*\$showingCourseSearch\s*\)",
        ):
            self.assertRegex(body, modifier)
        for page_body in (course_page, setup_page):
            for shared in (r"\.task\(", r"\.sheet\(", r"\.navigationTitle\("):
                self.assertNotRegex(page_body, shared, "shared modifiers stay on the outer view")

    def test_phone_page_changes_only_on_a_player_pick(self) -> None:
        # G1: page is set only by showSetupPage (.setup) and the back control (.course); only a tapped
        # row or a search pick opens page 2; GPS selection and its clearing never change the page.
        code = _code(START_VIEW)
        assigned = re.findall(r"(?<![\w])(?:self\.)?page\s*=(?!=)\s*\.(\w+)", code)
        self.assertEqual(sorted(assigned), ["course", "setup"], "page is assigned in exactly two places")
        self.assertRegex(code, r"\bprivate func showSetupPage\(\)")
        self.assertRegex(_func_body(self, code, "showSetupPage"), r"(?<![\w.])page\s*=(?!=)\s*\.setup\b")
        calls = len(re.findall(r"\bshowSetupPage\s*\(", code)) - len(re.findall(r"\bfunc\s+showSetupPage\s*\(", code))
        self.assertEqual(calls, 2, "showSetupPage() has exactly two callers")
        row = _func_body(self, code, "selectCourseRow")
        self.assertIn("showSetupPage()", row)
        self.assertRegex(row, r"\A\s*guard\s+let\s+\w+\s*=\s*StartRoundPresentation\.preselectedLoop\(")
        self.assertEqual(len(re.findall(r"\breturn\b", row)), 1, "no early return for the venue already selected")
        search = _func_body(self, code, "selectSearchResult")
        self.assertIn("showSetupPage()", search)
        self.assertGreater(search.index("showSetupPage()"), search.rindex("applySelectedCourse("))
        for name in (
            "ensureDefaultSelection",
            "selectVenue",
            "discoverNearbyCourses",
            "clearAutomaticSelection",
            "selectLoop",
            "loadTees",
        ):
            self.assertNotIn("showSetupPage(", _func_body(self, code, name), name)

    def test_phone_swift_tests_assert_every_opening_case(self) -> None:
        # G1: the native suite asserts the four opening-page cases, each as the contract rule gives.
        body = _func_body(self, _code(DISCOVERY_TESTS), "testOpeningPageIsCourseUnlessACourseIsPassed")
        self._check_rule_table(
            _assert_cases(body, "StartRoundView.openingPage"),
            _literal_args("initialPage", "defaultCourseGlobalId"),
            _rule_opening_page,
            OPENING_TABLE,
            "openingPage",
        )

    # G2 — phone: preselection

    def test_presentation_declares_the_preselection_rules(self) -> None:
        # G2: the three pure rules page 2 uses, with the contract's signatures, in StartRoundPresentation.
        code = _code(PRESENTATION)
        enum = re.search(r"\benum StartRoundPresentation\b[^{]*\{", code)
        self.assertIsNotNone(enum, "missing enum StartRoundPresentation")
        body = _body_at(code, enum.end() - 1)
        self.assertRegex(
            body,
            r"\bstatic func preselectedLoop\(\s*in loops:\s*\[MobileCourseOption\]\s*,\s*current:\s*MobileCourseOption\?\s*,"
            r"\s*recent:\s*MobileCourseOption\?\s*\)\s*->\s*MobileCourseOption\?",
        )
        self.assertRegex(
            body,
            r"\bstatic func preselectedTee\(\s*lastUsed:\s*String\?\s*,\s*offered:\s*\[String\]\s*,"
            r"\s*defaultTee:\s*String\?\s*\)\s*->\s*String\b",
        )
        self.assertRegex(
            body,
            r"\bstatic func lastUsedTee\(\s*selectedVenue:\s*String\s*,\s*recentVenue:\s*String\?\s*,"
            r"\s*recentTee:\s*String\?\s*,\s*callerVenue:\s*String\?\s*,\s*callerTee:\s*String\?\s*\)\s*->\s*String\?",
        )

    def test_tee_refresh_rule_never_lets_the_current_guess_win(self) -> None:
        # G2: the /tees refresh takes the real last used tee; the tee guessed on selection is never
        # passed as lastUsed, and the two-argument form is gone from the view and the Swift tests.
        code = _code(START_VIEW)
        self.assertRegex(
            code,
            r"\bstatic func teeAfterRefresh\(\s*current:\s*String\s*,\s*userPicked:\s*Bool\s*,"
            r"\s*lastUsed:\s*String\?\s*,\s*rows:\s*\[CourseTee\]\s*\)\s*->\s*String\b",
        )
        old_form = r"\bteeAfterRefresh\(\s*current:\s*[^,()]+,\s*rows:"
        self.assertNotRegex(code, old_form)
        self.assertNotRegex(_code(DISCOVERY_TESTS), old_form)
        body = _func_body(self, code, "teeAfterRefresh")
        self.assertRegex(body, r"\buserPicked\b")
        self.assertNotRegex(body, r"\blastUsed:\s*current\b")
        calls = _call_args(body, r"StartRoundPresentation\.preselectedTee")
        self.assertTrue(
            any(re.search(r"\blastUsed:\s*lastUsed\b", call) and "isDefault" in call for call in calls),
            "teeAfterRefresh must call preselectedTee(lastUsed: lastUsed, …, defaultTee: <the isDefault row>)",
        )

    def test_start_round_wires_last_used_tee_into_the_tees_refresh(self) -> None:
        # G2: a tapped row keeps the current / recent loop; /tees answers through the refresh rule with
        # the recent or caller tee of this venue; a tapped tee chip is tracked and reset per course.
        code = _code(START_VIEW)
        self.assertRegex(
            _func_body(self, code, "selectCourseRow"),
            r"StartRoundPresentation\.preselectedLoop\(\s*in:\s*row\.segments\s*,\s*current:\s*selectedSegment\s*,"
            r"\s*recent:\s*recentResolvedCourseOption\s*\)",
        )
        self.assertRegex(code, r"\bprivate let callerCourseGlobalId\s*:\s*Int\?")
        self.assertRegex(code, r"\bprivate let callerTeeBox\s*:\s*String\b")
        self.assertRegex(code, r"\bself\.callerCourseGlobalId\s*=\s*defaultCourseGlobalId\b")
        self.assertRegex(code, r"\bself\.callerTeeBox\s*=\s*defaultTeeBox\b")
        self.assertRegex(code, r"\bprivate var lastUsedTee\s*:\s*String\?")
        last_used = _var_body(self, code, "lastUsedTee")
        calls = _call_args(last_used, r"StartRoundPresentation\.lastUsedTee")
        self.assertEqual(len(calls), 1, "lastUsedTee must call StartRoundPresentation.lastUsedTee once")
        args = _labelled(calls[0])
        for key in ("selectedVenue", "recentVenue", "recentTee", "callerVenue", "callerTee"):
            self.assertIn(key, args)
        self.assertNotEqual(args["recentTee"], "nil")
        self.assertNotEqual(args["callerTee"], "nil")
        for name in ("recentCourseOption", "callerTeeBox", "callerCourseGlobalId", "courseVenueName"):
            self.assertRegex(last_used, rf"\b{name}\b", f"lastUsedTee must read {name}")
        load_tees = _func_body(self, code, "loadTees")
        self.assertRegex(
            load_tees,
            r"\bteeBox\s*=\s*Self\.teeAfterRefresh\(\s*current:\s*teeBox\s*,\s*userPicked:\s*userPickedTee\s*,"
            r"\s*lastUsed:\s*lastUsedTee\s*,\s*rows:\s*tees\s*\)",
        )
        self.assertNotRegex(load_tees, r"\bif\s+!userPickedTee\b")
        self.assertRegex(code, r"@State\s+private\s+var\s+userPickedTee\b")
        self.assertRegex(_func_body(self, code, "teeChip"), r"\buserPickedTee\s*=\s*true\b")
        self.assertRegex(_func_body(self, code, "applySelectedCourse"), r"\buserPickedTee\s*=\s*false\b")

    def test_swift_tee_table_matches_the_contract(self) -> None:
        # G2: every asserted preselectedTee call agrees with the rule; T1–T10 are all asserted.
        body = _func_body(self, _code(DISCOVERY_TESTS), "testPreselectedTeePrefersLastUsedThenCourseDefault")
        self._check_rule_table(
            _assert_cases(body, "StartRoundPresentation.preselectedTee"),
            _literal_args("lastUsed", "offered", "defaultTee"),
            _rule_preselected_tee,
            TEE_TABLE,
            "preselectedTee",
        )

    def test_swift_loop_cases_match_the_contract(self) -> None:
        # G2: current beats recent beats first, also when current is another venue; empty gives nil.
        body = _squash(_func_body(self, _code(DISCOVERY_TESTS), "testPreselectedLoopPrefersCurrentThenRecentThenFirst"))
        self.assertIn(_squash('let loops = [blackKnight(31794, "A"), blackKnight(31795, "B"), blackKnight(31796, "C")]'), body)
        self.assertIn(_squash("let otherVenue = MobileCourseOption("), body)
        for line in (
            "XCTAssertEqual(StartRoundPresentation.preselectedLoop(in: loops, current: loops[2], recent: loops[1])?.globalId, 31796)",
            "XCTAssertEqual(StartRoundPresentation.preselectedLoop(in: loops, current: nil, recent: loops[1])?.globalId, 31795)",
            "XCTAssertEqual(StartRoundPresentation.preselectedLoop(in: loops, current: otherVenue, recent: loops[1])?.globalId, 31795)",
            "XCTAssertEqual(StartRoundPresentation.preselectedLoop(in: loops, current: otherVenue, recent: nil)?.globalId, 31794)",
            "XCTAssertNil(StartRoundPresentation.preselectedLoop(in: [], current: nil, recent: otherVenue))",
        ):
            self.assertIn(_squash(line), body, line)

    def test_swift_last_used_tee_table_matches_the_contract(self) -> None:
        # G2: every asserted lastUsedTee call agrees with the rule; L1–L7 are all asserted.
        body = _func_body(self, _code(DISCOVERY_TESTS), "testLastUsedTeeIsTheRecentThenTheCallerTeeAtThisVenue")
        self._check_rule_table(
            _assert_cases(body, "StartRoundPresentation.lastUsedTee"),
            _literal_args("selectedVenue", "recentVenue", "recentTee", "callerVenue", "callerTee"),
            _rule_last_used_tee,
            LAST_USED_TABLE,
            "lastUsedTee",
        )

    def test_swift_tee_refresh_table_matches_the_contract(self) -> None:
        # G2: every asserted teeAfterRefresh call agrees with the rule; R1–R6 (the guessed Blue losing
        # to the gold default row first) are all asserted against the goldDefault / noDefault fixtures.
        body = _func_body(self, _code(DISCOVERY_TESTS), "testTeeAfterRefreshPrefersTheDefaultRowOverTheGuess")
        fixtures = _course_tee_fixtures(body)

        def convert(args: dict[str, str]) -> tuple:
            missing = [key for key in ("current", "userPicked", "lastUsed", "rows") if key not in args]
            if missing:
                raise AssertionError(f"a teeAfterRefresh call without {missing}: {args}")
            rows_text = args["rows"].strip()
            rows = _course_tee_rows(rows_text) if rows_text.startswith("[") else fixtures.get(rows_text)
            if rows is None:
                raise _Unevaluable(rows_text)
            return (_literal(args["current"]), _literal(args["userPicked"]), _literal(args["lastUsed"]), rows)

        self._check_rule_table(
            _assert_cases(body, "StartRoundView.teeAfterRefresh"),
            convert,
            _rule_tee_after_refresh,
            REFRESH_TABLE,
            "teeAfterRefresh",
        )

    # G3 — Watch: tap a tee to start

    def test_watch_tee_tap_is_the_only_start(self) -> None:
        # G3: start(teeBox:) is fenced, records the tee, then submits selection(teeBox:) — the file's
        # only onStart; selection(teeBox:) builds from its argument; the start button is gone.
        code = _code(WATCH_SETUP)
        self.assertEqual(len(re.findall(r"\bonStart\s*\(", code)), 1, "onStart must be called exactly once")
        self.assertRegex(code, r"\bfunc start\(\s*teeBox:\s*String\s*\)")
        start = _func_body(self, code, "start")
        self.assertRegex(start, r"\A\s*guard\s+!isPreparing\s*(,|&&)\s*!didSubmitStart\s+else\s*\{\s*return\s*\}")
        submit = re.search(r"\bonStart\(\s*selection\(\s*teeBox:\s*teeBox\s*\)\s*\)", start)
        records = re.search(r"\bselectedTee\s*=\s*teeBox\b", start)
        fences = re.search(r"\bdidSubmitStart\s*=\s*true\b", start)
        self.assertIsNotNone(submit, "start must call onStart(selection(teeBox: teeBox))")
        self.assertIsNotNone(records, "start must set selectedTee = teeBox")
        self.assertIsNotNone(fences, "start must set didSubmitStart = true")
        self.assertLess(max(records.start(), fences.start()), submit.start())
        self.assertRegex(code, r"\bfunc selection\(\s*teeBox:\s*String\s*\)\s*->\s*WatchCourseSelection")
        selection = _func_body(self, code, "selection")
        self.assertRegex(selection, r"\bteeBox:\s*teeBox\b")
        self.assertRegex(selection, r"\bfirstHalf:")
        self.assertRegex(selection, r"\bselectedHalf\b")
        self.assertNotRegex(selection, r"\bselectedTee\b(?!\s*:)", "selection(teeBox:) must not read selectedTee")
        self.assertRegex(
            _var_body(self, code, "startSelection"), r"\A\s*(return\s+)?selection\(\s*teeBox:\s*selectedTee\s*\)\s*\Z"
        )
        self.assertNotIn("watch-setup-start", code)
        self.assertNotRegex(code, r"\bvar startAction\b")

    def test_watch_tee_rows_start_the_round_with_default_first(self) -> None:
        # G3: rows come from teeChoices (default first, or the 球场默认 T row); each row's action
        # starts the round; identifiers per tee and for the default row; rows disabled while starting.
        code = _code(WATCH_SETUP)
        self.assertRegex(code, r"\bvar orderedTeeChoices\s*:\s*\[WatchRoundSetupChoicePresentation\]")
        ordered = _var_body(self, code, "orderedTeeChoices")
        self.assertRegex(ordered, r"\bisDefault\b")
        self.assertRegex(ordered, r"\bteeChoice\(\s*for:")
        tee_choices = _var_body(self, code, "teeChoices")
        self.assertRegex(tee_choices, r"\borderedTeeChoices\b")
        self.assertIn('"球场默认 T"', tee_choices)
        self.assertRegex(tee_choices, r"\bisSelected:\s*true\b")
        content = _var_body(self, code, "teeSelectionContent")
        self.assertRegex(content, r"\bteeChoices\b")
        self.assertRegex(content, r"\bavailabilityText\b")
        row_starts = False
        for match in re.finditer(r"\bForEach\s*\(", content):
            close = _matching(content, match.end() - 1)
            brace = content.find("{", close)
            if brace >= 0 and re.search(r"\bstart\(\s*teeBox:", _body_at(content, brace)):
                row_starts = True
        self.assertTrue(row_starts, "a ForEach row action in teeSelectionContent must call start(teeBox:)")
        tee_stage = _var_body(self, code, "teeSelection")
        self.assertRegex(tee_stage, r"\bScrollView\b")
        self.assertRegex(tee_stage, r"\bteeSelectionContent\b")
        identifiers = _call_args(code, r"\.accessibilityIdentifier")
        self.assertTrue(any('"watch-setup-tee-default"' in args for args in identifiers))
        self.assertTrue(any('"watch-setup-tee-\\(' in args for args in identifiers))
        self.assertRegex(code, r"\.disabled\(\s*isPreparing\s*\|\|\s*didSubmitStart\s*\)")
        self.assertIn('return "unknown"', code)
        self.assertEqual(code.count(".ignoresSafeArea(edges: .top)"), 2)

    def test_watch_swift_tests_cover_order_default_row_and_tap_start(self) -> None:
        # G3: native tests pin the default-first order (White, Red, none), the tee-less default row and
        # that a tap submits that tee.
        tests = _code(WATCH_SNAPSHOTS)
        order_body = _func_body(self, tests, "testTeeChoicesListTheDefaultTeeFirstAndHighlighted")
        order = _squash(order_body)
        for fragment in (
            'teeBox: "White"',
            'teeBox: "Red"',
            'tees: ["Blue", "White", "Red"]',
            r"orderedTeeChoices.map(\.title)",
            r"orderedTeeChoices.map(\.isSelected)",
            '["白 T", "蓝 T", "红 T"]',
            '["红 T", "蓝 T", "白 T"]',
            '["蓝 T", "白 T", "红 T"]',
            "[true, false, false]",
        ):
            self.assertIn(_squash(fragment), order, fragment)
        options = [_labelled(args) for args in _call_args(order_body, r"\bWatchCourseOption")]
        self.assertTrue(any(option.get("teeBox", "nil") == "nil" for option in options), "a case without teeBox")
        default_body = _func_body(self, tests, "testATeeLessCourseOffersTheCourseDefaultRow")
        default = _squash(default_body)
        for fragment in (r"teeChoices.map(\.title)", '["球场默认 T"]', r"teeChoices.map(\.isSelected)", "[true]"):
            self.assertIn(_squash(fragment), default, fragment)
        tee_less = [_labelled(args) for args in _call_args(default_body, r"\bWatchCourseOption")]
        self.assertTrue(
            any(option.get("teeBox", "nil") == "nil" and option.get("tees", "[]") == "[]" for option in tee_less),
            "the default-row case has no tees and no teeBox",
        )
        tap = _squash(_func_body(self, tests, "testTappingATeeStartsTheRoundWithThatTee"))
        for fragment in ('.start(teeBox: "Red")', "onStart:", '"Red"', "firstHalf"):
            self.assertIn(_squash(fragment), tap, fragment)

    # G4 — snapshots

    def test_phone_snapshots_capture_both_pages(self) -> None:
        # G4: one capture per page; page 2 is loop B with its tee rows so the chips show yards.
        snapshots = _code(PHONE_SNAPSHOTS)
        self.assertIn(_squash("initialPage: .course"), _squash(_capture_segment(snapshots, "full-start-page-course")))
        setup = _squash(_capture_segment(snapshots, "full-start-page-setup"))
        for fragment in (
            "initialPage: .setup",
            "defaultCourseGlobalId: 31795",
            "initialCourseTees: loopBTees",
            "onLoadCourseTees: { _ in loopBTees }",
        ):
            self.assertIn(_squash(fragment), setup, fragment)

    def test_watch_snapshot_captures_the_tee_list(self) -> None:
        # G4: the tee stage content (no ScrollView) rendered with the White-default fixture.
        body = _squash(_func_body(self, _code(WATCH_SNAPSHOTS), "testRenderWatchCourseSetupTees"))
        for fragment in ('teeBox: "White"', 'tees: ["Blue", "White", "Red"]', '["白 T", "蓝 T", "红 T"]'):
            self.assertIn(_squash(fragment), body, fragment)
        self.assertRegex(body, r'render\(\w+\.teeSelectionContent.*named:"watch-course-setup-tees"\)')

    # G5 — nine-hole loop rules unchanged

    def test_nine_hole_loop_rules_stay_unchanged(self) -> None:
        # G5
        # pinned: README §8 and the one-loop start must keep today's behaviour; this passes on main.
        readme = DESIGN_README.read_text(encoding="utf-8")
        self.assertIn("选第一个 9 洞环（A / B / C 大块）", readme)
        self.assertIn("开始时只选**第一个环**", readme)
        self.assertIn("第二个环打到中途再选", readme)
        self.assertIn("StartRoundPresentation.combinedLoopEntries(selected: course)", _code(START_VIEW))
        watch = _code(WATCH_SETUP)
        self.assertIn('"watch-setup-half-\\(half)"', watch)
        self.assertRegex(watch, r"\bvar halfChoices\s*:")
        self.assertRegex(watch, r"\bvar holeSelectionContent\s*:\s*some View")

    # Real entry point: the repository's unittest runner

    def test_phone_contract_pin_passes(self) -> None:
        # G1 G2 G5: the phone source pin runs and passes through `python -m unittest`.
        code, output = _run_unittest(f"{PIN_CLASS}.{PHONE_PIN}")
        self.assertEqual(code, 0, output)
        self.assertRegex(output, r"Ran 1 test\b")
        self.assertRegex(output, rf"{PHONE_PIN} \(.*\) \.\.\. ok")

    def test_watch_contract_pin_passes(self) -> None:
        # G3 G4 G5: the Watch source pin runs and passes through `python -m unittest`.
        code, output = _run_unittest(f"{PIN_CLASS}.{WATCH_PIN}")
        self.assertEqual(code, 0, output)
        self.assertRegex(output, r"Ran 1 test\b")
        self.assertRegex(output, rf"{WATCH_PIN} \(.*\) \.\.\. ok")

    def test_mobile_source_pin_modules_stay_green(self) -> None:
        # G1 G2 G3 G4 G5: the whole mobile pin modules pass with both new pins and the kept pins.
        code, output = _run_unittest("tests.test_mobile_contracts", "tests.test_native_visual_parity")
        self.assertEqual(code, 0, output[-6000:])
        for name in (PHONE_PIN, WATCH_PIN, *KEPT_PINS):
            self.assertRegex(output, rf"{name} \(.*\) \.\.\. ok", name)


if __name__ == "__main__":
    unittest.main()
