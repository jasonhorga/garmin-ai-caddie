"""Keep the event loop responsive while prep checks disconnects between CPU/IO stages."""
import asyncio
import threading
from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import Response

from ai_caddie.courses.prep_work import cancellation
from .timing import mark


async def run_prep(request: Request, build: Callable):
    cancelled = threading.Event()

    def work():
        with cancellation(cancelled):
            return build()

    async def watch_disconnect():
        # is_disconnected() cancels its own receive scope and can lose the disconnect under
        # BaseHTTPMiddleware's receive_or_disconnect task group. Own one uninterrupted receive
        # instead. This GET route has no request body consumer to compete with the watcher.
        while True:
            message = await request.receive()
            if message["type"] == "http.disconnect":
                cancelled.set()
                mark("prep_cancelled")
                return

    worker = asyncio.create_task(asyncio.to_thread(work))
    watcher = asyncio.create_task(watch_disconnect())
    try:
        done, _ = await asyncio.wait({worker, watcher}, return_when=asyncio.FIRST_COMPLETED)
        if watcher in done:
            await watcher  # Propagate receive failures; only an actual disconnect means 499.
            return Response(status_code=499)
        return await worker
    except asyncio.CancelledError:
        mark("prep_cancelled")
        raise
    finally:
        # Cancelling a thread's await cannot stop CPU work. Signal the actual builder too.
        cancelled.set()
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        # Drain late errors without retaining this request or an unobserved task exception.
        def consume(task):
            if not task.cancelled():
                task.exception()
        worker.add_done_callback(consume)
