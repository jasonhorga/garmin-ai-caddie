"""J7.3 runtime secret-safety checks.

The values below are created at runtime and are never present in the repository fixtures. Each
test checks the actual response, captured logs, model prompt, and every durable file written by
the operation; this does not depend on source-text searches or repository fixtures.
"""
from __future__ import annotations

import logging
import os
import secrets
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.connectors.base import ConnectorRunResult
from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import players
from server_v2 import reports as reports_api
from server_v2 import session as session_api
import server_v2.main as main_api
from server_v2.main import app
from server_v2.sync_jobs import GarminSyncJobStore
from server_v2.sync_status import build_sync_status_response


ADMIN = "runtime-admin-secret"


def _data_tree_text(root: Path) -> str:
    chunks: list[str] = []
    if not root.exists():
        return ""
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        chunks.append(str(path.relative_to(root)))
        chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


class J7SecretTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
            mock.patch.object(session_api, "SESSION_ROOT", self.root),
            mock.patch.object(main_api, "SYNC_ROOT", self.root),
            mock.patch.object(reports_api, "REPORT_ROOT", self.root),
            mock.patch.object(main_api, "_prepare_recent_bg"),
            mock.patch.dict(
                os.environ,
                {"AI_CADDIE_ADMIN_TOKEN": ADMIN, "AI_CADDIE_DATA_MODE": "fixture"},
            ),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)
        # Every sensitive sample is fresh per test process; no fixture or source-text value is
        # reused as the oracle.
        self.cookie = f"JWT_WEB=runtime-cookie-{secrets.token_hex(8)}"
        self.csrf = f"runtime-csrf-{secrets.token_hex(8)}"
        self.password = f"runtime-garmin-password-{secrets.token_hex(8)}"
        self.private_path = str(self.root / "private" / f"runtime-secret-{secrets.token_hex(8)}.json")
        self.member_player = players.create_player("Member recipient", root=self.root)
        self.client = TestClient(app)
        self.log_messages: list[str] = []
        handler = logging.Handler()
        handler.emit = lambda record: self.log_messages.append(logging.Formatter().format(record))
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)

    def _assert_secret_free(self, *texts: object, extra: tuple[str, ...] = ()) -> None:
        joined = "\n".join(str(value) for value in texts)
        for secret in (self.cookie, self.cookie.split("=", 1)[1], self.csrf, self.password, self.private_path, *extra):
            self.assertNotIn(secret, joined, f"secret leaked: {secret}")

    def test_j7_3_member_link_response_and_runtime_files_do_not_contain_token(self) -> None:
        # /p/<token> authenticates a member; it is distinct from the anonymous share capability.
        response = self.client.get(
            "/api/v2/history/rounds",
            headers={"Authorization": f"Bearer {self.member_player['token']}"},
        )
        self.assertEqual(response.status_code, 200)
        self._assert_secret_free(
            response.text, *self.log_messages, _data_tree_text(self.root),
            extra=(str(self.member_player["token"]),),
        )

    def test_j7_3_share_token_never_persists_or_logs(self) -> None:
        """A share capability is delivered once, then absent from reads, logs and disk."""
        round_id = "900001"
        created = self.client.post(
            f"/api/v2/history/rounds/{round_id}/share", headers={"X-AI-Caddie-Admin-Token": ADMIN},
        )
        self.assertEqual(created.status_code, 201, created.text)
        share_token = created.json()["url"].rsplit("/", 1)[-1]
        read = self.client.get(created.json()["url"])
        self.assertEqual(read.status_code, 200, read.text)
        keyed = self.client.get(created.json()["url"] + "?key=" + self.member_player["token"])
        self.assertEqual(keyed.status_code, 200, keyed.text)
        self._assert_secret_free(
            read.text, keyed.text, *self.log_messages, _data_tree_text(self.root),
            extra=(str(self.member_player["token"]), share_token),
        )
        revoked = self.client.delete(
            f"/api/v2/history/rounds/{round_id}/share",
            headers={"X-AI-Caddie-Admin-Token": ADMIN},
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        after = self.client.get(created.json()["url"])
        self.assertEqual(after.status_code, 404)
        self._assert_secret_free(
            after.text, *self.log_messages, _data_tree_text(self.root),
            extra=(str(self.member_player["token"]), share_token),
        )

    def _invalid_import_rows(self):
        # Each body goes through the real request validator and session-material function.
        valid = {"webSessionHeader": f"Cookie: {self.cookie}",
                 "antiForgeryValue": f"connect-csrf-token: {self.csrf}"}
        return [
            ("multiline cookie", {**valid, "webSessionHeader": f"{self.cookie}\npath={self.private_path}"}),
            ("no equals", {**valid, "webSessionHeader": self.password}),
            ("multiline csrf", {**valid, "antiForgeryValue": f"{self.csrf}\n{self.private_path}"}),
            ("prefix only", {**valid, "webSessionHeader": "Cookie:"}),
            ("invalid source", {**valid, "source": self.password}),
            ("long invalid cookie", {**valid, "webSessionHeader": self.password * 8192}),
        ]

    def test_j7_3_invalid_session_inputs_never_echo_or_persist_secrets(self) -> None:
        for label, body in self._invalid_import_rows():
            with self.subTest(input=label):
                response = self.client.post(
                    "/api/v2/sync/garmin/session",
                    headers={"X-AI-Caddie-Admin-Token": ADMIN}, json=body,
                )
                self.assertEqual(response.status_code, 422)
                self._assert_secret_free(response.text, *self.log_messages, _data_tree_text(self.root))
                self.assertFalse(list(self.root.rglob("web_cookie.txt")))

    def test_j7_3_password_in_import_path_is_not_stored(self) -> None:
        rows = [
            ("unsupported password login", {
                "webSessionHeader": f"Cookie: {self.cookie}", "antiForgeryValue": self.csrf,
                "source": "username_password", "username": "fixture-user", "password": self.password,
            }),
            ("password pasted as cookie", {
                "webSessionHeader": self.password, "antiForgeryValue": self.csrf,
            }),
            ("password pasted after csrf", {
                "webSessionHeader": self.cookie, "antiForgeryValue": f"{self.csrf}\n{self.password}",
            }),
        ]
        for label, body in rows:
            with self.subTest(input=label):
                response = self.client.post(
                    "/api/v2/sync/garmin/session",
                    headers={"X-AI-Caddie-Admin-Token": ADMIN}, json=body,
                )
                self.assertEqual(response.status_code, 422)
                self._assert_secret_free(response.text, *self.log_messages, _data_tree_text(self.root))
                self.assertFalse(list(self.root.rglob("web_cookie.txt")))

    def test_j7_3_sync_failure_redacts_connector_metadata_and_status(self) -> None:
        connector = mock.Mock()
        connector.sync.return_value = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="error",
            detail=f"failed Cookie: {self.cookie} path={self.private_path}",
            error_code="sync_failed",
            safe_meta={"cookie": self.cookie, "csrf": self.csrf, "sourceError": f"password={self.password}"},
        )
        jobs = GarminSyncJobStore(root=self.root)
        with (
            mock.patch.object(main_api, "GarminCnWebSessionConnector", return_value=connector),
            mock.patch.object(main_api, "_garmin_sync_jobs", jobs),
            mock.patch.object(main_api, "_history_input_signature", return_value=None),
            mock.patch.object(main_api, "warm_stats_cache_in_background"),
            mock.patch.object(main_api, "_prepare_recent_bg"),
            mock.patch.object(main_api, "load_sync_status_response",
                              side_effect=lambda: build_sync_status_response(root=self.root, data_mode="local")),
        ):
            headers = {"X-AI-Caddie-Admin-Token": ADMIN}
            queued = self.client.post("/api/v2/sync/garmin", headers=headers)
            self.assertEqual(queued.status_code, 202)
            self._assert_secret_free(queued.text)
            deadline = time.monotonic() + 3
            while True:
                response = self.client.get(f"/api/v2/sync/garmin/jobs/{queued.json()['jobId']}", headers=headers)
                self.assertEqual(response.status_code, 200)
                self._assert_secret_free(response.text)
                if response.json()["state"] not in {"queued", "running"} or time.monotonic() >= deadline:
                    break
                threading.Event().wait(0.01)
            self.assertEqual(response.json()["state"], "error")
            status = self.client.get("/api/v2/sync/status", headers=headers)
            self.assertEqual(status.status_code, 200)
            self._assert_secret_free(status.text, *self.log_messages, _data_tree_text(self.root))
        self.assertTrue(list(jobs.directory.glob("*.json")), "scan a real persisted sync job")


    def test_j7_3_report_model_input_and_stored_report_are_secret_free(self) -> None:
        captured: list[str] = []

        class CaptureProvider:
            model = "capture"

            def chat(self, messages, max_tokens=None):
                del max_tokens
                captured.extend(str(message.content) for message in messages)
                return "基于事实的复盘"

        facts = {
            "kind": "round",
            "subjectId": "round-1",
            "factsUsed": [{"label": "note", "value": f"cookie={self.cookie}; csrf={self.csrf}; path={self.private_path}"}],
            "missingData": [],
        }
        with (
            mock.patch.object(reports_api, "build_round_report_facts", return_value=facts),
            mock.patch.object(reports_api, "build_text_provider", return_value=CaptureProvider()),
            mock.patch.object(reports_api, "_history_stats_dict", return_value={}),
            mock.patch.object(reports_api, "_history_data", return_value=None),
        ):
            response = self.client.post(
                "/api/v2/reports/round/round-1/generate",
                headers={"X-AI-Caddie-Admin-Token": ADMIN},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(captured, "the fake model must actually receive input")
        self._assert_secret_free(captured, response.text, *self.log_messages, _data_tree_text(self.root))
        self.assertTrue((self.root / "data" / "reports" / "reports.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
