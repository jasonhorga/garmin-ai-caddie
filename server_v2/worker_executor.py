"""Bounded executor backed by explicit worker subprocesses.

The API is launched through uvicorn's console entry point. A multiprocessing ``spawn`` child
would replay that entry point, so tasks use the dedicated ``server_v2.worker_process`` module.
"""

from __future__ import annotations

from concurrent.futures import Future
import pickle
import os
import queue
import struct
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable



def _worker_environment() -> dict[str, str]:
    environment = dict(os.environ)
    module_root = str(Path(__file__).resolve().parents[1])
    environment["PYTHONPATH"] = module_root + (
        (":" + environment["PYTHONPATH"]) if environment.get("PYTHONPATH") else ""
    )
    # A worker lane is already the bounded execution boundary.  Letting a child inherit one of
    # the API's lane counts creates an unbounded grandchild pool (and makes shutdown impossible).
    for key in tuple(environment):
        if key.startswith("AI_CADDIE_") and key.endswith("_PROCESSES"):
            environment[key] = "0"
    return environment


def _read_exact(stream: Any, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise RuntimeError("worker process exited without a response")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _run_worker(process: subprocess.Popen[bytes], function: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[Any, tuple[str, ...]]:
    payload = pickle.dumps((function, args, kwargs), protocol=5)
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(struct.pack("!Q", len(payload)) + payload)
    process.stdin.flush()
    size = struct.unpack("!Q", _read_exact(process.stdout, 8))[0]
    response = _read_exact(process.stdout, size)
    try:
        unpacked = pickle.loads(response)
        status, value = unpacked[:2]
        child_marks = unpacked[2] if len(unpacked) > 2 else ()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("worker process returned invalid payload") from exc
    if status == "ok":
        return value, tuple(str(stage) for stage in (child_marks or ()))
    if status == "error":
        raise value
    return value


class SubprocessExecutor:
    """A bounded queue with one persistent clean Python process per lane worker."""

    def __init__(self, max_workers: int, *, max_tasks_per_child: int | None = None,
                 task_timeout_seconds: float | None = None) -> None:
        self._max_tasks_per_child = max_tasks_per_child
        configured_timeout = os.environ.get("AI_CADDIE_WORKER_TASK_TIMEOUT_SECONDS", "120")
        try:
            configured_timeout_value = float(configured_timeout)
        except ValueError:
            configured_timeout_value = 120.0
        self._task_timeout_seconds = task_timeout_seconds if task_timeout_seconds is not None else configured_timeout_value
        self._queue: queue.Queue[Any] = queue.Queue()
        self._closed = False
        self._threads: list[threading.Thread] = []
        for index in range(max(1, int(max_workers))):
            thread = threading.Thread(target=self._worker, name=f"subprocess-worker-{index}", daemon=True)
            self._threads.append(thread)
            thread.start()

    def submit(self, function: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Future[Any]:
        future: Future[Any] = Future()
        if self._closed:
            future.set_exception(RuntimeError("worker executor is shut down"))
            return future
        self._queue.put((future, function, args, kwargs))
        return future

    def _worker(self) -> None:
        process: subprocess.Popen[bytes] | None = None
        task_count = 0

        def start() -> subprocess.Popen[bytes]:
            return subprocess.Popen(
                [sys.executable, "-u", "-m", "server_v2.worker_process"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                # stderr must never be a pipe that nobody drains: a verbose child otherwise
                # blocks on the OS pipe before it can send its response.
                stderr=None,
                env=_worker_environment(),
                cwd=Path.cwd(),
            )

        def stop(current: subprocess.Popen[bytes] | None) -> None:
            if current is None:
                return
            try:
                if current.poll() is None:
                    current.terminate()
                try:
                    current.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    current.kill()
                    current.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
            for stream in (current.stdin, current.stdout, current.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass

        try:
            while True:
                task = self._queue.get()
                if task is None:
                    return
                future, function, args, kwargs = task
                if future.cancelled():
                    continue
                try:
                    if process is None or process.poll() is not None:
                        stop(process)
                        process = start()
                        task_count = 0
                    result: list[Any] = []
                    error: list[BaseException] = []
                    done = threading.Event()

                    def invoke() -> None:
                        try:
                            result.append(_run_worker(process, function, args, kwargs))
                        except BaseException as exc:  # noqa: BLE001
                            error.append(exc)
                        finally:
                            done.set()

                    io_thread = threading.Thread(target=invoke, name="worker-io", daemon=True)
                    io_thread.start()
                    timeout = self._task_timeout_seconds
                    if timeout and timeout > 0 and not done.wait(timeout):
                        stop(process)
                        process = None
                        task_count = 0
                        future.set_exception(TimeoutError("worker task timed out"))
                        continue
                    done.wait()
                    if error:
                        stop(process)
                        process = None
                        task_count = 0
                        raise error[0]
                    value, stages = result[0]
                    # Future attributes are intentionally used as a tiny transport side-channel:
                    # the lane thread has no request ContextVar, while the API waiter does.
                    setattr(future, "worker_stages", stages)
                    future.set_result(value)
                    task_count += 1
                    if self._max_tasks_per_child and task_count >= self._max_tasks_per_child:
                        stop(process)
                        process = None
                        task_count = 0
                except BaseException as exc:  # noqa: BLE001
                    if not future.done():
                        future.set_exception(exc)
        finally:
            stop(process)

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        self._closed = True
        if cancel_futures:
            while True:
                try:
                    future, _function, _args, _kwargs = self._queue.get_nowait()
                except queue.Empty:
                    break
                future.cancel()
        for _thread in self._threads:
            self._queue.put(None)
        if wait:
            for thread in self._threads:
                thread.join(timeout=5)
