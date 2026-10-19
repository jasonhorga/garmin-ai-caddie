"""Card #434: the Watch hole root goes back to D02 (S70 parity) and draws one aim line only.

The Watch app only runs on macOS (native-mobile CI). These tests run offline on any host: each one
lists the tracked files with `git ls-files` in a subprocess, then checks the tracked Swift sources
and the design README structurally. Comments are ignored and string contents are masked wherever
code structure is analysed. Native XCTests and snapshots (G6) run in native-mobile; the reviewer
compares the snapshots with the S70 evidence document.

Contract: .agent/contracts/card-434.md
"""

from __future__ import annotations

import functools
import re
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TRACKED_ROOTS = ("mobile/ios", "docs/design")
GIT_LS_FILES = ["git", "ls-files", "-z", "--cached", "--", *TRACKED_ROOTS]

MAP_VIEW = "mobile/ios/AICaddieWatch/Views/WatchHoleMapView.swift"
CONTAINER = "mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift"
CADDIE_VIEW = "mobile/ios/AICaddieWatch/Views/WatchCaddieOptionsView.swift"
SNAPSHOT_TESTS = "mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift"
PAGES_UI_TESTS = "mobile/ios/AICaddieWatchUITests/WatchHolePagesUITests.swift"
WATCH_TESTS = "mobile/ios/AICaddieWatchTests/"
WATCH_SWIFT = ("mobile/ios/AICaddieWatch/", "mobile/ios/AICaddieWatchTests/", "mobile/ios/AICaddieWatchUITests/")
README = "docs/design/2026-09-25-ui-redesign/README.md"

# Every call of the D02 rule, never negated or compared: `Self.drawsRouteAndPlan(fullMap: fullMap)`.
POLICY_CALL = re.compile(
    r"(?<![!\w.])(?:(?:Self|WatchHoleMapView)\.)?drawsRouteAndPlan\(\s*fullMap:\s*fullMap\s*\)(?!\s*(?:==|!=|\?))"
)
# A local that shadows the view's own `fullMap` inside a drawing function.
FULL_MAP_SHADOW = re.compile(r"\b(?:let|var)\s+fullMap\b|\bfullMap\s+in\b|(?<![\w.])fullMap\s*=(?!=)")
POLICY_DECL = re.compile(r"\bstatic\s+func\s+drawsRouteAndPlan\s*\(\s*fullMap:\s*Bool\s*\)\s*->\s*Bool")
CURRENT_SHOT_FIELDS = {"player", "target", "carryP10", "carryP90", "continuation"}
KEPT_SNAPSHOTS = (
    "watch-hole-page-plan",
    "watch-hole-page-plan-measure",
    "watch-caddie-options",
    "watch-holemap-measured",
    "watch-holemap-current-shot",
)
PAIRS = {"(": ")", "[": "]", "{": "}"}
# A line ending like this continues on the next one; a line starting like this continues the last.
CONTINUES_AFTER = (",", "&&", "||", "(", "=")
CONTINUES_BEFORE = ("&&", "||", ",", ")", ".")
# Outside brackets, none of these can follow a signature before its body: the next declaration began.
DECLARATION_START = re.compile(
    r"(?:func|var|let|init|deinit|subscript|struct|class|enum|protocol|extension|case|typealias"
    r"|static|private|fileprivate|internal|public|open|override|mutating|nonmutating)\b"
)

# Inline Swift for the parser self-check: empty, typed, throwing, async, multi-line and bodiless
# declarations, a closure default argument and a string holding a bracket.
PARSER_SAMPLE = """struct S {
    func example() { return true }
    func other(_ a: [Int], b: (Int) -> Int = { $0 }) -> Bool {
        a.isEmpty
    }
    func typed(_ shot: Shot, at index: Int) throws -> Int { index }
    func spread(
        over legs: [Leg],
        label: String = ")"
    ) async throws -> [Leg] {
        legs
    }
    func bare()
    var tail: Int { 1 }
}
"""
PARSER_TESTS_SAMPLE = """final class T: XCTestCase {
    func testA() { XCTAssert(true) }
    func testB() throws {
        try f("watch-x")
    }
    func testC(_ unused: Int = 0) async throws { await g(")") }
    func testAB() { h() }
}
"""


# --- Swift source reading -------------------------------------------------------------------------


def _skip_interpolation(src: str, k: int) -> int:
    # G1 G2 G3 G4 G6: from the `(` of a `\(...)` interpolation to just past its `)`.
    depth = 0
    n = len(src)
    while k < n:
        c = src[k]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return k + 1
        elif c == '"':
            m = k + 1
            while m < n and src[m] != '"':
                m += 2 if src[m] == "\\" else 1
            k = m
        k += 1
    return n


def _lex(src: str) -> tuple[str, str]:
    """G1 G2 G3 G4 G6: (code, text), both as long as `src`. `code` blanks comments and string
    contents (brackets inside them cannot unbalance a parse); `text` blanks only comments."""
    code = list(src)
    text = list(src)
    n = len(src)

    def blank(start: int, end: int, *, both: bool) -> None:
        for k in range(start, min(end, n)):
            if src[k] != "\n":
                code[k] = " "
                if both:
                    text[k] = " "

    i = 0
    while i < n:
        if src.startswith("//", i):
            end = src.find("\n", i)
            end = n if end < 0 else end
            blank(i, end, both=True)
            i = end
        elif src.startswith("/*", i):
            depth, j = 0, i
            while j < n:
                if src.startswith("/*", j):
                    depth += 1
                    j += 2
                elif src.startswith("*/", j):
                    depth -= 1
                    j += 2
                    if depth == 0:
                        break
                else:
                    j += 1
            blank(i, j, both=True)
            i = j
        elif src[i] in '#"':
            j = i
            while j < n and src[j] == "#":
                j += 1
            hashes = j - i
            if j >= n or src[j] != '"':
                i = j if hashes else i + 1
                continue
            multi = src.startswith('"""', j)
            terminator = ('"""' if multi else '"') + "#" * hashes
            content = k = j + (3 if multi else 1)
            while k < n:
                if src.startswith(terminator, k):
                    break
                if src[k] == "\\" and src.startswith("#" * hashes, k + 1):
                    k += 1 + hashes
                    if k < n and src[k] == "(":
                        k = _skip_interpolation(src, k)
                    else:
                        k += 1
                    continue
                if not multi and src[k] == "\n":
                    break
                k += 1
            blank(content, k, both=False)
            i = min(k + len(terminator), n)
        else:
            i += 1
    return "".join(code), "".join(text)


@functools.lru_cache(maxsize=None)
def _lexed(relative: str) -> tuple[str, str]:
    # G1 G2 G3 G4 G6: one lexed Swift file, read once per run.
    return _lex((REPO_ROOT / relative).read_text(encoding="utf-8"))


class _Sources:
    """G1 G2 G3 G4 G5 G6: the tracked files under TRACKED_ROOTS, from a `git ls-files` run (or a
    filesystem walk when the checkout has no git metadata)."""

    def __init__(self, listing: subprocess.CompletedProcess) -> None:
        names: set[str] | None = None
        if listing.returncode == 0 and listing.stdout:
            names = {name for name in listing.stdout.decode("utf-8", "surrogateescape").split("\0") if name}
        if names is None:
            names = {
                path.relative_to(REPO_ROOT).as_posix()
                for root in TRACKED_ROOTS
                for path in (REPO_ROOT / root).rglob("*")
                if path.is_file()
            }
        self.names = names

    def swift(self, *prefixes: str) -> list[str]:
        return sorted(name for name in self.names if name.endswith(".swift") and name.startswith(prefixes))

    def read(self, relative: str) -> tuple[str, str]:
        if relative not in self.names:
            raise AssertionError(f"{relative} is not a tracked file")
        return _lexed(relative)

    def read_raw(self, relative: str) -> str:
        if relative not in self.names:
            raise AssertionError(f"{relative} is not a tracked file")
        return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _match(code: str, open_index: int) -> int:
    # G1 G2 G3 G4 G6: index of the bracket closing the one at `open_index`.
    stack: list[str] = []
    for k in range(open_index, len(code)):
        c = code[k]
        if c in PAIRS:
            stack.append(PAIRS[c])
        elif c in ")]}":
            if not stack or stack.pop() != c:
                raise AssertionError(f"unbalanced {c!r} at offset {k}")
            if not stack:
                return k
    raise AssertionError(f"bracket at offset {open_index} is never closed")


def _body(code: str, pattern: str, start: int = 0, end: int | None = None) -> tuple[int, int] | None:
    """G1 G2 G3 G4 G6: (open, close) of the `{ }` body of the first declaration matching `pattern`
    in code[start:end], or None when there is no such declaration or it has no body.

    The pattern may stop anywhere in the signature, including just after the parameter list's `(`:
    brackets the match leaves open are counted, so the scan resumes at the right depth. A `)`, `]`
    or `}` that closes a scope the declaration is inside, or the start of the next declaration,
    means the declaration has no body."""
    match = re.compile(pattern).search(code, start, len(code) if end is None else end)
    if match is None:
        return None
    matched = code[match.start() : match.end()]
    depth = matched.count("(") + matched.count("[") - matched.count(")") - matched.count("]")
    if depth < 0:
        return None
    for k in range(match.end(), len(code)):
        c = code[k]
        if depth == 0 and c.isalpha() and not (code[k - 1].isalnum() or code[k - 1] in "_@#.") and DECLARATION_START.match(code, k):
            return None
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
            if depth < 0:
                return None
        elif c == "}" and depth == 0:
            return None
        elif c == "{" and depth == 0:
            return k, _match(code, k)
    return None


def _required_body(code: str, pattern: str, start: int = 0, end: int | None = None) -> tuple[int, int]:
    # G1 G2 G3 G4 G6: like `_body`, failing when the declaration is missing.
    span = _body(code, pattern, start, end)
    if span is None:
        raise AssertionError(f"declaration /{pattern}/ not found")
    return span


def _calls(code: str, name: str, start: int, end: int) -> list[tuple[int, dict[str, tuple[int, int]]]]:
    """G1 G2 G3 G4 G6: each `name(...)` call in code[start:end], as (offset, labelled arguments).
    Each argument maps its label to the span of its value."""
    calls = []
    for match in re.compile(rf"(?<![\w.]){re.escape(name)}\s*\(").finditer(code, start, end):
        open_index = match.end() - 1
        close = _match(code, open_index)
        calls.append((match.start(), _arguments(code, open_index + 1, close)))
    return calls


def _arguments(code: str, start: int, end: int) -> dict[str, tuple[int, int]]:
    # G1 G2 G3 G4 G6: labelled top-level arguments between the call's parentheses.
    parts = []
    depth = 0
    segment = start
    for k in range(start, end):
        c = code[k]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append((segment, k))
            segment = k + 1
    parts.append((segment, end))
    labelled = {}
    for s, e in parts:
        match = re.match(r"\s*(\w+)\s*:", code[s:e])
        if match:
            labelled[match.group(1)] = (s + match.end(), e)
    return labelled


def _value(code: str, args: dict[str, tuple[int, int]], label: str) -> str | None:
    # G1 G2 G3 G4 G6: the stripped value of one labelled argument, or None when absent.
    if label not in args:
        return None
    s, e = args[label]
    return " ".join(code[s:e].split())


def _statement_before(code: str, position: int) -> str:
    """G1 G4: the statement text that ends at `position` (usually the `{` opening a block),
    joined across continuation lines and cut after any earlier `{` or `;` on them."""
    line_start = code.rfind("\n", 0, position) + 1
    header = code[line_start:position]
    while line_start > 0:
        previous_start = code.rfind("\n", 0, line_start - 1) + 1
        previous = code[previous_start : line_start - 1]
        if previous.rstrip().endswith(CONTINUES_AFTER) or header.lstrip().startswith(CONTINUES_BEFORE):
            header = previous + "\n" + header
            line_start = previous_start
        else:
            break
    cut = max(header.rfind("{"), header.rfind(";"))
    return header[cut + 1 :]


def _enclosing_headers(code: str, start: int, index: int) -> list[str]:
    # G1 G4: the statements opening every `{ }` block of code[start:] that encloses `index`.
    stack: list[int] = []
    for k in range(start, index):
        if code[k] == "{":
            stack.append(k)
        elif code[k] == "}" and stack:
            stack.pop()
    return [_statement_before(code, p) for p in stack]


def _gate_names(code: str, start: int, end: int) -> set[str]:
    # G1: locals bound from the rule, e.g. `let drawsFullPlan = Self.drawsRouteAndPlan(...) && ...`.
    names = set()
    for match in re.finditer(r"\blet\s+(\w+)\s*(?::[^=\n]+)?=\s*([^\n]+)", code[start:end]):
        initializer = match.group(2)
        if POLICY_CALL.search(initializer) and "||" not in initializer:
            names.add(match.group(1))
    return names


def _mentions_gate(header: str, names: set[str]) -> bool:
    # G1: the statement tests the rule itself or a local bound from it, not its negation, a
    # comparison, or a disjunction that would run the code without it.
    if "||" in header:
        return False
    if POLICY_CALL.search(header):
        return True
    return any(re.search(rf"(?<![!\w.]){re.escape(name)}\b(?!\s*(?:=|!=))", header) for name in names)


def _gated(code: str, span: tuple[int, int], index: int, *, own_statement: bool = False) -> bool:
    """G1: whether the code at `index` inside the function body `span` only runs when the rule
    holds: an enclosing block (or, with `own_statement`, the statement at `index`) tests it, or a
    `guard` before `index` in that body does."""
    start, end = span
    names = _gate_names(code, start, end)
    headers = _enclosing_headers(code, start, index)
    if own_statement:
        line_end = code.find("\n", index, end)
        line_end = end if line_end < 0 else line_end
        brace = code.find("{", index, line_end)
        headers.append(_statement_before(code, brace if brace >= 0 else line_end))
    if any(_mentions_gate(header, names) for header in headers):
        return True
    return any(_mentions_gate(guard, names) for guard in _top_level_guards(code, start, index))


def _top_level_guards(code: str, start: int, end: int) -> list[str]:
    # G1: the conditions of the `guard … else` statements directly in the body opening at `start`
    # (not inside a nested block, which would not cover the rest of the body).
    guards = []
    for match in re.finditer(r"\bguard\b(.*?)\belse\b", code[start + 1 : end], re.S):
        before = code[start + 1 : start + 1 + match.start()]
        if before.count("{") == before.count("}"):
            guards.append(match.group(1))
    return guards


def _callee_guarded(code: str, function: str) -> bool:
    # G1: the called function itself starts by guarding on the rule.
    span = _body(code, rf"\bfunc\s+{function}\b")
    if span is None:
        return False
    return any(_mentions_gate(guard, set()) for guard in _top_level_guards(code, *span))


def _call_sites(code: str, function: str) -> list[int]:
    # G1: offsets of every `function(` call in the file, skipping its own declaration.
    return [
        match.start()
        for match in re.finditer(rf"\b{function}\s*\(", code)
        if not re.search(r"\bfunc\s+$", code[max(0, match.start() - 40) : match.start()])
    ]


def _test_functions(code: str) -> list[tuple[str, tuple[int, int]]]:
    # G6: (name, body span) of every `func test…` in a Swift test file.
    functions = []
    for match in re.finditer(r"\bfunc\s+(test\w+)\s*\(", code):
        span = _body(code, rf"\bfunc\s+{match.group(1)}\s*\(", match.start())
        if span is not None:
            functions.append((match.group(1), span))
    return functions


class SwiftBodyParserTests(unittest.TestCase):
    """The declaration parser the goal tests rely on. A pattern may end just after the parameter
    list's `(` (as the G2 and G6 patterns do); that must still find the body."""

    def test_body_is_found_whether_or_not_the_pattern_consumes_the_parenthesis(self) -> None:
        # G2 G6
        # pinned: parser self-check on inline Swift; the goal tests below exercise the real sources.
        listing = subprocess.run(GIT_LS_FILES, cwd=REPO_ROOT, capture_output=True, timeout=120, check=False)
        self.assertIn(CONTAINER, _Sources(listing).names)
        code, _ = _lex(PARSER_SAMPLE)

        def body(pattern: str) -> str | None:
            span = _body(code, pattern)
            return None if span is None else " ".join(code[span[0] : span[1] + 1].split())

        expected = {
            "example": "{ return true }",
            "other": "{ a.isEmpty }",
            "typed": "{ index }",
            "spread": "{ legs }",
        }
        for name, braces in expected.items():
            for pattern in (rf"func\s+{name}\s*\(", rf"func\s+{name}\b", rf"\bfunc\s+{name}\s*\(\s*"):
                self.assertEqual(body(pattern), braces, pattern)
        self.assertEqual(body(r"func\s+example\s*\(\s*\)"), "{ return true }")
        self.assertEqual(body(r"func\s+other\s*\(_\s+a:\s*\["), "{ a.isEmpty }")
        self.assertEqual(body(r"func\s+typed\s*\(_\s+shot:\s*Shot,"), "{ index }")
        self.assertEqual(body(r"func\s+typed\s*\([^)]*\)\s*throws"), "{ index }")
        self.assertEqual(body(r"func\s+spread\s*\(\s*over\s+legs:\s*\[Leg\]"), "{ legs }")
        self.assertIsNone(body(r"func\s+bare\s*\("), "a declaration without a body has none")
        self.assertIsNone(body(r"func\s+bare\b"), "a declaration without a body has none")
        self.assertIsNone(body(r"func\s+missing\s*\("))
        self.assertEqual(body(r"\bvar\s+tail\b"), "{ 1 }")

        tests_code, tests_text = _lex(PARSER_TESTS_SAMPLE)
        functions = _test_functions(tests_code)
        self.assertEqual([name for name, _ in functions], ["testA", "testB", "testC", "testAB"])
        bodies = {name: " ".join(tests_text[s : e + 1].split()) for name, (s, e) in functions}
        self.assertEqual(bodies["testA"], "{ XCTAssert(true) }")
        self.assertEqual(bodies["testB"], '{ try f("watch-x") }')
        self.assertEqual(bodies["testC"], '{ await g(")") }')
        self.assertEqual(bodies["testAB"], "{ h() }")


class WatchRootOneAimLineTests(unittest.TestCase):
    def _sources(self, listing: subprocess.CompletedProcess) -> _Sources:
        # G1 G2 G3 G4 G5 G6: the tracked tree this test checks.
        sources = _Sources(listing)
        self.assertIn(MAP_VIEW, sources.names, "the Watch hole map view must be tracked")
        return sources

    def _root_call(self, code: str) -> dict[str, tuple[int, int]]:
        # G1 G2 G3 G4: the arguments of the hole root's WatchHoleMapView in `holeMapView`.
        span = _required_body(code, r"\bfunc\s+holeMapView\b")
        calls = _calls(code, "WatchHoleMapView", *span)
        self.assertEqual(len(calls), 1, "holeMapView builds exactly one WatchHoleMapView")
        return calls[0][1]

    # G1 — the hole root draws the facts layer and at most one aim line

    def test_map_view_draws_route_and_plan_only_on_a_full_map(self) -> None:
        # G1: the D02 rule exists, is `fullMap`, and gates the factual route, the multi-shot plan and
        # the current-shot continuation; the lightweight fallback stays ungated.
        sources = self._sources(subprocess.run(GIT_LS_FILES, cwd=REPO_ROOT, capture_output=True, timeout=120, check=False))
        code, _ = sources.read(MAP_VIEW)

        declarations = list(POLICY_DECL.finditer(code))
        self.assertEqual(len(declarations), 1, "declare `static func drawsRouteAndPlan(fullMap: Bool) -> Bool` once")
        declaration = declarations[0].start()
        owners = [_required_body(code, r"\bstruct\s+WatchHoleMapView\b")]
        for match in re.finditer(r"\bextension\s+WatchHoleMapView\b", code):
            span = _body(code, r"\bextension\s+WatchHoleMapView\b", match.start())
            if span is not None:
                owners.append(span)
        self.assertTrue(
            any(open_ < declaration < close for open_, close in owners),
            "drawsRouteAndPlan must be a member of WatchHoleMapView",
        )
        rule_span = _required_body(code, POLICY_DECL.pattern)
        self.assertIn(" ".join(code[rule_span[0] + 1 : rule_span[1]].split()), {"fullMap", "return fullMap"})
        for match in re.finditer(r"\bdrawsRouteAndPlan\s*\(", code):
            if match.start() >= declaration and match.start() <= declarations[0].end():
                continue
            close = _match(code, match.end() - 1)
            self.assertEqual(
                " ".join(code[match.end() : close].split()),
                "fullMap: fullMap",
                "every call of the rule passes the view's own fullMap",
            )

        draw_map = _required_body(code, r"\bfunc\s+drawMap\b")
        current_shot = _required_body(code, r"\bfunc\s+drawCurrentShot\b")
        for span in (draw_map, current_shot):
            self.assertNotRegex(
                code[span[0] : span[1]], FULL_MAP_SHADOW, "the rule is applied to the view's own fullMap"
            )

        # Every call in the file, not only those in drawMap: neither drawing may move elsewhere ungated.
        for function, message in (
            ("drawFullPlan", "drawFullPlan is drawn only when drawsRouteAndPlan(fullMap:) holds"),
            ("drawFactualRoute", "the tee-to-green route over the topo image is drawn only when drawsRouteAndPlan(fullMap:) holds"),
        ):
            if _callee_guarded(code, function):
                continue
            for index in _call_sites(code, function):
                self.assertTrue(draw_map[0] < index < draw_map[1], f"{message}: call outside drawMap")
                self.assertTrue(_gated(code, draw_map, index), message)
        full_plan_calls = [index for index in _call_sites(code, "drawFullPlan") if draw_map[0] < index < draw_map[1]]
        self.assertTrue(full_plan_calls, "drawMap still draws the plan for the caddie page")

        uses = [m.start() for m in re.finditer(r"\blayout\.continuation\b", code[: current_shot[1]]) if m.start() > current_shot[0]]
        for index in uses:
            self.assertTrue(
                _gated(code, current_shot, index, own_statement=True),
                "the current-shot continuation is drawn only when drawsRouteAndPlan(fullMap:) holds",
            )

        fallback = [m.start() for m in re.finditer(r"\bdrawLightweightMapFacts\s*\(", code[: draw_map[1]]) if m.start() > draw_map[0]]
        self.assertTrue(fallback, "the lightweight map facts remain the not-ready fallback")
        for index in fallback:
            self.assertFalse(
                any("drawsRouteAndPlan" in header for header in _enclosing_headers(code, draw_map[0], index)),
                "the README §8 fallback is not gated by the root rule",
            )

    def test_hole_root_is_built_without_plan_legs(self) -> None:
        # G1: the container's hole root passes no plan legs and stays a resting (non-full) map.
        sources = self._sources(subprocess.run(GIT_LS_FILES, cwd=REPO_ROOT, capture_output=True, timeout=120, check=False))
        code, _ = sources.read(CONTAINER)

        root = self._root_call(code)

        self.assertNotIn("planLegs", root, "the hole root never receives the multi-shot plan")
        self.assertEqual(_value(code, root, "fullMap"), "false")
        self.assertEqual(_value(code, root, "interactionMode"), ".measure")
        self.assertNotRegex(code, r"\bWatchPlanLegs\.resolve\s*\(", "the container no longer resolves plan legs")
        holemap = _required_body(code, r"\bfunc\s+holeMapView\b")
        self.assertNotRegex(code[holemap[0] : holemap[1]], r"\blet\s+legs\b")

    def test_no_resting_map_is_given_plan_legs(self) -> None:
        # G1 G6: across the tracked Watch app, unit tests and UI tests, only a full map (the caddie
        # page) is handed plan legs; no snapshot asserts the full plan on the root any more.
        sources = self._sources(subprocess.run(GIT_LS_FILES, cwd=REPO_ROOT, capture_output=True, timeout=120, check=False))
        offenders = []
        checked = 0

        for relative in sources.swift(*WATCH_SWIFT):
            code, _ = sources.read(relative)
            if not re.search(r"(?<![\w.])WatchHoleMapView\s*\(", code):
                continue
            for offset, args in _calls(code, "WatchHoleMapView", 0, len(code)):
                checked += 1
                if "planLegs" in args and _value(code, args, "fullMap") != "true":
                    offenders.append(f"{relative}:{code.count(chr(10), 0, offset) + 1}")

        self.assertGreater(checked, 3, "expected the production and snapshot WatchHoleMapView calls")
        self.assertEqual(offenders, [], "resting maps (the hole root) must not receive planLegs")

    # G2 — the recommendation layer appears only when it is real and allowed

    def test_root_recommendation_shows_only_when_real_and_allowed(self) -> None:
        # G2: the club tag (and its aim line) follows the live or prepared-Tee gate, never the mere
        # existence of a plan.
        sources = self._sources(subprocess.run(GIT_LS_FILES, cwd=REPO_ROOT, capture_output=True, timeout=120, check=False))
        code, _ = sources.read(CONTAINER)

        helper = _required_body(code, r"\bfunc\s+showsRootRecommendation\s*\(")
        body = code[helper[0] : helper[1]]
        # The live gate, or the prepared Tee plan with its geometry: nothing else can turn it on.
        self.assertRegex(body, r"\bcurrentShotLayout\s*\(\s*for:\s*s\s*,\s*geometry:\s*geometry\s*\)\s*!=\s*nil")
        self.assertRegex(body, r"\bmodel\.preparedRootCaddieLayerAvailable\s*\(\s*at:\s*shotLocation\s*\)")
        self.assertRegex(body, r"\bpreparedRootGeometry\s*\(\s*for:\s*s\s*,\s*base:\s*geometry\s*\)\s*!=\s*nil")
        self.assertEqual(body.count("||"), 1, "exactly two alternatives: the live gate or the prepared Tee gate")
        self.assertIn("&&", body, "the prepared Tee gate needs both the model gate and the prepared geometry")
        for forbidden in (
            r"\bplanLegs\b",
            r"\blegs\b",
            r"\bcaddieOptions\b",
            r"\bcaddieOption\b",
            r"\bcurrentCaddieOptions\b",
            r"\.count\b",
            r"\.plan\b",
            r"\boptionId\b",
            r"\btrue\b",
            r"!(?!=)",
        ):
            self.assertNotRegex(body, forbidden, "the root layer gate never depends on the plan itself")

        root = self._root_call(code)
        self.assertEqual(
            _value(code, root, "showCaddieRecommendation"),
            "showsRootRecommendation(s, geometry: geometry)",
            "the club tag and aim line follow the gate alone",
        )

    def test_root_aim_line_keeps_real_dispersion_only(self) -> None:
        # G2
        # pinned: one aim line with measured p10/p90 depth, no lateral ellipse, no root continuation.
        sources = self._sources(subprocess.run(GIT_LS_FILES, cwd=REPO_ROOT, capture_output=True, timeout=120, check=False))
        code, text = sources.read(MAP_VIEW)

        layout = _required_body(code, r"\bstruct\s+WatchCurrentShotLayout\b")
        fields = set(re.findall(r"\b(?:public\s+)?let\s+(\w+)\s*:", code[layout[0] : layout[1]]))
        self.assertEqual(fields, CURRENT_SHOT_FIELDS, "no lateral radius or ellipse field is added")
        self.assertIn("carryP10M <= aimCarryM, aimCarryM <= carryP90M", text[layout[0] : layout[1]])

        prepared = _required_body(code, r"\bfunc\s+drawPreparedPlan\b")
        self.assertNotRegex(code[prepared[0] : prepared[1]], r"carryP\d", "the prepared plan has no dispersion")

        overlay = _required_body(code, r"\benum\s+WatchHoleMapRouteOverlay\b")
        resolve = _required_body(code, r"\bstatic\s+func\s+resolve\b", *overlay)
        resolved = code[resolve[0] : resolve[1]]
        order = [resolved.find(token) for token in ("return .measurement", "return .currentShot", "return .preparedPlan")]
        self.assertTrue(all(index >= 0 for index in order) and order == sorted(order), order)

        container, _ = sources.read(CONTAINER)
        shot = _required_body(container, r"\bfunc\s+currentShotLayout\b")
        self.assertIn("model.rootCaddieLayerAvailable(at: shotLocation)", container[shot[0] : shot[1]])
        resolved_calls = _calls(container, "WatchCurrentShotLayout.resolve", *shot)
        self.assertEqual(len(resolved_calls), 1)
        self.assertNotIn("continuation", resolved_calls[0][1], "the root overlay describes only this shot")

    # G3 — tapping the recommended club opens the caddie page

    def test_club_tag_opens_the_caddie_page(self) -> None:
        # G3: the root's club tag and the tap target above the pager open the caddie page; in-place
        # plan cycling is gone.
        sources = self._sources(subprocess.run(GIT_LS_FILES, cwd=REPO_ROOT, capture_output=True, timeout=120, check=False))
        code, _ = sources.read(CONTAINER)

        root = self._root_call(code)
        self.assertEqual(_value(code, root, "onOpenCaddie"), "{ model.openCaddie() }")

        target = _required_body(code, r"\bvar\s+planTagTapTarget\b")
        body = code[target[0] : target[1]]
        self.assertRegex(
            body,
            r"\bshowsRootRecommendation\s*\(\s*s\s*,\s*geometry:\s*geometry\s*\)",
            "the tap target exists exactly when the tag does",
        )
        self.assertNotIn("||", body, "nothing but the recommendation gate shows the tap target")
        for forbidden in (r"count\s*>\s*1", r"\bcaddieOption\b", r"\bcurrentCaddieOptions\b", r"!\s*showsRootRecommendation"):
            self.assertNotRegex(body, forbidden)
        taps = [
            " ".join(code[match.end() : _match(code, match.end() - 1)].split())
            for match in re.compile(r"\.onTapGesture\s*(?:\(\s*\))?\s*\{").finditer(code, target[0], target[1])
        ]
        self.assertEqual(taps, ["model.openCaddie()"], "the tap opens the caddie page and does nothing else")
        self.assertNotRegex(code, r"\bcyclePlan\b", "the root no longer switches plans in place")
        self.assertNotRegex(code, r"\bselectedPlanId\b", "no in-place plan selection is left on the root")

    def test_caddie_page_keeps_the_multi_shot_plan(self) -> None:
        # G3
        # pinned: the caddie page already draws the whole plan on a full map and browses plans by Crown.
        sources = self._sources(subprocess.run(GIT_LS_FILES, cwd=REPO_ROOT, capture_output=True, timeout=120, check=False))
        code, _ = sources.read(CADDIE_VIEW)

        instrument = _required_body(code, r"\bfunc\s+optionInstrument\b")
        calls = _calls(code, "WatchHoleMapView", *instrument)
        self.assertEqual(len(calls), 1)
        args = calls[0][1]
        self.assertEqual(_value(code, args, "planLegs"), "legs")
        self.assertEqual(_value(code, args, "fullMap"), "true")
        self.assertEqual(_value(code, args, "showCaddieRecommendation"), "true")
        self.assertRegex(code, r"\.digitalCrownRotation\s*\(")
        self.assertRegex(code, r"\bstatic\s+func\s+clubChain\b")

        map_code, _ = sources.read(MAP_VIEW)
        draw_map = _required_body(map_code, r"\bfunc\s+drawMap\b")
        self.assertRegex(map_code[draw_map[0] : draw_map[1]], r"\bdrawFullPlan\s*\(")

    # G4 — Touch Targeting, the map fallback and the 999 state are unchanged

    def test_touch_targeting_fallback_and_waiting_state_are_unchanged(self) -> None:
        # G4
        # pinned: Touch Targeting's two ranges, the README §8 fallback and 999 / 等待定位 stay as today.
        sources = self._sources(subprocess.run(GIT_LS_FILES, cwd=REPO_ROOT, capture_output=True, timeout=120, check=False))
        code, text = sources.read(MAP_VIEW)

        draw_map = _required_body(code, r"\bfunc\s+drawMap\b")
        drawn = code[draw_map[0] : draw_map[1]]
        self.assertRegex(drawn, r"\bWatchTouchTargetDistanceLayout\.resolve\s*\(")
        self.assertRegex(drawn, r"\bplayerToTargetYards\b")
        self.assertRegex(drawn, r"\btargetToPinYards\b")
        self.assertRegex(drawn, r"\bdrawMeasurementRoute\s*\(")
        fallback = [m.start() for m in re.finditer(r"\bdrawLightweightMapFacts\s*\(", code[: draw_map[1]]) if m.start() > draw_map[0]]
        self.assertTrue(fallback)
        for index in fallback:
            self.assertFalse(any("drawsRouteAndPlan" in h for h in _enclosing_headers(code, draw_map[0], index)))

        overlay = _required_body(code, r"\benum\s+WatchHoleMapRouteOverlay\b")
        resolve = _required_body(code, r"\bstatic\s+func\s+resolve\b", *overlay)
        self.assertRegex(
            code[resolve[0] : resolve[1]].strip("{ \n"),
            r"^if let measuredPoint \{ return \.measurement\(measuredPoint\) \}",
        )

        label = _required_body(code, r"\bfunc\s+centerRangeLabel\b")
        self.assertIn('"999 码 · 等待定位"', text[label[0] : label[1]])
        self.assertIn('Text("等待定位")', text)

        container, container_text = sources.read(CONTAINER)
        distance = _required_body(container, r"\bvar\s+distanceText\b")
        self.assertIn('"999 码 · 等待定位"', container_text[distance[0] : distance[1]])
        detail = _required_body(container, r"\bfunc\s+holeMapDetailView\b")
        detail_calls = _calls(container, "WatchHoleMapView", *detail)
        self.assertEqual(len(detail_calls), 1)
        self.assertEqual(_value(container, detail_calls[0][1], "interactionMode"), ".touchTarget")
        self.assertEqual(_value(container, detail_calls[0][1], "fullMap"), "true")
        self.assertEqual(_value(container, self._root_call(container), "interactionMode"), ".measure")

    # G5 — the design README agrees with D02

    def test_readme_watch_plan_item_follows_d02(self) -> None:
        # G5: README §3 本洞 item 1 no longer promises the AI route with labels on the root.
        sources = self._sources(subprocess.run(GIT_LS_FILES, cwd=REPO_ROOT, capture_output=True, timeout=120, check=False))
        readme = sources.read_raw(README)

        section = re.search(r"^## 3\..*?(?=^## )", readme, re.M | re.S)
        self.assertIsNotNone(section, "README §3 (手表) is missing")
        item = re.search(r"^[ \t]*1\.[ \t].*?(?=^[ \t]*2\.[ \t])", section.group(0), re.M | re.S)
        self.assertIsNotNone(item, "README §3 本洞 list item 1 is missing")
        text = item.group(0)
        for superseded in ("地图画 AI 球童路线", "点它换方案"):
            self.assertNotIn(superseded, text)
        for required in ("D02", "瞄准线", "球童页", "不画"):
            self.assertIn(required, text)

    # G6 — native tests and snapshots show the new root for review

    def test_native_tests_cover_the_root_and_the_caddie_page(self) -> None:
        # G6: the unit test of the rule, the two root snapshots, the kept snapshots and the UI test
        # that the club tag opens the caddie page.
        sources = self._sources(subprocess.run(GIT_LS_FILES, cwd=REPO_ROOT, capture_output=True, timeout=120, check=False))

        rule_tests = []
        for relative in sources.swift(WATCH_TESTS):
            code, text = sources.read(relative)
            span = _body(code, r"\bfunc\s+testHoleRootNeverDrawsTheRouteOrTheMultiShotPlan\s*\(")
            if span is not None:
                rule_tests.append(" ".join(text[span[0] : span[1]].split()))
        self.assertEqual(len(rule_tests), 1, "one testHoleRootNeverDrawsTheRouteOrTheMultiShotPlan")
        self.assertRegex(rule_tests[0], r"XCTAssertFalse\( ?WatchHoleMapView\.drawsRouteAndPlan\(fullMap: false\)")
        self.assertRegex(rule_tests[0], r"XCTAssertTrue\( ?WatchHoleMapView\.drawsRouteAndPlan\(fullMap: true\)")

        code, text = sources.read(SNAPSHOT_TESTS)
        functions = _test_functions(code)
        self.assertGreater(len(functions), 5, "the snapshot test functions are discovered")

        def rendering(name: str) -> list[tuple[int, int]]:
            return [span for _, span in functions if f'"{name}"' in text[span[0] : span[1]]]

        root = rendering("watch-hole-root-aim-line")
        self.assertEqual(len(root), 1, "one test renders watch-hole-root-aim-line")
        root_calls = _calls(code, "WatchHoleMapView", *root[0])
        self.assertTrue(
            any(
                _value(code, args, "interactionMode") == ".measure"
                and _value(code, args, "playerMarker") == ".chevron"
                and _value(code, args, "showCaddieRecommendation") == "true"
                and _value(code, args, "currentShotLayout") not in (None, "nil")
                and _value(code, args, "fullMap") in (None, "false")
                and "planLegs" not in args
                for _, args in root_calls
            ),
            "watch-hole-root-aim-line renders a production-like root with a live current shot",
        )

        container = rendering("watch-container-root-aim-line")
        self.assertEqual(len(container), 1, "one test renders watch-container-root-aim-line")
        body_code = code[container[0][0] : container[0][1]]
        body_text = text[container[0][0] : container[0][1]]
        self.assertRegex(body_code, r"(?<![\w.])WatchRoundContainerView\s*\(")
        self.assertRegex(body_code, r"\bholeGeometry\s*:")
        self.assertIn("rootCaddieRecommendation", body_text)
        self.assertTrue(
            body_text.count("WatchCaddiePlanStep(") >= 2 or '"plan"' in body_text,
            "the container root is given a multi-shot plan",
        )
        self.assertNotRegex(body_code, r"\b(openHoleMap|openCaddie)\s*\(", "render the root, not another screen")

        for name in KEPT_SNAPSHOTS:
            self.assertIn(f'"{name}"', text, f"{name} is still rendered for review")

        ui_code, ui_text = sources.read(PAGES_UI_TESTS)
        self.assertNotRegex(ui_code, r"\btestAfterTheTeeShotThePlanTagShowsTheNextClubAndSwitchesPlans\b")
        self.assertNotIn("switches plan", ui_text)
        tap = _body(ui_code, r"\bfunc\s+testTappingThePlanTagOpensTheCaddiePage\s*\(")
        self.assertIsNotNone(tap, "WatchHolePagesUITests.testTappingThePlanTagOpensTheCaddiePage")
        tap_text = ui_text[tap[0] : tap[1]]
        self.assertIn('"watch-plan-club-tag"', tap_text)
        self.assertRegex(ui_code[tap[0] : tap[1]], r"\.tap\(\)")
        self.assertIn('"watch-caddie-instrument"', tap_text)


if __name__ == "__main__":
    unittest.main()
