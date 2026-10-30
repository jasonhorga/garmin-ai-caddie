#!/usr/bin/env python3
"""Apply and run the product fault corpus in disposable worktrees.

The fault patches are intentionally kept outside the product history.  This tool never applies a
patch to the caller's checkout: every check and mutant run gets its own detached worktree.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import sys
import re
from collections import defaultdict
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "tests/product/faults/manifest.json"
# Host-specific runners come from the environment; defaults work in any checkout.
RUN_TESTS = os.environ.get("CADDIE_RUNTESTS", "")
SHARED_PYTHON = Path(os.environ.get("CADDIE_SHARED_PYTHON", sys.executable))
# Injectable batch budget; isolated retries retain their own full load budget.
PYTHON_BATCH_TIMEOUT = 60.0


# Use a result file: imported test modules may write arbitrary stdout/stderr.
# Inspect unittest's objects and loader errors, never its formatted console output.
PYTHON_LOAD_PROBE = r'''
import json
from pathlib import Path
import sys
import traceback
import unittest

def failed_tests(test):
    if isinstance(test, unittest.loader._FailedTest):
        return True
    if isinstance(test, unittest.TestSuite):
        return any(failed_tests(child) for child in test)
    return False

reports = {}
baseline_path = list(sys.path)
previous_modules = set(sys.modules)
for target in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")):
    # Remove only the previous target's imports from paths it added. Normal
    # dependencies must stay cached: some C extensions cannot initialize twice.
    added_paths = [Path(entry).resolve() for entry in sys.path if entry not in baseline_path]
    if added_paths:
        for name in set(sys.modules) - previous_modules:
            module = sys.modules[name]
            spec = getattr(module, "__spec__", None)
            origin = getattr(spec, "origin", None) or getattr(module, "__file__", None)
            locations = list(getattr(spec, "submodule_search_locations", None) or [])
            if origin and origin not in {"built-in", "frozen"}:
                locations.append(origin)
            if any(Path(location).resolve().is_relative_to(directory)
                   for location in locations for directory in added_paths):
                del sys.modules[name]
    sys.path[:] = baseline_path
    previous_modules = set(sys.modules)
    try:
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName(target)
        count = suite.countTestCases()
        if loader.errors or failed_tests(suite):
            report = {"ok": False, "reason": "\n".join(loader.errors) or "unittest _FailedTest"}
        elif count == 0:
            report = {"ok": False, "reason": "0 tests loaded"}
        else:
            report = {"ok": True, "reason": ""}
    except (Exception, SystemExit):
        report = {"ok": False, "reason": traceback.format_exc()}
    reports[target] = report
Path(sys.argv[2]).write_text(json.dumps(reports), encoding="utf-8")
'''


def _run_python_load_probe(targets: list[str], repo: Path) -> dict[str, tuple[str, str]]:
    """Load a batch in one interpreter, returning a separate result per target."""
    env = {**os.environ, "AI_CADDIE_DATA_MODE": "fixture", "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        with tempfile.TemporaryDirectory(prefix="fault-load-") as directory:
            source = Path(directory) / "targets.json"
            output = Path(directory) / "load.json"
            source.write_text(json.dumps(targets), encoding="utf-8")
            timeout = PYTHON_BATCH_TIMEOUT if len(targets) > 1 else 60.0
            try:
                result = subprocess.run(
                    [str(SHARED_PYTHON), "-c", PYTHON_LOAD_PROBE, str(source), str(output)],
                    cwd=repo, env=env, text=True, capture_output=True, timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                if len(targets) > 1:
                    print(f"LOAD_PROBE_TIMEOUT timeout={timeout:g}s fallback_targets={len(targets)}",
                          file=sys.stderr)
                raise
            if result.returncode or not output.is_file():
                reason = f"load probe exited {result.returncode}: {result.stderr.strip()}"
            else:
                reports = json.loads(output.read_text(encoding="utf-8"))
                return {
                    target: ("ok", "") if reports[target]["ok"] else
                    ("unavailable", f"target 无法加载：{reports[target]['reason'][-5800:]}")
                    for target in targets
                }
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        reason = str(error)
    return {target: ("unavailable", f"target 无法加载：{reason[-5800:]}") for target in targets}


def probe_python_targets(targets: Iterable[str], repo: Path) -> dict[str, tuple[str, str]]:
    """Use one batch, retrying only failures without other modules' side effects."""
    targets = list(dict.fromkeys(targets))
    if not targets:
        return {}
    results = _run_python_load_probe(targets, repo)
    if len(targets) > 1:
        for target in targets:
            if results[target][0] != "ok":
                results[target] = _run_python_load_probe([target], repo)[target]
    return results


def target_check(record: dict[str, Any], repo: Path) -> tuple[str, str]:
    """Validate a target without executing tests or applying its fault patch."""
    kind, target = record["kind"], record["target"]
    if kind == "python":
        return probe_python_targets([target], repo)[target]
    if kind in {"native-unit", "native-ui"}:
        parts = target.split("/")
        if len(parts) != 3 or not all(re.fullmatch(r"\w+", part) for part in parts):
            return "unavailable", f"target 无法加载：invalid native target {target}"
        bundle, class_name, method = parts
        for source in (repo / "mobile/ios" / bundle).rglob("*.swift"):
            text = source.read_text(encoding="utf-8")
            if (re.search(rf"\bclass\s+{re.escape(class_name)}\b", text)
                    and re.search(rf"\bfunc\s+{re.escape(method)}\s*\(", text)):
                return "ok", ""
        return "unavailable", f"target 无法加载：Swift test class/method not found: {target}"
    return "ok", ""


def load_manifest() -> list[dict[str, Any]]:
    """Load the central records, then card fragments in directory-name order.

    Both forms use {"records": [...]} and repository-relative patch paths.
    Keep source paths during validation so collisions identify both authors.
    """
    manifests = [MANIFEST, *sorted(MANIFEST.parent.glob("*/manifest.json"), key=lambda path: path.parent.name)]
    records: list[dict[str, Any]] = []
    seen: dict[str, Path] = {}
    for manifest in manifests:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("records"), list):
            raise ValueError(f"{manifest}: manifest must contain a records array")
        for record in data["records"]:
            if not isinstance(record, dict):
                raise ValueError(f"{manifest}: manifest record must be an object: {record!r}")
            required = ("id", "patch", "kind", "target", "promise")
            missing = [key for key in required if not record.get(key)]
            if missing:
                raise ValueError(f"{manifest}: manifest record is missing {missing}: {record!r}")
            if record["id"] in seen:
                raise ValueError(
                    f"duplicate manifest id {record['id']!r}: {seen[record['id']]} and {manifest}"
                )
            seen[record["id"]] = manifest
            patch = ROOT / record["patch"]
            if not patch.is_file():
                raise ValueError(f"{manifest}: manifest patch does not exist: {record['patch']}")
            if record["kind"] not in {
                "python",
                "python-script",
                "web-vitest",
                "web-playwright",
                "native-unit",
                "native-ui",
            }:
                raise ValueError(f"{manifest}: unknown fault kind {record['kind']!r} for {record['id']}")
            records.append(record)
    return records


def run(*args: str, cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args), cwd=cwd, text=True, capture_output=True, check=check
    )


def make_worktree() -> tuple[Path, tempfile.TemporaryDirectory[str]]:
    holder = tempfile.TemporaryDirectory(prefix="caddie-fault-")
    path = Path(holder.name) / "repo"
    result = run("git", "worktree", "add", "--detach", "--quiet", str(path), "HEAD", cwd=ROOT)
    if result.returncode:
        holder.cleanup()
        raise RuntimeError(result.stderr.strip() or "git worktree add failed")
    return path, holder


def remove_worktree(path: Path, holder: tempfile.TemporaryDirectory[str]) -> None:
    run("git", "worktree", "remove", "--force", str(path), cwd=ROOT)
    holder.cleanup()


def patch_check(record: dict[str, Any], repo: Path) -> tuple[str, str]:
    if record.get("disabled"):
        return "disabled", str(record.get("reason", "disabled"))
    patch = ROOT / record["patch"]
    if record["kind"] == "python-script":
        return ("ok", "python source") if patch.is_file() else ("unappliable", "script missing")
    result = run("git", "apply", "--check", str(patch), cwd=repo)
    if result.returncode:
        return "unappliable", (result.stderr or result.stdout).strip()
    return "ok", ""


def check(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    records = list(records)
    rows: list[dict[str, Any]] = []
    worktree, holder = make_worktree()
    targets: dict[tuple[str, str], tuple[str, str]] = {}
    try:
        python_targets = [record["target"] for record in records
                          if record["kind"] == "python" and not record.get("disabled")]
        targets.update({("python", target): result
                        for target, result in probe_python_targets(python_targets, worktree).items()})
        for record in records:
            status, detail = patch_check(record, worktree)
            if status != "disabled":
                key = (record["kind"], record["target"])
                if key not in targets:
                    targets[key] = target_check(record, worktree)
                target_status, target_detail = targets[key]
                if target_status != "ok":
                    status, detail = target_status, target_detail + (f"\npatch: {detail}" if detail else "")
            rows.append({"id": record["id"], "kind": record["kind"], "status": status, "detail": detail})
    finally:
        remove_worktree(worktree, holder)
    print_results(rows, title="patch and target check")
    return {"mode": "check", "results": rows, "summary": summarize(rows)}


def apply_patch(record: dict[str, Any], repo: Path) -> tuple[bool, str]:
    patch = ROOT / record["patch"]
    if record["kind"] == "python-script":
        return True, "python source"
    result = run("git", "apply", "--whitespace=nowarn", str(patch), cwd=repo)
    if result.returncode:
        return False, (result.stderr or result.stdout).strip()
    return True, ""


def native_include_ui(record: dict[str, Any]) -> bool:
    """Whether a native dispatch must run the application-test scheme."""
    return record["target"].startswith("AICaddieUITests/")


def run_target(record: dict[str, Any], repo: Path) -> tuple[str, str, list[str]]:
    """Return (status, detail, command) for an already patched worktree."""
    kind = record["kind"]
    target = record["target"]
    env = {**os.environ, "AI_CADDIE_DATA_MODE": "fixture", "PYTHONDONTWRITEBYTECODE": "1"}
    if kind == "python-script":
        script = shlex.split(target)
        if script and script[0] in {"python", "python3"}:
            script = script[1:]
        command = [str(SHARED_PYTHON), *script]
        result = subprocess.run(command, cwd=repo, env=env, text=True, capture_output=True)
    elif kind == "python":
        if RUN_TESTS:
            command = ["bash", RUN_TESTS, str(repo), target]
        else:
            command = [str(SHARED_PYTHON), "-m", "unittest", target]
        result = subprocess.run(command, cwd=repo, env=env, text=True, capture_output=True)
    elif kind == "web-vitest":
        executable = repo / "web_v2/node_modules/.bin/vitest"
        if not executable.exists():
            return "unavailable", "web_v2/node_modules is absent", []
        command = ["npm", "run", "test", "--", "run", *shlex.split(target)]
        result = subprocess.run(command, cwd=repo / "web_v2", env=env, text=True, capture_output=True)
    elif kind == "web-playwright":
        executable = repo / "web_v2/node_modules/.bin/playwright"
        if not executable.exists():
            return "unavailable", "web_v2/node_modules is absent", []
        command = [
            "npm",
            "run",
            "test:e2e",
            "--",
            "e2e/product",
            "--project=desktop-chromium",
            "--grep",
            target,
        ]
        result = subprocess.run(command, cwd=repo / "web_v2", env=env, text=True, capture_output=True)
    else:
        return "native-pending", "native tests are dispatched by the project console", []
    if kind == "python" and result.returncode:
        # A non-zero test process may be a mutant assertion or a load failure.
        # Probe only this path so a zero exit is recorded as survived directly.
        status, detail = target_check(record, repo)
        if status != "ok":
            return status, detail, command
    output = (result.stdout + "\n" + result.stderr).strip()
    # Python unittest targets have passed structured loading checks before this
    # execution. Keep the assertion/error text for review of the actual test red.
    if kind == "python-script":
        # c16c_mutants.py is a harness: a successful N/N report means every mutation was
        # rejected by its green control, while a non-zero exit is a failed harness run.
        report = re.search(r"(\d+)/(\d+) killed", output)
        if report:
            status = "killed" if report.group(1) == report.group(2) else "leaked"
        else:
            status = "killed" if result.returncode else "leaked"
    else:
        status = "killed" if result.returncode else "leaked"
    return status, output[-6000:], command


def run_mutants(records: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if record.get("disabled"):
            rows.append({"id": record["id"], "kind": record["kind"], "status": "disabled", "detail": record.get("reason", "")})
            continue
        if record["kind"] in {"native-unit", "native-ui"}:
            rows.append({"id": record["id"], "kind": record["kind"], "status": "native-pending", "detail": "dispatch required"})
            continue
        worktree, holder = make_worktree()
        try:
            if record["kind"] == "python":
                status, detail = target_check(record, worktree)
                if status != "ok":
                    rows.append({"id": record["id"], "kind": record["kind"], "status": status, "detail": detail})
                    continue
            applied, detail = apply_patch(record, worktree)
            if not applied:
                rows.append({"id": record["id"], "kind": record["kind"], "status": "unappliable", "detail": detail})
                continue
            status, detail, command = run_target(record, worktree)
            rows.append({"id": record["id"], "kind": record["kind"], "status": status, "detail": detail, "command": command})
        finally:
            remove_worktree(worktree, holder)
    print_results(rows, title="mutant run")
    return {"mode": "run", "results": rows, "summary": summarize(rows)}


def dispatch_native(records: list[dict[str, Any]]) -> dict[str, Any]:
    head = run("git", "rev-parse", "HEAD", cwd=ROOT).stdout.strip()
    commands: list[dict[str, str]] = []
    for record in records:
        if record.get("disabled") or record["kind"] not in {"native-unit", "native-ui"}:
            continue
        patch_b64 = base64.b64encode((ROOT / record["patch"]).read_bytes()).decode("ascii")
        include_ui = "true" if native_include_ui(record) else "false"
        command = (
            "gh workflow run agenthub-native-mutant.yml "
            f"-f request_id=c58c-{record['id']} "
            f"-f head_sha={head} "
            f"-f patch_b64={patch_b64} "
            f"-f only_testing={shlex.quote(record['target'])} "
            f"-f include_ui={include_ui}"
        )
        print(command)
        commands.append({"id": record["id"], "command": command})
    return {"mode": "dispatch-native", "commands": commands}


def summarize(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        summary[row["kind"]][row["status"]] += 1
    return {kind: dict(counts) for kind, counts in sorted(summary.items())}


def print_results(rows: list[dict[str, Any]], title: str) -> None:
    print(f"\n{title}")
    print("kind                 killed leaked unappliable unavailable pending disabled ok")
    summary = summarize(rows)
    for kind, counts in summary.items():
        print(
            f"{kind:<20} {counts.get('killed', 0):>6} {counts.get('leaked', 0):>6}"
            f" {counts.get('unappliable', 0):>11} {counts.get('unavailable', 0):>11}"
            f" {counts.get('native-pending', 0):>7} {counts.get('disabled', 0):>8} {counts.get('ok', 0):>2}"
        )
    for row in rows:
        if row["status"] in {"unappliable", "leaked", "unavailable"}:
            print(f"{row['status'].upper()} {row['id']}: {row.get('detail', '')[:600]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--dispatch-native", action="store_true")
    parser.add_argument("--kind")
    parser.add_argument("--id")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    records = load_manifest()
    if args.kind == "python":
        records = [r for r in records if r["kind"] in {"python", "python-script"}]
    elif args.kind:
        records = [r for r in records if r["kind"] == args.kind]
    if args.id:
        records = [r for r in records if r["id"] == args.id]
    no_match = bool(args.id and not records)
    if no_match:
        print(f"NO_MATCH {args.id}")
        mode_name = "check" if args.check else "run" if args.run else "dispatch-native"
        result = {"mode": mode_name, "results": [], "summary": {}}
        if mode_name == "dispatch-native":
            result["commands"] = []
    elif args.check:
        result = check(records)
    elif args.run:
        result = run_mutants(records)
    else:
        result = dispatch_native(records)
    if args.out:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return int(no_match or any(row["status"] in {"unappliable", "unavailable", "leaked"}
                   for row in result.get("results", [])))


if __name__ == "__main__":
    raise SystemExit(main())
