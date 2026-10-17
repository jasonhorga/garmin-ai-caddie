"""Card #432: every repository path readiness reads for runtimeStatus ships in the API image.

The guard under test is the repository test named by GUARD_TEST. Each case runs it in a
subprocess, either on the checkout itself or on a temporary copy with one deliberate change,
and checks that it passes on the real tree, fails (naming the path) on each defect, and stays
green for reads that belong to packaging/evidence checks or to the private runtime root.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_TEST = (
    "tests.test_deployment_manifests.DeploymentManifestTests."
    "test_readiness_runtime_paths_are_copied_into_image"
)
MOBILE_CONTRACTS_COPY = re.compile(r"^COPY\s+mobile/contracts/?\s+\S+\s*$", re.MULTILINE)
OPS_COPY = re.compile(r"^COPY\s+ops/?\s+\S+\s*$", re.MULTILINE)
EVENT_CONTRACT_CONSTANT = re.compile(r"^LIVE_ROUND_EVENT_CONTRACT\s*=.*$", re.MULTILINE)
# Runtime check (label mobile_events) and packaging check (label external_release).
RUNTIME_READER = "_contract_event_kinds"
PACKAGING_READER = "_external_release_evidence"
SKIP_EVERYWHERE = {
    ".git", ".venv", "node_modules", "__pycache__", ".agenthub-home",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
# Private runtime root links (ops/start_api.sh); never copied out of the checkout.
SKIP_AT_ROOT = {"data", ".garmin_tokens", "output", "logs", "backups", "clubs.json"}


def _copy_ignore(directory: str, names: list[str]) -> set[str]:
    # G1 G2: copy helper; drops caches, private-root links and special files.
    skipped: set[str] = set()
    at_root = Path(directory).resolve() == REPO_ROOT
    for name in names:
        path = os.path.join(directory, name)
        if name in SKIP_EVERYWHERE or name.endswith(".pyc") or (at_root and name in SKIP_AT_ROOT):
            skipped.add(name)
        elif not (os.path.islink(path) or os.path.isdir(path) or os.path.isfile(path)):
            skipped.add(name)
    return skipped


def _run_guard(root: Path) -> tuple[int, str]:
    # G1 G2: runs the repository guard test as a real unittest subprocess.
    env = dict(os.environ)
    env["AI_CADDIE_DATA_MODE"] = "fixture"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("AI_CADDIE_PRIVATE_ROOT", None)
    env["PYTHONPATH"] = os.pathsep.join(part for part in (str(root), env.get("PYTHONPATH", "")) if part)
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", GUARD_TEST],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return proc.returncode, proc.stdout + proc.stderr


class ReadinessImagePathGuardTests(unittest.TestCase):
    def _tree_copy(self) -> Path:
        # G1: temporary full copy of the checkout for one mutation.
        holder = tempfile.TemporaryDirectory(prefix="card432-")
        self.addCleanup(holder.cleanup)
        tree = Path(holder.name) / "checkout"
        shutil.copytree(REPO_ROOT, tree, ignore=_copy_ignore, symlinks=True)
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

    def _inject_read(self, tree: Path, function: str, relative: str) -> None:
        # G1: makes one readiness helper read `relative` as its first statement.
        readiness = tree / "server_v2" / "readiness.py"
        pattern = re.compile(rf"^def {re.escape(function)}\(\)[^\n]*:\n", re.MULTILINE)
        statement = f'    Path("{relative}").read_text(encoding="utf-8")\n'
        text, count = pattern.subn(lambda m: m.group(0) + statement, readiness.read_text(encoding="utf-8"), count=1)
        self.assertEqual(count, 1, f"expected one `def {function}()` in readiness")
        readiness.write_text(text, encoding="utf-8")

    def _inject_statement(self, tree: Path, function: str, statement: str) -> None:
        # G1: inserts a deliberately chosen filesystem probe into a readiness helper.
        readiness = tree / "server_v2" / "readiness.py"
        pattern = re.compile(rf"^def {re.escape(function)}\(\)[^\n]*:\n", re.MULTILINE)
        text, count = pattern.subn(
            lambda m: m.group(0) + f"    {statement}\n",
            readiness.read_text(encoding="utf-8"),
            count=1,
        )
        self.assertEqual(count, 1, f"expected one `def {function}()` in readiness")
        readiness.write_text(text, encoding="utf-8")

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

    def test_guard_passes_on_the_checkout(self) -> None:
        # G1 G2: the guard exists, really runs, and the shipped Dockerfile satisfies it.
        code, output = _run_guard(REPO_ROOT)
        self._assert_guard_passed(code, output)

    def test_guard_fails_when_mobile_contracts_copy_is_removed(self) -> None:
        # G1: the #428 failure mode is caught again.
        tree = self._tree_copy()
        dockerfile = tree / "Dockerfile"
        text, count = MOBILE_CONTRACTS_COPY.subn("", dockerfile.read_text(encoding="utf-8"))
        self.assertEqual(count, 1, "expected exactly one COPY of mobile/contracts in Dockerfile")
        dockerfile.write_text(text, encoding="utf-8")

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

    def test_guard_fails_when_dockerignore_excludes_a_runtime_path(self) -> None:
        # G1: a COPY whose source the build context drops does not ship the path.
        tree = self._tree_copy()
        dockerignore = tree / ".dockerignore"
        text = dockerignore.read_text(encoding="utf-8") if dockerignore.exists() else ""
        dockerignore.write_text(text.rstrip("\n") + "\nmobile/contracts\n", encoding="utf-8")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "mobile/contracts")

    def test_guard_follows_readiness_when_a_runtime_contract_moves(self) -> None:
        # G1: the paths come from readiness itself, not from a hard-coded list in the test.
        tree = self._tree_copy()
        source = tree / "mobile" / "contracts" / "live_round_event.schema.json"
        relocated = tree / "relocated_contracts" / "live_round_event.schema.json"
        relocated.parent.mkdir(parents=True)
        shutil.copyfile(source, relocated)
        readiness = tree / "server_v2" / "readiness.py"
        text, count = EVENT_CONTRACT_CONSTANT.subn(
            'LIVE_ROUND_EVENT_CONTRACT = Path("relocated_contracts/live_round_event.schema.json")',
            readiness.read_text(encoding="utf-8"),
        )
        self.assertEqual(count, 1, "expected one LIVE_ROUND_EVENT_CONTRACT assignment in readiness")
        readiness.write_text(text, encoding="utf-8")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "relocated_contracts")

    def test_guard_reports_a_new_runtime_read_outside_the_image(self) -> None:
        # G1: a file a runtime check starts reading (not a path constant) is caught.
        tree = self._tree_copy()
        self._write_probe(tree, "runtime_probe/extra.json")
        self._inject_read(tree, RUNTIME_READER, "runtime_probe/extra.json")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "runtime_probe/extra.json")

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
        self._write_probe(tree, "packaging_probe/extra.json")
        self._inject_read(tree, PACKAGING_READER, "packaging_probe/extra.json")

        code, output = _run_guard(tree)

        self._assert_guard_passed(code, output)

    def test_guard_ignores_private_root_reads(self) -> None:
        # G1: private-root paths (data/ and friends) are not image content.
        tree = self._tree_copy()
        self._write_probe(tree, "data/card432_probe.json")
        self._inject_read(tree, RUNTIME_READER, "data/card432_probe.json")

        code, output = _run_guard(tree)

        self._assert_guard_passed(code, output)

    def test_guard_reports_bytes_path_runtime_read(self) -> None:
        # G1: audit-hook open events may expose bytes paths and must remain attributable.
        tree = self._tree_copy()
        self._write_probe(tree, "bytes_probe/extra.json")
        self._inject_statement(
            tree,
            RUNTIME_READER,
            'open(b"bytes_probe/extra.json", "rb").read()',
        )

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "bytes_probe/extra.json")

    def test_guard_reports_os_path_isfile_runtime_probe(self) -> None:
        # G1: os.path.isfile delegates to os.stat, which must be traced as a runtime dependency.
        tree = self._tree_copy()
        self._write_probe(tree, "stat_probe/extra.json")
        self._inject_statement(tree, RUNTIME_READER, 'import os; os.path.isfile("stat_probe/extra.json")')

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "stat_probe/extra.json")

    def test_guard_reports_pyo_runtime_file(self) -> None:
        # G1: a runtime .pyo file is not an image-generated cache and must be covered.
        tree = self._tree_copy()
        self._write_probe(tree, "pyo_probe/extra.pyo")
        self._inject_read(tree, RUNTIME_READER, "pyo_probe/extra.pyo")

        code, output = _run_guard(tree)

        self._assert_guard_failed(code, output, "pyo_probe/extra.pyo")


if __name__ == "__main__":
    unittest.main()
