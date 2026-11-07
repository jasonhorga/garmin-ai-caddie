"""Large layer (test-plan 3.1): collected only when AI_CADDIE_TEST_LAYER=slow.

Without it, discovery (including the host CD command) imports this package but
none of its modules; see tests/support/layers.py.
"""
from tests.support.layers import discover_package, slow_layer_selected


def load_tests(loader, standard_tests, pattern):
    if slow_layer_selected():
        standard_tests.addTests(discover_package(loader, __file__, pattern))
    return standard_tests
