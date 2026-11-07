"""Sentinel for the quarantine gate in tests/quarantine/__init__.py."""
import unittest


class QuarantineSentinel(unittest.TestCase):
    def test_quarantine_runs_only_when_named(self):
        """Quarantined tests never join a discovery gate; they run only when named explicitly."""
