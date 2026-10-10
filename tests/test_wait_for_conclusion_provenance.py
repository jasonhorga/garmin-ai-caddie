"""Own CI stays quiet; manual release/Apple outcomes and other agents' CI are delivered.

PR #383 review (2026-10-06): `--feedback` returned the finished live Native 37426762320 and
TestFlight 37438559636 again, both on `codex/internal-release-3614bf6f-20261006` with a
`Generated-by: Codex` head, because the self-generated filter only looked at `main`.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

WAITER = Path("ops/wait_for_conclusion.sh").resolve()

CODEX_SHA = "a" * 40
CLAUDE_SHA = "b" * 40
UNMARKED_DOCS_SHA = "c" * 40
MAIN_BOOKKEEPING_SHA = "d" * 40

COMMITS = {
    CODEX_SHA: {"message": "release: pin internal candidate\n\nGenerated-by: Codex", "files": ["ops/x.sh"]},
    CLAUDE_SHA: {
        "message": "docs: note\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
        "files": ["docs/a.md"],
    },
    UNMARKED_DOCS_SHA: {"message": "docs: owner note", "files": ["docs/b.md"]},
    MAIN_BOOKKEEPING_SHA: {"message": "ops: record state", "files": ["docs/operations/PROJECT_STATE.md"]},
}

FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
fixtures = json.load(open(os.environ["FAKE_GH_FIXTURES"]))
args = sys.argv[1:]
if args[:1] == ["api"]:
    sha = args[1].rsplit("/", 1)[-1]
    commit = fixtures["commits"].get(sha)
    if commit is None:
        sys.exit(1)
    print(json.dumps({
        "author": {"login": "jasonhorga"}, "committer": {"login": "jasonhorga"},
        "commit": {"message": commit["message"],
                   "author": {"email": "owner@example.invalid"}, "committer": {"email": "owner@example.invalid"}},
        "files": [{"filename": name} for name in commit["files"]],
    }))
elif args[:2] == ["run", "watch"]:
    sys.exit(0)
elif args[:2] == ["run", "view"]:
    run = fixtures["runs"][args[2]]
    if "--log" in args:
        print("log for run", args[2])
    else:
        print(json.dumps({"status": "completed", "conclusion": run["conclusion"],
                          "url": "https://example.invalid/run/" + args[2],
                          "headBranch": run["headBranch"], "headSha": run["headSha"],
                          "workflowName": run.get("workflowName", "CI"),
                          "event": run.get("event", "push"),
                          "jobs": run.get("jobs", [])}))
else:
    sys.exit(3)
"""

RUNS = {
    "101": {"headBranch": "codex/internal-release-3614bf6f-20261006", "headSha": CODEX_SHA, "conclusion": "success"},
    "102": {"headBranch": "claude/some-fix", "headSha": CLAUDE_SHA, "conclusion": "success"},
    "103": {"headBranch": "owner/docs", "headSha": UNMARKED_DOCS_SHA, "conclusion": "success"},
    "104": {"headBranch": "main", "headSha": MAIN_BOOKKEEPING_SHA, "conclusion": "success"},
    "105": {"headBranch": "codex/fix-pr-7", "headSha": CODEX_SHA, "conclusion": "failure"},
    "106": {
        "headBranch": "main", "headSha": CODEX_SHA, "conclusion": "failure",
        "workflowName": "iOS TestFlight (CD)", "event": "workflow_dispatch",
        "jobs": [{"name": "testflight", "conclusion": "failure"}],
    },
    "107": {
        "headBranch": "main", "headSha": MAIN_BOOKKEEPING_SHA, "conclusion": "success",
        "workflowName": "iOS TestFlight Testers", "event": "workflow_dispatch",
    },
    "108": {
        "headBranch": "main", "headSha": CODEX_SHA, "conclusion": "success",
        "workflowName": "Native Mobile CI", "event": "workflow_dispatch",
    },
    "109": {
        "headBranch": "main", "headSha": CODEX_SHA, "conclusion": "success",
        "workflowName": "iOS TestFlight (CD)", "event": "push",
    },
    "110": {
        "headBranch": "codex/internal-release-3614bf6f-20261006", "headSha": CODEX_SHA,
        "conclusion": "success", "workflowName": "iOS TestFlight (CD)", "event": "workflow_dispatch",
    },
    "111": {
        "headBranch": "main", "headSha": CODEX_SHA, "conclusion": "success",
        "workflowName": "iOS TestFlight Artifact Diagnostics", "event": "workflow_dispatch",
    },
}


def run_event(run_id: str, prs: list[int] | None = None) -> dict:
    run = RUNS[run_id]
    return {"kind": "ci_run_changed", "runId": run_id, "status": "completed", "conclusion": run["conclusion"],
            "headBranch": run["headBranch"], "headSha": run["headSha"], "pullRequests": prs or []}


@unittest.skipUnless(shutil.which("jq") and shutil.which("bash"), "needs bash and jq")
class WaitForConclusionProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="wait-provenance-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(FAKE_GH, encoding="utf-8")
        gh.chmod(0o755)
        fixtures = self.tmp / "fixtures.json"
        fixtures.write_text(json.dumps({"commits": COMMITS, "runs": RUNS}), encoding="utf-8")
        self.events = self.tmp / "events.jsonl"
        self.cursor = self.tmp / "cursor"
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_GH_FIXTURES": str(fixtures),
            "WAIT_REPO": "owner/repo",
            "WAIT_DATA_ROOT": str(self.tmp / "data"),
            "WAIT_EVENT_FILE": str(self.events),
            "WAIT_CURSOR_FILE": str(self.cursor),
            "WAIT_SELF_COMMIT_LOGIN": "jasonhorga",
            "WAIT_SELF_COMMIT_EMAIL": "owner@example.invalid",
        }

    def _write_events(self, *events: dict) -> None:
        self.events.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")

    def _feedback(self) -> str:
        self.cursor.write_text("0\n", encoding="utf-8")
        result = subprocess.run(
            ["bash", str(WAITER), "--feedback", "--poll-seconds", "1", "--timeout-seconds", "5"],
            env=self.env, capture_output=True, text=True, timeout=60,
        )
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1, result.stdout)
        return lines[0]

    def test_manual_release_and_apple_outcomes_survive_self_head_filtering(self) -> None:
        for run_id in ("106", "107", "110", "111"):
            with self.subTest(run=run_id):
                self._write_events(run_event(run_id), {"kind": "issue_comment", "pr": 7, "id": 9})

                line = self._feedback()

                self.assertIn(f"status=completed conclusion={RUNS[run_id]['conclusion']}", line)
                self.assertIn("failed_jobs=testflight" if run_id == "106" else "failed_jobs=none", line)
                self.assertEqual(self.cursor.read_text(encoding="utf-8").strip(), "1")
                log = Path(line.rsplit("log=", 1)[1]).read_text(encoding="utf-8")
                self.assertIn("keeping manual release/Apple outcome", log)
                self.assertIn(f"log for run {run_id}", log)

    def test_manual_native_ci_and_non_dispatch_release_ci_stay_quiet(self) -> None:
        for run_id in ("104", "108", "109"):
            with self.subTest(run=run_id):
                self._write_events(run_event(run_id), {"kind": "issue_comment", "pr": 7, "id": 10})

                line = self._feedback()

                self.assertIn("conclusion=pr_feedback:issue_comment:pr7", line)
                self.assertEqual(self.cursor.read_text(encoding="utf-8").strip(), "2")

    def test_stream_cannot_claim_a_release_exception_for_ordinary_ci(self) -> None:
        event = {**run_event("101"), "workflowName": "iOS TestFlight (CD)", "event": "workflow_dispatch"}
        self._write_events(event, {"kind": "issue_comment", "pr": 7, "id": 11})

        self.assertIn("conclusion=pr_feedback:issue_comment:pr7", self._feedback())

    def test_manual_release_does_not_wake_before_terminal_event(self) -> None:
        event = {**run_event("106"), "status": "in_progress", "conclusion": ""}
        self._write_events(event, {"kind": "issue_comment", "pr": 7, "id": 12})

        self.assertIn("conclusion=pr_feedback:issue_comment:pr7", self._feedback())

    def test_check_summary_keeps_manual_apple_outcome_on_bookkeeping_head(self) -> None:
        self._write_events(run_event("104"), checks_event(7, "107", "SUCCESS"),
                           {"kind": "issue_comment", "pr": 7, "id": 13})

        line = self._feedback()

        self.assertIn("status=completed conclusion=ci_checks_terminal failed_jobs=none", line)
        self.assertEqual(self.cursor.read_text(encoding="utf-8").strip(), "2")

    def test_explicit_release_wait_reports_failed_testflight(self) -> None:
        result = subprocess.run(
            ["bash", str(WAITER), "--release", "106", "--poll-seconds", "1"],
            env=self.env, capture_output=True, text=True, timeout=60,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(result.stdout.strip().splitlines()), 1)
        self.assertIn("status=completed conclusion=failure failed_jobs=testflight", result.stdout)

    def test_feedback_skips_codex_ci_on_an_internal_release_branch(self) -> None:
        comment = {"kind": "issue_comment", "pr": 7, "id": 1}
        self._write_events(run_event("101"), comment)

        line = self._feedback()

        self.assertIn("conclusion=pr_feedback:issue_comment:pr7", line)
        self.assertEqual(self.cursor.read_text(encoding="utf-8").strip(), "2")
        log = Path(line.rsplit("log=", 1)[1]).read_text(encoding="utf-8")
        self.assertIn("ignored self-generated CI event run=101 branch=codex/internal-release", log)

    def test_feedback_skips_codex_ci_on_a_pr_branch_even_when_red(self) -> None:
        self._write_events(run_event("105", prs=[7]), {"kind": "issue_comment", "pr": 7, "id": 2})

        self.assertIn("conclusion=pr_feedback:issue_comment:pr7", self._feedback())

    def test_claude_and_unmarked_branch_ci_still_wake_the_loop(self) -> None:
        for run_id in ("102", "103"):
            with self.subTest(run=run_id):
                self._write_events(run_event(run_id, prs=[9]), {"kind": "issue_comment", "pr": 9, "id": 3})

                line = self._feedback()

                self.assertIn("status=completed conclusion=success", line)
                self.assertEqual(self.cursor.read_text(encoding="utf-8").strip(), "1")

    def test_main_bookkeeping_rule_is_unchanged(self) -> None:
        self._write_events(run_event("104"), {"kind": "issue_comment", "pr": 9, "id": 4})

        self.assertIn("conclusion=pr_feedback:issue_comment:pr9", self._feedback())

    def test_explicit_run_wait_still_reports_codex_own_run(self) -> None:
        for run_id, expected in (("101", "status=completed conclusion=success"),
                                 ("105", "status=completed conclusion=failure")):
            with self.subTest(run=run_id):
                result = subprocess.run(
                    ["bash", str(WAITER), "--run", run_id, "--poll-seconds", "1"],
                    env=self.env, capture_output=True, text=True, timeout=60,
                )
                self.assertIn(expected, result.stdout)

    def test_pr_wait_skips_codex_ci_and_returns_the_next_pr_event(self) -> None:
        self.events.write_text("", encoding="utf-8")
        waiter = subprocess.Popen(
            ["bash", str(WAITER), "--pr", "7", "--poll-seconds", "1", "--timeout-seconds", "10"],
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        time.sleep(1.5)
        with self.events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(run_event("105", prs=[7])) + "\n")
            handle.write(json.dumps({"kind": "issue_comment", "pr": 7, "id": 5}) + "\n")
        stdout, _stderr = waiter.communicate(timeout=30)

        self.assertIn("conclusion=pr_feedback:issue_comment:pr7", stdout)

    # PR #388 review: the monitor emits both the Actions run event and the PR check summary
    # (`ci_changed`, which has no head of its own — only each check's run link).

    def test_feedback_skips_the_run_and_check_summary_of_codex_ci_then_returns_feedback(self) -> None:
        self._write_events(
            run_event("105", prs=[7]),
            checks_event(7, "105", "FAILURE"),
            {"kind": "issue_comment", "pr": 7, "id": 6},
        )

        line = self._feedback()

        self.assertIn("conclusion=pr_feedback:issue_comment:pr7", line)
        self.assertEqual(self.cursor.read_text(encoding="utf-8").strip(), "3")
        log = Path(line.rsplit("log=", 1)[1]).read_text(encoding="utf-8")
        self.assertIn("ignored self-generated check summary pr=7", log)

    def test_pr_wait_skips_the_codex_check_summary_too(self) -> None:
        self.events.write_text("", encoding="utf-8")
        waiter = subprocess.Popen(
            ["bash", str(WAITER), "--pr", "7", "--poll-seconds", "1", "--timeout-seconds", "10"],
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        time.sleep(1.5)
        with self.events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(run_event("105", prs=[7])) + "\n")
            handle.write(json.dumps(checks_event(7, "105", "FAILURE")) + "\n")
            handle.write(json.dumps({"kind": "issue_comment", "pr": 7, "id": 7}) + "\n")
        stdout, _stderr = waiter.communicate(timeout=30)

        self.assertIn("conclusion=pr_feedback:issue_comment:pr7", stdout)

    def test_check_summaries_not_proven_codex_still_wake(self) -> None:
        cases = {
            "claude run": checks_event(9, "102", "FAILURE"),
            "check without an Actions link": {
                "kind": "ci_changed", "pr": 9,
                "checks": [{"name": "external", "state": "FAILURE", "link": "https://status.example.invalid/1"}],
            },
            "codex and claude runs": {
                "kind": "ci_changed", "pr": 9,
                "checks": checks_event(9, "105", "FAILURE")["checks"] + checks_event(9, "102", "SUCCESS")["checks"],
            },
        }
        for name, summary in cases.items():
            with self.subTest(name):
                self._write_events(summary, {"kind": "issue_comment", "pr": 9, "id": 8})

                line = self._feedback()

                self.assertIn("status=completed conclusion=ci_checks_terminal", line)
                self.assertEqual(self.cursor.read_text(encoding="utf-8").strip(), "1")


def checks_event(pr: int, run_id: str, state: str) -> dict:
    return {
        "kind": "ci_changed",
        "pr": pr,
        "checks": [{
            "name": "native-mobile",
            "state": state,
            "link": f"https://github.com/owner/repo/actions/runs/{run_id}/job/{run_id}01",
        }],
    }


if __name__ == "__main__":
    unittest.main()
