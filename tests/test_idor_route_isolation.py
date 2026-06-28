"""Phase 2 — the four mobile/caddie AGGREGATOR reads are now open to family MEMBERS.

The mobile round package, the mobile course package, the reconciliation-GET, and the
caddie-context read aggregate per-round data from shared, UNPARTITIONED stores keyed by
round_id / source_ref — the mobile event log, weather snapshots, and the annotation store.
Phase 1c kept them admin-only because threading the resolved player_id isolated only the
player-keyed HistoryData half. Phase 2 made every evidence READ loader player-aware (each
short-circuits to empty for a non-owner via ``evidence_root``) and the response builders now
thread the resolved player_id down to every one — so a member who guesses an owner round_id
gets a 200 with NO owner evidence. The routes are therefore opened to members.

This module proves, through the REAL admin-gate middleware (TestClient, ADMIN_ENV set so the
gate is fully active), that a family-member capability token now REACHES each builder (200)
while an anonymous caller is still rejected (401) on all four routes. The builders are mocked
here so this stays a pure GATE test (instant, offline); the isolation BELOW the builder
(member sees no owner evidence on the real builders) is proven in
test_aggregator_route_isolation, and the owner-threads-player_id="me" path in
test_server_v2_admin_protection.

The genuinely player-keyed reads (history / stats / reports / prep / mobile course-options)
remain member-accessible and are isolation-tested in test_player_side_isolation and
test_players_api_auth (PlayerScopeDataIsolationTests).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import Mock

from fastapi.testclient import TestClient

from ai_caddie.caddie.mobile_live import _event_cursor, mobile_event_log
from ai_caddie.history.history import OWNER_ID
from ai_caddie.rounds import players
from server_v2.main import app
from tests.test_server_v2_admin_protection import (
    _caddie_context_response,
    _mobile_package_response,
    _reconciliation_response,
)


ADMIN_ENV = {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}

_FIXTURE_ROUND_ID = "900001"
_FIXTURE_GLOBAL_ID = 31795

# The four aggregator reads + the server_v2.main builder each routes to and a canned response.
_AGGREGATOR_CASES = [
    (
        "round package",
        f"/api/v2/mobile/rounds/{_FIXTURE_ROUND_ID}/package",
        "build_mobile_round_package_response",
        _mobile_package_response,
    ),
    (
        "course package",
        f"/api/v2/mobile/courses/{_FIXTURE_GLOBAL_ID}/package?round_id=test-round-1",
        "build_mobile_course_package_response",
        _mobile_package_response,
    ),
    (
        "reconciliation",
        "/api/v2/mobile/rounds/test-round-1/reconciliation",
        "reconcile_mobile_round_response",
        _reconciliation_response,
    ),
    (
        "caddie context",
        f"/api/v2/caddie/context?source_ref={_FIXTURE_ROUND_ID}:1&shot_type=approach",
        "build_caddie_context_response",
        _caddie_context_response,
    ),
]


class AggregatorRoutesOpenToMembersTests(unittest.TestCase):
    """A family-member token now REACHES each per-round aggregator builder (200) through the
    real admin gate; an anonymous caller is still rejected (401) and the builder never runs."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patch = mock.patch.object(players, "ROOT", self.root)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.addCleanup(self._tmp.cleanup)
        self.member_token = players.create_player("Bob", root=self.root)["token"]
        self.client = TestClient(app)

    def test_member_token_now_reaches_every_aggregator_builder(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            for label, url, builder, canned in _AGGREGATOR_CASES:
                handler = Mock(return_value=canned())
                with mock.patch(f"server_v2.main.{builder}", handler):
                    resp = self.client.get(
                        url, headers={"Authorization": f"Bearer {self.member_token}"}
                    )
                self.assertEqual(
                    resp.status_code, 200,
                    f"a family-member token must now reach the {label} read ({url}): {resp.text[:200]}",
                )
                handler.assert_called_once()

    def test_anonymous_is_still_401_on_every_aggregator_route(self) -> None:
        with mock.patch.dict("os.environ", ADMIN_ENV):
            for label, url, builder, canned in _AGGREGATOR_CASES:
                handler = Mock(return_value=canned())
                with mock.patch(f"server_v2.main.{builder}", handler):
                    anon = self.client.get(url)
                self.assertEqual(
                    anon.status_code, 401,
                    f"an anonymous caller must still be 401 on the {label} read ({url})",
                )
                handler.assert_not_called()


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
