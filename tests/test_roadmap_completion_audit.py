from __future__ import annotations

import re
from pathlib import Path
import unittest


ROADMAP = Path("docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md")
AUDIT = Path("docs/superpowers/reviews/2026-06-07-roadmap-completion-audit.md")


class RoadmapCompletionAuditTests(unittest.TestCase):
    def test_authoritative_roadmap_has_only_expected_external_phase6_open_items(self) -> None:
        text = ROADMAP.read_text(encoding="utf-8")
        open_items = re.findall(r"^- \[ \] (.+)$", text, flags=re.MULTILINE)

        self.assertEqual(
            [
                "Deploy a phone-reachable backend host and point the native app at it.",
                "Submit external Beta App Review.",
                "Add/confirm target tester emails for the external group or confirm the",
                "Verify installation from TestFlight on iPhone/watch.",
            ],
            open_items,
        )

    def test_completion_audit_tracks_open_items_and_evidence_sources(self) -> None:
        audit = AUDIT.read_text(encoding="utf-8")

        for required in [
            "Authoritative roadmap",
            "Older detailed implementation plans",
            "historical planning artifacts",
            "Deploy a phone-reachable backend host",
            "Submit external Beta App Review",
            "external Beta App Review submission",
            "Add/confirm target tester emails",
            "Verify installation from TestFlight on iPhone/watch",
            "docs/superpowers/reviews/2026-06-05-test-execution.md",
            "docs/superpowers/reviews/2026-06-06-phase-6-deployment-native-trial-hardening.md",
            "logs/phase6_external_readiness_latest.json",
            "external_release",
            "No-Quota External Audit",
            "The six long-lived signing secrets are present",
            "GitHub Actions variables are empty",
            "AI_CADDIE_API_BASE_URL",
            "0.1.0 (2)",
            "usesNonExemptEncryption=false",
            "READY_FOR_BETA_SUBMISSION",
            "to submit for external Beta Review",
            "External group `Private Trial` exists",
            "not strong enough to prove target tester coverage",
            "The active goal is not complete yet.",
        ]:
            self.assertIn(required, audit)

    def test_roadmap_phase6_preflight_writes_readiness_evidence(self) -> None:
        roadmap = ROADMAP.read_text(encoding="utf-8")

        self.assertIn("ops/phase6_external_readiness.py", roadmap)
        self.assertIn("--probe-backend", roadmap)
        self.assertIn("--output logs/phase6_external_readiness_latest.json", roadmap)


if __name__ == "__main__":
    unittest.main()
