"""Regression tests for the codex-review batch-1 security/validation hardening (#1/#2/#5/#6/#7/#11).

unittest on purpose — CI runs ``python -m unittest discover``.
"""

from __future__ import annotations

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from server_v2 import main
from server_v2.main import app

_ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret", "AI_CADDIE_SECURITY_PROFILE": "private"}
_ADMIN_HEADER = {"x-ai-caddie-admin-token": "admin-secret"}


class CodexSec1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    # #1 — geometry source_ref is private (owner shot routes); gate it under a private profile.
    def test_geometry_source_ref_requires_auth_but_plain_geometry_stays_public(self) -> None:
        with mock.patch.dict("os.environ", _ADMIN_ENV):
            # WITH source_ref + no token -> 401 (the owner's shot routes are protected).
            denied = self.client.get("/api/v2/geometry/hole/31795/4?source_ref=900001:4")
            self.assertEqual(denied.status_code, 401)
            # WITH source_ref + admin token -> auth passes (NOT 401; data may 200/empty).
            allowed = self.client.get(
                "/api/v2/geometry/hole/31795/4?source_ref=900001:4", headers=_ADMIN_HEADER
            )
            self.assertNotEqual(allowed.status_code, 401)
            # WITHOUT source_ref -> pure course geometry stays public (no token, not 401).
            public = self.client.get("/api/v2/geometry/hole/31795/4")
            self.assertNotEqual(public.status_code, 401)

    # #6 — out-of-range / oversized query params are rejected (422), not silently processed.
    def test_geometry_landing_radius_out_of_range_rejected(self) -> None:
        with mock.patch.dict("os.environ", _ADMIN_ENV):
            resp = self.client.get(
                "/api/v2/geometry/hole/31795/4?landing_radius_m=99999", headers=_ADMIN_HEADER
            )
            self.assertEqual(resp.status_code, 422)

    def test_prep_too_many_holes_rejected(self) -> None:
        with mock.patch.dict("os.environ", _ADMIN_ENV):
            qs = "&".join(f"holes={h}" for h in range(1, 60))
            resp = self.client.get(f"/api/v2/courses/31795/prep?{qs}", headers=_ADMIN_HEADER)
            self.assertEqual(resp.status_code, 422)

    # #5 — a giant ingest events list is rejected before processing.
    def test_ingest_events_over_cap_rejected(self) -> None:
        with mock.patch.dict("os.environ", _ADMIN_ENV):
            body = {"events": [{"k": "score"}] * 6000}
            resp = self.client.post(
                "/api/v2/players/me/rounds", json=body, headers=_ADMIN_HEADER
            )
            self.assertEqual(resp.status_code, 422)

    # #7 — an oversized caddie-decision context is rejected.
    def test_decision_oversized_context_rejected(self) -> None:
        with mock.patch.dict("os.environ", _ADMIN_ENV):
            body = {"shotType": "tee", "context": {"blob": "x" * 200_000}}
            resp = self.client.post("/api/v2/caddie/decision", json=body, headers=_ADMIN_HEADER)
            self.assertEqual(resp.status_code, 422)

    # #2 — a second concurrent Garmin sync is rejected (409) rather than racing the in-flight one.
    def test_concurrent_sync_is_rejected(self) -> None:
        with mock.patch.dict("os.environ", _ADMIN_ENV):
            self.assertTrue(main._SYNC_LOCK.acquire(blocking=False))
            try:
                resp = self.client.post("/api/v2/sync/garmin", headers=_ADMIN_HEADER)
                self.assertEqual(resp.status_code, 409)
            finally:
                main._SYNC_LOCK.release()


if __name__ == "__main__":
    unittest.main()
