from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server_v2.main import app


class ServerV2ReadinessTests(unittest.TestCase):
    def test_readiness_endpoint_reports_private_trial_checks_without_secrets(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}):
            response = client.get("/api/v2/readiness")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-readiness-v1")
        self.assertIn(payload["status"], {"ready", "degraded"})
        labels = {check["label"] for check in payload["checks"]}
        self.assertGreaterEqual(labels, {"service", "history", "sync", "mobile", "secret_handling"})
        self.assertGreaterEqual(labels, {"mobile_package", "mobile_events", "media_context", "reports", "operations", "native_mobile"})
        self.assertNotIn("cookie", str(payload).lower())
        self.assertNotIn("csrf", str(payload).lower())
        self.assertNotIn("token", str(payload).lower())
        checks = {check["label"]: check for check in payload["checks"]}
        self.assertEqual(checks["mobile_package"]["state"], "ready")
        self.assertEqual(checks["mobile_events"]["state"], "ready")
        self.assertEqual(checks["media_context"]["state"], "ready")
        self.assertEqual(checks["reports"]["state"], "ready")
        self.assertEqual(checks["operations"]["state"], "ready")
        self.assertEqual(checks["native_mobile"]["state"], "degraded")
        self.assertEqual(checks["native_mobile"]["evidence"]["nativeBuild"], "environment_blocked")
        self.assertIn("mobile/ios/project.yml", checks["native_mobile"]["evidence"]["projectManifest"])
        self.assertIn("xcodebuild test", checks["native_mobile"]["evidence"]["macosCommands"][0])
        self.assertIn("ops/smoke_private_trial.sh", checks["operations"]["evidence"]["scripts"])
        self.assertEqual(checks["operations"]["evidence"]["deploymentManifests"], ["render.yaml", "web_v2/vercel.json"])

        mobile_package = checks["mobile_package"]["evidence"]
        self.assertEqual(mobile_package["contractSchema"], "mobile/contracts/live_round_package.schema.json")
        self.assertEqual(mobile_package["offlinePackageStatus"]["state"], "ready")
        self.assertEqual(mobile_package["sourceCoverage"]["state"], "ready")
        self.assertTrue(mobile_package["sourceCoverage"]["roundFound"])
        self.assertGreaterEqual(mobile_package["caddieSeedCount"], 1)
        self.assertTrue(mobile_package["cachedCaddieRules"]["offlineCapable"])
        self.assertEqual(mobile_package["missingDataCount"], 0)

        mobile_events = checks["mobile_events"]["evidence"]
        self.assertEqual(mobile_events["contractSchema"], "mobile/contracts/live_round_event.schema.json")
        self.assertEqual(
            mobile_events["eventKinds"],
            ["score", "club", "putt", "penalty", "note", "location", "photo", "video", "sync_marker"],
        )
        self.assertEqual(mobile_events["idempotencyHeader"], "Idempotency-Key")
        self.assertEqual(
            mobile_events["endpoints"],
            {
                "batch": "/api/v2/mobile/rounds/{round_id}/events",
                "reconciliation": "/api/v2/mobile/rounds/{round_id}/reconciliation",
                "reconciliationApply": "/api/v2/mobile/rounds/{round_id}/reconciliation/apply",
            },
        )

        media_context = checks["media_context"]["evidence"]
        self.assertEqual(media_context["uploadRoot"], "data/media/uploads")
        self.assertTrue(media_context["localPathEscapeProtection"])
        self.assertEqual(media_context["allowedMediaKinds"], ["photo", "video"])
        self.assertEqual(
            media_context["confirmationStates"],
            ["unconfirmed", "confirmed", "player_confirmed", "manual_confirmed", "rejected"],
        )
        self.assertTrue(media_context["findingsRedactLocalPath"])

        reports = checks["reports"]["evidence"]
        self.assertEqual(reports["schema"], "ai-caddie-review-report-v1")
        self.assertEqual(reports["factBinding"]["state"], "bound")
        self.assertEqual(reports["unsupportedClaimCount"], 0)
        self.assertGreaterEqual(reports["sourceRefCount"], 1)
        self.assertGreaterEqual(reports["factsUsedCount"], 1)
        self.assertGreaterEqual(reports["missingDataCount"], 0)

        operations = checks["operations"]["evidence"]
        self.assertEqual(operations["smokeCommand"], "ops/smoke_private_trial.sh")
        self.assertGreaterEqual(
            set(operations["smokeCovers"]),
            {"readiness", "mobile_package", "caddie_decision", "reports", "media_context"},
        )
        self.assertEqual(operations["redactionPolicy"], "no credential material or private filesystem paths in status responses")

    def test_service_index_and_smoke_script_advertise_readiness(self) -> None:
        client = TestClient(app)

        response = client.get("/")
        script = __import__("pathlib").Path("ops/smoke_private_trial.sh")

        self.assertEqual(response.json()["endpoints"]["readiness"], "/api/v2/readiness")
        self.assertTrue(script.exists())
        script_text = script.read_text(encoding="utf-8")
        self.assertIn("/api/v2/readiness", script_text)
        self.assertIn("uv run python", script_text)


if __name__ == "__main__":
    unittest.main()
