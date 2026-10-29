"""Bounded shared work lanes; foreground holes overtake queued regional work."""

from __future__ import annotations

from concurrent.futures import Future
from contextlib import contextmanager
from contextvars import ContextVar
import heapq
import itertools
import logging
import threading
import time
from typing import Any, Callable, Hashable

FOREGROUND = 0
SELECTED_COURSE = 10
NEARBY = 20
BACKFILL = 30

# A package build is synchronous CPU work in the API process.  New background units wait for it
# so a round start does not spend its budget competing with warmers.  Thirty seconds is deliberately
# finite: each package blocks only until its entry age reaches 30s, not for 30s per waiter.
FOREGROUND_GATE_TIMEOUT_SECONDS = 30.0


_FOREGROUND_CONTEXT: ContextVar[bool] = ContextVar("foreground_admission", default=False)
logger = logging.getLogger(__name__)

_CURRENT_PRIORITY: ContextVar[int | None] = ContextVar("work_priority", default=None)


def current_priority() -> int:
    """Unknown threads are background; request/worker entry points set their lane."""
    value = _CURRENT_PRIORITY.get()
    return NEARBY if value is None else value


@contextmanager
def work_priority(priority: int):
    token = _CURRENT_PRIORITY.set(priority)
    try:
        yield
    finally:
        _CURRENT_PRIORITY.reset(token)


class ForegroundGate:
    """Coordinate synchronous package requests with background CPU units.

    A foreground request never acquires a background slot, which avoids a package -> warmer
    deadlock. Background callers wait only for unexpired foreground activities. Stale activities
    keep their lifecycle/count but cease blocking; a fresh request gets its own bounded window.
    """

    def __init__(self, *, timeout_s: float = FOREGROUND_GATE_TIMEOUT_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.timeout_s = max(0.0, float(timeout_s))
        self._clock = clock
        self._condition = threading.Condition()
        self._foreground: dict[object, float] = {}
        self._warned: set[object] = set()
        self._background = 0

    @contextmanager
    def foreground(self):
        with self._condition:
            ticket = object()
            self._foreground[ticket] = self._clock()
        try:
            yield
        finally:
            with self._condition:
                self._foreground.pop(ticket, None)
                self._warned.discard(ticket)
                self._condition.notify_all()

    @contextmanager
    def background(self, *, timeout_s: float | None = None):
        timeout = self.timeout_s if timeout_s is None else max(0.0, float(timeout_s))
        from ai_caddie.core.request_timing import mark

        with self._condition:
            marked = False
            wait_started = self._clock()
            while self._foreground:
                now = self._clock()
                live = []
                for ticket, started in self._foreground.items():
                    age = now - started
                    if age < timeout:
                        live.append(started + timeout)
                    elif ticket not in self._warned:
                        self._warned.add(ticket)
                        logger.warning("foreground_gate stale_package age_s=%.3f limit_s=%.3f", age, timeout)
                if not live:
                    break
                if not marked:
                    mark("background_gate_enter")
                    marked = True
                self._condition.wait(timeout=max(0.0, min(live) - now))
            if marked:
                mark("background_gate_wait")
                logger.info("background_gate_wait wait_ms=%.1f", (self._clock() - wait_started) * 1000)
            self._background += 1
        try:
            yield
        finally:
            with self._condition:
                self._background = max(0, self._background - 1)
                self._condition.notify_all()

    @property
    def foreground_count(self) -> int:
        with self._condition:
            return len(self._foreground)

    @property
    def background_count(self) -> int:
        with self._condition:
            return self._background


FOREGROUND_GATE = ForegroundGate()


@contextmanager
def foreground_scope():
    """Propagate an already-owned ASGI admission to synchronous endpoint/helper threads."""
    token = _FOREGROUND_CONTEXT.set(True)
    try:
        yield
    finally:
        _FOREGROUND_CONTEXT.reset(token)


@contextmanager
def foreground_work():
    """Mark one package build, reusing admission owned by its complete ASGI response."""
    if _FOREGROUND_CONTEXT.get():
        yield
        return
    with foreground_scope(), FOREGROUND_GATE.foreground():
        yield


@contextmanager
def background_work(*, timeout_s: float | None = None):
    """Admit one background CPU unit, with the finite package starvation bound."""
    with FOREGROUND_GATE.background(timeout_s=timeout_s):
        yield


class PrioritySlots:
    """A bounded render gate that admits the highest priority waiting caller first.

    Running renders complete normally; priority only chooses the next admission.
    """
    def __init__(self, capacity: int):
        self._condition = threading.Condition()
        self._available = capacity
        self._waiters: list[tuple[int, int]] = []
        self._sequence = itertools.count()

    def __enter__(self):
        priority = current_priority()
        ticket = (priority, next(self._sequence))
        with self._condition:
            heapq.heappush(self._waiters, ticket)
            try:
                self._condition.wait_for(lambda: self._available > 0 and self._waiters[0] == ticket)
            except BaseException:
                self._waiters.remove(ticket)
                heapq.heapify(self._waiters)
                self._condition.notify_all()
                raise
            heapq.heappop(self._waiters)
            self._available -= 1
            self._condition.notify_all()
        return self

    def __exit__(self, *exc):
        with self._condition:
            self._available += 1
            self._condition.notify_all()


class PriorityExecutor:
    """An executor with a priority queue and no per-request worker pools.

    Running provider/render calls finish normally. Only queued work is reordered,
    so callers should submit small windows rather than whole regions at once.
    """

    def __init__(self, max_workers: int, *, name: str) -> None:
        self._condition = threading.Condition()
        self._queue: list[tuple[int, int, int, Future, Callable, tuple, dict, Hashable | None]] = []
        self._sequence = itertools.count()
        self._entry_version = itertools.count()
        self._keyed: dict[Hashable, tuple[int, Future, Callable, tuple[Any, ...], dict[str, Any]]] = {}
        self._threads: list[threading.Thread] = []
        self._max_workers = max(1, max_workers)
        self._name = name
        self._closed = False

    def submit(self, fn: Callable, /, *args: Any, priority: int = SELECTED_COURSE,
               **kwargs: Any) -> Future:
        # Callers that need durable reprioritisation can attach a process-local key to the
        # submitted callable while retaining this long-standing ``submit`` API. This keeps simple
        # test/embedding doubles compatible and routes keyed work through the same heap path.
        key = getattr(fn, "__priority_work_key__", None)
        return self._submit(fn, args, kwargs, priority=int(priority), key=key)

    def submit_keyed(
        self,
        key: Hashable,
        fn: Callable,
        /,
        *args: Any,
        priority: int = SELECTED_COURSE,
        **kwargs: Any,
    ) -> Future:
        """Submit one keyed unit, reusing and reprioritising a queued/running future.

        A key is process-local and deliberately has no cancellation semantics.  If the same work is
        requested while it is queued, its heap entry is replaced with the newest priority.  If it is
        already running, the current call continues normally and receives the same future.  Entries
        are removed once complete, so a later request can retry a failed unit or observe a new
        geometry revision.
        """
        key = _hashable_key(key)
        with self._condition:
            current = self._keyed.get(key)
            if current is not None:
                version, future, _fn, _fn_args, _fn_kwargs = current
                if not future.done():
                    if not future.running():
                        self._reprioritize_locked(key, int(priority), version=version)
                    return future
                # The worker's done callback normally removes this entry.  The defensive cleanup
                # keeps a completed future from blocking a new retry if the callback is in flight.
                self._keyed.pop(key, None)
            # Keep lookup, key reservation and heap insertion under this same condition.  Calling
            # ``_submit`` after releasing it allowed two concurrent callers to both observe no key.
            return self._submit_locked(fn, args, kwargs, priority=int(priority), key=key)

    def reprioritize(self, key: Hashable, priority: int) -> bool:
        """Raise/lower a queued keyed unit without interrupting a running call."""
        key = _hashable_key(key)
        with self._condition:
            current = self._keyed.get(key)
            if current is None:
                return False
            version, future, _fn, _fn_args, _fn_kwargs = current
            if future.done() or future.running():
                return False
            self._reprioritize_locked(key, int(priority), version=version)
            self._condition.notify()
            return True

    def _reprioritize_locked(self, key: Hashable, priority: int, *, version: int) -> None:
        current = self._keyed.get(key)
        if current is None or current[0] != version:
            return
        future = current[1]
        fn = current[2]
        args = current[3]
        kwargs = current[4]
        replacement_version = next(self._entry_version)
        self._keyed[key] = (replacement_version, future, fn, args, kwargs)
        heapq.heappush(
            self._queue,
            (int(priority), next(self._sequence), replacement_version, future, fn, args, kwargs, key),
        )

    def _submit(
        self,
        fn: Callable,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        priority: int,
        key: Hashable | None,
    ) -> Future:
        with self._condition:
            return self._submit_locked(fn, args, kwargs, priority=priority, key=key)

    def _submit_locked(
        self,
        fn: Callable,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        priority: int,
        key: Hashable | None,
    ) -> Future:
        """Insert a unit; the caller holds ``_condition``."""
        if self._closed:
            raise RuntimeError("executor is shut down")
        future: Future = Future()
        version = next(self._entry_version)
        if key is not None:
            self._keyed[key] = (version, future, fn, args, kwargs)
        heapq.heappush(
            self._queue,
            (int(priority), next(self._sequence), version, future, fn, args, kwargs, key),
        )
        if len(self._threads) < self._max_workers:
            thread = threading.Thread(target=self._run, name=f"{self._name}-{len(self._threads)}", daemon=True)
            self._threads.append(thread)
            thread.start()
        self._condition.notify()
        if key is not None:
            future.add_done_callback(
                lambda completed, keyed=key, entry_version=version: self._key_done(
                    keyed, entry_version, completed
                )
            )
        return future

    def _key_done(self, key: Hashable, version: int, future: Future) -> None:
        with self._condition:
            current = self._keyed.get(key)
            if current is not None and current[:2] == (version, future):
                self._keyed.pop(key, None)
            self._condition.notify_all()

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._queue)
                if not self._queue:
                    return
                _priority, _sequence, version, future, fn, args, kwargs, key = heapq.heappop(self._queue)
                if key is not None:
                    current = self._keyed.get(key)
                    if current is None or current[:2] != (version, future):
                        # A keyed unit was reprioritised.  Its old heap entry is stale.
                        continue
            if not future.set_running_or_notify_cancel():
                continue
            token = _CURRENT_PRIORITY.set(_priority)
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                future.set_exception(exc)
            else:
                future.set_result(result)
            finally:
                _CURRENT_PRIORITY.reset(token)

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        with self._condition:
            self._closed = True
            if cancel_futures:
                for _priority, _sequence, _version, future, _fn, _args, _kwargs, _key in self._queue:
                    future.cancel()
                self._queue.clear()
            self._condition.notify_all()
        if wait:
            for thread in self._threads:
                thread.join()


def _hashable_key(value: Hashable) -> Hashable:
    """Fail early with a useful error when a caller accidentally supplies a mutable key."""
    try:
        hash(value)
    except TypeError as exc:
        raise TypeError("priority work key must be hashable") from exc
    return value
