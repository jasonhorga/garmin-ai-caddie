"""Requirement -> test traceability (docs/test-plan.md sections 2 and 9).

The goals are the ``S-xx``/``I-xx``/``W-xx`` rows of the section 2 tables. Tests
name the goals they cover (section 9.1):

* Python, in ``tests/small|medium|large``: the first docstring line starts with
  the IDs, ``S-11 S-27 [main]: ...``. IDs on a class docstring apply to every
  ``test*`` method of the class.
* Swift, in test targets (a ``*Tests*`` directory under ``mobile/ios``): a
  ``// goals: I-10 W-08 [main]`` comment, normally on the line above the test.

``check`` turns goals + tagged tests + the allowed-missing list into problems,
each listing the IDs involved. ``card_named_python``/``card_named_swift`` and
``source_reads`` flag test files named after card numbers and test code that
reads product source text.
Only test files are read here; product source never is.
"""
import ast
from dataclasses import dataclass
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs" / "test-plan.md"
ALLOWED_MISSING_FILE = Path(__file__).resolve().parent / "traceability_allowed_missing.txt"
COUNTED_LAYERS = ("small", "medium", "large")
QUARANTINE = "quarantine"
SWIFT_ROOT = ROOT / "mobile" / "ios"

META = "META"  # tests of the test infrastructure itself; not a product goal
MAIN = "[main]"
D3_MIN_TESTS = 4

ID_TOKEN = r"(?:[A-Z]+-\d+|META|\[main\])"
DOCSTRING_TAGS = re.compile(rf"^\s*({ID_TOKEN}(?:[\s,]+{ID_TOKEN})*)\s*:")
SWIFT_TAGS = re.compile(r"^\s*//\s*goals:\s*(.*)$")
SWIFT_TEST = re.compile(r"\bfunc\s+(test\w*)")
ID = re.compile(r"[A-Z]+-\d+")
GOAL_ROW = re.compile(r"^\|\s*([SIW]-\d+)\s*\|")
SUMMARY_ROW = re.compile(r"^\|[^|]*\s([SIW])\s*\|\s*(\d+)\s*\|")
DEPTH = re.compile(r"^D[123]$")
CARD_NAMED_PY = re.compile(r"^test_c\d+", re.IGNORECASE)
CARD_NAMED_SWIFT = re.compile(r"^(?:test_?)?c\d+", re.IGNORECASE)

SOURCE_DIRS = frozenset({"server_v2", "ai_caddie", "mobile"})
# Reading data that lives under a source directory (JSON fixtures, images) is
# not reading source text; an expression naming such a file is allowed.
DATA_SUFFIXES = (".json", ".geojson", ".csv", ".png", ".jpg", ".jpeg", ".pdf", ".gpx", ".fit")
READ_METHODS = frozenset({"read_text", "read_bytes", "open"})
SOURCE_INSPECTION = frozenset({"getsource", "getsourcelines"})


@dataclass(frozen=True)
class TaggedTest:
    label: str
    ids: frozenset
    main: bool


def plan_sections(plan_text):
    """Split the plan into ``{section number: text}`` at its ``## N.`` headings."""
    sections, number, lines = {}, None, []
    for line in plan_text.splitlines():
        heading = re.match(r"^## (\d+)\.", line)
        if heading:
            if number is not None:
                sections[number] = "\n".join(lines)
            number, lines = int(heading.group(1)), []
        elif number is not None:
            lines.append(line)
    if number is not None:
        sections[number] = "\n".join(lines)
    return sections


def parse_goals(plan_text):
    """``{goal ID: depth}`` from the section 2 tables; malformed rows raise ValueError."""
    goals = {}
    for line in plan_sections(plan_text).get(2, "").splitlines():
        if not GOAL_ROW.match(line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        goal, depth = cells[0], cells[4] if len(cells) > 4 else ""
        if not DEPTH.match(depth):
            raise ValueError(f"test-plan section 2 row {goal} has no D1/D2/D3 depth: {depth!r}")
        if goal in goals:
            raise ValueError(f"test-plan section 2 lists {goal} twice")
        goals[goal] = depth
    return goals


def summary_counts(plan_text):
    """``{"S": 31, ...}`` from the section 2.4 summary table."""
    return {match.group(1): int(match.group(2))
            for match in map(SUMMARY_ROW.match, plan_sections(plan_text).get(2, "").splitlines())
            if match}


def _tags(text):
    tokens = re.split(r"[\s,]+", text.strip())
    return frozenset(token for token in tokens if token and token != MAIN), MAIN in tokens


def docstring_tags(docstring):
    """IDs and the ``[main]`` flag from a docstring's first line; empty when untagged."""
    first_line = (docstring or "").strip().splitlines()[0] if (docstring or "").strip() else ""
    match = DOCSTRING_TAGS.match(first_line)
    return _tags(match.group(1)) if match else (frozenset(), False)


def python_tests(label, source):
    """Tagged ``test*`` methods of the module's classes."""
    return _python_tests(label, ast.parse(source))


def _python_tests(label, tree):
    tests = []

    def visit(node, prefix, inherited_ids, inherited_main):
        class_ids, class_main = docstring_tags(ast.get_docstring(node))
        ids, main = inherited_ids | class_ids, inherited_main or class_main
        for child in node.body:
            name = f"{prefix}::{node.name}"
            if isinstance(child, ast.ClassDef):
                visit(child, name, ids, main)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test"):
                own_ids, own_main = docstring_tags(ast.get_docstring(child))
                if ids or own_ids:
                    tests.append(TaggedTest(f"{name}::{child.name}", ids | own_ids, main or own_main))

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            visit(node, label, frozenset(), False)
    return tests


def swift_tests(label, text):
    """One tagged test per ``// goals:`` comment, named after the next ``func test*``."""
    tests, lines = [], text.splitlines()
    for number, line in enumerate(lines, 1):
        match = SWIFT_TAGS.match(line)
        if not match:
            continue
        name = next((test.group(1) for test in map(SWIFT_TEST.search, lines[number:number + 5]) if test),
                    f"line {number}")
        ids, main = _tags(match.group(1))
        tests.append(TaggedTest(f"{label}::{name}", ids, main))
    return tests


def check(goals, tests, allowed_missing, quarantined=()):
    """Problems as ``{kind: sorted IDs or labels}``; an empty dict means traceable.

    ``quarantined`` are tests under ``tests/quarantine``: they never count as
    coverage, but a goal whose main test sits there is reported (``quarantined``)
    instead of failing, so moving an unstable test out of the gates stays possible
    (test-plan section 5) without growing the allowed-missing list.
    """
    by_goal = {goal: [] for goal in goals}
    unknown = set()
    for test in tests:
        for goal in test.ids:
            if goal in by_goal:
                by_goal[goal].append(test)
            elif goal != META:
                unknown.add(f"{goal} ({test.label})")
    quarantined_mains = {goal for test in quarantined if test.main for goal in test.ids}
    problems = {
        "unknown": unknown,
        "allowed_unknown": set(allowed_missing) - set(goals),
        "missing": set(), "no_main": set(), "multiple_main": set(), "shallow": set(),
        "allowed_but_covered": set(), "quarantined": set(),
    }
    for goal, covering in by_goal.items():
        mains = sum(test.main for test in covering)
        if goal in allowed_missing:
            if mains:
                problems["allowed_but_covered"].add(goal)
        elif not mains and goal in quarantined_mains:
            problems["quarantined"].add(goal)
        elif not covering:
            problems["missing"].add(goal)
        elif not mains:
            problems["no_main"].add(goal)
        elif goals[goal] == "D3" and len(covering) < D3_MIN_TESTS:
            problems["shallow"].add(goal)
        if mains > 1:
            problems["multiple_main"].add(goal)
    return {kind: sorted(found) for kind, found in problems.items() if found}


def parse_allowed_missing(text):
    """IDs listed in the allowed-missing file; ``#`` starts a comment."""
    return frozenset(token for line in text.splitlines()
                     for token in line.split("#", 1)[0].split())


def added_allowances(base_text, current_text):
    """Entries the current allowed-missing file has that the base did not; the list only shrinks."""
    return sorted(parse_allowed_missing(current_text) - parse_allowed_missing(base_text))


class _SourceReads:
    """Calls that read a file under a product source directory.

    A path expression points at source when it contains a string naming a
    source directory (``"server_v2"``, ``"mobile/ios"``) or a name assigned from
    such an expression, and no string naming a data file (``*.json``).
    ``inspect.getsource`` is always flagged.

    Each expression is walked once; the taint fixpoint then only compares name
    sets, so a large test file costs one pass over its tree.
    """

    def __init__(self, tree):
        self.tainted, self.found, self._facts = set(), [], {}
        nodes = list(ast.walk(tree))
        assignments = [(_names(target), value) for node in nodes for target, value in _bindings(node)]
        changed = True
        while changed:
            changed = False
            for names, value in assignments:
                if not self.tainted.issuperset(names) and self.points_at_source(value):
                    self.tainted.update(names)
                    changed = True
        for node in nodes:
            if isinstance(node, ast.Call):
                self.check_call(node)

    def points_at_source(self, node):
        facts = self._facts.get(id(node))
        if facts is None:
            constants, names = [], set()
            for child in ast.walk(node):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    constants.append(child.value)
                elif isinstance(child, ast.Name):
                    names.add(child.id)
            facts = self._facts[id(node)] = (
                any(value.lower().endswith(DATA_SUFFIXES) for value in constants),
                any(SOURCE_DIRS & set(value.replace("\\", "/").split("/")) for value in constants),
                names)
        data, source, names = facts
        return not data and (source or not self.tainted.isdisjoint(names))

    def check_call(self, node):
        function = node.func
        name = function.attr if isinstance(function, ast.Attribute) else getattr(function, "id", None)
        if name in SOURCE_INSPECTION:
            self.found.append((node.lineno, name))
        elif isinstance(function, ast.Attribute) and name in READ_METHODS and (
                self.points_at_source(function.value) or (node.args and self.points_at_source(node.args[0]))):
            self.found.append((node.lineno, name))
        elif isinstance(function, ast.Name) and name == "open" and node.args and self.points_at_source(node.args[0]):
            self.found.append((node.lineno, name))


def _bindings(node):
    if isinstance(node, ast.Assign):
        return [(target, node.value) for target in node.targets]
    if isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and node.value is not None:
        return [(node.target, node.value)]
    if isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
        return [(node.target, node.iter)]
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return [(item.optional_vars, item.context_expr) for item in node.items if item.optional_vars]
    return []


def _names(target):
    return [child.id for child in ast.walk(target) if isinstance(child, ast.Name)]


def source_reads(label, source):
    """``"<label>:<line> <call>"`` for each read of product source text."""
    return _source_reads(label, ast.parse(source))


def _source_reads(label, tree):
    visitor = _SourceReads(tree)
    return [f"{label}:{line} {call}" for line, call in sorted(visitor.found)]


def card_named_python(name):
    return bool(CARD_NAMED_PY.match(name))


def card_named_swift(name):
    return bool(CARD_NAMED_SWIFT.match(name))


@dataclass
class Repository:
    goals: dict
    summary: dict
    tests: list
    quarantined: list
    allowed_missing: frozenset
    card_named: list
    source_reads: list


def _relative(path, root):
    return path.relative_to(root).as_posix()


def _python_files(root, layer):
    return sorted((root / "tests" / layer).rglob("*.py"))


def _swift_test_files(root):
    swift_root = root / SWIFT_ROOT.relative_to(ROOT)
    return sorted(path for path in swift_root.rglob("*.swift")
                  if any("Tests" in part for part in path.relative_to(swift_root).parts[:-1]))


def scan(root=ROOT):
    """Read the plan, the allowed-missing list and every test file once."""
    plan_text = (root / PLAN.relative_to(ROOT)).read_text(encoding="utf-8")
    allowed_text = (root / ALLOWED_MISSING_FILE.relative_to(ROOT)).read_text(encoding="utf-8")
    tests, quarantined, card_named, reads = [], [], [], []
    for layer in COUNTED_LAYERS + (QUARANTINE,):
        for path in _python_files(root, layer):
            label, tree = _relative(path, root), ast.parse(path.read_text(encoding="utf-8"))
            (quarantined if layer == QUARANTINE else tests).extend(_python_tests(label, tree))
            reads.extend(_source_reads(label, tree))
            if card_named_python(path.name):
                card_named.append(label)
    for path in _swift_test_files(root):
        label = _relative(path, root)
        found = swift_tests(label, path.read_text(encoding="utf-8"))
        tests.extend(found)
        # Legacy Swift tests named after cards stay until their migration; a
        # file that carries goal tags is a new test and must not be.
        if found and card_named_swift(path.name):
            card_named.append(label)
    return Repository(parse_goals(plan_text), summary_counts(plan_text), tests, quarantined,
                      parse_allowed_missing(allowed_text), card_named, reads)
