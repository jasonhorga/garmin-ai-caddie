"""Classes exercising startup must restore process logging, regardless of run order."""

import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import logging
import unittest
from unittest.mock import patch


class ServiceLoggingIsolationTests(unittest.TestCase):
    def test_J73_unregistered_module_leaks_are_rejected_at_module_boundary(self):
        """J7.3: CI's base runner catches any module, after module cleanups."""
        for method in ("addHandler", "callHandlers"):
            for restore in (False, True):
                with self.subTest(method=method, restore=restore), tempfile.TemporaryDirectory() as tmp:
                    module = Path(tmp) / "logging_boundary_probe.py"
                    module.write_text(
                        "import logging, unittest\n"
                        f"original = logging.Logger.{method}\n"
                        "class Probe(unittest.TestCase):\n"
                        "    def test_leak(self):\n"
                        f"        logging.Logger.{method} = lambda *args: None\n"
                        + (f"def tearDownModule():\n    logging.Logger.{method} = original\n"
                           if restore else "")
                    )
                    following = Path(tmp) / "logging_boundary_observer.py"
                    following.write_text(
                        "import logging, unittest\n"
                        f"original = logging.Logger.{method}\n"
                        "class Observer(unittest.TestCase):\n"
                        "    def test_restored(self):\n"
                        f"        self.assertIs(logging.Logger.{method}, original)\n"
                    )
                    for modules in (("logging_boundary_probe", "logging_boundary_observer"),
                                    ("logging_boundary_observer", "logging_boundary_probe")):
                        result = subprocess.run(
                            [sys.executable, "-m", "tests.check_isolation", *modules],
                            env={**os.environ, "PYTHONPATH": os.pathsep.join(
                                [tmp, str(Path(__file__).resolve().parents[1])])},
                            capture_output=True, text=True, timeout=120)
                        output = result.stdout + result.stderr
                        if restore:
                            self.assertEqual(result.returncode, 0, output)
                        else:
                            self.assertNotEqual(result.returncode, 0, output)
                            self.assertIn(f"logging_boundary_probe leaked Logger.{method}", output)
                            self.assertNotIn("FAIL: test_restored", output)

    def test_J73_isolation_guard_rejects_leaked_logger_methods(self):
        """J7.3: detect process hooks even if handlers and levels were restored."""
        for method in ("addHandler", "callHandlers"):
            with self.subTest(method=method):
                class LeakingTest(unittest.TestCase):
                    def runTest(self):
                        setattr(logging.Logger, method, lambda *args: None)

                suite = unittest.TestSuite([LeakingTest()])
                with patch.object(unittest.TestLoader, "loadTestsFromName",
                                  return_value=[suite]):
                    with self.assertRaisesRegex(AssertionError, f"leaked Logger.{method}"):
                        self.assert_module_restores_logging("logging_leak_probe")

    def test_J73_isolation_guard_rejects_logger_state_leaks_and_restores_them(self):
        """J7.3: module boundaries cover root and named logger state."""
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "logging_state_probe.py"
            module.write_text(
                "import logging, unittest\n"
                "target = None\n"
                "class Probe(unittest.TestCase):\n"
                "    def test_leak(self):\n"
                "        root = logging.getLogger()\n"
                "        root.setLevel(logging.DEBUG)\n"
                "        root.filters[:] = [logging.Filter('leaked')]\n"
                "        global target\n"
                "        target = logging.getLogger('logging_state_probe.named')\n"
                "        target.handlers[:] = [logging.StreamHandler()]\n"
                "        target.setLevel(logging.ERROR)\n"
                "        target.propagate = False\n"
            )
            observer = Path(tmp) / "logging_state_observer.py"
            observer.write_text(
                "import logging, unittest, logging_state_probe\n"
                "class Observer(unittest.TestCase):\n"
                "    def test_restored(self):\n"
                "        root = logging.getLogger()\n"
                "        self.assertEqual(root.level, logging.WARNING)\n"
                "        self.assertEqual(root.filters, [])\n"
                "        target = logging.getLogger('logging_state_probe.named')\n"
                "        self.assertIs(target, logging_state_probe.target)\n"
                "        self.assertEqual(target.handlers, [])\n"
                "        self.assertEqual(target.level, logging.NOTSET)\n"
                "        self.assertTrue(target.propagate)\n"
            )
            result = subprocess.run(
                [sys.executable, "-m", "tests.check_isolation",
                 "logging_state_probe", "logging_state_observer"],
                env={**os.environ, "PYTHONPATH": os.pathsep.join(
                    [tmp, str(Path(__file__).resolve().parents[1])])},
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn("logging_state_probe leaked logger state", output)
            self.assertIn("root", output)
            self.assertIn("logging_state_probe.named", output)
            self.assertNotIn("logging_state_observer leaked", output)
            self.assertNotIn("FAIL: test_restored", output)

    def test_J73_isolation_guard_detects_in_place_handler_mutation(self):
        """Handler level/filter changes must not disappear from a shallow snapshot."""
        from tests.check_isolation import LoggingIsolationSuite

        root = logging.getLogger()
        original = (root.handlers[:], root.filters[:], root.level,
                    root.propagate, root.disabled)
        handler = logging.StreamHandler(io.StringIO())
        root.handlers[:] = [handler]
        try:
            before = LoggingIsolationSuite._snapshot_logging()
            handler.setLevel(logging.ERROR)
            handler.addFilter(logging.Filter("mutated"))
            after = LoggingIsolationSuite._snapshot_logging()
            self.assertIn("root", LoggingIsolationSuite._logging_changes(before, after))
            LoggingIsolationSuite._restore_logging(before)
            self.assertEqual(handler.level, logging.NOTSET)
            self.assertEqual(handler.filters, [])
        finally:
            root.handlers[:] = original[0]
            root.filters[:] = original[1]
            root.setLevel(original[2])
            root.propagate = original[3]
            root.disabled = original[4]

    def test_J73_setUpModule_logger_leak_is_reported_before_final_status(self):
        """A module fixture cannot hide a logging leak in the next baseline."""
        with tempfile.TemporaryDirectory() as tmp:
            leaking = Path(tmp) / "logging_setup_probe.py"
            leaking.write_text(
                "import logging, unittest\n"
                "def setUpModule():\n"
                "    logging.getLogger().setLevel(logging.DEBUG)\n"
                "class Probe(unittest.TestCase):\n"
                "    def test_setup_leak(self):\n"
                "        pass\n"
            )
            observer = Path(tmp) / "logging_setup_observer.py"
            observer.write_text(
                "import logging, unittest\n"
                "class Observer(unittest.TestCase):\n"
                "    def test_restored(self):\n"
                "        self.assertEqual(logging.getLogger().level, logging.WARNING)\n"
            )
            result = subprocess.run(
                [sys.executable, "-m", "tests.check_isolation",
                 "logging_setup_probe", "logging_setup_observer"],
                env={**os.environ, "PYTHONPATH": os.pathsep.join(
                    [tmp, str(Path(__file__).resolve().parents[1])])},
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn("logging_setup_probe leaked logger state: root", output)
            self.assertNotIn("logging_setup_observer leaked", output)
            self.assertIn("FAILED", output)
            self.assertNotIn("\nOK\n", output)
            self.assertLess(output.index("logging_setup_probe leaked logger state"),
                            output.rindex("FAILED"))

    def test_J73_external_logger_does_not_hide_root_handler_leak(self):
        """Migration logger churn may not excuse a real root handler mutation."""
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "logging_external_probe.py"
            module.write_text(
                "import logging, unittest\n"
                "class Probe(unittest.TestCase):\n"
                "    def test_leak(self):\n"
                "        logging.getLogger('alembic.runtime').setLevel(logging.INFO)\n"
                f"        logging.getLogger().handlers.append(logging.FileHandler({str(Path(tmp) / 'isolation.tmp')!r}))\n"
            )
            result = subprocess.run(
                [sys.executable, "-m", "tests.check_isolation", "logging_external_probe"],
                env={**os.environ, "PYTHONPATH": os.pathsep.join(
                    [tmp, str(Path(__file__).resolve().parents[1])])},
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn("logging_external_probe leaked logger state: root", output)

    def test_J73_external_logger_whitelist_requires_component_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "logging_prefix_probe.py"
            module.write_text(
                "import logging, unittest\n"
                "class Probe(unittest.TestCase):\n"
                "    def test_prefix_is_not_external(self):\n"
                "        logging.getLogger('sqlalchemy_custom').setLevel(logging.INFO)\n"
            )
            result = subprocess.run(
                [sys.executable, "-m", "tests.check_isolation", "logging_prefix_probe"],
                env={**os.environ, "PYTHONPATH": os.pathsep.join(
                    [tmp, str(Path(__file__).resolve().parents[1])])},
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn("logging_prefix_probe leaked logger state: sqlalchemy_custom", output)

    def test_J73_import_time_leak_names_the_importing_module(self):
        """J7.3: discover reports the module that leaked while being imported."""
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "logging_import_probe.py"
            module.write_text(
                "import logging\n"
                "logging.getLogger('logging_import_probe.named').setLevel(logging.ERROR)\n"
                "import unittest\n"
                "class Probe(unittest.TestCase):\n"
                "    def test_imported(self):\n"
                "        pass\n"
            )
            result = subprocess.run(
                [sys.executable, "-m", "tests.check_isolation", "logging_import_probe"],
                env={**os.environ, "PYTHONPATH": os.pathsep.join(
                    [tmp, str(Path(__file__).resolve().parents[1])])},
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn("logging_import_probe leaked logger state at import", output)
            self.assertNotIn("tests.check_isolation leaked", output)

    def test_J73_import_time_leak_names_second_module_after_clean_module(self):
        """J7.3: an import leak is attributed to the later module in a run."""
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "logging_clean_probe.py"
            clean.write_text(
                "import unittest\n"
                "class Probe(unittest.TestCase):\n"
                "    def test_clean(self):\n"
                "        pass\n"
            )
            leaking = Path(tmp) / "logging_import_probe.py"
            leaking.write_text(
                "import logging\n"
                "logging.getLogger('logging_import_probe.named').setLevel(logging.ERROR)\n"
                "import unittest\n"
                "class Probe(unittest.TestCase):\n"
                "    def test_imported(self):\n"
                "        pass\n"
            )
            result = subprocess.run(
                [sys.executable, "-m", "tests.check_isolation",
                 "logging_clean_probe", "logging_import_probe"],
                env={**os.environ, "PYTHONPATH": os.pathsep.join(
                    [tmp, str(Path(__file__).resolve().parents[1])])},
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn("logging_import_probe leaked logger state at import", output)
            self.assertNotIn("logging_clean_probe leaked", output)

    def test_J73_pipeline_then_course_prep_preserves_diagnostics(self):
        """J7.3: cron privacy setup must not change a later library log capture.

        Run both modules in one interpreter, in the order that exposed the CI
        regression. Course-prep's hand-written exception diagnostics must survive.
        """
        from tests.service_logging import preserve_service_logging

        output = io.StringIO()
        suite = unittest.TestLoader().loadTestsFromNames(
            ["tests.test_pipeline", "tests.test_course_prep"]
        )
        with preserve_service_logging():
            result = unittest.TextTestRunner(stream=output).run(suite)
        self.assertTrue(result.wasSuccessful(), output.getvalue())

    def test_J42_background_slot_logging_suite_is_discoverable(self):
        """J4.2: the logging isolation regression suite is visible to unittest discover."""
        discovered = unittest.TestLoader().discover(
            "tests/product", pattern="test_c154b.py", top_level_dir="."
        )

        def test_ids(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from test_ids(test)
                else:
                    yield test.id()

        self.assertIn(
            "tests.product.test_c154b.BackgroundSlotLoggingIsolationTests.test_J42_background_slot_logging_isolation_suite",
            set(test_ids(discovered)),
        )

    def test_c154b_restores_logging(self):
        from server_v2.main import SERVICE_INFO_LOGGERS
        from tests.service_logging import preserve_service_logging

        with preserve_service_logging():
            for name in SERVICE_INFO_LOGGERS:
                logging.getLogger(name).handlers[:] = [logging.StreamHandler(io.StringIO())]
            self.assert_module_restores_logging(
                "tests.product.test_c154b", only_class="ForegroundAdmissionTests"
            )

    def test_c154b_background_slot_capture_is_isolated(self):
        from tests.product.test_c154b import background_slot_logging_isolation_suite
        from server_v2.main import SERVICE_INFO_LOGGERS
        from tests.service_logging import preserve_service_logging

        with preserve_service_logging():
            # Model an already-running service: configure must replace inherited
            # service handlers before the suite captures the slot log.
            for name in SERVICE_INFO_LOGGERS:
                logging.getLogger(name).handlers[:] = [logging.StreamHandler(io.StringIO())]
            result = unittest.TestResult()
            background_slot_logging_isolation_suite().run(result)
        self.assertTrue(result.wasSuccessful(), result)

    def assert_module_restores_logging(self, module, only_class=None):
        from server_v2.main import SERVICE_INFO_LOGGERS

        loggers = [logging.getLogger(name) for name in
                   (*SERVICE_INFO_LOGGERS, "uvicorn.access", "uvicorn.error", "", "alembic")]

        def snapshot():
            return {logger.name: (logger.handlers[:], logger.filters[:], logger.level,
                                  logger.propagate, logger.disabled) for logger in loggers}

        # The loader groups a module by class. Run and inspect each class separately:
        # another class's cleanup must not hide the class that leaked logging state.
        # Use a fresh loader so CLI -k filters cannot empty these nested checks.
        for suite in unittest.TestLoader().loadTestsFromName(module):
            if isinstance(suite, unittest.TestCase):
                suite = unittest.TestSuite([suite])
            class_name = type(next(iter(suite))).__name__
            if only_class is not None and class_name != only_class:
                continue
            before = snapshot()
            before_methods = (logging.Logger.addHandler, logging.Logger.callHandlers)
            output = io.StringIO()
            try:
                result = unittest.TextTestRunner(stream=output).run(suite)
                self.assertTrue(result.wasSuccessful(), output.getvalue())
                after = snapshot()
                changed = {name: (before[name], after[name]) for name in before
                           if before[name] != after[name]}
                self.assertEqual(changed, {}, f"{module}.{class_name} leaked logging state: {changed}")
                self.assertIs(logging.Logger.addHandler, before_methods[0],
                              f"{module}.{class_name} leaked Logger.addHandler")
                self.assertIs(logging.Logger.callHandlers, before_methods[1],
                              f"{module}.{class_name} leaked Logger.callHandlers")
            finally:
                # This guard's cleanup is independent of the fixture it checks.
                logging.Logger.addHandler, logging.Logger.callHandlers = before_methods
                for logger in loggers:
                    handlers, filters, level, propagate, disabled = before[logger.name]
                    logger.handlers[:] = handlers
                    logger.filters[:] = filters
                    logger.setLevel(level)
                    logger.propagate = propagate
                    logger.disabled = disabled

    # Keep the individual C226 targets stable for the existing fault fragment.
    def test_course_tees_restores_logging(self):
        self.assert_module_restores_logging("tests.test_course_tees")

    def test_app_boots_with_db_restores_logging(self):
        self.assert_module_restores_logging("tests.test_app_boots_with_db")

    def test_release_hardening_restores_logging(self):
        self.assert_module_restores_logging("tests.test_release_hardening")

    def test_cache_warmup_restores_logging(self):
        self.assert_module_restores_logging("tests.test_server_v2_cache_warmup")

    def test_mobile_restores_logging(self):
        self.assert_module_restores_logging("tests.test_server_v2_mobile")

    def test_start_fast_restores_logging(self):
        self.assert_module_restores_logging("tests.product.test_c33_start_fast")

    def test_cold_release_start_restores_logging(self):
        self.assert_module_restores_logging("tests.product.test_c36_cold_release_start")
