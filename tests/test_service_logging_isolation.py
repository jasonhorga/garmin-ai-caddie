"""Classes exercising startup must restore process logging, regardless of run order."""

import io
import logging
import unittest


class ServiceLoggingIsolationTests(unittest.TestCase):
    def assert_module_restores_logging(self, module):
        from server_v2.main import SERVICE_INFO_LOGGERS

        loggers = [logging.getLogger(name) for name in
                   (*SERVICE_INFO_LOGGERS, "uvicorn.access", "uvicorn.error", "", "alembic")]

        def snapshot():
            return {logger.name: (logger.handlers[:], logger.filters[:], logger.level,
                                  logger.propagate, logger.disabled) for logger in loggers}

        # The loader groups a module by class. Run and inspect each class separately:
        # another class's cleanup must not hide the class that leaked logging state.
        for suite in unittest.defaultTestLoader.loadTestsFromName(module):
            before = snapshot()
            output = io.StringIO()
            try:
                result = unittest.TextTestRunner(stream=output).run(suite)
                self.assertTrue(result.wasSuccessful(), output.getvalue())
                after = snapshot()
                changed = {name: (before[name], after[name]) for name in before
                           if before[name] != after[name]}
                self.assertEqual(changed, {}, f"{module} class leaked logging state: {changed}")
            finally:
                # This guard's cleanup is independent of the fixture it checks.
                for logger in loggers:
                    handlers, filters, level, propagate, disabled = before[logger.name]
                    logger.handlers[:] = handlers
                    logger.filters[:] = filters
                    logger.setLevel(level)
                    logger.propagate = propagate
                    logger.disabled = disabled

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
