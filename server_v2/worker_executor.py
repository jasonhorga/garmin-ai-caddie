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


def _run_worker(process: subprocess.Popen[bytes], function: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    payload = pickle.dumps((function, args, kwargs), protocol=5)
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(struct.pack("!Q", len(payload)) + payload)
    process.stdin.flush()
    size = struct.unpack("!Q", _read_exact(process.stdout, 8))[0]
    response = _read_exact(process.stdout, size)
    try:
        status, value = pickle.loads(response)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("worker process returned invalid payload") from exc
    if status == "error":
        raise value
    return value


class SubprocessExecutor:
    """A bounded queue with one persistent clean Python process per lane worker."""

    def __init__(self, max_workers: int, *, max_tasks_per_child: int | None = None) -> None:
        del max_tasks_per_child
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
        try:
            process = subprocess.Popen(
                [sys.executable, "-u", "-m", "server_v2.worker_process"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_worker_environment(),
                cwd=Path.cwd(),
            )
            while True:
                task = self._queue.get()
                if task is None:
                    return
                future, function, args, kwargs = task
                if future.cancelled():
                    continue
                try:
                    future.set_result(_run_worker(process, function, args, kwargs))
                except BaseException as exc:  # noqa: BLE001
                    future.set_exception(exc)
        finally:
            if process is not None:
                process.terminate()
                process.wait(timeout=5)

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
