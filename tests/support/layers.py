"""Directory test layers: tests/small, tests/medium, tests/large, tests/quarantine.

The host CD command ``python -m tests.check_isolation discover -s tests -t .``
collects small + medium (plus the legacy modules until K13). ``tests/large``
joins only when ``AI_CADDIE_TEST_LAYER=slow``; ``tests/quarantine`` never joins
a discovery run and is executed only by naming its modules.

Both gates are package-level ``load_tests`` hooks. unittest discovery imports a
package's ``__init__`` and, when it defines ``load_tests``, hands the whole
package to that hook and does not recurse itself, so returning the (empty)
standard suite keeps every module of the package unimported.
"""
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
LAYER_ENV = "AI_CADDIE_TEST_LAYER"
SLOW = "slow"


def slow_layer_selected(environ=None):
    return (os.environ if environ is None else environ).get(LAYER_ENV) == SLOW


def discover_package(loader, package_file, pattern):
    """Discover a layer package's modules from inside its ``load_tests`` hook."""
    directory = str(Path(package_file).resolve().parent)
    # Inside an outer discover the loader keeps that run's top-level directory
    # (and its module naming); a bare ``python -m unittest tests.small`` has
    # none, so anchor at the repository like ``-t .``.
    top_level = None if getattr(loader, "_top_level_dir", None) else str(ROOT)
    return loader.discover(directory, pattern=pattern or "test*.py", top_level_dir=top_level)


def iter_tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_tests(item)
        else:
            yield item


def require_test_base(suite, base, layer):
    """Add a failing test naming every test in ``suite`` not derived from ``base``.

    Import failures (unittest.loader's placeholder tests) are left to report
    themselves.
    """
    offenders = sorted(
        test.id() for test in iter_tests(suite)
        if not isinstance(test, base) and type(test).__module__ != "unittest.loader"
    )
    if offenders:
        message = (f"tests/{layer} tests must subclass {base.__module__}.{base.__qualname__}, "
                   f"which installs the {layer}-layer guard: {', '.join(offenders)}")

        def unguarded_tests():
            raise AssertionError(message)

        suite.addTest(unittest.FunctionTestCase(
            unguarded_tests, description=f"tests.{layer} test base class"))
    return suite
