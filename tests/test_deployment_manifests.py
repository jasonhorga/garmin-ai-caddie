from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib
import unittest
import yaml


def _normalise_dockerignore_pattern(value: str) -> str:
    return value.removeprefix("./").removeprefix("/").rstrip("/")


def _relative_copy_destination(workdir: str, stage_root: str, value: str) -> str | None:
    raw = value.rstrip("/") or "."
    if raw.startswith("/"):
        destination = Path(raw)
        try:
            return destination.relative_to(Path(workdir)).as_posix() or "."
        except ValueError:
            return None
    try:
        relative_workdir = Path(workdir).relative_to(Path(stage_root))
    except ValueError:
        return None
    combined = relative_workdir / raw
    return combined.as_posix() or "."


def _docker_instructions(lines: list[str]) -> list[str]:
    instructions: list[str] = []
    index = 0
    while index < len(lines):
        current = lines[index].strip()
        index += 1
        if not current or current.startswith("#"):
            continue
        parts = [current]
        while parts[-1].endswith("\\"):
            parts[-1] = parts[-1][:-1].rstrip()
            while index < len(lines):
                continuation = lines[index].strip()
                index += 1
                if continuation and not continuation.startswith("#"):
                    parts.append(continuation)
                    break
        instructions.append(" ".join(parts))
    return instructions


class DeploymentManifestTests(unittest.TestCase):
    def _load_compose(self) -> dict:
        return yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))

    def test_readiness_runtime_paths_are_copied_into_image(self) -> None:
        """Every repository file read by runtime readiness is in the API image.

        The path set is observed while readiness runs, rather than duplicated here. This keeps
        the guard aligned with future readiness checks and makes a moved contract fail with the
        moved path in the assertion instead of silently preserving an old allow-list.
        """
        root = Path(__file__).resolve().parents[1]
        trace_script = r'''
import json
import os
import sys
from pathlib import Path
from server_v2 import readiness

root = Path.cwd().resolve()
observed = set()
paths_by_label = {}
active = True
recording = False

def record(value):
    global recording
    if not active or recording or isinstance(value, int):
        return
    recording = True
    try:
        try:
            raw = os.fsdecode(os.fspath(value))
        except TypeError:
            return
        absolute = os.path.realpath(raw if os.path.isabs(raw) else os.path.join(os.getcwd(), raw))
        root_text = os.path.realpath(os.fspath(root))
        try:
            relative = os.path.relpath(absolute, root_text)
        except ValueError:
            return
        if relative in (os.curdir, os.pardir) or relative.startswith(os.pardir + os.sep):
            return
        observed.add(Path(relative).as_posix())
    finally:
        recording = False

original_path_methods = {
    name: getattr(Path, name)
    for name in ("exists", "is_file", "is_symlink", "is_dir", "stat", "lstat", "open", "read_text", "read_bytes")
}
original_os_methods = {name: getattr(os, name) for name in ("stat", "lstat", "access")}

def wrap_path(name):
    original = original_path_methods[name]
    def traced(path, *args, **kwargs):
        record(path)
        return original(path, *args, **kwargs)
    return traced

def wrap_os(name):
    original = original_os_methods[name]
    def traced(path, *args, **kwargs):
        record(path)
        return original(path, *args, **kwargs)
    return traced

def audit_hook(event, args):
    if event in {"open", "os.listdir", "os.scandir", "os.walk"} and args:
        record(args[0] if args[0] is not None else os.getcwd())

sys.addaudithook(audit_hook)
original_check = readiness._check

def traced_check(label, *args, **kwargs):
    paths_by_label.setdefault(label, set()).update(observed)
    observed.clear()
    return original_check(label, *args, **kwargs)

for name in original_path_methods:
    setattr(Path, name, wrap_path(name))
for name in original_os_methods:
    setattr(os, name, wrap_os(name))
readiness._check = traced_check
try:
    readiness.build_readiness_response()
finally:
    active = False
    readiness._check = original_check
    for name, original in original_path_methods.items():
        setattr(Path, name, original)
    for name, original in original_os_methods.items():
        setattr(os, name, original)

print("CARD432-TRACE:" + json.dumps({
    "labels": {label: sorted(paths) for label, paths in paths_by_label.items()},
    "packaging": sorted(readiness.PACKAGING_LABELS),
}))
'''
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(part for part in (str(root), env.get("PYTHONPATH", "")) if part)
        trace = subprocess.run(
            [sys.executable, "-c", trace_script],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
        )
        marker = "CARD432-TRACE:"
        result_lines = [line for line in trace.stdout.splitlines() if line.startswith(marker)]
        self.assertEqual(
            trace.returncode,
            0,
            "readiness trace child failed: " + (trace.stderr[-4000:] or trace.stdout[-4000:]),
        )
        self.assertTrue(result_lines, "readiness trace child produced no result")
        try:
            trace_payload = json.loads(result_lines[-1][len(marker):])
        except json.JSONDecodeError as exc:
            self.fail(f"invalid readiness trace result: {exc}")
        paths_by_label = {
            str(label): set(paths)
            for label, paths in (trace_payload.get("labels") or {}).items()
        }
        packaging_labels = set(trace_payload.get("packaging") or [])

        private_roots = {
            "data",
            ".garmin_tokens",
            "output",
            "logs",
            "backups",
            "clubs.json",
            ".venv",
            "node_modules",
        }

        def excluded(path: str) -> bool:
            parts = path.split("/")
            if parts[0] in private_roots:
                return True
            # Import-generated bytecode is built by the image, rather than copied from Git.
            return "__pycache__" in parts or path.endswith(".pyc")

        runtime_paths = sorted(
            {
                path
                for label, paths in paths_by_label.items()
                if label not in packaging_labels
                for path in paths
                if not excluded(path)
            }
        )
        dockerfile = root / "Dockerfile"
        dockerignore = root / ".dockerignore"
        # A missing image manifest ships no sources. Report the uncovered paths via the same
        # assertion as an omitted COPY, instead of raising FileNotFoundError.
        docker_lines = dockerfile.read_text(encoding="utf-8").splitlines() if dockerfile.exists() else []
        copied_sources: list[tuple[str, Path, bool, bool, str]] = []
        stage = -1
        instructions = _docker_instructions(docker_lines)
        final_stage = sum(line.split(None, 1)[0].upper() == "FROM" for line in instructions) - 1
        workdir = Path("/")

        def normalise_path(value: str) -> str:
            normalised = value.removeprefix("./").rstrip("/")
            return normalised or "."

        for line in instructions:
            stripped = line.strip()
            if stripped.upper().startswith("FROM "):
                stage += 1
                workdir = Path("/")
                continue
            if stage != final_stage:
                continue
            if stripped.upper().startswith("WORKDIR "):
                raw_workdir = shlex.split(stripped, comments=False)[1]
                if raw_workdir.startswith("/"):
                    workdir = Path(os.path.normpath(raw_workdir))
                else:
                    workdir = Path(os.path.normpath(str(workdir / raw_workdir)))
                continue
            if not stripped.upper().startswith("COPY "):
                continue
            try:
                tokens = shlex.split(stripped)
            except ValueError:
                continue
            arguments = [token for token in tokens[1:] if not token.startswith("--")]
            if len(arguments) < 2 or any(token.startswith("--from=") for token in tokens[1:]):
                continue
            raw_destination = arguments[-1]
            if raw_destination.startswith("/"):
                destination = Path(os.path.normpath(raw_destination))
            else:
                destination = Path(os.path.normpath(str(workdir / raw_destination)))
            sources = [normalise_path(token) for token in arguments[:-1]]
            multiple_sources = len(sources) > 1
            for source in sources:
                source_path = root / source
                copied_sources.append(
                    (source, workdir / destination, source_path.is_dir() or source == ".", multiple_sources, raw_destination)
                )

        runtime_root = workdir

        ignored_patterns: list[str] = []
        if dockerignore.exists():
            for line in dockerignore.read_text(encoding="utf-8").splitlines():
                pattern = line.strip()
                if pattern and not pattern.startswith("#") and not pattern.startswith("!"):
                    ignored_patterns.append(_normalise_dockerignore_pattern(pattern))

        def is_ignored(path: str) -> bool:
            ancestors = [path]
            parent = Path(path).parent
            while str(parent) not in {".", ""}:
                ancestors.append(parent.as_posix())
                parent = parent.parent
            return any(fnmatch.fnmatch(candidate, pattern) for candidate in ancestors for pattern in ignored_patterns)

        def is_copied(path: str) -> bool:
            path_obj = Path(path)
            target = runtime_root / path_obj
            for source, destination, source_is_dir, multiple_sources, raw_destination in copied_sources:
                source_path = Path(source)
                if source_is_dir:
                    try:
                        relative = path_obj.relative_to(source_path)
                    except ValueError:
                        continue
                    if destination / relative == target:
                        return True
                    continue
                if multiple_sources or raw_destination.endswith("/") or raw_destination in {"", "."}:
                    landed = Path(destination) / source_path.name
                else:
                    landed = Path(destination)
                if landed == target:
                    return True
            return False

        uncovered = [path for path in runtime_paths if not is_copied(path) or is_ignored(path)]
        self.assertFalse(
            uncovered or not dockerfile.exists(),
            "readiness runtime paths are not shipped by the final Docker stage: " + ", ".join(uncovered),
        )

    def test_dockerignore_root_pattern_is_normalized(self) -> None:
        self.assertEqual(_normalise_dockerignore_pattern("/mobile/contracts/"), "mobile/contracts")

    def test_copy_outside_stage_root_is_uncovered(self) -> None:
        self.assertIsNone(_relative_copy_destination("/other", "/app", "./mobile/contracts"))

    def test_no_argument_directory_listing_records_current_repository_directory(self) -> None:
        repository_subdirectory = Path(__file__).resolve().parent
        script = """
import os
import sys

recorded = []

def record(value):
    recorded.append(os.fsdecode(os.fspath(value)))

def audit_hook(event, args):
    if event in {\"os.listdir\", \"os.scandir\"} and args:
        record(args[0] if args[0] is not None else os.getcwd())

sys.addaudithook(audit_hook)
os.chdir(sys.argv[1])
os.listdir()
assert sys.argv[1] in recorded, (sys.argv[1], recorded)
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(repository_subdirectory)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

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

    def test_sync_build_script_pins_tag_to_api_source_revision(self) -> None:
        script = Path("ops/build_sync_image.sh")
        self.assertTrue(script.exists(), "missing sync image build script")
        text = script.read_text(encoding="utf-8")

        for required in [
            "ai.caddie.source-revision",
            "SYNC_IMAGE_TAG:-$API_SOURCE_REVISION",
            "CANONICAL_TAG=\"aicaddie-sync:${API_SOURCE_REVISION}\"",
            "docker tag \"$SYNC_TAG\" \"$CANONICAL_TAG\"",
            "--label \"ai.caddie.source-revision=${API_SOURCE_REVISION}\"",
            "PUBLISH_LATEST",
            "does not exist locally",
            "refusing an unbound sync image",
            "no active API container found",
            "AICADDIE_API_PORT",
            "multiple release containers",
            "CONTAINER_SOURCE_REVISION",
        ]:
            self.assertIn(required, text)

        # Building the API and then silently tagging an unrelated `latest` image
        # was the incident's root cause; the helper must consume a labelled API
        # image and produce the immutable cron tag.
        self.assertNotIn("docker compose build api", text)
        self.assertNotIn("SYNC_IMAGE_TAG:-latest", text)

    def test_homeserver_deploy_gate_builds_sync_after_health(self) -> None:
        script = Path("ops/complete_homeserver_api_deploy.sh")
        self.assertTrue(script.exists(), "missing homeserver deployment gate")
        text = script.read_text(encoding="utf-8")

        for required in [
            "AICADDIE_API_CONTAINER",
            "AICADDIE_API_PORT",
            "api/v2/health",
            "env -u API_IMAGE",
            "AICADDIE_DEPLOY_GATE_CHECK_ONLY",
            "ops/build_sync_image.sh",
            "aicaddie-sync:${source_revision}",
            "deployment complete",
        ]:
            self.assertIn(required, text)

    def test_homeserver_sync_alerts_on_missing_or_mismatched_image(self) -> None:
        script = Path("ops/homeserver_sync.sh")
        self.assertTrue(script.exists(), "missing homeserver sync entrypoint")
        text = script.read_text(encoding="utf-8")

        for required in [
            "AICADDIE_SYNC_ALERT_WEBHOOK_URL",
            "AICADDIE_SYNC_ALERT_STATE",
            "logger -t aicaddie-sync",
            "notify-send",
            "sync_failed",
            "sync_recovered",
            "multiple release containers",
            "aicaddie-sync:${API_SOURCE_REVISION}",
            "refusing stale/latest image",
            "sync ok",
            "done",
        ]:
            self.assertIn(required, text)

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
        self.assertIn("COPY mobile/contracts/ ./mobile/contracts/", docker_text)
        for contract in [
            "mobile/contracts/live_round_package.schema.json",
            "mobile/contracts/live_round_event.schema.json",
        ]:
            self.assertTrue(Path(contract).is_file(), f"missing readiness contract: {contract}")
            self.assertIn(f"test -s /app/{contract}", workflow_text)
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
