"""J9 backend-facing Web contracts: corrections, Garmin import, and clean share links."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players
from server_v2 import session as session_api
from server_v2.main import app


ADMIN = "j9-owner-admin"
ADMIN_HEADER = {"X-AI-Caddie-Admin-Token": ADMIN}


def _round_body(course: str) -> dict[str, object]:
    return {
        "events": [
            {"hole": 1, "kind": "score", "payload": {"strokes": 4}},
            {"hole": 1, "kind": "putt", "payload": {"putts": 2}},
        ],
        "meta": {"courseGlobalId": 41825, "courseName": course, "holePars": "4"},
    }


class J9WebApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
            mock.patch.object(session_api, "SESSION_ROOT", self.root),
            mock.patch.dict(
                os.environ,
                {"AI_CADDIE_ADMIN_TOKEN": ADMIN, "AI_CADDIE_DATA_MODE": "local_or_fixture"},
            ),
            mock.patch("server_v2.main._prepare_recent_bg"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        self.alice = players.create_player("Alice", root=self.root)
        self.bob = players.create_player("Bob", root=self.root)
        self.client = TestClient(app)

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _ingest(self, player: dict[str, str], course: str) -> str:
        response = self.client.post(
            f"/api/v2/players/{player['id']}/rounds",
            headers=self._auth(player["token"]),
            json=_round_body(course),
        )
        self.assertEqual(response.status_code, 201, response.text)
        return str(response.json()["id"])

    def test_web_correction_uses_the_same_append_only_player_rule(self) -> None:
        round_id = self._ingest(self.alice, "Alice correction course")
        correction = self.client.post(
            f"/api/v2/history/rounds/{round_id}/corrections",
            headers=self._auth(self.alice["token"]),
            json={"op": "setHolePenalty", "hole": 1, "value": 1, "clientMutationId": "web-c-1"},
        )
        self.assertEqual(correction.status_code, 201, correction.text)
        log = self.client.get(
            f"/api/v2/history/rounds/{round_id}/correction-log",
            headers=self._auth(self.alice["token"]),
        )
        self.assertEqual(log.status_code, 200, log.text)
        self.assertEqual(len(log.json()["entries"]), 1)

        # The same round reference is not an authorization capability for owner or another member.
        owner_log = self.client.get(
            f"/api/v2/history/rounds/{round_id}/correction-log", headers=ADMIN_HEADER
        )
        bob_log = self.client.get(
            f"/api/v2/history/rounds/{round_id}/correction-log",
            headers=self._auth(self.bob["token"]),
        )
        self.assertEqual(owner_log.status_code, 404, owner_log.text)
        self.assertEqual(bob_log.status_code, 404, bob_log.text)

        # Web must fail closed on unknown edit fields rather than silently dropping a correction.
        invalid = self.client.post(
            f"/api/v2/history/rounds/{round_id}/corrections",
            headers=self._auth(self.alice["token"]),
            json={"op": "setHolePenalty", "hole": 1, "value": 1, "unknown": "must-reject"},
        )
        self.assertEqual(invalid.status_code, 422, invalid.text)

    def test_failed_garmin_session_import_does_not_overwrite_existing_material(self) -> None:
        token_dir = self.root / ".garmin_tokens"
        token_dir.mkdir(parents=True)
        cookie = token_dir / "web_cookie.txt"
        csrf = token_dir / "csrf.txt"
        cookie.write_text("JWT_WEB=existing-cookie\n", encoding="utf-8")
        csrf.write_text("existing-csrf\n", encoding="utf-8")
        before = (cookie.read_bytes(), csrf.read_bytes())
        with mock.patch.object(
            session_api,
            "save_garmin_cn_web_session",
            side_effect=ValueError("provider rejected the replacement session"),
        ):
            response = self.client.post(
                "/api/v2/sync/garmin/session",
                headers=ADMIN_HEADER,
                json={
                    "webSessionHeader": "Cookie: JWT_WEB=replacement",
                    "antiForgeryValue": "connect-csrf-token: replacement-csrf",
                },
            )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual((cookie.read_bytes(), csrf.read_bytes()), before)

    def test_share_token_is_read_only_for_owner_controls_and_cannot_read_another_round(self) -> None:
        owner_round = self._ingest(self.alice, "Alice private round")
        bob_round = self._ingest(self.bob, "Bob private round")
        alice_auth = self._auth(self.alice["token"])

        own = self.client.get("/api/v2/history/rounds", headers=alice_auth)
        self.assertEqual(own.status_code, 200, own.text)
        self.assertIn("Alice private round", own.text)
        self.assertNotIn("Bob private round", own.text)

        # Guessing a different round id never turns a share token into an owner read.
        foreign = self.client.get(f"/api/v2/history/rounds/{bob_round}", headers=alice_auth)
        self.assertEqual(foreign.status_code, 404, foreign.text)
        self.assertNotIn("Bob private round", foreign.text)

        # A share bearer cannot reach owner management or owner reconciliation writes.
        self.assertEqual(self.client.get("/api/v2/admin/players", headers=alice_auth).status_code, 403)
        apply_response = self.client.post(
            f"/api/v2/mobile/rounds/{owner_round}/reconciliation/apply",
            headers=alice_auth,
            json={"suggestionIds": []},
        )
        self.assertEqual(apply_response.status_code, 403, apply_response.text)
        sync_status = self.client.get("/api/v2/sync/status", headers=alice_auth)
        self.assertEqual(sync_status.status_code, 200, sync_status.text)
        self.assertNotIn("scorecardCount", sync_status.text)
        self.assertNotIn("lastRun", sync_status.text)


if __name__ == "__main__":
    unittest.main()
