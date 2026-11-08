"""META: the traceability allowed-missing list only shrinks (test-plan section 9.2)."""
from pathlib import Path
import subprocess
import unittest

from tests.support import traceability as trace

ROOT = Path(__file__).resolve().parents[2]
LIST = trace.ALLOWED_MISSING_FILE.relative_to(ROOT).as_posix()
# The CD clone pins the main it rebases onto as refs/cd/base; a work clone has origin/main.
BASE_REFS = ("refs/cd/base", "origin/main")


def git(*args):
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=20)
    return result.stdout if result.returncode == 0 else None


class AllowedMissingRatchetTests(unittest.TestCase):
    """META: the allowed-missing list never gains a goal."""

    def test_no_goal_was_added_since_the_base_revision(self):
        """Every entry of the allowed-missing list was already listed at the merge base with main."""
        base = next((found.strip() for ref in BASE_REFS
                     if (found := git("merge-base", "HEAD", ref))), None)
        if base is None:
            self.skipTest("no main revision to compare against")
        base_text = git("show", f"{base}:{LIST}")
        if base_text is None:
            self.skipTest(f"{LIST} does not exist at {base[:12]}; this change introduces it")
        added = trace.added_allowances(base_text, trace.ALLOWED_MISSING_FILE.read_text(encoding="utf-8"))
        self.assertEqual(added, [], f"{LIST} only shrinks; added since {base[:12]}: {', '.join(added)}")
