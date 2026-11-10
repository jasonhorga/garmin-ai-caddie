"""Which test processes import the backend and where they cache bytecode."""
from tests import startup
from tests.support.hermetic import SmallTestCase


class IsolationParentTests(SmallTestCase):
    """META: only the outer isolation runner skips the backend import."""

    def test_the_outer_isolation_runner_is_recognised(self):
        """The host's full-suite and probe command lines start a parent that imports no backend."""
        for argv in (
            ["python", "-m", "tests.check_isolation", "discover", "-s", "tests", "-t", "."],
            ["python", "-X", "importtime", "-m", "tests.check_isolation", "probe_module"],
            ["python", "-m", "tests.check_isolation"],
        ):
            with self.subTest(argv=argv):
                self.assertTrue(startup.isolation_parent(argv))

    def test_every_process_that_runs_tests_still_imports_the_backend(self):
        """The isolation child, unittest, tests.run and in-process imports keep the offline guard."""
        for argv in (
            ["python", "-m", "tests.check_isolation", "--logging-child", "discover"],
            ["python", "-m", "unittest", "tests.test_offline_discovery"],
            ["python", "-m", "tests.run", "--layer", "small"],
            ["python", "-c", "import tests"],
            ["python", "script.py", "-m", "tests.check_isolation"],
        ):
            with self.subTest(argv=argv):
                self.assertFalse(startup.isolation_parent(argv))


class BytecodePrefixTests(SmallTestCase):
    """META: a read-only checkout caches bytecode once under TMPDIR."""

    def test_a_writable_checkout_keeps_its_own_pycache(self):
        """Developers' and CI checkouts keep writing __pycache__ next to the source."""
        self.assertIsNone(startup.bytecode_prefix("/repo", lambda path: True, "/tmp/job"))

    def test_a_read_only_checkout_caches_under_the_temporary_root(self):
        """The CD sandbox checkout is read-only, so bytecode goes to one directory under TMPDIR."""
        seen = []
        prefix = startup.bytecode_prefix("/repo", lambda path: seen.append(path) or False, "/tmp/job")
        self.assertEqual(prefix, "/tmp/job/caddie-pycache")
        self.assertEqual(seen, ["/repo"])
