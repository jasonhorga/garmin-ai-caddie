"""Run unittest arguments and reject new/changed data or output git status.

CI/local usage: python -m tests.check_isolation tests.test_offline_followups
Full CI usage: python -m tests.check_isolation discover -s tests -t . -v
"""
import logging
import builtins
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def repository_artifacts():
    """Include ignored files, which normal git status would hide."""
    return subprocess.check_output(
        ["git", "status", "--porcelain", "--ignored", "--untracked-files=all",
         "--", "data/", "output/"], cwd=ROOT, text=True,
    )


def artifact_files():
    """Catch rewritten ignored files even when their git status stays '!!'."""
    files = {}
    for directory in (ROOT / "data", ROOT / "output"):
        for path in directory.rglob("*"):
            if path.is_file() or path.is_symlink():
                stat = path.lstat()
                files[path.relative_to(ROOT).as_posix()] = (stat.st_size, stat.st_mtime_ns, stat.st_mode)
    return files


class LoggingIsolationSuite(unittest.TestSuite):
    """Check each module after tearDownModule and unittest module cleanups.

    The child runner captures pristine methods before importing test modules.
    Report leaks at their source and restore the methods so subsequent modules
    still run with independent results.
    """

    original_methods = (logging.Logger.addHandler, logging.Logger.callHandlers)
    _module_snapshots = {}
    _import_leaks = []
    _tracking_import = False
    _track_imports_enabled = True
    # Alembic's fileConfig and SQLAlchemy's logger setup are process-wide
    # integration side effects, rather than test-owned logging mutations.
    _expected_external_loggers = ("alembic", "sqlalchemy")

    @classmethod
    def reset_tracking(cls):
        cls._module_snapshots = {}
        cls._import_leaks = []
        cls._track_imports_enabled = True

    @staticmethod
    def _snapshot_logging():
        loggers = {"root": logging.getLogger()}
        loggers.update({name: logger for name, logger in logging.Logger.manager.loggerDict.items()
                        if isinstance(logger, logging.Logger)})
        return {
            name: (tuple(logger.handlers), tuple(logger.filters), logger.level,
                   logger.propagate, logger.disabled)
            for name, logger in loggers.items()
        }

    @staticmethod
    def _logging_changes(before, after):
        changes = {}
        default = ((), (), logging.NOTSET, True, False)
        for name in before.keys() | after.keys():
            if name not in before and after.get(name) == default:
                continue
            if before.get(name) != after.get(name):
                changes[name] = (before.get(name), after.get(name))
        for name in tuple(changes):
            if name.startswith(LoggingIsolationSuite._expected_external_loggers):
                changes.pop(name)
        # Alembic's fileConfig also replaces the root stderr handler.  Keep
        # detecting root filters, levels, propagation, and arbitrary handlers;
        # ignore this one handler-only change when the migration loggers moved
        # in the same boundary.
        root = changes.get("root")
        external_changed = any(
            name.startswith(LoggingIsolationSuite._expected_external_loggers)
            for name in before.keys() | after.keys()
            if before.get(name) != after.get(name)
        )
        if root and external_changed:
            before_root, after_root = root
            if (before_root[1:] == after_root[1:]
                    and before_root[0] != after_root[0]):
                changes.pop("root", None)
        if root and "root" in changes:
            before_root, after_root = root
            def handler_shape(handler):
                return (type(handler), handler.level,
                        getattr(handler, "stream", None) is sys.stderr)
            if (before_root[1:] == after_root[1:]
                    and [handler_shape(item) for item in before_root[0]]
                    == [handler_shape(item) for item in after_root[0]]):
                changes.pop("root", None)
        return changes

    @staticmethod
    def _restore_logging(snapshot):
        default = ((), (), logging.NOTSET, True, False)
        # Preserve logger objects created by a module.  Removing them from
        # loggerDict leaves references held by tests detached from getLogger;
        # reset only a newly-created logger that actually carries state.
        for name, logger in list(logging.Logger.manager.loggerDict.items()):
            if not isinstance(logger, logging.Logger) or name in snapshot:
                continue
            state = (tuple(logger.handlers), tuple(logger.filters), logger.level,
                     logger.propagate, logger.disabled)
            if state != default:
                logger.handlers[:] = []
                logger.filters[:] = []
                logger.setLevel(logging.NOTSET)
                logger.propagate = True
                logger.disabled = False
        for name, state in snapshot.items():
            logger = logging.getLogger() if name == "root" else logging.getLogger(name)
            handlers, filters, level, propagate, disabled = state
            logger.handlers[:] = handlers
            logger.filters[:] = filters
            logger.setLevel(level)
            logger.propagate = propagate
            logger.disabled = disabled

    @classmethod
    def _record_import_leak(cls, module_name, before):
        after = cls._snapshot_logging()
        changes = cls._logging_changes(before, after)
        if changes:
            cls._import_leaks.append((module_name, changes))
            cls._restore_logging(before)

    @classmethod
    def track_imports(cls):
        original = builtins.__import__

        def tracked(name, globals=None, locals=None, fromlist=(), level=0):
            if not cls._track_imports_enabled or cls._tracking_import:
                return original(name, globals, locals, fromlist, level)
            cls._tracking_import = True
            before = cls._snapshot_logging()
            try:
                return original(name, globals, locals, fromlist, level)
            finally:
                try:
                    if level == 0:
                        cls._record_import_leak(name, before)
                finally:
                    cls._tracking_import = False

        builtins.__import__ = tracked
        return original

    def _handleModuleTearDown(self, result):
        previous = self._get_previous_module(result)
        super()._handleModuleTearDown(result)
        if previous is None:
            return
        changed = [name for name, original in zip(
            ("addHandler", "callHandlers"), self.original_methods)
            if getattr(logging.Logger, name) is not original]
        snapshot = self._module_snapshots.pop(previous, None)
        state_changes = self._logging_changes(snapshot, self._snapshot_logging()) if snapshot else {}
        if not changed and not state_changes:
            return
        try:
            details = [f"{previous} leaked Logger.{name}" for name in changed]
            if state_changes:
                details.append(f"{previous} leaked logger state: {', '.join(sorted(state_changes))}")
            raise AssertionError("; ".join(details))
        except AssertionError:
            # Use a real assertion failure, attributed to the completed module.
            witness = unittest.FunctionTestCase(lambda: None,
                                                description=previous + " logging isolation")
            result.addFailure(witness, sys.exc_info())
        finally:
            handle = getattr(logging.Logger.addHandler, "_privacy_handle", None)
            if handle is not None:
                handle.close()
            logging.Logger.addHandler, logging.Logger.callHandlers = self.original_methods
            if snapshot:
                self._restore_logging(snapshot)

    def _handleModuleFixture(self, test, result):
        # Imports during suite loading are the module-import boundary under
        # inspection. Once the first test starts, imports belong to test code
        # and dependency setup, so they must not be reported as import leaks.
        type(self)._track_imports_enabled = False
        super()._handleModuleFixture(test, result)
        module = getattr(test.__class__, "__module__", None)
        if module and module not in self._module_snapshots:
            self._module_snapshots[module] = self._snapshot_logging()


def run_logging_checked_tests(arguments):
    LoggingIsolationSuite.reset_tracking()
    original_import = LoggingIsolationSuite.track_imports()
    loader = unittest.TestLoader()
    loader.suiteClass = LoggingIsolationSuite
    try:
        program = unittest.main(module=None, argv=[sys.argv[0], *arguments],
                                testLoader=loader, exit=False)
    finally:
        builtins.__import__ = original_import
    for module, changes in LoggingIsolationSuite._import_leaks:
        witness = unittest.FunctionTestCase(lambda: None,
                                            description=module + " import logging isolation")
        message = f"{module} leaked logger state at import: {', '.join(sorted(changes))}"
        try:
            raise AssertionError(message)
        except AssertionError:
            program.result.addFailure(witness, sys.exc_info())
        print(message, file=sys.stderr)
    return 0 if program.result.wasSuccessful() else 1


def main():
    if len(sys.argv) == 1:
        raise SystemExit("Pass unittest modules or discovery arguments")
    before = repository_artifacts()
    before_files = artifact_files()
    result = subprocess.run([sys.executable, "-m", "tests.check_isolation",
                             "--logging-child", *sys.argv[1:]], cwd=ROOT)
    after = repository_artifacts()
    after_files = artifact_files()
    changed = {
        path for path in before_files.keys() | after_files.keys()
        if before_files.get(path) != after_files.get(path)
    }
    # Retain the git-status check too (e.g. an index/status change without a file
    # metadata change), and report only the differing entries from this run.
    changed.update(line[3:] for line in set(before.splitlines()) ^ set(after.splitlines()))
    if changed:
        print("Repository artifacts changed:\nNew/changed repository artifacts:", file=sys.stderr)
        for path in sorted(changed):
            print(f"  {path}", file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--logging-child":
        raise SystemExit(run_logging_checked_tests(sys.argv[2:]))
    raise SystemExit(main())
