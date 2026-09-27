"""Offline harness for ops/oneoff/2026-09-27-cleanup-remote-branches.sh.

Runs a copy of the script (snapshot constants swapped for a local fixture) against a
local bare "origin" and a stub `gh`, so no network is used. Covers the fail-closed
paths the PR #334 review asked for: base drift, open PR, tag conflict, branch drift,
and resuming from the action log.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "ops/oneoff/2026-09-27-cleanup-remote-branches.sh"
GH_STUB = """#!/usr/bin/env bash
case "$*" in
  *"--jq .default_branch"*) echo "${FAKE_DEFAULT:-integration/v2}" ;;
  "pr list"*) printf '%s\\n' ${FAKE_OPEN_HEADS:-} ;;
  *) echo "unexpected gh call: $*" >&2; exit 9 ;;
esac
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@unittest.skipUnless(shutil.which("bash") and shutil.which("git"), "needs bash and git")
class CleanupRemoteBranchesScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.origin = self.tmp / "jasonhorga/garmin-ai-caddie.git"
        self.origin.mkdir(parents=True)
        git(self.origin, "init", "--bare", "-q")

        seed = self.tmp / "seed"
        seed.mkdir()
        git(seed, "init", "-q")
        git(seed, "config", "user.email", "t@example.com")
        git(seed, "config", "user.name", "t")

        def commit(msg: str) -> str:
            git(seed, "commit", "-q", "--allow-empty", "-m", msg)
            return git(seed, "rev-parse", "HEAD")

        self.old_main = commit("old main")
        merged = commit("merged work")
        self.base = commit("base")
        git(seed, "checkout", "-q", "-b", "side", self.old_main)
        self.archive = commit("unmerged work")
        refs = {
            "integration/v2": self.base,
            "main": self.old_main,
            "done/merged": merged,
            "old/unmerged": self.archive,
            "claude/code-audit-performance-17wqcv": self.base,
            "someone/new-branch": self.base,
        }
        for name, sha in refs.items():
            git(seed, "push", "-q", str(self.origin), f"{sha}:refs/heads/{name}")
        git(seed, "tag", "archive/main-before-v2-integration-2026-05-28", self.old_main)
        git(seed, "push", "-q", str(self.origin), "--tags")
        git(self.origin, "symbolic-ref", "HEAD", "refs/heads/integration/v2")
        self.merged = merged

        self.work = self.tmp / "work"
        subprocess.run(
            ["git", "clone", "-q", str(self.origin), str(self.work)],
            check=True,
            capture_output=True,
        )

        text = SCRIPT.read_text()
        text = re.sub(r'BASE_SHA="[0-9a-f]+"', f'BASE_SHA="{self.base}"', text)
        text = re.sub(r'OLD_MAIN_SHA="[0-9a-f]+"', f'OLD_MAIN_SHA="{self.old_main}"', text)
        text = re.sub(
            r"(ARCHIVE_SNAPSHOT=\$\(cat <<'LIST'\n).*?(\nLIST\n\))",
            lambda m: f"{m.group(1)}old/unmerged {self.archive}{m.group(2)}",
            text,
            flags=re.S,
        )
        text = re.sub(
            r"(MERGED_SNAPSHOT=\$\(cat <<'LIST'\n).*?(\nLIST\n\))",
            lambda m: f"{m.group(1)}done/merged {merged}{m.group(2)}",
            text,
            flags=re.S,
        )
        self.script = self.tmp / "cleanup.sh"
        self.script.write_text(text)

        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(GH_STUB)
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        self.env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
        self.log = self.tmp / "actions.log"

    def run_script(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.script), "--log", str(self.log), *args],
            cwd=self.work,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            timeout=60,
        )

    def origin_refs(self) -> dict[str, str]:
        out = git(self.origin, "for-each-ref", "--format=%(refname) %(objectname)")
        return dict(line.split(" ", 1) for line in out.splitlines()) if out else {}

    def assert_untouched(self, before: dict[str, str]) -> None:
        self.assertEqual(before, self.origin_refs())
        self.assertFalse(self.log.exists() and self.log.read_text().strip())

    def test_dry_run_changes_nothing(self) -> None:
        before = self.origin_refs()
        res = self.run_script()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("DRY RUN", res.stdout)
        self.assertIn("not in snapshot, left untouched: someone/new-branch", res.stdout)
        self.assert_untouched(before)

    def test_execute_archives_deletes_and_rerun_is_idempotent(self) -> None:
        res = self.run_script("--execute")
        self.assertEqual(res.returncode, 0, res.stderr)
        refs = self.origin_refs()
        self.assertEqual(refs.get("refs/tags/archive/old/unmerged"), self.archive)
        for gone in ("old/unmerged", "done/merged", "main"):
            self.assertNotIn(f"refs/heads/{gone}", refs)
        for kept in ("integration/v2", "claude/code-audit-performance-17wqcv", "someone/new-branch"):
            self.assertIn(f"refs/heads/{kept}", refs)
        self.assertIn(f"deleted done/merged {self.merged}", self.log.read_text())

        again = self.run_script("--execute")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(refs, self.origin_refs())

    def test_resume_from_log_after_partial_run(self) -> None:
        git(self.origin, "update-ref", "-d", "refs/heads/done/merged")
        before = self.origin_refs()
        res = self.run_script()
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("target missing on origin and not in the log: done/merged", res.stderr)
        self.assert_untouched(before)

        self.log.write_text(f"deleted done/merged {self.merged}\n")
        res = self.run_script("--execute")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("refs/heads/old/unmerged", self.origin_refs())

    def test_base_drift_aborts(self) -> None:
        git(self.origin, "update-ref", "refs/heads/integration/v2", self.old_main)
        before = self.origin_refs()
        res = self.run_script("--execute")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("regenerate the lists", res.stderr)
        self.assert_untouched(before)

    def test_wrong_default_branch_aborts(self) -> None:
        before = self.origin_refs()
        res = self.run_script("--execute", FAKE_DEFAULT="main")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("default branch is main", res.stderr)
        self.assert_untouched(before)

    def test_open_pr_on_target_aborts(self) -> None:
        before = self.origin_refs()
        res = self.run_script("--execute", FAKE_OPEN_HEADS="done/merged")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("target has an open PR: done/merged", res.stderr)
        self.assert_untouched(before)

    def test_branch_drift_aborts(self) -> None:
        git(self.origin, "update-ref", "refs/heads/done/merged", self.base)
        before = self.origin_refs()
        res = self.run_script("--execute")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("target moved: done/merged", res.stderr)
        self.assert_untouched(before)

    def test_conflicting_archive_tag_aborts(self) -> None:
        git(self.origin, "update-ref", "refs/tags/archive/old/unmerged", self.base)
        before = self.origin_refs()
        res = self.run_script("--execute")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn(f"archive/old/unmerged exists at {self.base}", res.stderr)
        self.assert_untouched(before)


if __name__ == "__main__":
    unittest.main()
