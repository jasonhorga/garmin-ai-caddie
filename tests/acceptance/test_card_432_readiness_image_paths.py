"""Card #432: every repository path readiness reads for runtimeStatus ships in the API image.

The guard under test is the repository test named by GUARD_TEST. Each case runs it in a
subprocess on a temporary copy of the checkout's tracked files, either unchanged or with one
deliberate change, and checks that it passes on the real tree, fails (naming the path) on each
defect, and stays green for reads that belong to packaging/evidence checks or to the private
runtime root.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_TEST = (
    "tests.test_deployment_manifests.DeploymentManifestTests."
    "test_readiness_runtime_paths_are_copied_into_image"
)
MOBILE_CONTRACTS_COPY = re.compile(r"^COPY\s+mobile/contracts/?\s+\S+\s*$", re.MULTILINE)
OPS_COPY = re.compile(r"^COPY\s+ops/?\s+\S+\s*$", re.MULTILINE)
EVENT_CONTRACT_CONSTANT = re.compile(r"^LIVE_ROUND_EVENT_CONTRACT\s*=.*$", re.MULTILINE)
# The first statement after the final `_check` of build_readiness_response (runtimeStatus is computed here).
RUNTIME_STATUS_STATEMENT = re.compile(r"^    runtime_checks = \[", re.MULTILINE)
# Runtime check (label mobile_events) and packaging check (label external_release).
RUNTIME_READER = "_contract_event_kinds"
PACKAGING_READER = "_external_release_evidence"
SKIP_EVERYWHERE = {
    ".git", ".venv", "node_modules", "__pycache__", ".agenthub-home", ".codex-tmp",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
# Private runtime root links (ops/start_api.sh); never copied out of the checkout.
SKIP_AT_ROOT = {"data", ".garmin_tokens", "output", "logs", "backups", "clubs.json"}


def _random_name() -> str:
    # G1: a fresh, meaningless path component per case, so a guard cannot special-case probe names.
    return "p" + uuid.uuid4().hex[:12]


def _opaque(text: str) -> str:
    # G1: a Python expression that builds `text` at run time. The path never appears as a literal
    # in readiness, so a guard that scans the source instead of tracing readiness cannot see it.
    return f'bytes.fromhex("{text.encode("utf-8").hex()}").decode("utf-8")'


def _environment_roots_inside_checkout() -> list[Path]:
    # G1 G2: temp and home directories inside the checkout must never be copied into a tree.
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
    # G1 G2: caches, runtime environments, private-root names and the temp/home area stay out of copies.
    parts = relative.split("/")
    if any(part in SKIP_EVERYWHERE for part in parts) or relative.endswith(".pyc"):
        return True
    if parts[0] in SKIP_AT_ROOT:
        return True
    # Without git, untracked top-level hidden directories (agent homes, tool caches) stay out.
    if fallback and parts[0].startswith(".") and (REPO_ROOT / parts[0]).is_dir():
        return True
    for root in _environment_roots_inside_checkout():
        try:
            (REPO_ROOT / relative).resolve().relative_to(root)
            return True
        except ValueError:
            pass
    return False


def _listed_files() -> list[str] | None:
    # G1 G2: tracked (and staged) files only; None when git cannot list them.
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
    # G1 G2: copies the checkout into `tree` without following it into itself.
    listed = _listed_files()
    if listed is None:
        def ignore(directory: str, names: list[str]) -> set[str]:
            # G1 G2: the same exclusions as the git-listed copy, applied while walking the tree.
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


def _run_guard(root: Path, *, warm_first: bool = False) -> tuple[int, str]:
    # G1 G2: runs the repository guard test as a real unittest subprocess.
    # With warm_first, the same interpreter evaluates readiness once before the guard runs, as
    # the full CI suite does, so in-process caches are already populated.
    env = dict(os.environ)
    env["AI_CADDIE_DATA_MODE"] = "fixture"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("AI_CADDIE_PRIVATE_ROOT", None)
    env["PYTHONPATH"] = os.pathsep.join(part for part in (str(root), env.get("PYTHONPATH", "")) if part)
    if warm_first:
        command = [
            sys.executable,
            "-c",
            "import unittest\n"
            "from server_v2 import readiness\n"
            "readiness.build_readiness_response()\n"
            f"unittest.main(module=None, argv=['unittest', {GUARD_TEST!r}])\n",
        ]
    else:
        command = [sys.executable, "-m", "unittest", GUARD_TEST]
    proc = subprocess.run(
        command,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return proc.returncode, proc.stdout + proc.stderr


class ReadinessImagePathGuardTests(unittest.TestCase):
    def _tree_copy(self) -> Path:
        # G1 G2: temporary copy of the checkout's tracked files, for the baseline or one mutation.
        holder = tempfile.TemporaryDirectory(prefix="card432-")
        self.addCleanup(holder.cleanup)
        tree = Path(holder.name) / "checkout"
        _copy_checkout(tree)
        self.assertTrue((tree / "server_v2" / "readiness.py").is_file(), "copy is missing server_v2/readiness.py")
        self.assertTrue((tree / "Dockerfile").is_file(), "copy is missing Dockerfile")
        return tree

    def _write_probe(self, tree: Path, relative: str) -> None:
        # G1: creates a real file inside the copy (never through a symlink).
        target = tree / relative
        for parent in [target.parent, *target.parent.parents]:
            if parent == tree:
                break
            self.assertFalse(parent.is_symlink(), f"probe parent {parent} must not be a symlink")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")

    def _inject(self, tree: Path, function: str, statement: str) -> None:
        # G1: makes `statement` the first statement of one readiness helper.
        readiness = tree / "server_v2" / "readiness.py"
        pattern = re.compile(rf"^def {re.escape(function)}\(\)[^\n]*:\n", re.MULTILINE)
        line = f"    {statement}\n"
        text, count = pattern.subn(lambda m: m.group(0) + line, readiness.read_text(encoding="utf-8"), count=1)
        self.assertEqual(count, 1, f"expected one `def {function}()` in readiness")
        readiness.write_text(text, encoding="utf-8")

    def _inject_read(self, tree: Path, function: str, relative: str) -> None:
        # G1: makes one readiness helper read `relative` as its first statement (path built at run time).
        self._inject(tree, function, f'Path({_opaque(relative)}).read_text(encoding="utf-8")')

    def _replace_mobile_contracts_copy(self, tree: Path, replacement: str) -> None:
        # G1: rewrites the single `COPY mobile/contracts/ …` line of the copy's Dockerfile.
        dockerfile = tree / "Dockerfile"
        text, count = MOBILE_CONTRACTS_COPY.subn(lambda _match: replacement, dockerfile.read_text(encoding="utf-8"))
        self.assertEqual(count, 1, "expected exactly one COPY of mobile/contracts in Dockerfile")
        dockerfile.write_text(text, encoding="utf-8")

    def _mobile_contracts_copy_line(self, tree: Path) -> str:
        # G1: the copy's current `COPY mobile/contracts/ …` line, exactly as written.
        match = MOBILE_CONTRACTS_COPY.search((tree / "Dockerfile").read_text(encoding="utf-8"))
        self.assertIsNotNone(match, "expected a COPY of mobile/contracts in Dockerfile")
        return match.group(0)

    def _append_dockerignore(self, tree: Path, pattern: str) -> None:
        # G1: adds one exclusion line to the copy's .dockerignore.
        dockerignore = tree / ".dockerignore"
        text = dockerignore.read_text(encoding="utf-8") if dockerignore.exists() else ""
        dockerignore.write_text(text.rstrip("\n") + f"\n{pattern}\n", encoding="utf-8")

    def _assert_guard_failed(self, code: int, output: str, needle: str) -> None:
        # G1: an assertion failure of the single guard test that names the path.
        self.assertNotEqual(code, 0, output)
        self.assertIn("Ran 1 test", output)
        self.assertIn("FAILED (failures=1)", output)
        self.assertIn(needle, output)

    def _assert_guard_passed(self, code: int, output: str) -> None:
        # G1 G2: the single guard test ran and passed without skipping.
        self.assertEqual(code, 0, output)
        self.assertIn("Ran 1 test", output)
        self.assertNotIn("skipped", output)

    def test_guard_passes_on_a_clean_copy_of_the_checkout(self) -> None:
        # G1 G2: the guard exists, really runs, and the shipped Dockerfile satisfies it.
        # The copy holds the tracked files only, so agent homes, temp areas and tool caches
        # that may sit inside a sandboxed checkout cannot leak into the traced path set.
        tree = self._tree_copy()

        code, output = _run_guard(tree)

        self._assert_guard_passed(code, output)

    def test_guard_fails_when_mobile_contracts_copy_is_removed(self) -> None:
        # G1: the #428 failure mode is caught again.
        tree = self._tree_copy()
        self._replace_mobile_contracts_copy(tree, "")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "mobile/contracts")

    def test_guard_ignores_copy_into_a_build_stage(self) -> None:
        # G1: only COPY instructions of the final (runtime) stage count.
        tree = self._tree_copy()
        dockerfile = tree / "Dockerfile"
        original = dockerfile.read_text(encoding="utf-8")
        match = MOBILE_CONTRACTS_COPY.search(original)
        self.assertIsNotNone(match, "expected a COPY of mobile/contracts in Dockerfile")
        copy_line = match.group(0)
        lines = MOBILE_CONTRACTS_COPY.sub("", original).splitlines()
        first_from = next(i for i, line in enumerate(lines) if line.strip().upper().startswith("FROM "))
        lines.insert(first_from + 1, copy_line)
        moved = "\n".join(lines) + "\n"
        self.assertGreater(
            len(re.findall(r"^FROM\s", moved[moved.index(copy_line):], re.MULTILINE)),
            0,
            "the moved COPY must sit before the runtime stage",
        )
        dockerfile.write_text(moved, encoding="utf-8")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "mobile/contracts")

    def test_guard_fails_when_a_copy_lands_at_the_wrong_destination(self) -> None:
        # G1: `COPY mobile/contracts/ ./` flattens the files into the workdir, so readiness misses them.
        tree = self._tree_copy()
        self._replace_mobile_contracts_copy(tree, "COPY mobile/contracts/ ./")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "mobile/contracts")

    def test_guard_accepts_an_absolute_destination_under_the_workdir(self) -> None:
        # G1: an absolute destination equal to WORKDIR/<path> ships the path at the same place.
        tree = self._tree_copy()
        text = (tree / "Dockerfile").read_text(encoding="utf-8")
        final_stage = text[[m.start() for m in re.finditer(r"^FROM\s", text, re.MULTILINE)][-1]:]
        self.assertRegex(final_stage, r"(?m)^WORKDIR\s+/app\s*$", "expected WORKDIR /app in the runtime stage")
        self._replace_mobile_contracts_copy(tree, "COPY mobile/contracts /app/mobile/contracts")

        code, output = _run_guard(tree)

        self._assert_guard_passed(code, output)

    def test_guard_fails_when_dockerignore_excludes_a_runtime_path(self) -> None:
        # G1: a COPY whose source the build context drops does not ship the path.
        tree = self._tree_copy()
        self._append_dockerignore(tree, "mobile/contracts")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "mobile/contracts")

    def test_guard_follows_readiness_when_a_runtime_contract_moves(self) -> None:
        # G1: the paths come from readiness itself, not from a hard-coded list in the test.
        tree = self._tree_copy()
        relocated_dir = _random_name()
        source = tree / "mobile" / "contracts" / "live_round_event.schema.json"
        relocated = tree / relocated_dir / "live_round_event.schema.json"
        relocated.parent.mkdir(parents=True)
        shutil.copyfile(source, relocated)
        readiness = tree / "server_v2" / "readiness.py"
        text, count = EVENT_CONTRACT_CONSTANT.subn(
            f'LIVE_ROUND_EVENT_CONTRACT = Path("{relocated_dir}/live_round_event.schema.json")',
            readiness.read_text(encoding="utf-8"),
        )
        self.assertEqual(count, 1, "expected one LIVE_ROUND_EVENT_CONTRACT assignment in readiness")
        readiness.write_text(text, encoding="utf-8")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, f"{relocated_dir}/live_round_event.schema.json")

    def test_guard_reports_a_new_runtime_read_outside_the_image(self) -> None:
        # G1: a file a runtime check starts reading (not a path constant) is caught.
        tree = self._tree_copy()
        probe = f"{_random_name()}/extra.json"
        self._write_probe(tree, probe)
        self._inject_read(tree, RUNTIME_READER, probe)

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, probe)

    def test_guard_reports_an_os_path_probe_outside_the_image(self) -> None:
        # G1: an os.path existence probe gates readiness like a read does (the #428 shape).
        tree = self._tree_copy()
        probe = f"{_random_name()}/stat_only.json"
        self._write_probe(tree, probe)
        self._inject(tree, RUNTIME_READER, f'__import__("os").path.isfile({_opaque(probe)})')

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, probe)

    def test_guard_reports_a_directory_listing_outside_the_image(self) -> None:
        # G1: a runtime check that lists a directory depends on that directory being shipped.
        tree = self._tree_copy()
        probe_dir = _random_name()
        self._write_probe(tree, f"{probe_dir}/item.json")
        self._inject(tree, RUNTIME_READER, f"list(Path({_opaque(probe_dir)}).iterdir())")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, probe_dir)

    def test_guard_reports_runtime_read_under_a_directory_packaging_also_uses(self) -> None:
        # G1: scope follows the check label, so ops/ is not exempt when a runtime check reads it.
        tree = self._tree_copy()
        self.assertTrue((tree / "ops" / "start_api.sh").is_file(), "expected ops/start_api.sh")
        self._inject_read(tree, RUNTIME_READER, "ops/start_api.sh")
        dockerfile = tree / "Dockerfile"
        text, count = OPS_COPY.subn("", dockerfile.read_text(encoding="utf-8"))
        self.assertEqual(count, 1, "expected exactly one COPY of ops in Dockerfile")
        dockerfile.write_text(text, encoding="utf-8")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "ops/start_api.sh")

    def test_guard_ignores_uncopied_reads_of_packaging_checks(self) -> None:
        # G1: a file read only by a PACKAGING_LABELS check never fails the guard.
        tree = self._tree_copy()
        probe = f"{_random_name()}/extra.json"
        self._write_probe(tree, probe)
        self._inject_read(tree, PACKAGING_READER, probe)

        code, output = _run_guard(tree)

        self._assert_guard_passed(code, output)

    def test_guard_ignores_private_root_reads(self) -> None:
        # G1: private-root paths (data/ and friends) are not image content.
        tree = self._tree_copy()
        probe = f"data/{_random_name()}.json"
        self._write_probe(tree, probe)
        self._inject_read(tree, RUNTIME_READER, probe)

        code, output = _run_guard(tree)

        self._assert_guard_passed(code, output)

    def test_guard_accepts_a_copy_split_over_continuation_lines(self) -> None:
        # G1: Docker joins `\`-continued lines, so a two-line COPY still ships the directory.
        tree = self._tree_copy()
        self._replace_mobile_contracts_copy(tree, "COPY mobile/contracts/ \\\n    ./mobile/contracts/")

        code, output = _run_guard(tree)

        self._assert_guard_passed(code, output)

    def test_guard_rejects_a_copy_line_swallowed_by_a_run_continuation(self) -> None:
        # G1: after `RUN true \` the next line is an argument of RUN, not a COPY instruction.
        tree = self._tree_copy()
        copy_line = self._mobile_contracts_copy_line(tree)
        self._replace_mobile_contracts_copy(tree, "RUN true \\\n" + copy_line)

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "mobile/contracts")

    def test_guard_rejects_an_absolute_copy_outside_the_runtime_workdir(self) -> None:
        # G1: an absolute destination under a different WORKDIR is not where readiness looks.
        tree = self._tree_copy()
        self._replace_mobile_contracts_copy(
            tree,
            "WORKDIR /srv\nCOPY mobile/contracts/ /srv/mobile/contracts/\nWORKDIR /app",
        )

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "mobile/contracts")

    def test_guard_reports_an_os_access_probe_outside_the_image(self) -> None:
        # G1: os.access gates on a file's presence like a stat does.
        tree = self._tree_copy()
        probe = f"{_random_name()}/access_only.json"
        self._write_probe(tree, probe)
        self._inject(tree, RUNTIME_READER, f'__import__("os").access({_opaque(probe)}, 4)')

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, probe)

    def test_guard_sees_cached_runtime_reads_after_readiness_already_ran(self) -> None:
        # G1: in the full suite readiness has usually run before the guard. A runtime read behind
        # an in-process cache must still be traced (the shape of lru_cache'd contract loaders).
        tree = self._tree_copy()
        probe = f"{_random_name()}/cached.json"
        self._write_probe(tree, probe)
        readiness = tree / "server_v2" / "readiness.py"
        readiness.write_text(
            readiness.read_text(encoding="utf-8").rstrip("\n")
            + "\n\n\n"
            + "@__import__(\"functools\").lru_cache(maxsize=1)\n"
            + "def _card432_cached_probe() -> str:\n"
            + f'    return Path({_opaque(probe)}).read_text(encoding="utf-8")\n',
            encoding="utf-8",
        )
        self._inject(tree, RUNTIME_READER, "_card432_cached_probe()")

        code, output = _run_guard(tree, warm_first=True)

        self._assert_guard_failed(code, output, probe)

    def test_guard_reports_a_read_after_the_final_check(self) -> None:
        # G1: a read made after the last `_check` call, where runtimeStatus is computed, has no
        # later check to be attributed to. It must stay in scope instead of being dropped.
        tree = self._tree_copy()
        probe = f"{_random_name()}/after_final_check.json"
        self._write_probe(tree, probe)
        readiness = tree / "server_v2" / "readiness.py"
        statement = f'    Path({_opaque(probe)}).read_text(encoding="utf-8")\n'
        text, count = RUNTIME_STATUS_STATEMENT.subn(
            lambda m: statement + m.group(0), readiness.read_text(encoding="utf-8"), count=1
        )
        self.assertEqual(count, 1, "expected one `runtime_checks = [` statement in readiness")
        readiness.write_text(text, encoding="utf-8")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, probe)

    def test_guard_normalises_dockerignore_patterns_like_docker(self) -> None:
        # G1: Docker cleans each pattern (`.` elements, repeated and trailing `/`, then one leading
        # `/`), so this line excludes mobile/contracts from the build context.
        tree = self._tree_copy()
        self._append_dockerignore(tree, "/./mobile/./contracts//")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "mobile/contracts")

    def test_guard_matches_double_star_dockerignore_patterns_like_docker(self) -> None:
        # G1: in .dockerignore, `**/` matches zero or more directories, so `mobile/**/contracts`
        # excludes mobile/contracts itself.
        tree = self._tree_copy()
        self._append_dockerignore(tree, "mobile/**/contracts")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "mobile/contracts")

    def test_guard_accepts_a_json_array_copy(self) -> None:
        # G1: the exec (JSON-array) form of COPY ships the same directory as the shell form.
        tree = self._tree_copy()
        self._replace_mobile_contracts_copy(tree, 'COPY ["mobile/contracts/", "./mobile/contracts/"]')

        code, output = _run_guard(tree)

        self._assert_guard_passed(code, output)

    def test_guard_rejects_a_copy_with_a_flag_it_does_not_model(self) -> None:
        # G1: flags such as --exclude or --parents change what a COPY ships or where it lands.
        # The guard only understands --chown, --chmod and --link; any other flag ships nothing.
        tree = self._tree_copy()
        self._replace_mobile_contracts_copy(tree, "COPY --exclude=mobile/contracts . ./")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "mobile/contracts")

    def test_guard_accepts_ownership_mode_and_link_flags(self) -> None:
        # G1: --chown, --chmod and --link do not change which files ship or where they land.
        tree = self._tree_copy()
        self._replace_mobile_contracts_copy(
            tree, "COPY --chown=1000:1000 --chmod=644 --link mobile/contracts/ ./mobile/contracts/"
        )

        code, output = _run_guard(tree)

        self._assert_guard_passed(code, output)


if __name__ == "__main__":
    unittest.main()
