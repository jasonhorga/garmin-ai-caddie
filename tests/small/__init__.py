"""Small layer: pure in-memory tests (test-plan 3.1).

Every test must subclass ``tests.support.hermetic.SmallTestCase``, which denies
the real clock, sleep, disk writes and network connections while the test runs
(by any entry point, including ``python -m unittest tests.small.test_x``). Under
discovery this hook also turns the gate red for a test that skips that base.
"""
from tests.support.hermetic import SmallTestCase
from tests.support.layers import discover_package, require_test_base


def load_tests(loader, standard_tests, pattern):
    standard_tests.addTests(discover_package(loader, __file__, pattern))
    return require_test_base(standard_tests, SmallTestCase, "small")
