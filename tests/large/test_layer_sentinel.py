"""Sentinel for the slow-layer gate in tests/large/__init__.py."""
import os
import unittest

from tests.support.layers import LAYER_ENV, SLOW


class LargeLayerSentinel(unittest.TestCase):
    def test_large_tests_run_only_when_slow_layer_selected(self):
        """Large tests are collected only when AI_CADDIE_TEST_LAYER=slow selects the slow layer."""
        self.assertEqual(os.environ.get(LAYER_ENV), SLOW)
