from __future__ import annotations

import json
from pathlib import Path
import tomllib
import unittest
import yaml


class DeploymentManifestTests(unittest.TestCase):
    def _load_compose(self) -> dict:
        return yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))

    def test_compose_has_postgres_and_api_database_url(self) -> None:
        compose = self._load_compose()
        services = compose["services"]

        # db service exists with a postgres image
        self.assertIn("db", services)
        self.assertIn("postgres", services["db"]["image"])

        # api environment contains AI_CADDIE_DATABASE_URL
        api_env = services["api"].get("environment", {})
        keys = (
            api_env.keys()
            if isinstance(api_env, dict)
            else {e.split("=", 1)[0] for e in api_env}
        )
        self.assertIn("AI_CADDIE_DATABASE_URL", keys)

        # api depends_on db
        self.assertIn("db", services["api"].get("depends_on", {}))

    def test_render_manifest_runs_private_fixture_api_with_health_check(self) -> None:
        manifest = Path("render.yaml")
        self.assertTrue(manifest.exists(), "missing Render staging manifest")
        text = manifest.read_text(encoding="utf-8")
        payload = yaml.safe_load(text)
        service = payload["services"][0]

        for required in [
            "type: web",
            "runtime: python",
            "uv sync --frozen --no-dev",
            "sh ops/start_api.sh",
            "healthCheckPath: /api/v2/health",
            "AI_CADDIE_SECURITY_PROFILE",
            "sync: false",
            "AI_CADDIE_ADMIN_TOKEN",
            "AI_CADDIE_DATA_MODE",
            "local_or_fixture",
        ]:
            self.assertIn(required, text)
        self.assertEqual(service["startCommand"], "sh ops/start_api.sh")
        self.assertEqual(service["disk"]["mountPath"], "/var/data/ai-caddie")
        self.assertEqual(service["disk"]["sizeGB"], 5)
        environment = {entry["key"]: entry for entry in service["envVars"]}
        self.assertEqual(environment["AI_CADDIE_PRIVATE_ROOT"]["value"], "/var/data/ai-caddie")
        self.assertEqual(
            environment["AI_CADDIE_DATABASE_URL"]["fromDatabase"]["name"],
            "ai-caddie-db",
        )
        self.assertEqual(payload["databases"][0]["name"], "ai-caddie-db")
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

    def test_private_trial_docs_cover_home_only_nas_vm_tunnel(self) -> None:
        private_trial = Path("docs/deployment/private-trial.md").read_text(encoding="utf-8")
        runbook = Path("docs/deployment/nas-vm-tunnel.md")
        self.assertTrue(runbook.exists(), "missing NAS VM tunnel runbook")
        text = runbook.read_text(encoding="utf-8")

        for required in [
            "reachable only from the home LAN",
            "Do not expose SSH through a home proxy",
            "Cloudflare Tunnel",
            "Tailscale Funnel",
            "127.0.0.1:9000",
            "ops/bootstrap_nas_vm_api.sh",
            "AI_CADDIE_API_BASE_URL",
            "AI_CADDIE_ADMIN_TOKEN",
            "Phase 6 Readiness",
            "iOS TestFlight (CD)",
            "origin only",
            "docker compose up -d --build api",
            "ops/smoke_private_trial.sh http://127.0.0.1:9000",
        ]:
            self.assertIn(required, text)
        self.assertIn("docs/deployment/nas-vm-tunnel.md", private_trial)
        self.assertIn("Cloudflare Tunnel or Tailscale Funnel", private_trial)

    def test_nas_vm_bootstrap_script_keeps_api_local_and_secret_safe(self) -> None:
        script = Path("ops/bootstrap_nas_vm_api.sh")
        self.assertTrue(script.exists(), "missing NAS VM bootstrap script")
        text = script.read_text(encoding="utf-8")

        for required in [
            "AI_CADDIE_API_PUBLISH_HOST 127.0.0.1",
            "openssl rand -hex 32",
            "docker compose",
            "compose up -d --build api",
            "curl -fsS http://127.0.0.1:9000/api/v2/health",
            "ops/smoke_private_trial.sh http://127.0.0.1:9000",
            "Do not paste AI_CADDIE_ADMIN_TOKEN into chat",
        ]:
            self.assertIn(required, text)
        self.assertNotIn("echo $AI_CADDIE_ADMIN_TOKEN", text)
        self.assertNotIn("9000:9000", text)

    def test_private_trial_docs_include_local_and_cloud_smoke_commands(self) -> None:
        text = Path("docs/deployment/private-trial.md").read_text(encoding="utf-8")

        for required in [
            "PORT=9000 sh ops/start_api.sh",
            "ops/smoke_private_trial.sh http://127.0.0.1:9000",
            "ops/backup_data.sh",
            "ops/export_snapshot.py",
            "ops/import_snapshot.py",
            "Render API URL",
            "Fly API URL",
            "Vercel Web URL",
            "AI_CADDIE_ADMIN_TOKEN",
            "AI_CADDIE_PRIVATE_ROOT",
            "Backend Fly Deploy",
            "FLY_API_TOKEN",
            "flyctl deploy --remote-only",
            "AI_CADDIE_API_BASE_URL",
            "phase6_external_readiness_latest.json",
            "Phase 6 Readiness",
            "roadmap_completion_status.json",
            "fail_when_incomplete",
            "PHASE6_GH_TOKEN",
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
            "postgresql-client",
            "EXPOSE 9000",
        ]:
            self.assertIn(required, docker_text)
        self.assertIn("AI_CADDIE_PRIVATE_ROOT: /var/lib/ai-caddie", compose_text)
        self.assertIn("AI_CADDIE_BUILD_REVISION", compose_text)
        self.assertIn("ai-caddie-private:/var/lib/ai-caddie", compose_text)
        self.assertIn('restart: "on-failure:3"', compose_text)
        self.assertIn('restart: "on-failure:5"', compose_text)
        self.assertIn("mem_limit:", compose_text)
        self.assertIn("max-size: \"10m\"", compose_text)
        self.assertIn("VITE_AI_CADDIE_API_BASE_URL", compose_text)
        self.assertIn("${AI_CADDIE_API_PUBLISH_HOST:-127.0.0.1}:9000:9000", compose_text)
        self.assertIn("AI_CADDIE_PRIVATE_ROOT", entrypoint_text)
        self.assertIn(".garmin_tokens", entrypoint_text)
        self.assertIn("python -m server_v2.identity_seed", entrypoint_text)
        self.assertIn("wait_for_postgres", entrypoint_text)
        self.assertIn("pg_isready", entrypoint_text)
        self.assertIn("flock", entrypoint_text)
        self.assertIn("flock -u 9", entrypoint_text)
        self.assertIn("exec 9>&-", entrypoint_text)
        self.assertIn("AI_CADDIE_MIGRATION_TIMEOUT_SECONDS", entrypoint_text)
        self.assertNotIn("JWT_WEB", docker_text + compose_text)
        self.assertNotIn("connect-csrf-token", docker_text + compose_text)

    def test_compose_persists_topo_render_cache_inside_private_volume(self) -> None:
        compose = self._load_compose()
        api = compose["services"]["api"]
        environment = api["environment"]

        cache_dir = environment.get("AI_CADDIE_TOPO_CACHE_DIR")
        private_root = environment["AI_CADDIE_PRIVATE_ROOT"].rstrip("/")

        self.assertEqual(cache_dir, "/var/lib/ai-caddie/topo_render_cache")
        self.assertTrue(cache_dir.startswith(f"{private_root}/"))
        self.assertIn(f"ai-caddie-private:{private_root}", api["volumes"])

    def test_api_image_packages_and_smokes_canonical_contracts(self) -> None:
        docker_text = Path("Dockerfile").read_text(encoding="utf-8")
        workflow_text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn("COPY contracts/canonical/ ./contracts/canonical/", docker_text)
        for required in [
            "docker exec -i aicaddie-api /app/.venv/bin/python -",
            "from ai_caddie.contracts.typed_ids import typed_id",
            'Path("/app/contracts/canonical/fixtures/canonical_json_v1.json")',
            'fixture["typedIds"].items()',
            'typed_id(domain, fixture["value"])',
        ]:
            self.assertIn(required, workflow_text)

    def test_ci_guards_default_branch_and_identity_cold_start(self) -> None:
        workflow_text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

        for required in [
            "push:",
            "- main",
            "- integration/v2",
            'AI_CADDIE_DATABASE_URL="sqlite:///$RUNNER_TEMP/identity-cold-start.db"',
            "uv run --frozen alembic upgrade head",
            "uv run --frozen python -m server_v2.identity_seed",
            'patch(\n              "server_v2.auth_api._verify"',
            'client.post(\n                      "/api/v2/auth/apple"',
            'payload.get("token")',
            'payload.get("playerId")',
        ]:
            self.assertIn(required, workflow_text)

    def test_fly_manifest_uses_container_volume_and_secret_driven_admin_token(self) -> None:
        manifest = Path("fly.toml")
        self.assertTrue(manifest.exists(), "missing Fly API manifest")

        payload = tomllib.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(payload["build"]["dockerfile"], "Dockerfile")
        self.assertEqual(payload["env"]["AI_CADDIE_SECURITY_PROFILE"], "private")
        self.assertEqual(payload["env"]["AI_CADDIE_BUILD_REVISION"], "unknown")
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
            "AI_CADDIE_DB_PASSWORD=replace-with-random-db-password",
            "AI_CADDIE_DATA_MODE=local_or_fixture",
            "AI_CADDIE_API_PUBLISH_HOST=127.0.0.1",
            "VITE_AI_CADDIE_API_BASE_URL=http://127.0.0.1:9000",
            "AI_CADDIE_LLM_PROVIDER=static",
        ]:
            self.assertIn(required, text)
        self.assertNotIn("/home/ubuntu/claude-web-data", text)
        self.assertNotIn("JWT_WEB", text)
        self.assertNotIn("connect-csrf-token", text)


if __name__ == "__main__":
    unittest.main()
