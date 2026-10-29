#!/usr/bin/env python3
"""Single-command homeserver API deploy/rollback for the agenthub executor.

Usage:
    ops/agenthub_deploy.py deploy <40-hex-sha>
    ops/agenthub_deploy.py rollback <40-hex-sha>
    ops/agenthub_deploy.py up

The executor runs this file from a `git archive <sha>` tree (no `.git`) and
then polls `/api/v2/health` for `revision == sha`. Exit codes:

    0  success (also for an idempotent re-run of an already-live revision)
    1  failed; the previous container is serving again (or was never stopped)
    2  invalid invocation or configuration; nothing was touched
    3  failed and the previous container could NOT be confirmed healthy

The `up` action only starts existing containers, database first. It returns
0 when the stack is healthy, 1 on recovery failure, or 2 on invalid input.

Every host-specific value comes from the environment (see
docs/operations/runbook.md, "agenthub executor deploy"); the defaults are the
production values already used by ops/homeserver_sync.sh and the deploy gate.
The production container's environment carries credentials, so it is copied
only into a 0600 file on tmpfs that is removed immediately after `docker run`.
Nothing in this file prints environment values, env-file contents, or the
configured paths/URLs.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = REPO_ROOT / "ops" / "complete_homeserver_api_deploy.sh"
SYNC_BUILD_SCRIPT = REPO_ROOT / "ops" / "build_sync_image.sh"

SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
PREFIX_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*")
REVISION_LABEL = "ai.caddie.source-revision"
DEPENDENCY_HASH_LABEL = "ai.caddie.dependencies-hash"
API_DEPENDENCY_HASH_LABEL = "ai.caddie.api-dependencies-hash"
DEPENDENCY_START = "# BEGIN DEPENDENCY IMAGE"
DEPENDENCY_END = "# END DEPENDENCY IMAGE"
NODE_BASE_DIGEST = "sha256:91acba91b842bec0bf7ea6f5e09c644c7ccad72c4996ed9616d861d1c7cd60d4"
UV_BASE_DIGEST = "sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58"
API_REPOSITORY = "garmin-ai-caddie-api"
SYNC_REPOSITORY = "aicaddie-sync"
API_DEPS_REPOSITORY = "garmin-ai-caddie-deps"
SYNC_DEPS_REPOSITORY = "aicaddie-sync-deps"
PRIVATE_ROOT = "/var/lib/ai-caddie"
CONTAINER_PORT = "9000"
STOP_TIMEOUT_SECONDS = "30"
SYNC_CHECK_MARKER = "sync contract ok (check-only)"
DEFAULT_RELEASE_STATE_RELATIVE = Path(".local/state/aicaddie/current-release")
# Stop timeout plus gate/sync check time, on top of the health waits.
SWITCH_OVERHEAD_SECONDS = 90.0
SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_UNRECOVERED = 3

# Explicit projections keep other projects' container environments out of
# this process; only the production container's Env is read, separately.
CONTAINER_FORMAT = (
    '{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Image}},'
    '"labels":{{json .Config.Labels}},"running":{{json .State.Running}},'
    '"finishedAt":{{json .State.FinishedAt}},'
    '"ports":{{json .HostConfig.PortBindings}},'
    '"network":{{json .HostConfig.NetworkMode}},'
    '"networks":{{json .NetworkSettings.Networks}},"mounts":{{json .Mounts}},'
    '"memory":{{json .HostConfig.Memory}},"nanoCpus":{{json .HostConfig.NanoCpus}}}'
)
DATABASE_FORMAT = '{"running":{{json .State.Running}},"health":{{json .State.Health}}}'
ENV_FORMAT = "{{json .Config.Env}}"
IMAGE_FORMAT = '{"id":{{json .Id}},"tags":{{json .RepoTags}},"labels":{{json .Config.Labels}}}'

# Overrides applied on top of the copied production environment, matching the
# exact-revision deploy controller used before agenthub.
FIXED_ENV = {
    "AI_CADDIE_PRIVATE_ROOT": PRIVATE_ROOT,
    # 3 since C154a: green/raster CPU work shares the topo pool; with 2, two cold greens
    # (~9s each on real data) fill it and raster mattes queue behind them (review-C154a-r1).
    # Fixed rather than cgroup-derived so a 2-core container keeps two render workers.
    "AI_CADDIE_TOPO_RENDER_PROCESSES": "3",
    "PORT": CONTAINER_PORT,
}

# Caller variables that would bypass the revision binding of the helpers.
UNSAFE_CHILD_ENV = (
    "API_IMAGE", "SYNC_IMAGE_TAG", "PUBLISH_LATEST", "AICADDIE_SYNC_IMAGE",
    "SYNC_DEPS_IMAGE",
)


class DeployError(Exception):
    """A failure whose message is safe to print (no environment values)."""


class ConfigError(DeployError):
    pass


class Interrupted(DeployError):
    pass


class UpFailed(DeployError):
    def __init__(self, part: str, container: str, message: str, reason: str = "unexpected",
                 *, candidates: str = ""):
        super().__init__(message)
        self.part = part
        self.container = container
        self.reason = reason
        self.candidates = candidates


class LockTimeout(DeployError):
    """The recovery path could not acquire the sync lock before its deadline."""


class CutoverFailed(DeployError):
    def __init__(self, message: str, restored: bool | None):
        super().__init__(message)
        self.restored = restored  # None: there was no previous container


_UP_QUIET = False


def log(message: str) -> None:
    if _UP_QUIET:
        return
    print(f"agenthub-deploy: {message}", flush=True)


UP_REASONS = frozenset({
    "docker_unavailable",
    "database_missing",
    "database_unhealthy",
    "no_release_candidate",
    "release_tie",
    "api_unhealthy",
    "lock_timeout",
    "unexpected",
    "release_record_missing",
    "release_record_invalid",
    "release_record_unavailable",
})
UP_FIELDS = frozenset({"action", "result", "part", "container", "revision", "elapsed_s", "reason", "candidates", "selection"})


def _up_value(key: str, value: object) -> str | None:
    if key not in UP_FIELDS:
        return None
    if not isinstance(value, str):
        return "invalid"
    if key == "action":
        return value if value == "up" else "invalid"
    if key == "result":
        return value if value in {"ok", "failed"} else "invalid"
    if key == "part":
        return value if value in {"docker", "database", "api"} else "invalid"
    if key == "container":
        return value if value == "none" or PREFIX_PATTERN.fullmatch(value) else "invalid"
    if key == "revision":
        return value if SHA_PATTERN.fullmatch(value) else "invalid"
    if key == "elapsed_s":
        return value if re.fullmatch(r"\d+\.\d+", value) else "invalid"
    if key == "reason":
        return value if value in UP_REASONS else "invalid"
    if key == "selection":
        return value if value in {"record", "legacy"} else "invalid"
    if key == "candidates":
        return value if all(PREFIX_PATTERN.fullmatch(name) for name in value.split(",")) else "invalid"
    return "invalid"


def up_line(**fields: object) -> None:
    """Write one redacted recovery line; invalid values never reach stdout."""
    parts = []
    for key, value in fields.items():
        if key == "candidates" and fields.get("reason") != "release_tie":
            continue
        safe = _up_value(key, value)
        if safe is not None:
            parts.append(f"{key}={safe}")
    print(f"agenthub-deploy: {' '.join(parts)}", flush=True)


# ---------------------------------------------------------------------------
# Configuration


class Config:
    def __init__(self, env: dict[str, str]):
        self.port = _int(env, "AICADDIE_API_PORT", 39055, minimum=1, maximum=65535)
        self.prefix = env.get("AICADDIE_CONTAINER_PREFIX") or "aicaddie-release-"
        if not PREFIX_PATTERN.fullmatch(self.prefix):
            raise ConfigError("AICADDIE_CONTAINER_PREFIX must be a valid container name prefix")
        self.network = env.get("AICADDIE_DEPLOY_NETWORK") or "garmin-ai-caddie_default"
        self.volume = env.get("AICADDIE_PRIVATE_VOLUME") or "garmin-ai-caddie_ai-caddie-private"
        self.lock_path = env.get("AICADDIE_SYNC_LOCK") or "/tmp/aicaddie-sync.lock"
        self.sync_script = env.get("AICADDIE_SYNC_SCRIPT") or ""
        self.public_health_url = env.get("AICADDIE_DEPLOY_PUBLIC_HEALTH_URL") or ""
        self.bootstrap_env_file = env.get("AICADDIE_DEPLOY_BOOTSTRAP_ENV_FILE") or ""
        release_state = env.get("AICADDIE_DEPLOY_RELEASE_STATE") or ""
        if release_state:
            self.release_state_path = Path(release_state)
            if not self.release_state_path.is_absolute():
                raise ConfigError("AICADDIE_DEPLOY_RELEASE_STATE must be an absolute path")
        else:
            home = Path(env["HOME"]) if env.get("HOME") else None
            self.release_state_path = (
                home / DEFAULT_RELEASE_STATE_RELATIVE
                if home is not None and home.is_absolute()
                else None
            )
        self.keep_stopped = _int(env, "AICADDIE_DEPLOY_KEEP_STOPPED", 2, minimum=1)
        self.default_cpus = _float(env, "AICADDIE_DEPLOY_DEFAULT_CPUS", 2.0, positive=True)
        self.default_memory = _int(env, "AICADDIE_DEPLOY_DEFAULT_MEMORY_BYTES", 3 * 1024**3, minimum=1)
        self.health_timeout = _float(env, "AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS", 180.0)
        self.public_timeout = _float(env, "AICADDIE_DEPLOY_PUBLIC_HEALTH_TIMEOUT_SECONDS", 60.0)
        self.lock_timeout = _float(env, "AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS", 600.0)
        self.deadline_seconds = _float(env, "AICADDIE_DEPLOY_DEADLINE_SECONDS", 2280.0)
        self.poll = _float(env, "AICADDIE_DEPLOY_POLL_SECONDS", 2.0)
        self.started = time.monotonic()
        self.release_selection = "legacy"
        self.release_selection_reason = "release_record_unavailable" if self.release_state_path is None else None

    @property
    def local_health_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/api/v2/health"

    @property
    def switch_reserve(self) -> float:
        """Worst case for switching, checking and restoring the previous container."""
        return 2 * self.health_timeout + self.public_timeout + SWITCH_OVERHEAD_SECONDS

    def switch_deadline(self) -> float:
        """Latest monotonic time at which a switch may still start."""
        return self.started + self.deadline_seconds - self.switch_reserve

    def require_time_for_switch(self) -> None:
        if time.monotonic() > self.switch_deadline():
            raise DeployError("not enough time left before AICADDIE_DEPLOY_DEADLINE_SECONDS "
                              "to switch and still restore the previous container")


def _int(env, name, default, *, minimum, maximum=None):
    raw = env.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer") from None
    if value < minimum or (maximum is not None and value > maximum):
        raise ConfigError(f"{name} is out of range")
    return value


def _float(env, name, default, *, positive=False):
    raw = env.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number") from None
    if value != value or value < 0 or (positive and value == 0):
        raise ConfigError(f"{name} is out of range")
    return value


class DeployConfig(Config):
    def __init__(self, env: dict[str, str]):
        super().__init__(env)
        self.db_ready_timeout = _float(env, "AICADDIE_DB_READY_TIMEOUT_SECONDS", 180.0)
        self.db_name = env.get("AICADDIE_DB_CONTAINER") or "garmin-ai-caddie-db-1"
        if not PREFIX_PATTERN.fullmatch(self.db_name):
            raise ConfigError("AICADDIE_DB_CONTAINER must be a valid container name")


class UpConfig(DeployConfig):
    """Recovery settings do not change deploy/rollback configuration."""

    def __init__(self, env: dict[str, str]):
        super().__init__(env)
        self.up_docker_timeout = _float(env, "AICADDIE_UP_DOCKER_TIMEOUT_SECONDS", 300.0)


# ---------------------------------------------------------------------------
# Process and Docker helpers


def child_env(**extra: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in UNSAFE_CHILD_ENV}
    env.update(extra)
    return env


def run(args, *, label, capture=False, quiet=False, env=None, check=True):
    """Run a command; a failure reports only `label`, never the arguments."""
    result = subprocess.run(
        args, cwd=REPO_ROOT, env=env, text=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.DEVNULL if quiet else None,
    )
    if check and result.returncode != 0:
        raise DeployError(f"{label} failed (exit {result.returncode})")
    return result


def docker(*args, label=None, capture=False, quiet=False, check=True):
    if _UP_QUIET:
        capture = True
        quiet = True
    return run(["docker", *args], label=label or f"docker {args[0]}",
               capture=capture, quiet=quiet, check=check)


def _finished_key(value: str) -> tuple[str, float]:
    # Docker trims trailing zeros from the fraction, so compare it numerically.
    match = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?Z", value)
    return (match[1], float(match[2] or 0)) if match else ("", 0.0)


class Container:
    def __init__(self, data: dict):
        self.id = data["id"]
        self.name = data["name"].lstrip("/")
        self.image_id = data.get("image") or ""
        self.labels = data.get("labels") or {}
        self.running = bool(data.get("running"))
        self.finished_key = _finished_key(data.get("finishedAt") or "")
        self.ports = data.get("ports") or {}
        self.network = data.get("network") or ""
        # Older docker projections (and older test fixtures) do not carry
        # NetworkSettings.Networks.  None means the projection predates the
        # self-healing check; an explicit empty mapping means the attachment
        # is missing and must be repaired before start.
        self.networks = data.get("networks")
        self.mounts = data.get("mounts") or []
        self.memory = int(data.get("memory") or 0)
        self.nano_cpus = int(data.get("nanoCpus") or 0)

    @property
    def revision(self) -> str:
        return self.labels.get(REVISION_LABEL, "")

    def publishes(self, port: int) -> bool:
        return any(
            str(binding.get("HostPort")) == str(port)
            for bindings in self.ports.values()
            for binding in (bindings or [])
        )


def list_containers() -> list[Container]:
    # Other projects' `--rm` containers can vanish between `ps` and `inspect`;
    # docker still prints the ones that exist, so a partial answer is kept.
    for _ in range(3):
        ids = docker("ps", "-a", "--no-trunc", "--format", "{{.ID}}", capture=True).stdout.split()
        if not ids:
            return []
        result = docker("inspect", "--format", CONTAINER_FORMAT, *ids,
                        capture=True, quiet=True, check=False)
        containers = [Container(json.loads(line)) for line in result.stdout.splitlines() if line.strip()]
        if result.returncode == 0 or containers:
            return containers
    raise DeployError(f"docker inspect failed (exit {result.returncode})")


def container_env(container: Container) -> list[str]:
    """The container's Env minus entries inherited unchanged from its image,
    so the new image's own ENV defaults take effect."""
    entries = json.loads(docker("inspect", "--format", ENV_FORMAT, container.name, capture=True).stdout) or []
    result = docker("image", "inspect", "--format", ENV_FORMAT, container.image_id,
                    capture=True, quiet=True, check=False)
    image_defaults = set(json.loads(result.stdout) or []) if result.returncode == 0 else set()
    return [entry for entry in entries if entry not in image_defaults]


def image_info(reference: str) -> dict | None:
    result = docker("image", "inspect", "--format", IMAGE_FORMAT, reference,
                    capture=True, quiet=True, check=False)
    if result.returncode != 0:
        return None
    info = json.loads(result.stdout)
    info["labels"] = info.get("labels") or {}
    info["tags"] = info.get("tags") or []
    return info


def image_revision(reference: str) -> str:
    info = image_info(reference)
    return info["labels"].get(REVISION_LABEL, "") if info else ""


def image_label(reference: str, label: str) -> str:
    """Return one image label without exposing the rest of its metadata."""
    info = image_info(reference)
    return info["labels"].get(label, "") if info else ""


def _dependency_section(path: Path) -> bytes:
    """Read the marked dependency part of a Dockerfile.

    Application COPY instructions deliberately live after the end marker. This
    keeps a code-only change out of the dependency image hash while retaining
    the base image and apt/uv/npm instructions as hash inputs.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        raise DeployError("a dependency Dockerfile cannot be read") from None
    start = text.find(DEPENDENCY_START)
    end = text.find(DEPENDENCY_END, start + len(DEPENDENCY_START)) if start >= 0 else -1
    if start < 0 or end < 0:
        raise DeployError("a dependency Dockerfile has no complete dependency section")
    end += len(DEPENDENCY_END)
    return text[start:end].encode("utf-8")


def _hash_inputs(inputs: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, data in inputs:
        name_bytes = name.encode("utf-8")
        digest.update(len(name_bytes).to_bytes(4, "big"))
        digest.update(name_bytes)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _read_dependency_file(name: str) -> tuple[str, bytes]:
    path = REPO_ROOT / name
    try:
        return name, path.read_bytes()
    except OSError:
        raise DeployError("a dependency input file cannot be read") from None


def api_dependency_hash() -> str:
    """Hash only inputs that require rebuilding the API dependency image."""
    inputs = [
        ("node-base-digest", NODE_BASE_DIGEST.encode("ascii")),
        ("uv-base-digest", UV_BASE_DIGEST.encode("ascii")),
        _read_dependency_file("pyproject.toml"),
        _read_dependency_file("uv.lock"),
        _read_dependency_file("package.json"),
        _read_dependency_file("package-lock.json"),
        ("Dockerfile.deps:dependency-section",
         _dependency_section(REPO_ROOT / "Dockerfile.deps")),
    ]
    return _hash_inputs(inputs)


def sync_dependency_hash(api_hash: str | None = None) -> str:
    """Hash the sync-only dependency stage plus the API dependency hash."""
    api_hash = api_hash or api_dependency_hash()
    inputs = [
        ("api-dependency-hash", api_hash.encode("ascii")),
        ("uv-base-digest", UV_BASE_DIGEST.encode("ascii")),
        ("Dockerfile.sync-deps:dependency-section",
         _dependency_section(REPO_ROOT / "Dockerfile.sync-deps")),
    ]
    return _hash_inputs(inputs)


def dependency_hash(kind: str) -> str:
    """Return the named dependency hash used by deploy and acceptance tests."""
    if kind == "api":
        return api_dependency_hash()
    if kind == "sync":
        return sync_dependency_hash()
    raise ValueError("kind must be 'api' or 'sync'")


def fetch_health(url: str) -> dict | None:
    # curl's own error text may echo the URL, so it is discarded.
    result = subprocess.run(
        ["curl", "--fail", "--silent", "--max-time", "5", url],
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def wait_health(url: str, revision: str, timeout: float, poll: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        data = fetch_health(url)
        if data and data.get("status") == "ok" and data.get("revision") == revision:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll)


def wait_database_healthy(cfg: DeployConfig) -> None:
    """Require the exact configured database to be running with a healthcheck."""
    deadline = time.monotonic() + cfg.db_ready_timeout
    while True:
        result = docker(
            "inspect", "--format", DATABASE_FORMAT, cfg.db_name,
            label="database inspect", capture=True, quiet=True, check=False,
        )
        if result.returncode != 0:
            raise DeployError(f"database container {cfg.db_name} is missing")
        try:
            state = json.loads(result.stdout)
        except (TypeError, ValueError):
            raise DeployError(f"database container {cfg.db_name} has no usable health status") from None
        if not isinstance(state, dict):
            raise DeployError(f"database container {cfg.db_name} has no usable health status")
        health = state.get("health")
        if state.get("running") and isinstance(health, dict) and health.get("Status") == "healthy":
            return
        if not state.get("running"):
            reason = f"database container {cfg.db_name} is not running"
        elif not isinstance(health, dict):
            reason = f"database container {cfg.db_name} has no healthcheck"
        else:
            reason = f"database container {cfg.db_name} is not healthy"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DeployError(reason)
        time.sleep(min(cfg.poll, remaining))


class SyncLock:
    """The same flock the sync cron takes, so no sync runs during a switch."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.handle = None

    def __enter__(self):
        self.handle = open(self.cfg.lock_path, "a")
        deadline = min(time.monotonic() + self.cfg.lock_timeout, self.cfg.switch_deadline())
        while True:
            try:
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                log("sync lock acquired")
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    self.handle.close()
                    raise LockTimeout("sync lock was not acquired in time; a sync is still running") from None
                time.sleep(min(max(self.cfg.poll, 0.05), 1.0))

    def __exit__(self, *exc):
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()
        log("sync lock released")
        return False


class PrivateDir:
    """A 0700 tmpfs directory for the env file and helper logs."""

    def __enter__(self):
        base = os.environ.get("XDG_RUNTIME_DIR") or ""
        if not base or not os.path.isdir(base):
            base = "/dev/shm"
        if not os.path.isdir(base):
            raise DeployError("no tmpfs directory (XDG_RUNTIME_DIR or /dev/shm) for the private env file")
        self.path = Path(tempfile.mkdtemp(prefix="aicaddie-agenthub-deploy-", dir=base))
        return self.path

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)
        return False


def shield_signals() -> None:
    """Ignore further signals: a restore, or the tail of a successful switch,
    must not be cut short and reported as untouched."""
    for sig in SIGNALS:
        signal.signal(sig, signal.SIG_IGN)


def install_signal_handlers() -> None:
    def handler(signum, _frame):
        shield_signals()
        raise Interrupted(f"interrupted by signal {signum}")

    for sig in SIGNALS:
        signal.signal(sig, handler)


# ---------------------------------------------------------------------------
# Shared deploy/rollback steps


def find_current(cfg: Config, containers: list[Container]) -> Container | None:
    on_port = [c for c in containers if c.running and c.publishes(cfg.port)]
    foreign = sorted(c.name for c in on_port if not c.name.startswith(cfg.prefix))
    if foreign:
        raise DeployError(f"the configured port is published by a non-release container: {', '.join(foreign)}")
    if len(on_port) > 1:
        names = ", ".join(sorted(c.name for c in on_port))
        raise DeployError(f"multiple running release containers publish the configured port: {names}")
    return on_port[0] if on_port else None


def assert_layout(cfg: Config, container: Container) -> None:
    mounts = container.mounts
    if not (len(mounts) == 1 and mounts[0].get("Name") == cfg.volume
            and mounts[0].get("Destination") == PRIVATE_ROOT and mounts[0].get("RW")):
        raise DeployError(f"{container.name} does not mount exactly the configured private volume read-write at {PRIVATE_ROOT}")
    if container.network != cfg.network:
        raise DeployError(f"{container.name} is not on the configured network")


def previous_release(cfg: Config, containers: list[Container], sha: str) -> Container | None:
    """The most recently stopped release of another revision that could serve again."""
    candidates = sorted((c for c in containers if c.name.startswith(cfg.prefix) and not c.running
                         and c.revision != sha and SHA_PATTERN.fullmatch(c.revision)
                         and c.publishes(cfg.port)),
                        key=lambda c: c.finished_key, reverse=True)
    for candidate in candidates:
        try:
            assert_layout(cfg, candidate)
        except DeployError:
            continue
        return candidate
    return None


def restore_previous(cfg: Config, previous: Container | None) -> bool | None:
    if previous is None:
        log("no previous container to restore")
        return None
    try:
        ensure_network(cfg, previous)
        docker("start", previous.name)
    except DeployError as exc:
        log(f"error: {exc}")
    if wait_health(cfg.local_health_url, previous.revision, cfg.health_timeout, cfg.poll):
        log(f"restored: {previous.name} serves revision {previous.revision}")
        return True
    log(f"error: ROLLBACK NOT CONFIRMED: {previous.name} did not report revision {previous.revision}")
    return False


# ---------------------------------------------------------------------------
# deploy


def _ensure_dependency_image(repository: str, dependency_hash_value: str, *, dockerfile: str,
                             build_args: list[str], label: str,
                             extra_labels: dict[str, str] | None = None) -> str:
    image = f"{repository}:{dependency_hash_value}"
    expected_labels = {DEPENDENCY_HASH_LABEL: dependency_hash_value, **(extra_labels or {})}
    if all(image_label(image, key) == value for key, value in expected_labels.items()):
        log(f"dependency image {image} present; build skipped")
        return image
    log(f"building dependency image {image}")
    args = ["docker", "build"]
    for key, value in expected_labels.items():
        args.extend(["--label", f"{key}={value}"])
    args.extend(["-t", image])
    for value in build_args:
        args.extend(["--build-arg", value])
    args.extend(["-f", dockerfile, "."])
    run(args, label=label)
    if image_label(image, DEPENDENCY_HASH_LABEL) != dependency_hash_value:
        raise DeployError(f"{image} is not labelled with its dependency hash after the build")
    return image


def ensure_images(sha: str) -> dict[str, str]:
    api_image = f"{API_REPOSITORY}:{sha}"
    api_needs_build = image_revision(api_image) != sha
    sync_image = f"{SYNC_REPOSITORY}:{sha}"
    sync_needs_build = image_revision(sync_image) != sha

    # A pre-existing application image is already usable even if it predates
    # this optimisation. Build/publish a named dependency image whenever a
    # new application image (API or sync) needs one.
    api_hash = api_dependency_hash()
    api_deps_image = ""
    if sync_needs_build and not api_needs_build:
        actual_api_hash = image_label(api_image, DEPENDENCY_HASH_LABEL)
        if actual_api_hash != api_hash:
            detail = actual_api_hash or "missing"
            raise DeployError(
                f"{api_image} has dependency hash {detail}; expected {api_hash} "
                "before building sync dependencies"
            )
    if api_needs_build or sync_needs_build:
        api_deps_image = _ensure_dependency_image(
            API_DEPS_REPOSITORY, api_hash, dockerfile="Dockerfile.deps",
            build_args=[], label="api dependency image build",
        )

    if api_needs_build:
        log(f"building api image {api_image}")
        run(["docker", "build", "--label", f"{REVISION_LABEL}={sha}", "-t", api_image,
             "--build-arg", f"DEPS_IMAGE={api_deps_image}",
             "-f", "Dockerfile", "."], label="api image build")
        if image_revision(api_image) != sha:
            raise DeployError(f"{api_image} is not labelled with revision {sha} after the build")
        if image_label(api_image, DEPENDENCY_HASH_LABEL) != api_hash:
            raise DeployError(f"{api_image} did not inherit dependency hash {api_hash} from {api_deps_image}")
    else:
        log(f"api image {api_image} present; build skipped")

    sync_hash = sync_dependency_hash(api_hash)
    if sync_needs_build:
        sync_deps_image = _ensure_dependency_image(
            SYNC_DEPS_REPOSITORY, sync_hash, dockerfile="Dockerfile.sync-deps",
            build_args=[f"API_IMAGE={api_deps_image}"], label="sync dependency image build",
            extra_labels={API_DEPENDENCY_HASH_LABEL: api_hash},
        )
        log(f"building sync image {sync_image}")
        run(["bash", str(SYNC_BUILD_SCRIPT)], label="sync image build",
            env=child_env(API_IMAGE=api_image, SYNC_DEPS_IMAGE=sync_deps_image))
        if image_revision(sync_image) != sha:
            raise DeployError(f"{sync_image} is not labelled with revision {sha} after the build")
    else:
        log(f"sync image {sync_image} present; build skipped")
    return {"api": api_hash, "sync": sync_hash}


def read_env_file(path: str) -> list[str]:
    """Parse a docker --env-file style file (KEY=VALUE, `#` comments)."""
    entries = []
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        raise DeployError("the bootstrap env file cannot be read") from None
    for number, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise DeployError(f"bootstrap env file line {number} is not KEY=VALUE")
        entries.append(stripped)
    return entries


def prepare_env(entries: list[str], sha: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for entry in entries:
        if "=" not in entry:
            continue
        key, value = entry.split("=", 1)
        values[key] = value
    values.update(FIXED_ENV, AI_CADDIE_BUILD_REVISION=sha)
    for key, value in values.items():
        if not key or any(ch in key for ch in "= \t\r\n") or "\n" in value or "\r" in value:
            raise DeployError("an environment entry cannot be represented in an env file")
    return values


def write_env_file(directory: Path, values: dict[str, str]) -> Path:
    path = directory / "api.env"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.writelines(f"{key}={value}\n" for key, value in values.items())
    return path


def run_api_container(cfg: Config, private: Path, name: str, sha: str,
                      values: dict[str, str], cpus: float, memory: int) -> None:
    # Written only now, so the credentials file never outlives this call.
    env_file = write_env_file(private, values)
    try:
        docker("run", "-d", "--init", "--pull", "never", "--name", name,
               "--restart", "no",
               "--cpus", str(cpus), "--memory", str(memory),
               "--network", cfg.network,
               "--log-driver", "json-file", "--log-opt", "max-size=10m", "--log-opt", "max-file=3",
               "--label", f"{REVISION_LABEL}={sha}",
               "--env-file", str(env_file),
               "-p", f"127.0.0.1:{cfg.port}:{CONTAINER_PORT}",
               "-v", f"{cfg.volume}:{PRIVATE_ROOT}",
               f"{API_REPOSITORY}:{sha}", capture=True)
    finally:
        env_file.unlink(missing_ok=True)


def post_checks(cfg: Config, container: str, sha: str, private: Path) -> None:
    run(["bash", str(GATE_SCRIPT)], label="deployment gate (check-only)",
        env=child_env(AICADDIE_DEPLOY_GATE_CHECK_ONLY="1",
                      AICADDIE_API_CONTAINER=container,
                      AICADDIE_API_PORT=str(cfg.port)))
    log("deployment gate (check-only): ok")

    if cfg.sync_script:
        # A private lock/log: this process already holds the real sync lock,
        # and a busy lock would make the sync script skip with exit 0.
        # Its alert state is private too, so a deploy-time failure cannot make
        # the next real sync send a "recovered" alert.
        sync_log = private / "sync-check.log"
        result = run(["bash", cfg.sync_script], label="sync contract (check-only)", check=False,
                     env=child_env(AICADDIE_SYNC_CHECK_ONLY="1",
                                   AICADDIE_API_CONTAINER=container,
                                   AICADDIE_API_PORT=str(cfg.port),
                                   AICADDIE_SYNC_LOCK=str(private / "sync-check.lock"),
                                   AICADDIE_SYNC_LOG=str(sync_log),
                                   AICADDIE_SYNC_ALERT_STATE=str(private / "sync-alert.state")))
        lines = sync_log.read_text().splitlines() if sync_log.exists() else []
        if result.returncode != 0 or not any(line.endswith(SYNC_CHECK_MARKER) for line in lines):
            # The check-only log holds only timestamps, names, revisions and reasons.
            for line in lines[-20:]:
                log(f"sync check: {line}")
            raise DeployError(f"sync contract (check-only) failed (exit {result.returncode})")
        log("sync contract (check-only): ok")
    else:
        log("sync contract (check-only): skipped (AICADDIE_SYNC_SCRIPT not configured)")

    if cfg.public_health_url:
        if not wait_health(cfg.public_health_url, sha, cfg.public_timeout, cfg.poll):
            raise DeployError(f"public health did not report revision {sha}")
        log("public health: ok")
    else:
        log("public health: skipped (AICADDIE_DEPLOY_PUBLIC_HEALTH_URL not configured)")


def check_deploy_source(cfg: Config, current: Container | None) -> None:
    if current is None:
        if not cfg.bootstrap_env_file:
            raise DeployError("no running release container publishes the configured port "
                              "(set AICADDIE_DEPLOY_BOOTSTRAP_ENV_FILE for a first deploy)")
    else:
        assert_layout(cfg, current)


def deploy(cfg: Config, sha: str) -> str:
    new_name = f"{cfg.prefix}{sha[:8]}"
    # Fail fast before the long image builds; everything is re-read under the lock.
    check_deploy_source(cfg, find_current(cfg, list_containers()))
    wait_database_healthy(cfg)
    dependency_hashes = ensure_images(sha)

    with PrivateDir() as private, SyncLock(cfg):
        wait_database_healthy(cfg)
        containers = list_containers()
        current = find_current(cfg, containers)
        normalize_restart_policy(cfg, containers)
        if current is not None and current.revision == sha:
            verify_live(cfg, sha, current, containers, private)
            deployed = current.name
        else:
            switch(cfg, sha, new_name, current, containers, private)
            deployed = new_name
        try:
            cleanup(cfg, dependency_hashes)
        except Exception as exc:  # the new release is live; cleanup is best effort
            reason = str(exc) if isinstance(exc, DeployError) else type(exc).__name__
            log(f"warning: cleanup incomplete: {reason}")
        write_release_state(cfg, sha)
    return deployed


def verify_live(cfg: Config, sha: str, current: Container, containers: list[Container],
                private: Path) -> None:
    """Idempotent re-run: the revision already serves, so only re-check it."""
    log(f"{current.name} already runs revision {sha}; verifying only")
    try:
        if not wait_health(cfg.local_health_url, sha, cfg.health_timeout, cfg.poll):
            raise DeployError(f"{current.name} runs revision {sha} but its health check fails")
        post_checks(cfg, current.name, sha, private)
    except BaseException as exc:
        shield_signals()
        reason = str(exc) if isinstance(exc, DeployError) else f"unexpected {type(exc).__name__}"
        previous = previous_release(cfg, containers, sha)
        if previous is None:
            log(f"error: {reason}; no stopped previous release to restore, {current.name} left running")
            raise CutoverFailed(reason, False) from None
        log(f"error: {reason}; restoring {previous.name}")
        docker("stop", "--time", STOP_TIMEOUT_SECONDS, current.name, capture=True, check=False)
        restored = restore_previous(cfg, previous)
        if not restored:
            docker("stop", "--time", STOP_TIMEOUT_SECONDS, previous.name, capture=True, check=False)
            try:
                ensure_network(cfg, current)
                docker("start", current.name, capture=True, check=False)
            except BaseException as restore_exc:
                log(f"error: failed to re-start {current.name} after restore failure: {type(restore_exc).__name__}")
        raise CutoverFailed(reason, restored) from None
    shield_signals()


def switch(cfg: Config, sha: str, new_name: str, current: Container | None,
           containers: list[Container], private: Path) -> None:
    check_deploy_source(cfg, current)
    # A concurrent cleanup (for example a drill with its own lock) could have
    # removed the images since they were built.
    for image in (f"{API_REPOSITORY}:{sha}", f"{SYNC_REPOSITORY}:{sha}"):
        if image_revision(image) != sha:
            raise DeployError(f"{image} disappeared before the switch; re-run to rebuild it")
    if current is None:
        log("no current container; bootstrap deploy from the configured env file")
        values = prepare_env(read_env_file(cfg.bootstrap_env_file), sha)
        cpus, memory = cfg.default_cpus, cfg.default_memory
    else:
        values = prepare_env(container_env(current), sha)
        cpus = current.nano_cpus / 1e9 if current.nano_cpus else cfg.default_cpus
        memory = current.memory or cfg.default_memory

    residual = next((c for c in containers if c.name == new_name), None)
    if residual is not None:
        if residual.running or residual.revision != sha:
            raise DeployError(f"{new_name} already exists and is not a stopped revision-{sha[:8]} container")
        log(f"removing stopped residual {new_name}")
        docker("rm", "-v", new_name, capture=True)

    cfg.require_time_for_switch()
    try:
        if current is not None:
            log(f"stopping {current.name}")
            docker("stop", "--time", STOP_TIMEOUT_SECONDS, current.name, capture=True)
        log(f"starting {new_name}")
        run_api_container(cfg, private, new_name, sha, values, cpus, memory)
        if not wait_health(cfg.local_health_url, sha, cfg.health_timeout, cfg.poll):
            raise DeployError(f"{new_name} did not report status=ok revision={sha}")
        log(f"{new_name} healthy")
        post_checks(cfg, new_name, sha, private)
    except BaseException as exc:
        shield_signals()
        reason = str(exc) if isinstance(exc, DeployError) else f"unexpected {type(exc).__name__}"
        log(f"error: {reason}; restoring the previous container")
        removed = docker("rm", "-f", "-v", new_name, capture=True, quiet=True, check=False)
        if removed.returncode == 0:
            log(f"removed {new_name}")
        restored = restore_previous(cfg, current)
        raise CutoverFailed(reason, restored) from None
    shield_signals()


def _dependency_image_refs() -> list[str]:
    """List only the two named dependency repositories owned by this deploy."""
    result = docker("image", "ls", "--format", "{{.Repository}}:{{.Tag}}|{{.CreatedAt}}",
                    capture=True, quiet=True, check=False)
    if result.returncode != 0:
        log("cleanup: warning: dependency image listing failed; leaving dependency tags unchanged")
        return []
    entries: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        ref, _, created = line.strip().partition("|")
        if ref.startswith(f"{API_DEPS_REPOSITORY}:") or ref.startswith(f"{SYNC_DEPS_REPOSITORY}:"):
            if ref.rsplit(":", 1)[-1] and ref.rsplit(":", 1)[-1] != "<none>":
                entries.append((ref, created))
    entries.sort(key=lambda item: item[1], reverse=True)
    return [ref for ref, _created in entries]


def cleanup_dependency_images(current_hashes: dict[str, str]) -> None:
    """Keep the current hash and newest other hash in each dependency repo."""
    refs = _dependency_image_refs()
    if not refs:
        return
    current_by_repo = {
        API_DEPS_REPOSITORY: current_hashes.get(API_DEPS_REPOSITORY) or current_hashes.get("api", ""),
        SYNC_DEPS_REPOSITORY: current_hashes.get(SYNC_DEPS_REPOSITORY) or current_hashes.get("sync", ""),
    }
    keep: set[str] = set()
    # Docker's image ls ordering is newest-first by default. Keep the explicit
    # current hash even when it is older, then the newest other hash as the
    # rollback dependency. Never inspect or remove another repository's tags.
    for repository, current_hash in current_by_repo.items():
        repo_refs = [ref for ref in refs if ref.startswith(repository + ":")]
        current_ref = f"{repository}:{current_hash}" if current_hash else ""
        if current_ref in repo_refs:
            keep.add(current_ref)
        for ref in repo_refs:
            if ref not in keep:
                keep.add(ref)
                break
    for ref in refs:
        if ref in keep:
            continue
        removed = docker("rmi", ref, capture=True, check=False)
        if removed.returncode == 0:
            log(f"cleanup: removed dependency image {ref}")
        else:
            log(f"cleanup: warning: could not remove dependency image {ref}")


def _application_image_refs() -> list[str]:
    result = docker("image", "ls", "--format", "{{.Repository}}:{{.Tag}}",
                    capture=True, quiet=True, check=False)
    if result.returncode != 0:
        log("cleanup: warning: application image listing failed; leaving orphan tags unchanged")
        return []
    refs = []
    for line in result.stdout.splitlines():
        ref = line.strip()
        repository, _, tag = ref.rpartition(":")
        if repository in {API_REPOSITORY, SYNC_REPOSITORY} and SHA_PATTERN.fullmatch(tag):
            refs.append(ref)
    return refs


def cleanup_orphan_application_images(cfg: Config, containers: list[Container]) -> None:
    """Remove unreferenced old API/sync tags while protecting rollback images."""
    stopped = sorted((c for c in containers if c.name.startswith(cfg.prefix) and not c.running),
                     key=lambda c: c.finished_key, reverse=True)
    retained_revisions = {
        c.revision for c in containers
        if c.running and c.name.startswith(cfg.prefix)
    }
    retained_revisions.update(c.revision for c in stopped[:cfg.keep_stopped] if c.revision)
    used_image_ids = {c.image_id for c in containers if c.image_id}
    for ref in _application_image_refs():
        repository, _, tag = ref.rpartition(":")
        if repository not in {API_REPOSITORY, SYNC_REPOSITORY} or tag in retained_revisions:
            continue
        info = image_info(ref)
        if not info or info["id"] in used_image_ids:
            continue
        repositories = {item.rsplit(":", 1)[0] for item in info["tags"]}
        if not repositories <= {API_REPOSITORY, SYNC_REPOSITORY}:
            continue
        removed = docker("rmi", ref, capture=True, check=False)
        if removed.returncode == 0:
            log(f"cleanup: removed orphan image {ref}")
        else:
            log(f"cleanup: warning: could not remove orphan image {ref}")


def cleanup(cfg: Config, dependency_hashes: dict[str, str]) -> None:
    containers = list_containers()
    remaining = containers
    stopped = sorted((c for c in containers if c.name.startswith(cfg.prefix) and not c.running),
                     key=lambda c: c.finished_key, reverse=True)
    doomed = stopped[cfg.keep_stopped:]
    if not doomed:
        log(f"cleanup: nothing to remove ({len(stopped)} stopped release container(s) kept)")
    else:
        for container in doomed:
            docker("rm", "-v", container.name, capture=True)
            log(f"cleanup: removed container {container.name}")

        doomed_ids = {c.id for c in doomed}
        remaining = [c for c in containers if c.id not in doomed_ids]
        used_images = {c.image_id for c in remaining}
        used_revisions = {c.revision for c in remaining if c.revision}
        handled: set[str] = set()
        for container in doomed:
            candidates = [image_info(container.image_id)] if container.image_id else []
            if SHA_PATTERN.fullmatch(container.revision) and container.revision not in used_revisions:
                candidates.append(image_info(f"{SYNC_REPOSITORY}:{container.revision}"))
            for info in candidates:
                if not info or info["id"] in handled or info["id"] in used_images:
                    continue
                handled.add(info["id"])
                repositories = {tag.rsplit(":", 1)[0] for tag in info["tags"]}
                if not info["tags"] or not repositories <= {API_REPOSITORY, SYNC_REPOSITORY}:
                    log(f"cleanup: kept image {info['id'][:19]} (untagged or not an api/sync image)")
                    continue
                for tag in info["tags"]:
                    repository, _, tag_value = tag.rpartition(":")
                    if repository not in {API_REPOSITORY, SYNC_REPOSITORY} or not SHA_PATTERN.fullmatch(tag_value):
                        continue
                    removed = docker("rmi", tag, capture=True, check=False)
                    if removed.returncode == 0:
                        log(f"cleanup: removed image {tag}")
                    else:
                        log(f"cleanup: warning: could not remove image {tag}")
    cleanup_dependency_images(dependency_hashes)
    cleanup_orphan_application_images(cfg, remaining)


# ---------------------------------------------------------------------------
# rollback


def select_rollback(cfg: Config, sha: str) -> tuple[Container | None, Container | None]:
    """Return (current, target); target is None when sha already serves."""
    containers = list_containers()
    current = find_current(cfg, containers)
    if current is not None and current.revision == sha:
        return current, None
    targets = sorted((c for c in containers if c.name.startswith(cfg.prefix)
                      and not c.running and c.revision == sha),
                     key=lambda c: c.finished_key, reverse=True)
    if not targets:
        raise DeployError(f"no stopped release container is labelled with revision {sha}")
    target = targets[0]
    assert_layout(cfg, target)
    if not target.publishes(cfg.port):
        raise DeployError(f"{target.name} does not publish the configured port")
    sync_image = f"{SYNC_REPOSITORY}:{sha}"
    if image_revision(sync_image) != sha:
        raise DeployError(f"{sync_image} is missing or mislabelled; the sync cron would refuse this revision")
    return current, target


def rollback(cfg: Config, sha: str) -> str:
    select_rollback(cfg, sha)
    with SyncLock(cfg):
        wait_database_healthy(cfg)
        current, target = select_rollback(cfg, sha)
        normalize_restart_policy(cfg, list_containers())
        if target is None:
            if not wait_health(cfg.local_health_url, sha, cfg.health_timeout, cfg.poll):
                raise DeployError(f"{current.name} runs revision {sha} but its health check fails")
            log(f"{current.name} already runs revision {sha}")
            write_release_state(cfg, sha)
            return current.name

        cfg.require_time_for_switch()
        try:
            if current is not None:
                log(f"stopping {current.name}")
                docker("stop", "--time", STOP_TIMEOUT_SECONDS, current.name, capture=True)
            log(f"starting {target.name}")
            ensure_network(cfg, target)
            docker("start", target.name, capture=True)
            if not wait_health(cfg.local_health_url, sha, cfg.health_timeout, cfg.poll):
                raise DeployError(f"{target.name} did not report status=ok revision={sha}")
        except BaseException as exc:
            shield_signals()
            reason = str(exc) if isinstance(exc, DeployError) else f"unexpected {type(exc).__name__}"
            log(f"error: {reason}; restoring the previous container")
            docker("stop", "--time", STOP_TIMEOUT_SECONDS, target.name, capture=True, quiet=True, check=False)
            restored = restore_previous(cfg, current)
            raise CutoverFailed(reason, restored) from None
        shield_signals()
        write_release_state(cfg, sha)
        return target.name


def normalize_restart_policy(cfg: Config, containers: list[Container]) -> None:
    """Make every release container independently safe across daemon restarts."""
    for container in containers:
        if container.name.startswith(cfg.prefix):
            docker("update", "--restart=no", container.name, label="release restart policy")


def ensure_network(cfg: Config, container: Container) -> None:
    """Repair a missing runtime network attachment before starting a container."""
    if container.networks is None:
        # Projection compatibility for old callers/tests. Docker installations
        # using CONTAINER_FORMAT always provide an explicit mapping.
        attached = container.network == cfg.network
    else:
        attached = isinstance(container.networks, dict) and cfg.network in container.networks
    if attached:
        return
    log(f"connecting {container.name} to configured network before start")
    docker("network", "connect", cfg.network, container.name, label="network connect")


def write_release_state(cfg: Config, revision: str) -> None:
    """Atomically publish the revision selected by the last successful action."""
    path = cfg.release_state_path
    if path is None:
        log("HOME is unavailable; release record not written")
        return
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = {
            "revision": revision,
            "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log("WARNING: release record write failed and stale record could not be removed")
        else:
            log("WARNING: release record write failed; stale record removed")
        log("release record could not be written; continuing without it")


def read_release_state(cfg: Config) -> str | None:
    if cfg.release_state_path is None:
        log("HOME is unavailable; using legacy stopped-container selection")
        cfg.release_selection = "legacy"
        cfg.release_selection_reason = "release_record_unavailable"
        return None
    try:
        data = json.loads(cfg.release_state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        cfg.release_selection = "legacy"
        cfg.release_selection_reason = "release_record_missing"
        return None
    except OSError:
        log("release state is unreadable; falling back to stopped-container selection")
        cfg.release_selection = "legacy"
        cfg.release_selection_reason = "release_record_unavailable"
        return None
    except (ValueError, TypeError):
        log("release state is invalid; falling back to stopped-container selection")
        cfg.release_selection = "legacy"
        cfg.release_selection_reason = "release_record_invalid"
        return None
    revision = data.get("revision") if isinstance(data, dict) else None
    if not isinstance(revision, str) or not SHA_PATTERN.fullmatch(revision):
        log("release state has no valid revision; falling back to stopped-container selection")
        cfg.release_selection = "legacy"
        cfg.release_selection_reason = "release_record_invalid"
        return None
    cfg.release_selection = "record"
    cfg.release_selection_reason = None
    return revision


# ---------------------------------------------------------------------------
# Ordered recovery of existing containers


def wait_docker(timeout: float, poll: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        result = docker("info", label="docker daemon", capture=True, quiet=True, check=False)
        if result.returncode == 0:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll)


def wait_up_database(cfg: UpConfig) -> None:
    deadline = time.monotonic() + cfg.db_ready_timeout
    started = False
    while True:
        result = docker(
            "inspect", "--format",
            '{"running":{{json .State.Running}},"health":{{json .State.Health}}}',
            cfg.db_name, label="database inspect", capture=True, quiet=True, check=False,
        )
        if result.returncode != 0:
            raise UpFailed("database", cfg.db_name, "database is missing", reason="database_missing")
        state = json.loads(result.stdout)
        if state["running"] and (state.get("health") or {}).get("Status") == "healthy":
            return
        if not state["running"] and not started:
            log(f"starting {cfg.db_name}")
            try:
                docker("start", cfg.db_name, label="database start", capture=True, quiet=True)
            except DeployError:
                raise UpFailed("database", cfg.db_name, "database did not become healthy",
                                reason="database_unhealthy") from None
            started = True
        if time.monotonic() >= deadline:
            raise UpFailed("database", cfg.db_name, "database did not become healthy",
                           reason="database_unhealthy")
        time.sleep(cfg.poll)


def assert_up_release(cfg: Config, container: Container) -> None:
    revision = container.revision
    if not isinstance(revision, str) or not SHA_PATTERN.fullmatch(revision):
        raise DeployError(f"{container.name} has an invalid source revision label")
    assert_layout(cfg, container)


def select_up_api(cfg: Config, containers: list[Container]) -> Container | None:
    recorded = read_release_state(cfg)
    if recorded is not None:
        recorded_candidates = [
            candidate for candidate in containers
            if candidate.name.startswith(cfg.prefix)
            and candidate.revision == recorded
            and candidate.publishes(cfg.port)
        ]
        valid_recorded = []
        for candidate in recorded_candidates:
            try:
                assert_up_release(cfg, candidate)
            except DeployError:
                continue
            valid_recorded.append(candidate)
        if valid_recorded:
            running = [candidate for candidate in valid_recorded if candidate.running]
            if running:
                return running[0]
            return max(valid_recorded, key=lambda candidate: candidate.finished_key)
        cfg.release_selection = "legacy"
        cfg.release_selection_reason = "release_record_missing"
        log(f"recorded release {recorded} is missing or invalid; falling back to stopped-container selection")
    try:
        current = find_current(cfg, containers)
    except DeployError:
        raise UpFailed("api", "none", "no valid release candidate",
                       reason="no_release_candidate") from None
    if current is not None:
        try:
            assert_up_release(cfg, current)
        except DeployError:
            raise UpFailed("api", current.name, "no valid release candidate",
                           reason="no_release_candidate") from None
        return current
    candidates = []
    for candidate in containers:
        if candidate.running or not candidate.name.startswith(cfg.prefix) or not candidate.publishes(cfg.port):
            continue
        try:
            assert_up_release(cfg, candidate)
        except DeployError:
            continue
        candidates.append(candidate)
    if not candidates:
        return None
    latest = max(candidates, key=lambda c: c.finished_key)
    tied = sorted(c.name for c in candidates if c.finished_key == latest.finished_key)
    if len(tied) > 1:
        raise UpFailed("api", "none", "multiple latest stopped release candidates",
                       reason="release_tie", candidates=",".join(tied))
    return latest


def up(cfg: UpConfig) -> Container:
    part, container = "docker", "none"
    global _UP_QUIET
    was_quiet = _UP_QUIET
    _UP_QUIET = True
    try:
        if not wait_docker(cfg.up_docker_timeout, cfg.poll):
            raise UpFailed("docker", "none", "Docker daemon unavailable",
                           reason="docker_unavailable")
        part, container = "database", cfg.db_name
        wait_up_database(cfg)
        part, container = "api", "none"
        api = select_up_api(cfg, list_containers())
        selection_fields = {"action": "up", "selection": cfg.release_selection}
        if cfg.release_selection_reason:
            selection_fields["reason"] = cfg.release_selection_reason
        up_line(**selection_fields)
        if api is None:
            raise UpFailed("api", "none", "no valid release candidate",
                           reason="no_release_candidate")
        container = api.name
        previous_api = None
        if not api.running:
            with SyncLock(cfg):
                # A deploy can change the release set while recovery waits for this lock.
                container = "none"
                api = select_up_api(cfg, list_containers())
                if api is None:
                    raise UpFailed("api", "none", "no valid release candidate",
                                   reason="no_release_candidate")
                container = api.name
                if not api.running:
                    try:
                        current = find_current(cfg, list_containers())
                    except DeployError:
                        raise UpFailed("api", "none", "no valid release candidate",
                                       reason="no_release_candidate") from None
                    if current is not None and current.name != api.name:
                        previous_api = current
                        up_line(action="up", selection="record", container=current.name,
                                revision=api.revision)
                        log(f"stopping {current.name} for recorded release {api.revision}")
                        docker("stop", "--time", STOP_TIMEOUT_SECONDS, current.name,
                               label="API stop", capture=True, quiet=True)
                    log(f"starting {api.name}")
                    ensure_network(cfg, api)
                    docker("start", api.name, label="API start", capture=True, quiet=True)
        if not wait_health(cfg.local_health_url, api.revision, cfg.health_timeout, cfg.poll):
            if previous_api is not None:
                docker("stop", api.name, label="API stop after failed health", capture=True,
                       quiet=True, check=False)
                try:
                    ensure_network(cfg, previous_api)
                    docker("start", previous_api.name, label="API restore after failed health",
                           capture=True, quiet=True, check=False)
                except BaseException as restore_exc:
                    log(f"error: failed to restore {previous_api.name}: {type(restore_exc).__name__}")
            raise UpFailed("api", api.name, "API health check failed", reason="api_unhealthy")
        return api
    except UpFailed:
        raise
    except LockTimeout:
        raise UpFailed("api", container, "sync lock timeout", reason="lock_timeout") from None
    except BaseException:
        raise UpFailed(part, container, "unexpected recovery failure", reason="unexpected") from None
    finally:
        _UP_QUIET = was_quiet


# ---------------------------------------------------------------------------


USAGE = "usage: agenthub_deploy.py {deploy|rollback} <40-lowercase-hex-sha> | up"


def main(argv: list[str]) -> int:
    is_up = argv == ["up"]
    if not is_up and (len(argv) != 2 or argv[0] not in ("deploy", "rollback")
                      or not SHA_PATTERN.fullmatch(argv[1])):
        print(USAGE, file=sys.stderr, flush=True)
        return EXIT_USAGE
    action, sha = ("up", "") if is_up else argv
    if not is_up:
        expected = os.environ.get("AGENTHUB_DEPLOY_SHA")
        if expected and expected != sha:
            print("error: argument sha does not match AGENTHUB_DEPLOY_SHA", file=sys.stderr, flush=True)
            return EXIT_USAGE
    try:
        cfg = UpConfig(dict(os.environ)) if is_up else DeployConfig(dict(os.environ))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr, flush=True)
        return EXIT_USAGE

    install_signal_handlers()
    started = time.monotonic()
    if is_up:
        up_line(action="up")
        try:
            api = up(cfg)
        except UpFailed as exc:
            up_line(result="failed", action="up", part=exc.part, container=exc.container,
                    elapsed_s=f"{time.monotonic() - started:.1f}", reason=exc.reason,
                    candidates=exc.candidates, selection=cfg.release_selection)
            return EXIT_FAILED
        except BaseException:
            up_line(result="failed", action="up", part="api", container="none",
                    elapsed_s=f"{time.monotonic() - started:.1f}", reason="unexpected",
                    selection=cfg.release_selection)
            return EXIT_FAILED
        up_line(result="ok", action="up", container=api.name, revision=api.revision,
                elapsed_s=f"{time.monotonic() - started:.1f}", selection=cfg.release_selection)
        return EXIT_OK
    log(f"action={action} revision={sha}")
    try:
        container = deploy(cfg, sha) if action == "deploy" else rollback(cfg, sha)
    except CutoverFailed as exc:
        code = EXIT_UNRECOVERED if exc.restored is False else EXIT_FAILED
        restored = "none" if exc.restored is None else str(exc.restored).lower()
        log(f"result=failed action={action} revision={sha} previous_restored={restored} "
            f"elapsed_s={time.monotonic() - started:.1f} reason={exc}")
        return code
    except DeployError as exc:
        log(f"result=failed action={action} revision={sha} previous_untouched=true "
            f"elapsed_s={time.monotonic() - started:.1f} reason={exc}")
        return EXIT_FAILED
    except Exception as exc:  # report the location, not a message that may carry values
        frame = traceback.extract_tb(exc.__traceback__)[-1]
        log(f"result=failed action={action} revision={sha} previous_untouched=true "
            f"reason=unexpected {type(exc).__name__} in {frame.name} line {frame.lineno}")
        return EXIT_FAILED
    log(f"result=ok action={action} revision={sha} container={container} "
        f"elapsed_s={time.monotonic() - started:.1f}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
