"""META: the traceability rules on in-memory plans and tests (test-plan section 9.2).

The run over the real repository reads every test file, so it is a medium test:
tests/medium/test_traceability_repository.py.
"""
from tests.support import traceability as trace
from tests.support.hermetic import SmallTestCase

PLAN = """\
## 2. Goals

| ID | Goal | Spec | Risk | Depth | Entry |
|---|---|---|---|---|---|
| S-01 | sign in | J7.2 | high | D3 | `auth` |
| S-02 | bag | J4.1 | medium | D2 | `bag` |
| W-01 | watch | J5.1 | low | D1 | `watch` |

| Layer | Goals | High | Medium | Low |
|---|---|---|---|---|
| Server S | 2 | 1 | 1 | 0 |
| Watch W | 1 | 0 | 0 | 1 |

## 9. Matrix

| S-99 | a matrix row outside section 2 is not a goal | x | x | D1 | x |
"""
GOALS = {"S-01": "D3", "S-02": "D2", "W-01": "D1"}

COVERED = '''
class SignIn:
    """S-01: sign-in sessions."""

    def test_sign_in(self):
        """S-01 [main]: a session is issued, refreshed and revoked."""

    def test_expired(self):
        """An expired session is rejected."""

    def test_wrong_audience(self):
        """S-01, S-02: a token for another app is rejected."""

    def test_replay(self):
        """S-01: a replayed token is rejected."""

    def helper(self):
        """S-02 [main]: not a test method, never counted."""


class Bag:
    def test_bag(self):
        """S-02 [main]: the bag lists the player's clubs."""

    def test_untagged(self):
        """Plain docstrings are allowed; they cover nothing."""
'''
WATCH = """
final class WatchTests: XCTestCase {
    // goals: W-01 [main]
    @MainActor
    func testQueueSurvivesRelaunch() async throws {}
}
"""


def tests_of(source, label="tests/medium/test_s_auth.py"):
    return trace.python_tests(label, source)


def covered():
    return tests_of(COVERED) + trace.swift_tests("WatchTests.swift", WATCH)


class PlanParsingTests(SmallTestCase):
    """META: goals and depths are read from test-plan section 2."""

    def test_goals_come_from_the_section_two_tables_with_their_depth(self):
        """Only section 2 rows are goals; rows elsewhere in the plan are not."""
        self.assertEqual(trace.parse_goals(PLAN), GOALS)
        self.assertEqual(trace.summary_counts(PLAN), {"S": 2, "W": 1})

    def test_a_goal_row_without_a_depth_is_rejected(self):
        """A section 2 row whose depth cell is not D1-D3 stops the check instead of being skipped."""
        with self.assertRaisesRegex(ValueError, "S-02"):
            trace.parse_goals(PLAN.replace("| D2 |", "| high |"))


class TagParsingTests(SmallTestCase):
    """META: goal tags are read from Python docstrings and Swift comments."""

    def test_python_tags_merge_class_and_method_docstrings(self):
        """Class IDs apply to every test method; untagged and non-test methods add nothing."""
        found = {test.label.rsplit("::", 1)[1]: (set(test.ids), test.main) for test in tests_of(COVERED)}
        self.assertEqual(found, {
            "test_sign_in": ({"S-01"}, True),
            "test_expired": ({"S-01"}, False),
            "test_wrong_audience": ({"S-01", "S-02"}, False),
            "test_replay": ({"S-01"}, False),
            "test_bag": ({"S-02"}, True),
        })

    def test_only_a_leading_id_list_counts_as_tags(self):
        """IDs mentioned inside the sentence, or without the colon, are not tags."""
        self.assertEqual(trace.docstring_tags("Mirrors S-01: not a tag"), (frozenset(), False))
        self.assertEqual(trace.docstring_tags("S-01 [main] no colon"), (frozenset(), False))
        self.assertEqual(trace.docstring_tags("META: infrastructure"), (frozenset({"META"}), False))
        self.assertEqual(trace.docstring_tags("\n  I-10 W-08 [main]: x\n second"),
                         (frozenset({"I-10", "W-08"}), True))

    def test_swift_goal_comments_name_the_following_test(self):
        """A `// goals:` comment tags the next test function of the file."""
        self.assertEqual(trace.swift_tests("AICaddieWatchTests/QueueTests.swift", WATCH), [
            trace.TaggedTest("AICaddieWatchTests/QueueTests.swift::testQueueSurvivesRelaunch",
                             frozenset({"W-01"}), True),
        ])


class CoverageRuleTests(SmallTestCase):
    """META: goals need tests, one main test, and four tests at D3."""

    def test_fully_covered_goals_pass(self):
        """Each goal with one main test (and four tests for D3) leaves nothing to report."""
        self.assertEqual(trace.check(GOALS, covered(), frozenset()), {})

    def test_missing_unknown_and_mainless_goals_are_listed_by_id(self):
        """A goal without tests, one without a main test and an unknown ID are each reported."""
        tests = tests_of(COVERED.replace("S-02 [main]: the bag", "S-02: the bag")
                         .replace('"""S-01, S-02:', '"""S-01, S-2:'))
        self.assertEqual(trace.check(GOALS, tests, frozenset()), {
            "missing": ["W-01"],
            "no_main": ["S-02"],
            "unknown": ["S-2 (tests/medium/test_s_auth.py::SignIn::test_wrong_audience)"],
        })

    def test_a_second_main_test_is_rejected(self):
        """Exactly one main test per goal: a second one is reported."""
        tests = covered() + tests_of('class Again:\n    def test_x(self):\n        """S-02 [main]: x"""\n')
        self.assertEqual(trace.check(GOALS, tests, frozenset()), {"multiple_main": ["S-02"]})

    def test_a_d3_goal_needs_four_tests(self):
        """A D3 goal with a main test but fewer than four tests is too shallow."""
        tests = [test for test in covered() if not test.label.endswith("test_replay")]
        self.assertEqual(trace.check(GOALS, tests, frozenset()), {"shallow": ["S-01"]})

    def test_quarantined_tests_do_not_count_but_keep_the_gate_open(self):
        """A goal whose only main test is quarantined is reported as quarantined, not covered."""
        quarantined = trace.swift_tests("WatchTests.swift", WATCH)
        self.assertEqual(trace.check(GOALS, tests_of(COVERED), frozenset(), quarantined),
                         {"quarantined": ["W-01"]})
        self.assertEqual(trace.check(GOALS, tests_of(COVERED), frozenset(), tests_of(COVERED)),
                         {"missing": ["W-01"]})


class AllowedMissingTests(SmallTestCase):
    """META: unfinished goals pass through the allowed-missing list."""

    def test_allowed_goals_may_be_unfinished(self):
        """Listed goals pass with no tests or without a main test yet."""
        tests = tests_of(COVERED.replace("S-02 [main]: the bag", "S-02: the bag"))
        self.assertEqual(trace.check(GOALS, tests, frozenset({"S-02", "W-01"})), {})

    def test_a_listed_goal_that_gained_a_main_test_must_leave_the_list(self):
        """Once a goal has its main test the entry is stale and must be deleted."""
        self.assertEqual(trace.check(GOALS, tests_of(COVERED), frozenset({"S-02", "W-01"})),
                         {"allowed_but_covered": ["S-02"]})

    def test_the_list_names_only_goals(self):
        """An entry that is not a section 2 goal is reported."""
        self.assertEqual(trace.check(GOALS, covered(), frozenset({"S-03"})),
                         {"allowed_unknown": ["S-03"]})

    def test_the_list_file_ignores_comments(self):
        """IDs are whitespace separated; `#` starts a comment."""
        self.assertEqual(trace.parse_allowed_missing("# S-09 header\nS-01 S-02  # W-02\n\nW-01\n"),
                         frozenset({"S-01", "S-02", "W-01"}))

    def test_the_list_may_only_shrink(self):
        """Entries added since the base revision are reported; removed ones are fine."""
        self.assertEqual(trace.added_allowances("S-01 S-02\n", "S-02 W-01 # S-09\n"), ["W-01"])
        self.assertEqual(trace.added_allowances("S-01 S-02\n", "S-02\n"), [])


class HygieneRuleTests(SmallTestCase):
    """META: no card-named test files, no reading of product source."""

    def test_test_files_named_after_cards_are_rejected(self):
        """test_c123*.py is a card name, not a goal; the same goes for tagged Swift files."""
        self.assertTrue(trace.card_named_python("test_c391_traceability.py"))
        self.assertTrue(trace.card_named_python("TEST_C9.py"))
        self.assertFalse(trace.card_named_python("test_course_search.py"))
        self.assertTrue(trace.card_named_swift("C89HoleMapFrameTests.swift"))
        self.assertTrue(trace.card_named_swift("testC85Queue.swift"))
        self.assertFalse(trace.card_named_swift("ClubBagTests.swift"))

    def test_reading_product_source_text_is_rejected(self):
        """read_text/read_bytes/open on server_v2, ai_caddie or mobile sources and getsource are flagged."""
        source = '\n'.join([
            'ROOT = Path(__file__).parents[2]',
            'MAIN = ROOT / "server_v2" / "main.py"',
            'MAIN.read_text()',
            '(ROOT / "ai_caddie").joinpath("caddie.py").read_bytes()',
            'open("mobile/ios/AICaddie/AICaddieApp.swift")',
            'with open(ROOT / "server_v2/auth_api.py") as handle: pass',
            'for path in (ROOT / "mobile").rglob("*.swift"): path.read_text()',
            'inspect.getsource(module)',
        ])
        self.assertEqual(trace.source_reads("tests/medium/test_s_x.py", source), [
            "tests/medium/test_s_x.py:3 read_text",
            "tests/medium/test_s_x.py:4 read_bytes",
            "tests/medium/test_s_x.py:5 open",
            "tests/medium/test_s_x.py:6 open",
            "tests/medium/test_s_x.py:7 read_text",
            "tests/medium/test_s_x.py:8 getsource",
        ])

    def test_reading_fixtures_and_test_data_is_allowed(self):
        """JSON fixtures (even under mobile/) and files outside product source stay readable."""
        source = '\n'.join([
            'SHARED = ROOT / "contracts" / "fixtures" / "shared"',
            '(SHARED / "round.json").read_text()',
            '(ROOT / "mobile" / "ios" / "Fixtures" / "round.json").read_bytes()',
            'for path in (ROOT / "mobile").rglob("*.json"): path.read_text()',
            'open(os.environ["TMPDIR"] + "/out.log")',
        ])
        self.assertEqual(trace.source_reads("tests/medium/test_s_x.py", source), [])

