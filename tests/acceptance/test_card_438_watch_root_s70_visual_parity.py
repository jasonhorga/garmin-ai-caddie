"""Card #438: the Watch hole root looks like the S70 hole view.

#434 made the root's content right (facts layer, one aim line, club, no full route). This card is the
visual pass: a yellow player disc with a black navigation arrow, a small depth square at the landing,
a distance arc through it, an aim line that stops at the square, S70-sized remaining-yard markers and
a compact caddie chip.

The Watch app only builds on macOS (native-mobile CI). Like card #434's module, every test here lists
the tracked files with `git ls-files` in a subprocess and checks the tracked Swift sources and the
design README structurally; comments are ignored and string contents are masked wherever code
structure is analysed. The native tests these checks require render the root with `ImageRenderer`
and sample its pixels, so a Swift change that breaks a goal fails a native test. The reviewer compares
the snapshots with the two Garmin images on the card.

The Swift lexer and declaration parser are card #434's (its pinned parser self-check covers them).

Contract: .agent/contracts/card-438.md
"""

from __future__ import annotations

import re
import subprocess
import unittest

from .test_card_434_watch_root_one_aim_line import (
    GIT_LS_FILES,
    NATIVE_ESCAPES,
    REPO_ROOT,
    _arguments,
    _body,
    _calls,
    _enclosing_headers,
    _match,
    _required_body,
    _Sources,
    _statement_before,
    _test_functions,
    _value,
)


MAP_VIEW = "mobile/ios/AICaddieWatch/Views/WatchHoleMapView.swift"
CONTAINER = "mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift"
CADDIE_VIEW = "mobile/ios/AICaddieWatch/Views/WatchCaddieOptionsView.swift"
SNAPSHOT_TESTS = "mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift"
WATCH_TESTS = "mobile/ios/AICaddieWatchTests/"
README = "docs/design/2026-09-25-ui-redesign/README.md"

# Native tests (any file under WATCH_TESTS, exactly one function of each name).
MARKS_TEST = "testRootShotMarksFollowTheS70Geometry"
DISC_TEST = "testHoleRootDrawsTheS70PlayerDisc"
BOX_TEST = "testHoleRootDrawsTheBoxArcAndShortAimLine"
PREPARED_TEST = "testPreparedRootDrawsTheAimLineAndArcWithoutABox"
MARKERS_TEST = "testRemainingMarkersAreS70Sized"
CHIP_TEST = "testRootCaddieChipIsCompactAndClearOfTheControls"
FOOTPRINT_TEST = "testCurrentShotFootprintHasNoFabricatedLateralDispersion"

# The two carry points default to nil, so the prepared plan can call `resolve(player:landing:)`
# (card #434's pinned check keeps every `carryP…` token out of `drawPreparedPlan`).
MARKS_RESOLVE = re.compile(
    r"\bstatic\s+func\s+resolve\s*\(\s*player:\s*CGPoint\s*,\s*landing:\s*CGPoint\s*,"
    r"\s*carryP10:\s*CGPoint\?\s*=\s*nil\s*,\s*carryP90:\s*CGPoint\?\s*=\s*nil\s*\)\s*->\s*WatchRootShotMarks\?"
)
CANVAS_POINT = re.compile(
    r"\bfunc\s+canvasPoint\s*\(\s*_\s+imagePoint:\s*CGPoint\s*,\s*in\s+size:\s*CGSize\s*\)\s*->\s*CGPoint"
)
MARKS_FIELDS = {"player", "landing", "heading", "boxSide", "aimStart", "aimEnd", "arcRadius"}
# A second, lateral extent of the square would be the fabricated dispersion the card forbids.
LATERAL_FIELD = re.compile(r"(?i)lateral|ellipse|boxWidth|boxDepth|width|depth")
FACES = ("CGSize(width: 176, height: 215)", "CGSize(width: 198, height: 242)", "CGSize(width: 205, height: 251)")
STRING_LITERAL = re.compile(r'"((?:[^"\\\n]|\\.)*)"')


def _listing() -> subprocess.CompletedProcess:
    # G1 G2 G3 G4 G5 G6 G7 G8: the tracked tree, from the real `git ls-files` command.
    return subprocess.run(GIT_LS_FILES, cwd=REPO_ROOT, capture_output=True, timeout=120, check=False)


def _static_number(code: str, span: tuple[int, int], name: str) -> float:
    # G2 G3 G5: the literal value of `static let <name>: CGFloat = <number>` inside `span`.
    match = re.compile(rf"\bstatic\s+let\s+{name}\s*(?::\s*CGFloat)?\s*=\s*(\d+(?:\.\d+)?)\b").search(
        code, span[0], span[1]
    )
    if match is None:
        raise AssertionError(f"`static let {name}: CGFloat = <number>` not found")
    return float(match.group(1))


def _top_level(code: str, span: tuple[int, int]) -> str:
    # G2 G3 G4: the body of a type with every nested bracket's contents blanked, so only its own
    # member declarations remain (no locals of its functions).
    out = []
    depth = 0
    for c in code[span[0] + 1 : span[1]]:
        if c in "([{":
            depth += 1
            out.append(c if depth == 1 else " ")
        elif c in ")]}":
            out.append(c if depth == 1 else " ")
            depth -= 1
        else:
            out.append(c if depth == 0 or c == "\n" else " ")
    return "".join(out)


def _stored_fields(code: str, span: tuple[int, int]) -> set[str]:
    # G2 G3 G4: names of the instance `let`/`var` members declared directly in the type body.
    members = _top_level(code, span)
    return {
        match.group(1)
        for match in re.finditer(r"\b(?:let|var)\s+(\w+)\s*:", members)
        if not re.search(r"\bstatic\s+(?:\w+\s+)*$", members[max(0, match.start() - 30) : match.start()])
    }


def _member_calls(code: str, method: str, span: tuple[int, int]) -> list[dict[str, tuple[int, int]]]:
    # G3 G4: the labelled arguments of every `.method(...)` call (for example `arc.addArc(`) in span.
    calls = []
    for match in re.compile(rf"\.{re.escape(method)}\s*\(").finditer(code, span[0], span[1]):
        open_index = match.end() - 1
        calls.append(_arguments(code, open_index + 1, _match(code, open_index)))
    return calls


def _comment_blocks(raw: str) -> list[str]:
    # G2: runs of consecutive `//` / `///` comment lines, joined.
    blocks, current = [], []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            current.append(stripped.lstrip("/ "))
        elif current:
            blocks.append(" ".join(current))
            current = []
    if current:
        blocks.append(" ".join(current))
    return blocks


def _enclosing_block(code: str, index: int, needle: str) -> tuple[int, int] | None:
    # G6: the innermost `{ }` block around `index` whose opening statement mentions `needle`.
    stack: list[int] = []
    for k in range(index):
        if code[k] == "{":
            stack.append(k)
        elif code[k] == "}" and stack:
            stack.pop()
    for open_index in reversed(stack):
        if needle in _statement_before(code, open_index):
            return open_index, _match(code, open_index)
    return None


class WatchRootS70VisualParityTests(unittest.TestCase):
    def _sources(self) -> _Sources:
        # G1 G2 G3 G4 G5 G6 G7 G8: the tracked tree this test checks.
        sources = _Sources(_listing())
        self.assertIn(MAP_VIEW, sources.names, "the Watch hole map view must be tracked")
        return sources

    def _native_test(self, sources: _Sources, name: str) -> tuple[str, str, str, tuple[int, int]]:
        # G1 G2 G3 G4 G5 G6: (file, code, text, body span) of the one native test `name`.
        found = []
        for relative in sources.swift(WATCH_TESTS):
            code, text = sources.read(relative)
            for match in re.finditer(rf"\bfunc\s+{name}\s*\(", code):
                span = _body(code, rf"\bfunc\s+{name}\s*\(", match.start())
                if span is not None:
                    found.append((relative, code, text, span))
        self.assertEqual(len(found), 1, f"exactly one native {name} under {WATCH_TESTS}")
        relative, code, _, (start, end) = found[0]
        self.assertNotRegex(code[start:end], NATIVE_ESCAPES, f"{name} neither skips nor expects its own failure")
        return found[0]

    def _assert_native(
        self,
        sources: _Sources,
        name: str,
        tokens: tuple[str, ...],
        *,
        pixels: bool,
        assertions: int,
        forbidden: tuple[str, ...] = (),
    ) -> str:
        # G1 G2 G3 G4 G5 G6: the native test exists, uses the named seams and asserts enough.
        relative, code, text, (start, end) = self._native_test(sources, name)
        body_code = code[start:end]
        body_text = text[start:end]
        if pixels:
            self.assertRegex(code, r"\bImageRenderer\s*\(", f"{relative} renders pixels for {name}")
            self.assertRegex(body_code, r"(?<![\w.])WatchHoleMapView\s*\(", f"{name} renders the production map")
        for token in tokens:
            self.assertIn(token, body_text, f"{name} uses {token}")
        for token in forbidden:
            self.assertNotIn(token, body_text, f"{name} must not use {token}")
        count = len(re.findall(r"\bXCTAssert\w*\s*\(", body_code))
        self.assertGreaterEqual(count, assertions, f"{name} makes at least {assertions} assertions")
        return body_text

    def _marks(self, code: str) -> tuple[int, int]:
        # G2 G3 G4: the body of `struct WatchRootShotMarks`.
        return _required_body(code, r"\bstruct\s+WatchRootShotMarks\b")

    def _draw_marks(self, code: str) -> tuple[int, int]:
        # G2 G3 G4: the body of the one function that draws the S70 marks.
        return _required_body(code, r"\bfunc\s+drawRootShotMarks\s*\(")

    # G1 — the player is a yellow disc with a black navigation arrow along the aim

    def test_root_player_marker_is_the_s70_disc(self) -> None:
        # G1: `.chevron` (the root's style) now draws the disc; the thin white chevron is gone.
        sources = self._sources()
        code, _ = sources.read(MAP_VIEW)

        styles = _required_body(code, r"\benum\s+WatchPlayerMarkerStyle\b")
        cases = set(re.findall(r"\bcase\s+(\w+)", code[styles[0] : styles[1]]))
        self.assertEqual(cases, {"youDot", "chevron"}, "the root keeps `.chevron`; #434's checks name it")

        draw_map = _required_body(code, r"\bfunc\s+drawMap\b")
        drawn = code[draw_map[0] : draw_map[1]]
        self.assertNotRegex(drawn, r"\bvar\s+chevron\b", "the thin white chevron path is gone")
        calls = [m.start() for m in re.finditer(r"(?<![\w.])drawPlayerDisc\s*\(", code) if draw_map[0] < m.start() < draw_map[1]]
        self.assertEqual(len(calls), 1, "drawMap draws the disc once")
        self.assertEqual(
            len(list(re.finditer(r"(?<![\w.])drawPlayerDisc\s*\(", code))), 2, "one declaration and one call"
        )
        headers = _enclosing_headers(code, draw_map[0], calls[0])
        self.assertTrue(
            any("playerMarker == .chevron" in h and "!rangeUnavailable" in h and "||" not in h for h in headers),
            "the disc is drawn for `.chevron` with a qualified fix only (the 999 state hides it)",
        )

        disc = _required_body(code, r"\bfunc\s+drawPlayerDisc\s*\(")
        body = code[disc[0] : disc[1]]
        self.assertRegex(body, r"\bPath\s*\(\s*ellipseIn:", "a disc")
        self.assertRegex(body, r"\b(?:golfYellow|hudYellow)\b", "a yellow disc")
        self.assertRegex(body, r"\.black\b", "a black arrow")
        self.assertIn("WatchRootShotMarks.playerDiscRadius", body)
        self.assertRegex(body, r"\bheading\b", "the arrow is rotated to the aim")
        self.assertNotRegex(body, r"\byouBlue\b")

        seam = list(CANVAS_POINT.finditer(code))
        self.assertEqual(len(seam), 1, "declare `func canvasPoint(_ imagePoint: CGPoint, in size: CGSize) -> CGPoint`")
        self.assertNotRegex(code, r"\b(?:private|fileprivate)\s+(?:\w+\s+)*func\s+canvasPoint\b", "internal seam")
        seam_body = _required_body(code, CANVAS_POINT.pattern)
        self.assertRegex(code[seam_body[0] : seam_body[1]], r"\banchors\s*\(\s*size\s*\)\s*\.t\s*\(", "the drawing transform")

        container, _ = sources.read(CONTAINER)
        holemap = _required_body(container, r"\bfunc\s+holeMapView\b")
        root = _calls(container, "WatchHoleMapView", *holemap)
        self.assertEqual(len(root), 1)
        self.assertEqual(_value(container, root[0][1], "playerMarker"), ".chevron")

        self._assert_native(
            sources,
            DISC_TEST,
            ("playerMarker: .chevron", "rangeUnavailable: true", "canvasPoint(", "WatchRootShotMarks.playerDiscRadius"),
            pixels=True,
            assertions=4,
            forbidden=("fullMap: true",),
        )

    # G2 — the landing is a small square whose depth is the real p10–p90 and whose width equals it

    def test_dispersion_is_a_depth_square_without_lateral_data(self) -> None:
        # G2: one side length, clamped 14–28 pt, from p10/p90; no lateral field, label or green dot.
        sources = self._sources()
        code, text = sources.read(MAP_VIEW)

        marks = self._marks(code)
        fields = _stored_fields(code, marks)
        self.assertTrue(MARKS_FIELDS <= fields, f"WatchRootShotMarks stores {sorted(MARKS_FIELDS)}; has {sorted(fields)}")
        self.assertEqual([f for f in fields if LATERAL_FIELD.search(f)], [], "one side length, no lateral extent")
        self.assertRegex(_top_level(code, marks), r"\blet\s+boxSide\s*:\s*CGFloat\?", "no box without real p10/p90")
        minimum = _static_number(code, marks, "minimumBoxSide")
        maximum = _static_number(code, marks, "maximumBoxSide")
        self.assertTrue(12 <= minimum <= 16, minimum)
        self.assertTrue(26 <= maximum <= 30, maximum)
        self.assertEqual(len(list(MARKS_RESOLVE.finditer(code))), 1, "declare WatchRootShotMarks.resolve once")
        resolve = _required_body(code, MARKS_RESOLVE.pattern)
        self.assertTrue(marks[0] < resolve[0] < marks[1], "resolve is a member of WatchRootShotMarks")
        resolved = code[resolve[0] : resolve[1]]
        for token in ("minimumBoxSide", "maximumBoxSide", "carryP10", "carryP90", "hypot("):
            self.assertIn(token, resolved)

        layout = _required_body(code, r"\bstruct\s+WatchCurrentShotLayout\b")
        self.assertEqual(
            _stored_fields(code, layout),
            {"player", "target", "carryP10", "carryP90", "continuation"},
            "the live layout still carries carry depth only",
        )

        draw = self._draw_marks(code)
        drawn = code[draw[0] : draw[1]]
        self.assertRegex(drawn, r"\bPath\s*\(\s*roundedRect:", "a rounded square")
        self.assertIn("boxSide", drawn)
        self.assertRegex(drawn, r"\.white\b", "white outline and light fill")
        self.assertNotRegex(drawn, r"\bcaddieGreen\b", "the green landing dot is gone")
        self.assertNotRegex(drawn, r"\bPath\s*\(\s*ellipseIn:", "no dot and no ellipse")

        current = _required_body(code, r"\bfunc\s+drawCurrentShot\b")
        shot_calls = _calls(code, "WatchRootShotMarks.resolve", *current)
        self.assertEqual(len(shot_calls), 1, "drawCurrentShot resolves the S70 marks once")
        for label in ("carryP10", "carryP90"):
            self.assertNotIn(_value(code, shot_calls[0][1], label), (None, "nil"), f"the live shot passes its real {label}")
        self.assertRegex(code[current[0] : current[1]], r"(?<![\w.])drawRootShotMarks\s*\(")

        self.assertTrue(
            any(
                re.search(r"(?i)\blateral\b", block) and re.search(r"(?i)\bwidth\b", block) and re.search(r"(?i)\bdepth\b", block)
                for block in _comment_blocks(sources.read_raw(MAP_VIEW))
            ),
            "a code comment says the square's width equals its depth because there is no lateral data",
        )
        for relative in (MAP_VIEW, CONTAINER):
            _, file_text = sources.read(relative)
            for literal in STRING_LITERAL.findall(file_text):
                self.assertNotRegex(literal, r"(?i)lateral|横向", f"{relative} labels nothing as lateral dispersion")

        self._assert_native(
            sources,
            MARKS_TEST,
            ("minimumBoxSide", "maximumBoxSide", "carryP10: nil", ".boxSide"),
            pixels=False,
            assertions=10,
        )
        _, marks_code, _, marks_span = self._native_test(sources, MARKS_TEST)
        self.assertGreaterEqual(
            len(re.findall(r"\bWatchRootShotMarks\.resolve\s*\(", marks_code[marks_span[0] : marks_span[1]])),
            5,
            "in range, clamped low, clamped high, no dispersion and a degenerate case, written out",
        )
        self.assertRegex(marks_code[marks_span[0] : marks_span[1]], r"\bXCTAssertNil\s*\(")
        self._assert_native(
            sources,
            BOX_TEST,
            (
                "WatchCurrentShotLayout.resolve(",
                "WatchRootShotMarks.resolve(",
                "canvasPoint(",
                "showCaddieRecommendation: true",
                "showCaddieRecommendation: false",
                "fullMap: false",
                "boxSide",
            ),
            pixels=True,
            assertions=8,
            forbidden=("fullMap: true",),
        )
        self._assert_native(
            sources,
            FOOTPRINT_TEST,
            ("WatchRootShotMarks.resolve(", "decorativeEllipse", "boxSide"),
            pixels=True,
            assertions=3,
        )

    # G3 — a thin arc through the landing, centred on the player, about ±25° of the aim

    def test_distance_arc_marks_the_club_distance(self) -> None:
        # G3: the arc's radius is player→landing and its span follows the aim; the prepared Tee plan
        # draws the same arc and aim line with no square.
        sources = self._sources()
        code, _ = sources.read(MAP_VIEW)

        marks = self._marks(code)
        half_angle = _static_number(code, marks, "arcHalfAngleDegrees")
        self.assertTrue(20 <= half_angle <= 30, half_angle)
        self.assertRegex(_top_level(code, marks), r"\blet\s+arcRadius\s*:\s*CGFloat\b")
        self.assertRegex(_top_level(code, marks), r"\blet\s+heading\s*:\s*CGFloat\b")

        draw = self._draw_marks(code)
        arcs = _member_calls(code, "addArc", draw)
        self.assertEqual(len(arcs), 1, "drawRootShotMarks draws one arc")
        arc = arcs[0]
        self.assertRegex(_value(code, arc, "center") or "", r"\.player\b", "centred on the player")
        self.assertRegex(_value(code, arc, "radius") or "", r"\.arcRadius\b", "radius = player→landing")
        for label in ("startAngle", "endAngle"):
            value = _value(code, arc, label) or ""
            self.assertRegex(value, r"\bheading\b", f"{label} follows the aim")
            self.assertRegex(value, r"\barcHalfAngleDegrees\b", f"{label} spans the configured half angle")

        prepared = _required_body(code, r"\bfunc\s+drawPreparedPlan\b")
        prepared_calls = _calls(code, "WatchRootShotMarks.resolve", *prepared)
        self.assertEqual(len(prepared_calls), 1, "the prepared plan resolves the S70 marks")
        self.assertEqual(
            set(prepared_calls[0][1]), {"player", "landing"}, "a prepared plan has no dispersion: no carry points"
        )
        drawn = code[prepared[0] : prepared[1]]
        self.assertRegex(drawn, r"(?<![\w.])drawRootShotMarks\s*\(")
        self.assertNotRegex(drawn, r"\baddQuadCurve\b", "a straight S70 aim line, not the old curve")
        self.assertNotRegex(drawn, r"\bcaddieGreen\b", "no green landing dot")
        self.assertNotRegex(drawn, r"carryP\d", "the prepared plan invents no dispersion (#434 G2)")

        self._assert_native(sources, BOX_TEST, ("arcHalfAngleDegrees", "arcRadius", "heading"), pixels=True, assertions=8)
        self._assert_native(
            sources,
            PREPARED_TEST,
            ("showPreparedPlan: true", "layupPx", "canvasPoint(", "WatchRootShotMarks.resolve(", "arcRadius", "boxSide"),
            pixels=True,
            assertions=4,
            forbidden=("fullMap: true",),
        )
        self._assert_native(sources, MARKS_TEST, (".arcRadius", ".heading"), pixels=False, assertions=10)

    # G4 — the aim line runs from the disc edge to the near edge of the square, not through it

    def test_aim_line_stops_at_the_near_edge_of_the_square(self) -> None:
        # G4: the line is drawn from `aimStart` to `aimEnd`, both resolved from the disc and the square.
        sources = self._sources()
        code, _ = sources.read(MAP_VIEW)

        marks = self._marks(code)
        fields = _stored_fields(code, marks)
        self.assertTrue({"aimStart", "aimEnd"} <= fields, sorted(fields))
        disc_radius = _static_number(code, marks, "playerDiscRadius")
        self.assertTrue(6 <= disc_radius <= 8, disc_radius)
        resolve = _required_body(code, MARKS_RESOLVE.pattern)
        resolved = code[resolve[0] : resolve[1]]
        self.assertIn("playerDiscRadius", resolved, "the line starts at the disc edge")

        draw = self._draw_marks(code)
        drawn = code[draw[0] : draw[1]]
        self.assertRegex(drawn, r"\.move\s*\(\s*to:\s*\w+\.aimStart\s*\)")
        self.assertRegex(drawn, r"\.addLine\s*\(\s*to:\s*\w+\.aimEnd\s*\)")
        self.assertNotRegex(drawn, r"\.addLine\s*\(\s*to:\s*\w+\.landing\s*\)", "never through the square to its centre")
        self.assertNotRegex(drawn, r"\.move\s*\(\s*to:\s*\w+\.player\s*\)", "never from the disc centre")

        self._assert_native(sources, MARKS_TEST, (".aimStart", ".aimEnd"), pixels=False, assertions=10)
        self._assert_native(sources, BOX_TEST, ("aimStart", "aimEnd"), pixels=True, assertions=8)

    # G5 — red 100 / white 150 / blue 200 markers at S70 size with a dark outline

    def test_remaining_yard_markers_are_s70_sized(self) -> None:
        # G5: about 2.5× today's 2.1 pt radius, with a dark outline, from named constants.
        sources = self._sources()
        code, _ = sources.read(MAP_VIEW)

        layout = _required_body(code, r"\benum\s+WatchHoleMapReferenceLayout\b")
        radius = _static_number(code, layout, "remainingMarkerRadius")
        outline = _static_number(code, layout, "remainingMarkerOutlineWidth")
        self.assertTrue(4.75 <= radius <= 6.0, radius)
        self.assertTrue(1.0 <= outline <= 2.0, outline)
        self.assertRegex(code[layout[0] : layout[1]], r"\bremainingYards\s*=\s*\[\s*100\s*,\s*150\s*,\s*200\s*\]")

        facts = _required_body(code, r"\bfunc\s+drawReferenceFacts\b")
        drawn = code[facts[0] : facts[1]]
        self.assertIn("WatchHoleMapReferenceLayout.remainingMarkerRadius", drawn)
        self.assertIn("WatchHoleMapReferenceLayout.remainingMarkerOutlineWidth", drawn)
        self.assertNotRegex(drawn, r"(?<![\d.])2\.1(?!\d)", "no 2.1 pt marker left")
        self.assertRegex(drawn, r"\.black\b", "a dark outline")
        colours = _required_body(code, r"\bfunc\s+remainingMarkerColor\b")
        for yards in ("100", "150", "200"):
            self.assertRegex(code[colours[0] : colours[1]], rf"\bcase\s+{yards}\s*:")

        self._assert_native(
            sources,
            MARKERS_TEST,
            (
                "showReferenceMarkers: true",
                "showReferenceMarkers: false",
                "hazardRoute:",
                "WatchHoleMapReferenceLayout.remainingMarkers(",
                "remainingMarkerRadius",
                "canvasPoint(",
            ),
            pixels=True,
            assertions=4,
            forbidden=("fullMap: true",),
        )

    # G6 — the caddie entry is a compact chip: caddie figure + club, opening the caddie page

    def test_caddie_entry_is_a_compact_caddie_chip(self) -> None:
        # G6: a caddie figure and the club, no green pill, the same tap and identifier.
        sources = self._sources()
        code, text = sources.read(MAP_VIEW)

        identifiers = [m.start() for m in re.finditer(r'"watch-plan-club-tag"', text)]
        self.assertEqual(len(identifiers), 1, "one root caddie chip")
        block = _enclosing_block(code, identifiers[0], "showCaddieRecommendation")
        self.assertIsNotNone(block, "the chip is shown under the recommendation gate")
        chip_code = code[block[0] : block[1]]
        chip_text = text[block[0] : block[1]]
        self.assertIn('Image(systemName: "figure.golf")', chip_text, "a caddie figure")
        self.assertIn("WatchClubDisplay.shortCode(caddieClub)", chip_code, "the recommended club")
        self.assertGreaterEqual(len(re.findall(r"\bonOpenCaddie\s*\(\s*\)", chip_code)), 2, "tap and accessibility action")
        for green in (r"\bAICaddieDesignTokens\.hudGreen\b", r"\bcaddieGreen\b", r"\.green\b"):
            self.assertNotRegex(chip_code, green, "no green pill")
        self.assertRegex(chip_code, r"\brootCaddieChipFrame\s*\(\s*in:\s*size\s*\)", "drawn in the shared frame")

        container, _ = sources.read(CONTAINER)
        target = _required_body(container, r"\bvar\s+planTagTapTarget\b")
        self.assertRegex(
            container[target[0] : target[1]],
            r"\bWatchHoleMapView\.rootCaddieChipFrame\s*\(\s*in:",
            "the tap target above the pager follows the chip's frame",
        )

        body = self._assert_native(
            sources,
            CHIP_TEST,
            (
                "rootCaddieChipFrame(in:",
                "rootRailBottom(in:",
                "instrumentControlSize",
                "rootFactsFrame(in:",
                "WatchRootShotMarks.playerDiscRadius",
                "clockLane(in:",
                *FACES,
            ),
            pixels=True,
            assertions=8,
        )
        self.assertRegex(body, r"\bshowTextOverlay\s*:\s*true\b", "the chip is rendered")

    # G7 — the facts column, Touch Targeting, the caddie page, 999 and the fallback are unchanged

    def test_unchanged_layers_stay_as_they_are(self) -> None:
        # G7
        # pinned: F/M/B facts, Touch Targeting's two ranges, the caddie page, the 999 / waiting state
        # and the lightweight map facts are exactly as before this card.
        sources = self._sources()
        code, text = sources.read(MAP_VIEW)

        for pattern in (
            r"\bdistanceValue\s*\(\s*backGreen\s*\+\s*d\b",
            r"\bdistanceValue\s*\(\s*centerGreen\s*\+\s*d\b",
            r"\bdistanceValue\s*\(\s*frontGreen\s*\+\s*d\b",
        ):
            self.assertRegex(code, pattern, "the F/M/B facts column")
        draw_map = _required_body(code, r"\bfunc\s+drawMap\b")
        drawn = code[draw_map[0] : draw_map[1]]
        for pattern in (
            r"\bdrawLightweightMapFacts\s*\(",
            r"\bWatchTouchTargetDistanceLayout\.resolve\s*\(",
            r"\bplayerToTargetYards\b",
            r"\btargetToPinYards\b",
            r"\bdrawMeasurementRoute\s*\(",
        ):
            self.assertRegex(drawn, pattern)
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
        holemap = _required_body(container, r"\bfunc\s+holeMapView\b")
        root = _calls(container, "WatchHoleMapView", *holemap)
        self.assertEqual(len(root), 1)
        self.assertEqual(_value(container, root[0][1], "onOpenCaddie"), "{ model.openCaddie() }")
        self.assertEqual(_value(container, root[0][1], "interactionMode"), ".measure")
        self.assertEqual(_value(container, root[0][1], "fullMap"), "false")

        caddie, _ = sources.read(CADDIE_VIEW)
        option_map = _required_body(caddie, r"\bfunc\s+optionMap\b")
        maps = _calls(caddie, "WatchHoleMapView", *option_map)
        self.assertEqual(len(maps), 1)
        self.assertEqual(_value(caddie, maps[0][1], "planLegs"), "legs")
        self.assertEqual(_value(caddie, maps[0][1], "fullMap"), "true")
        self.assertRegex(caddie, r"\.digitalCrownRotation\s*\(")
        self.assertRegex(caddie, r"\bstatic\s+func\s+clubChain\b")

    # G8 — README and snapshots show the S70 root for review

    def test_readme_and_snapshots_show_the_s70_root(self) -> None:
        # G8: README §3 item 1 describes the S70 marks; the review snapshots render them.
        sources = self._sources()
        readme = sources.read_raw(README)

        section = re.search(r"^## 3\..*?(?=^## )", readme, re.M | re.S)
        self.assertIsNotNone(section, "README §3 (手表) is missing")
        item = re.search(r"^[ \t]*1\.[ \t].*?(?=^[ \t]*2\.[ \t])", section.group(0), re.M | re.S)
        self.assertIsNotNone(item, "README §3 本洞 list item 1 is missing")
        text = item.group(0)
        for required in ("黄色圆盘", "黑色箭头", "方框", "宽度等于深度", "没有横向散布数据", "弧线", "球童图标", "不画方框"):
            self.assertIn(required, text)
        self.assertRegex(text, r"100\s*/\s*150\s*/\s*200")
        for kept in ("D02", "瞄准线", "球童页", "不画"):
            self.assertIn(kept, text, "#434's D02 wording stays")
        for superseded in ("点绿色球杆签", "地图画 AI 球童路线", "点它换方案"):
            self.assertNotIn(superseded, text)

        code, snapshot_text = sources.read(SNAPSHOT_TESTS)
        functions = _test_functions(code)
        self.assertGreater(len(functions), 5, "the snapshot test functions are discovered")

        def rendering(name: str) -> list[tuple[int, int]]:
            return [span for _, span in functions if f'"{name}"' in snapshot_text[span[0] : span[1]]]

        for name, extra in (
            ("watch-hole-root-aim-line", {}),
            ("watch-hole-page-plan", {"showPreparedPlan": "true"}),
        ):
            spans = rendering(name)
            self.assertEqual(len(spans), 1, f"one test renders {name}")
            calls = _calls(code, "WatchHoleMapView", *spans[0])
            self.assertTrue(
                any(
                    _value(code, args, "playerMarker") == ".chevron"
                    and _value(code, args, "showReferenceMarkers") == "true"
                    and _value(code, args, "hazardRoute") not in (None, "[]")
                    and _value(code, args, "restingPlayerAnchorFraction") == "nil"
                    and _value(code, args, "showCaddieRecommendation") == "true"
                    and _value(code, args, "fullMap") in (None, "false")
                    and all(_value(code, args, k) == v for k, v in extra.items())
                    for _, args in calls
                ),
                f"{name} renders the production root: the disc, the markers and the marks",
            )
        self.assertEqual(len(rendering("watch-container-root-aim-line")), 1)


if __name__ == "__main__":
    unittest.main()
