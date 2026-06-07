from __future__ import annotations

from pathlib import Path
import unittest


ROADMAP = Path("docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md")
AUDIT = Path("docs/superpowers/reviews/2026-06-07-roadmap-completion-audit.md")


def _open_checklist_items(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("- [ ] "):
            if current is not None:
                items.append(" ".join(current))
            current = [line.removeprefix("- [ ] ").strip()]
            continue
        if line.startswith("- [x] ") or line.startswith("### "):
            if current is not None:
                items.append(" ".join(current))
                current = None
            continue
        if current is not None and line.startswith("  ") and line.strip():
            current.append(line.strip())
            continue
        if current is not None and not line.strip():
            items.append(" ".join(current))
            current = None
    if current is not None:
        items.append(" ".join(current))
    return items


class RoadmapCompletionAuditTests(unittest.TestCase):
    def test_authoritative_roadmap_has_only_expected_external_phase6_open_items(self) -> None:
        text = ROADMAP.read_text(encoding="utf-8")
        open_items = _open_checklist_items(text)

        self.assertEqual(
            [
                "Deploy a phone-reachable backend host and point the native app at it.",
                "Submit external Beta App Review.",
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
            "Target tester coverage is now closed",
            "Verify installation from TestFlight on iPhone/watch",
            "docs/superpowers/reviews/2026-06-05-test-execution.md",
            "docs/superpowers/reviews/2026-06-06-phase-6-deployment-native-trial-hardening.md",
            "logs/phase6_external_readiness_latest.json",
            "external_release",
            "uv run python ops/roadmap_completion_status.py --no-fail",
            "without network access",
            "grouped `phase6Gates`",
            "`roadmapGateAlignment`",
            "roadmap/evidence drift",
            "backend reachability",
            "Beta Review submission",
            "Latest Local Continuation Evidence",
            "heavyweight validation on manual GitHub",
            "cold `/api/v2/readiness` startup",
            "endpointCount=14",
            "adminProtectedEndpointCount=11",
            "tests.test_phase6_external_readiness tests.test_server_v2_readiness tests.test_deployment_manifests tests.test_roadmap_completion_status",
            "reported 49 tests OK",
            "parses multiline checklist items",
            "ignores GitHub Actions script-source echo",
            "do not replace the three remaining external Phase 6 gates",
            "No-Quota External Audit",
            "The six long-lived signing secrets are present",
            "GitHub Actions variables are empty",
            "AI_CADDIE_API_BASE_URL",
            "TESTFLIGHT_FEEDBACK_EMAIL",
            "0.1.0 (3)",
            "usesNonExemptEncryption=false",
            "READY_FOR_BETA_SUBMISSION",
            "to submit for external Beta Review",
            "External group `Private Trial` exists",
            "assigned 2 external testers",
            "That is strong enough to prove target tester",
            "failed before external distribution",
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
