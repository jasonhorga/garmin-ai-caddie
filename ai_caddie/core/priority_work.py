"""Bounded shared work lanes; foreground holes overtake queued regional work."""

from __future__ import annotations

from concurrent.futures import Future
import heapq
import itertools
import threading
from typing import Any, Callable

FOREGROUND = 0
SELECTED_COURSE = 10
NEARBY = 20


class PriorityExecutor:
    """An executor with a priority queue and no per-request worker pools.

    Running provider/render calls finish normally. Only queued work is reordered,
    so callers should submit small windows rather than whole regions at once.
    """

    def __init__(self, max_workers: int, *, name: str) -> None:
        self._condition = threading.Condition()
        self._queue: list[tuple[int, int, Future, Callable, tuple, dict]] = []
        self._sequence = itertools.count()
        self._threads: list[threading.Thread] = []
        self._max_workers = max(1, max_workers)
        self._name = name
        self._closed = False

    def submit(self, fn: Callable, /, *args: Any, priority: int = SELECTED_COURSE,
               **kwargs: Any) -> Future:
        future: Future = Future()
        with self._condition:
            if self._closed:
                raise RuntimeError("executor is shut down")
            heapq.heappush(self._queue, (int(priority), next(self._sequence), future, fn, args, kwargs))
            if len(self._threads) < self._max_workers:
                thread = threading.Thread(target=self._run, name=f"{self._name}-{len(self._threads)}", daemon=True)
                self._threads.append(thread)
                thread.start()
            self._condition.notify()
        return future

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._queue)
                if not self._queue:
                    return
                _priority, _sequence, future, fn, args, kwargs = heapq.heappop(self._queue)
            if not future.set_running_or_notify_cancel():
                continue
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                future.set_exception(exc)
            else:
                future.set_result(result)

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        with self._condition:
            self._closed = True
            if cancel_futures:
                for _priority, _sequence, future, _fn, _args, _kwargs in self._queue:
                    future.cancel()
                self._queue.clear()
            self._condition.notify_all()
        if wait:
            for thread in self._threads:
                thread.join()
