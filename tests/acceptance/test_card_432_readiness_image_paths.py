"""Card #432: every repository path readiness reads for runtimeStatus is in the built API image.

`ops/readiness_runtime_paths.py` has two commands:

- `collect` runs `build_readiness_response()` in a fresh interpreter, records every repository
  path it opens, probes or lists, attributes each path to the readiness check label it was read
  for, and writes a JSON manifest (runtime / packaging / absent / excluded);
- `verify` checks the manifest's runtime entries against an image root. In CI's `docker` job that
  root is `/app` inside the API image the job just built.

These tests run both commands as subprocesses on temporary copies of the checkout's tracked files.
The real image is only available in CI; offline, an image root is assembled from the paths today's
runtime stage copies (IMAGE_LAYOUT).

Revision 9 hardens the suite against implementations that only look right: probe paths are unique
per run, one path is reachable only through data readiness reads, labels are compared exactly, the
collector's environment, root selection and failure handling are exercised, and the CI steps are
checked structurally so that a fail-open or redirected verification cannot pass.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import shlex
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
IMAGE_SCRIPT = "/app/ops/readiness_runtime_paths.py"
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
EXCLUSION_REASONS = {"private_root", "build_environment", "bytecode"}
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
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
    # G1 G2 G3 G4: tracked (and staged) files only; None when git cannot list them.
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


def _with_pythonpath(env: dict[str, str], first: Path) -> dict[str, str]:
    # G1 G4: `env` with `first` ahead of any PYTHONPATH the runtime already uses.
    env = dict(env)
    env["PYTHONPATH"] = os.pathsep.join(part for part in (str(first), env.get("PYTHONPATH", "")) if part)
    return env


def _run_split(
    command: list[str], cwd: Path, *, env: dict[str, str] | None = None, stdin: str | None = None
) -> tuple[int, str, str]:
    # G1 G2 G4: one real subprocess; returns the exit code, stdout and stderr separately.
    proc = subprocess.run(
        command,
        cwd=cwd,
        env=env or _base_env(),
        input=stdin,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _run(command: list[str], cwd: Path, *, env: dict[str, str] | None = None, stdin: str | None = None) -> tuple[int, str]:
    # G1 G2 G4: one real subprocess; returns the exit code and stdout+stderr.
    code, stdout, stderr = _run_split(command, cwd, env=env, stdin=stdin)
    return code, stdout + stderr


def _sha256(path: Path) -> str:
    # G1 G2: digest the manifest must carry for a runtime file.
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _section(manifest: dict, name: str) -> dict[str, dict]:
    # G1: one manifest section keyed by path.
    entries = manifest.get(name)
    assert isinstance(entries, list), f"manifest section {name!r} must be a list"
    return {entry["path"]: entry for entry in entries}


def _probe_dir() -> str:
    # G1: a top-level probe directory name no implementation can know in advance.
    return f"probe_{uuid.uuid4().hex[:12]}"


def _with_statements(text: str, function: str, statements: tuple[str, ...]) -> tuple[str, int]:
    # G1: readiness source with `statements` as the first statements of one argument-free helper.
    pattern = re.compile(rf"^def {re.escape(function)}\(\)[^\n]*:\n", re.MULTILINE)
    lines = "".join(f"    {statement}\n" for statement in statements)
    return pattern.subn(lambda match: match.group(0) + lines, text, count=1)


def _logical_lines(run: str) -> list[str]:
    # G3: shell lines of a step, with backslash continuations joined as bash reads them.
    joined = re.sub(r"\\\n[ \t]*", " ", run)
    return [line.strip() for line in joined.splitlines() if line.strip()]


def _option_value(tokens: list[str], option: str) -> str | None:
    # G3: the value of `option value` or `option=value` among shell words.
    for index, token in enumerate(tokens):
        if token == option and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith(option + "="):
            return token[len(option) + 1 :]
    return None


def _collect_output(tokens: list[str]) -> str | None:
    # G3: the file a collect command writes its manifest to (`--output FILE` or `> FILE`).
    value = _option_value(tokens, "--output")
    if value not in (None, "-"):
        return value
    for index, token in enumerate(tokens):
        if token == ">" and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith(">") and len(token) > 1:
            return token[1:]
    return None


def _mount_targets(options: list[str]) -> list[str]:
    # G3: container paths that `docker run` options mount over; --volumes-from counts as "/".
    targets: list[str] = []
    index = 0
    while index < len(options):
        option = options[index]
        index += 1
        if option in {"-v", "--volume", "--mount", "--volumes-from"}:
            name = option
            value = options[index] if index < len(options) else ""
            index += 1
        elif option.startswith(("--volume=", "--mount=", "--volumes-from=")):
            name, _, value = option.partition("=")
        elif option.startswith("-v") and not option.startswith("--"):
            name, value = "-v", option[2:].removeprefix("=")
        else:
            continue
        if name == "--volumes-from":
            targets.append("/")
        elif name == "--mount":
            fields = dict(field.partition("=")[::2] for field in value.split(","))
            targets.append(fields.get("target") or fields.get("dst") or fields.get("destination") or "")
        else:
            parts = value.split(":")
            targets.append(parts[1] if len(parts) > 1 else parts[0])
    return targets


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

    def _collect(
        self, tree: Path, *, output: Path | None = None, env: dict[str, str] | None = None
    ) -> tuple[int, str, dict | None, Path]:
        # G1: runs `collect` from a working directory outside the tree; only --root names it.
        script = tree / COLLECTOR
        self.assertTrue(script.is_file(), f"missing collector {COLLECTOR.as_posix()}")
        output = output or tree.parent / f"manifest-{uuid.uuid4().hex}.json"
        code, text = _run(
            [sys.executable, str(script), "collect", "--root", str(tree), "--output", str(output)],
            tree.parent,
            env=env,
        )
        manifest = json.loads(output.read_text(encoding="utf-8")) if code == 0 and output.is_file() else None
        return code, text, manifest, output

    def _check_manifest(self, manifest: dict) -> dict:
        # G1: the manifest's structural invariants: schema, sorted sections and labels, one section
        # per path, normalised paths, digests for runtime files, a reason for every exclusion.
        self.assertEqual(manifest.get("schema"), MANIFEST_SCHEMA)
        packaging_labels = manifest.get("packagingLabels")
        self.assertIsInstance(packaging_labels, list, "packagingLabels")
        self.assertEqual(packaging_labels, sorted(packaging_labels), "packagingLabels must be sorted")
        seen: dict[str, str] = {}
        for name in SECTIONS:
            entries = manifest.get(name)
            self.assertIsInstance(entries, list, f"section {name}")
            paths = [entry["path"] for entry in entries]
            self.assertEqual(paths, sorted(paths), f"section {name} must be sorted by path")
            for entry in entries:
                path = entry["path"]
                self.assertNotIn(path, seen, f"{path} is in both {seen.get(path)} and {name}")
                seen[path] = name
                self.assertFalse(path.startswith("/") or "\\" in path or path in {"", "."}, path)
                self.assertNotIn("..", path.split("/"), path)
                if name == "excluded":
                    self.assertIn(entry.get("reason"), EXCLUSION_REASONS, path)
                    continue
                labels = entry.get("labels")
                self.assertIsInstance(labels, list, path)
                self.assertTrue(labels, f"{path} has no labels")
                self.assertEqual(labels, sorted(labels), f"labels of {path} must be sorted")
                if name == "runtime":
                    self.assertIn(entry.get("kind"), {"file", "dir"}, path)
                    if entry.get("kind") == "file":
                        self.assertTrue(SHA256_HEX.fullmatch(str(entry.get("sha256"))), f"{path} needs a lowercase hex SHA-256")
        return manifest

    def _collected(self, tree: Path, *, env: dict[str, str] | None = None) -> dict:
        # G1: a successful collection, with the manifest's structural invariants checked.
        code, output, manifest, _ = self._collect(tree, env=env)
        self.assertEqual(code, 0, output)
        self.assertIsNotNone(manifest, output)
        return self._check_manifest(manifest)

    def _clean_collection(self) -> tuple[Path, dict]:
        # G1 G2 G4: one collection of an unchanged copy, shared by the tests that only read it.
        cls = type(self)
        if cls._clean is None:
            tree = self._tree_copy(shared=True)
            cls._clean = (tree, self._collected(tree))
        return cls._clean

    def _write_probe(self, tree: Path, relative: str, text: str = '{"card": 432}\n') -> None:
        # G1: creates a real file inside the copy (never through a symlink).
        target = tree / relative
        for parent in [target.parent, *target.parent.parents]:
            if parent == tree:
                break
            self.assertFalse(parent.is_symlink(), f"probe parent {parent} must not be a symlink")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def _inject(self, tree: Path, function: str, *statements: str) -> None:
        # G1: makes `statements` the first statements of one readiness helper.
        readiness = tree / "server_v2" / "readiness.py"
        text, count = _with_statements(readiness.read_text(encoding="utf-8"), function, statements)
        self.assertEqual(count, 1, f"expected one `def {function}()` in readiness")
        readiness.write_text(text, encoding="utf-8")

    def _append_to_readiness(self, tree: Path, source: str) -> None:
        # G1: appends module-level statements to the copy's readiness (they run at import).
        readiness = tree / "server_v2" / "readiness.py"
        readiness.write_text(readiness.read_text(encoding="utf-8").rstrip("\n") + "\n\n\n" + source, encoding="utf-8")

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
        # G1: paths read only for a PACKAGING_LABELS check are packaging, attributed by label;
        # private-root paths those checks probe are excluded, which takes precedence.
        _, manifest = self._clean_collection()
        runtime = _section(manifest, "runtime")
        packaging = _section(manifest, "packaging")
        excluded = _section(manifest, "excluded")
        for path in ("render.yaml", "web_v2/vercel.json", "docs/security/secrets.md"):
            self.assertIn(path, packaging)
            self.assertIn("operations", packaging[path].get("labels", []), path)
            self.assertNotIn(path, runtime)
        self.assertIn("mobile/ios/project.yml", packaging)
        self.assertIn("native_mobile", packaging["mobile/ios/project.yml"].get("labels", []))
        for path in ("backups/latest.json", "logs/private_trial_smoke_latest.json"):
            self.assertIn(path, excluded)
            self.assertEqual(excluded[path].get("reason"), "private_root", path)
        self.assertFalse([path for path in runtime if path.startswith(("docs/", "mobile/ios/"))])

    def test_collect_records_opens_probes_and_listings_of_a_runtime_check(self) -> None:
        # G1: every way of opening, probing or listing a path counts, including a path readiness only
        # learns from data it reads, and each path carries exactly the label of the check that read it.
        tree = self._tree_copy()
        probe = _probe_dir()
        indirect = f"{probe}/named_only_in_pointer.json"
        files = {
            f"{probe}/path_read_text.json": 'Path("{}").read_text(encoding="utf-8")',
            f"{probe}/path_read_bytes.json": 'Path("{}").read_bytes()',
            f"{probe}/path_open.json": 'Path("{}").open("rb").close()',
            f"{probe}/builtin_open.json": 'open("{}", encoding="utf-8").close()',
            f"{probe}/os_open.json": '__import__("os").close(__import__("os").open("{}", __import__("os").O_RDONLY))',
            f"{probe}/path_exists.json": 'Path("{}").exists()',
            f"{probe}/path_is_file.json": 'Path("{}").is_file()',
            f"{probe}/path_is_symlink.json": 'Path("{}").is_symlink()',
            f"{probe}/path_stat.json": 'Path("{}").stat()',
            f"{probe}/os_stat.json": '__import__("os").stat("{}")',
            f"{probe}/os_lstat.json": '__import__("os").lstat("{}")',
            f"{probe}/os_access.json": '__import__("os").access("{}", 4)',
            f"{probe}/os_path_exists.json": '__import__("os").path.exists("{}")',
            f"{probe}/os_path_isfile.json": '__import__("os").path.isfile("{}")',
            f"{probe}/os_path_islink.json": '__import__("os").path.islink("{}")',
            f"{probe}/pointer.txt": 'Path(Path("{}").read_text(encoding="utf-8").strip()).read_text(encoding="utf-8")',
        }
        directories = {
            f"{probe}/path_is_dir": 'Path("{}").is_dir()',
            f"{probe}/os_path_isdir": '__import__("os").path.isdir("{}")',
            f"{probe}/path_iterdir": 'list(Path("{}").iterdir())',
            f"{probe}/path_glob": 'list(Path("{}").glob("*.json"))',
            f"{probe}/path_rglob": 'list(Path("{}").rglob("*.json"))',
            f"{probe}/os_listdir": '__import__("os").listdir("{}")',
            f"{probe}/os_scandir": '__import__("os").scandir("{}").close()',
            f"{probe}/os_walk": 'list(__import__("os").walk("{}"))',
            f"{probe}/glob_glob": '__import__("glob").glob("{}/*.json")',
        }
        for relative in (*files, indirect):
            self._write_probe(tree, relative)
        # The indirect path appears only in this data file, never in readiness source.
        self._write_probe(tree, f"{probe}/pointer.txt", indirect + "\n")
        for relative in directories:
            self._write_probe(tree, f"{relative}/item.json")
        self._write_probe(tree, f"{probe}/path_rglob/nested/item.json")
        self._inject(tree, RUNTIME_READER, *(template.format(path) for path, template in {**files, **directories}.items()))

        runtime = _section(self._collected(tree), "runtime")

        for path in (*files, indirect):
            with self.subTest(path=path):
                self.assertIn(path, runtime)
                self.assertEqual(runtime[path].get("kind"), "file")
                self.assertEqual(runtime[path].get("sha256"), _sha256(tree / path))
                self.assertEqual(runtime[path].get("labels"), ["mobile_events"])
        for path in directories:
            with self.subTest(path=path):
                self.assertIn(path, runtime)
                self.assertEqual(runtime[path].get("kind"), "dir")
                self.assertEqual(runtime[path].get("labels"), ["mobile_events"])

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
        target = f"{_probe_dir()}/packaging_only.json"
        self._write_probe(tree, target)
        self._inject(tree, PACKAGING_READER, f'Path("{target}").read_text(encoding="utf-8")')

        manifest = self._collected(tree)

        self.assertNotIn(target, _section(manifest, "runtime"))
        packaging = _section(manifest, "packaging")
        self.assertIn(target, packaging)
        self.assertEqual(packaging[target].get("labels"), ["external_release"])

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

    def test_collect_excludes_private_root_build_environment_and_bytecode_paths(self) -> None:
        # G1: every private-root name (ops/start_api.sh links them to AI_CADDIE_PRIVATE_ROOT), build
        # environments and bytecode are excluded with their reason, whether or not the path exists;
        # names that only look like them are not.
        tree = self._tree_copy()
        probe = _probe_dir()
        expected = {
            f"data/{probe}.json": "private_root",
            f".garmin_tokens/{probe}.json": "private_root",
            f"output/{probe}.json": "private_root",
            f"logs/{probe}.json": "private_root",
            f"backups/{probe}/__pycache__/cached.pyc": "private_root",
            "clubs.json": "private_root",
            f"{probe}/node_modules/package.json": "build_environment",
            f"{probe}/.venv/pyvenv.cfg": "build_environment",
            f"{probe}/__pycache__/module.json": "bytecode",
            f"{probe}/module.pyc": "bytecode",
        }
        lookalikes = (f"data_{probe}/kept.json", f"{probe}/data/kept.json")
        for relative in lookalikes:
            self._write_probe(tree, relative)
        self._inject(
            tree,
            RUNTIME_READER,
            *(f'Path("{path}").exists()' for path in expected),
            *(f'Path("{path}").read_text(encoding="utf-8")' for path in lookalikes),
        )

        manifest = self._collected(tree)

        excluded = _section(manifest, "excluded")
        for path, reason in expected.items():
            with self.subTest(path=path):
                self.assertIn(path, excluded)
                self.assertEqual(excluded[path].get("reason"), reason)
        runtime = _section(manifest, "runtime")
        for path in lookalikes:
            with self.subTest(path=path):
                self.assertIn(path, runtime)
                self.assertEqual(runtime[path].get("labels"), ["mobile_events"])

    def test_collect_reports_a_read_after_the_final_check_as_runtime(self) -> None:
        # G1: a read after the last `_check` call has no later check; it stays in scope.
        tree = self._tree_copy()
        target = f"{_probe_dir()}/after_final_check.json"
        self._write_probe(tree, target)
        readiness = tree / "server_v2" / "readiness.py"
        statement = f'    Path("{target}").read_text(encoding="utf-8")\n'
        text, count = RUNTIME_STATUS_STATEMENT.subn(
            lambda m: statement + m.group(0), readiness.read_text(encoding="utf-8"), count=1
        )
        self.assertEqual(count, 1, "expected one `runtime_checks = [` statement in readiness")
        readiness.write_text(text, encoding="utf-8")

        runtime = _section(self._collected(tree), "runtime")

        self.assertIn(target, runtime)
        self.assertEqual(runtime[target].get("labels"), [AFTER_FINAL_CHECK])

    def test_collect_lists_a_missing_runtime_path_as_absent(self) -> None:
        # G1: a runtime probe of a path the tree does not have is reported, but not required in the image.
        tree = self._tree_copy()
        target = f"{_probe_dir()}/never_created.json"
        self._inject(tree, RUNTIME_READER, f'Path("{target}").exists()')

        manifest = self._collected(tree)

        absent = _section(manifest, "absent")
        self.assertIn(target, absent)
        self.assertEqual(absent[target].get("labels"), ["mobile_events"])
        self.assertNotIn(target, _section(manifest, "runtime"))

    def test_collect_runs_readiness_in_a_fresh_interpreter(self) -> None:
        # G1: main() called where readiness already ran (warm lru_cache) still sees the cached read.
        tree = self._tree_copy()
        target = f"{_probe_dir()}/cached.json"
        self._write_probe(tree, target)
        self._append_to_readiness(
            tree,
            '@__import__("functools").lru_cache(maxsize=1)\n'
            + "def _card432_cached_probe() -> str:\n"
            + f'    return Path("{target}").read_text(encoding="utf-8")\n',
        )
        self._inject(tree, RUNTIME_READER, "_card432_cached_probe()")
        output = tree.parent / "warm-manifest.json"
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
            env=_with_pythonpath(_base_env(), tree),
        )

        self.assertEqual(code, 0, text)
        manifest = self._check_manifest(json.loads(output.read_text(encoding="utf-8")))
        self.assertIn(target, _section(manifest, "runtime"))

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
        # G1: a readiness child that crashes, prints no result, or exits non-zero after its result is a
        # failed collection: non-zero exit, and --output is neither created nor overwritten.
        tree = self._tree_copy()
        readiness = tree / "server_v2" / "readiness.py"
        original = readiness.read_text(encoding="utf-8")
        silent_exit, count = _with_statements(original, RUNTIME_READER, ('__import__("os")._exit(0)',))
        self.assertEqual(count, 1, f"expected one `def {RUNTIME_READER}()` in readiness")
        variants = {
            "readiness raises at import": (
                original.rstrip("\n") + '\n\nraise RuntimeError("card432 readiness boom")\n',
                False,
            ),
            "child exits 0 without a result": (silent_exit, True),
            "child exits non-zero after its result": (
                original.rstrip("\n")
                + '\n\n__import__("atexit").register(lambda: (__import__("sys").stdout.flush(), __import__("os")._exit(7)))\n',
                True,
            ),
        }
        for name, (text, existing) in variants.items():
            with self.subTest(name):
                readiness.write_text(text, encoding="utf-8")
                output = tree.parent / f"failed-{uuid.uuid4().hex}.json"
                if existing:
                    output.write_text("previous manifest\n", encoding="utf-8")

                code, log, _, _ = self._collect(tree, output=output)

                self.assertNotEqual(code, 0, log)
                if existing:
                    self.assertEqual(output.read_text(encoding="utf-8"), "previous manifest\n", "output was overwritten")
                else:
                    self.assertFalse(output.exists(), "a failed collection must not write a manifest")
                if name == "readiness raises at import":
                    self.assertIn("card432 readiness boom", log)
        readiness.write_text(original, encoding="utf-8")

    def test_collect_takes_packaging_labels_from_readiness(self) -> None:
        # G1: packagingLabels and the runtime/packaging split follow readiness.PACKAGING_LABELS as it is
        # in the tree, not a list kept in the collector.
        tree = self._tree_copy()
        target = f"{_probe_dir()}/now_packaging.json"
        self._write_probe(tree, target)
        self._inject(tree, RUNTIME_READER, f'Path("{target}").read_text(encoding="utf-8")')
        self._append_to_readiness(
            tree, 'PACKAGING_LABELS = frozenset((PACKAGING_LABELS | {"mobile_events"}) - {"operations"})\n'
        )

        manifest = self._collected(tree)

        packaging_labels = manifest.get("packagingLabels") or []
        self.assertIn("mobile_events", packaging_labels)
        self.assertIn("external_release", packaging_labels)
        self.assertNotIn("operations", packaging_labels)
        packaging = _section(manifest, "packaging")
        runtime = _section(manifest, "runtime")
        self.assertIn(target, packaging)
        self.assertEqual(packaging[target].get("labels"), ["mobile_events"])
        self.assertNotIn(target, runtime)
        self.assertIn("render.yaml", runtime)
        self.assertEqual(runtime["render.yaml"].get("kind"), "file")
        self.assertEqual(runtime["render.yaml"].get("sha256"), _sha256(tree / "render.yaml"))
        self.assertIn("operations", runtime["render.yaml"].get("labels", []))

    def test_collect_forces_fixture_mode_and_imports_readiness_from_root(self) -> None:
        # G1: the readiness child runs in fixture mode without a private root, whatever the caller's
        # environment says, and imports readiness from --root even when PYTHONPATH names another checkout.
        tree = self._tree_copy()
        probe = _probe_dir()
        private_root = self._holder() / "private-root"
        private_root.mkdir()
        self._inject(
            tree,
            RUNTIME_READER,
            f'Path("{probe}/mode-" + __import__("os").environ.get("AI_CADDIE_DATA_MODE", "unset") + ".json").exists()',
            f'Path("{probe}/private-root-" + ("set" if "AI_CADDIE_PRIVATE_ROOT" in __import__("os").environ else "unset") + ".json").exists()',
        )
        env = _with_pythonpath(_base_env(), REPO_ROOT)
        env["AI_CADDIE_DATA_MODE"] = "local"
        env["AI_CADDIE_PRIVATE_ROOT"] = str(private_root)
        env["PYTHONSAFEPATH"] = "1"

        manifest = self._collected(tree, env=env)

        absent = _section(manifest, "absent")
        for path in (f"{probe}/mode-fixture.json", f"{probe}/private-root-unset.json"):
            self.assertIn(path, absent)
            self.assertEqual(absent[path].get("labels"), ["mobile_events"])
        everything = {path for name in SECTIONS for path in _section(manifest, name)}
        self.assertNotIn(f"{probe}/mode-local.json", everything)
        self.assertNotIn(f"{probe}/private-root-set.json", everything)
        self.assertEqual(sorted(private_root.iterdir()), [], "the collector wrote into the private root")

    def test_collect_defaults_to_the_script_checkout_and_honours_root(self) -> None:
        # G1: without --root the script's own checkout is collected; with --root that tree is, whichever
        # checkout the script lives in. Without --output (or with -) the manifest is stdout's only content.
        tree = self._tree_copy()
        target = f"{_probe_dir()}/root_selection.json"
        self._write_probe(tree, target)
        self._inject(tree, RUNTIME_READER, f'Path("{target}").read_text(encoding="utf-8")')
        commands = {
            "copy's script, no --root, --output -": [sys.executable, str(tree / COLLECTOR), "collect", "--output", "-"],
            "checkout's script, --root copy, no --output": [
                sys.executable, str(REPO_ROOT / COLLECTOR), "collect", "--root", str(tree),
            ],
        }
        for name, command in commands.items():
            with self.subTest(name):
                code, stdout, stderr = _run_split(command, tree.parent)
                self.assertEqual(code, 0, stderr)
                try:
                    manifest = json.loads(stdout)
                except json.JSONDecodeError as exc:
                    self.fail(f"stdout must hold only the manifest JSON ({exc}): {stdout[:400]!r}")
                runtime = _section(self._check_manifest(manifest), "runtime")
                self.assertIn(target, runtime)
                self.assertEqual(runtime[target].get("labels"), ["mobile_events"])

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
        (image / "file_is_dir").mkdir()
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

        for wrong in (
            {"path": "wrong_kind", "kind": "dir", "labels": ["mobile_events"]},
            {"path": "file_is_dir", "kind": "file", "sha256": digest, "labels": ["mobile_events"]},
        ):
            with self.subTest(wrong["path"]):
                code, output = self._verify(image, {**manifest, "runtime": [*manifest["runtime"], wrong]})
                self.assertNotEqual(code, 0, output)
                self.assertIn(f"missing from image: {wrong['path']}", output)

    def test_verify_reports_every_problem_in_path_order(self) -> None:
        # G2: verification does not stop at the first problem; it prints one line per problem, by path.
        image = self._holder() / "app"
        image.mkdir()
        digest = hashlib.sha256(b"{}\n").hexdigest()
        (image / "aa_ok.json").write_text("{}\n", encoding="utf-8")
        (image / "cc_dir_is_file").write_text("{}\n", encoding="utf-8")
        (image / "kk_file_is_dir").mkdir()
        (image / "mm_differs.json").write_text('{"changed": true}\n', encoding="utf-8")
        runtime = [
            {"path": "zz_missing.json", "kind": "file", "sha256": digest, "labels": ["mobile_events"]},
            {"path": "mm_differs.json", "kind": "file", "sha256": digest, "labels": ["mobile_events"]},
            {"path": "kk_file_is_dir", "kind": "file", "sha256": digest, "labels": ["mobile_events"]},
            {"path": "cc_dir_is_file", "kind": "dir", "labels": ["mobile_events"]},
            {"path": "aa_ok.json", "kind": "file", "sha256": digest, "labels": ["mobile_events"]},
        ]
        manifest = {"schema": MANIFEST_SCHEMA, "packagingLabels": [], "runtime": runtime, "packaging": [], "absent": [], "excluded": []}

        code, output = self._verify(image, manifest)

        self.assertNotEqual(code, 0, output)
        problems = [
            line.strip()
            for line in output.splitlines()
            if line.strip().startswith(("missing from image:", "differs in image:"))
        ]
        self.assertEqual(
            problems,
            [
                "missing from image: cc_dir_is_file",
                "missing from image: kk_file_is_dir",
                "differs in image: mm_differs.json",
                "missing from image: zz_missing.json",
            ],
        )

    def test_verify_fails_closed_on_an_unusable_manifest(self) -> None:
        # G2: an empty, malformed, foreign, unreadable or path-escaping manifest never verifies an
        # image, and validation finishes before any image path is checked.
        image = self._holder() / "app"
        image.mkdir()
        (image / "runtime_file.json").write_text("{}\n", encoding="utf-8")
        (image.parent / "outside.json").write_text("{}\n", encoding="utf-8")
        digest = hashlib.sha256(b"{}\n").hexdigest()

        def manifest(runtime: object, schema: str = MANIFEST_SCHEMA) -> dict:
            return {"schema": schema, "packagingLabels": [], "runtime": runtime, "packaging": [], "absent": [], "excluded": []}

        # Sorted first and absent from the image: checking it before validation would print a problem.
        unchecked = {"path": "aaa_not_in_image.json", "kind": "file", "sha256": digest, "labels": ["mobile_events"]}
        good = {"path": "runtime_file.json", "kind": "file", "sha256": digest, "labels": ["mobile_events"]}
        outside = str(image.parent / "outside.json")
        cases: dict[str, tuple[object, str | None]] = {
            "no runtime entries": (manifest([]), None),
            "runtime is not a list": (manifest({"runtime_file.json": good}), None),
            "manifest is not an object": ("[]", None),
            "foreign schema": (manifest([unchecked, good], schema="something-else-v1"), None),
            "not JSON": ("{not json", None),
            "entry without path": (manifest([unchecked, {"kind": "file", "sha256": digest}]), None),
            "entry without kind": (manifest([unchecked, {"path": "runtime_file.json", "sha256": digest}]), None),
            "unknown kind": (manifest([unchecked, {**good, "kind": "symlink"}]), None),
            "file without digest": (manifest([unchecked, {"path": "runtime_file.json", "kind": "file"}]), None),
            "digest is not lowercase hex": (manifest([unchecked, {**good, "sha256": "not-a-digest"}]), None),
            "parent escape": (manifest([unchecked, good, {**good, "path": "../outside.json"}]), "../outside.json"),
            "absolute path": (manifest([unchecked, good, {**good, "path": outside}]), outside),
            "backslash path": (manifest([unchecked, {**good, "path": "mobile\\contracts\\x.json"}]), "mobile\\contracts\\x.json"),
            "empty path": (manifest([unchecked, {**good, "path": ""}]), ""),
            "dot path": (manifest([unchecked, {**good, "path": "."}]), "."),
        }
        for name, (payload, bad_path) in cases.items():
            with self.subTest(name):
                code, output = self._verify(image, payload)
                self.assertNotEqual(code, 0, output)
                self.assertIn("invalid manifest", output)
                self.assertNotIn("Traceback", output)
                self.assertNotIn("missing from image", output)
                self.assertNotIn("differs in image", output)
                if bad_path is not None:
                    self.assertIn(f"invalid manifest path: {bad_path}", output)
        with self.subTest("manifest file does not exist"):
            code, output = _run(
                [
                    sys.executable, str(REPO_ROOT / COLLECTOR), "verify",
                    "--manifest", str(image.parent / "no-such-manifest.json"), "--image-root", str(image),
                ],
                image.parent,
            )
            self.assertNotEqual(code, 0, output)
            self.assertIn("invalid manifest", output)
            self.assertNotIn("Traceback", output)

    # G3 — CI verifies the built image

    def test_ci_docker_job_verifies_the_built_api_image(self) -> None:
        # G3: the docker job collects a manifest and verifies that same manifest inside the image it built,
        # with the image's own script and /app unmounted, and nothing that lets a failure pass.
        workflow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
        jobs = workflow["jobs"]
        for job in ("backend", "frontend", "docker"):
            self.assertIn(job, jobs)
        docker = jobs["docker"]
        self.assertFalse(docker.get("continue-on-error"), "the docker job must not tolerate failures")
        self.assertNotIn("if", docker, "the docker job must run on every CI run")
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
        tag_match = re.search(r"docker build -f Dockerfile\b[^\n]*?\s-t\s+(\S+)", runs[build[0]])
        self.assertIsNotNone(tag_match, "the API image build must name its tag with -t")
        tag = tag_match.group(1)

        workflow_shell = ((workflow.get("defaults") or {}).get("run") or {}).get("shell")
        job_shell = ((docker.get("defaults") or {}).get("run") or {}).get("shell")
        for index in sorted(set(collect + verify)):
            step = steps[index]
            name = step.get("name") or f"docker step {index}"
            self.assertFalse(step.get("continue-on-error"), name)
            self.assertNotIn("if", step, f"{name} must run on every docker job run")
            self.assertEqual(step.get("shell") or job_shell or workflow_shell or "bash", "bash", f"{name} must keep bash errexit")
            self.assertNotRegex(runs[index], r"\bset\s+\+\w*e|\bset\s+\+o\s+(errexit|pipefail)|\btrap\b", name)
            for line in _logical_lines(runs[index]):
                if "readiness_runtime_paths.py" not in line:
                    continue
                self.assertFalse(set("|&;`") & set(line) or "$(" in line, f"{name}: run the script as one plain command: {line}")
                self.assertNotIn(shlex.split(line)[0], {"!", "if", "elif", "while", "until"}, line)

        collect_lines = [
            line for i in collect for line in _logical_lines(runs[i]) if "readiness_runtime_paths.py collect" in line
        ]
        self.assertTrue(collect_lines, "no command line runs collect")
        collect_tokens = shlex.split(collect_lines[0])
        self.assertTrue(
            collect_tokens[:2] in (["docker", "run"], ["docker", "exec"], ["uv", "run"])
            or posixpath.basename(collect_tokens[0]).startswith("python"),
            f"collect must be run, not quoted: {collect_lines[0]}",
        )
        manifest_file = _collect_output(collect_tokens)
        self.assertTrue(manifest_file and manifest_file != "-", "collect must write the manifest to a file")
        manifest_name = posixpath.basename(manifest_file)
        listed = _listed_files()
        if listed is not None:
            self.assertFalse(
                [path for path in listed if posixpath.basename(path) == manifest_name],
                f"{manifest_name} must be produced by collect, not committed",
            )

        for index in verify:
            for line in _logical_lines(runs[index]):
                if "readiness_runtime_paths.py verify" not in line:
                    continue
                tokens = shlex.split(line)
                self.assertEqual(tokens[:2], ["docker", "run"], line)
                self.assertIn(tag, tokens, f"verify must run in the image this job built ({tag}): {line}")
                image_at = tokens.index(tag)
                for target in _mount_targets(tokens[2:image_at]):
                    normalized = posixpath.normpath(target or ".")
                    self.assertFalse(
                        normalized in {"/", "/app"} or normalized.startswith("/app/"),
                        f"verify must not mount anything over the image's /app: {line}",
                    )
                command = tokens[image_at + 1 :]
                self.assertIn(IMAGE_SCRIPT, command, f"verify must use the script copy inside the image: {line}")
                script_at = command.index(IMAGE_SCRIPT)
                self.assertEqual(command[script_at + 1 : script_at + 2], ["verify"], line)
                image_root = _option_value(command[script_at + 2 :], "--image-root")
                self.assertEqual(posixpath.normpath(image_root or "."), "/app", line)
                self.assertIn(manifest_name, line, f"verify must read the manifest collect wrote ({manifest_name})")

    # G4 — superseded static parsing removed

    def test_static_dockerfile_parser_and_its_tests_are_removed(self) -> None:
        # G4: the manifest tests still pass without the static parser and its helper tests.
        tree = self._tree_copy()

        code, output = _run(
            [sys.executable, "-m", "unittest", "-v", "tests.test_deployment_manifests"],
            tree,
            env=_with_pythonpath(_base_env(), tree),
        )

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

    # G1 G2 — repository tests of the script

    def test_repository_tests_for_the_script_pass(self) -> None:
        # G1 G2: the focused repository tests of ops/readiness_runtime_paths.py exist and pass offline.
        code, output = _run(
            [sys.executable, "-m", "unittest", "-v", "tests.test_readiness_runtime_paths"],
            REPO_ROOT,
            env=_with_pythonpath(_base_env(), REPO_ROOT),
        )

        self.assertEqual(code, 0, output)
        self.assertRegex(output, r"Ran [1-9]\d* tests?")


if __name__ == "__main__":
    unittest.main()
