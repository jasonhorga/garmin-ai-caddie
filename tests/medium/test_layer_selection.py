"""Default discovery runs small + medium; large waits for the slow layer; quarantine never runs."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from tests.support.layers import LAYER_ENV

ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "test_layer_sentinel.py"
LARGE_SENTINEL = "tests.large.test_layer_sentinel"
QUARANTINE_SENTINEL = "tests.quarantine.test_layer_sentinel"


class RecordingLoader(unittest.TestLoader):
    """Real unittest discovery that also records every module it imports."""

    def __init__(self):
        super().__init__()
        self.imported = []

    def _get_module_from_name(self, name):
        self.imported.append(name)
        return super()._get_module_from_name(name)


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


class LayerSelectionTests(unittest.TestCase):
    def discover(self, start, layer=None):
        """Run the host CD discovery shape (-s <start> -t .), restricted to the sentinels.

        Packages are visited regardless of the file pattern, so the restriction
        exercises the same package gates as the full command.
        """
        env = {key: value for key, value in os.environ.items() if key != LAYER_ENV}
        if layer is not None:
            env[LAYER_ENV] = layer
        loader = RecordingLoader()
        with patch.dict(os.environ, env, clear=True), patch.object(sys, "path", list(sys.path)):
            suite = loader.discover(str(ROOT / start), pattern=SENTINEL, top_level_dir=str(ROOT))
        self.assertEqual(loader.errors, [])
        return loader.imported, [test.id() for test in flatten(suite)]

    def test_host_command_skips_large_and_quarantine(self):
        """The unchanged host CD command visits tests/large and tests/quarantine but collects nothing there."""
        imported, ids = self.discover("tests")
        self.assertIn("tests.large", imported)
        self.assertIn("tests.quarantine", imported)
        self.assertNotIn(LARGE_SENTINEL, imported)
        self.assertNotIn(QUARANTINE_SENTINEL, imported)
        self.assertEqual([test for test in ids if test.startswith(("tests.large.", "tests.quarantine."))], [])

    def test_slow_layer_adds_large_but_never_quarantine(self):
        """AI_CADDIE_TEST_LAYER=slow adds tests/large; quarantine stays out of every gate."""
        imported, ids = self.discover("tests", layer="slow")
        self.assertIn(f"{LARGE_SENTINEL}.LargeLayerSentinel."
                      "test_large_tests_run_only_when_slow_layer_selected", ids)
        self.assertNotIn(QUARANTINE_SENTINEL, imported)
        self.assertEqual([test for test in ids if test.startswith("tests.quarantine.")], [])

    def test_targeting_large_directly_still_needs_the_slow_layer(self):
        """`discover -s tests/large -t .` is empty unless the slow layer is selected."""
        _imported, ids = self.discover("tests/large")
        self.assertEqual(ids, [])
        _imported, ids = self.discover("tests/quarantine", layer="slow")
        self.assertEqual(ids, [])

    def test_quarantined_module_still_runs_when_named(self):
        """A quarantined test can still be run on purpose by naming its module."""
        suite = unittest.TestLoader().loadTestsFromName(QUARANTINE_SENTINEL)
        self.assertEqual(suite.countTestCases(), 1)
