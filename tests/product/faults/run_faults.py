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


def load_manifest() -> list[dict[str, Any]]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError("manifest must contain a records array")
    records = data["records"]
    seen: set[str] = set()
    for record in records:
        required = ("id", "patch", "kind", "target", "promise")
        missing = [key for key in required if not record.get(key)]
        if missing:
            raise ValueError(f"manifest record is missing {missing}: {record!r}")
        if record["id"] in seen:
            raise ValueError(f"duplicate manifest id: {record['id']}")
        seen.add(record["id"])
        patch = ROOT / record["patch"]
        if not patch.is_file():
            raise ValueError(f"manifest patch does not exist: {record['patch']}")
        if record["kind"] not in {
            "python",
            "python-script",
            "web-vitest",
            "web-playwright",
            "native-unit",
            "native-ui",
        }:
            raise ValueError(f"unknown fault kind {record['kind']!r} for {record['id']}")
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
    rows: list[dict[str, Any]] = []
    worktree, holder = make_worktree()
    try:
        for record in records:
            status, detail = patch_check(record, worktree)
            rows.append({"id": record["id"], "kind": record["kind"], "status": status, "detail": detail})
    finally:
        remove_worktree(worktree, holder)
    print_results(rows, title="patch check")
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
        if not SHARED_PYTHON.exists():
            return "unavailable", f"shared Python not found: {SHARED_PYTHON}", []
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
    output = (result.stdout + "\n" + result.stderr).strip()
    # A mutant is killed when the selected test exits non-zero.  The runner deliberately leaves
    # the assertion text in the JSON so a console reviewer can distinguish a semantic red from a
    # collection/import failure.
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
        if row["status"] in {"unappliable", "leaked"}:
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
    if args.check:
        result = check(records)
    elif args.run:
        result = run_mutants(records)
    else:
        result = dispatch_native(records)
    if args.out:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
