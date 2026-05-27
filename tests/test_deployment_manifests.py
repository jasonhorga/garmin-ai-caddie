from __future__ import annotations

import json
from pathlib import Path
import unittest


class DeploymentManifestTests(unittest.TestCase):
    def test_render_manifest_runs_private_fixture_api_with_health_check(self) -> None:
        manifest = Path("render.yaml")
        self.assertTrue(manifest.exists(), "missing Render staging manifest")
        text = manifest.read_text(encoding="utf-8")

        for required in [
            "type: web",
            "runtime: python",
            "uv sync",
            "uv run uvicorn server_v2.main:app --host 0.0.0.0 --port $PORT",
            "healthCheckPath: /api/v2/health",
            "AI_CADDIE_SECURITY_PROFILE",
            "sync: false",
            "AI_CADDIE_ADMIN_TOKEN",
            "AI_CADDIE_DATA_MODE",
            "local_or_fixture",
        ]:
            self.assertIn(required, text)
        self.assertNotIn("cookie", text.lower())
        self.assertNotIn("csrf", text.lower())

    def test_vercel_manifest_builds_web_v2_with_node_24_and_spa_fallback(self) -> None:
        manifest = Path("web_v2/vercel.json")
        self.assertTrue(manifest.exists(), "missing Vercel web staging manifest")
        payload = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(payload["version"], 2)
        self.assertEqual(payload["buildCommand"], "npm run build")
        self.assertEqual(payload["outputDirectory"], "dist")
        self.assertEqual(payload["installCommand"], "npm ci")
        self.assertEqual(payload["framework"], "vite")
        self.assertEqual(payload["env"]["NODE_VERSION"], "24")
        self.assertIn("VITE_AI_CADDIE_API_BASE_URL", payload["env"])
        self.assertEqual(payload["rewrites"], [{"source": "/(.*)", "destination": "/index.html"}])

    def test_private_trial_docs_wire_staging_web_to_staging_api(self) -> None:
        text = Path("docs/deployment/private-trial.md").read_text(encoding="utf-8")

        self.assertIn("VITE_AI_CADDIE_API_BASE_URL", text)
        self.assertIn("AI_CADDIE_CORS_ORIGINS", text)
        self.assertIn("Render API URL", text)
        self.assertIn("Vercel Web URL", text)


if __name__ == "__main__":
    unittest.main()
