"""Card #440: agenthub native mutant workflow — Swift mutants judged by the real native tests.

agenthub dispatches `.github/workflows/agenthub-native-mutant.yml` once per mutant with a request id,
the head SHA under test and the mutant patch (base64; empty for a baseline run). The workflow tests
that head plus patch with the `AICaddie` and `AICaddieWatch` schemes and uploads `result.json` as
the artifact `agenthub-native-result`, written by `.github/scripts/agenthub_native_result.py` from the
xcresulttool test trees. agenthub counts a mutant as caught when a native test fails: `result.json`
is the verdict, not the job colour.

Linux CI has no Xcode. These tests read the workflow and then replay its job offline (`_Replay`):
- steps run in order under GitHub's rules: `if:` with status functions, `continue-on-error`, step
  outcomes, `$GITHUB_ENV` / `$GITHUB_OUTPUT`, and `${{ }}` in `env:` / `with:` values (the subset
  listed in `.agent/contracts/card-440.md`, "Replay rules");
- `run:` steps run in real bash with real git, base64 and python3, so the real result writer runs;
- `actions/checkout` is a clone of a throwaway origin: the head under test (without the workflow and
  the writer, like #434's head), the dispatched `main` commit (`github.sha`, with both) and a later
  `main` commit whose writer only fails, as when `main` moves on after the dispatch;
- `actions/upload-artifact` records the artifact name and the files it would upload;
- `xcrun`, `xcodebuild`, `xcodegen` and `brew` are fakes. They serve a sample simulator list and
  sample xcresulttool trees, and record how they were called. Like the real runner image, the fake
  `xcodegen` is missing until `brew install xcodegen` has run;
- a run can be cancelled while a scheme tests, or right after the writer: from then on `cancelled()`
  is true and `success()` false, as on GitHub.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "agenthub-native-mutant.yml"
WRITER = REPO_ROOT / ".github" / "scripts" / "agenthub_native_result.py"
NATIVE_MOBILE = REPO_ROOT / ".github" / "workflows" / "native-mobile.yml"
REPOSITORY = "jasonhorga/garmin-ai-caddie"
RUN_NAME = "agenthub-native ${{ inputs.request_id }}"
ARTIFACT = "agenthub-native-result"
PROJECT = "mobile/ios/AICaddieNative.xcodeproj"
XCODEGEN_ARGS = ["generate", "--spec", "mobile/ios/project.yml", "--project-root", "."]
MARKER = "mobile/ios/AICaddie/AgenthubMarker.swift"
HEAD_MARKER = 'let agenthubMarker = "head"'
MAIN_MARKER = 'let agenthubMarker = "main"'
MUTANT_MARKER = 'let agenthubMarker = "mutant"'
CONTEXT = "mobile/ios/AICaddie/AgenthubContext.swift"
CONTEXT_LINES = ("let agenthubFirst = 1", "let agenthubSecond = 2", "let agenthubThird = 3")
SPEC = "mobile/ios/project.yml"
SPEC_TEXT = "name: AICaddieNative"
BROKEN_SPEC = "card440-broken-spec"
STATUSES = {"passed", "failed", "skipped"}
STATUS_FUNCTIONS = re.compile(r"\b(?:success|failure|always|cancelled)\(\s*\)")
BASH = shutil.which("bash") or "/bin/bash"


def _diff(path: str, hunk: str, *lines: str) -> str:
    # G2 G3: a unified diff of one file, as agenthub would send for a mutant.
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n{hunk}\n" + "".join(f"{line}\n" for line in lines)


def _patch(old: str, new: str) -> str:
    # G2 G3: a one-line mutant of the marker file.
    return _diff(MARKER, "@@ -1 +1 @@", f"-{old}", f"+{new}")


def _b64(text: str) -> str:
    # G1 G3: the patch input is base64.
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


@contextmanager
def _case(name: str):
    # G1 G2 G3 G4: labels one case of a multi-case test. Unlike subTest, a failing case fails the test
    # function itself, so the gate credits it on the base branch and for every mutant.
    try:
        yield
    except AssertionError as exc:
        raise AssertionError(f"[{name}] {exc}") from exc


MUTANT_PATCH = _b64(_patch(HEAD_MARKER, MUTANT_MARKER))
# A mutant whose added line ends in a space. `git apply` applies it as it is; `--whitespace=error`
# refuses it and `--whitespace=fix` strips the space.
TRAILING_SPACE_MARKER = MUTANT_MARKER + " "
TRAILING_SPACE_PATCH = _b64(_patch(HEAD_MARKER, TRAILING_SPACE_MARKER))
STALE_PATCH = _b64(_patch('let agenthubMarker = "elsewhere"', MUTANT_MARKER))
# The hunk header counts two lines where the hunk has one. `git apply` refuses it; `--recount` would
# apply it.
WRONG_COUNT_PATCH = _b64(_diff(MARKER, "@@ -1,2 +1,2 @@", f"-{HEAD_MARKER}", f"+{MUTANT_MARKER}"))
# Valid base64 of the mutant with one character outside the base64 alphabet. A lenient decoder
# (`b64decode` without `validate=True`, `base64 --ignore-garbage`) drops it and applies the mutant.
STRAY_CHARACTER_PATCH = MUTANT_PATCH[:8] + "*" + MUTANT_PATCH[8:]
# The changed line matches the head; the lines around it do not. `git apply` refuses it; `patch` with
# fuzz, or `git apply -C0`, would apply it.
STALE_CONTEXT_PATCH = _b64(
    _diff(
        CONTEXT,
        "@@ -1,3 +1,3 @@",
        " let agenthubFirst = 10",
        f"-{CONTEXT_LINES[1]}",
        "+let agenthubSecond = 20",
        " let agenthubThird = 30",
    )
)
# The context matches the head except for a trailing space. `git apply` refuses it; `--whitespace=fix`,
# `--ignore-whitespace` or `--ignore-space-change` would apply it.
WHITESPACE_CONTEXT_PATCH = _b64(
    _diff(
        CONTEXT,
        "@@ -1,3 +1,3 @@",
        f" {CONTEXT_LINES[0]} ",
        f"-{CONTEXT_LINES[1]}",
        "+let agenthubSecond = 20",
        f" {CONTEXT_LINES[2]}",
    )
)
# Applies cleanly, but the patched project spec does not generate: a build failure of the mutant.
BROKEN_SPEC_PATCH = _b64(_diff(SPEC, "@@ -1 +1 @@", f"-{SPEC_TEXT}", f"+{SPEC_TEXT} # {BROKEN_SPEC}"))
# A mutant that also adds a writer to the head under test, one that only fails. The verdict must still
# come from the workflow's own writer.
HEAD_WRITER = ".github/scripts/agenthub_native_result.py"
HEAD_WRITER_PATCH = _b64(
    _patch(HEAD_MARKER, MUTANT_MARKER)
    + f"diff --git a/{HEAD_WRITER} b/{HEAD_WRITER}\nnew file mode 100644\n--- /dev/null\n+++ b/{HEAD_WRITER}\n"
    + "@@ -0,0 +1 @@\n"
    + '+raise SystemExit("card #440: this writer comes from the head under test and must not run")\n'
)
# The writer of a `main` commit made after the dispatch. The workflow runs the dispatched revision's
# writer (`github.sha`), not the branch tip's.
LATER_WRITER = 'raise SystemExit("card #440: this writer comes from a later main commit and must not run")\n'

# Simulators. The expected ones are the iPhone 16 and the Apple Watch Series 10 (46mm) on the newest
# runtime (numeric version order) that has them available. Runtime keys are deliberately unordered:
# the expected device is neither the first nor the last candidate of its platform, the newest
# runtimes (iOS 26.1, watchOS 26.0) have none available, and watchOS 11.10 sorts before 11.5 and
# 11.2 as text. Its UDID is neither the smallest nor the largest of its candidates. A similar name
# shares each expected device's runtime: `iPhone 16 Plus` after the iPhone 16 with a smaller UDID,
# `Series 10 (42mm)` before the Series 10 (46mm) with a larger one. A prefix or substring name match
# picks a wrong device whether ties go to the first, the last, the smallest or the largest UDID.
IOS_UDID = "6C2B1E8A-3F4D-4E5A-9B7C-1D2E3F4A5B01"
IOS_OLD = "6C2B1E8A-3F4D-4E5A-9B7C-1D2E3F4A5B02"
IOS_PLUS = "6C2B1E8A-3F4D-4E5A-9B7C-1D2E3F4A5AFF"
IOS_PRO = "6C2B1E8A-3F4D-4E5A-9B7C-1D2E3F4A5B04"
IOS_GONE = "6C2B1E8A-3F4D-4E5A-9B7C-1D2E3F4A5B05"
IOS_17 = "6C2B1E8A-3F4D-4E5A-9B7C-1D2E3F4A5B06"
IOS_OLDEST = "6C2B1E8A-3F4D-4E5A-9B7C-1D2E3F4A5B00"
WATCH_UDID = "8A7B6C5D-4E3F-4A2B-8C1D-0E9F8A7B6C01"
WATCH_OLD = "8A7B6C5D-4E3F-4A2B-8C1D-0E9F8A7B6C02"
WATCH_42 = "8A7B6C5D-4E3F-4A2B-8C1D-0E9F8A7B6C03"
WATCH_11 = "8A7B6C5D-4E3F-4A2B-8C1D-0E9F8A7B6C04"
WATCH_GONE = "8A7B6C5D-4E3F-4A2B-8C1D-0E9F8A7B6C05"
WATCH_EARLY = "8A7B6C5D-4E3F-4A2B-8C1D-0E9F8A7B6C00"
IPHONE = "iPhone 16"
WATCH = "Apple Watch Series 10 (46mm)"


def _sim(name: str, udid: str, available: bool = True) -> dict:
    # G2: one `simctl list devices -j` entry.
    return {"name": name, "udid": udid, "isAvailable": available, "state": "Shutdown"}


def _runtime(platform: str, major: int, minor: int) -> str:
    # G2: a CoreSimulator runtime identifier.
    return f"com.apple.CoreSimulator.SimRuntime.{platform}-{major}-{minor}"


DEVICES = {
    _runtime("iOS", 18, 6): [_sim(IPHONE, IOS_OLD), _sim("iPhone 16 Pro", IOS_PRO)],
    _runtime("watchOS", 11, 2): [_sim(WATCH, WATCH_EARLY)],
    _runtime("watchOS", 26, 0): [_sim("Apple Watch Series 11 (46mm)", WATCH_11), _sim(WATCH, WATCH_GONE, False)],
    _runtime("iOS", 26, 0): [_sim(IPHONE, IOS_UDID), _sim("iPhone 16 Plus", IOS_PLUS)],
    _runtime("watchOS", 11, 10): [_sim("Apple Watch Series 10 (42mm)", WATCH_42), _sim(WATCH, WATCH_UDID)],
    _runtime("iOS", 26, 1): [_sim(IPHONE, IOS_GONE, False), _sim("iPhone 17", IOS_17)],
    _runtime("watchOS", 11, 5): [_sim(WATCH, WATCH_OLD)],
    _runtime("iOS", 17, 5): [_sim(IPHONE, IOS_OLDEST)],
}


def _without_available(devices: dict, name: str) -> dict:
    # G2 G3: the sample simulator list without any available device called `name`; unavailable ones
    # and devices with similar names (iPhone 16 Plus, Series 10 (42mm)) stay.
    return {key: [d for d in value if not (d["name"] == name and d["isAvailable"])] for key, value in devices.items()}


# xcresulttool `get test-results tests` trees (Xcode 16 shape). A suite path `Outer/Inner` is a suite
# nested in another one, as Swift Testing reports it: its Test Case sits one level deeper.
IOS_CASES = (
    ("AICaddieDomainTests", "CanonicalJSONTests", "testNumberVectorsMatchRFC8785()"),
    ("AICaddieTests", "StartRoundDiscoveryTests", "testOpeningPageIsCourseUnlessACourseIsPassed()"),
    ("AICaddieTests", "StartRoundDiscoveryTests", "testPreselectedTeePrefersLastUsedThenCourseDefault()"),
    ("AICaddieTests", "StartRoundDiscoveryTests/NearbyDiscovery", "testNearbyDiscoveryWaitsForLocation()"),
    ("AICaddieTests", "DesignSnapshotTests", "testKnownRenderingIssueIsExpected()"),
)
WATCH_CASES = (
    ("AICaddieWatchTests", "WatchDesignSnapshotTests", "testTeeChoicesListTheDefaultTeeFirstAndHighlighted()"),
    ("AICaddieWatchTests", "WatchDesignSnapshotTests", "testTappingATeeStartsTheRoundWithThatTee()"),
    ("AICaddieWatchUITests", "WatchHolePagesUITests", "testVerticalSwipesWalkTheThreeHolePagesAndBack()"),
)
IOS_DEVICE = {"deviceId": IOS_UDID, "deviceName": IPHONE, "platform": "iOS Simulator", "osVersion": "26.0"}
WATCH_DEVICE = {"deviceId": WATCH_UDID, "deviceName": WATCH, "platform": "watchOS Simulator", "osVersion": "11.10"}


def _aggregate(results: list[str]) -> str:
    # G4: container result, as Xcode reports it.
    return "Failed" if any(result not in {"Passed", "Skipped", "Expected Failure"} for result in results) else "Passed"


def _suites(entries: list[tuple[list[str], dict]]) -> list[dict]:
    # G4: Test Suite nodes for (suite path, Test Case) pairs; `Outer/Inner` nests Inner inside Outer.
    groups: dict[str, list[tuple[list[str], dict]]] = {}
    for path, node in entries:
        groups.setdefault(path[0], []).append((path[1:], node))
    suites = []
    for name, members in groups.items():
        children = [node for rest, node in members if not rest]
        children += _suites([(rest, node) for rest, node in members if rest])
        suites.append(
            {
                "name": name,
                "nodeType": "Test Suite",
                "result": _aggregate([str(child.get("result")) for child in children]),
                "children": children,
            }
        )
    return suites


def _tree(plan: str, cases: tuple, results: tuple, device: dict) -> dict:
    # G4: an xcresulttool test tree; the first case carries Device / Test Case Run children that are
    # not tests themselves, failed cases carry a Failure Message.
    bundles: dict[str, list[tuple[list[str], dict]]] = {}
    for index, ((bundle, suite, name), result) in enumerate(zip(cases, results, strict=True)):
        node: dict = {"name": name, "nodeType": "Test Case", "nodeIdentifier": f"{suite}/{name}", "duration": "0,1s"}
        if result is not None:
            node["result"] = result
        if index == 0:
            node["children"] = [
                {
                    "name": device["deviceName"],
                    "nodeType": "Device",
                    "nodeIdentifier": device["deviceId"],
                    "result": result,
                    "children": [{"name": name, "nodeType": "Test Case Run", "result": result}],
                }
            ]
        elif result == "Failed":
            node["children"] = [
                {
                    "name": f"{suite.split('/')[-1]}.swift:42: XCTAssertEqual failed: (\"Blue\") is not equal to (\"Gold\")",
                    "nodeType": "Failure Message",
                    "result": "Failed",
                }
            ]
        bundles.setdefault(bundle, []).append((suite.split("/"), node))
    bundle_nodes = []
    for bundle, entries in bundles.items():
        suite_nodes = _suites(entries)
        bundle_nodes.append(
            {
                "name": bundle,
                "nodeType": "UI test bundle" if bundle.endswith("UITests") else "Unit test bundle",
                "result": _aggregate([node["result"] for node in suite_nodes]),
                "children": suite_nodes,
            }
        )
    return {
        "devices": [device],
        "testNodes": [
            {
                "name": plan,
                "nodeType": "Test Plan",
                "result": _aggregate([node["result"] for node in bundle_nodes]),
                "children": bundle_nodes,
            }
        ],
        "testPlanConfigurations": [{"configurationId": "1", "configurationName": "Test Scheme Action"}],
    }


def _without_identifier(tree: dict, name: str, *, nameless: bool = False) -> dict:
    # G4: a copy of `tree` whose Test Case `name` has no nodeIdentifier; its id falls back to
    # `<bundle>/<nearest suite>/<name>`. In a flat suite that is the same id as with the identifier.
    # `nameless` also drops the name, so no id can be formed at all.
    copy = json.loads(json.dumps(tree))
    stack = list(copy["testNodes"])
    found = 0
    while stack:
        node = stack.pop()
        if node.get("nodeType") == "Test Case" and node.get("name") == name:
            node.pop("nodeIdentifier", None)
            if nameless:
                node.pop("name")
            found += 1
        stack.extend(node.get("children", []))
    if found != 1:
        raise AssertionError(f"card #440 sample tree: expected one Test Case {name!r}, found {found}")
    return copy


def _nested_bundle(tree: dict, inner: str, outer: str) -> dict:
    # G4: a copy of `tree` whose bundle `inner` sits inside the bundle `outer`. Real output does not nest
    # bundles, but the contract names the nearest one, so `inner`'s tests keep `inner` as their bundle.
    copy = json.loads(json.dumps(tree))
    plan = copy["testNodes"][0]
    bundles = {node["name"]: node for node in plan["children"]}
    plan["children"] = [node for node in plan["children"] if node["name"] != inner]
    bundles[outer]["children"].append(bundles[inner])
    return copy


def _expected(cases: tuple, statuses: tuple) -> dict[str, str]:
    # G4: result.json test ids are `<bundle>/<nodeIdentifier>`.
    return {f"{bundle}/{suite}/{name}": status for (bundle, suite, name), status in zip(cases, statuses, strict=True)}


IOS_PASSING = _tree("AICaddie", IOS_CASES, ("Passed",) * 5, IOS_DEVICE)
WATCH_PASSING = _tree("AICaddieWatch", WATCH_CASES, ("Passed",) * 3, WATCH_DEVICE)
# The nested iOS case has no nodeIdentifier here: its id falls back to the nearest suite, NearbyDiscovery.
IOS_MUTANT = _without_identifier(
    _tree("AICaddie", IOS_CASES, ("Passed", "Passed", "Failed", "Skipped", "Expected Failure"), IOS_DEVICE),
    IOS_CASES[3][2],
)
# The Watch UI test bundle sits inside the Watch unit test bundle here: its test keeps its own bundle.
WATCH_MUTANT = _nested_bundle(
    _without_identifier(
        _tree("AICaddieWatch", WATCH_CASES, ("Passed", "Skipped", "Passed"), WATCH_DEVICE), WATCH_CASES[1][2]
    ),
    "AICaddieWatchUITests",
    "AICaddieWatchTests",
)
WATCH_NO_TESTS = {
    "devices": [WATCH_DEVICE],
    "testNodes": [
        {
            "name": "AICaddieWatch",
            "nodeType": "Test Plan",
            "result": "Failed",
            "children": [{"name": "AICaddieWatchTests", "nodeType": "Unit test bundle", "result": "Failed", "children": []}],
        }
    ],
    "testPlanConfigurations": [{"configurationId": "1", "configurationName": "Test Scheme Action"}],
}
BASELINE_STATUSES = {**_expected(IOS_CASES, ("passed",) * 5), **_expected(WATCH_CASES, ("passed",) * 3)}
MUTANT_STATUSES = {
    **_expected(IOS_CASES[:3], ("passed", "passed", "failed")),
    "AICaddieTests/NearbyDiscovery/testNearbyDiscoveryWaitsForLocation()": "skipped",
    **_expected(IOS_CASES[4:], ("passed",)),
    **_expected(WATCH_CASES, ("passed", "skipped", "passed")),
}
# The iOS run fails StartRoundDiscoveryTests/testPreselectedTee…
IOS_FAILED_ONCE = _tree("AICaddie", IOS_CASES, ("Passed", "Passed", "Failed", "Passed", "Passed"), IOS_DEVICE)


def _scheme(
    exit_code: int = 0,
    *,
    tree: dict | None = None,
    bundle: bool = True,
    xcresult: dict | None = None,
    cancel: bool = False,
) -> dict:
    # G2 G3 G4: how the fake xcodebuild and xcresulttool behave for one scheme. `cancel` cancels the run
    # while this scheme tests.
    return {
        "exit": exit_code,
        "bundle": bundle,
        "cancel": cancel,
        "xcresult": xcresult if xcresult is not None else {"tree": tree},
    }


PASSING_IOS = _scheme(0, tree=IOS_PASSING)
PASSING_WATCH = _scheme(0, tree=WATCH_PASSING)


FAKE_TOOLS = r'''
import json
import os
import re
import sys
from pathlib import Path

STATE = Path(os.environ["CARD440_FAKE_STATE"])
CONFIG = json.loads((STATE / "config.json").read_text(encoding="utf-8"))


def option(args, name):
    for index, arg in enumerate(args):
        if arg == name and index + 1 < len(args):
            return args[index + 1]
        if arg.startswith(name + "="):
            return arg[len(name) + 1:]
    return None


def marker():
    # Trailing spaces are kept: a patch's added line must arrive as it was sent.
    path = Path.cwd() / CONFIG["marker"]
    return path.read_text(encoding="utf-8").rstrip("\n") if path.is_file() else None


def log(tool, args, **extra):
    entry = {"tool": tool, "args": args, "cwd": os.getcwd(), **extra}
    with (STATE / "calls.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def bundles():
    path = STATE / "bundles.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def runtime_key(key):
    match = re.search(r"\.(iOS|watchOS)-(\d+)-(\d+)$", key)
    return (match.group(1), int(match.group(2)), int(match.group(3))) if match else (key, 0, 0)


def simctl(args):
    if args[:1] != ["list"]:
        return 0
    devices = CONFIG["devices"]
    if "available" in args:
        devices = {key: [d for d in value if d.get("isAvailable")] for key, value in devices.items()}
    if "-j" in args or "--json" in args:
        print(json.dumps({"devices": devices}, indent=2))
        return 0
    print("== Devices ==")
    # Same unordered runtime order as the JSON: the contract picks the simulators from the JSON.
    for key in devices:
        platform, major, minor = runtime_key(key)
        print(f"-- {platform} {major}.{minor} --")
        for device in devices[key]:
            print(f"    {device['name']} ({device['udid']}) ({device.get('state', 'Shutdown')})")
    return 0


def xcresulttool(args):
    if args[:3] != ["get", "test-results", "tests"] or "--legacy" in args:
        print("card440 fake xcresulttool: only `get test-results tests --path <bundle>` is served", file=sys.stderr)
        return 64
    path = option(args, "--path")
    scheme = bundles().get(os.path.realpath(path)) if path else None
    if scheme is None or not Path(path).is_dir():
        print(f"Error: no result bundle at {path}", file=sys.stderr)
        return 1
    served = CONFIG["xcresult"].get(scheme) or {"exit": 1}
    if served.get("tree") is not None:
        # A case can print a tree and still exit non-zero: xcresulttool failed.
        print(json.dumps(served["tree"], indent=2))
        return int(served.get("exit", 0))
    if "raw" in served:
        print(served["raw"])
        return 0
    print("Error: the result bundle could not be read", file=sys.stderr)
    return int(served.get("exit", 1))


def xcrun(args):
    log("xcrun", args)
    if args[:1] == ["simctl"]:
        return simctl(args[1:])
    if args[:1] == ["xcresulttool"]:
        return xcresulttool(args[1:])
    print(f"card440 fake xcrun: unsupported {args}", file=sys.stderr)
    return 64


def xcodebuild(args):
    log("xcodebuild", args, marker=marker())
    if "test-without-building" in args:
        print("card440 fake xcodebuild: run `xcodebuild test` (contract)", file=sys.stderr)
        return 64
    if "test" not in args:
        print("Xcode 16.4")
        return 0
    project = option(args, "-project")
    if not project or not (Path.cwd() / project).is_dir():
        print(f"xcodebuild: error: '{project}' does not exist.", file=sys.stderr)
        return 66
    scheme = option(args, "-scheme") or ""
    behaviour = CONFIG["xcodebuild"].get(scheme, {"exit": 0, "bundle": True})
    if behaviour.get("cancel"):
        # The run is cancelled while this scheme tests (agenthub cancels it, or the job times out).
        (STATE / "cancelled").touch()
        print("** TEST INTERRUPTED **", file=sys.stderr)
        return 130
    bundle = option(args, "-resultBundlePath")
    if bundle and behaviour.get("bundle", True):
        target = Path(bundle) if os.path.isabs(bundle) else Path.cwd() / bundle
        if target.exists():
            print(f"xcodebuild: error: Existing file at -resultBundlePath \"{bundle}\"", file=sys.stderr)
            return 64
        target.mkdir(parents=True)
        (target / "Info.plist").write_text("card440 fake result bundle\n", encoding="utf-8")
        known = bundles()
        known[os.path.realpath(target)] = scheme
        (STATE / "bundles.json").write_text(json.dumps(known), encoding="utf-8")
    code = int(behaviour.get("exit", 0))
    print("** TEST SUCCEEDED **" if code == 0 else "** TEST FAILED **")
    return code


def xcodegen(args):
    log("xcodegen", args, marker=marker())
    if not (STATE / "xcodegen-installed").is_file():
        print("xcodegen: command not found (the runner image has no XcodeGen: brew install xcodegen)", file=sys.stderr)
        return 127
    if args[:1] != ["generate"]:
        return 0
    spec = option(args, "--spec") or "project.yml"
    if not (Path.cwd() / spec).is_file():
        print(f"xcodegen: no spec at {spec}", file=sys.stderr)
        return 1
    if CONFIG["broken_spec"] in (Path.cwd() / spec).read_text(encoding="utf-8"):
        print(f"xcodegen: Spec validation error in {spec}", file=sys.stderr)
        return 1
    (Path.cwd() / Path(spec).parent / "AICaddieNative.xcodeproj").mkdir(parents=True, exist_ok=True)
    return 0


def other(tool, args):
    log(tool, args)
    if tool in CONFIG["fail"]:
        print(f"card440 fake {tool}: failed (runner failure)", file=sys.stderr)
        return 1
    if tool == "brew" and "install" in args and "xcodegen" in args:
        (STATE / "xcodegen-installed").touch()
    return 0


TOOLS = {"xcrun": xcrun, "xcodebuild": xcodebuild, "xcodegen": xcodegen}
tool, args = sys.argv[1], sys.argv[2:]
sys.exit(TOOLS[tool](args) if tool in TOOLS else other(tool, args))
'''


def _option(args: list[str], name: str) -> str | None:
    # G2: the value of `name value` or `name=value` in a recorded command line.
    for index, arg in enumerate(args):
        if arg == name and index + 1 < len(args):
            return args[index + 1]
        if arg.startswith(name + "="):
            return arg[len(name) + 1 :]
    return None


def _destination(value: str | None) -> dict[str, str]:
    # G2: `platform=…,id=…` as a mapping.
    fields: dict[str, str] = {}
    for part in (value or "").split(","):
        key, _, item = part.partition("=")
        fields[key.strip()] = item.strip()
    return fields


def _skip_testing(args: list[str]) -> list[str]:
    # G2: every -skip-testing target in a command line.
    targets = []
    for index, arg in enumerate(args):
        if arg == "-skip-testing" and index + 1 < len(args):
            targets.append(args[index + 1])
        elif arg.startswith("-skip-testing:"):
            targets.append(arg.split(":", 1)[1])
    return targets


VALUE_OPTIONS = ("-project", "-scheme", "-destination", "-resultBundlePath")


def _arguments(args: list[str]) -> tuple[list[str], list[str]]:
    # G2: an `xcodebuild test` command line split into the contract's arguments (`test`, the four value
    # options, `-skip-testing`) and everything else (build settings, retries, timeouts, other options).
    known: list[str] = []
    other: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in (*VALUE_OPTIONS, "-skip-testing") and index + 1 < len(args):
            known.append(arg)
            index += 2
            continue
        name = re.split(r"[=:]", arg, maxsplit=1)[0]
        if arg == "test" or (name in VALUE_OPTIONS and arg.startswith(f"{name}=")) or arg.startswith("-skip-testing:"):
            known.append(name)
        else:
            other.append(arg)
        index += 1
    return known, other


def _text(value: object) -> str:
    # G1 G3: a GitHub expression value as the string it interpolates to.
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _truthy(value: object) -> bool:
    # G1 G3: GitHub expression truthiness.
    return value not in (None, False, 0, "")


def _command_file(path: Path) -> dict[str, str]:
    # G2 G3: `NAME=value` and `NAME<<DELIM … DELIM` entries of $GITHUB_ENV / $GITHUB_OUTPUT.
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip():
            continue
        if "<<" in line and ("=" not in line or line.index("<<") < line.index("=")):
            name, delimiter = line.split("<<", 1)
            body = []
            while index < len(lines) and lines[index] != delimiter:
                body.append(lines[index])
                index += 1
            index += 1
            values[name] = "\n".join(body)
        elif "=" in line:
            name, value = line.split("=", 1)
            values[name] = value
    return values


_TOKEN = re.compile(
    r"\s*(?:"
    r"(?P<string>'(?:[^']|'')*')"
    r"|(?P<op>==|!=|&&|\|\||!|\(|\))"
    r"|(?P<call>[A-Za-z_]\w*)\(\s*\)"
    r"|(?P<number>\d+)"
    r"|(?P<name>[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)*)"
    r")"
)


class _Expression:
    """The subset of GitHub expressions the replay evaluates (contract, "Replay rules")."""

    def __init__(self, text: str, resolve, failed: bool, cancelled: bool) -> None:
        self.text = text
        self.tokens: list[tuple[str, str]] = []
        source = text.strip()
        position = 0
        while position < len(source):
            match = _TOKEN.match(source, position)
            if not match or match.end() == position or match.lastgroup is None:
                raise AssertionError(f"card #440 replay cannot read the expression {text!r} at {source[position:]!r}")
            self.tokens.append((match.lastgroup, match.group(match.lastgroup)))
            position = match.end()
            while position < len(source) and source[position].isspace():
                position += 1
        self.index = 0
        self.resolve = resolve
        self.failed = failed
        self.cancelled = cancelled

    def value(self) -> object:
        result = self._or()
        if self.index != len(self.tokens):
            raise AssertionError(f"card #440 replay cannot read the expression {self.text!r}")
        return result

    def _peek(self) -> tuple[str | None, str | None]:
        return self.tokens[self.index] if self.index < len(self.tokens) else (None, None)

    def _take(self) -> tuple[str | None, str | None]:
        token = self._peek()
        self.index += 1
        return token

    def _or(self) -> object:
        left = self._and()
        while self._peek() == ("op", "||"):
            self._take()
            right = self._and()
            left = left if _truthy(left) else right
        return left

    def _and(self) -> object:
        left = self._not()
        while self._peek() == ("op", "&&"):
            self._take()
            right = self._not()
            left = right if _truthy(left) else left
        return left

    def _not(self) -> object:
        if self._peek() == ("op", "!"):
            self._take()
            return not _truthy(self._not())
        return self._compare()

    def _compare(self) -> object:
        left = self._primary()
        if self._peek() in (("op", "=="), ("op", "!=")):
            operator = self._take()[1]
            right = self._primary()
            if isinstance(left, str) and isinstance(right, str):
                equal = left.casefold() == right.casefold()
            else:
                equal = left == right
            return equal if operator == "==" else not equal
        return left

    def _primary(self) -> object:
        kind, value = self._take()
        if (kind, value) == ("op", "("):
            inner = self._or()
            if self._take() != ("op", ")"):
                raise AssertionError(f"card #440 replay: unbalanced parentheses in {self.text!r}")
            return inner
        if kind == "string":
            return str(value)[1:-1].replace("''", "'")
        if kind == "number":
            return int(str(value))
        if kind == "call":
            if value == "success":
                return not self.failed and not self.cancelled
            if value == "failure":
                return self.failed
            if value == "always":
                return True
            if value == "cancelled":
                return self.cancelled
            raise AssertionError(f"card #440 replay does not support {value}() in {self.text!r}")
        if kind == "name":
            if value == "true":
                return True
            if value == "false":
                return False
            if value == "null":
                return None
            return self.resolve(value)
        raise AssertionError(f"card #440 replay cannot read the expression {self.text!r}")


@dataclass
class _Outcome:
    request_id: str
    head_sha: str
    main_sha: str
    job_failed: bool
    cancelled: bool
    cancel_index: int | None
    steps: list[dict]
    uploads: list[dict]
    calls: list[dict]

    def tool(self, name: str) -> list[dict]:
        # G2: recorded calls of one fake tool.
        return [call for call in self.calls if call["tool"] == name]

    def scheme_runs(self) -> list[dict]:
        # G2: `xcodebuild test` invocations. (Not named test_*: the gate treats such names as tests.)
        return [call for call in self.tool("xcodebuild") if "test" in call["args"]]

    def writer_steps(self) -> list[dict]:
        # G3: the steps that ran and whose `run:` names the result writer.
        return [step for step in self.steps if step["ran"] and step["writer"]]

    def result_files(self) -> list[str]:
        # G3 G4: every uploaded file named result.json, in any artifact and at any depth.
        return [
            text
            for upload in self.uploads
            for name, text in upload["files"].items()
            if name.rsplit("/", 1)[-1] == "result.json"
        ]

    def describe(self) -> str:
        # G1 G2 G3 G4: the replayed job, for failure messages.
        colour = "CANCELLED" if self.cancelled else "FAILED" if self.job_failed else "green"
        lines = [f"job {colour}; uploads: {[u['name'] for u in self.uploads]}"]
        for step in self.steps:
            if not step["ran"]:
                lines.append(f"  - {step['name']}: skipped")
                continue
            lines.append(f"  - {step['name']}: {step['outcome']} (exit {step['exit']}, conclusion {step['conclusion']})")
            if step["exit"]:
                lines.extend("      " + line for line in step["output"][-2000:].splitlines())
        return "\n".join(lines)


class _Replay:
    """Runs the workflow's single job offline under GitHub's step rules (see the module docstring)."""

    def __init__(
        self,
        root: Path,
        workflow: dict,
        config: dict,
        inputs: dict[str, str],
        origin: Path,
        main_sha: str,
        git_env: dict[str, str],
        cancel_after_writer: bool = False,
    ) -> None:
        self.workflow = workflow
        self.inputs = inputs
        self.origin = origin
        self.git_env = git_env
        self.cancel_after_writer = cancel_after_writer
        self.workspace = root / "runner" / "work" / "garmin-ai-caddie"
        self.temp = root / "runner" / "temp"
        self.state = root / "state"
        self.bin = root / "bin"
        for path in (self.workspace, self.temp, self.state, self.bin):
            path.mkdir(parents=True, exist_ok=True)
        (self.state / "config.json").write_text(json.dumps(config), encoding="utf-8")
        self._install_fakes()
        self.env_file = self.temp / "card440-github-env"
        self.env_file.touch()
        path_file = self.temp / "card440-github-path"
        path_file.touch()
        summary_file = self.temp / "card440-step-summary"
        summary_file.touch()
        self.github = {
            "sha": main_sha,
            "ref": "refs/heads/main",
            "ref_name": "main",
            "repository": REPOSITORY,
            "repository_owner": "jasonhorga",
            "workspace": str(self.workspace),
            "run_id": "4400440",
            "run_number": "1",
            "run_attempt": "1",
            "event_name": "workflow_dispatch",
            "actor": "agenthub",
            "server_url": "https://github.com",
        }
        self.runner = {"temp": str(self.temp), "os": "macOS", "arch": "ARM64"}
        self.base_env = {
            **git_env,
            "PATH": f"{self.bin}{os.pathsep}{git_env['PATH']}",
            "TMPDIR": str(self.temp),
            "CI": "true",
            "GITHUB_ACTIONS": "true",
            "GITHUB_WORKSPACE": str(self.workspace),
            "GITHUB_SHA": main_sha,
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_REPOSITORY": REPOSITORY,
            "GITHUB_RUN_ID": "4400440",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_ENV": str(self.env_file),
            "GITHUB_PATH": str(path_file),
            "GITHUB_STEP_SUMMARY": str(summary_file),
            "RUNNER_TEMP": str(self.temp),
            "RUNNER_OS": "macOS",
            "RUNNER_ARCH": "ARM64",
            "CARD440_FAKE_STATE": str(self.state),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        self.env: dict[str, str] = {}
        self.step_results: dict[str, dict] = {}
        self.failed = False
        self.cancelled = False
        self.cancel_index: int | None = None
        self.log: list[dict] = []
        self.uploads: list[dict] = []

    def _install_fakes(self) -> None:
        fake = self.state / "card440_fake_tools.py"
        fake.write_text(FAKE_TOOLS, encoding="utf-8")
        python = shlex.quote(sys.executable)
        wrappers = {
            tool: f'#!/bin/sh\nexec {python} {shlex.quote(str(fake))} {tool} "$@"\n'
            for tool in ("xcrun", "xcodebuild", "xcodegen", "brew", "xcode-select")
        }
        wrappers["python3"] = f'#!/bin/sh\nexec {python} "$@"\n'
        wrappers["python"] = f'#!/bin/sh\nexec {python} "$@"\n'
        wrappers["sudo"] = '#!/bin/sh\nexec "$@"\n'
        for name, text in wrappers.items():
            path = self.bin / name
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)

    def _env_context(self) -> dict[str, str]:
        return {**self.env, **_command_file(self.env_file)}

    def _resolve(self, name: str) -> object:
        parts = name.split(".")
        if parts[0] == "inputs" and len(parts) == 2:
            return self.inputs.get(parts[1], "")
        if parts[:3] == ["github", "event", "inputs"] and len(parts) == 4:
            return self.inputs.get(parts[3], "")
        if parts[0] == "github" and len(parts) == 2 and parts[1] in self.github:
            return self.github[parts[1]]
        if parts[0] == "runner" and len(parts) == 2 and parts[1] in self.runner:
            return self.runner[parts[1]]
        if parts[0] == "env" and len(parts) == 2:
            return self._env_context().get(parts[1], "")
        if parts[0] == "steps" and len(parts) in (3, 4):
            step = self.step_results.get(parts[1], {})
            if len(parts) == 3 and parts[2] in ("outcome", "conclusion"):
                return step.get(parts[2], "")
            if len(parts) == 4 and parts[2] == "outputs":
                return step.get("outputs", {}).get(parts[3], "")
        if name == "job.status":
            return "cancelled" if self.cancelled else "failure" if self.failed else "success"
        raise AssertionError(f"card #440 replay does not support the expression context {name!r} (contract, replay rules)")

    def _evaluate(self, text: str) -> object:
        return _Expression(text, self._resolve, self.failed, self.cancelled).value()

    def _interpolate(self, value: object) -> str:
        if not isinstance(value, str):
            return _text(value)
        return re.sub(r"\$\{\{(.*?)\}\}", lambda match: _text(self._evaluate(match.group(1))), value, flags=re.S)

    def _mapping(self, values: object) -> dict[str, str]:
        if not values:
            return {}
        if not isinstance(values, dict):
            raise AssertionError(f"card #440 replay: env must be a mapping, not {values!r}")
        return {str(key): self._interpolate(value) for key, value in values.items()}

    def _condition(self, raw: object) -> bool:
        # Without a status function, `success()` applies: false after a failure or a cancellation.
        clear = not self.failed and not self.cancelled
        if raw is None:
            return clear
        if isinstance(raw, bool):
            return raw and clear
        text = str(raw).strip()
        if text.startswith("${{") and text.endswith("}}"):
            text = text[3:-2]
        value = _truthy(self._evaluate(text))
        if not STATUS_FUNCTIONS.search(text):
            return value and clear
        return value

    def run(self, request_id: str, head_sha: str) -> _Outcome:
        jobs = self.workflow.get("jobs") or {}
        if len(jobs) != 1:
            raise AssertionError(f"the workflow must have exactly one job, found {list(jobs)}")
        job = next(iter(jobs.values()))
        self.env.update(self._mapping(self.workflow.get("env")))
        self.env.update(self._mapping(job.get("env")))
        defaults = {
            **(((self.workflow.get("defaults") or {}).get("run")) or {}),
            **(((job.get("defaults") or {}).get("run")) or {}),
        }
        steps = job.get("steps") or []
        writers = [index for index, step in enumerate(steps) if WRITER.name in str(step.get("run") or "")]
        for index, step in enumerate(steps):
            self._step(index, step, defaults)
            if self.cancel_after_writer and writers and index == writers[-1] and not self.cancelled:
                # The cancellation arrives once the last step that names the writer has finished.
                self.cancelled = True
                self.cancel_index = index
        calls_file = self.state / "calls.jsonl"
        calls = (
            [json.loads(line) for line in calls_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            if calls_file.is_file()
            else []
        )
        return _Outcome(
            request_id=request_id,
            head_sha=head_sha,
            main_sha=self.github["sha"],
            job_failed=self.failed,
            cancelled=self.cancelled,
            cancel_index=self.cancel_index,
            steps=self.log,
            uploads=self.uploads,
            calls=calls,
        )

    def _step(self, index: int, step: dict, defaults: dict) -> None:
        run_text = str(step.get("run") or "").strip()
        name = str(step.get("name") or step.get("uses") or (run_text.splitlines()[0] if run_text else f"step {index}"))
        step_id = str(step.get("id") or f"__card440_step_{index}")
        record = {
            "name": name,
            "id": step.get("id"),
            "writer": WRITER.name in run_text,
            "ran": False,
            "exit": None,
            "outcome": "skipped",
            "conclusion": "skipped",
            "output": "",
        }
        self.log.append(record)
        if not self._condition(step.get("if")):
            self.step_results[step_id] = {"outcome": "skipped", "conclusion": "skipped", "outputs": {}}
            return
        record["ran"] = True
        step_env = self._mapping(step.get("env"))
        outputs: dict[str, str] = {}
        if "uses" in step:
            code, text = self._uses(str(step["uses"]), step.get("with") or {})
        else:
            code, text, outputs = self._run(name, step, defaults, step_env)
        continue_on_error = step.get("continue-on-error", False)
        if isinstance(continue_on_error, str):
            raw = continue_on_error.strip()
            if raw.startswith("${{") and raw.endswith("}}"):
                raw = raw[3:-2]
            continue_on_error = _truthy(self._evaluate(raw))
        if not self.cancelled and (self.state / "cancelled").is_file():
            # The run was cancelled while this step ran: the step ends `cancelled`, whatever its exit.
            self.cancelled = True
            self.cancel_index = index
            outcome = conclusion = "cancelled"
        else:
            outcome = "success" if code == 0 else "failure"
            conclusion = "success" if code == 0 or continue_on_error else "failure"
        if conclusion == "failure":
            self.failed = True
        record.update(exit=code, outcome=outcome, conclusion=conclusion, output=text)
        self.step_results[step_id] = {"outcome": outcome, "conclusion": conclusion, "outputs": outputs}

    def _run(self, name: str, step: dict, defaults: dict, step_env: dict[str, str]) -> tuple[int, str, dict[str, str]]:
        shell = step.get("shell", defaults.get("shell"))
        if shell not in (None, "bash"):
            raise AssertionError(f"step {name!r}: the replay runs bash steps only (shell: {shell!r})")
        script = str(step["run"])
        if "${{" in script:
            raise AssertionError(f"step {name!r}: pass values to run: through env:, not ${{{{ }}}} (contract, replay rules)")
        directory = step.get("working-directory", defaults.get("working-directory"))
        cwd = self.workspace / self._interpolate(directory) if directory else self.workspace
        if not cwd.is_dir():
            return 1, f"working directory {cwd} does not exist", {}
        index = len(self.log)
        script_path = self.temp / f"card440-step-{index}.sh"
        script_path.write_text(script, encoding="utf-8")
        output_file = self.temp / f"card440-output-{index}"
        output_file.touch()
        env = {**self.base_env, **self._env_context(), **step_env, "GITHUB_OUTPUT": str(output_file)}
        command = (
            [BASH, "--noprofile", "--norc", "-eo", "pipefail", str(script_path)]
            if shell == "bash"
            else [BASH, "-e", str(script_path)]
        )
        proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
        return proc.returncode, proc.stdout + proc.stderr, _command_file(output_file)

    def _uses(self, uses: str, with_: dict) -> tuple[int, str]:
        values = {str(key): self._interpolate(value) for key, value in with_.items()}
        action = uses.split("@", 1)[0]
        if action == "actions/checkout":
            return self._checkout(values)
        if action == "actions/upload-artifact":
            return self._upload(values)
        return 0, f"{uses}: not replayed"

    def _checkout(self, values: dict[str, str]) -> tuple[int, str]:
        repository = values.get("repository", "")
        if repository not in ("", REPOSITORY):
            return 1, f"checkout of another repository: {repository!r}"
        ref = values.get("ref") or self.github["sha"]
        workspace = self.workspace.resolve()
        target = (self.workspace / values.get("path", "")).resolve()
        if target != workspace and workspace not in target.parents:
            return 1, f"checkout path outside the workspace: {target}"
        if re.fullmatch(r"[0-9a-f]{40}", ref):
            commit = ref
        elif ref.startswith("refs/heads/"):
            commit = "origin/" + ref[len("refs/heads/") :]
        elif ref.startswith("refs/"):
            return 1, f"the replay checks out commits and branches only, not {ref!r}"
        else:
            commit = "origin/" + ref
        if target.exists():
            # actions/checkout replaces whatever the path held.
            for child in target.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        else:
            target.mkdir(parents=True)
        output = ""
        for command in (
            ["git", "clone", "--quiet", str(self.origin), str(target)],
            ["git", "-C", str(target), "checkout", "--quiet", "--detach", commit],
        ):
            proc = subprocess.run(command, env=self.git_env, capture_output=True, text=True, timeout=120)
            output += proc.stdout + proc.stderr
            if proc.returncode:
                return proc.returncode, output
        return 0, f"checked out {ref} into {target}\n{output}"

    def _upload(self, values: dict[str, str]) -> tuple[int, str]:
        raw = values.get("path", "").strip()
        if not raw or "\n" in raw:
            return 1, f"the replay uploads one path per upload-artifact step, not {raw!r}"
        target = Path(raw) if os.path.isabs(raw) else self.workspace / raw
        files: dict[str, str] = {}
        if target.is_file():
            files[target.name] = target.read_text(encoding="utf-8", errors="replace")
        elif target.is_dir():
            for path in sorted(target.rglob("*")):
                if path.is_file():
                    files[path.relative_to(target).as_posix()] = path.read_text(encoding="utf-8", errors="replace")
        if not files:
            # upload-artifact@v4 creates no artifact without files; `error` also fails the step.
            return (1 if values.get("if-no-files-found", "warn") == "error" else 0), f"no files found at {raw}"
        self.uploads.append({"name": values.get("name", "artifact"), "path": raw, "files": files})
        return 0, f"uploaded {sorted(files)}"


class NativeMutantWorkflowTests(unittest.TestCase):
    def _workflow(self) -> dict:
        # G1: the workflow and the writer exist; the workflow parses.
        self.assertTrue(WORKFLOW.is_file(), f"missing {WORKFLOW.relative_to(REPO_ROOT).as_posix()}")
        self.assertTrue(WRITER.is_file(), f"missing {WRITER.relative_to(REPO_ROOT).as_posix()}")
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.assertIsInstance(workflow, dict)
        return workflow

    def _input_names(self, workflow: dict) -> tuple[str, str, str]:
        # G1: exactly three dispatch inputs: request_id, the head SHA and the base64 patch.
        triggers = workflow.get("on", workflow.get(True))
        self.assertIsInstance(triggers, dict, "`on:` must be a mapping with workflow_dispatch")
        dispatch = triggers.get("workflow_dispatch") or {}
        inputs = dispatch.get("inputs") or {}
        self.assertEqual(len(inputs), 3, f"expected three inputs, found {list(inputs)}")
        self.assertIn("request_id", inputs)
        sha = [name for name in inputs if name != "request_id" and "sha" in name.lower()]
        patch = [name for name in inputs if name != "request_id" and "patch" in name.lower()]
        self.assertEqual(len(sha), 1, f"one input must name the head SHA: {list(inputs)}")
        self.assertEqual(len(patch), 1, f"one input must carry the patch: {list(inputs)}")
        self.assertNotEqual(sha[0], patch[0])
        return "request_id", sha[0], patch[0]

    def _git_env(self, root: Path) -> dict[str, str]:
        # G1 G2 G3: git isolated from the host's configuration.
        home = root / "home"
        home.mkdir()
        gitconfig = root / "gitconfig"
        gitconfig.write_text(
            "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n[advice]\n\tdetachedHead = false\n",
            encoding="utf-8",
        )
        return {
            "PATH": os.environ.get("PATH", os.defpath),
            "HOME": str(home),
            "LANG": "C.UTF-8",
            "GIT_CONFIG_GLOBAL": str(gitconfig),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "card440",
            "GIT_AUTHOR_EMAIL": "card440@example.invalid",
            "GIT_COMMITTER_NAME": "card440",
            "GIT_COMMITTER_EMAIL": "card440@example.invalid",
        }

    def _git(self, env: dict[str, str], cwd: Path, *args: str) -> str:
        # G1 G2 G3: one git command for the throwaway origin.
        proc = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, f"git {' '.join(args)}: {proc.stderr}")
        return proc.stdout.strip()

    def _origin(self, root: Path, env: dict[str, str]) -> tuple[Path, str, str]:
        # G1 G2 G3: origin with the head under test (no workflow, no writer), the dispatched main commit on
        # top of it, and a later main commit whose writer only fails. Returns the dispatched commit.
        seed = root / "seed"
        (seed / MARKER).parent.mkdir(parents=True)
        (seed / MARKER).write_text(HEAD_MARKER + "\n", encoding="utf-8")
        (seed / CONTEXT).write_text("".join(f"{line}\n" for line in CONTEXT_LINES), encoding="utf-8")
        (seed / SPEC).write_text(SPEC_TEXT + "\n", encoding="utf-8")
        scripts = seed / ".github" / "scripts"
        scripts.mkdir(parents=True)
        for path in sorted((REPO_ROOT / ".github" / "scripts").iterdir()):
            if path.is_file() and path.name != WRITER.name:
                shutil.copy2(path, scripts / path.name)
        self._git(env, seed, "init", "--quiet")
        self._git(env, seed, "symbolic-ref", "HEAD", "refs/heads/main")
        self._git(env, seed, "add", "--all")
        self._git(env, seed, "commit", "--quiet", "-m", "head under test")
        head = self._git(env, seed, "rev-parse", "HEAD")
        self._git(env, seed, "branch", "card-434")
        (seed / MARKER).write_text(MAIN_MARKER + "\n", encoding="utf-8")
        shutil.copy2(WRITER, scripts / WRITER.name)
        (seed / ".github" / "workflows").mkdir()
        shutil.copy2(WORKFLOW, seed / ".github" / "workflows" / WORKFLOW.name)
        self._git(env, seed, "add", "--all")
        self._git(env, seed, "commit", "--quiet", "-m", "main with the native mutant workflow")
        main = self._git(env, seed, "rev-parse", "HEAD")
        (scripts / WRITER.name).write_text(LATER_WRITER, encoding="utf-8")
        self._git(env, seed, "commit", "--quiet", "--all", "-m", "a later main commit")
        origin = root / "origin.git"
        self._git(env, root, "clone", "--quiet", "--bare", str(seed), str(origin))
        self._git(env, origin, "config", "uploadpack.allowAnySHA1InWant", "true")
        return origin, head, main

    def _replay(
        self,
        *,
        patch_b64: str = "",
        ios: dict = PASSING_IOS,
        watch: dict = PASSING_WATCH,
        devices: dict = DEVICES,
        fail: tuple[str, ...] = (),
        cancel_after_writer: bool = False,
    ) -> _Outcome:
        # G1 G2 G3 G4: one dispatch of the workflow, replayed offline. `fail` names fake runner tools
        # (brew, xcode-select) that exit non-zero; `cancel_after_writer` cancels the run once the writer's
        # step has finished.
        workflow = self._workflow()
        request_key, sha_key, patch_key = self._input_names(workflow)
        holder = tempfile.TemporaryDirectory(prefix="card440-")
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        git_env = self._git_env(root)
        origin, head, main = self._origin(root, git_env)
        request_id = f"card440-{uuid.uuid4().hex[:12]}"
        config = {
            "marker": MARKER,
            "broken_spec": BROKEN_SPEC,
            "fail": list(fail),
            "devices": devices,
            "xcodebuild": {
                "AICaddie": {"exit": ios["exit"], "bundle": ios["bundle"], "cancel": ios["cancel"]},
                "AICaddieWatch": {"exit": watch["exit"], "bundle": watch["bundle"], "cancel": watch["cancel"]},
            },
            "xcresult": {"AICaddie": ios["xcresult"], "AICaddieWatch": watch["xcresult"]},
        }
        replay = _Replay(
            root,
            workflow,
            config,
            {request_key: request_id, sha_key: head, patch_key: patch_b64},
            origin,
            main,
            git_env,
            cancel_after_writer,
        )
        return replay.run(request_id, head)

    def _result(self, run: _Outcome) -> dict:
        # G3 G4: exactly one result.json is uploaded, at the root of the artifact `agenthub-native-result`,
        # with its common fields checked.
        found = run.result_files()
        self.assertEqual(len(found), 1, f"expected one uploaded result.json\n{run.describe()}")
        carriers = [upload for upload in run.uploads if "result.json" in upload["files"]]
        self.assertEqual(
            [upload["name"] for upload in carriers],
            [ARTIFACT],
            f"result.json must sit at the root of the artifact {ARTIFACT!r}\n{run.describe()}",
        )
        try:
            result = json.loads(found[0])
        except json.JSONDecodeError as exc:
            self.fail(f"result.json is not JSON ({exc}): {found[0][:400]!r}")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("request_id"), run.request_id)
        self.assertEqual(result.get("head_sha"), run.head_sha)
        tests = result.get("tests")
        self.assertIsInstance(tests, list, "result.json `tests` must be a list")
        ids = []
        for entry in tests:
            self.assertIsInstance(entry, dict)
            self.assertIsInstance(entry.get("id"), str, entry)
            self.assertIn(entry.get("status"), STATUSES, entry)
            ids.append(entry["id"])
        self.assertEqual(len(ids), len(set(ids)), f"test ids must be unique: {ids}")
        return result

    def _statuses(self, result: dict) -> dict[str, str]:
        # G4: test id -> status.
        return {entry["id"]: entry["status"] for entry in result["tests"]}

    def _check_scheme_runs(self, run: _Outcome, marker: str) -> None:
        # G2: one `xcodebuild test` per scheme, on the generated project, on the resolved simulator by
        # UDID, after the patch, each with its own result bundle and no other argument, and never the
        # AICaddieUITests target.
        for call in run.calls:
            self.assertFalse([arg for arg in call["args"] if "AICaddieUITests" in arg], call)
        runs = run.scheme_runs()
        self.assertEqual(
            sorted(_option(call["args"], "-scheme") or "" for call in runs),
            ["AICaddie", "AICaddieWatch"],
            run.describe(),
        )
        bundles = {
            os.path.normpath(os.path.join(call["cwd"], _option(call["args"], "-resultBundlePath") or ""))
            for call in runs
        }
        self.assertEqual(len(bundles), 2, f"each scheme needs its own -resultBundlePath: {sorted(bundles)}")
        expected = {"AICaddie": ("iOS Simulator", IOS_UDID), "AICaddieWatch": ("watchOS Simulator", WATCH_UDID)}
        for call in runs:
            args = call["args"]
            scheme = _option(args, "-scheme") or ""
            with _case(f"scheme {scheme}"):
                self.assertEqual(_option(args, "-project"), PROJECT)
                self.assertEqual(call["marker"], marker, "the head under test (plus the patch) must be tested")
                self.assertTrue(_option(args, "-resultBundlePath"), "xcodebuild test needs -resultBundlePath")
                known, other = _arguments(args)
                self.assertEqual(
                    other,
                    [],
                    "xcodebuild test takes only test, -project, -scheme, -destination, -resultBundlePath and "
                    "-skip-testing:AICaddieWatchUITests: no build settings, test plans or configurations, "
                    f"-only-testing, retries, iterations, timeouts or other options: {args}",
                )
                for name in ("test", *VALUE_OPTIONS):
                    self.assertEqual(known.count(name), 1, f"exactly one {name} per scheme: {args}")
                for target in _skip_testing(args):
                    self.assertTrue(
                        scheme == "AICaddieWatch" and target.split("/")[0] == "AICaddieWatchUITests",
                        f"only AICaddieWatchUITests may be skipped: {args}",
                    )
                self.assertEqual(
                    _destination(_option(args, "-destination")),
                    {"platform": expected[scheme][0], "id": expected[scheme][1]},
                    f"-destination is exactly platform=…,id=<UDID>, never name= or OS=: {args}",
                )

    # G1 — dispatch-only, read-only, named by the request id

    def test_workflow_is_dispatch_only_read_only_and_named_by_request_id(self) -> None:
        # G1: trigger, permissions, run-name, inputs (the patch optional), single job on native-mobile's
        # runner image without a concurrency group or a short timeout, values reach the shell through
        # env, no secrets, checkouts keep no credentials, the writer is the one in .github/scripts, and one
        # upload step names the artifact `agenthub-native-result` literally.
        workflow = self._workflow()
        text = WORKFLOW.read_text(encoding="utf-8")
        triggers = workflow.get("on", workflow.get(True))
        self.assertIsInstance(triggers, dict)
        self.assertEqual(list(triggers), ["workflow_dispatch"], "workflow_dispatch must be the only trigger")
        request, sha, patch = self._input_names(workflow)
        inputs = triggers["workflow_dispatch"]["inputs"]
        for name in (request, sha, patch):
            self.assertEqual((inputs[name] or {}).get("type", "string"), "string", name)
        self.assertIs(inputs[request].get("required"), True)
        self.assertIs(inputs[sha].get("required"), True)
        self.assertIs((inputs[patch] or {}).get("required", False), False, "a baseline sends an empty patch")
        self.assertEqual(workflow.get("permissions"), {"contents": "read"})
        self.assertEqual(workflow.get("run-name"), RUN_NAME)
        jobs = workflow.get("jobs") or {}
        self.assertEqual(len(jobs), 1, list(jobs))
        job = next(iter(jobs.values()))
        self.assertEqual(job.get("permissions", {"contents": "read"}), {"contents": "read"})
        native_runner = yaml.safe_load(NATIVE_MOBILE.read_text(encoding="utf-8"))["jobs"]["native-mobile"]["runs-on"]
        self.assertEqual(job.get("runs-on"), native_runner)
        self.assertNotIn("if", job)
        self.assertNotIn("continue-on-error", job)
        self.assertNotIn("concurrency", workflow, "one run per mutant: a concurrency group cancels pending runs")
        self.assertNotIn("concurrency", job, "one run per mutant: a concurrency group cancels pending runs")
        if "timeout-minutes" in job:
            timeout = job["timeout-minutes"]
            self.assertTrue(
                isinstance(timeout, int) and not isinstance(timeout, bool) and timeout >= 60,
                f"the job's timeout-minutes, if set, is a literal of at least 60, not {timeout!r}",
            )
        self.assertNotIn("secrets.", text)
        self.assertNotIn("AICaddieUITests", text)
        steps = job.get("steps") or []
        self.assertEqual(
            [step.get("name") or step.get("uses") for step in steps if "timeout-minutes" in step],
            [],
            "no step sets timeout-minutes: a test step cut short leaves a partial result that reads as a pass",
        )
        for step in steps:
            if "run" in step:
                self.assertNotIn("${{", str(step["run"]), step.get("name"))
                self.assertIn(step.get("shell", "bash"), ("bash",), step.get("name"))
        self.assertTrue([step for step in steps if WRITER.name in str(step.get("run") or "")], "no step runs the writer")
        head_refs = {f"${{{{inputs.{sha}}}}}", f"${{{{github.event.inputs.{sha}}}}}"}
        checkout_steps = [step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@")]
        checkouts = [re.sub(r"\s+", "", str((step.get("with") or {}).get("ref", ""))) for step in checkout_steps]
        self.assertTrue(head_refs & set(checkouts), f"checkout the head under test by its input: {checkouts}")
        for step in checkout_steps:
            # The patch is untrusted code that runs on the runner: no token left in .git/config.
            self.assertIn(
                (step.get("with") or {}).get("persist-credentials"),
                (False, "false"),
                f"{step.get('name') or step['uses']}: set persist-credentials: false",
            )
        artifact_names = [
            (step.get("with") or {}).get("name")
            for step in steps
            if str(step.get("uses", "")).startswith("actions/upload-artifact@")
        ]
        self.assertEqual(artifact_names, [ARTIFACT], f"one upload step, named {ARTIFACT!r} literally")

    # G1 G2 G3 G4 — a baseline run

    def test_baseline_run_tests_the_head_with_both_schemes_on_udid_simulators(self) -> None:
        # G1 G2 G3 G4: empty patch; the head is generated with xcodegen and tested with AICaddie and
        # AICaddieWatch on the newest iPhone 16 / Series 10 (46mm) by UDID, picked from the JSON list of
        # available simulators; result.json lists every test, written by the dispatched revision's writer
        # although main has moved on.
        run = self._replay(patch_b64="")

        self.assertFalse(run.job_failed, run.describe())
        listings = [
            call["args"]
            for call in run.tool("xcrun")
            if call["args"][:2] == ["simctl", "list"]
            and "devices" in call["args"]
            and ("-j" in call["args"] or "--json" in call["args"])
        ]
        self.assertTrue(listings, f"pick the simulators from `xcrun simctl list devices available -j`\n{run.describe()}")
        for args in listings:
            self.assertIn("available", args, f"list the available simulators only: {args}")
        generate = [call for call in run.tool("xcodegen") if call["args"][:1] == ["generate"]]
        self.assertEqual([call["args"] for call in generate], [XCODEGEN_ARGS], run.describe())
        self.assertEqual(generate[0]["marker"], HEAD_MARKER, "generate the project in the head checkout")
        self._check_scheme_runs(run, HEAD_MARKER)
        result = self._result(run)
        self.assertEqual(result.get("status"), "tested")
        self.assertEqual(self._statuses(result), BASELINE_STATUSES)

    # G2 G3 G4 — a mutant that a native test catches

    def test_failing_native_test_is_reported_and_the_job_stays_green(self) -> None:
        # G2 G3 G4: the patch is applied before generate and test; the iOS run exits 65 with a failed
        # test, the Watch run still happens, the job stays green and result.json has each status. One
        # Watch case and the nested iOS case have no nodeIdentifier, so their ids fall back to
        # <bundle>/<nearest suite>/<name>; the Watch UI test bundle, nested in the unit test bundle, keeps
        # its own name (the nearest bundle).
        run = self._replay(patch_b64=MUTANT_PATCH, ios=_scheme(65, tree=IOS_MUTANT), watch=_scheme(0, tree=WATCH_MUTANT))

        self.assertFalse(run.job_failed, run.describe())
        generate = [call for call in run.tool("xcodegen") if call["args"][:1] == ["generate"]]
        self.assertEqual([call["marker"] for call in generate], [MUTANT_MARKER], run.describe())
        self._check_scheme_runs(run, MUTANT_MARKER)
        result = self._result(run)
        self.assertEqual(result.get("status"), "tested")
        self.assertEqual(self._statuses(result), MUTANT_STATUSES)

    def test_watch_only_failure_is_reported(self) -> None:
        # G2 G3 G4: a failure in the Watch scheme alone is reported as failed with a green job. The
        # mutant's added line ends in a space; it applies and is tested exactly as sent.
        watch_failing = _tree("AICaddieWatch", WATCH_CASES, ("Passed", "Failed", "Passed"), WATCH_DEVICE)
        run = self._replay(patch_b64=TRAILING_SPACE_PATCH, watch=_scheme(65, tree=watch_failing))

        self.assertFalse(run.job_failed, run.describe())
        self._check_scheme_runs(run, TRAILING_SPACE_MARKER)
        result = self._result(run)
        self.assertEqual(result.get("status"), "tested")
        expected = dict(BASELINE_STATUSES)
        expected["AICaddieWatchTests/WatchDesignSnapshotTests/testTappingATeeStartsTheRoundWithThatTee()"] = "failed"
        self.assertEqual(self._statuses(result), expected)

    # G1 G3 G4 — the verdict comes from the workflow's own writer

    def test_the_writer_comes_from_the_workflow_revision_not_the_head(self) -> None:
        # G1 G3 G4: the mutant patch also adds a writer to the head under test, one that only fails. The
        # workflow still runs its own writer: the job stays green and result.json lists every test.
        run = self._replay(patch_b64=HEAD_WRITER_PATCH)

        self.assertFalse(run.job_failed, run.describe())
        self._check_scheme_runs(run, MUTANT_MARKER)
        result = self._result(run)
        self.assertEqual(result.get("status"), "tested")
        self.assertEqual(self._statuses(result), BASELINE_STATUSES)

    # G3 — apply and build failures are verdicts too

    def test_patch_that_does_not_apply_is_reported_as_apply_failed(self) -> None:
        # G1 G3: a patch whose changed line or surrounding context does not match the head (also by
        # whitespace alone), whose hunk counts are wrong, input that is not base64 (also one stray
        # character in valid base64), or is not a patch: nothing is selected, installed, generated or
        # tested, the job stays green, result.json says apply_failed with no tests.
        cases = {
            "stale changed line": STALE_PATCH,
            "stale surrounding context": STALE_CONTEXT_PATCH,
            "surrounding context differs only in whitespace": WHITESPACE_CONTEXT_PATCH,
            "hunk counts do not match the hunk": WRONG_COUNT_PATCH,
            "not base64": "not base64!",
            "a stray character in valid base64": STRAY_CHARACTER_PATCH,
            "not a patch": _b64("this is not a unified diff\n"),
        }
        for name, patch in cases.items():
            with _case(name):
                run = self._replay(patch_b64=patch)

                self.assertFalse(run.job_failed, run.describe())
                self.assertEqual(run.scheme_runs(), [], run.describe())
                after_apply = [
                    " ".join([call["tool"], *call["args"]])
                    for call in run.calls
                    if call["tool"] in ("brew", "xcodegen", "xcodebuild") or call["args"][:1] == ["simctl"]
                ]
                self.assertEqual(
                    after_apply,
                    [],
                    f"after an apply failure no simulator is picked, nothing installed, generated or built\n{run.describe()}",
                )
                result = self._result(run)
                self.assertEqual(result.get("status"), "apply_failed")
                self.assertEqual(result.get("tests"), [])

    def test_build_failure_is_reported_as_build_failed(self) -> None:
        # G2 G3 G4: a patched spec that does not generate, or a scheme without a usable result (no test
        # case, no bundle, unreadable bundle, xcresulttool exiting non-zero, output that is not JSON or
        # has no test nodes), makes the run build_failed, with a green job and result.json uploaded. A
        # failed test in the other scheme does not turn it into `tested`. When nothing was generated, no
        # xcodebuild test runs; otherwise both schemes run.
        both = ["AICaddie", "AICaddieWatch"]
        cases = {
            "the patched project spec does not generate": (BROKEN_SPEC_PATCH, PASSING_IOS, PASSING_WATCH, []),
            "watch ran no test": (MUTANT_PATCH, PASSING_IOS, _scheme(65, tree=WATCH_NO_TESTS), both),
            "watch left no result bundle": (MUTANT_PATCH, PASSING_IOS, _scheme(65, bundle=False), both),
            "watch bundle unreadable": (MUTANT_PATCH, PASSING_IOS, _scheme(65, xcresult={"exit": 1}), both),
            "watch tree is not JSON": (
                MUTANT_PATCH,
                PASSING_IOS,
                _scheme(65, xcresult={"raw": "error: malformed result"}),
                both,
            ),
            "watch xcresulttool printed a tree and exited 1": (
                MUTANT_PATCH,
                PASSING_IOS,
                _scheme(0, xcresult={"tree": WATCH_PASSING, "exit": 1}),
                both,
            ),
            "watch output is JSON without testNodes": (
                MUTANT_PATCH,
                PASSING_IOS,
                _scheme(65, xcresult={"raw": json.dumps({"devices": [WATCH_DEVICE]})}),
                both,
            ),
            "ios left no result bundle": (MUTANT_PATCH, _scheme(65, bundle=False), PASSING_WATCH, both),
            "ios failed a test, watch left no result bundle": (
                MUTANT_PATCH,
                _scheme(65, tree=IOS_FAILED_ONCE),
                _scheme(65, bundle=False),
                both,
            ),
        }
        for name, (patch, ios, watch, schemes) in cases.items():
            with _case(name):
                run = self._replay(patch_b64=patch, ios=ios, watch=watch)

                self.assertFalse(run.job_failed, run.describe())
                ran = sorted(_option(call["args"], "-scheme") or "" for call in run.scheme_runs())
                self.assertEqual(ran, schemes, run.describe())
                result = self._result(run)
                self.assertEqual(result.get("status"), "build_failed", result)

    # G2 G3 — a runner failure judges nothing

    def test_runner_failure_is_red_and_uploads_no_result(self) -> None:
        # G2 G3: without an available iPhone 16 or Series 10 (46mm), or when `brew install xcodegen`
        # fails, the job fails, no result.json is uploaded, and no test runs on another device.
        cases = {
            "no available iPhone 16": {"devices": _without_available(DEVICES, IPHONE)},
            "no available Apple Watch Series 10 (46mm)": {"devices": _without_available(DEVICES, WATCH)},
            "XcodeGen cannot be installed": {"fail": ("brew",)},
        }
        for name, options in cases.items():
            with _case(name):
                run = self._replay(patch_b64="", **options)

                self.assertTrue(run.job_failed, run.describe())
                self.assertEqual(run.result_files(), [], run.describe())
                devices = options.get("devices", DEVICES)
                available = {d["udid"] for entries in devices.values() for d in entries if d["isAvailable"]}
                expected = {"AICaddie": IOS_UDID, "AICaddieWatch": WATCH_UDID}
                for call in run.scheme_runs():
                    scheme = _option(call["args"], "-scheme") or ""
                    udid = _destination(_option(call["args"], "-destination")).get("id")
                    self.assertEqual(udid, expected.get(scheme), call)
                    self.assertIn(udid, available, call)

    def test_result_that_cannot_be_judged_uploads_no_result(self) -> None:
        # G3 G4: a Test Case whose result is not exactly Passed / Failed / Skipped / Expected Failure, in
        # either scheme, a Test Case without any usable id, or a test id that occurs twice (across the
        # schemes or within one, whatever the statuses), fails closed, also when the other scheme left no
        # result: the writer exits non-zero, the job fails, no result.json is uploaded.
        unknown = _tree("AICaddie", IOS_CASES, ("Passed", "unknown", "Passed", "Passed", "Passed"), IOS_DEVICE)
        missing = _tree("AICaddie", IOS_CASES, ("Passed", None, "Passed", "Passed", "Passed"), IOS_DEVICE)
        mixed = _tree("AICaddie", IOS_CASES, ("Passed", "Mixed", "Passed", "Passed", "Passed"), IOS_DEVICE)
        lowercase = _tree("AICaddie", IOS_CASES, ("Passed", "passed", "Passed", "Passed", "Passed"), IOS_DEVICE)
        # The failed iOS case has neither nodeIdentifier nor name: dropping it would hide the failure.
        anonymous = _without_identifier(IOS_FAILED_ONCE, IOS_CASES[2][2], nameless=True)
        watch_unknown = _tree("AICaddieWatch", WATCH_CASES, ("Passed", "Passed", "unknown"), WATCH_DEVICE)
        # The Watch tree also passes the iOS test StartRoundDiscoveryTests/testPreselectedTee….
        passed_again = _tree("AICaddieWatch", (*WATCH_CASES, IOS_CASES[2]), ("Passed",) * 4, WATCH_DEVICE)
        # The iOS tree lists StartRoundDiscoveryTests/testOpeningPage… twice.
        ios_twice = _tree("AICaddie", (*IOS_CASES, IOS_CASES[1]), ("Passed",) * 6, IOS_DEVICE)
        cases = {
            "unknown result": (_scheme(65, tree=unknown), PASSING_WATCH),
            "missing result": (_scheme(65, tree=missing), PASSING_WATCH),
            "result Mixed": (_scheme(65, tree=mixed), PASSING_WATCH),
            "result in lower case": (_scheme(0, tree=lowercase), PASSING_WATCH),
            "a failed Test Case without nodeIdentifier or name": (_scheme(65, tree=anonymous), PASSING_WATCH),
            "unknown result in the Watch scheme": (PASSING_IOS, _scheme(65, tree=watch_unknown)),
            "unknown Watch result after the iOS scheme left no result bundle": (
                _scheme(65, bundle=False),
                _scheme(65, tree=watch_unknown),
            ),
            "one test id in both schemes, failed and passed": (
                _scheme(65, tree=IOS_FAILED_ONCE),
                _scheme(0, tree=passed_again),
            ),
            "one test id in both schemes, passed twice": (PASSING_IOS, _scheme(0, tree=passed_again)),
            "one test id twice in the iOS scheme": (_scheme(0, tree=ios_twice), PASSING_WATCH),
            "one test id twice in the iOS scheme, and the Watch scheme left no result bundle": (
                _scheme(0, tree=ios_twice),
                _scheme(65, bundle=False),
            ),
        }
        for name, (ios, watch) in cases.items():
            with _case(name):
                run = self._replay(patch_b64=MUTANT_PATCH, ios=ios, watch=watch)

                self.assertTrue(run.job_failed, run.describe())
                self.assertEqual(run.result_files(), [], run.describe())
                self.assertTrue(
                    [step for step in run.writer_steps() if step["outcome"] == "failure"],
                    f"the writer must exit non-zero\n{run.describe()}",
                )

    # G3 — a cancelled run judges nothing

    def test_cancelled_run_uploads_no_result(self) -> None:
        # G3: a run cancelled while the iOS scheme tests, or right after the writer has written a
        # result, judges nothing: no later step runs (not the other scheme, the writer or the upload) and
        # no result.json is uploaded.
        cases = {
            "cancelled while the iOS scheme tests": {"ios": _scheme(0, tree=IOS_PASSING, cancel=True)},
            "cancelled right after the writer": {"cancel_after_writer": True},
        }
        for name, options in cases.items():
            with _case(name):
                run = self._replay(patch_b64=MUTANT_PATCH, **options)

                self.assertTrue(run.cancelled, f"the run was not cancelled\n{run.describe()}")
                if options.get("cancel_after_writer"):
                    self.assertTrue(
                        [step for step in run.writer_steps() if step["outcome"] == "success"],
                        f"the writer must have written a result before the cancellation\n{run.describe()}",
                    )
                later = [step["name"] for step in run.steps[run.cancel_index + 1 :] if step["ran"]]
                self.assertEqual(later, [], f"no step runs after a cancellation\n{run.describe()}")
                self.assertEqual(run.result_files(), [], run.describe())


if __name__ == "__main__":
    unittest.main()
