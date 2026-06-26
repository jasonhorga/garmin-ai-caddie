from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server_v2.main import app

# private profile + no admin token = an anonymous caller on a locked deploy.
_PRIVATE_NO_TOKEN = {"AI_CADDIE_SECURITY_PROFILE": "private", "AI_CADDIE_ADMIN_TOKEN": ""}
_OWNER_LEAK_TERMS = (
    "totalRounds",
    "roundId",
    "scorecardCount",
    "shotFileCount",
    "snapshotId",
    "geometryDependencies",
    "lastRun",
)


class ReadinessSyncStatusGatingTests(unittest.TestCase):
    """P0-2: ``/readiness`` and ``/sync/status`` stay publicly reachable (liveness)
    but must reveal no owner operational data to anonymous callers — and the
    anonymous path must NOT build the heavy owner package (no-auth DoS amplifier).
    The owner/admin full-payload path is exercised by test_server_v2_readiness.
    """

    def test_anonymous_caller_gets_liveness_only(self) -> None:
        client = TestClient(app)
        with patch.dict("os.environ", _PRIVATE_NO_TOKEN):
            # If the anonymous branch ever fell through to the real builder this
            # patch would blow up; instead the handler must short-circuit.
            with patch("server_v2.main.build_readiness_response", side_effect=AssertionError("owner package built for anon")):
                readiness = client.get("/api/v2/readiness")
            sync = client.get("/api/v2/sync/status")
        self.assertEqual(readiness.status_code, 200)
        self.assertEqual(sync.status_code, 200)
        self.assertLessEqual(set(readiness.json().keys()), {"schema", "status"})
        self.assertEqual(sync.json(), {"schema": "ai-caddie-sync-status-v2", "status": "ok"})
        for term in _OWNER_LEAK_TERMS:
            self.assertNotIn(term, readiness.text)
            self.assertNotIn(term, sync.text)


if __name__ == "__main__":
    unittest.main()
