"""Acceptance coverage for card 457 named dependency images.

The tests exercise the deploy planner with Docker calls stubbed. They never
connect to a Docker daemon and keep the dependency hash assertions independent
of application source files.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import os
from unittest.mock import patch

from ops import agenthub_deploy as deploy


SHA = "2b" * 20
API_HASH = "a" * 64
SYNC_HASH = deploy.sync_dependency_hash(API_HASH)
API_DEPS = f"{deploy.API_DEPS_REPOSITORY}:{API_HASH}"
SYNC_DEPS = f"{deploy.SYNC_DEPS_REPOSITORY}:{SYNC_HASH}"
API_IMAGE = f"{deploy.API_REPOSITORY}:{SHA}"
SYNC_IMAGE = f"{deploy.SYNC_REPOSITORY}:{SHA}"


class Card457BuildPlannerTests(unittest.TestCase):
    def _planner(self, *, existing_api_deps: bool, existing_sync_deps: bool):
        images: dict[str, tuple[str, str]] = {}
        if existing_api_deps:
            images[API_DEPS] = ("", API_HASH)
        if existing_sync_deps:
            images[SYNC_DEPS] = ("", SYNC_HASH)
        calls: list[tuple[list[str], dict]] = []

        def image_revision(reference: str) -> str:
            return SHA if images.get(reference, ("", ""))[0] == "revision" else ""

        def image_label(reference: str, label: str) -> str:
            if reference == API_IMAGE and label == deploy.DEPENDENCY_HASH_LABEL:
                return images.get(reference, ("", ""))[1]
            if reference in (API_DEPS, SYNC_DEPS) and reference in images:
                if label == deploy.API_DEPENDENCY_HASH_LABEL and reference == SYNC_DEPS:
                    return API_HASH
                return images[reference][1]
            return ""

        def run(args, **kwargs):
            calls.append((list(args), kwargs))
            if args[0:2] == ["docker", "build"]:
                tag = args[args.index("-t") + 1]
                if tag == API_DEPS:
                    images[tag] = ("", API_HASH)
                elif tag == SYNC_DEPS:
                    images[tag] = ("", SYNC_HASH)
                elif tag == API_IMAGE:
                    images[tag] = ("revision", API_HASH)
            elif args[0:2] == ["bash", str(deploy.SYNC_BUILD_SCRIPT)]:
                images[SYNC_IMAGE] = ("revision", "")
            return subprocess.CompletedProcess(args, 0)

        return images, calls, image_revision, image_label, run

    def test_g1_existing_dependency_images_skip_dependency_build_and_base_app_on_them(self):
        images, calls, image_revision, image_label, run = self._planner(
            existing_api_deps=True, existing_sync_deps=True,
        )
        with patch.object(deploy, "image_revision", side_effect=image_revision), \
             patch.object(deploy, "image_label", side_effect=image_label), \
             patch.object(deploy, "api_dependency_hash", return_value=API_HASH), \
             patch.object(deploy, "sync_dependency_hash", return_value=SYNC_HASH), \
             patch.object(deploy, "run", side_effect=run):
            deploy.ensure_images(SHA)

        builds = [args for args, _ in calls if args[:2] == ["docker", "build"]]
        self.assertEqual([args[args.index("-f") + 1] for args in builds], ["Dockerfile",])
        api_build = builds[0]
        self.assertIn(f"DEPS_IMAGE={API_DEPS}", api_build)
        sync_call = next(kwargs for args, kwargs in calls if args[:2] == ["bash", str(deploy.SYNC_BUILD_SCRIPT)])
        self.assertEqual(sync_call["env"]["API_IMAGE"], API_IMAGE)
        self.assertEqual(sync_call["env"]["SYNC_DEPS_IMAGE"], SYNC_DEPS)
        self.assertIn(API_DEPS, images)
        self.assertIn(SYNC_DEPS, images)

    def test_g2_missing_dependency_images_are_built_before_each_application_image(self):
        _images, calls, image_revision, image_label, run = self._planner(
            existing_api_deps=False, existing_sync_deps=False,
        )
        with patch.object(deploy, "image_revision", side_effect=image_revision), \
             patch.object(deploy, "image_label", side_effect=image_label), \
             patch.object(deploy, "api_dependency_hash", return_value=API_HASH), \
             patch.object(deploy, "sync_dependency_hash", return_value=SYNC_HASH), \
             patch.object(deploy, "run", side_effect=run):
            deploy.ensure_images(SHA)

        builds = [args for args, _ in calls if args[:2] == ["docker", "build"]]
        self.assertEqual(
            [(args[args.index("-f") + 1], args[args.index("-t") + 1]) for args in builds],
            [("Dockerfile.deps", API_DEPS),
             ("Dockerfile", API_IMAGE),
             ("Dockerfile.sync-deps", SYNC_DEPS)],
        )
        self.assertEqual(
            [args for args, _ in calls if args[:2] == ["bash", str(deploy.SYNC_BUILD_SCRIPT)]],
            [["bash", str(deploy.SYNC_BUILD_SCRIPT)]],
        )

    def test_g3_application_source_does_not_enter_dependency_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("pyproject.toml", "uv.lock", "package.json", "package-lock.json",
                         "Dockerfile.deps", "Dockerfile.sync-deps"):
                shutil.copy(deploy.REPO_ROOT / name, root / name)
            (root / "server_v2").mkdir()
            with patch.object(deploy, "REPO_ROOT", root):
                before_api = deploy.api_dependency_hash()
                before_sync = deploy.sync_dependency_hash()
                (root / "server_v2" / "changed.py").write_text("changed\n", encoding="utf-8")
                self.assertEqual(before_api, deploy.api_dependency_hash())
                self.assertEqual(before_sync, deploy.sync_dependency_hash())

    def test_g4_dependency_inputs_change_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("pyproject.toml", "uv.lock", "package.json", "package-lock.json",
                         "Dockerfile.deps", "Dockerfile.sync-deps"):
                shutil.copy(deploy.REPO_ROOT / name, root / name)
            with patch.object(deploy, "REPO_ROOT", root):
                original = deploy.api_dependency_hash()
                (root / "uv.lock").write_text((root / "uv.lock").read_text() + "\n# changed\n")
                self.assertNotEqual(original, deploy.api_dependency_hash())
                (root / "Dockerfile.deps").write_text(
                    (root / "Dockerfile.deps").read_text().replace(
                        "postgresql-client", "postgresql-client git",
                    ),
                )
                self.assertNotEqual(original, deploy.api_dependency_hash())

    def test_g5_cleanup_keeps_two_hashes_and_never_touches_other_repositories(self):
        refs = [
            f"{deploy.API_DEPS_REPOSITORY}:old|2026-10-22 12:00:00 +0000 UTC",
            f"{deploy.API_DEPS_REPOSITORY}:previous|2026-10-22 11:00:00 +0000 UTC",
            f"{deploy.API_DEPS_REPOSITORY}:current|2026-10-22 10:00:00 +0000 UTC",
            f"{deploy.SYNC_DEPS_REPOSITORY}:old|2026-10-22 12:00:00 +0000 UTC",
            f"{deploy.SYNC_DEPS_REPOSITORY}:previous|2026-10-22 11:00:00 +0000 UTC",
            f"{deploy.SYNC_DEPS_REPOSITORY}:current|2026-10-22 10:00:00 +0000 UTC",
            "other-project:old",
        ]
        removed: list[str] = []

        def docker(*args, **kwargs):
            if args[:2] == ("image", "ls"):
                return subprocess.CompletedProcess(args, 0, stdout="\n".join(refs))
            if args[0] == "rmi":
                removed.append(args[1])
            return subprocess.CompletedProcess(args, 0, stdout="")

        with patch.object(deploy, "docker", side_effect=docker):
            deploy.cleanup_dependency_images({"api": "current", "sync": "current"})
        self.assertEqual(
            removed,
            [f"{deploy.API_DEPS_REPOSITORY}:previous", f"{deploy.SYNC_DEPS_REPOSITORY}:previous"],
        )
        self.assertNotIn("other-project:old", removed)

    def test_g6_sync_hash_includes_api_dependency_hash_and_sync_dependency_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("pyproject.toml", "uv.lock", "package.json", "package-lock.json",
                         "Dockerfile.deps", "Dockerfile.sync-deps"):
                shutil.copy(deploy.REPO_ROOT / name, root / name)
            with patch.object(deploy, "REPO_ROOT", root):
                first = deploy.sync_dependency_hash("a" * 64)
                self.assertNotEqual(first, deploy.sync_dependency_hash("b" * 64))
                sync_file = root / "Dockerfile.sync-deps"
                sync_file.write_text(sync_file.read_text().replace("xvfb xauth", "xvfb xauth git"))
                self.assertNotEqual(first, deploy.sync_dependency_hash("a" * 64))

    def test_g7_sync_dependency_build_arg_matches_the_dockerfile_declared_arg(self):
        sync_deps = (deploy.REPO_ROOT / "Dockerfile.sync-deps").read_text(encoding="utf-8")
        declared = re.findall(r"(?m)^ARG\s+([A-Za-z_][A-Za-z0-9_]*)", sync_deps)
        self.assertEqual(declared, ["API_IMAGE"])

        _images, calls, image_revision, image_label, run = self._planner(
            existing_api_deps=True, existing_sync_deps=False,
        )
        with patch.object(deploy, "image_revision", side_effect=image_revision), \
             patch.object(deploy, "image_label", side_effect=image_label), \
             patch.object(deploy, "api_dependency_hash", return_value=API_HASH), \
             patch.object(deploy, "sync_dependency_hash", return_value=SYNC_HASH), \
             patch.object(deploy, "run", side_effect=run):
            deploy.ensure_images(SHA)
        dependency_build = next(
            args for args, _ in calls
            if args[:2] == ["docker", "build"]
            and args[args.index("-f") + 1] == "Dockerfile.sync-deps"
        )
        passed = [value.split("=", 1)[0] for index, value in enumerate(dependency_build)
                  if index and dependency_build[index - 1] == "--build-arg"]
        self.assertEqual(passed, declared)

    def test_g8_application_dockerfiles_have_no_duplicate_dependency_stage(self):
        api = (deploy.REPO_ROOT / "Dockerfile").read_text()
        sync = (deploy.REPO_ROOT / "Dockerfile.sync").read_text()
        self.assertNotIn("BEGIN DEPENDENCY IMAGE", api)
        self.assertNotIn("BEGIN DEPENDENCY IMAGE", sync)
        self.assertIn("FROM ${DEPS_IMAGE}", api)
        self.assertIn("FROM ${SYNC_DEPS_IMAGE}", sync)
        self.assertIn("ARG API_IMAGE", sync)
        self.assertIn("FROM ${API_IMAGE} AS api", sync)
        self.assertIn("COPY --from=api /app/ai_caddie/ ./ai_caddie/", sync)
        self.assertIn("ARG DEPS_IMAGE", api)
        self.assertNotIn("DEPS_IMAGE=garmin-ai-caddie-deps:local", api)
        self.assertNotRegex(api, r"(?m)^RUN\s+.*uv sync")
        self.assertNotRegex(sync, r"(?m)^RUN\s+.*uv sync")
        application_destinations = lambda text: [line.split()[-1] for line in text.splitlines()
                                                 if line.strip().startswith("COPY ")
                                                 and ("pyproject" not in line and "package" not in line
                                                      and "node_modules" not in line)]
        self.assertEqual(application_destinations(api), application_destinations(sync))
        for name in ("Dockerfile.deps", "Dockerfile.sync-deps"):
            text = (deploy.REPO_ROOT / name).read_text(encoding="utf-8")
            self.assertEqual(text.count("BEGIN DEPENDENCY IMAGE"), 1)
            self.assertEqual(text.count("END DEPENDENCY IMAGE"), 1)

    def test_g9_sync_dependency_hit_skips_its_build(self):
        images, calls, _rev, image_label, run = self._planner(
            existing_api_deps=True, existing_sync_deps=True,
        )
        images[API_IMAGE] = ("revision", API_HASH)

        def image_revision(reference: str) -> str:
            return SHA if reference == API_IMAGE or images.get(reference, ("",))[0] == "revision" else ""

        with patch.object(deploy, "image_revision", side_effect=image_revision), \
             patch.object(deploy, "image_label", side_effect=image_label), \
             patch.object(deploy, "api_dependency_hash", return_value=API_HASH), \
             patch.object(deploy, "sync_dependency_hash", return_value=SYNC_HASH), \
             patch.object(deploy, "run", side_effect=run):
            deploy.ensure_images(SHA)
        self.assertFalse(any(args[args.index("-f") + 1] == "Dockerfile.sync-deps"
                             for args, _ in calls if args[:2] == ["docker", "build"]))

    def test_g10_sync_dependency_miss_builds_before_sync_application(self):
        images, calls, _rev, image_label, run = self._planner(
            existing_api_deps=True, existing_sync_deps=False,
        )
        images[API_IMAGE] = ("revision", API_HASH)

        def image_revision(reference: str) -> str:
            return SHA if reference == API_IMAGE or images.get(reference, ("",))[0] == "revision" else ""

        with patch.object(deploy, "image_revision", side_effect=image_revision), \
             patch.object(deploy, "image_label", side_effect=image_label), \
             patch.object(deploy, "api_dependency_hash", return_value=API_HASH), \
             patch.object(deploy, "sync_dependency_hash", return_value=SYNC_HASH), \
             patch.object(deploy, "run", side_effect=run):
            deploy.ensure_images(SHA)
        builds = [args for args, _ in calls if args[:2] == ["docker", "build"]]
        self.assertEqual([args[args.index("-f") + 1] for args in builds], ["Dockerfile.sync-deps"])
        self.assertIn(f"API_IMAGE={API_DEPS}", builds[0])

    def test_g11_sync_dependency_cleanup_keeps_current_and_previous(self):
        refs = [
            f"{deploy.SYNC_DEPS_REPOSITORY}:{SYNC_HASH}",
            f"{deploy.SYNC_DEPS_REPOSITORY}:previous",
            f"{deploy.SYNC_DEPS_REPOSITORY}:old",
        ]
        removed: list[str] = []

        def docker(*args, **kwargs):
            if args[:2] == ("image", "ls"):
                return subprocess.CompletedProcess(args, 0, stdout="\n".join(refs))
            if args[0] == "rmi":
                removed.append(args[1])
            return subprocess.CompletedProcess(args, 0, stdout="")

        with patch.object(deploy, "docker", side_effect=docker):
            deploy.cleanup_dependency_images({"sync": SYNC_HASH})
        self.assertEqual(removed, [f"{deploy.SYNC_DEPS_REPOSITORY}:old"])

    def test_g12_orphan_application_cleanup_protects_current_and_rollback_revisions(self):
        current = "c" * 40
        previous = "b" * 40
        older = "a" * 40
        orphan = "d" * 40

        def container(name: str, revision: str, image_id: str, running: bool, finished: str):
            return deploy.Container({
                "id": image_id,
                "name": name,
                "image": image_id,
                "labels": {deploy.REVISION_LABEL: revision},
                "running": running,
                "finishedAt": finished,
                "ports": {}, "network": "", "mounts": [], "memory": 0, "nanoCpus": 0,
            })

        containers = [
            container("aicaddie-release-current", current, "id-current", True, ""),
            container("aicaddie-release-previous", previous, "id-previous", False,
                      "2026-10-22T12:00:00Z"),
            container("aicaddie-release-older", older, "id-older", False,
                      "2026-10-21T12:00:00Z"),
        ]
        refs = [
            f"{deploy.API_REPOSITORY}:{current}",
            f"{deploy.SYNC_REPOSITORY}:{previous}",
            f"{deploy.API_REPOSITORY}:{orphan}",
            f"{deploy.SYNC_REPOSITORY}:{orphan}",
            f"{deploy.API_REPOSITORY}:{orphan}-shared",
        ]
        info = {
            ref: {"id": f"id-{index}", "tags": [ref]}
            for index, ref in enumerate(refs)
        }
        info[f"{deploy.API_REPOSITORY}:{orphan}-shared"]["tags"].append("other/project:keep")
        removed: list[str] = []

        def docker(*args, **kwargs):
            if args[0] == "rmi":
                removed.append(args[1])
            return subprocess.CompletedProcess(args, 0, stdout="")

        cfg = deploy.Config({})
        with patch.object(deploy, "_application_image_refs", return_value=refs), \
             patch.object(deploy, "image_info", side_effect=lambda ref: info.get(ref)), \
             patch.object(deploy, "docker", side_effect=docker):
            deploy.cleanup_orphan_application_images(cfg, containers)
        self.assertEqual(
            removed,
            [f"{deploy.API_REPOSITORY}:{orphan}", f"{deploy.SYNC_REPOSITORY}:{orphan}"],
        )

    def test_g13_dependency_base_digests_and_uv_version_are_hash_inputs(self):
        deps = (deploy.REPO_ROOT / "Dockerfile.deps").read_text(encoding="utf-8")
        self.assertIn(f"node:24-bookworm-slim@{deploy.NODE_BASE_DIGEST}", deps)
        self.assertIn(
            f"ghcr.io/astral-sh/uv:python3.12-bookworm-slim@{deploy.UV_BASE_DIGEST}",
            deps,
        )
        self.assertRegex(deps, r"(?m)^ARG UV_VERSION=\d+\.\d+\.\d+$")
        self.assertIn('RUN test "$(uv --version)" = "uv ${UV_VERSION}"', deps)
        before = deploy.api_dependency_hash()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("pyproject.toml", "uv.lock", "package.json", "package-lock.json",
                         "Dockerfile.deps", "Dockerfile.sync-deps"):
                shutil.copy(deploy.REPO_ROOT / name, root / name)
            with patch.object(deploy, "REPO_ROOT", root):
                changed = root / "Dockerfile.deps"
                changed.write_text(changed.read_text().replace(
                    "ARG UV_VERSION=0.9.30", "ARG UV_VERSION=0.9.31",
                ))
                self.assertNotEqual(before, deploy.api_dependency_hash())

    def test_g17_sync_builder_without_dependency_arg_requires_hashed_local_image(self):
        tree_revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=deploy.REPO_ROOT, text=True,
        ).strip()
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "docker"
            fake.write_text("""#!/bin/sh
if [ "$1" = image ] && [ "$2" = inspect ]; then
  case "$*" in
    *dependencies-hash*) echo '%s'; exit 0 ;;
    *source-revision*) echo '%s'; exit 0 ;;
    *garmin-ai-caddie-api:*) exit 0 ;;
    *) exit 1 ;;
  esac
fi
exit 1
""" % (API_HASH, tree_revision))
            fake.chmod(0o755)
            env = {**os.environ, "PATH": f"{tmp}:{os.environ.get('PATH', '')}",
                   "API_IMAGE": API_IMAGE, "SOURCE_REVISION": tree_revision}
            result = subprocess.run(["bash", "ops/build_sync_image.sh"], cwd=deploy.REPO_ROOT,
                                    env=env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("aicaddie-sync-deps:", result.stderr)
        self.assertIn("docker build -f Dockerfile.sync-deps", result.stderr)

    def test_g18_sync_builder_rejects_source_revision_mismatch(self):
        tree_revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=deploy.REPO_ROOT, text=True,
        ).strip()
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "docker"
            fake.write_text("""#!/bin/sh
if [ "$1" = image ] && [ "$2" = inspect ]; then
  case "$*" in
    *dependencies-hash*) echo '%s'; exit 0 ;;
    *source-revision*) echo '%s'; exit 0 ;;
    *garmin-ai-caddie-api:*) exit 0 ;;
    *) exit 1 ;;
  esac
fi
exit 1
""" % (API_HASH, tree_revision))
            fake.chmod(0o755)
            env = {**os.environ, "PATH": f"{tmp}:{os.environ.get('PATH', '')}",
                   "API_IMAGE": API_IMAGE, "SOURCE_REVISION": "c" * 40}
            result = subprocess.run(["bash", "ops/build_sync_image.sh"], cwd=deploy.REPO_ROOT,
                                    env=env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match git HEAD", result.stderr)

    def _run_sync_builder(self, *, api_labels: dict[str, str],
                          sync_labels: dict[str, dict[str, str]] | None = None,
                          explicit_sync: str | None = None,
                          candidates: list[str] | None = None):
        """Run the shell helper against a deterministic fake Docker executable."""
        tree_revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=deploy.REPO_ROOT, text=True,
        ).strip()
        sync_labels = sync_labels or {}
        candidates = candidates or list(sync_labels)
        state = repr({
            "api_ref": API_IMAGE, "api_labels": api_labels,
            "sync_labels": sync_labels, "candidates": candidates,
            "tree_revision": tree_revision, "log": "__LOG__",
        })
        script = f'''#!/usr/bin/env python3
import sys
state = {state}
def labels(ref):
    if ref == state["api_ref"]: return state["api_labels"]
    return state["sync_labels"].get(ref, {{"ai.caddie.source-revision": state["api_labels"].get("ai.caddie.source-revision", state["tree_revision"])}})
args = sys.argv[1:]
with open(state["log"], "a") as log:
    log.write("docker " + " ".join(args) + "\\n")
if args[:2] == ["image", "inspect"]:
    ref = args[-1]
    if ref != state["api_ref"] and ref not in state["sync_labels"] and \
            (ref.startswith("aicaddie-sync-deps:") or not ref.startswith("aicaddie-sync:")):
        sys.exit(1)
    if "--format" in args:
        fmt = args[args.index("--format") + 1]
        if "source-revision" in fmt: print(labels(ref).get("ai.caddie.source-revision", ""))
        elif "api-dependencies-hash" in fmt: print(labels(ref).get("ai.caddie.api-dependencies-hash", ""))
        elif "dependencies-hash" in fmt: print(labels(ref).get("ai.caddie.dependencies-hash", ""))
    sys.exit(0)
if args[:2] == ["image", "ls"]:
    print("\\n".join(state["candidates"]))
    sys.exit(0)
if args and args[0] == "build": sys.exit(0)
if args and args[0] == "tag": sys.exit(0)
sys.exit(1)
'''
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake = tmp_path / "docker"
            log = tmp_path / "docker.log"
            fake.write_text(script.replace("__LOG__", str(log)), encoding="utf-8")
            fake.chmod(0o755)
            env = {**os.environ, "PATH": f"{tmp}:{os.environ.get('PATH', '')}",
                   "API_IMAGE": API_IMAGE}
            if explicit_sync is not None:
                env["SYNC_DEPS_IMAGE"] = explicit_sync
            result = subprocess.run(["bash", "ops/build_sync_image.sh"], cwd=deploy.REPO_ROOT,
                                    env=env, text=True, capture_output=True)
            log_text = log.read_text(encoding="utf-8") if log.exists() else ""
        return result, log_text

    def test_g22_explicit_sync_dependency_hash_mismatch_is_rejected(self):
        result, _log = self._run_sync_builder(
            api_labels={"ai.caddie.source-revision": "2b" * 20,
                        deploy.DEPENDENCY_HASH_LABEL: API_HASH},
            sync_labels={SYNC_DEPS: {deploy.API_DEPENDENCY_HASH_LABEL: "c" * 64}},
            explicit_sync=SYNC_DEPS,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("api-dependencies-hash", result.stderr)

    def test_g23_pre457_api_dependency_label_is_rejected_with_existing_sync_hint(self):
        result, _log = self._run_sync_builder(
            api_labels={"ai.caddie.source-revision": "2b" * 20},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pre-457", result.stderr)
        self.assertIn("aicaddie-sync:", result.stderr)

    def test_g24_matching_explicit_sync_dependency_enters_sync_build_with_both_images(self):
        result, log = self._run_sync_builder(
            api_labels={"ai.caddie.source-revision": "2b" * 20,
                        deploy.DEPENDENCY_HASH_LABEL: API_HASH},
            sync_labels={SYNC_DEPS: {deploy.API_DEPENDENCY_HASH_LABEL: API_HASH}},
            explicit_sync=SYNC_DEPS,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        build = next(line for line in log.splitlines() if "-f Dockerfile.sync" in line)
        self.assertIn(f"API_IMAGE={API_IMAGE}", build)
        self.assertIn(f"SYNC_DEPS_IMAGE={SYNC_DEPS}", build)

    def test_g25_automatic_selection_uses_exact_sync_dependency_hash_regardless_of_listing_order(self):
        first = "aicaddie-sync-deps:first"
        second = SYNC_DEPS
        sync_labels = {
            first: {deploy.API_DEPENDENCY_HASH_LABEL: API_HASH},
            second: {deploy.API_DEPENDENCY_HASH_LABEL: API_HASH},
        }
        for candidates in ([first, second], [second, first]):
            with self.subTest(candidates=candidates):
                result, log = self._run_sync_builder(
                    api_labels={"ai.caddie.source-revision": "2b" * 20,
                                deploy.DEPENDENCY_HASH_LABEL: API_HASH},
                    sync_labels=sync_labels,
                    candidates=list(candidates),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                build = next(line for line in log.splitlines() if "-f Dockerfile.sync" in line)
                self.assertIn(f"SYNC_DEPS_IMAGE={second}", build)
                self.assertNotIn(f"SYNC_DEPS_IMAGE={first}", build)

    def test_g26_automatic_selection_missing_exact_hash_prints_build_command(self):
        wrong = "aicaddie-sync-deps:wrong"
        result, _log = self._run_sync_builder(
            api_labels={"ai.caddie.source-revision": "2b" * 20,
                        deploy.DEPENDENCY_HASH_LABEL: API_HASH},
            sync_labels={wrong: {deploy.API_DEPENDENCY_HASH_LABEL: API_HASH}},
            candidates=[wrong],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"aicaddie-sync-deps:{SYNC_HASH}", result.stderr)
        self.assertIn("docker build -f Dockerfile.sync-deps", result.stderr)

    def test_g19_sync_builder_passes_api_image_to_dockerfile(self):
        script = (deploy.REPO_ROOT / "ops" / "build_sync_image.sh").read_text(encoding="utf-8")
        self.assertIn('BUILD_ARGS+=(--build-arg "API_IMAGE=${API_IMAGE}")', script)

    def test_g20_sync_dependency_build_carries_api_dependency_hash_label(self):
        _images, calls, image_revision, image_label, run = self._planner(
            existing_api_deps=True, existing_sync_deps=False,
        )
        with patch.object(deploy, "image_revision", side_effect=image_revision), \
             patch.object(deploy, "image_label", side_effect=image_label), \
             patch.object(deploy, "api_dependency_hash", return_value=API_HASH), \
             patch.object(deploy, "sync_dependency_hash", return_value=SYNC_HASH), \
             patch.object(deploy, "run", side_effect=run):
            deploy.ensure_images(SHA)
        dependency_build = next(
            args for args, _ in calls
            if args[:2] == ["docker", "build"]
            and args[args.index("-f") + 1] == "Dockerfile.sync-deps"
        )
        self.assertIn(f"{deploy.API_DEPENDENCY_HASH_LABEL}={API_HASH}", dependency_build)

    def test_g21_existing_api_with_bad_dependency_hash_fails_before_dependency_build(self):
        images, calls, image_revision, image_label, run = self._planner(
            existing_api_deps=False, existing_sync_deps=False,
        )
        images[API_IMAGE] = ("revision", "wrong-hash")
        with patch.object(deploy, "image_revision", side_effect=image_revision), \
             patch.object(deploy, "image_label", side_effect=image_label), \
             patch.object(deploy, "api_dependency_hash", return_value=API_HASH), \
             patch.object(deploy, "sync_dependency_hash", return_value=SYNC_HASH), \
             patch.object(deploy, "run", side_effect=run):
            with self.assertRaisesRegex(deploy.DeployError, "before building sync dependencies"):
                deploy.ensure_images(SHA)
        self.assertEqual(calls, [])

    def test_g27_api_build_dependency_label_mismatch_fails_before_sync_build(self):
        images, calls, image_revision, image_label, run = self._planner(
            existing_api_deps=True, existing_sync_deps=False,
        )

        def bad_run(args, **kwargs):
            result = run(args, **kwargs)
            if args[:2] == ["docker", "build"] and "Dockerfile" in args and \
                    args[args.index("-t") + 1] == API_IMAGE:
                images[API_IMAGE] = ("revision", "wrong-hash")
            return result

        with patch.object(deploy, "image_revision", side_effect=image_revision), \
             patch.object(deploy, "image_label", side_effect=image_label), \
             patch.object(deploy, "api_dependency_hash", return_value=API_HASH), \
             patch.object(deploy, "sync_dependency_hash", return_value=SYNC_HASH), \
             patch.object(deploy, "run", side_effect=bad_run):
            with self.assertRaisesRegex(deploy.DeployError, "did not inherit"):
                deploy.ensure_images(SHA)
        self.assertFalse(any(args[:2] == ["bash", str(deploy.SYNC_BUILD_SCRIPT)]
                             for args, _ in calls))
        self.assertFalse(any(args[:2] == ["docker", "build"] and
                             args[args.index("-f") + 1] == "Dockerfile.sync-deps"
                             for args, _ in calls))

    def test_g14_cleanup_passes_current_dependency_hashes_and_runs_orphan_cleanup(self):
        cfg = deploy.Config({})
        current = deploy.Container({
            "id": "current", "name": "aicaddie-release-current", "image": "api-current",
            "labels": {deploy.REVISION_LABEL: "c" * 40}, "running": True,
            "finishedAt": "", "ports": {}, "network": "", "mounts": [],
            "memory": 0, "nanoCpus": 0,
        })
        hashes = {"api": API_HASH, "sync": SYNC_HASH}
        with patch.object(deploy, "list_containers", return_value=[current]), \
             patch.object(deploy, "cleanup_dependency_images") as dependency_cleanup, \
             patch.object(deploy, "cleanup_orphan_application_images") as orphan_cleanup:
            deploy.cleanup(cfg, hashes)
        dependency_cleanup.assert_called_once_with(hashes)
        orphan_cleanup.assert_called_once_with(cfg, [current])

    def test_g15_orphan_cleanup_only_warns_when_image_removal_fails(self):
        orphan = "d" * 40
        ref = f"{deploy.API_REPOSITORY}:{orphan}"

        def docker(*args, **kwargs):
            self.assertEqual(args[0], "rmi")
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="busy")

        with patch.object(deploy, "_application_image_refs", return_value=[ref]), \
             patch.object(deploy, "image_info", return_value={"id": "orphan-id", "tags": [ref]}), \
             patch.object(deploy, "docker", side_effect=docker), \
             patch.object(deploy, "log") as log:
            deploy.cleanup_orphan_application_images(deploy.Config({}), [])
        log.assert_called_once()
        self.assertIn("warning: could not remove orphan image", log.call_args.args[0])

    def test_g16_ci_builds_dependency_chain_before_application_images(self):
        workflow = (deploy.REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
        commands = [
            "docker build -f Dockerfile.deps",
            "docker build -f Dockerfile.sync-deps",
            "docker build -f Dockerfile --build-arg DEPS_IMAGE=",
            "docker build -f Dockerfile.sync --build-arg SYNC_DEPS_IMAGE=",
        ]
        positions = [workflow.index(command) for command in commands]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("--build-arg API_IMAGE=garmin-ai-caddie-deps:ci", workflow)


if __name__ == "__main__":
    unittest.main()
