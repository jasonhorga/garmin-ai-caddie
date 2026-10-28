"""J9 backend-facing Web contracts: corrections, Garmin import, and clean share links."""
from __future__ import annotations

import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players
from ai_caddie.connectors import session_material
from server_v2 import session as session_api, history_round_detail, annotations
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
    @staticmethod
    def _current_generation(token_dir: Path) -> Path:
        name = (token_dir / session_material.CURRENT_FILE).read_text(encoding="ascii").strip()
        return token_dir / session_material.GENERATIONS_DIR / name

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
            mock.patch.object(session_api, "SESSION_ROOT", self.root),
            mock.patch.object(history_round_detail, "ANNOTATION_ROOT", self.root),
            mock.patch.object(annotations, "ANNOTATION_ROOT", self.root),
            mock.patch.dict(
                os.environ,
                {"AI_CADDIE_ADMIN_TOKEN": ADMIN, "AI_CADDIE_DATA_MODE": "local"},
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

    def test_j9_2_web_correction_uses_the_same_append_only_player_rule(self) -> None:
        # J3.1 golden: raw par-4 hole=4 strokes/2 putts/0 penalty. Setting penalty to 1
        # changes the projected shotmap to 1, appending a 0 -> 1 audit entry. No raw byte
        # changes, and replaying the original ingest must not erase the correction.
        for client in ("web", "app"):
            with self.subTest(client=client):
                round_id = self._ingest(self.alice, f"{client} correction course")
                raw_files = [p for p in (self.root / "data" / "players" / self.alice["id"]).rglob("*.json")
                             if p.parent.name in {"scorecards", "shots"}]
                self.assertTrue(raw_files)
                raw_before = {p: p.read_bytes() for p in raw_files}
                headers = self._auth(self.alice["token"])
                correction = self.client.post(
                    f"/api/v2/history/rounds/{round_id}/corrections", headers=headers,
                    json={"op": "setHolePenalty", "hole": 1, "value": 1,
                          "clientMutationId": f"{client}-c-1"},
                )
                self.assertEqual(correction.status_code, 201, correction.text)
                for read_stage in ("immediate", "after ingest replay"):
                    with self.subTest(stage=read_stage):
                        if read_stage == "after ingest replay":
                            self.assertEqual(self._ingest(self.alice, f"{client} correction course"), round_id)
                        shotmap = self.client.get(
                            f"/api/v2/history/rounds/{round_id}/holes/1/shotmap?includeImage=false",
                            headers=headers,
                        )
                        self.assertEqual(shotmap.status_code, 200)
                        self.assertTrue(shotmap.json()["found"])
                        self.assertEqual(shotmap.json()["manualPenalty"], 1)
                        detail = self.client.get(f"/api/v2/history/rounds/{round_id}", headers=headers)
                        self.assertEqual(detail.status_code, 200)
                        self.assertEqual([(h["score"], h["putts"]) for h in detail.json()["scorecard"]], [(4, 2)])
                        log = self.client.get(f"/api/v2/history/rounds/{round_id}/correction-log", headers=headers)
                        self.assertEqual(log.status_code, 200)
                        self.assertEqual([(e["hole"], e["op"], e["before"], e["after"])
                                          for e in log.json()["entries"]], [(1, "penalty", 0, 1)])
                        self.assertEqual({p: p.read_bytes() for p in raw_before}, raw_before)
                for other in (ADMIN_HEADER, self._auth(self.bob["token"])):
                    denied = self.client.get(f"/api/v2/history/rounds/{round_id}/correction-log", headers=other)
                    self.assertEqual(denied.status_code, 404)

    def test_j9_3_failed_garmin_session_import_does_not_overwrite_existing_material(self) -> None:
        cookie_sample = "JWT_WEB=" + secrets.token_hex(16)
        csrf_sample = secrets.token_hex(16)
        good = {"webSessionHeader": f"Cookie: {cookie_sample}", "antiForgeryValue": csrf_sample}
        for label, path, headers, token_dir in [
            ("owner", "/api/v2/sync/garmin/session", ADMIN_HEADER, self.root / ".garmin_tokens"),
            ("member", f"/api/v2/players/{self.alice['id']}/sync/garmin/session",
             self._auth(self.alice["token"]), self.root / "data" / "players" / self.alice["id"] / ".garmin_tokens"),
        ]:
            with self.subTest(player=label):
                response = self.client.post(path, headers=headers, json=good)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["state"], "stored")
                generation = self._current_generation(token_dir)
                cookie, csrf = generation / "web_cookie.txt", generation / "csrf.txt"
                # Handwritten golden for the imported material; header prefix is not stored.
                self.assertEqual((cookie.read_text(), csrf.read_text()), (cookie_sample + "\n", csrf_sample + "\n"))
                before = (cookie.read_bytes(), csrf.read_bytes())
                for name, change in [
                    ("multiline cookie", {"webSessionHeader": "JWT_WEB=replacement\nextra=value"}),
                    ("no equals", {"webSessionHeader": "replacement-without-equals"}),
                    ("multiline csrf", {"antiForgeryValue": "replacement\ncsrf"}),
                    ("prefix only", {"webSessionHeader": "Cookie:"}),
                    ("invalid source", {"source": "username_password"}),
                    ("long invalid", {"webSessionHeader": "invalid" * 8192}),
                ]:
                    with self.subTest(input=name):
                        response = self.client.post(path, headers=headers, json={**good, **change})
                        self.assertEqual(response.status_code, 422)
                        self.assertEqual((cookie.read_bytes(), csrf.read_bytes()), before)

    def test_j9_3_session_material_failure_rolls_back_replacement_files(self) -> None:
        """A failure after validation must leave the previously working session untouched."""
        token_dir = self.root / ".garmin_tokens"
        token_dir.mkdir(parents=True)
        cookie = token_dir / "web_cookie.txt"
        csrf = token_dir / "csrf.txt"
        cookie.write_text("JWT_WEB=existing-cookie\n", encoding="utf-8")
        csrf.write_text("existing-csrf\n", encoding="utf-8")
        before = (cookie.read_bytes(), csrf.read_bytes())
        with mock.patch.object(
            session_material,
            "write_connector_status",
            side_effect=RuntimeError("status store unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                session_material.save_garmin_cn_web_session(
                    web_session_header="Cookie: JWT_WEB=replacement",
                    anti_forgery_value="connect-csrf-token: replacement-csrf",
                    root=self.root,
                )
        self.assertEqual((cookie.read_bytes(), csrf.read_bytes()), before)

    def _create_share_url(self, round_id: str) -> str:
        # /p/<member-token> is a full member login, not a share link. The API share URL is
        # intentionally separate so recipients never receive a player capability.
        response = self.client.post(
            f"/api/v2/history/rounds/{round_id}/share", headers=self._auth(self.alice["token"]),
        )
        self.assertEqual(response.status_code, 201, "read-only share view is not implemented")
        url = response.json().get("url")
        self.assertIsInstance(url, str)
        self.assertTrue(url)
        return url

    def test_j9_5_share_link_is_anonymous_read_only_and_round_scoped(self) -> None:
        round_id = self._ingest(self.alice, "Shared fixture round")
        other_id = self._ingest(self.alice, "Unshared fixture round")
        url = self._create_share_url(round_id)
        # The recipient has no member bearer, admin header or browser login cookie.
        recipient = TestClient(app)
        try:
            response = recipient.get(url)
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["found"])
            self.assertEqual(str(payload["round"]["id"]), round_id)
            self.assertEqual(payload["round"]["score"], 4)
            self.assertNotIn("Unshared fixture round", response.text)
            for key in ("diagnostics", "safeMeta", "scorecardCount", "localPath"):
                self.assertNotIn(key, response.text)
            guessed_url = (url.replace(round_id, other_id) if round_id in url else
                           url + ("&" if "?" in url else "?") + f"roundId={other_id}")
            foreign = recipient.get(guessed_url)
            self.assertIn(foreign.status_code, {200, 403, 404})
            if foreign.status_code == 200:
                self.assertEqual(str(foreign.json()["round"]["id"]), round_id)
            self.assertNotIn("Unshared fixture round", foreign.text)
            write_url = urlsplit(url)
            write_url = write_url._replace(path=write_url.path + "/corrections").geturl()
            write = recipient.post(write_url, json={
                "op": "setHolePenalty", "hole": 1, "value": 1, "clientMutationId": "share-write",
            })
            self.assertIn(write.status_code, {403, 405})
        finally:
            recipient.close()
        # Neither a rejected share write nor the read changed the owner's round.
        log = self.client.get(f"/api/v2/history/rounds/{round_id}/correction-log",
                              headers=self._auth(self.alice["token"]))
        self.assertEqual(log.json()["entries"], [])


if __name__ == "__main__":
    unittest.main()
