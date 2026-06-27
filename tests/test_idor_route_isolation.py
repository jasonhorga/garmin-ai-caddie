"""Phase 1c — the four mobile/caddie AGGREGATOR reads are admin-only.

The mobile round package, the mobile course package, the reconciliation-GET, and the
caddie-context read aggregate per-round data from shared, UNPARTITIONED stores keyed by
round_id / source_ref — the mobile event log, weather snapshots, and the annotation store.
Threading the resolved player_id isolates only the player-keyed HistoryData half, NOT those
stores, so opening these routes to a family member would let them read the owner's round
data (weather, hand-written notes, event activity / sequence) by a guessed round_id. They
therefore stay admin-only until the stores are per-user partitioned (Phase 2).

This module proves, through the REAL admin-gate middleware (TestClient, ADMIN_ENV set so the
gate is fully active), that a family-member capability token AND an anonymous caller are both
rejected (401) on all four routes. That the 401 is GATING and not a broken route is proven
for the owner (admin → 200, builder threads player_id="me") in
test_server_v2_admin_protection (MobilePackageAdminOnlyTests /
ReconciliationAndCaddieContextAdminOnlyTests), which mocks the builders.

The genuinely player-keyed reads (history / stats / reports / prep / mobile course-options)
remain member-accessible and are isolation-tested in test_player_side_isolation and
test_players_api_auth (PlayerScopeDataIsolationTests).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.caddie.mobile_live import _event_cursor, mobile_event_log
from ai_caddie.history.history import OWNER_ID
from ai_caddie.rounds import players
from server_v2.main import app


ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}

_FIXTURE_ROUND_ID = "900001"
_FIXTURE_GLOBAL_ID = 31795

# The four aggregator reads that must NOT be reachable by a per-player token in Phase 1c.
_AGGREGATOR_ROUTES = [
    ("round package", f"/api/v2/mobile/rounds/{_FIXTURE_ROUND_ID}/package"),
    ("course package", f"/api/v2/mobile/courses/{_FIXTURE_GLOBAL_ID}/package?round_id=test-round-1"),
    ("reconciliation", "/api/v2/mobile/rounds/test-round-1/reconciliation"),
    ("caddie context", f"/api/v2/caddie/context?source_ref={_FIXTURE_ROUND_ID}:1&shot_type=approach"),
]


class AggregatorRoutesAreAdminOnlyTests(unittest.TestCase):
    """A family-member token (and an anonymous caller) must be rejected by the real admin
    gate on every per-round aggregator read — they are owner-only until Phase 2."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patch = mock.patch.object(players, "ROOT", self.root)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.addCleanup(self._tmp.cleanup)
        self.member_token = players.create_player("Bob", root=self.root)["token"]
        self.client = TestClient(app)

    def test_member_and_anonymous_are_401_on_every_aggregator_route(self) -> None:
        # The 401 fires at the middleware gate (before any builder), so this needs no fixture
        # data: a valid per-player token does not bypass the gate on a non-player-scoped route.
        with mock.patch.dict("os.environ", ADMIN_ENV):
            for label, url in _AGGREGATOR_ROUTES:
                member = self.client.get(
                    url, headers={"Authorization": f"Bearer {self.member_token}"}
                )
                anon = self.client.get(url)
                self.assertEqual(
                    member.status_code, 401,
                    f"a family-member token must be 401 on the {label} read ({url})",
                )
                self.assertEqual(
                    anon.status_code, 401,
                    f"an anonymous caller must be 401 on the {label} read ({url})",
                )


class EventCursorDefenseInDepthTests(unittest.TestCase):
    """Defense-in-depth: _event_cursor is gated to the owner so that even if a future change
    re-exposed the package to a non-owner before MOBILE_ROOT is partitioned, the unpartitioned
    event log's sequence / pending-count metadata could not leak."""

    def test_non_owner_player_gets_empty_cursor_without_reading_the_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = mobile_event_log(root)
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(
                '{"roundId": "900001", "serverSequence": 7, "event": {"type": "score"}}\n',
                encoding="utf-8",
            )
            owner_cursor = _event_cursor("900001", root=root, player_id=OWNER_ID)
            member_cursor = _event_cursor("900001", root=root, player_id="p_member")

        self.assertEqual(owner_cursor["serverSequence"], 7, "owner reads the real event log")
        self.assertEqual(
            member_cursor["serverSequence"], 0,
            "a non-owner must not learn the round's event sequence from the shared log",
        )
        self.assertEqual(member_cursor.get("pendingEventCount"), 0)
        self.assertNotIn("replayEndpoint", member_cursor)


if __name__ == "__main__":
    unittest.main()
