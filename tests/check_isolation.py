"""Run unittest arguments and reject new/changed data or output git status.

CI/local usage: python -m tests.check_isolation tests.test_offline_followups
Full CI usage: python -m tests.check_isolation discover -s tests -t . -v

The child runner also times tests under tests/small, tests/medium and
tests/large against the budgets of docs/test-plan.md 3.1/3.2. Budgets are a
health check, not a gate: a test over its limit or a layer over its total is
listed in the layer budget report but does not fail the run; failed assertions
and small-layer guard violations still do. Per-file durations go to
$TMPDIR/test-durations.json. Legacy test modules are timed but never budgeted.
"""
import logging
import builtins
import copy
from functools import partial
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


_NO_MEMO = object()


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
    _module_setup_leaks = {}
    _module_setup_method_leaks = {}
    _import_leaks = []
    _tracking_import = False
    _track_imports_enabled = True
    # Alembic's fileConfig and SQLAlchemy's logger setup are process-wide
    # integration side effects, rather than test-owned logging mutations.
    _expected_external_loggers = ("alembic", "sqlalchemy", "psycopg")

    @classmethod
    def reset_tracking(cls):
        cls._module_snapshots = {}
        cls._module_setup_leaks = {}
        cls._module_setup_method_leaks = {}
        cls._import_leaks = []
        cls._track_imports_enabled = True

    @staticmethod
    def _stable_state(value):
        """Copy logging component state without retaining object identities."""
        if value is None or isinstance(value, (bool, int, float, str, bytes)):
            return value
        if isinstance(value, dict):
            return tuple(sorted((repr(key), LoggingIsolationSuite._stable_state(item))
                                for key, item in value.items()))
        if isinstance(value, (list, tuple)):
            return tuple(LoggingIsolationSuite._stable_state(item) for item in value)
        if isinstance(value, (set, frozenset)):
            return frozenset(LoggingIsolationSuite._stable_state(item) for item in value)
        if hasattr(value, "__dict__"):
            return (type(value), LoggingIsolationSuite._stable_state(vars(value)))
        return type(value)

    @staticmethod
    def _callable_state(value):
        code = getattr(value, "__code__", None)
        if code is None:
            return None
        return (
            code.co_code,
            code.co_consts,
            code.co_names,
            code.co_varnames,
            LoggingIsolationSuite._stable_state(getattr(value, "__defaults__", None)),
            LoggingIsolationSuite._stable_state(getattr(value, "__kwdefaults__", None)),
            LoggingIsolationSuite._stable_state(
                tuple(getattr(cell, "cell_contents", None)
                      for cell in (getattr(value, "__closure__", None) or ()))
            ),
        )

    @staticmethod
    def _component_snapshot(item, memo=None):
        memo = {} if memo is None else memo
        original_defaults = getattr(item, "__defaults__", None)
        original_kwdefaults = getattr(item, "__kwdefaults__", None)
        original_closure = tuple(getattr(cell, "cell_contents", None)
                                 for cell in (getattr(item, "__closure__", None) or ()))
        defaults, kwdefaults, closure = copy.deepcopy((
            getattr(item, "__defaults__", None),
            getattr(item, "__kwdefaults__", None),
            tuple(getattr(cell, "cell_contents", None)
                  for cell in (getattr(item, "__closure__", None) or ())),
        ), memo)
        return (
            copy.deepcopy(getattr(item, "__dict__", {}), memo),
            defaults,
            kwdefaults,
            closure,
            (original_defaults, original_kwdefaults, original_closure),
        )

    @staticmethod
    def _restore_callable(item, state, memo=None):
        memo = {} if memo is None else memo
        originals = state[4] if len(state) > 4 else (None, None, ())
        original_defaults, original_kwdefaults, original_closure = originals
        current_defaults = original_defaults or getattr(item, "__defaults__", None)
        defaults = (tuple(LoggingIsolationSuite._restore_value(current, saved, memo)
                           for current, saved in zip(current_defaults or (), state[1] or ()))
                    if state[1] is not None else None)
        current_kwdefaults = original_kwdefaults or getattr(item, "__kwdefaults__", None) or {}
        kwdefaults = (dict((key, LoggingIsolationSuite._restore_value(current_kwdefaults.get(key), value, memo))
                            for key, value in state[2].items())
                      if state[2] is not None else None)
        closure = getattr(item, "__closure__", None) or ()
        current_closure = original_closure or tuple(
            getattr(cell, "cell_contents", None) for cell in closure
        )
        closure_values = tuple(
            LoggingIsolationSuite._restore_value(current, saved, memo)
            for current, saved in zip(current_closure, state[3])
        )
        if hasattr(item, "__defaults__"):
            item.__defaults__ = defaults
        if hasattr(item, "__kwdefaults__"):
            item.__kwdefaults__ = kwdefaults
        for cell, value in zip(closure, closure_values):
            cell.cell_contents = value

    @staticmethod
    def _restore_value(current, saved, memo):
        if saved is current or memo.get(id(saved), _NO_MEMO) is current:
            return current
        if isinstance(current, tuple) and isinstance(saved, tuple):
            return tuple(LoggingIsolationSuite._restore_value(existing, original, memo)
                         for existing, original in zip(current, saved))
        if isinstance(current, dict) and isinstance(saved, dict):
            memo[id(saved)] = current
            for key in tuple(current):
                if key not in saved:
                    del current[key]
            for key, value in saved.items():
                current[key] = LoggingIsolationSuite._restore_value(
                    current.get(key), value, memo
                )
            return current
        if isinstance(current, list) and isinstance(saved, list):
            memo[id(saved)] = current
            current[:] = [LoggingIsolationSuite._restore_value(
                current[index] if index < len(current) else None, value, memo
            ) for index, value in enumerate(saved)]
            return current
        if isinstance(current, set) and isinstance(saved, set):
            saved_copy = copy.deepcopy(saved, memo)
            memo[id(saved)] = current
            current.clear()
            current.update(saved_copy)
            return current
        return copy.deepcopy(saved, memo)

    @classmethod
    def _restore_component_dict(cls, item, saved, memo):
        current = dict(getattr(item, "__dict__", {}))
        item.__dict__.clear()
        for key, value in saved.items():
            item.__dict__[key] = cls._restore_value(current.get(key), value, memo)

    @staticmethod
    def _handler_shape(handler):
        formatter = getattr(handler, "formatter", None)
        return (
            type(handler),
            handler.level,
            id(getattr(handler, "stream", None)),
            tuple((type(item), LoggingIsolationSuite._stable_state(getattr(item, "__dict__", {})),
                   LoggingIsolationSuite._callable_state(item))
                  for item in handler.filters),
            type(formatter),
            getattr(formatter, "_fmt", None),
            getattr(formatter, "datefmt", None),
            LoggingIsolationSuite._stable_state(getattr(formatter, "__dict__", {})),
        )

    @classmethod
    def _snapshot_logging(cls):
        loggers = {"root": logging.getLogger()}
        loggers.update({name: logger for name, logger in logging.Logger.manager.loggerDict.items()
                        if isinstance(logger, logging.Logger)})
        memo = {}
        return {
            name: (tuple(logger.handlers), tuple(logger.filters), logger.level,
                   logger.propagate, logger.disabled,
                   (tuple(cls._handler_shape(handler) for handler in logger.handlers),
                    tuple((type(item), cls._stable_state(getattr(item, "__dict__", {})),
                           cls._callable_state(item))
                          for item in logger.filters)),
                   tuple((handler.level, tuple(handler.filters),
                          getattr(handler, "formatter", None),
                          getattr(handler, "stream", None),
                          tuple((item, cls._component_snapshot(item, memo))
                                for item in handler.filters),
                          copy.deepcopy(getattr(getattr(handler, "formatter", None),
                                                "__dict__", {})))
                         for handler in logger.handlers),
                   tuple((item, cls._component_snapshot(item, memo))
                         for item in logger.filters))
            for name, logger in loggers.items()
        }

    @staticmethod
    def _logging_changes(before, after, *, ignore_external=True):
        def is_expected_external(name):
            return any(name == prefix or name.startswith(prefix + ".")
                       for prefix in LoggingIsolationSuite._expected_external_loggers)

        changes = {}
        default = ((), (), logging.NOTSET, True, False, ((), ()), (), ())
        def comparable(state):
            if state is None:
                return None
            handlers, filters, level, propagate, disabled, shapes, _details, filter_states = state
            details_signature = tuple(
                (level, tuple((type(item), LoggingIsolationSuite._stable_state(state),
                               LoggingIsolationSuite._callable_state(item))
                              for item, state in handler_filter_states),
                 LoggingIsolationSuite._stable_state(formatter_state))
                for level, _filters, _formatter, _stream, handler_filter_states, formatter_state
                in _details
            )
            filter_signature = tuple((type(item), LoggingIsolationSuite._stable_state(data),
                                      LoggingIsolationSuite._callable_state(item))
                                     for item, data in filter_states)
            return (shapes, details_signature, filter_signature, level, propagate, disabled)
        for name in before.keys() | after.keys():
            if name not in before and comparable(after.get(name)) == comparable(default):
                continue
            if comparable(before.get(name)) != comparable(after.get(name)):
                changes[name] = (before.get(name), after.get(name))
        if ignore_external:
            for name in tuple(changes):
                if is_expected_external(name):
                    changes.pop(name)
        # Alembic's fileConfig also replaces the root stderr handler.  Keep
        # detecting root filters, levels, propagation, and arbitrary handlers;
        # ignore this one handler-only change when the migration loggers moved
        # in the same boundary.
        root = changes.get("root")
        external_changed = any(
            is_expected_external(name)
            for name in before.keys() | after.keys()
            if before.get(name) != after.get(name)
        )
        if root and external_changed:
            before_root, after_root = root
            # Alembic's fileConfig may replace an equivalent stderr handler
            # while it adjusts its own loggers.  A real root handler change,
            # such as a new FileHandler, remains a leak even in that case.
            if (before_root[1:5] == after_root[1:5]
                    and before_root[5] == after_root[5]):
                changes.pop("root", None)
        if root and "root" in changes:
            before_root, after_root = root
            if (before_root[1:5] == after_root[1:5]
                    and before_root[5] == after_root[5]):
                changes.pop("root", None)
        return changes

    @staticmethod
    def _restore_logging(snapshot):
        default = ((), (), logging.NOTSET, True, False, ((), ()), (), ())
        # Preserve logger objects created by a module.  Removing them from
        # loggerDict leaves references held by tests detached from getLogger;
        # reset only a newly-created logger that actually carries state.
        for name, logger in list(logging.Logger.manager.loggerDict.items()):
            if not isinstance(logger, logging.Logger) or name in snapshot:
                continue
            state = (tuple(logger.handlers), tuple(logger.filters), logger.level,
                     logger.propagate, logger.disabled,
                     tuple(LoggingIsolationSuite._handler_shape(handler)
                           for handler in logger.handlers),
                     tuple((handler.level, tuple(handler.filters),
                            getattr(handler, "formatter", None),
                            getattr(handler, "stream", None),
                            tuple((item, LoggingIsolationSuite._component_snapshot(item))
                                  for item in handler.filters),
                            copy.deepcopy(getattr(getattr(handler, "formatter", None),
                                                  "__dict__", {})))
                           for handler in logger.handlers),
                     tuple((item, LoggingIsolationSuite._component_snapshot(item))
                           for item in logger.filters))
            if (state[1:] != default[1:]):
                logger.handlers[:] = []
                logger.filters[:] = []
                logger.setLevel(logging.NOTSET)
                logger.propagate = True
                logger.disabled = False
        callable_memo = {}
        restored_callable_ids = set()
        for name, state in snapshot.items():
            logger = logging.getLogger() if name == "root" else logging.getLogger(name)
            handlers, filters, level, propagate, disabled, _handler_shapes, handler_details, filter_states = state
            logger.handlers[:] = handlers
            logger.filters[:] = filters
            for item, item_state in filter_states:
                if id(item) in restored_callable_ids:
                    continue
                if hasattr(item, "__dict__"):
                    LoggingIsolationSuite._restore_component_dict(item, item_state[0], callable_memo)
                LoggingIsolationSuite._restore_callable(item, item_state, callable_memo)
                restored_callable_ids.add(id(item))
            logger.setLevel(level)
            logger.propagate = propagate
            logger.disabled = disabled
            for handler, details in zip(handlers, handler_details):
                handler_level, handler_filters, formatter, stream, filter_states, formatter_state = details
                handler.setLevel(handler_level)
                handler.filters[:] = handler_filters
                handler.setFormatter(formatter)
                for item, state in filter_states:
                    if id(item) in restored_callable_ids:
                        continue
                    if hasattr(item, "__dict__"):
                        LoggingIsolationSuite._restore_component_dict(item, state[0], callable_memo)
                    LoggingIsolationSuite._restore_callable(item, state, callable_memo)
                    restored_callable_ids.add(id(item))
                if formatter is not None and hasattr(formatter, "__dict__"):
                    formatter.__dict__.clear()
                    formatter.__dict__.update(copy.deepcopy(formatter_state))
                if hasattr(handler, "stream"):
                    handler.stream = stream

    @classmethod
    def _record_import_leak(cls, module_name, before):
        after = cls._snapshot_logging()
        changes = cls._logging_changes(before, after)
        all_changes = cls._logging_changes(before, after, ignore_external=False)
        if all_changes:
            cls._restore_logging(before)
        if changes:
            cls._import_leaks.append((module_name, changes))

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

    def _tearDownPreviousClass(self, test, result):
        super()._tearDownPreviousClass(test, result)
        tracker = getattr(result, "budget_tracker", None)
        if tracker is not None:
            tracker.teardown_done()

    def _handleModuleTearDown(self, result):
        previous = self._get_previous_module(result)
        super()._handleModuleTearDown(result)
        tracker = getattr(result, "budget_tracker", None)
        if tracker is not None:
            tracker.teardown_done()
        if previous is None:
            return
        changed = [name for name, original in zip(
            ("addHandler", "callHandlers"), self.original_methods)
            if getattr(logging.Logger, name) is not original]
        snapshot = self._module_snapshots.pop(previous, None)
        current = self._snapshot_logging()
        state_changes = self._logging_changes(snapshot, current) if snapshot else {}
        all_state_changes = self._logging_changes(snapshot, current, ignore_external=False) if snapshot else {}
        setup_changes = self._module_setup_leaks.pop(previous, {})
        setup_method_changes = self._module_setup_method_leaks.pop(previous, ())
        if not changed and not state_changes and not setup_changes and not setup_method_changes:
            if snapshot and all_state_changes:
                self._restore_logging(snapshot)
            return
        try:
            details = [f"{previous} leaked Logger.{name}" for name in changed]
            details.extend(f"{previous} leaked logger state in setUpModule: {name}"
                           for name in sorted(setup_changes))
            details.extend(f"{previous} leaked Logger.{name} in setUpModule"
                           for name in setup_method_changes)
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
        module = getattr(test.__class__, "__module__", None)
        previous = self._get_previous_module(result)
        if previous == module:
            return
        # TestSuite normally performs the previous module's teardown inside
        # the superclass fixture method.  Do that first so this snapshot is a
        # genuine post-teardown baseline; otherwise a clean observer inherits
        # the prior module's leaked state and is reported as a second leak.
        self._handleModuleTearDown(result)
        before = self._snapshot_logging()
        previous_class = getattr(result, "_previousTestClass", None)
        result._previousTestClass = None
        try:
            super()._handleModuleFixture(test, result)
        finally:
            result._previousTestClass = previous_class
        if module:
            # Keep the pre-fixture state as the module baseline.  setUpModule
            # changes are allowed for the module's tests; teardown and cleanup
            # must restore them before the next module is compared.
            self._module_snapshots[module] = before


# Test-plan 3.1 limit per test and 3.2 wall budget per layer, in seconds.
# Overruns are reported, never failures (3.2: budgets watch cost, timeouts stop
# hangs). Only tests under tests/<layer>/ are budgeted; legacy modules carry no layer.
TEST_LAYERS = ("small", "medium", "large", "quarantine")
TEST_LIMITS = {"small": 1.0, "medium": 30.0, "large": 300.0}
LAYER_BUDGETS = {"small": 45.0, "medium": 135.0, "large": 360.0}


_module_files = {}


def _module_file(test):
    name = type(test).__module__
    if name not in _module_files:
        path = getattr(sys.modules.get(name), "__file__", None)
        _module_files[name] = Path(path).resolve() if path else None
    return name, _module_files[name]


def layer_of_test(test):
    """'small', 'medium', 'large' or 'quarantine' by directory, else None."""
    _name, path = _module_file(test)
    if path is None or not path.is_relative_to(ROOT / "tests"):
        return None
    parts = path.relative_to(ROOT / "tests").parts
    return parts[0] if len(parts) > 1 and parts[0] in TEST_LAYERS else None


def file_of_test(test):
    name, path = _module_file(test)
    if path is not None and path.is_relative_to(ROOT):
        return path.relative_to(ROOT).as_posix()
    return name


def default_durations_path():
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "test-durations.json"


class BudgetTracker:
    """Wall time per test, file and layer, measured by the runner.

    ``clock`` is injectable so self-tests drive it with a FakeClock. Time
    between tests is charged too: class/module teardown to the test before
    (see LoggingIsolationSuite), set-up to the test after.
    """

    def __init__(self, *, clock=time.monotonic, limits=None, budgets=None,
                 layer_of=layer_of_test, file_of=file_of_test):
        self.clock = clock
        self.limits = dict(TEST_LIMITS if limits is None else limits)
        self.budgets = dict(LAYER_BUDGETS if budgets is None else budgets)
        self.layer_of = layer_of
        self.file_of = file_of
        self.layer_counts = {}
        self.layer_seconds = {}
        self.file_seconds = {}
        self._mark = None
        self._started = {}
        self._previous = None
        self.overruns = []  # (test id, seconds, layer, limit)

    def _charge(self, test, seconds, *, count=False):
        layer = self.layer_of(test)
        file = self.file_of(test)
        self.file_seconds[file] = self.file_seconds.get(file, 0.0) + seconds
        if layer is not None:
            self.layer_seconds[layer] = self.layer_seconds.get(layer, 0.0) + seconds
            if count:
                self.layer_counts[layer] = self.layer_counts.get(layer, 0) + 1
        return layer

    def begin(self):
        self._mark = self.clock()

    def start(self, test):
        now = self.clock()
        if self._mark is not None:
            self._charge(test, now - self._mark)
        self._started[id(test)] = now

    def stop(self, test):
        """Record a finished test; return a message if it overran its limit."""
        now = self.clock()
        self._mark = now
        started = self._started.pop(id(test), None)
        if started is None:
            return None
        elapsed = now - started
        self._previous = test
        layer = self._charge(test, elapsed, count=True)
        limit = self.limits.get(layer)
        if limit is not None and elapsed > limit:
            self.overruns.append((test.id(), elapsed, layer, limit))
            return (f"{test.id()} took {elapsed:.2f} s; {layer} tests must finish "
                    f"within {limit:g} s (docs/test-plan.md 3.1)")
        return None

    def teardown_done(self):
        """Charge class/module teardown since the last test to that test."""
        if self._mark is not None and self._previous is not None:
            now = self.clock()
            self._charge(self._previous, now - self._mark)
            self._mark = now

    def end(self):
        self.teardown_done()
        self._mark = None

    def over_budget(self):
        return [layer for layer, budget in self.budgets.items()
                if self.layer_seconds.get(layer, 0.0) > budget]

    def report(self):
        over = set(self.over_budget())
        lines = ["Layer budget report (docs/test-plan.md 3.2):"]
        for layer, budget in self.budgets.items():
            count = self.layer_counts.get(layer, 0)
            if layer == "large" and not count:
                continue
            seconds = self.layer_seconds.get(layer, 0.0)
            lines.append(f"  {layer:<7}{count:>5} tests {seconds:>9.2f} s / {budget:g} s budget"
                         + ("  OVER BUDGET" if layer in over else ""))
        if self.overruns:
            lines.append(f"Tests over their limit ({len(self.overruns)}):")
            lines.extend(f"  {test_id}  {elapsed:.2f} s > {limit:g} s {layer} limit"
                         for test_id, elapsed, layer, limit in self.overruns)
        if over or self.overruns:
            lines.append("Budgets are a health check, not a gate: the run's result "
                         "depends only on test outcomes.")
        return "\n".join(lines)

    def write_durations(self, path):
        """Write {file: seconds} atomically, for tests/durations.json refreshes."""
        path = Path(path)
        data = {file: round(seconds, 3) for file, seconds in sorted(self.file_seconds.items())}
        partial_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        partial_path.write_text(json.dumps(data, indent=2) + "\n")
        os.replace(partial_path, path)


class BudgetedTextTestResult(unittest.TextTestResult):
    def __init__(self, *args, budget_tracker, **kwargs):
        super().__init__(*args, **kwargs)
        self.budget_tracker = budget_tracker

    def startTestRun(self):
        super().startTestRun()
        self.budget_tracker.begin()

    def startTest(self, test):
        self.budget_tracker.start(test)
        super().startTest(test)

    def stopTest(self, test):
        self.budget_tracker.stop(test)
        super().stopTest(test)

    def stopTestRun(self):
        self.budget_tracker.end()
        super().stopTestRun()


def run_logging_checked_tests(arguments, *, tracker=None, durations_path=None):
    LoggingIsolationSuite.reset_tracking()
    original_import = LoggingIsolationSuite.track_imports()
    loader = unittest.TestLoader()
    loader.suiteClass = LoggingIsolationSuite
    runner_stream = io.StringIO()
    verbosity = 2 if any(argument in {"-v", "--verbose"} for argument in arguments) else 1
    tracker = BudgetTracker() if tracker is None else tracker
    runner = unittest.TextTestRunner(
        stream=runner_stream, verbosity=verbosity,
        resultclass=partial(BudgetedTextTestResult, budget_tracker=tracker),
    )
    try:
        program = unittest.main(module=None, argv=[sys.argv[0], *arguments],
                                testLoader=loader, testRunner=runner, exit=False)
    finally:
        builtins.__import__ = original_import
    new_failures = []
    for module, changes in LoggingIsolationSuite._import_leaks:
        witness = unittest.FunctionTestCase(lambda: None,
                                            description=module + " import logging isolation")
        message = f"{module} leaked logger state at import: {', '.join(sorted(changes))}"
        try:
            raise AssertionError(message)
        except AssertionError:
            program.result.addFailure(witness, sys.exc_info())
            new_failures.append((witness, program.result.failures[-1][1]))

    # unittest.main prints its summary as soon as the test body returns.  An
    # import leak is discovered immediately after that body, so append it to a
    # captured report and emit one final status line.  This keeps a stale
    # trailing ``OK`` from masking the non-zero exit status.
    rendered = runner_stream.getvalue()
    marker = "\n----------------------------------------------------------------------\n"
    if marker in rendered:
        body, _summary = rendered.rsplit(marker, 1)
    else:
        body = rendered.rstrip("\n")
    if body:
        print(body, file=sys.stderr)
    for witness, trace in new_failures:
        print(f"\n{witness.id()}", file=sys.stderr)
        print(trace.rstrip("\n"), file=sys.stderr)
    # Layer budgets (test-plan 3.2) are reported only; they never fail the run.
    print("", file=sys.stderr)
    print(tracker.report(), file=sys.stderr)
    try:
        tracker.write_durations(durations_path or default_durations_path())
    except OSError as error:
        print(f"Could not write test durations: {error}", file=sys.stderr)
    print(marker.rstrip("\n"), file=sys.stderr)
    print(f"Ran {program.result.testsRun} tests", file=sys.stderr)
    successful = program.result.wasSuccessful()
    if successful:
        print("OK", file=sys.stderr)
    else:
        counts = []
        if program.result.failures:
            counts.append(f"failures={len(program.result.failures)}")
        if program.result.errors:
            counts.append(f"errors={len(program.result.errors)}")
        print(f"FAILED ({', '.join(counts)})", file=sys.stderr)
    return 0 if successful else 1


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
