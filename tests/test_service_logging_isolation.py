"""Classes exercising startup must restore process logging, regardless of run order."""

import io
import logging
import unittest


LOGGING_MUTATING_MODULES = (
    "tests.product.test_c154b",
    "tests.product.test_c33_start_fast",
    "tests.product.test_c36_cold_release_start",
    "tests.test_app_boots_with_db",
    "tests.test_course_tees",
    "tests.test_release_hardening",
    "tests.test_server_v2_cache_warmup",
    "tests.test_server_v2_mobile",
)

# c154b contains a large HTTP/DB suite.  Its logging-mutating class is the
# admission class; keeping the guard scoped to that class makes this check
# cheap enough for every backend test run while still catching the SM5 leak.
LOGGING_GUARD_TARGETS = {
    "tests.product.test_c154b": ("ForegroundAdmissionTests",),
}


class ServiceLoggingIsolationTests(unittest.TestCase):
    def test_J73_pipeline_then_course_prep_preserves_diagnostics(self):
        """J7.3: cron privacy setup must not change a later library log capture.

        Run both modules in one interpreter, in the order that exposed the CI
        regression. Course-prep's hand-written exception diagnostics must survive.
        """
        from tests.service_logging import preserve_service_logging

        output = io.StringIO()
        suite = unittest.defaultTestLoader.loadTestsFromNames(
            ["tests.test_pipeline", "tests.test_course_prep"]
        )
        with preserve_service_logging():
            result = unittest.TextTestRunner(stream=output).run(suite)
        self.assertTrue(result.wasSuccessful(), output.getvalue())

    def test_J42_logging_mutating_module_registry_is_explicit(self):
        """J4.2: a newly logging-mutating module must be added to this guard registry."""
        self.assertIn("tests.product.test_c154b", LOGGING_MUTATING_MODULES)

    def test_J42_background_slot_logging_suite_is_discoverable(self):
        """J4.2: the logging isolation regression suite is visible to unittest discover."""
        discovered = unittest.defaultTestLoader.discover(
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
        for suite in unittest.defaultTestLoader.loadTestsFromName(module):
            if isinstance(suite, unittest.TestCase):
                suite = unittest.TestSuite([suite])
            class_name = type(next(iter(suite))).__name__
            if only_class is not None and class_name != only_class:
                continue
            before = snapshot()
            output = io.StringIO()
            try:
                result = unittest.TextTestRunner(stream=output).run(suite)
                self.assertTrue(result.wasSuccessful(), output.getvalue())
                after = snapshot()
                changed = {name: (before[name], after[name]) for name in before
                           if before[name] != after[name]}
                self.assertEqual(changed, {}, f"{module}.{class_name} leaked logging state: {changed}")
            finally:
                # This guard's cleanup is independent of the fixture it checks.
                for logger in loggers:
                    handlers, filters, level, propagate, disabled = before[logger.name]
                    logger.handlers[:] = handlers
                    logger.filters[:] = filters
                    logger.setLevel(level)
                    logger.propagate = propagate
                    logger.disabled = disabled

    def test_logging_mutating_modules_restore_logging(self):
        for module in LOGGING_MUTATING_MODULES:
            with self.subTest(module=module):
                targets = LOGGING_GUARD_TARGETS.get(module)
                if targets is None:
                    self.assert_module_restores_logging(module)
                else:
                    for target in targets:
                        self.assert_module_restores_logging(module, only_class=target)

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
