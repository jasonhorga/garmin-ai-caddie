#!/usr/bin/env python3
"""Write the native mutant verdict defined by .agent/contracts/card-440.md."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


STATUS_MAP = {
    "Passed": "passed",
    "Expected Failure": "passed",
    "Failed": "failed",
    "Skipped": "skipped",
}


class UnusableResult(ValueError):
    """A scheme did not produce a readable test tree with test cases."""


class InvalidTestResult(ValueError):
    """A verdict cannot safely represent the reported test cases."""


def test_cases(tree: object) -> list[dict[str, str]]:
    """Extract cases, preserving bundle identity and ignoring per-device children."""
    if not isinstance(tree, dict) or not isinstance(tree.get("testNodes"), list):
        raise UnusableResult("Missing testNodes")
    cases: list[dict[str, str]] = []

    def visit(node: object, bundle: str = "", suite: str = "") -> None:
        if not isinstance(node, dict):
            raise UnusableResult("Malformed test node")
        kind = node.get("nodeType")
        if kind in ("Unit test bundle", "UI test bundle"):
            bundle = node.get("name", "")
            suite = ""
        elif kind == "Test Suite":
            suite = node.get("name", "")
        elif kind == "Test Case":
            result = node.get("result")
            if not isinstance(result, str) or result not in STATUS_MAP:
                raise InvalidTestResult("Unrecognised or missing Test Case result")
            identifier = node.get("nodeIdentifier")
            if identifier is None:
                name = node.get("name")
                if not isinstance(suite, str) or not suite or not isinstance(name, str) or not name:
                    raise InvalidTestResult("Test Case has no usable identifier")
                identifier = f"{suite}/{name}"
            if not isinstance(bundle, str) or not bundle or not isinstance(identifier, str) or not identifier:
                raise InvalidTestResult("Test Case has no usable bundle or identifier")
            cases.append({"id": f"{bundle}/{identifier}", "status": STATUS_MAP[result]})
            return
        children = node.get("children", [])
        if not isinstance(children, list):
            raise UnusableResult("Malformed test children")
        for child in children:
            visit(child, bundle, suite)

    for node in tree["testNodes"]:
        visit(node)
    if not cases:
        raise UnusableResult("No Test Case nodes")
    return cases


def read_bundle(path: Path) -> list[dict[str, str]]:
    if not path.is_dir():
        raise UnusableResult("Missing result bundle")
    try:
        process = subprocess.run(
            ["xcrun", "xcresulttool", "get", "test-results", "tests", "--path", str(path)],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        tree = json.loads(process.stdout)
    except (OSError, subprocess.SubprocessError, UnicodeError, json.JSONDecodeError) as exc:
        raise UnusableResult("Unreadable result bundle") from exc
    return test_cases(tree)


def verdict(request_id: str, head_sha: str, apply_outcome: str, bundles: list[Path]) -> dict:
    result = {"request_id": request_id, "head_sha": head_sha, "status": "apply_failed", "tests": []}
    if apply_outcome == "failure":
        return result
    cases: list[dict[str, str]] = []
    unusable = False
    for bundle in bundles:
        try:
            cases.extend(read_bundle(bundle))
        except UnusableResult:
            # Still inspect the other scheme: unknown statuses always fail closed.
            unusable = True
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise InvalidTestResult("Duplicate Test Case identifiers")
    result["status"] = "build_failed" if unusable else "tested"
    result["tests"] = cases
    return result


def agenthub_result(
    request_id: str,
    head_sha: str,
    patch: Path,
    stage: str,
    bundles: list[Path],
) -> dict:
    """Build the five-key result object consumed by agenthub's native reader."""
    try:
        patch_bytes = patch.read_bytes()
    except OSError:
        patch_bytes = b""
    result = {
        "request_id": request_id,
        "head": head_sha,
        "patch_sha256": hashlib.sha256(patch_bytes).hexdigest(),
        "stage": stage,
        "tests": [],
    }
    if stage != "tested":
        return result
    cases: list[dict[str, str]] = []
    unusable = False
    for bundle in bundles:
        try:
            cases.extend(read_bundle(bundle))
        except UnusableResult:
            unusable = True
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise InvalidTestResult("Duplicate Test Case identifiers")
    if unusable:
        result["stage"] = "build_failed"
        return result
    result["tests"] = cases
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--head", dest="head")
    parser.add_argument("--head-sha", dest="head_sha")
    parser.add_argument("--patch", type=Path)
    parser.add_argument("--stage", choices=("tested", "apply_failed", "build_failed"))
    parser.add_argument("--apply-outcome", choices=("success", "failure"))
    parser.add_argument("--ios-result", type=Path)
    parser.add_argument("--watch-result", type=Path)
    parser.add_argument("--out", "--output", dest="output", required=True, type=Path)
    args = parser.parse_args()
    head = args.head or args.head_sha
    if not head:
        parser.error("one of --head or --head-sha is required")
    stage = args.stage
    if stage is None:
        if args.apply_outcome is None or args.ios_result is None or args.watch_result is None:
            parser.error("--stage or the legacy result arguments are required")
        stage = "apply_failed" if args.apply_outcome == "failure" else "tested"
    patch = args.patch or Path("")
    bundles = [path for path in (args.ios_result, args.watch_result) if path is not None]

    # A failed invocation must never leave a previous verdict available to upload.
    args.output.unlink(missing_ok=True)
    try:
        result = agenthub_result(args.request_id, head, patch, stage, bundles)
    except InvalidTestResult as exc:
        print(f"Cannot judge native tests: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)
    finally:
        temporary.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
