from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.rounds import players
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
        self.assertLessEqual(set(readiness.json().keys()), {"schema", "status", "authenticated", "runtimeStatus", "evidenceStatus", "reason", "checks"})
        self.assertEqual(sync.json(), {"schema": "ai-caddie-sync-status-v2", "status": "ok"})
        self.assertEqual(readiness.json()["runtimeStatus"], "ready")
        for term in _OWNER_LEAK_TERMS:
            self.assertNotIn(term, readiness.text)
            self.assertNotIn(term, sync.text)

    def test_member_token_gets_liveness_only(self) -> None:
        # A *resolved* non-owner member token (Phase 1b made members resolve) must receive the
        # same liveness stub as an anonymous caller on BOTH owner-operational endpoints —
        # sync/status AND readiness — so no owner counts / snapshot id / geometry deps /
        # last-run / owner-package detail leaks to a family member, and the heavy owner
        # readiness package is never built for a member.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(players, "ROOT", root):
                member = players.create_player("FamilyMember", root=root)
                client = TestClient(app)
                hdrs = {"Authorization": f"Bearer {member['token']}"}
                with patch.dict("os.environ", {"AI_CADDIE_SECURITY_PROFILE": "private",
                                               "AI_CADDIE_ADMIN_TOKEN": "admin-secret"}):
                    with patch("server_v2.main.build_readiness_response",
                               side_effect=AssertionError("owner readiness package built for a member")):
                        readiness = client.get("/api/v2/readiness", headers=hdrs)
                    sync = client.get("/api/v2/sync/status", headers=hdrs)
        self.assertEqual(readiness.status_code, 200)
        self.assertEqual(sync.status_code, 200)
        self.assertEqual(sync.json(), {"schema": "ai-caddie-sync-status-v2", "status": "ok"})
        self.assertEqual(readiness.json()["runtimeStatus"], "ready")
        self.assertLessEqual(set(readiness.json().keys()), {"schema", "status", "authenticated", "runtimeStatus", "evidenceStatus", "reason", "checks"})
        for term in _OWNER_LEAK_TERMS:
            self.assertNotIn(term, readiness.text)
            self.assertNotIn(term, sync.text)


if __name__ == "__main__":
    unittest.main()
