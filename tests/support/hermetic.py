"""Small-layer hermetic guard (test-plan sections 3.1 and 5).

While a ``SmallTestCase`` runs, on the thread running it:

* reading the real clock from repository code fails: ``time.time``/``time_ns``/
  ``monotonic``/``monotonic_ns``/``perf_counter``/``perf_counter_ns`` and
  ``datetime.now``/``utcnow``/``today``, ``date.today``. Library internals
  (logging timestamps, unittest's own timing) keep the real clock.
* ``time.sleep`` fails;
* disk writes fail: ``open`` in a write mode, ``os.open`` with write flags,
  ``os`` create/remove/rename functions and ``tempfile`` file/directory creation;
* network access fails: ``socket.connect``/``connect_ex``/``sendto``,
  ``socket.create_connection`` and ``socket.getaddrinfo``.

Coverage. ``time``, ``os``, ``tempfile``, ``socket`` and ``builtins.open`` are
patched at module level. ``datetime``/``date`` are C types, so instead the
guard rebinds names in repository modules (``from datetime import datetime``,
``import datetime``, ``from time import monotonic`` ...) to guarded versions.
Not covered: function objects captured before the test (e.g. a default argument
``now=datetime.now``), and libraries reading the clock on the code's behalf.

Process safety. Unit tests share one process with every other module (CI and
host CD), so the guard only affects the thread that runs the small test, and
everything it replaced is restored when the test ends, even when it fails.
A violation that the code under test catches and swallows still fails the test.
"""
import builtins
from contextlib import contextmanager
import datetime as _datetime_module
from functools import wraps
import io
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
_REAL_DATETIME = _datetime_module.datetime
_REAL_DATE = _datetime_module.date

CLOCK_READS = ("time", "time_ns", "monotonic", "monotonic_ns", "perf_counter", "perf_counter_ns")
OS_WRITES = ("mkdir", "makedirs", "remove", "unlink", "rmdir", "removedirs", "rename", "renames",
             "replace", "symlink", "link", "truncate", "chmod", "utime", "mkfifo")
TEMPFILE_WRITES = ("mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryFile")
SOCKET_METHODS = ("connect", "connect_ex", "sendto")
SOCKET_FUNCTIONS = ("create_connection", "getaddrinfo")
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

CLOCK, SLEEP, DISK, NETWORK = "read the real clock", "sleep", "write to disk", "use the network"


class HermeticViolation(AssertionError):
    """A small test touched the real clock, sleep, disk writes or the network."""


_active = None  # the installed SmallGuard, if any


def _repo_code_paths():
    root = os.path.join(str(ROOT), "")
    # A virtualenv inside the checkout (``uv run`` in CI) is library code.
    environments = tuple(os.path.join(prefix, "")
                         for prefix in {sys.prefix, sys.base_prefix, sys.exec_prefix}
                         if os.path.join(prefix, "").startswith(root))
    # The runner and this guard are infrastructure, not code under test.
    infrastructure = {str(ROOT / "tests" / "check_isolation.py"), os.path.abspath(__file__)}
    return root, environments, infrastructure


_ROOT_PREFIX, _ENVIRONMENTS, _INFRASTRUCTURE = _repo_code_paths()
_repo_file_cache = {}


def _is_repo_file(filename):
    cached = _repo_file_cache.get(filename)
    if cached is None:
        path = os.path.abspath(filename)
        cached = (path.startswith(_ROOT_PREFIX) and not path.startswith(_ENVIRONMENTS)
                  and "site-packages" not in path and path not in _INFRASTRUCTURE)
        _repo_file_cache[filename] = cached
    return cached


def _violation(kind, name):
    violation = HermeticViolation(
        f"small tests must not {kind} ({name}); inject tests.support.clock.FakeClock "
        "or an in-memory fake, or move the test to tests/medium")
    _active.violations.append(violation)
    raise violation


def _guarding_this_thread():
    return _active is not None and _active.thread == threading.get_ident()


class _RealTypeCheck(type):
    """isinstance/issubclass against a guarded class behave as for the real class."""

    def __instancecheck__(cls, instance):
        return isinstance(instance, cls._real)

    def __subclasscheck__(cls, subclass):
        return issubclass(subclass, cls._real)


class GuardedDate(_REAL_DATE, metaclass=_RealTypeCheck):
    _real = _REAL_DATE

    def __new__(cls, *args, **kwargs):
        return _REAL_DATE(*args, **kwargs)

    @classmethod
    def today(cls):
        if _guarding_this_thread():
            _violation(CLOCK, "date.today")
        return _REAL_DATE.today()


class GuardedDatetime(_REAL_DATETIME, metaclass=_RealTypeCheck):
    _real = _REAL_DATETIME

    def __new__(cls, *args, **kwargs):
        return _REAL_DATETIME(*args, **kwargs)

    @classmethod
    def now(cls, tz=None):
        if _guarding_this_thread():
            _violation(CLOCK, "datetime.now")
        return _REAL_DATETIME.now(tz)

    @classmethod
    def utcnow(cls):
        if _guarding_this_thread():
            _violation(CLOCK, "datetime.utcnow")
        return _REAL_DATETIME.utcnow()

    @classmethod
    def today(cls):
        if _guarding_this_thread():
            _violation(CLOCK, "datetime.today")
        return _REAL_DATETIME.today()


class _DatetimeModule(types.ModuleType):
    """Stands in for ``import datetime`` bindings in repository modules."""

    def __getattr__(self, name):
        return getattr(_datetime_module, name)


_DATETIME_MODULE = _DatetimeModule("datetime")
_DATETIME_MODULE.datetime = GuardedDatetime
_DATETIME_MODULE.date = GuardedDate


def _clock_reader(name, original):
    @wraps(original)
    def guarded(*args, **kwargs):
        if _guarding_this_thread() and _is_repo_file(sys._getframe(1).f_code.co_filename):
            _violation(CLOCK, name)
        return original(*args, **kwargs)
    return guarded


def _always_denied(kind, name, original):
    @wraps(original)
    def guarded(*args, **kwargs):
        if _guarding_this_thread():
            _violation(kind, name)
        return original(*args, **kwargs)
    return guarded


def _guarded_open(original):
    @wraps(original)
    def guarded(file, mode="r", *args, **kwargs):
        if (_guarding_this_thread() and not isinstance(file, int)
                and any(flag in mode for flag in "wax+")):
            _violation(DISK, f"open(mode={mode!r})")
        return original(file, mode, *args, **kwargs)
    return guarded


def _guarded_os_open(original):
    @wraps(original)
    def guarded(path, flags, *args, **kwargs):
        if _guarding_this_thread() and flags & _WRITE_FLAGS:
            _violation(DISK, "os.open with write flags")
        return original(path, flags, *args, **kwargs)
    return guarded


class SmallGuard:
    """Installs the small-layer patches for the current thread; restores on exit."""

    def __init__(self):
        self.violations = []
        self.thread = None
        self._attributes = []  # (owner, name, had_own_value, own_value)
        self._bindings = []    # (namespace, key, original, replacement)

    def __enter__(self):
        global _active
        if _active is not None:
            raise RuntimeError("small-layer guard is already active")
        self.thread = threading.get_ident()
        try:
            self._install()
        except BaseException:
            self._restore()
            raise
        _active = self
        return self

    def __exit__(self, *exc_info):
        global _active
        _active = None
        self._restore()
        return False

    def _patch(self, owner, name, replacement):
        own = vars(owner)
        self._attributes.append((owner, name, name in own, own.get(name)))
        setattr(owner, name, replacement)
        return replacement

    def _install(self):
        swaps = {
            id(_REAL_DATETIME): (_REAL_DATETIME, GuardedDatetime),
            id(_REAL_DATE): (_REAL_DATE, GuardedDate),
            id(_datetime_module): (_datetime_module, _DATETIME_MODULE),
        }

        def module_function(module, name, make):
            original = getattr(module, name)
            swaps[id(original)] = (original, self._patch(module, name, make(original)))

        for name in CLOCK_READS:
            module_function(time, name, lambda original, name=name: _clock_reader(f"time.{name}", original))
        module_function(time, "sleep", lambda original: _always_denied(SLEEP, "time.sleep", original))
        opener = _guarded_open(builtins.open)
        swaps[id(builtins.open)] = (builtins.open, opener)
        self._patch(builtins, "open", opener)
        self._patch(io, "open", opener)
        module_function(os, "open", _guarded_os_open)
        for name in OS_WRITES:
            if hasattr(os, name):
                module_function(os, name, lambda original, name=name: _always_denied(DISK, f"os.{name}", original))
        for name in TEMPFILE_WRITES:
            module_function(tempfile, name,
                            lambda original, name=name: _always_denied(DISK, f"tempfile.{name}", original))
        for name in SOCKET_FUNCTIONS:
            module_function(socket, name,
                            lambda original, name=name: _always_denied(NETWORK, f"socket.{name}", original))
        for name in SOCKET_METHODS:
            original = getattr(socket.socket, name)
            self._patch(socket.socket, name, _always_denied(NETWORK, f"socket.{name}", original))
        self._rebind_repository_names(swaps)

    def _rebind_repository_names(self, swaps):
        """Swap names that repository modules imported from time/datetime/os/... directly."""
        for module in list(sys.modules.values()):
            namespace = getattr(module, "__dict__", None)
            filename = namespace.get("__file__") if isinstance(namespace, dict) else None
            if not isinstance(filename, str) or not _is_repo_file(filename):
                continue
            for key, value in list(namespace.items()):
                swap = swaps.get(id(value))
                if swap is not None and swap[0] is value:
                    namespace[key] = swap[1]
                    self._bindings.append((namespace, key, value, swap[1]))

    def _restore(self):
        while self._bindings:
            namespace, key, original, replacement = self._bindings.pop()
            if namespace.get(key) is replacement:
                namespace[key] = original
        while self._attributes:
            owner, name, had_own, own_value = self._attributes.pop()
            if had_own:
                setattr(owner, name, own_value)
            else:
                delattr(owner, name)


@contextmanager
def small_guard():
    """Guard the current thread; a nested call while a guard is active is a no-op."""
    if _active is not None:
        yield None
        return
    with SmallGuard() as guard:
        yield guard


def _raise_unreported(guard, where):
    if guard is not None and guard.violations:
        raise HermeticViolation(f"{where}: " + "; ".join(map(str, guard.violations)))


def _guarded_class_fixture(function):
    @wraps(function)
    def fixture(cls):
        with small_guard() as guard:
            result = function(cls)
            _raise_unreported(guard, f"{cls.__qualname__}.{function.__name__} hid a violation")
            return result
    return fixture


class _ReportedViolations:
    """Result proxy: a violation reaching the result is reported, not hidden."""

    def __init__(self, result, guard):
        self._result = result
        self._guard = guard

    def __getattr__(self, name):
        return getattr(self._result, name)

    def _reported(self, err):
        error = err[1] if err else None
        self._guard.violations[:] = [item for item in self._guard.violations if item is not error]

    def addError(self, test, err):
        self._reported(err)
        self._result.addError(test, err)

    def addFailure(self, test, err):
        self._reported(err)
        self._result.addFailure(test, err)

    def addSubTest(self, test, subtest, err):
        self._reported(err)
        self._result.addSubTest(test, subtest, err)

    def addExpectedFailure(self, test, err):
        self._reported(err)
        self._result.addExpectedFailure(test, err)


class SmallTestCase(unittest.TestCase):
    """Base class for every test in tests/small; runs each test under ``small_guard``."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name in ("setUpClass", "tearDownClass"):
            fixture = cls.__dict__.get(name)
            if isinstance(fixture, classmethod):
                setattr(cls, name, classmethod(_guarded_class_fixture(fixture.__func__)))

    def run(self, result=None):
        with small_guard() as guard:
            if guard is None or result is None:
                return super().run(result)
            check = (_raise_unreported, (guard, "the code under test caught and hid a violation"), {})
            self._cleanups.append(check)  # first in, so it runs after every test cleanup
            try:
                super().run(_ReportedViolations(result, guard))
            finally:
                if check in self._cleanups:  # skipped tests never run cleanups
                    self._cleanups.remove(check)
            return result

    @contextmanager
    def assertHermeticViolation(self, kind):
        """Expect one guard violation of ``kind`` inside the block (for guard self-tests)."""
        with self.assertRaises(HermeticViolation) as caught:
            yield caught
        if _active is not None:
            _active.violations[:] = [item for item in _active.violations
                                     if item is not caught.exception]
        self.assertIn(kind, str(caught.exception))
