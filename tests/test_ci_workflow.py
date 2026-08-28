from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


class CIWorkflowTests(unittest.TestCase):
    def test_ci_workflow_runs_backend_frontend_and_visual_smoke(self) -> None:
        workflow = Path(".github/workflows/ci.yml")
        self.assertTrue(workflow.exists(), "missing CI workflow")
        text = workflow.read_text(encoding="utf-8")

        for required in [
            "uv sync",
            "uv run python -m unittest discover -s tests -v",
            "uv run python -m py_compile",
            "node-version: 24",
            "npm ci",
            "npm test -- --run",
            "npm run lint",
            "npm run build",
            "npx playwright install --with-deps chromium",
            "npm run test:e2e",
            "ops/smoke_private_trial.sh",
            "AI_CADDIE_DATA_MODE: fixture",
            "AI_CADDIE_SECURITY_PROFILE: private",
            "AI_CADDIE_ADMIN_TOKEN:",
        ]:
            self.assertIn(required, text)

    def test_backend_unit_tests_run_without_private_admin_middleware(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
        backend = workflow["jobs"]["backend"]
        steps = {step.get("name"): step for step in backend["steps"]}

        self.assertEqual({"AI_CADDIE_DATA_MODE": "fixture"}, backend["env"])
        self.assertNotIn("AI_CADDIE_SECURITY_PROFILE", steps["Run backend tests"].get("env", {}))
        self.assertNotIn("AI_CADDIE_ADMIN_TOKEN", steps["Run backend tests"].get("env", {}))
        self.assertEqual("private", steps["Start fixture API"]["env"]["AI_CADDIE_SECURITY_PROFILE"])
        self.assertEqual("ci-admin-token", steps["Start fixture API"]["env"]["AI_CADDIE_ADMIN_TOKEN"])
        self.assertEqual("private", steps["Private trial smoke"]["env"]["AI_CADDIE_SECURITY_PROFILE"])
        self.assertEqual("ci-admin-token", steps["Private trial smoke"]["env"]["AI_CADDIE_ADMIN_TOKEN"])

    def test_ci_workflow_avoids_duplicate_feature_branch_push_runs(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
        triggers = workflow[True]

        self.assertIn("workflow_dispatch", triggers)
        self.assertIn("pull_request", triggers)
        self.assertEqual(
            triggers["push"]["branches"],
            ["main", "integration/v2"],
            "push CI must protect integration branches without duplicating feature-branch PR runs",
        )

    def test_canonical_authority_check_propagates_git_diff_failures(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
        steps = {step.get("name"): step for step in workflow["jobs"]["backend"]["steps"]}
        run_lines = steps["Check canonical contract authority"]["run"].splitlines()

        self.assertEqual(
            [
                "set -euo pipefail",
                'git diff --no-renames --name-only -z "$AUTHORITY_RANGE" | uv run python tools/contracts/check_authority.py',
            ],
            run_lines,
        )

    def test_canonical_authority_uses_one_full_history_checkout_and_exact_ranges(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
        backend_steps = workflow["jobs"]["backend"]["steps"]
        checkout_steps = [
            step for step in backend_steps if step.get("uses") == "actions/checkout@v4"
        ]
        self.assertEqual(1, len(checkout_steps))
        self.assertEqual(0, checkout_steps[0]["with"]["fetch-depth"])

        steps = {step.get("name"): step for step in backend_steps}
        resolver = steps["Resolve canonical authority diff base"]
        self.assertEqual("canonical-authority-base", resolver["id"])
        self.assertEqual(
            {
                "EVENT_NAME": "${{ github.event_name }}",
                "PR_BASE_SHA": "${{ github.event.pull_request.base.sha }}",
                "PUSH_BEFORE_SHA": "${{ github.event.before }}",
            },
            resolver["env"],
        )
        self.assertEqual(
            [
                "set -euo pipefail",
                'if [[ "$EVENT_NAME" == "pull_request" || "$EVENT_NAME" == "pull_request_target" ]]; then',
                '  test -n "$PR_BASE_SHA"',
                '  echo "range=${PR_BASE_SHA}...HEAD" >> "$GITHUB_OUTPUT"',
                'elif [[ "$EVENT_NAME" == "push" && -n "$PUSH_BEFORE_SHA" && "$PUSH_BEFORE_SHA" != "0000000000000000000000000000000000000000" ]]; then',
                '  echo "range=${PUSH_BEFORE_SHA}..HEAD" >> "$GITHUB_OUTPUT"',
                "else",
                "  git rev-parse HEAD^ >/dev/null",
                '  echo "range=HEAD^..HEAD" >> "$GITHUB_OUTPUT"',
                "fi",
            ],
            resolver["run"].splitlines(),
        )

    def test_canonical_authority_range_resolver_executes_event_semantics(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
        steps = {
            step.get("name"): step for step in workflow["jobs"]["backend"]["steps"]
        }
        script = steps["Resolve canonical authority diff base"]["run"]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            for index in (1, 2):
                (root / "tracked.txt").write_text(f"{index}\n", encoding="utf-8")
                subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
                subprocess.run(
                    [
                        "git", "-c", "user.name=CI Test", "-c",
                        "user.email=ci@example.invalid", "commit", "-qm", f"commit {index}",
                    ],
                    cwd=root, check=True,
                )
            base = subprocess.run(
                ["git", "rev-parse", "HEAD^"], cwd=root, check=True,
                capture_output=True, text=True,
            ).stdout.strip()

            scenarios = (
                ("pull_request", base, "", f"range={base}...HEAD"),
                ("pull_request_target", base, "", f"range={base}...HEAD"),
                ("push", "", base, f"range={base}..HEAD"),
                ("push", "", "0" * 40, "range=HEAD^..HEAD"),
                ("workflow_dispatch", "", "", "range=HEAD^..HEAD"),
            )
            for index, (event, pr_base, push_before, expected) in enumerate(scenarios):
                with self.subTest(event=event, push_before=push_before):
                    output = root / f"github-output-{index}"
                    env = {
                        **os.environ,
                        "EVENT_NAME": event,
                        "PR_BASE_SHA": pr_base,
                        "PUSH_BEFORE_SHA": push_before,
                        "GITHUB_OUTPUT": str(output),
                    }
                    result = subprocess.run(
                        ["bash", "-c", script], cwd=root, env=env,
                        capture_output=True, text=True,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(expected, output.read_text(encoding="utf-8").strip())

            missing_pr_base = subprocess.run(
                ["bash", "-c", script], cwd=root,
                env={
                    **os.environ,
                    "EVENT_NAME": "pull_request",
                    "PR_BASE_SHA": "",
                    "PUSH_BEFORE_SHA": "",
                    "GITHUB_OUTPUT": str(root / "missing-pr-output"),
                },
                capture_output=True, text=True,
            )
            self.assertNotEqual(0, missing_pr_base.returncode)

    def test_canonical_authority_invalid_diff_range_fails_the_exact_ci_step(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
        steps = {
            step.get("name"): step for step in workflow["jobs"]["backend"]["steps"]
        }
        script = steps["Check canonical contract authority"]["run"]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
            subprocess.run(
                [
                    "git", "-c", "user.name=CI Test", "-c",
                    "user.email=ci@example.invalid", "commit", "-qm", "initial",
                ],
                cwd=root, check=True,
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            uv = bin_dir / "uv"
            uv.write_text("#!/bin/sh\ncat >/dev/null\nexit 0\n", encoding="utf-8")
            uv.chmod(0o755)

            result = subprocess.run(
                ["bash", "-c", script], cwd=root,
                env={
                    **os.environ,
                    "AUTHORITY_RANGE": "definitely-missing-ref..HEAD",
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                },
                capture_output=True, text=True,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("definitely-missing-ref..HEAD", result.stderr)

    def test_canonical_authority_step_rejects_source_rename_outside_generated_pattern(
        self,
    ) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
        steps = {
            step.get("name"): step for step in workflow["jobs"]["backend"]["steps"]
        }
        script = steps["Check canonical contract authority"]["run"]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "diff.renames", "true"], cwd=root, check=True
            )
            (root / "contracts/canonical").mkdir(parents=True)
            (root / "generated").mkdir()
            (root / "tools/contracts").mkdir(parents=True)
            (root / "contracts/canonical/authority.json").write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-contract-authority-v1",
                        "authoritativeInputs": [],
                        "evidenceInputs": [],
                        "canonicalRoots": ["contracts/canonical"],
                        "legacyAdapters": [],
                        "forbiddenSymbols": [],
                        "generatedGroups": [
                            {
                                "name": "generated-contracts",
                                "sources": ["contracts/canonical/**/*.schema.json"],
                                "outputs": ["generated/contracts.py"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            source = "contracts/canonical/source.schema.json"
            destination = "archive/source.schema.json"
            (root / source).write_text('{"type":"object"}\n', encoding="utf-8")
            (root / "generated/contracts.py").write_text(
                "GENERATED = True\n", encoding="utf-8"
            )
            (root / "tools/contracts/check_authority.py").write_text(
                Path("tools/contracts/check_authority.py").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                [
                    "git", "-c", "user.name=CI Test", "-c",
                    "user.email=ci@example.invalid", "commit", "-qm", "initial",
                ],
                cwd=root,
                check=True,
            )
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            (root / "archive").mkdir()
            subprocess.run(["git", "mv", source, destination], cwd=root, check=True)
            subprocess.run(
                [
                    "git", "-c", "user.name=CI Test", "-c",
                    "user.email=ci@example.invalid", "commit", "-qm", "rename source",
                ],
                cwd=root,
                check=True,
            )
            authority_range = f"{base}..HEAD"
            detected = subprocess.run(
                ["git", "diff", "--name-only", "-z", authority_range],
                cwd=root,
                check=True,
                capture_output=True,
            )
            self.assertEqual(destination.encode() + b"\0", detected.stdout)

            bin_dir = root / "bin"
            bin_dir.mkdir()
            uv = bin_dir / "uv"
            uv.write_text(
                "#!/bin/sh\n"
                "set -eu\n"
                'test "$1" = run\n'
                'test "$2" = python\n'
                "shift 2\n"
                'exec "$CI_TEST_PYTHON" "$@"\n',
                encoding="utf-8",
            )
            uv.chmod(0o755)
            result = subprocess.run(
                ["bash", "-c", script],
                cwd=root,
                env={
                    **os.environ,
                    "AUTHORITY_RANGE": authority_range,
                    "CI_TEST_PYTHON": sys.executable,
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                },
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, result.returncode, result.stderr)
            self.assertIn(
                "generated group generated-contracts changed a source without an owned output",
                result.stderr,
            )

    def test_private_trial_smoke_can_send_admin_token_header(self) -> None:
        script = Path("ops/smoke_private_trial.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn("AI_CADDIE_ADMIN_TOKEN", text)
        self.assertIn("X-AI-Caddie-Admin-Token", text)
        self.assertIn("/api/v2/mobile/rounds/900001/package", text)

    def test_private_trial_smoke_gives_readiness_cold_start_a_longer_timeout(self) -> None:
        script = Path("ops/smoke_private_trial.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn("AI_CADDIE_SMOKE_TIMEOUT_SECONDS", text)
        self.assertIn("AI_CADDIE_SMOKE_READINESS_TIMEOUT_SECONDS", text)
        self.assertIn('("/api/v2/readiness", False, READINESS_TIMEOUT_SECONDS)', text)
        self.assertIn("timeout=timeout_s or DEFAULT_REQUEST_TIMEOUT_SECONDS", text)

    def test_private_trial_smoke_exercises_media_roundtrip_and_redaction(self) -> None:
        script = Path("ops/smoke_private_trial.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn("/api/v2/media/target/round/900001", text)
        self.assertIn('"POST",\n    "/api/v2/media"', text)
        self.assertIn('"contentBase64"', text)
        self.assertIn('"/api/v2/media/{media_id}/analyze"', text)
        self.assertIn('"/api/v2/media/findings/{finding_id}/confirmation"', text)
        self.assertIn('"/api/v2/media/{media_id}/redact"', text)
        self.assertIn('"privacyState") != "redacted"', text)

    def test_private_trial_smoke_uses_admin_token_for_protected_history_reads(self) -> None:
        script = Path("ops/smoke_private_trial.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn('("/api/v2/history/overview", True, None)', text)

    def test_private_trial_smoke_rejects_private_paths_and_assignment_secrets(self) -> None:
        script = Path("ops/smoke_private_trial.sh")
        text = script.read_text(encoding="utf-8")

        for forbidden_probe in ['"password="', '"secret="', '"/home/"', '"/users/"', '".garmin_tokens"']:
            self.assertIn(forbidden_probe, text)

    def test_private_trial_smoke_writes_secret_free_evidence_file(self) -> None:
        text = Path("ops/smoke_private_trial.sh").read_text(encoding="utf-8")

        self.assertIn("AI_CADDIE_PRIVATE_SMOKE_EVIDENCE", text)
        self.assertIn("ai-caddie-private-trial-smoke-evidence-v1", text)
        self.assertIn("secretFree", text)
        self.assertIn("endpointCount", text)
        self.assertIn("adminProtectedEndpointCount", text)

    def test_backup_script_records_latest_manifest(self) -> None:
        script = Path("ops/backup_data.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn("ops/export_snapshot.py", text)
        self.assertIn("latest.json", text)
        self.assertIn("ai-caddie-backup-manifest-v1", text)
        self.assertIn("sizeBytes", text)
        self.assertIn("createdAt", text)

    def test_codex_runs_audit_inventories_nested_worktree_venvs(self) -> None:
        script = Path("ops/audit_homeserver_codex_runs.sh")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            run_a = runs / "run-a"
            run_b = runs / "run-b"
            (run_a / ".venv").mkdir(parents=True)
            (run_a / ".claude" / "worktrees" / "one" / ".venv").mkdir(parents=True)
            (run_a / ".claude" / "worktrees" / "two" / "nested" / ".venv").mkdir(
                parents=True
            )
            (run_a / ".claude" / "worktrees" / "one" / ".venv" / "marker").write_bytes(
                b"one-venv"
            )
            (run_a / ".claude" / "worktrees" / "two" / "nested" / ".venv" / "marker").write_bytes(
                b"two-venv-marker"
            )
            (run_a / ".claude" / "worktrees" / "two" / "source.txt").write_text(
                "source", encoding="utf-8"
            )
            (run_b / ".venv").mkdir(parents=True)

            manifest_root = root / "manifests"
            result = subprocess.run(
                ["bash", str(script)],
                env={
                    **os.environ,
                    "AICADDIE_CODEX_RUNS": str(runs),
                    "AICADDIE_MANIFEST_ROOT": str(manifest_root),
                    "AICADDIE_MANIFEST_STAMP": "test-stamp",
                },
                check=True,
                capture_output=True,
                text=True,
            )

            output = Path(result.stdout.strip())
            with (output / "runs.tsv").open(newline="", encoding="utf-8") as handle:
                rows = {row["name"]: row for row in csv.DictReader(handle, delimiter="\t")}

            metric_fields = {
                "nested_venv_count",
                "nested_venv_bytes",
                "nested_worktree_count",
                "nested_claude_bytes",
            }
            self.assertTrue(metric_fields.issubset(rows["run-a"]))
            self.assertEqual(rows["run-a"]["nested_venv_count"], "2")
            self.assertEqual(rows["run-a"]["nested_worktree_count"], "2")
            nested_venv_bytes = sum(
                int(
                    subprocess.run(
                        ["du", "--bytes", "--summarize", str(path)],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.split()[0]
                )
                for path in (
                    run_a / ".claude" / "worktrees" / "one" / ".venv",
                    run_a / ".claude" / "worktrees" / "two" / "nested" / ".venv",
                )
            )
            claude_bytes = int(
                subprocess.run(
                    ["du", "--bytes", "--summarize", str(run_a / ".claude")],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.split()[0]
            )
            self.assertEqual(rows["run-a"]["nested_venv_bytes"], str(nested_venv_bytes))
            self.assertEqual(rows["run-a"]["nested_claude_bytes"], str(claude_bytes))
            self.assertEqual(rows["run-b"]["nested_venv_count"], "0")
            self.assertEqual(rows["run-b"]["nested_venv_bytes"], "0")
            self.assertEqual(rows["run-b"]["nested_worktree_count"], "0")
            self.assertEqual(rows["run-b"]["nested_claude_bytes"], "0")

            self.assertTrue((run_a / ".claude" / "worktrees" / "one" / ".venv").exists())

    def test_frontend_lint_ignores_generated_playwright_artifacts(self) -> None:
        config = Path("web_v2/eslint.config.js").read_text(encoding="utf-8")

        self.assertIn("playwright-report", config)
        self.assertIn("test-results", config)

    def test_visual_smoke_has_explicit_timeout_budget_for_loaded_ci_hosts(self) -> None:
        config = Path("web_v2/playwright.config.ts").read_text(encoding="utf-8")

        self.assertIn("timeout: 60_000", config)

    def test_ci_workflow_keeps_expensive_native_validation_out_of_general_ci(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
        self.assertNotIn("native-mobile", workflow["jobs"])

    def test_native_mobile_workflow_runs_ios_and_watch_validation_on_macos_only_for_native_changes(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/native-mobile.yml").read_text(encoding="utf-8"))
        triggers = workflow[True]
        native = workflow["jobs"]["native-mobile"]

        self.assertIn("workflow_dispatch", triggers)
        self.assertIn("fixture_mode", triggers["workflow_dispatch"]["inputs"])
        self.assertFalse(triggers["workflow_dispatch"]["inputs"]["fixture_mode"]["default"])
        self.assertNotIn("push", triggers)
        paths = triggers["pull_request"]["paths"]
        self.assertIn("mobile/ios/**", paths)
        self.assertIn("Package.swift", paths)
        self.assertIn(".github/workflows/native-mobile.yml", paths)
        self.assertNotIn("ai_caddie/**", paths)

        self.assertEqual("macos-15", native["runs-on"])
        self.assertEqual("platform=iOS Simulator,name=iPhone 16,OS=latest", native["env"]["IOS_DESTINATION"])
        self.assertEqual(
            "platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest",
            native["env"]["WATCH_DESTINATION"],
        )

        steps = {step.get("name"): step for step in native["steps"]}
        self.assertIn("Start isolated CI fixture", steps)
        self.assertEqual("brew install uv", steps["Install uv for isolated CI fixture"]["run"])
        self.assertIn("inputs.fixture_mode", steps["Install uv for isolated CI fixture"]["if"])
        self.assertEqual("start_fixture", steps["Start isolated CI fixture"]["id"])
        fixture_start = steps["Start isolated CI fixture"]["run"]
        self.assertIn("openssl rand -hex 32", fixture_start)
        self.assertIn("command -v openssl", fixture_start)
        self.assertIn('echo "::add-mask::$FIXTURE_TOKEN"', fixture_start)
        self.assertIn("AI_CADDIE_ADMIN_TOKEN=%s", fixture_start)
        self.assertIn("TEST_RUNNER_AI_CADDIE_ADMIN_TOKEN=%s", fixture_start)
        self.assertIn("ARTIFACT_ADMIN_TOKEN=%s", fixture_start)
        self.assertIn("SIMCTL_CHILD_AI_CADDIE_ADMIN_TOKEN=%s", fixture_start)
        self.assertIn("SIMCTL_CHILD_AI_CADDIE_FIXTURE_MODE=1", fixture_start)
        self.assertIn("SIMCTL_CHILD_AI_CADDIE_DATA_MODE=fixture", fixture_start)
        self.assertIn("SIMCTL_CHILD_AI_CADDIE_API_BASE_URL=http://127.0.0.1:9000", fixture_start)
        self.assertIn('export AI_CADDIE_ADMIN_TOKEN="$FIXTURE_TOKEN"', fixture_start)
        self.assertNotIn("AI_CADDIE_CI_FIXTURE_ADMIN_TOKEN", fixture_start)
        self.assertIn("Configure live native auth", steps)
        self.assertIn("secrets.AI_CADDIE_ADMIN_TOKEN", steps["Configure live native auth"]["env"]["LIVE_ADMIN_TOKEN"])
        self.assertIn("command -v uv", fixture_start)
        self.assertIn("uv --version", fixture_start)
        self.assertIn("python3 --version", fixture_start)
        self.assertIn("nohup bash ops/run_ci_fixture.sh", fixture_start)
        self.assertIn("Upload fixture startup diagnostics", steps)
        self.assertIn("Validate native launch environment", steps)
        self.assertIn("Validate native launch environment (app target)", steps)
        launch_validation = steps["Validate native launch environment"]["run"]
        self.assertIn("token_len", launch_validation)
        self.assertIn("SIMCTL_CHILD_AI_CADDIE_FIXTURE_MODE", launch_validation)
        self.assertIn("SIMCTL_CHILD_AI_CADDIE_ADMIN_TOKEN", launch_validation)
        self.assertIn("fixture-startup-diagnostics", steps["Upload fixture startup diagnostics artifact"]["with"]["name"])
        self.assertIn("[REDACTED]", steps["Upload fixture startup diagnostics"]["run"])
        self.assertEqual("brew install xcodegen", steps["Install XcodeGen"]["run"])
        self.assertEqual(
            "xcodegen generate --spec mobile/ios/project.yml --project-root .",
            steps["Generate native project"]["run"],
        )
        self.assertIn("xcrun simctl list devices available", steps["Show simulator inventory"]["run"])

        ios_test = steps["Test iOS app target"]["run"]
        self.assertIn("xcodebuild test", ios_test)
        self.assertIn("-project mobile/ios/AICaddieNative.xcodeproj", ios_test)
        self.assertIn("-scheme AICaddie", ios_test)
        self.assertIn('-destination "$IOS_DESTINATION"', ios_test)
        for name in (
            "Test iOS app target",
            "Real-simulator screenshots (iOS, XCUITest against live backend)",
            "Collect design snapshots",
            "Scan design snapshots for secret bytes",
            "Scan real Native evidence for secret bytes",
            "Upload real screenshots",
            "Upload real video",
            "Scan native build evidence for secret bytes",
        ):
            self.assertIn("steps.start_fixture.outcome == 'success'", steps[name]["if"])
        for name in (
            "Test iOS app target",
            "Real-simulator screenshots (iOS, XCUITest against live backend)",
            "Collect design snapshots",
            "Scan design snapshots for secret bytes",
            "Collect real screenshots",
            "Scan real Native evidence for secret bytes",
            "Upload real screenshots",
            "Upload real video",
        ):
            self.assertIn("steps.validate_native_launch_prereq.outcome == 'success'", steps[name]["if"])
            self.assertIn("steps.validate_native_launch_environment_app.outcome == 'success'", steps[name]["if"])
            self.assertIn("steps.validate_native_launch_environment.outcome == 'success'", steps[name]["if"])

        watch_test = steps["Test Watch app target"]["run"]
        self.assertIn("xcodebuild test", watch_test)
        self.assertIn("-project mobile/ios/AICaddieNative.xcodeproj", watch_test)
        self.assertIn("-scheme AICaddieWatch", watch_test)
        self.assertIn('-destination "platform=watchOS Simulator,id=$NATIVE_WATCH_UDID"', watch_test)

        evidence_step = steps["Write native build evidence"]
        self.assertEqual(
            {
                "NATIVE_EVENT_NAME": "${{ github.event_name }}",
                "NATIVE_CAPTURE_SCOPE": "${{ github.event.inputs.capture_scope || 'full' }}",
                "IOS_TARGET_OUTCOME": "${{ steps.test_ios_app.outcome }}",
                "IOS_CAPTURE_OUTCOME": "${{ steps.real_ios_capture.outcome }}",
                "WATCH_TEST_OUTCOME": "${{ steps.test_watch_app.outcome }}",
                "FIXTURE_MODE": "${{ inputs.fixture_mode }}",
                "FIXTURE_START_OUTCOME": "${{ steps.start_fixture.outcome }}",
                "LAUNCH_VALIDATION_OUTCOME": "${{ steps.validate_native_launch_environment.outcome }}",
                "LAUNCH_PREREQ_OUTCOME": "${{ steps.validate_native_launch_prereq.outcome }}",
            },
            evidence_step["env"],
        )
        self.assertEqual("${{ inputs.fixture_mode }}", evidence_step["env"]["FIXTURE_MODE"])
        self.assertEqual("${{ steps.start_fixture.outcome }}", evidence_step["env"]["FIXTURE_START_OUTCOME"])
        self.assertEqual("${{ steps.validate_native_launch_environment.outcome }}", evidence_step["env"]["LAUNCH_VALIDATION_OUTCOME"])
        self.assertEqual("${{ steps.validate_native_launch_prereq.outcome }}", evidence_step["env"]["LAUNCH_PREREQ_OUTCOME"])
        evidence_run = evidence_step["run"]
        self.assertIn('FIXTURE_START_OUTCOME" != "success"', evidence_run)
        self.assertIn('ios_status="skipped"', evidence_run)
        self.assertIn('watch_status="skipped"', evidence_run)
        self.assertTrue(steps["Resolve and boot Watch test simulator"]["if"].startswith("${{ always()"))
        self.assertTrue(steps["Test Watch app target"]["if"].startswith("${{ always()"))
        self.assertTrue(steps["Real Watch round seed and restore screenshots"]["if"].startswith("${{ always()"))
        for name in (
            "Resolve and boot Watch test simulator",
            "Test Watch app target",
            "Collect Watch design snapshots",
            "Real Watch round seed and restore screenshots",
        ):
            self.assertIn("steps.start_fixture.outcome == 'success'", steps[name]["if"])
        self.assertIn("steps.test_ios_app.outcome == 'success'", steps["Verify SwiftJCS consumer boundaries"]["if"])
        for name in (
            "Resolve and boot Watch test simulator",
            "Test Watch app target",
            "Collect Watch design snapshots",
            "Scan Watch design snapshots for secret bytes",
            "Upload Watch design snapshots",
            "Real Watch round seed and restore screenshots",
            "Scan Watch runtime screenshots for secret bytes",
            "Upload watch real screenshots",
        ):
            self.assertIn("steps.validate_native_launch_environment.outcome == 'success'", steps[name]["if"])
            self.assertIn("steps.validate_native_launch_prereq.outcome == 'success'", steps[name]["if"])
        watch_runtime = steps["Real Watch round seed and restore screenshots"]["run"]
        self.assertIn('export SIMCTL_CHILD_AI_CADDIE_ADMIN_TOKEN="$AI_CADDIE_ADMIN_TOKEN"', watch_runtime)
        self.assertNotIn('SIMCTL_CHILD_AI_CADDIE_ADMIN_TOKEN=', watch_runtime.split('export SIMCTL_CHILD_AI_CADDIE_ADMIN_TOKEN=', 1)[1])
        self.assertEqual("test_ios_app", steps["Test iOS app target"]["id"])
        self.assertEqual("real_ios_capture", steps["Real-simulator screenshots (iOS, XCUITest against live backend)"]["id"])
        self.assertIn('watch_status="passed"', evidence_step["run"])
        self.assertIn('watch_status="skipped"', evidence_step["run"])
        self.assertIn('failure) echo "failed"', evidence_step["run"])
        self.assertIn('--ios-status "$ios_status"', evidence_step["run"])
        self.assertIn('failure) echo "failed"', evidence_step["run"])
        self.assertIn('cancelled|skipped|*) echo "skipped"', evidence_step["run"])
        self.assertIn(
            'python3 ops/write_native_build_evidence.py --ios-status "$ios_status" --watch-status "$watch_status"',
            evidence_step["run"],
        )

    def test_native_review_capture_scope_exits_normally_after_post_round_evidence(self) -> None:
        workflow_path = Path(".github/workflows/native-mobile.yml")
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        dispatch = workflow[True]["workflow_dispatch"] or {}
        inputs = dispatch.get("inputs", {})
        real_step = {
            step.get("name"): step for step in workflow["jobs"]["native-mobile"]["steps"]
        }["Real-simulator screenshots (iOS, XCUITest against live backend)"]
        real_flow = Path("mobile/ios/AICaddieUITests/RealFlowUITests.swift").read_text(
            encoding="utf-8"
        )
        for ui_test in ("RealFlowUITests.swift", "ReviewEditUITests.swift", "TeeSelectionUITests.swift"):
            harness = Path("mobile/ios/AICaddieUITests") / ui_test
            source = harness.read_text(encoding="utf-8")
            self.assertIn('app.launchEnvironment["AI_CADDIE_API_BASE_URL"]', source)
            self.assertIn('app.launchEnvironment["AI_CADDIE_ADMIN_TOKEN"]', source)
            self.assertIn('app.launchEnvironment["AI_CADDIE_FIXTURE_MODE"]', source)
            self.assertIn('app.launchEnvironment["AI_CADDIE_DATA_MODE"]', source)

        self.assertIn("capture_scope", inputs)
        self.assertEqual(["full", "review", "edit"], inputs["capture_scope"]["options"])
        self.assertEqual("full", inputs["capture_scope"]["default"])
        self.assertIn("api_base_url", inputs)
        self.assertFalse(inputs["api_base_url"]["required"])
        self.assertEqual("", inputs["api_base_url"]["default"])
        self.assertIn("backend_revision", inputs)
        self.assertFalse(inputs["backend_revision"]["required"])
        self.assertEqual("", inputs["backend_revision"]["default"])
        self.assertIn("require_live_preflight", inputs)
        self.assertEqual("boolean", inputs["require_live_preflight"]["type"])
        self.assertTrue(inputs["require_live_preflight"]["default"])
        self.assertIn("UITEST_CAPTURE_SCOPE", real_step["env"])
        self.assertIn("TEST_RUNNER_UITEST_CAPTURE_SCOPE", real_step["env"])
        self.assertIn('case "$UITEST_CAPTURE_SCOPE" in', real_step["run"])
        self.assertIn("review)", real_step["run"])
        self.assertIn("edit)", real_step["run"])
        self.assertIn(
            "-only-testing:AICaddieUITests/RealFlowUITests/testCaptureRealAppFlow",
            real_step["run"],
        )
        self.assertIn(
            "-only-testing:AICaddieUITests/ReviewEditUITests/testCaptureReviewEditFlow",
            real_step["run"],
        )
        review_exit = 'if cfg("UITEST_CAPTURE_SCOPE") == "review" { return }'
        self.assertIn(review_exit, real_flow)
        self.assertGreater(real_flow.index(review_exit), real_flow.index('save("05-last-round-review")'))
        self.assertLess(real_flow.index(review_exit), real_flow.index("// ---- Section 4:"))

    def test_native_journeys_preflight_real_course_discovery_before_launch(self) -> None:
        script_path = Path(".github/scripts/preflight_live_course_catalogue.py")
        self.assertTrue(script_path.is_file())
        script = script_path.read_text(encoding="utf-8")
        self.assertIn("/api/v2/health", script)
        self.assertIn("/api/v2/courses/nearby", script)
        self.assertIn("/api/v2/courses/search", script)
        self.assertIn("require_distance_order=True", script)

        native = yaml.safe_load(
            Path(".github/workflows/native-mobile.yml").read_text(encoding="utf-8")
        )["jobs"]["native-mobile"]["steps"]
        watch = yaml.safe_load(
            Path(".github/workflows/watch-runtime.yml").read_text(encoding="utf-8")
        )["jobs"]["watch-runtime"]["steps"]
        native_steps = {step.get("name"): step for step in native}
        watch_steps = {step.get("name"): step for step in watch}

        native_preflight = native_steps["Preflight live course discovery"]
        watch_preflight = watch_steps["Preflight live course discovery"]
        self.assertIn("inputs.require_live_preflight", native_preflight["if"])
        self.assertEqual("admin", native_preflight["env"]["AI_CADDIE_PREFLIGHT_AUTH_MODE"])
        self.assertEqual("bearer", watch_preflight["env"]["AI_CADDIE_PREFLIGHT_AUTH_MODE"])
        self.assertIn("AI_CADDIE_ADMIN_TOKEN", native_preflight["env"]["AI_CADDIE_PREFLIGHT_TOKEN"])
        self.assertIn("AI_CADDIE_CI_PLAYER_TOKEN", watch_preflight["env"]["AI_CADDIE_PREFLIGHT_TOKEN"])
        self.assertIn("github.event.inputs.backend_revision", native_preflight["env"]["AI_CADDIE_PREFLIGHT_EXPECTED_REVISION"])
        self.assertIn("vars.AI_CADDIE_BACKEND_REVISION", native_preflight["env"]["AI_CADDIE_PREFLIGHT_EXPECTED_REVISION"])
        self.assertNotIn("github.sha", native_preflight["env"]["AI_CADDIE_PREFLIGHT_EXPECTED_REVISION"])
        self.assertIn("github.event.inputs.backend_revision", watch_preflight["env"]["AI_CADDIE_PREFLIGHT_EXPECTED_REVISION"])
        self.assertIn("vars.AI_CADDIE_BACKEND_REVISION", watch_preflight["env"]["AI_CADDIE_PREFLIGHT_EXPECTED_REVISION"])
        self.assertNotIn("github.sha", watch_preflight["env"]["AI_CADDIE_PREFLIGHT_EXPECTED_REVISION"])
        self.assertEqual("${{ github.sha }}", native_preflight["env"]["AI_CADDIE_PREFLIGHT_APP_REVISION"])
        self.assertEqual("${{ github.sha }}", watch_preflight["env"]["AI_CADDIE_PREFLIGHT_APP_REVISION"])
        self.assertLess(
            list(native_steps).index("Preflight live course discovery"),
            list(native_steps).index("Real-simulator screenshots (iOS, XCUITest against live backend)"),
        )
        self.assertLess(
            list(watch_steps).index("Preflight live course discovery"),
            list(watch_steps).index("Seed and restore a real Watch round"),
        )

    def test_watch_runtime_uses_an_isolated_player_bearer_instead_of_the_owner_admin_token(self) -> None:
        workflow_path = Path(".github/workflows/watch-runtime.yml")
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        runtime = workflow["jobs"]["watch-runtime"]
        steps = {step.get("name"): step for step in runtime["steps"]}
        journey = steps["Seed and restore a real Watch round"]
        script = journey["run"]
        workflow_text = workflow_path.read_text(encoding="utf-8")

        self.assertIn("REAL_COURSE_PLAYER_TOKEN", journey["env"])
        self.assertEqual(
            "${{ secrets.AI_CADDIE_CI_PLAYER_TOKEN }}",
            journey["env"]["REAL_COURSE_PLAYER_TOKEN"],
        )
        self.assertNotIn("REAL_COURSE_ADMIN_TOKEN", journey["env"])
        self.assertIn("test -n \"$REAL_COURSE_PLAYER_TOKEN\"", script)
        self.assertIn("select(.isOwner == false)", script)
        self.assertIn("| .id", script)
        self.assertIn('select(type == "string" and length > 0 and . != "me")', script)
        self.assertIn(
            "SIMCTL_CHILD_AI_CADDIE_PLAYER_TOKEN=\"$REAL_COURSE_PLAYER_TOKEN\"",
            script,
        )
        self.assertIn(
            'if ! xcrun simctl privacy "$WATCH_UDID" grant location "$BID"; then',
            script,
        )
        self.assertIn("continuing to the runtime GPS gate", script)
        self.assertNotIn("SIMCTL_CHILD_AI_CADDIE_ADMIN_TOKEN", script)
        self.assertIn("secrets.AI_CADDIE_ADMIN_TOKEN", workflow_text)

    def test_watch_runtime_accepts_one_api_override_for_watch_and_web_evidence(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/watch-runtime.yml").read_text(encoding="utf-8"))
        dispatch_inputs = workflow[True]["workflow_dispatch"]["inputs"]
        watch_steps = {
            step.get("name"): step for step in workflow["jobs"]["watch-runtime"]["steps"]
        }
        journey = watch_steps["Seed and restore a real Watch round"]
        web = workflow["jobs"]["web-live-evidence"]
        expected = (
            "${{ github.event.inputs.api_base_url || vars.AI_CADDIE_API_BASE_URL "
            "|| 'https://caddie.taile36706.ts.net' }}"
        )

        self.assertIn("api_base_url", dispatch_inputs)
        self.assertFalse(dispatch_inputs["api_base_url"]["required"])
        self.assertEqual("", dispatch_inputs["api_base_url"]["default"])
        self.assertEqual(expected, journey["env"]["REAL_COURSE_API_BASE_URL"])
        self.assertEqual(expected, web["env"]["VITE_AI_CADDIE_API_BASE_URL"])

    def test_watch_runtime_rejects_a_placeholder_or_truncated_player_secret_before_launch(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/watch-runtime.yml").read_text(encoding="utf-8"))
        steps = {step.get("name"): step for step in workflow["jobs"]["watch-runtime"]["steps"]}
        script = steps["Seed and restore a real Watch round"]["run"]

        length_gate = 'test "${#REAL_COURSE_PLAYER_TOKEN}" -ge 32'
        placeholder_gate = 'test "$REAL_COURSE_PLAYER_TOKEN" != "-"'
        first_launch = "launch_and_capture standalone-course-seed"
        self.assertIn(length_gate, script)
        self.assertIn(placeholder_gate, script)
        self.assertLess(script.index(length_gate), script.index(first_launch))
        self.assertLess(script.index(placeholder_gate), script.index(first_launch))

    def test_watch_runtime_redacts_the_player_secret_from_every_diagnostic_artifact(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/watch-runtime.yml").read_text(encoding="utf-8"))
        steps = {step.get("name"): step for step in workflow["jobs"]["watch-runtime"]["steps"]}
        diagnostics = steps["Collect Watch runtime diagnostics"]
        script = diagnostics["run"]

        self.assertIn("env", diagnostics)
        self.assertEqual(
            "${{ secrets.AI_CADDIE_CI_PLAYER_TOKEN }}",
            diagnostics["env"]["REAL_COURSE_PLAYER_TOKEN"],
        )
        self.assertIn('sed "s|$REAL_COURSE_PLAYER_TOKEN|[REDACTED]|g"', script)
        self.assertNotIn("-exec cp {} watch-runtime-artifacts/diagnostics/", script)

    def test_watch_runtime_captures_full_device_approval_states(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/watch-runtime.yml").read_text(encoding="utf-8"))
        steps = {step.get("name"): step for step in workflow["jobs"]["watch-runtime"]["steps"]}
        script = steps["Seed and restore a real Watch round"]["run"]

        for mode in [
            "standalone-course-touch-target",
            "standalone-course-view-green",
            "real-course-map-measured",
            "real-course-view-green",
            "caddie-options",
            "score-total",
            "score-putts",
            "score-penalty",
            "scorecard",
            "hole-select",
        ]:
            self.assertIn(f"launch_and_capture {mode} ", script)

    def test_watch_runtime_uses_a_real_41mm_device_for_compact_scroll_surfaces(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/watch-runtime.yml").read_text(encoding="utf-8"))
        steps = {step.get("name"): step for step in workflow["jobs"]["watch-runtime"]["steps"]}
        compact = steps["Capture compact 41mm runtime boundaries"]["run"]
        snapshots = Path(
            "mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift"
        ).read_text(encoding="utf-8")

        self.assertIn("Apple Watch Series 9 (41mm)", compact)
        self.assertIn('= "352"', compact)
        self.assertIn('= "430"', compact)
        for mode in [
            "compact-holemap-long-copy",
            "compact-score-fairway",
            "compact-club-prompt",
            "compact-finish",
            "compact-home",
        ]:
            self.assertIn(f"capture_compact {mode} ", compact)
        self.assertNotIn('named: "watch-compact-club-prompt"', snapshots)
        self.assertNotIn('named: "watch-compact-finish"', snapshots)

    def test_watch_runtime_real_course_visual_scope_stops_before_score_writes_and_web(self) -> None:
        workflow = yaml.safe_load(Path(".github/workflows/watch-runtime.yml").read_text(encoding="utf-8"))
        scopes = workflow[True]["workflow_dispatch"]["inputs"]["runtime_scope"]["options"]
        runtime_steps = {
            step.get("name"): step for step in workflow["jobs"]["watch-runtime"]["steps"]
        }
        script = runtime_steps["Seed and restore a real Watch round"]["run"]

        self.assertIn("real-course-visual", scopes)
        visual_exit = 'if [[ "$WATCH_RUNTIME_SCOPE" == "real-course-visual" ]]; then'
        self.assertIn(visual_exit, script)
        self.assertLess(script.index("real-course-hazard-mid-map"), script.index(visual_exit))
        self.assertLess(script.index(visual_exit), script.index("real-course-journey-start"))

        web_condition = workflow["jobs"]["web-live-evidence"]["if"]
        self.assertIn("runtime_scope != 'setup-visual'", web_condition)
        self.assertIn("runtime_scope != 'real-course-visual'", web_condition)

    def test_watch_runtime_hands_the_isolated_round_to_png_only_web_evidence(self) -> None:
        workflow_path = Path(".github/workflows/watch-runtime.yml")
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        web = workflow["jobs"]["web-live-evidence"]
        steps = {step.get("name"): step for step in web["steps"]}

        self.assertEqual("watch-runtime", web["needs"])
        self.assertEqual("ubuntu-latest", web["runs-on"])
        self.assertEqual(
            "${{ secrets.AI_CADDIE_CI_PLAYER_TOKEN }}",
            web["env"]["AI_CADDIE_CI_PLAYER_TOKEN"],
        )
        self.assertIn("AI_CADDIE_ADMIN_TOKEN", json.dumps(web))

        capture = steps["Capture real Web player evidence"]
        self.assertEqual("web_v2", capture["working-directory"])
        self.assertIn("live-ci-player-evidence.spec.ts", capture["run"])
        self.assertIn("--config=playwright.live.config.ts", capture["run"])
        self.assertIn("--project=desktop-chromium", capture["run"])
        self.assertIn("--reporter=line", capture["run"])

        upload = steps["Upload real Web player evidence"]
        self.assertEqual("actions/upload-artifact@v4", upload["uses"])
        self.assertEqual("web-live-evidence", upload["with"]["name"])
        self.assertEqual(
            "web_v2/web-live-evidence/",
            upload["with"]["path"],
        )
        self.assertNotIn("test-results", json.dumps(upload))
        self.assertNotIn("playwright-report", json.dumps(upload))

    def test_real_web_player_evidence_scrubs_the_token_and_disables_debug_artifacts(self) -> None:
        spec_path = Path("web_v2/e2e/live-ci-player-evidence.spec.ts")
        self.assertTrue(spec_path.exists())
        text = spec_path.read_text(encoding="utf-8")

        self.assertIn("process.env.AI_CADDIE_CI_PLAYER_TOKEN", text)
        self.assertIn("test.skip(!playerToken", text)
        self.assertIn("trace: 'off'", text)
        self.assertIn("screenshot: 'off'", text)
        self.assertIn("video: 'off'", text)
        self.assertIn("window.history.replaceState", text)
        for filename in [
            "review-workbench.png",
            "rounds-list.png",
            "round-review.png",
        ]:
            self.assertIn(filename, text)
        # Runtime diagnostics may record only non-secret response facts. They deliberately reduce a
        # URL to its pathname before logging and must never print the capability, full URL, request
        # headers, or the temporary credential-bearing browser location.
        self.assertIn("const url = new URL(response.url())", text)
        self.assertIn("LIVE_EVIDENCE_OVERVIEW_RESPONSE", text)
        self.assertIn("response.request().method() === 'GET'", text)
        self.assertIn("overviewResponse.status()", text)
        self.assertIn("rounds-list-load-failure.png", text)
        self.assertIn("pathname: url.pathname", text)
        self.assertNotIn("console.log(playerToken", text)
        self.assertNotIn("console.log(response.url()", text)
        self.assertNotIn("console.log(request.url()", text)
        self.assertNotIn("console.log(credentialPath", text)

    def test_backend_fly_deploy_workflow_is_manual_secret_driven_and_runs_remote_preflight(self) -> None:
        workflow_path = Path(".github/workflows/backend-fly-deploy.yml")
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        text = workflow_path.read_text(encoding="utf-8")
        triggers = workflow[True]
        inputs = triggers["workflow_dispatch"]["inputs"]
        deploy = workflow["jobs"]["deploy"]

        self.assertIn("workflow_dispatch", triggers)
        self.assertNotIn("push", triggers)
        self.assertEqual({"contents": "read", "actions": "write"}, workflow["permissions"])
        self.assertIn("app_name", inputs)
        self.assertIn("fly_org", inputs)
        self.assertIn("api_base_url", inputs)
        self.assertIn("update_github_variable", inputs)
        self.assertIn("run_smoke", inputs)
        self.assertIn("run_phase6_preflight", inputs)
        self.assertEqual("ubuntu-latest", deploy["runs-on"])

        env = deploy["env"]
        self.assertEqual("${{ secrets.FLY_API_TOKEN }}", env["FLY_API_TOKEN"])
        self.assertEqual("${{ secrets.AI_CADDIE_ADMIN_TOKEN }}", env["AI_CADDIE_ADMIN_TOKEN"])
        self.assertIn("superfly/flyctl-actions/setup-flyctl@master", text)
        self.assertIn("flyctl apps create", text)
        self.assertIn('--org "$FLY_ORG"', text)
        self.assertIn("flyctl volumes create ai_caddie_private", text)
        self.assertIn("flyctl secrets set", text)
        self.assertIn('AI_CADDIE_BUILD_REVISION="$GITHUB_SHA"', text)
        self.assertIn("flyctl deploy --remote-only --config fly.toml", text)
        self.assertIn("AI_CADDIE_API_BASE_URL", text)
        self.assertIn("Content-Type: application/json", text)
        self.assertIn("/actions/variables", text)
        self.assertIn("ops/smoke_private_trial.sh", text)
        self.assertIn("ops/phase6_external_readiness.py", text)
        self.assertIn("--probe-backend", text)
        self.assertIn("actions/upload-artifact@v4", text)
        self.assertNotIn("replace-with-random-admin-token", text)
        self.assertNotIn("connect-csrf-token", text)

    def test_phase6_readiness_workflow_is_manual_and_uploads_evidence(self) -> None:
        workflow_path = Path(".github/workflows/phase6-readiness.yml")
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        text = workflow_path.read_text(encoding="utf-8")
        triggers = workflow[True]
        inputs = triggers["workflow_dispatch"]["inputs"]
        readiness = workflow["jobs"]["readiness"]

        self.assertIn("workflow_dispatch", triggers)
        self.assertNotIn("push", triggers)
        self.assertEqual({"contents": "read", "actions": "read"}, workflow["permissions"])
        for name in [
            "api_base_url",
            "probe_backend",
            "feedback_email_filled",
            "beta_review_ready",
            "beta_review_submitted",
            "native_runtime_api_configured",
            "assigned_tester_count",
            "tester_coverage_confirmed",
            "install_verified",
            "fail_when_incomplete",
        ]:
            self.assertIn(name, inputs)

        env = readiness["env"]
        self.assertEqual("${{ secrets.AI_CADDIE_ADMIN_TOKEN }}", env["AI_CADDIE_ADMIN_TOKEN"])
        self.assertIn("PHASE6_GH_TOKEN", env["GH_TOKEN"])
        self.assertIn("github.token", env["GH_TOKEN"])
        self.assertIn("ASC_KEY_ID", env["AI_CADDIE_SIGNING_SECRETS_CONFIGURED"])
        self.assertIn("MATCH_PASSWORD", env["AI_CADDIE_SIGNING_SECRETS_CONFIGURED"])
        self.assertIn("TESTFLIGHT_FEEDBACK_EMAIL", env["AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_SECRET_CONFIGURED"])
        self.assertEqual(
            "github_actions_env:required_signing_presence",
            env["AI_CADDIE_SIGNING_SECRETS_SOURCE"],
        )
        self.assertEqual(
            "github_actions_env:testflight_feedback_email_presence",
            env["AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_SECRET_SOURCE"],
        )
        self.assertIn("ops/phase6_external_readiness.py", text)
        self.assertIn("--probe-backend", text)
        self.assertIn("--feedback-email-filled", text)
        self.assertIn("--beta-review-submitted", text)
        self.assertIn("--install-verified", text)
        self.assertIn("--no-fail", text)
        self.assertIn("ops/roadmap_completion_status.py", text)
        self.assertIn("phase6_external_readiness_latest.json", text)
        self.assertIn("roadmap_completion_status.json", text)
        self.assertIn("actions/upload-artifact@v4", text)
        self.assertNotIn("replace-with-random-admin-token", text)
        self.assertNotIn("connect-csrf-token", text)

    def test_testflight_workflows_are_manual_only_and_secret_driven(self) -> None:
        for name in ["ios-signing-bootstrap.yml", "ios-testflight.yml", "ios-testflight-testers.yml"]:
            workflow_path = Path(".github/workflows") / name
            workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
            triggers = workflow[True]
            text = workflow_path.read_text(encoding="utf-8")

            self.assertIn("workflow_dispatch", triggers)
            self.assertNotIn("push", triggers)
            self.assertIn("secrets.", text)
            self.assertNotIn("secrets.MATCH_KEYCHAIN_PASSWORD", text)
            if name != "ios-testflight-testers.yml":
                self.assertIn("MATCH_GIT_PRIVATE_KEY", text)
            self.assertNotIn("AI_CADDIE_ADMIN_TOKEN=", text)

    def test_testflight_tester_workflow_lists_adds_and_distributes_without_hardcoded_emails(self) -> None:
        workflow_path = Path(".github/workflows/ios-testflight-testers.yml")
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        text = workflow_path.read_text(encoding="utf-8")
        setup_doc = Path("docs/ios-testflight-setup.md").read_text(encoding="utf-8")
        triggers = workflow[True]
        inputs = triggers["workflow_dispatch"]["inputs"]

        self.assertEqual(
            ["list", "add", "assign_existing", "configure_review", "submit_review", "distribute"],
            inputs["operation"]["options"],
        )
        self.assertIn("tester_emails", inputs)
        self.assertIn("groups", inputs)
        self.assertNotIn("feedback_email", inputs)
        self.assertIn("notify_external_testers", inputs)
        for obsolete_pilot_command in [
            "bundle exec fastlane pilot builds",
            "bundle exec fastlane pilot list",
            "bundle exec fastlane pilot add",
            "bundle exec fastlane pilot distribute",
        ]:
            self.assertNotIn(obsolete_pilot_command, text)
        self.assertIn("bundle exec ruby", text)
        self.assertIn("Spaceship::ConnectAPI::Build.all", text)
        self.assertIn('require "spaceship/connect_api/spaceship"', text)
        self.assertIn("internal_build_state", text)
        self.assertIn("external_build_state", text)
        self.assertNotIn("post_bulk_beta_tester_assignments", text)
        self.assertIn("post_beta_tester_assignment", text)
        self.assertIn("add_beta_tester_to_group", text)
        self.assertIn("create_tester_assignments!", text)
        self.assertIn("assign_existing_testers_to_groups!", text)
        self.assertIn("app.get_beta_testers(limit: 200)", text)
        self.assertIn('when "assign_existing"', text)
        self.assertIn('when "configure_review"', text)
        self.assertIn('when "submit_review"', text)
        self.assertIn("Beta App Review submission requested.", text)
        self.assertIn("print_beta_app_test_info(app)", text)
        self.assertIn("print_beta_app_review_detail(app)", text)
        self.assertIn("descriptionConfigured", text)
        self.assertIn("feedbackEmailConfigured", text)
        self.assertIn("contactFirstNameConfigured", text)
        self.assertIn("contactLastNameConfigured", text)
        self.assertIn("contactEmailConfigured", text)
        self.assertIn("contactPhoneConfigured", text)
        self.assertIn("tester_assignment_blocked?", text)
        self.assertIn("Tester assignment blocked for group", text)
        self.assertIn("build.add_beta_groups", text)
        self.assertIn("app.create_beta_group", text)
        self.assertIn("patch_build_beta_details", text)
        self.assertIn("DEFAULT_BETA_APP_DESCRIPTION", text)
        self.assertIn("DEFAULT_BETA_APP_REVIEW_NOTES", text)
        self.assertIn("TESTFLIGHT_FEEDBACK_EMAIL", text)
        self.assertIn("TESTFLIGHT_REVIEW_CONTACT_FIRST_NAME", text)
        self.assertIn("TESTFLIGHT_REVIEW_CONTACT_LAST_NAME", text)
        self.assertIn("TESTFLIGHT_REVIEW_CONTACT_PHONE", text)
        self.assertNotIn("BETA_FEEDBACK_EMAIL", text)
        self.assertIn("get_beta_app_localizations", text)
        self.assertIn("patch_beta_app_localizations", text)
        self.assertIn("post_beta_app_localizations", text)
        self.assertIn("get_beta_app_review_detail", text)
        self.assertIn("patch_beta_app_review_detail", text)
        self.assertIn("ensure_beta_app_review_detail!", text)
        self.assertIn("demoAccountRequired", text)
        self.assertIn("TESTFLIGHT_FEEDBACK_EMAIL or fill Beta App feedback email", text)
        self.assertIn("Beta App Review contact fields", text)
        self.assertIn("beta_metadata_pending?", text)
        self.assertIn("sleep 10", text)
        self.assertIn("uses_non_exempt_encryption: false", text)
        self.assertIn("usesNonExemptEncryption=false", setup_doc)
        self.assertIn("none of the algorithms listed above", setup_doc)
        self.assertIn("redact_email", text)
        self.assertIn('APP_IDENTIFIER = "com.ai-caddie.mobile"', text)
        self.assertIn("App.find(APP_IDENTIFIER)", text)
        self.assertIn("ASC_API_KEY_PATH", text)
        self.assertIn("ASC_PRIVATE_KEY", text)
        self.assertNotIn("@", inputs["tester_emails"]["default"])

    def test_testflight_fastfile_is_text_and_embeds_watch_target(self) -> None:
        fastfile = Path("fastlane/Fastfile")
        raw = fastfile.read_bytes()
        self.assertNotIn(b"\x00", raw)
        text = raw.decode("utf-8")
        self.assertIn("build_app(", text)
        self.assertIn("scheme: SCHEME", text)
        self.assertIn("Spaceship::ConnectAPI::BundleId.create", text)
        self.assertIn('require "securerandom"', text)
        self.assertIn("SecureRandom.hex(24)", text)
        self.assertIn('require "shellwords"', text)
        self.assertIn("AI_CADDIE_API_BASE_URL=#{Shellwords.escape(api_base_url)}", text)
        self.assertIn("AI_CADDIE_ADMIN_TOKEN", text)
        self.assertIn('ENV.fetch("UPLOAD_TO_TESTFLIGHT", "false") == "true"', text)
        self.assertIn('UI.success("Signed IPA built; TestFlight upload was not requested.")', text)
        self.assertNotIn("create_app_online", text)

        project = yaml.safe_load(Path("mobile/ios/project.yml").read_text(encoding="utf-8"))
        targets = project["schemes"]["AICaddie"]["build"]["targets"]
        self.assertIn("AICaddieWatch", targets)
        app_release = project["targets"]["AICaddie"]["settings"]["configs"]["Release"]
        watch_release = project["targets"]["AICaddieWatch"]["settings"]["configs"]["Release"]
        app_base = project["targets"]["AICaddie"]["settings"]["base"]
        self.assertEqual(app_base["AI_CADDIE_API_BASE_URL"], "")
        self.assertNotIn("AI_CADDIE_ADMIN_TOKEN", app_base)
        self.assertEqual(app_release["PROVISIONING_PROFILE_SPECIFIER"], "match AppStore com.ai-caddie.mobile")
        self.assertEqual(watch_release["PROVISIONING_PROFILE_SPECIFIER"], "match AppStore com.ai-caddie.mobile.watchkitapp")

        workflow = yaml.safe_load(Path(".github/workflows/ios-testflight.yml").read_text(encoding="utf-8"))
        inputs = workflow[True]["workflow_dispatch"]["inputs"]
        self.assertIn("api_base_url", inputs)
        self.assertIn("upload_to_testflight", inputs)
        self.assertFalse(inputs["upload_to_testflight"]["default"])
        workflow_text = Path(".github/workflows/ios-testflight.yml").read_text(encoding="utf-8")
        self.assertIn("vars.AI_CADDIE_API_BASE_URL", workflow_text)
        self.assertIn("UPLOAD_TO_TESTFLIGHT", workflow_text)
        self.assertIn("AI_CADDIE_ADMIN_TOKEN", workflow_text)

        info_plist = Path("mobile/ios/AICaddie/Info.plist").read_text(encoding="utf-8")
        self.assertNotIn("AICaddieAdminToken", info_plist)
        self.assertNotIn("AI_CADDIE_ADMIN_TOKEN", info_plist)

    def test_signing_bootstrap_syncs_release_entitlements_before_match(self) -> None:
        text = Path("fastlane/Fastfile").read_text(encoding="utf-8")

        self.assertIn("ensure_bundle_capabilities!", text)
        self.assertIn("BundleIdCapability::Type::APPLE_ID_AUTH", text)
        self.assertIn("BundleIdCapability::Type::HEALTHKIT", text)
        self.assertIn("bundle.create_capability", text)
        self.assertLess(
            text.index("ensure_bundle_capabilities!"),
            text.index('match(\n      api_key: api_key, type: "appstore", readonly: false'),
        )

    def test_native_evidence_writer_is_documented_and_reused_by_ci(self) -> None:
        workflow = Path(".github/workflows/native-mobile.yml").read_text(encoding="utf-8")
        readme = Path("mobile/ios/README.md").read_text(encoding="utf-8")
        writer = Path("ops/write_native_build_evidence.py").read_text(encoding="utf-8")

        self.assertIn("ops/write_native_build_evidence.py", workflow)
        self.assertIn("ops/write_native_build_evidence.py", readme)
        self.assertIn("xcodegen generate --spec mobile/ios/project.yml --project-root .", readme)
        self.assertIn(
            'xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddie -destination "platform=iOS Simulator,name=iPhone 16,OS=latest"',
            readme,
        )
        self.assertIn(
            'xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddieWatch -destination "platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest"',
            readme,
        )
        self.assertIn("ai-caddie-native-build-evidence-v1", writer)
        self.assertIn("PRIVATE_VALUE_MARKERS", writer)


if __name__ == "__main__":
    unittest.main()
