from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ops.roadmap_completion_status import build_status, main


class RoadmapCompletionStatusTests(unittest.TestCase):
    def test_status_reports_multiline_open_items_and_external_actions_safely(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            roadmap = root / "roadmap.md"
            evidence = root / "phase6.json"
            roadmap.write_text(
                "\n".join(
                    [
                        "- [x] Complete local implementation.",
                        "- [ ] Add/confirm target tester emails for the external group or confirm the",
                        "  user is covered by the existing internal group.",
                        "- [ ] Verify installation from TestFlight on iPhone/watch.",
                    ]
                ),
                encoding="utf-8",
            )
            evidence.write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-phase6-external-readiness-v1",
                        "createdAt": "2026-06-07T00:00:00Z",
                        "state": "incomplete",
                        "missingExternalActions": [
                            "submit external Beta App Review",
                            "owner@example.test /home/user/private-note.txt",
                            "access_token=abc123",
                        ],
                        "checks": [
                            {
                                "label": "signing_secrets",
                                "state": "ready",
                                "reason": None,
                            },
                            {
                                "label": "device_install",
                                "state": "manual_required",
                                "reason": "install screenshot /Users/me/Desktop/install.png",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            payload = build_status(roadmap_path=roadmap, external_release_path=evidence, created_at="now")

        self.assertFalse(payload["completionReady"])
        self.assertEqual(payload["state"], "incomplete")
        self.assertEqual(payload["roadmap"]["openItemCount"], 2)
        self.assertEqual(
            payload["roadmap"]["openItems"][0],
            (
                "Add/confirm target tester emails for the external group or confirm the "
                "user is covered by the existing internal group."
            ),
        )
        check_labels = {row["label"] for row in payload["externalRelease"]["checks"]}
        self.assertIn("signing_secrets", check_labels)
        gates = {row["key"]: row for row in payload["phase6Gates"]}
        self.assertEqual(gates["device_install"]["state"], "incomplete")
        self.assertEqual(
            gates["device_install"]["remainingActions"],
            ["install screenshot [redacted_path]"],
        )
        self.assertEqual(gates["phone_reachable_backend"]["checks"][0]["state"], "missing")
        rendered = json.dumps(payload, sort_keys=True)
        self.assertIn("submit external Beta App Review", rendered)
        self.assertIn("[redacted_email] [redacted_path]", rendered)
        self.assertIn("redacted_text", rendered)
        self.assertIn("install screenshot [redacted_path]", rendered)
        self.assertNotIn("owner@example.test", rendered)
        self.assertNotIn("/home/user", rendered)
        self.assertNotIn("/Users/me", rendered)
        self.assertNotIn("abc123", rendered)

    def test_status_is_ready_only_when_roadmap_and_external_release_are_ready(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            roadmap = root / "roadmap.md"
            evidence = root / "phase6.json"
            roadmap.write_text("- [x] Everything required is done.\n", encoding="utf-8")
            evidence.write_text(
                json.dumps(
                    {
                        "schema": "ai-caddie-phase6-external-readiness-v1",
                        "createdAt": "2026-06-07T00:00:00Z",
                        "state": "ready",
                        "missingExternalActions": [],
                        "checks": [
                            {"label": "native_api_base_url_configuration", "state": "ready", "reason": None},
                            {"label": "phone_reachable_backend_url", "state": "ready", "reason": None},
                            {"label": "backend_probe", "state": "ready", "reason": None},
                            {"label": "external_beta_review_submission_ready", "state": "ready", "reason": None},
                            {"label": "external_beta_review_submission", "state": "ready", "reason": None},
                            {"label": "external_testers", "state": "ready", "reason": None},
                            {"label": "device_install", "state": "ready", "reason": None},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            payload = build_status(roadmap_path=roadmap, external_release_path=evidence, created_at="now")

        self.assertTrue(payload["completionReady"])
        self.assertEqual(payload["state"], "ready")
        self.assertEqual(payload["remainingRequirements"], [])
        self.assertTrue(all(gate["state"] == "ready" for gate in payload["phase6Gates"]))

    def test_cli_writes_output_and_preserves_incomplete_exit_code(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            roadmap = root / "roadmap.md"
            evidence = root / "missing.json"
            output = root / "status.json"
            roadmap.write_text("- [ ] Deploy a phone-reachable backend host.\n", encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(
                    [
                        "--roadmap",
                        roadmap.as_posix(),
                        "--external-release-evidence",
                        evidence.as_posix(),
                        "--output",
                        output.as_posix(),
                    ]
                )

            printed = json.loads(stdout.getvalue())
            written = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(code, 2)
        self.assertEqual(printed, written)
        self.assertFalse(written["completionReady"])
        self.assertIn("run ops/phase6_external_readiness.py", written["remainingRequirements"])

    def test_cli_no_fail_allows_incomplete_status_for_audits(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            roadmap = root / "roadmap.md"
            roadmap.write_text("- [ ] Submit external Beta App Review.\n", encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["--roadmap", roadmap.as_posix(), "--no-fail"])

        self.assertEqual(code, 0)
        self.assertFalse(json.loads(stdout.getvalue())["completionReady"])


if __name__ == "__main__":
    unittest.main()
