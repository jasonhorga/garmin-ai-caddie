from __future__ import annotations

import json
from pathlib import Path
import tomllib
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
        self.assertIn("AI_CADDIE_CORS_ORIGIN_REGEX", text)
        self.assertIn("Render API URL", text)
        self.assertIn("Vercel Web URL", text)

    def test_private_trial_docs_include_local_and_cloud_smoke_commands(self) -> None:
        text = Path("docs/deployment/private-trial.md").read_text(encoding="utf-8")

        for required in [
            "uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9000",
            "ops/smoke_private_trial.sh http://127.0.0.1:9000",
            "ops/backup_data.sh",
            "ops/export_snapshot.py",
            "ops/import_snapshot.py",
            "Render API URL",
            "Fly API URL",
            "Vercel Web URL",
            "AI_CADDIE_ADMIN_TOKEN",
            "AI_CADDIE_PRIVATE_ROOT",
        ]:
            self.assertIn(required, text)
        self.assertNotIn("JWT_WEB", text)
        self.assertNotIn("connect-csrf-token", text)

    def test_private_trial_docs_include_phase6_external_preflight(self) -> None:
        text = Path("docs/deployment/private-trial.md").read_text(encoding="utf-8")
        ios_setup = Path("docs/ios-testflight-setup.md").read_text(encoding="utf-8")

        for required in [
            "ops/phase6_external_readiness.py",
            "--api-base-url https://<Render API URL or Fly API URL origin>",
            "--probe-backend",
            "--output logs/phase6_external_readiness_latest.json",
            "external_release",
            "AI_CADDIE_TESTFLIGHT_TESTER_COUNT",
            "AI_CADDIE_TESTFLIGHT_BETA_REVIEW_READY",
            "AI_CADDIE_TESTFLIGHT_BETA_REVIEW_SUBMITTED",
            "AI_CADDIE_TESTFLIGHT_INSTALL_VERIFIED",
            "--feedback-email-filled",
            "--beta-review-ready",
            "--beta-review-submitted",
            "--assigned-tester-count",
            "--feedback-email-source",
            "--native-runtime-api-configured",
            "--native-runtime-api-source",
            "--beta-review-ready-source",
            "--beta-review-source",
            "--assigned-tester-source",
            "--tester-coverage-source",
            "--install-source",
            "--tester-coverage-confirmed",
            "READY_FOR_BETA_SUBMISSION",
            "recent",
            "iOS TestFlight Testers",
            "never tester email addresses or raw log lines",
            "app-level TestFlight tester records",
            "target tester coverage",
            "target testers confirmed assigned to",
            "do not pass app-level",
            "observedAppTesterCount",
            "Do not put tester email addresses, tokens, or local filesystem paths in source",
            "redacts those values before printing JSON",
            "not replace `--beta-review-submitted`",
            "remaining review action is only",
            "AI_CADDIE_API_BASE_URL",
            "api_base_url",
            "TESTFLIGHT_FEEDBACK_EMAIL",
            "repo variable value as the probe URL",
            "reports only",
            "VITE_AI_CADDIE_API_BASE_URL",
            "only proves the Web build",
            "does not satisfy native TestFlight configuration",
            "runtime Backend screen",
            "testflight_backend_screen",
            "backend probe does not count as ready unless `AI_CADDIE_ADMIN_TOKEN`",
            "ai-caddie-health-v2",
            "ai-caddie-readiness-v1",
            "confirmation source",
            "CLI-entered counts",
            "external Beta App Review has been submitted",
            "origin-only API URL",
            "with no path",
            "query string",
            "URL credentials",
        ]:
            self.assertIn(required, text)
        self.assertIn("ops/phase6_external_readiness.py", ios_setup)
        self.assertIn("state=ready", ios_setup)
        self.assertIn("origin-only `api_base_url`", ios_setup)
        self.assertIn("API origin only", ios_setup)
        self.assertNotIn("JWT_WEB", text + ios_setup)
        self.assertNotIn("connect-csrf-token", text + ios_setup)

    def test_container_manifests_define_persistent_private_runtime_root(self) -> None:
        dockerfile = Path("Dockerfile")
        compose = Path("docker-compose.yml")
        entrypoint = Path("ops/start_api.sh")

        self.assertTrue(dockerfile.exists(), "missing API Dockerfile")
        self.assertTrue(compose.exists(), "missing compose stack")
        self.assertTrue(entrypoint.exists(), "missing API container entrypoint")

        docker_text = dockerfile.read_text(encoding="utf-8")
        compose_text = compose.read_text(encoding="utf-8")
        entrypoint_text = entrypoint.read_text(encoding="utf-8")

        for required in [
            "ghcr.io/astral-sh/uv:python3.12-bookworm-slim",
            "uv sync --frozen --no-dev",
            "npm ci --omit=dev",
            "ops/start_api.sh",
            "EXPOSE 9000",
        ]:
            self.assertIn(required, docker_text)
        self.assertIn("AI_CADDIE_PRIVATE_ROOT: /var/lib/ai-caddie", compose_text)
        self.assertIn("ai-caddie-private:/var/lib/ai-caddie", compose_text)
        self.assertIn("VITE_AI_CADDIE_API_BASE_URL", compose_text)
        self.assertIn("AI_CADDIE_PRIVATE_ROOT", entrypoint_text)
        self.assertIn(".garmin_tokens", entrypoint_text)
        self.assertNotIn("JWT_WEB", docker_text + compose_text)
        self.assertNotIn("connect-csrf-token", docker_text + compose_text)

    def test_fly_manifest_uses_container_volume_and_secret_driven_admin_token(self) -> None:
        manifest = Path("fly.toml")
        self.assertTrue(manifest.exists(), "missing Fly API manifest")

        payload = tomllib.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(payload["build"]["dockerfile"], "Dockerfile")
        self.assertEqual(payload["env"]["AI_CADDIE_SECURITY_PROFILE"], "private")
        self.assertEqual(payload["env"]["AI_CADDIE_PRIVATE_ROOT"], "/var/lib/ai-caddie")
        self.assertEqual(payload["mounts"]["source"], "ai_caddie_private")
        self.assertEqual(payload["mounts"]["destination"], "/var/lib/ai-caddie")
        self.assertEqual(payload["http_service"]["internal_port"], 9000)
        self.assertNotIn("AI_CADDIE_ADMIN_TOKEN", payload["env"])

    def test_env_example_documents_placeholders_without_real_secret_values(self) -> None:
        env = Path(".env.example")
        self.assertTrue(env.exists(), "missing env template")
        text = env.read_text(encoding="utf-8")

        for required in [
            "AI_CADDIE_SECURITY_PROFILE=private",
            "AI_CADDIE_ADMIN_TOKEN=replace-with-random-admin-token",
            "AI_CADDIE_DATA_MODE=local_or_fixture",
            "VITE_AI_CADDIE_API_BASE_URL=http://127.0.0.1:9000",
            "AI_CADDIE_LLM_PROVIDER=static",
        ]:
            self.assertIn(required, text)
        self.assertNotIn("/home/ubuntu/claude-web-data", text)
        self.assertNotIn("JWT_WEB", text)
        self.assertNotIn("connect-csrf-token", text)


if __name__ == "__main__":
    unittest.main()
