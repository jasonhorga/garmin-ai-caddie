"""Small-layer hermetic guard (interface stub; no guard installed yet)."""
from contextlib import contextmanager
import unittest


class HermeticViolation(AssertionError):
    """A small test touched the real clock, sleep, disk writes or the network."""


@contextmanager
def small_guard():
    yield None


class SmallTestCase(unittest.TestCase):
    @contextmanager
    def assertHermeticViolation(self, kind):
        with self.assertRaises(HermeticViolation) as caught:
            yield caught
        self.assertIn(kind, str(caught.exception))
