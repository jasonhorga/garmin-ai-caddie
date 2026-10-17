"""Card #432: every repository path readiness reads for runtimeStatus is in the built API image.

Revision 8 replaces the static Dockerfile/.dockerignore guard with two commands of one script,
`ops/readiness_runtime_paths.py`:

- `collect` runs `build_readiness_response()` in a fresh interpreter, records every repository
  path it opens, probes or lists, attributes each path to the readiness check label it was read
  for, and writes a JSON manifest (runtime / packaging / absent / excluded);
- `verify` checks the manifest's runtime entries against an image root. In CI's `docker` job that
  root is `/app` inside the API image the job just built.

These tests run both commands as subprocesses on temporary copies of the checkout's tracked files.
The real image is only available in CI; offline, an image root is assembled from the paths today's
runtime stage copies (IMAGE_LAYOUT).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR = Path("ops") / "readiness_runtime_paths.py"
MANIFEST_SCHEMA = "ai-caddie-readiness-runtime-paths-v1"
AFTER_FINAL_CHECK = "<after-final-check>"
EVENT_CONTRACT = "mobile/contracts/live_round_event.schema.json"
EVENT_CONTRACT_CONSTANT = re.compile(r"^LIVE_ROUND_EVENT_CONTRACT\s*=.*$", re.MULTILINE)
# The first statement after the final `_check` of build_readiness_response (runtimeStatus is computed here).
RUNTIME_STATUS_STATEMENT = re.compile(r"^    runtime_checks = \[", re.MULTILINE)
# Runtime check (label mobile_events) and packaging check (label external_release).
RUNTIME_READER = "_contract_event_kinds"
PACKAGING_READER = "_external_release_evidence"
# What the runtime stage of today's Dockerfile copies from the build context into /app. Offline
# stand-in for the image; CI checks the real one. Claude updates this if the card adds a COPY.
IMAGE_LAYOUT = (
    "pyproject.toml",
    "uv.lock",
    "package.json",
    "package-lock.json",
    "ai_caddie",
    "contracts/canonical",
    "mobile/contracts",
    "server_v2",
    "ops",
    "alembic.ini",
    "migrations",
)
PRIVATE_ROOTS = ("data", ".garmin_tokens", "output", "logs", "backups", "clubs.json")
SECTIONS = ("runtime", "packaging", "absent", "excluded")
SUPERSEDED_TESTS = (
    "test_readiness_runtime_paths_are_copied_into_image",
    "test_dockerignore_rejects_patterns_outside_the_supported_syntax",
    "test_dockerfile_copies_reject_unsupported_instructions_per_line",
    "test_docker_instruction_word_accepts_tab_separated_from_and_copy",
)
SUPERSEDED_HELPERS = (
    "UNSUPPORTED_SYNTAX",
    "_docker_instruction_word",
    "_dockerignore_matches",
    "_docker_instructions",
    "_plain_words",
    "_docker_destination",
    "_dockerfile_copies",
    "_dockerignore_patterns",
)
SUPERSEDED_SENTENCE = "unsupported Dockerfile/.dockerignore syntax"
SKIP_EVERYWHERE = {
    ".git", ".venv", "node_modules", "__pycache__", ".agenthub-home", ".codex-tmp",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}


def _environment_roots_inside_checkout() -> list[Path]:
    # G1 G2 G4: temp and home directories inside the checkout must never be copied into a tree.
    roots: list[Path] = []
    for candidate in (tempfile.gettempdir(), os.environ.get("HOME", "")):
        if not candidate:
            continue
        resolved = Path(candidate).resolve()
        try:
            resolved.relative_to(REPO_ROOT)
        except ValueError:
            continue
        if resolved != REPO_ROOT:
            roots.append(resolved)
    return roots


def _skipped(relative: str, *, fallback: bool = False) -> bool:
    # G1 G2 G4: caches, runtime environments, private-root names and the temp/home area stay out.
    parts = relative.split("/")
    if any(part in SKIP_EVERYWHERE for part in parts) or relative.endswith(".pyc"):
        return True
    if parts[0] in PRIVATE_ROOTS:
        return True
    # Without git, untracked top-level hidden directories (agent homes, tool caches) stay out.
    if fallback and parts[0].startswith(".") and parts[0] not in {".github"} and (REPO_ROOT / parts[0]).is_dir():
        return True
    for root in _environment_roots_inside_checkout():
        try:
            (REPO_ROOT / relative).resolve().relative_to(root)
            return True
        except ValueError:
            pass
    return False


def _listed_files() -> list[str] | None:
    # G1 G2 G4: tracked (and staged) files only; None when git cannot list them.
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z", "--cached"],
            cwd=REPO_ROOT,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    return [name for name in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if name]


def _copy_checkout(tree: Path) -> None:
    # G1 G2 G4: copies the checkout's tracked files into `tree` without following it into itself.
    listed = _listed_files()
    if listed is None:
        def ignore(directory: str, names: list[str]) -> set[str]:
            relative_dir = os.path.relpath(directory, REPO_ROOT)
            skipped: set[str] = set()
            for name in names:
                relative = name if relative_dir == os.curdir else f"{Path(relative_dir).as_posix()}/{name}"
                path = os.path.join(directory, name)
                if _skipped(relative, fallback=True):
                    skipped.add(name)
                elif not (os.path.islink(path) or os.path.isdir(path) or os.path.isfile(path)):
                    skipped.add(name)
            return skipped

        shutil.copytree(REPO_ROOT, tree, ignore=ignore, symlinks=True)
        return
    tree.mkdir(parents=True)
    for relative in listed:
        if _skipped(relative):
            continue
        source = REPO_ROOT / relative
        target = tree / relative
        if source.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(os.readlink(source), target)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _base_env() -> dict[str, str]:
    # G1 G2 G4: offline fixture mode, never a private root. The tree under test is NOT put on
    # PYTHONPATH here: the collector must point its readiness child at --root by itself.
    env = dict(os.environ)
    env["AI_CADDIE_DATA_MODE"] = "fixture"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("AI_CADDIE_PRIVATE_ROOT", None)
    return env


def _run(command: list[str], cwd: Path, *, env: dict[str, str] | None = None, stdin: str | None = None) -> tuple[int, str]:
    # G1 G2 G4: one real subprocess; returns the exit code and stdout+stderr.
    proc = subprocess.run(
        command,
        cwd=cwd,
        env=env or _base_env(),
        input=stdin,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _sha256(path: Path) -> str:
    # G1 G2: digest the manifest must carry for a runtime file.
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _section(manifest: dict, name: str) -> dict[str, dict]:
    # G1: one manifest section keyed by path.
    entries = manifest.get(name)
    assert isinstance(entries, list), f"manifest section {name!r} must be a list"
    return {entry["path"]: entry for entry in entries}


class ReadinessRuntimePathTests(unittest.TestCase):
    _clean: tuple[Path, dict] | None = None
    _holders: list[tempfile.TemporaryDirectory] = []

    @classmethod
    def tearDownClass(cls) -> None:
        for holder in cls._holders:
            holder.cleanup()
        cls._holders = []
        cls._clean = None

    def _holder(self, *, shared: bool = False) -> Path:
        # G1 G2 G4: a temporary directory removed after the test (or after the class when shared).
        holder = tempfile.TemporaryDirectory(prefix="card432-")
        if shared:
            type(self)._holders.append(holder)
        else:
            self.addCleanup(holder.cleanup)
        return Path(holder.name)

    def _tree_copy(self, *, shared: bool = False) -> Path:
        # G1 G2 G4: temporary copy of the checkout's tracked files, unchanged or for one mutation.
        tree = self._holder(shared=shared) / "checkout"
        _copy_checkout(tree)
        self.assertTrue((tree / "server_v2" / "readiness.py").is_file(), "copy is missing server_v2/readiness.py")
        self.assertTrue((tree / COLLECTOR).is_file(), f"copy is missing {COLLECTOR.as_posix()} (stage new files with git add)")
        return tree

    def _collect(self, tree: Path) -> tuple[int, str, dict | None, Path]:
        # G1: runs `collect` from a working directory outside the tree; only --root names it.
        script = tree / COLLECTOR
        self.assertTrue(script.is_file(), f"missing collector {COLLECTOR.as_posix()}")
        output = tree.parent / f"manifest-{uuid.uuid4().hex}.json"
        code, text = _run(
            [sys.executable, str(script), "collect", "--root", str(tree), "--output", str(output)],
            tree.parent,
        )
        manifest = json.loads(output.read_text(encoding="utf-8")) if code == 0 and output.is_file() else None
        return code, text, manifest, output

    def _collected(self, tree: Path) -> dict:
        # G1: a successful collection, with the manifest's structural invariants checked.
        code, output, manifest, _ = self._collect(tree)
        self.assertEqual(code, 0, output)
        self.assertIsNotNone(manifest, output)
        self.assertEqual(manifest.get("schema"), MANIFEST_SCHEMA)
        seen: dict[str, str] = {}
        for name in SECTIONS:
            entries = manifest.get(name)
            self.assertIsInstance(entries, list, f"section {name}")
            paths = [entry["path"] for entry in entries]
            self.assertEqual(paths, sorted(paths), f"section {name} must be sorted by path")
            for path in paths:
                self.assertNotIn(path, seen, f"{path} is in both {seen.get(path)} and {name}")
                seen[path] = name
                self.assertFalse(path.startswith("/") or "\\" in path or path in {"", "."}, path)
                self.assertNotIn("..", path.split("/"), path)
        return manifest

    def _clean_collection(self) -> tuple[Path, dict]:
        # G1 G2 G4: one collection of an unchanged copy, shared by the tests that only read it.
        cls = type(self)
        if cls._clean is None:
            tree = self._tree_copy(shared=True)
            cls._clean = (tree, self._collected(tree))
        return cls._clean

    def _write_probe(self, tree: Path, relative: str) -> None:
        # G1: creates a real file inside the copy (never through a symlink).
        target = tree / relative
        for parent in [target.parent, *target.parent.parents]:
            if parent == tree:
                break
            self.assertFalse(parent.is_symlink(), f"probe parent {parent} must not be a symlink")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"card": 432}\n', encoding="utf-8")

    def _inject(self, tree: Path, function: str, *statements: str) -> None:
        # G1: makes `statements` the first statements of one readiness helper.
        readiness = tree / "server_v2" / "readiness.py"
        pattern = re.compile(rf"^def {re.escape(function)}\(\)[^\n]*:\n", re.MULTILINE)
        lines = "".join(f"    {statement}\n" for statement in statements)
        text, count = pattern.subn(lambda m: m.group(0) + lines, readiness.read_text(encoding="utf-8"), count=1)
        self.assertEqual(count, 1, f"expected one `def {function}()` in readiness")
        readiness.write_text(text, encoding="utf-8")

    def _image_root(self, tree: Path) -> Path:
        # G2: offline stand-in for /app in the API image: only what the runtime stage copies.
        image = self._holder() / "app"
        image.mkdir()
        for relative in IMAGE_LAYOUT:
            source = tree / relative
            self.assertTrue(source.exists(), f"image layout source {relative} is missing from the copy")
            target = image / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(source, target)
        return image

    def _verify(self, image_root: Path, manifest: dict | str | None = None, *, stdin: bool = False) -> tuple[int, str]:
        # G2: runs `verify` with the checkout's collector against an image root.
        script = REPO_ROOT / COLLECTOR
        self.assertTrue(script.is_file(), f"missing collector {COLLECTOR.as_posix()}")
        payload = manifest if isinstance(manifest, str) else json.dumps(manifest)
        if stdin:
            return _run(
                [sys.executable, str(script), "verify", "--manifest", "-", "--image-root", str(image_root)],
                image_root.parent,
                stdin=payload,
            )
        manifest_path = self._holder() / "manifest.json"
        manifest_path.write_text(payload, encoding="utf-8")
        return _run(
            [sys.executable, str(script), "verify", "--manifest", str(manifest_path), "--image-root", str(image_root)],
            image_root.parent,
        )

    # G1 — collector

    def test_collect_reports_the_event_contract_as_a_runtime_file(self) -> None:
        # G1: the #428 path is collected from readiness itself, with its label and digest.
        tree, manifest = self._clean_collection()
        runtime = _section(manifest, "runtime")
        self.assertIn(EVENT_CONTRACT, runtime)
        entry = runtime[EVENT_CONTRACT]
        self.assertEqual(entry.get("kind"), "file")
        self.assertEqual(entry.get("sha256"), _sha256(tree / EVENT_CONTRACT))
        self.assertIn("mobile_events", entry.get("labels", []))
        packaging_labels = set(manifest.get("packagingLabels") or [])
        self.assertTrue({"operations", "external_release", "native_mobile"} <= packaging_labels, packaging_labels)
        self.assertNotIn("mobile_events", packaging_labels)
        for path, entry in runtime.items():
            parts = path.split("/")
            self.assertNotIn(parts[0], PRIVATE_ROOTS, path)
            self.assertNotIn("__pycache__", parts, path)
            self.assertFalse(path.endswith(".pyc"), path)
            self.assertIn(entry.get("kind"), {"file", "dir"}, path)
            if entry.get("kind") == "file":
                self.assertEqual(entry.get("sha256"), _sha256(tree / path), path)
            self.assertTrue(set(entry.get("labels") or []) - packaging_labels, f"{path} has no runtime label")

    def test_collect_attributes_operations_reads_to_packaging(self) -> None:
        # G1: paths read only for a PACKAGING_LABELS check are packaging, attributed by label.
        _, manifest = self._clean_collection()
        runtime = _section(manifest, "runtime")
        packaging = _section(manifest, "packaging")
        for path in ("render.yaml", "web_v2/vercel.json", "docs/security/secrets.md"):
            self.assertIn(path, packaging)
            self.assertIn("operations", packaging[path].get("labels", []), path)
            self.assertNotIn(path, runtime)
        self.assertFalse([path for path in runtime if path.startswith(("docs/", "mobile/ios/"))])

    def test_collect_records_opens_probes_and_listings_of_a_runtime_check(self) -> None:
        # G1: Path reads, builtin open, os.path and os.access probes and directory listings all count.
        tree = self._tree_copy()
        for relative in (
            "runtime_probe/extra.json",
            "runtime_probe/builtin_open.json",
            "runtime_probe/stat_only.json",
            "runtime_probe/access_only.json",
            "runtime_probe_dir/item.json",
        ):
            self._write_probe(tree, relative)
        self._inject(
            tree,
            RUNTIME_READER,
            'Path("runtime_probe/extra.json").read_text(encoding="utf-8")',
            'open("runtime_probe/builtin_open.json", encoding="utf-8").close()',
            '__import__("os").path.isfile("runtime_probe/stat_only.json")',
            '__import__("os").access("runtime_probe/access_only.json", 4)',
            'list(Path("runtime_probe_dir").iterdir())',
        )

        runtime = _section(self._collected(tree), "runtime")

        for path in (
            "runtime_probe/extra.json",
            "runtime_probe/builtin_open.json",
            "runtime_probe/stat_only.json",
            "runtime_probe/access_only.json",
        ):
            self.assertIn(path, runtime)
            self.assertEqual(runtime[path].get("kind"), "file", path)
            self.assertEqual(runtime[path].get("sha256"), _sha256(tree / path), path)
            self.assertIn("mobile_events", runtime[path].get("labels", []), path)
        self.assertIn("runtime_probe_dir", runtime)
        self.assertEqual(runtime["runtime_probe_dir"].get("kind"), "dir")

    def test_collect_follows_a_moved_runtime_contract(self) -> None:
        # G1: the paths come from readiness, not from a list kept next to the Dockerfile.
        tree = self._tree_copy()
        relocated = tree / "relocated_contracts" / "live_round_event.schema.json"
        relocated.parent.mkdir(parents=True)
        shutil.copyfile(tree / EVENT_CONTRACT, relocated)
        readiness = tree / "server_v2" / "readiness.py"
        text, count = EVENT_CONTRACT_CONSTANT.subn(
            'LIVE_ROUND_EVENT_CONTRACT = Path("relocated_contracts/live_round_event.schema.json")',
            readiness.read_text(encoding="utf-8"),
        )
        self.assertEqual(count, 1, "expected one LIVE_ROUND_EVENT_CONTRACT assignment in readiness")
        readiness.write_text(text, encoding="utf-8")

        runtime = _section(self._collected(tree), "runtime")

        self.assertIn("relocated_contracts/live_round_event.schema.json", runtime)
        self.assertIn("mobile_events", runtime["relocated_contracts/live_round_event.schema.json"].get("labels", []))

    def test_collect_keeps_packaging_only_reads_out_of_runtime(self) -> None:
        # G1: a file read only by a packaging check (external_release) is never a runtime path.
        tree = self._tree_copy()
        self._write_probe(tree, "packaging_probe/extra.json")
        self._inject(tree, PACKAGING_READER, 'Path("packaging_probe/extra.json").read_text(encoding="utf-8")')

        manifest = self._collected(tree)

        self.assertNotIn("packaging_probe/extra.json", _section(manifest, "runtime"))
        packaging = _section(manifest, "packaging")
        self.assertIn("packaging_probe/extra.json", packaging)
        self.assertIn("external_release", packaging["packaging_probe/extra.json"].get("labels", []))

    def test_collect_keeps_a_path_shared_with_packaging_in_runtime(self) -> None:
        # G1: a path read by a runtime check stays runtime even when a packaging check reads it too.
        tree = self._tree_copy()
        self._inject(tree, RUNTIME_READER, 'Path("ops/smoke_private_trial.sh").read_text(encoding="utf-8")')

        manifest = self._collected(tree)

        runtime = _section(manifest, "runtime")
        self.assertIn("ops/smoke_private_trial.sh", runtime)
        labels = set(runtime["ops/smoke_private_trial.sh"].get("labels", []))
        self.assertTrue({"mobile_events", "operations"} <= labels, labels)
        self.assertNotIn("ops/smoke_private_trial.sh", _section(manifest, "packaging"))

    def test_collect_excludes_private_root_reads(self) -> None:
        # G1: private-root paths (ops/start_api.sh links them to AI_CADDIE_PRIVATE_ROOT) are not image content.
        tree = self._tree_copy()
        self._write_probe(tree, "data/card432_probe.json")
        self._inject(tree, RUNTIME_READER, 'Path("data/card432_probe.json").read_text(encoding="utf-8")')

        manifest = self._collected(tree)

        excluded = _section(manifest, "excluded")
        self.assertIn("data/card432_probe.json", excluded)
        self.assertEqual(excluded["data/card432_probe.json"].get("reason"), "private_root")
        for name in ("runtime", "absent", "packaging"):
            self.assertNotIn("data/card432_probe.json", _section(manifest, name), name)

    def test_collect_reports_a_read_after_the_final_check_as_runtime(self) -> None:
        # G1: a read after the last `_check` call has no later check; it stays in scope.
        tree = self._tree_copy()
        self._write_probe(tree, "runtime_probe/after_final_check.json")
        readiness = tree / "server_v2" / "readiness.py"
        statement = '    Path("runtime_probe/after_final_check.json").read_text(encoding="utf-8")\n'
        text, count = RUNTIME_STATUS_STATEMENT.subn(
            lambda m: statement + m.group(0), readiness.read_text(encoding="utf-8"), count=1
        )
        self.assertEqual(count, 1, "expected one `runtime_checks = [` statement in readiness")
        readiness.write_text(text, encoding="utf-8")

        runtime = _section(self._collected(tree), "runtime")

        self.assertIn("runtime_probe/after_final_check.json", runtime)
        self.assertIn(AFTER_FINAL_CHECK, runtime["runtime_probe/after_final_check.json"].get("labels", []))

    def test_collect_lists_a_missing_runtime_path_as_absent(self) -> None:
        # G1: a runtime probe of a path the tree does not have is reported, but not required in the image.
        tree = self._tree_copy()
        self._inject(tree, RUNTIME_READER, 'Path("runtime_probe/never_created.json").exists()')

        manifest = self._collected(tree)

        absent = _section(manifest, "absent")
        self.assertIn("runtime_probe/never_created.json", absent)
        self.assertIn("mobile_events", absent["runtime_probe/never_created.json"].get("labels", []))
        self.assertNotIn("runtime_probe/never_created.json", _section(manifest, "runtime"))

    def test_collect_runs_readiness_in_a_fresh_interpreter(self) -> None:
        # G1: main() called where readiness already ran (warm lru_cache) still sees the cached read.
        tree = self._tree_copy()
        self._write_probe(tree, "runtime_probe/cached.json")
        readiness = tree / "server_v2" / "readiness.py"
        readiness.write_text(
            readiness.read_text(encoding="utf-8").rstrip("\n")
            + "\n\n\n"
            + '@__import__("functools").lru_cache(maxsize=1)\n'
            + "def _card432_cached_probe() -> str:\n"
            + '    return Path("runtime_probe/cached.json").read_text(encoding="utf-8")\n',
            encoding="utf-8",
        )
        self._inject(tree, RUNTIME_READER, "_card432_cached_probe()")
        output = tree.parent / "warm-manifest.json"
        env = _base_env()
        env["PYTHONPATH"] = os.pathsep.join(part for part in (str(tree), env.get("PYTHONPATH", "")) if part)
        script = (
            "import runpy, sys\n"
            "from server_v2 import readiness\n"
            "readiness.build_readiness_response()\n"
            "namespace = runpy.run_path(sys.argv[1], run_name='card432_collector')\n"
            "raise SystemExit(namespace['main'](['collect', '--root', sys.argv[2], '--output', sys.argv[3]]))\n"
        )

        code, text = _run(
            [sys.executable, "-c", script, str(tree / COLLECTOR), str(tree), str(output)],
            tree,
            env=env,
        )

        self.assertEqual(code, 0, text)
        manifest = json.loads(output.read_text(encoding="utf-8"))
        self.assertIn("runtime_probe/cached.json", _section(manifest, "runtime"))

    def test_collect_does_not_read_dockerfile_or_dockerignore(self) -> None:
        # G1 G4: the collector is independent of the build files; no static parsing is left.
        _, clean = self._clean_collection()
        tree = self._tree_copy()
        (tree / "Dockerfile").unlink()
        dockerignore = tree / ".dockerignore"
        if dockerignore.exists():
            dockerignore.unlink()

        manifest = self._collected(tree)

        self.assertEqual(set(_section(manifest, "runtime")), set(_section(clean, "runtime")))
        for name in SECTIONS:
            paths = set(_section(manifest, name))
            self.assertFalse({"Dockerfile", ".dockerignore"} & paths, name)

    def test_collect_fails_closed_when_readiness_cannot_run(self) -> None:
        # G1: a readiness child that crashes is a failed collection with its error, and no manifest.
        tree = self._tree_copy()
        readiness = tree / "server_v2" / "readiness.py"
        readiness.write_text(
            readiness.read_text(encoding="utf-8").rstrip("\n") + '\n\nraise RuntimeError("card432 readiness boom")\n',
            encoding="utf-8",
        )

        code, output, _, manifest_path = self._collect(tree)

        self.assertNotEqual(code, 0, output)
        self.assertIn("card432 readiness boom", output)
        self.assertFalse(manifest_path.exists(), "a failed collection must not write a manifest")

    # G2 — verifier

    def test_verify_passes_on_the_runtime_stage_layout(self) -> None:
        # G2 G3: collect then verify, as CI does, against what today's runtime stage ships.
        tree, manifest = self._clean_collection()
        image = self._image_root(tree)

        code, output = self._verify(image, manifest)

        self.assertEqual(code, 0, output)
        self.assertNotIn("missing from image", output)
        self.assertNotIn("differs in image", output)

    def test_verify_reports_a_runtime_file_missing_from_the_image(self) -> None:
        # G2: the #428 failure mode: mobile/contracts is not in the image.
        tree, manifest = self._clean_collection()
        image = self._image_root(tree)
        shutil.rmtree(image / "mobile" / "contracts")

        code, output = self._verify(image, manifest)

        self.assertNotEqual(code, 0, output)
        self.assertIn(f"missing from image: {EVENT_CONTRACT}", output)

    def test_verify_reports_a_runtime_file_that_differs_in_the_image(self) -> None:
        # G2: a stale or different copy in the image is not the file readiness was collected with.
        tree, manifest = self._clean_collection()
        image = self._image_root(tree)
        (image / EVENT_CONTRACT).write_text('{"properties": {}}\n', encoding="utf-8")

        code, output = self._verify(image, manifest)

        self.assertNotEqual(code, 0, output)
        self.assertIn(f"differs in image: {EVENT_CONTRACT}", output)

    def test_verify_checks_only_runtime_entries_and_their_kind(self) -> None:
        # G2: packaging, absent and excluded entries are not required; a runtime entry must have its kind.
        image = self._holder() / "app"
        (image / "runtime_dir").mkdir(parents=True)
        (image / "runtime_file.json").write_text("{}\n", encoding="utf-8")
        (image / "wrong_kind").write_text("{}\n", encoding="utf-8")
        digest = hashlib.sha256(b"{}\n").hexdigest()
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "packagingLabels": ["operations"],
            "runtime": [
                {"path": "runtime_dir", "kind": "dir", "labels": ["mobile_events"]},
                {"path": "runtime_file.json", "kind": "file", "sha256": digest, "labels": ["mobile_events"]},
            ],
            "packaging": [{"path": "docs/security/secrets.md", "labels": ["operations"]}],
            "absent": [{"path": "runtime_probe/never_created.json", "labels": ["mobile_events"]}],
            "excluded": [{"path": "data/history.json", "reason": "private_root"}],
        }

        code, output = self._verify(image, manifest, stdin=True)
        self.assertEqual(code, 0, output)

        manifest["runtime"].append({"path": "wrong_kind", "kind": "dir", "labels": ["mobile_events"]})
        code, output = self._verify(image, manifest)
        self.assertNotEqual(code, 0, output)
        self.assertIn("missing from image: wrong_kind", output)

    def test_verify_fails_closed_on_an_unusable_manifest(self) -> None:
        # G2: an empty, malformed, foreign or path-escaping manifest never verifies an image.
        image = self._holder() / "app"
        image.mkdir()
        (image / "runtime_file.json").write_text("{}\n", encoding="utf-8")
        (image.parent / "outside.json").write_text("{}\n", encoding="utf-8")
        digest = hashlib.sha256(b"{}\n").hexdigest()

        def manifest(runtime: list[dict], schema: str = MANIFEST_SCHEMA) -> dict:
            return {"schema": schema, "packagingLabels": [], "runtime": runtime, "packaging": [], "absent": [], "excluded": []}

        good = {"path": "runtime_file.json", "kind": "file", "sha256": digest, "labels": ["mobile_events"]}
        cases = {
            "no runtime entries": manifest([]),
            "foreign schema": manifest([good], schema="something-else-v1"),
            "not JSON": "{not json",
            "file without digest": manifest([{"path": "runtime_file.json", "kind": "file", "labels": ["mobile_events"]}]),
            "parent escape": manifest([good, {**good, "path": "../outside.json"}]),
            "absolute path": manifest([good, {**good, "path": str(image.parent / "outside.json")}]),
        }
        for name, payload in cases.items():
            with self.subTest(name):
                code, output = self._verify(image, payload)
                self.assertNotEqual(code, 0, output)
                self.assertIn("invalid manifest", output)
                self.assertNotIn("Traceback", output)

    # G3 — CI verifies the built image

    def test_ci_docker_job_verifies_the_built_api_image(self) -> None:
        # G3: the docker job collects the manifest and verifies it inside the image it built.
        workflow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
        jobs = workflow["jobs"]
        for job in ("backend", "frontend", "docker"):
            self.assertIn(job, jobs)
        docker = jobs["docker"]
        self.assertFalse(docker.get("continue-on-error"), "the docker job must not tolerate failures")
        steps = docker["steps"]
        runs = [str(step.get("run") or "") for step in steps]
        build = [i for i, run in enumerate(runs) if "docker build -f Dockerfile " in run]
        collect = [i for i, run in enumerate(runs) if "readiness_runtime_paths.py collect" in run]
        verify = [i for i, run in enumerate(runs) if "readiness_runtime_paths.py verify" in run]
        self.assertTrue(build, "docker job no longer builds the API image")
        self.assertTrue(collect, "docker job does not collect readiness runtime paths")
        self.assertTrue(verify, "docker job does not verify readiness runtime paths")
        self.assertGreater(min(verify), build[0], "verification must run against the image built in this job")
        self.assertGreaterEqual(min(verify), min(collect), "verification needs the collected manifest")
        verify_run = runs[min(verify)]
        self.assertIn("--image-root /app", verify_run)
        self.assertRegex(verify_run, r"docker\s+(run|exec)\b")
        self.assertRegex(verify_run, r"garmin-ai-caddie-api|aicaddie-api")
        for index in set(collect + verify):
            step = steps[index]
            self.assertFalse(step.get("continue-on-error"), step.get("name"))
            self.assertNotIn("if", step, f"{step.get('name')} must run on every docker job run")
            for line in runs[index].splitlines():
                if "readiness_runtime_paths.py" in line:
                    self.assertNotRegex(line, r"\|\|\s*(true|:)", line)

    # G4 — superseded static parsing removed

    def test_static_dockerfile_parser_and_its_tests_are_removed(self) -> None:
        # G4: the manifest tests still pass without the static parser and its helper tests.
        tree = self._tree_copy()
        env = _base_env()
        env["PYTHONPATH"] = os.pathsep.join(part for part in (str(tree), env.get("PYTHONPATH", "")) if part)

        code, output = _run([sys.executable, "-m", "unittest", "-v", "tests.test_deployment_manifests"], tree, env=env)

        self.assertEqual(code, 0, output)
        self.assertRegex(output, r"Ran [1-9]\d* tests?")
        for name in SUPERSEDED_TESTS:
            self.assertNotIn(name, output)
        manifests_text = (tree / "tests" / "test_deployment_manifests.py").read_text(encoding="utf-8")
        for name in SUPERSEDED_HELPERS:
            self.assertNotRegex(manifests_text, rf"\b{re.escape(name)}\b", name)
        self.assertNotIn("dockerignore", manifests_text)
        self.assertNotIn("dockerignore", (tree / COLLECTOR).read_text(encoding="utf-8"))
        for path in sorted((tree / "tests").rglob("*.py")):
            if "acceptance" in path.relative_to(tree / "tests").parts:
                continue
            self.assertNotIn(SUPERSEDED_SENTENCE, path.read_text(encoding="utf-8"), path.relative_to(tree).as_posix())


if __name__ == "__main__":
    unittest.main()
