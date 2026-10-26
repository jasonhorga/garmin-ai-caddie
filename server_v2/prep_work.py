"""Keep the event loop responsive while prep checks disconnects between CPU/IO stages."""
import asyncio
import threading
from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import Response

from ai_caddie.courses.prep_work import PrepCancelled, cancellation
from .timing import mark


async def run_prep(request: Request, build: Callable):
    cancelled = threading.Event()

    def work():
        with cancellation(cancelled):
            try:
                return build()
            except PrepCancelled:
                return None

    worker = asyncio.create_task(asyncio.to_thread(work))
    try:
        while not worker.done():
            if await request.is_disconnected():
                mark("prep_disconnect")
                return Response(status_code=499)
            await asyncio.wait({worker}, timeout=0.05)
        return await worker
    finally:
        # Cancelling a thread's await cannot stop CPU work. Signal the actual builder too.
        cancelled.set()
        # Drain late errors without retaining this request or an unobserved task exception.
        def consume(task):
            if not task.cancelled():
                task.exception()
        worker.add_done_callback(consume)
