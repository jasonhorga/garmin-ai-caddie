"""Hold package admission through response encoding, compression and the final body send."""
import asyncio
from contextlib import ExitStack
import re

from ai_caddie.core import priority_work

_PACKAGE = re.compile(r"^/api/v2/mobile/(?:rounds|courses)/[^/]+/package$")


class PackageAdmissionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not _PACKAGE.fullmatch(scope.get("path", "")):
            return await self.app(scope, receive, send)
        # ExitStack.close is idempotent: final send, disconnect, cancellation and exceptions all
        # release exactly once. BackgroundTasks after a completed body do not retain admission.
        with priority_work.foreground_scope():
            await self._respond(scope, receive, send)

    async def _respond(self, scope, receive, send):
        with ExitStack() as stack:
            stack.enter_context(priority_work.FOREGROUND_GATE.foreground())

            async def send_body(message):
                await send(message)
                if message["type"] == "http.response.body" and not message.get("more_body", False):
                    stack.close()

            messages = asyncio.Queue(maxsize=1)

            async def watch_receive():
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        stack.close()
                        await messages.put(message)
                        return
                    await messages.put(message)

            receiver = asyncio.create_task(watch_receive())
            try:
                await self.app(scope, messages.get, send_body)
            finally:
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)
