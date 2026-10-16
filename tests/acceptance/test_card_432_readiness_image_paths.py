"""Card #432: every repository path readiness reads for runtimeStatus ships in the API image.

The guard under test is the repository test named by GUARD_TEST. Each case runs it in a
subprocess, either on the checkout itself or on a temporary copy with one deliberate defect,
and checks that it passes on the real tree and fails (naming the path) on each defect.
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
EVENT_CONTRACT_CONSTANT = re.compile(r"^LIVE_ROUND_EVENT_CONTRACT\s*=.*$", re.MULTILINE)
COPY_IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "node_modules", "__pycache__", "*.pyc", ".agenthub-home", ".pytest_cache"
)


def _run_guard(root: Path) -> tuple[int, str]:
    env = dict(os.environ)
    env["AI_CADDIE_DATA_MODE"] = "fixture"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("AI_CADDIE_PRIVATE_ROOT", None)
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
        holder = tempfile.TemporaryDirectory(prefix="card432-")
        self.addCleanup(holder.cleanup)
        tree = Path(holder.name) / "checkout"
        shutil.copytree(REPO_ROOT, tree, ignore=COPY_IGNORE, symlinks=True)
        return tree

    def _assert_guard_failed(self, code: int, output: str, needle: str) -> None:
        self.assertNotEqual(code, 0, output)
        self.assertIn("Ran 1 test", output)
        self.assertIn("FAILED (failures=1)", output)
        self.assertIn(needle, output)

    def test_guard_passes_on_the_checkout(self) -> None:
        # G1 G2: the guard exists, really runs, and the shipped Dockerfile satisfies it.
        code, output = _run_guard(REPO_ROOT)
        self.assertEqual(code, 0, output)
        self.assertIn("Ran 1 test", output)
        self.assertNotIn("skipped", output)

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


if __name__ == "__main__":
    unittest.main()
