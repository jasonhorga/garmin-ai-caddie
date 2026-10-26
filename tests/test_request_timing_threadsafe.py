"""A late worker stage must not invalidate an in-progress timing serialization."""
import threading
import unittest
from unittest.mock import patch

from ai_caddie.core.request_timing import RequestTiming


class RequestTimingThreadTests(unittest.TestCase):
    def test_late_worker_mark_during_headers_and_logging(self):
        for operation in ("headers", "logging"):
            with self.subTest(operation=operation):
                iterating, added = threading.Event(), threading.Event()

                class InterleavedMarks(dict):
                    def items(self):
                        for item in super().items():
                            # If serialization is reading the live dict, make the worker add its
                            # stage before iteration resumes. Copying the dict avoids this race.
                            iterating.set()
                            if not added.wait(2):
                                raise AssertionError("late worker did not mark")
                            yield item

                timing = RequestTiming("fixture", marks=InterleavedMarks(initial=1.0))

                def worker():
                    if iterating.wait(2):
                        timing.mark("prep_late")
                    added.set()

                thread = threading.Thread(target=worker)
                thread.start()
                try:
                    if operation == "headers":
                        self.assertIn("initial;dur=1.0", timing.server_timing())
                    else:
                        with patch("ai_caddie.core.request_timing.logger.info") as log:
                            timing.finish(method="GET", path="/fixture", status=499)
                            log.assert_called_once()
                finally:
                    iterating.set()
                    thread.join(3)
                self.assertFalse(thread.is_alive())
