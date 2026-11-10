"""A deploy only goes live with a sync image of the same revision, rolls back to a healthy old
release on any failure, leaves exactly one release able to restart on its own, and publishes
the API on the loopback host only.

Everything enters through the operator command line `ops/agenthub_deploy.py:main`
(deploy / rollback / up). Docker and the health probe are replaced by an in-memory
fake that keeps containers, images, labels, restart policies, port bindings and
running state, so each docker call the deploy makes changes the model it later reads.
"""
import ipaddress
import json
import os
import signal
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlparse

from ops import agenthub_deploy as cli

OLD = "a1" * 20
NEW = "b2" * 20
THIRD = "c3" * 20
REMNANT = "d4" * 20
PORT = 39055
DB_NAME = "garmin-ai-caddie-db-1"
NETWORK = "garmin-ai-caddie_default"
VOLUME = "garmin-ai-caddie_ai-caddie-private"
PREFIX = "aicaddie-release-"
IMAGE_ENV = ["PATH=/usr/local/bin:/usr/bin", "PYTHONUNBUFFERED=1"]


def release_name(sha: str) -> str:
    return f"{PREFIX}{sha[:8]}"


class FakeDocker:
    """In-memory docker daemon plus the two helper scripts the deploy shells out to."""

    def __init__(self):
        self.containers: dict[str, dict] = {}  # name -> state; insertion order = creation order
        self.images: dict[str, dict] = {}  # image id -> {"tags": [...], "labels": {...}, "env": [...]}
        self.fail: set[str] = set()  # e.g. "run", "api-build", "sync-build", "gate", "start:<name>", "ps"
        self.sync_build_revision: str | None = None  # label the sync build stamps (None: the asked revision)
        self.reports: dict[str, str] = {}  # revision -> revision its health endpoint reports
        self.unhealthy: set[str] = set()
        self.db = {"running": True, "health": "healthy"}
        self.calls: list[list[str]] = []
        self.gate_runs: list[dict] = []
        self._tick = 0
        self._serial = 0

    # -- model helpers -------------------------------------------------
    def _next(self) -> int:
        self._serial += 1
        return self._serial

    def _finished(self) -> str:
        self._tick += 1
        return f"2026-11-10T08:{self._tick // 60:02d}:{self._tick % 60:02d}.5Z"

    def image_by_ref(self, ref: str) -> dict | None:
        if ref in self.images:
            return self.images[ref]
        return next((img for img in self.images.values() if ref in img["tags"]), None)

    def rmi_all(self, ref: str) -> None:
        image = self.image_by_ref(ref)
        if image is not None and ref in image["tags"]:
            image["tags"].remove(ref)

    def add_image(self, tag: str, labels: dict, env=None) -> str:
        for img in self.images.values():
            if tag in img["tags"]:
                img["tags"].remove(tag)
        image_id = f"sha256:{self._next():064x}"
        self.images[image_id] = {"id": image_id, "tags": [tag], "labels": dict(labels),
                                 "env": list(IMAGE_ENV if env is None else env), "created": self._tick}
        return image_id

    def add_release(self, sha: str, *, running: bool, policy: str, loopback: str, api_hash: str,
                    sync_image: bool = True) -> str:
        image_id = self.add_image(f"{cli.API_REPOSITORY}:{sha}",
                                  {cli.REVISION_LABEL: sha, cli.DEPENDENCY_HASH_LABEL: api_hash})
        if sync_image:
            self.add_image(f"{cli.SYNC_REPOSITORY}:{sha}", {cli.REVISION_LABEL: sha})
        name = release_name(sha)
        self.containers[name] = self._container(
            name, image_id, {cli.REVISION_LABEL: sha}, policy,
            [(loopback, str(PORT), cli.CONTAINER_PORT)],
            IMAGE_ENV + ["AI_CADDIE_SESSION_SECRET=kept-across-releases", f"AI_CADDIE_BUILD_REVISION={sha}"])
        if running:
            self.containers[name]["running"] = True
        else:
            self.containers[name]["finishedAt"] = self._finished()
        return name

    def _container(self, name, image_id, labels, policy, ports, env) -> dict:
        bindings: dict[str, list] = {}
        for host, host_port, container_port in ports:
            bindings.setdefault(f"{container_port}/tcp", []).append({"HostIp": host, "HostPort": host_port})
        return {
            "id": f"{self._next():064x}", "name": name, "image": image_id, "labels": dict(labels),
            "running": False, "policy": policy, "finishedAt": "0001-01-01T00:00:00Z",
            "ports": bindings, "network": NETWORK, "networks": {NETWORK: {}},
            "mounts": [{"Name": VOLUME, "Destination": cli.PRIVATE_ROOT, "RW": True}],
            "env": list(env), "memory": 2 * 1024**3, "nanoCpus": 2 * 10**9,
        }

    def _port_holder(self, container: dict) -> dict | None:
        ports = {b["HostPort"] for bs in container["ports"].values() for b in bs}
        return next((other for other in self.containers.values()
                     if other is not container and other["running"]
                     and ports & {b["HostPort"] for bs in other["ports"].values() for b in bs}), None)

    def start(self, name: str) -> int:
        container = self.containers.get(name)
        if container is None or f"start:{name}" in self.fail or self._port_holder(container):
            return 1
        container["running"] = True
        return 0

    def stop(self, name: str) -> int:
        container = self.containers.get(name)
        if container is None:
            return 1
        if container["running"]:
            container["running"] = False
            container["finishedAt"] = self._finished()
        return 0

    def daemon_restart(self) -> None:
        """Host reboot: every container stops; those with a restart policy start again in creation order."""
        for container in self.containers.values():
            self.stop(container["name"])
        for container in self.containers.values():
            if container["policy"] != "no":
                self.start(container["name"])

    def auto_restart(self) -> list[str]:
        return sorted(n for n, c in self.containers.items() if n.startswith(PREFIX) and c["policy"] != "no")

    def running(self) -> list[str]:
        return sorted(n for n, c in self.containers.items() if c["running"])

    def serving(self) -> str | None:
        data = self.fetch_health(f"http://loopback:{PORT}/api/v2/health")
        return data["revision"] if data else None

    def bindings(self) -> list[tuple[str, str, str]]:
        return [(name, b["HostIp"], b["HostPort"])
                for name, c in self.containers.items() for bs in c["ports"].values() for b in bs]

    # -- the two seams -------------------------------------------------
    def fetch_health(self, url: str) -> dict | None:
        port = str(urlparse(url).port)
        for container in self.containers.values():
            published = {b["HostPort"] for bs in container["ports"].values() for b in bs}
            if container["running"] and port in published:
                revision = container["labels"].get(cli.REVISION_LABEL, "")
                if revision in self.unhealthy:
                    return None
                return {"status": "ok", "revision": self.reports.get(revision, revision)}
        return None

    def run(self, args, *, label, capture=False, quiet=False, env=None, check=True):
        args = [str(a) for a in args]
        self.calls.append(args)
        rc, out = self._dispatch(args, env or {})
        if check and rc != 0:
            raise cli.DeployError(f"{label} failed (exit {rc})")
        return subprocess.CompletedProcess(args, rc, out, "")

    def _dispatch(self, args: list[str], env: dict) -> tuple[int, str]:
        if args[0] == "bash":
            script = Path(args[1]).name
            if script == cli.SYNC_BUILD_SCRIPT.name:
                if "sync-build" in self.fail:
                    return 1, ""
                sha = env["API_IMAGE"].rsplit(":", 1)[1]
                self.add_image(f"{cli.SYNC_REPOSITORY}:{sha}",
                               {cli.REVISION_LABEL: self.sync_build_revision or sha})
                return 0, ""
            if script == cli.GATE_SCRIPT.name:
                self.gate_runs.append({k: env.get(k) for k in ("AICADDIE_DEPLOY_GATE_CHECK_ONLY", "AICADDIE_API_CONTAINER")})
                return (1 if "gate" in self.fail else 0), ""
            return 127, ""
        assert args[0] == "docker", args
        cmd, rest = args[1], args[2:]
        if cmd in self.fail:
            return 1, ""
        if cmd == "info":
            return 0, "{}"
        if cmd == "ps":
            return 0, "\n".join(c["id"] for c in self.containers.values()) + "\n"
        if cmd == "inspect":
            return self._inspect(rest[1], rest[2:])
        if cmd == "image":
            return self._image(rest)
        if cmd == "build":
            return self._build(rest)
        if cmd == "update":
            policy = rest[0].split("=", 1)[1]
            container = self.containers.get(rest[1])
            if container is None or f"update:{rest[1]}" in self.fail:
                return 1, ""
            container["policy"] = policy
            return 0, ""
        if cmd == "stop":
            return self.stop(rest[-1]), ""
        if cmd == "start":
            if rest[-1] == DB_NAME:
                self.db["running"] = True
                return 0, ""
            return self.start(rest[-1]), ""
        if cmd == "run":
            return self._run_container(rest)
        if cmd == "rm":
            name = rest[-1]
            container = self.containers.get(name)
            if container is None or (container["running"] and "-f" not in rest):
                return 1, ""
            del self.containers[name]
            return 0, ""
        if cmd == "rmi":
            image = self.image_by_ref(rest[0])
            if image is None:
                return 1, ""
            image["tags"].remove(rest[0])
            if not image["tags"] and not any(c["image"] == image["id"] for c in self.containers.values()):
                del self.images[image["id"]]
            return 0, ""
        if cmd == "network":
            self.containers[rest[-1]]["networks"][rest[-2]] = {}
            return 0, ""
        return 127, ""

    def _inspect(self, fmt: str, names: list[str]) -> tuple[int, str]:
        if fmt == cli.DATABASE_FORMAT:
            health = {"Status": self.db["health"]} if self.db["health"] else None
            return 0, json.dumps({"running": self.db["running"], "health": health})
        if fmt == cli.ENV_FORMAT:
            container = self.containers.get(names[0])
            return (0, json.dumps(container["env"])) if container else (1, "")
        assert fmt == cli.CONTAINER_FORMAT, fmt
        by_id = {c["id"]: c for c in self.containers.values()}
        lines = []
        for ref in names:
            c = by_id.get(ref) or self.containers.get(ref)
            if c is None:
                continue
            policy, _, retries = c["policy"].partition(":")
            lines.append(json.dumps({
                "id": c["id"], "name": "/" + c["name"], "image": c["image"], "labels": c["labels"],
                "running": c["running"], "status": "running" if c["running"] else "exited", "dead": False,
                "restartPolicy": {"Name": policy, "MaximumRetryCount": int(retries or 0)},
                "finishedAt": c["finishedAt"], "ports": c["ports"], "network": c["network"],
                "networks": c["networks"], "mounts": c["mounts"], "memory": c["memory"],
                "nanoCpus": c["nanoCpus"],
            }))
        return (0 if len(lines) == len(names) else 1), "\n".join(lines) + "\n"

    def _image(self, rest: list[str]) -> tuple[int, str]:
        if rest[0] == "inspect":
            fmt, ref = rest[2], rest[3]
            image = self.image_by_ref(ref)
            if image is None:
                return 1, ""
            if fmt == cli.ENV_FORMAT:
                return 0, json.dumps(image["env"])
            return 0, json.dumps({"id": image["id"], "tags": image["tags"], "labels": image["labels"]})
        if rest[0] == "ls":
            with_created = "|" in rest[2]
            lines = [f"{tag}|2026-11-10 08:00:{img['created'] % 60:02d}" if with_created else tag
                     for img in self.images.values() for tag in img["tags"]]
            return 0, "\n".join(lines) + "\n"
        return 127, ""

    def _build(self, rest: list[str]) -> tuple[int, str]:
        labels, tag, build_args = {}, "", {}
        it = iter(rest)
        for flag in it:
            if flag == "--label":
                key, _, value = next(it).partition("=")
                labels[key] = value
            elif flag == "-t":
                tag = next(it)
            elif flag == "--build-arg":
                key, _, value = next(it).partition("=")
                build_args[key] = value
            elif flag == "-f":
                next(it)
        kind = "api-build" if tag.startswith(cli.API_REPOSITORY + ":") else "deps-build"
        if kind in self.fail:
            return 1, ""
        base = self.image_by_ref(build_args.get("DEPS_IMAGE", "")) or {"labels": {}}
        self.add_image(tag, {**base["labels"], **labels})
        return 0, ""

    def _run_container(self, rest: list[str]) -> tuple[int, str]:
        with_value = {"--name", "--restart", "--cpus", "--memory", "--network", "--log-driver",
                      "--log-opt", "--label", "--env-file", "-p", "-v", "--pull"}
        opts: dict[str, list[str]] = {}
        image_ref = ""
        it = iter(rest)
        for arg in it:
            if arg in with_value:
                opts.setdefault(arg, []).append(next(it))
            elif not arg.startswith("-"):
                image_ref = arg
        name = opts["--name"][0]
        image = self.image_by_ref(image_ref)
        if image is None or name in self.containers:
            return 125, ""
        env = list(image["env"]) + Path(opts["--env-file"][0]).read_text().splitlines()
        labels = {**image["labels"], **dict(item.split("=", 1) for item in opts.get("--label", []))}
        ports = [tuple(spec.split(":")) for spec in opts.get("-p", [])]
        container = self._container(name, image["id"], labels, opts["--restart"][0], ports, env)
        container["network"] = opts["--network"][0]
        self.containers[name] = container
        if self.start(name) != 0:
            return 125, ""
        return 0, container["id"] + "\n"


class Deploy(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.state_path = self.tmp / "state" / "current-release"
        env = patch.dict(os.environ, {
            "AICADDIE_API_PORT": str(PORT),
            "AICADDIE_SYNC_LOCK": str(self.tmp / "sync.lock"),
            "AICADDIE_DEPLOY_RELEASE_STATE": str(self.state_path),
            "XDG_RUNTIME_DIR": str(self.tmp),
            "AICADDIE_DEPLOY_HEALTH_TIMEOUT_SECONDS": "0",
            "AICADDIE_DEPLOY_PUBLIC_HEALTH_TIMEOUT_SECONDS": "0",
            "AICADDIE_DEPLOY_LOCK_TIMEOUT_SECONDS": "0",
            "AICADDIE_DEPLOY_POLL_SECONDS": "0",
            "AICADDIE_DB_READY_TIMEOUT_SECONDS": "0",
            "AICADDIE_UP_DOCKER_TIMEOUT_SECONDS": "0",
        })
        env.start()
        self.addCleanup(env.stop)
        for name in ("AICADDIE_SYNC_SCRIPT", "AICADDIE_DEPLOY_PUBLIC_HEALTH_URL", "AGENTHUB_DEPLOY_SHA",
                     "AICADDIE_CONTAINER_PREFIX", "AICADDIE_DEPLOY_NETWORK", "AICADDIE_PRIVATE_VOLUME",
                     "AICADDIE_DEPLOY_BOOTSTRAP_ENV_FILE", "AICADDIE_DEPLOY_KEEP_STOPPED",
                     "AICADDIE_DEPLOY_DEADLINE_SECONDS", "AICADDIE_DB_CONTAINER",
                     "AICADDIE_DEPLOY_DEFAULT_CPUS", "AICADDIE_DEPLOY_DEFAULT_MEMORY_BYTES"):
            os.environ.pop(name, None)  # restored by the patch.dict above
        saved = {sig: signal.getsignal(sig) for sig in cli.SIGNALS}
        self.addCleanup(lambda: [signal.signal(sig, handler) for sig, handler in saved.items()])
        for target in (patch.object(cli, "run", lambda *a, **k: self.fake.run(*a, **k)),
                       patch.object(cli, "fetch_health", lambda url: self.fake.fetch_health(url)),
                       patch.object(cli, "_UP_QUIET", False)):
            target.start()
            self.addCleanup(target.stop)
        # The product's own idea of where its health endpoint (and so its published port) lives.
        self.loopback = urlparse(cli.DeployConfig(dict(os.environ)).local_health_url).hostname
        self.api_hash = cli.api_dependency_hash()
        self.world()

    def world(self, *, running=OLD, stopped=(REMNANT,), policy="on-failure:3", sync_images=True) -> FakeDocker:
        """Fresh daemon: earlier releases were all left with an auto-restart policy."""
        self.state_path.unlink(missing_ok=True)
        self.fake = FakeDocker()
        self.fake.containers[DB_NAME] = self.fake._container(DB_NAME, "sha256:db", {}, "unless-stopped", [], [])
        self.fake.containers[DB_NAME]["running"] = True
        for sha in stopped:
            self.fake.add_release(sha, running=False, policy=policy, loopback=self.loopback,
                                  api_hash=self.api_hash, sync_image=sync_images)
        if running:
            self.fake.add_release(running, running=True, policy=policy, loopback=self.loopback,
                                  api_hash=self.api_hash, sync_image=sync_images)
        return self.fake

    def cli(self, *argv: str) -> tuple[int, str]:
        self.fake.calls = []
        out = StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def recorded(self) -> str | None:
        return json.loads(self.state_path.read_text())["revision"] if self.state_path.exists() else None

    def docker_cmds(self) -> list[str]:
        return [c[1] if c[0] == "docker" else Path(c[1]).name for c in self.fake.calls]

    def assert_loopback_only(self):
        self.assertTrue(ipaddress.ip_address(self.loopback).is_loopback)
        for name, host, host_port in self.fake.bindings():
            self.assertEqual(host, self.loopback, f"{name} publishes on a non-loopback host")
            self.assertEqual(host_port, str(PORT))

    def assert_live(self, sha: str, out: str = ""):
        self.assertEqual(self.fake.serving(), sha, out)
        self.assertEqual([n for n in self.fake.running() if n.startswith(PREFIX)], [release_name(sha)], out)
        self.assertEqual(self.fake.auto_restart(), [release_name(sha)],
                         f"only the serving release may restart on its own\n{out}")

    def releases(self) -> dict[str, tuple]:
        return {n: (c["id"], c["running"], c["policy"]) for n, c in self.fake.containers.items()
                if n.startswith(PREFIX)}

    # ------------------------------------------------------------------
    def test_sync_image_gate_rollback_restart_policy(self):
        """S-26 [main]: deploy goes live only with a same-revision sync image, rolls back to a healthy old release on failure, leaves one auto-restart release on loopback, and up starts the recorded release"""
        code, out = self.cli("deploy", NEW)
        self.assertEqual(code, cli.EXIT_OK, out)
        self.assert_live(NEW, out)
        self.assertEqual(self.recorded(), NEW)
        self.assertEqual(self.fake.image_by_ref(f"{cli.SYNC_REPOSITORY}:{NEW}")["labels"][cli.REVISION_LABEL], NEW)
        new = self.fake.containers[release_name(NEW)]
        self.assertIn("AI_CADDIE_SESSION_SECRET=kept-across-releases", new["env"])
        self.assertIn(f"AI_CADDIE_BUILD_REVISION={NEW}", new["env"])
        self.assertEqual(self.fake.gate_runs[-1], {"AICADDIE_DEPLOY_GATE_CHECK_ONLY": "1",
                                                   "AICADDIE_API_CONTAINER": release_name(NEW)})
        self.assert_loopback_only()

        # Host reboot: only the release that was live comes back, no old release races for the port.
        self.fake.daemon_restart()
        self.assert_live(NEW)

        # An old release grabbed the port anyway (manual start); boot recovery must bring the
        # recorded release back instead of keeping whatever release happens to run.
        self.fake.stop(release_name(NEW))
        self.assertEqual(self.fake.start(release_name(OLD)), 0)
        code, out = self.cli("up")
        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertIn(f"container={release_name(NEW)}", out)
        self.assert_live(NEW, out)

        # A new image that reports the wrong revision is removed and the live release restored.
        self.fake.reports[THIRD] = OLD
        code, out = self.cli("deploy", THIRD)
        self.assertEqual(code, cli.EXIT_FAILED, out)
        self.assertIn("previous_restored=true", out)
        self.assertNotIn(release_name(THIRD), self.fake.containers)
        self.assert_live(NEW, out)
        self.assertEqual(self.recorded(), NEW)

        # No same-revision sync image can be produced: refused before anything is touched.
        self.fake.reports.clear()
        self.fake.rmi_all(f"{cli.SYNC_REPOSITORY}:{THIRD}")
        self.fake.fail.add("sync-build")
        before = self.releases()
        code, out = self.cli("deploy", THIRD)
        self.assertEqual(code, cli.EXIT_FAILED, out)
        self.assertIn("previous_untouched=true", out)
        self.assertNotIn("run", self.docker_cmds())
        self.assertEqual(self.releases(), before)
        self.assert_live(NEW, out)
        self.assert_loopback_only()

    def test_sync_image_equivalence_classes(self):
        """S-26: same-revision sync image is used, a missing or other-revision one is rebuilt, a wrong rebuild or a failing docker call is refused"""
        rows = [
            # (class, prepare(fake), exit, outcome: "new" live / "restored" old / "untouched")
            ("same-revision sync image present",
             lambda f: f.add_image(f"{cli.SYNC_REPOSITORY}:{NEW}", {cli.REVISION_LABEL: NEW}), cli.EXIT_OK, "new"),
            ("sync image missing, build produces it", lambda f: None, cli.EXIT_OK, "new"),
            ("sync image missing, build fails", lambda f: f.fail.add("sync-build"), cli.EXIT_FAILED, "untouched"),
            ("sync tag carries another revision, rebuild fixes it",
             lambda f: f.add_image(f"{cli.SYNC_REPOSITORY}:{NEW}", {cli.REVISION_LABEL: OLD}), cli.EXIT_OK, "new"),
            ("sync tag carries another revision, rebuild still wrong",
             lambda f: (f.add_image(f"{cli.SYNC_REPOSITORY}:{NEW}", {cli.REVISION_LABEL: OLD}),
                        setattr(f, "sync_build_revision", OLD)), cli.EXIT_FAILED, "untouched"),
            ("docker run fails", lambda f: f.fail.add("run"), cli.EXIT_FAILED, "restored"),
            ("docker ps fails", lambda f: f.fail.add("ps"), cli.EXIT_FAILED, "untouched"),
        ]
        for name, prepare, expected, outcome in rows:
            with self.subTest(name):
                fake = self.world()
                prepare(fake)
                before = self.releases()
                code, out = self.cli("deploy", NEW)
                self.assertEqual(code, expected, out)
                built_sync = cli.SYNC_BUILD_SCRIPT.name in self.docker_cmds()
                self.assertEqual(built_sync, name != "same-revision sync image present"
                                 and "ps fails" not in name, out)
                if outcome == "new":
                    self.assert_live(NEW, out)
                    sync = fake.image_by_ref(f"{cli.SYNC_REPOSITORY}:{NEW}")
                    self.assertEqual(sync["labels"][cli.REVISION_LABEL], NEW)
                    self.assertEqual(self.recorded(), NEW)
                else:
                    self.assertNotIn(release_name(NEW), fake.containers)
                    self.assertIsNone(self.recorded())
                    self.assertEqual(fake.serving(), OLD, out)
                    if outcome == "restored":
                        self.assertIn("previous_restored=true", out)
                        self.assert_live(OLD, out)
                    else:
                        self.assertIn("previous_untouched=true", out)
                        self.assertNotIn("run", self.docker_cmds())
                        self.assertEqual(self.releases(), before)
                self.assert_loopback_only()

    def test_failure_at_each_step_restores_old_release(self):
        """S-26: a failure in build, preflight, swap, health or gate leaves the old release serving with the only auto-restart policy"""
        def no_current(f):
            f.stop(release_name(OLD))

        rows = [
            # (step, prepare, exit, marker in output, outcome: "restored" / "untouched" / "down")
            ("build: api image build fails", lambda f: f.fail.add("api-build"), cli.EXIT_FAILED, "previous_untouched=true", "untouched"),
            ("preflight: database unhealthy", lambda f: f.db.update(health="starting"), cli.EXIT_FAILED, "previous_untouched=true", "untouched"),
            ("preflight: nothing serving and no bootstrap env", no_current, cli.EXIT_FAILED, "previous_untouched=true", "untouched"),
            ("swap: new container never healthy", lambda f: f.unhealthy.add(NEW), cli.EXIT_FAILED, "previous_restored=true", "restored"),
            ("health: new container reports another revision", lambda f: f.reports.update({NEW: OLD}), cli.EXIT_FAILED, "previous_restored=true", "restored"),
            ("done-gate: check-only gate fails", lambda f: f.fail.add("gate"), cli.EXIT_FAILED, "previous_restored=true", "restored"),
            ("restore fails too", lambda f: (f.fail.add("gate"), f.fail.add(f"start:{release_name(OLD)}")),
             cli.EXIT_UNRECOVERED, "previous_restored=false", "down"),
        ]
        for step, prepare, expected, marker, outcome in rows:
            with self.subTest(step):
                fake = self.world()
                prepare(fake)
                before = self.releases()
                code, out = self.cli("deploy", NEW)
                self.assertEqual(code, expected, out)
                self.assertIn(marker, out)
                self.assertNotIn(release_name(NEW), fake.containers, "a failed release container was left behind")
                self.assertIsNone(self.recorded())
                if outcome == "restored":
                    self.assert_live(OLD, out)
                elif outcome == "untouched":
                    self.assertEqual(self.releases(), before)
                    self.assertNotIn("run", self.docker_cmds())
                else:
                    self.assertIsNone(fake.serving(), out)
                self.assert_loopback_only()

    def test_redeploy_same_revision_and_retry_after_failure(self):
        """S-26: re-running a finished deploy only re-verifies, and a deploy retried after a failed docker run goes live without rebuilding"""
        self.fake.fail.add("run")
        code, out = self.cli("deploy", NEW)
        self.assertEqual(code, cli.EXIT_FAILED, out)
        self.assert_live(OLD, out)

        self.fake.fail.clear()
        code, out = self.cli("deploy", NEW)
        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertNotIn("build", self.docker_cmds(), "images from the failed attempt were rebuilt")
        self.assertNotIn(cli.SYNC_BUILD_SCRIPT.name, self.docker_cmds())
        self.assert_live(NEW, out)
        first_id = self.fake.containers[release_name(NEW)]["id"]

        code, out = self.cli("deploy", NEW)
        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertIn("verifying only", out)
        self.assertNotIn("run", self.docker_cmds())
        self.assertNotIn("stop", self.docker_cmds())
        self.assertEqual(self.fake.containers[release_name(NEW)]["id"], first_id)
        self.assertEqual(self.fake.gate_runs[-1]["AICADDIE_API_CONTAINER"], release_name(NEW))
        self.assert_live(NEW, out)
        self.assertEqual(self.recorded(), NEW)

    def test_command_line_boundaries(self):
        """S-26: a revision that is not exactly 40 lowercase hex characters, an unknown action or an out-of-range port is refused before any docker call"""
        rows = [
            ("39 characters", ["deploy", NEW[:39]], {}),
            ("41 characters", ["deploy", NEW + "b"], {}),
            ("uppercase", ["deploy", NEW.upper()], {}),
            ("unknown action", ["promote", NEW], {}),
            ("up with an argument", ["up", NEW], {}),
            ("controller revision differs", ["deploy", NEW], {"AGENTHUB_DEPLOY_SHA": OLD}),
            ("port 0", ["deploy", NEW], {"AICADDIE_API_PORT": "0"}),
            ("port 65536", ["deploy", NEW], {"AICADDIE_API_PORT": "65536"}),
            ("rollback revision malformed", ["rollback", "g" * 40], {}),
        ]
        for name, argv, env in rows:
            with self.subTest(name), patch.dict(os.environ, env):
                self.world()
                code, out = self.cli(*argv)
                self.assertEqual(code, cli.EXIT_USAGE, out)
                self.assertEqual(self.fake.calls, [])
        with self.subTest("exactly 40 lowercase characters matching the controller"), \
                patch.dict(os.environ, {"AGENTHUB_DEPLOY_SHA": NEW}):
            self.world()
            code, out = self.cli("deploy", NEW)
            self.assertEqual(code, cli.EXIT_OK, out)
            self.assert_live(NEW, out)

    def test_rollback_moves_auto_restart_and_refuses_without_sync_image(self):
        """S-26: rollback starts the stopped release of that revision as the only auto-restart release, and refuses one without its sync image or container"""
        self.assertEqual(self.cli("deploy", NEW)[0], cli.EXIT_OK)

        code, out = self.cli("rollback", OLD)
        self.assertEqual(code, cli.EXIT_OK, out)
        self.assert_live(OLD, out)
        self.assertEqual(self.recorded(), OLD)
        self.assert_loopback_only()

        for name, sha, prepare in [
            ("no container of that revision", THIRD, lambda: None),
            ("sync image missing", REMNANT, lambda: self.fake.rmi_all(f"{cli.SYNC_REPOSITORY}:{REMNANT}")),
        ]:
            with self.subTest(name):
                prepare()
                code, out = self.cli("rollback", sha)
                self.assertEqual(code, cli.EXIT_FAILED, out)
                self.assertIn("previous_untouched=true", out)
                self.assertNotIn("start", self.docker_cmds())
                self.assert_live(OLD, out)
                self.assertEqual(self.recorded(), OLD)

    def test_up_without_record_starts_newest_stopped_release(self):
        """S-26: boot recovery without a release record starts the newest stopped release on loopback and makes it the only auto-restart one"""
        self.world(running=None, stopped=(REMNANT, OLD))
        code, out = self.cli("up")
        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertIn("selection=legacy", out)
        self.assert_live(OLD, out)
        self.assert_loopback_only()


if __name__ == "__main__":
    unittest.main()
