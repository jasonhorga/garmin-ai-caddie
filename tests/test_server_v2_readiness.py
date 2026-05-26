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
