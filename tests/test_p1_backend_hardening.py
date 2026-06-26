"""P1 backend hardening (cross-review remediation doc):

- P1-6 geometry subprocess gets a timeout; the on-demand sync uses per-hole locks
  so one hung node can't wedge geometry for every other hole.
- P1-8 a single live-round event batch is length-capped; an oversized request body
  is refused by its Content-Length before any handler buffers it.
- P1-9 sanitize_safe_meta redacts a secret VALUE while keeping its (legible) key.
"""

from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from pydantic import ValidationError

from ai_caddie.connectors.garmin_cn import sanitize_safe_meta
from ai_caddie.geometry import batch_prodgeometry_course as batch
from ai_caddie.geometry import geometry_sync
from server_v2.models import LiveRoundEventBatchRequest


class SanitizeSafeMetaTests(unittest.TestCase):
    def test_secret_keys_redact_the_value_and_keep_the_key(self) -> None:
        meta = {
            "cookie": "SESSIONID=abc123",
            "X-CSRF-Token": "deadbeef",
            "nested": {"authorization": "Bearer zzz", "courseId": 42},
            "courseName": "Beijing Palace",
        }
        out = sanitize_safe_meta(meta)
        # secret-named keys keep their name but lose their value
        self.assertEqual(out["cookie"], "[redacted]")
        self.assertEqual(out["X-CSRF-Token"], "[redacted]")
        self.assertEqual(out["nested"]["authorization"], "[redacted]")
        # non-secret fields are untouched
        self.assertEqual(out["nested"]["courseId"], 42)
        self.assertEqual(out["courseName"], "Beijing Palace")
        # and the literal secret never survives anywhere in the output
        rendered = repr(out)
        self.assertNotIn("abc123", rendered)
        self.assertNotIn("deadbeef", rendered)
        self.assertNotIn("Bearer zzz", rendered)


class EventBatchSizeCapTests(unittest.TestCase):
    @staticmethod
    def _event(index: int) -> dict:
        return {
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": f"e{index}",
            "roundId": "r1",
            "timestamp": "2026-06-26T00:00:00Z",
            "hole": 1,
            "kind": "score",
            "payload": {"strokes": 4},
        }

    def test_batch_within_cap_is_accepted(self) -> None:
        req = LiveRoundEventBatchRequest(roundId="r1", events=[self._event(0)])
        self.assertEqual(len(req.events), 1)

    def test_batch_over_cap_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            LiveRoundEventBatchRequest(roundId="r1", events=[self._event(i) for i in range(5001)])


class GeometrySubprocessTimeoutTests(unittest.TestCase):
    def test_run_raises_on_timeout_when_not_allowed_to_fail(self) -> None:
        with mock.patch(
            "ai_caddie.geometry.batch_prodgeometry_course.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["node"], timeout=1.0, output="partial"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                batch.run(["node", "x.js"])
        self.assertIn("timed out", str(ctx.exception))

    def test_run_returns_failure_on_timeout_when_allowed_to_fail(self) -> None:
        with mock.patch(
            "ai_caddie.geometry.batch_prodgeometry_course.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["node"], timeout=1.0),
        ):
            ok, out = batch.run(["node", "x.js"], allow_fail=True)
        self.assertFalse(ok)
        self.assertIn("timed out", out)

    def test_run_passes_a_default_timeout_to_subprocess(self) -> None:
        completed = mock.Mock(returncode=0, stdout="{}")
        with mock.patch(
            "ai_caddie.geometry.batch_prodgeometry_course.subprocess.run",
            return_value=completed,
        ) as run_mock:
            batch.run(["node", "x.js"])
        self.assertEqual(run_mock.call_args.kwargs["timeout"], batch.GEOMETRY_SUBPROCESS_TIMEOUT_S)


class GeometryPerHoleLockTests(unittest.TestCase):
    def test_same_hole_shares_a_lock_distinct_holes_do_not(self) -> None:
        same_a = geometry_sync._hole_lock(100, 1)
        same_b = geometry_sync._hole_lock(100, 1)
        other_hole = geometry_sync._hole_lock(100, 2)
        other_course = geometry_sync._hole_lock(200, 1)
        self.assertIs(same_a, same_b)  # same (gid, hole) → one lock (serialize the same hole)
        self.assertIsNot(same_a, other_hole)  # different hole → free to proceed concurrently
        self.assertIsNot(same_a, other_course)


class RequestBodySizeCapTests(unittest.TestCase):
    def _client(self):
        from fastapi.testclient import TestClient
        from server_v2 import main

        return TestClient(main.app), main

    def test_oversized_body_is_rejected_with_413_before_routing(self) -> None:
        client, main = self._client()
        with mock.patch.object(main, "MAX_REQUEST_BODY_BYTES", 8):
            resp = client.post("/api/v2/players/me/rounds", json={"events": [1, 2, 3, 4]})
        self.assertEqual(resp.status_code, 413)

    def test_normal_request_passes_the_size_guard(self) -> None:
        client, _ = self._client()
        resp = client.get("/api/v2/health")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
