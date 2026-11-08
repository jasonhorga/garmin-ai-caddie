"""Quarantine for unstable tests (test-plan section 5): never in any gate.

Discovery always gets an empty suite here; run a quarantined module by name,
e.g. ``python -m tests.check_isolation tests.quarantine.test_x``.
"""


def load_tests(loader, standard_tests, pattern):
    return standard_tests
