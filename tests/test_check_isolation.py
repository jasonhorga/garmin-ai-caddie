"""The artifact checker reports this run's paths, including rewritten ignored files."""
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests import check_isolation


class CheckIsolationTests(unittest.TestCase):
    def test_failure_lists_only_new_and_changed_paths(self):
        self.check_changes(add_file=True)

    def test_rewriting_existing_ignored_file_also_fails(self):
        self.check_changes(add_file=False)

    def check_changes(self, *, add_file):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("data/\noutput/\n")
            (root / "data").mkdir()
            changed = root / "data/changed.json"
            changed.write_text("before")
            (root / "data/unchanged.json").write_text("untouched fixture")
            original_run = subprocess.run

            def run(command, **kwargs):
                if command[:3] == [sys.executable, "-m", "unittest"]:
                    changed.write_text("changed fixture")
                    if add_file:
                        (root / "data/new.json").write_text("new fixture")
                    return subprocess.CompletedProcess(command, 0)
                return original_run(command, **kwargs)

            output = StringIO()
            with (
                patch.object(check_isolation, "ROOT", root),
                patch.object(sys, "argv", ["check_isolation", "fixture_probe"]),
                patch.object(subprocess, "run", side_effect=run),
                redirect_stderr(output),
            ):
                result = check_isolation.main()
            self.assertEqual(result, 1)
            self.assertIn("New/changed repository artifacts:", output.getvalue())
            self.assertIn("data/changed.json", output.getvalue())
            if add_file:
                self.assertIn("data/new.json", output.getvalue())
            self.assertNotIn("data/unchanged.json", output.getvalue())
