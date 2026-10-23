"""J7.3 runtime secret-safety checks.

The values below are created at runtime and are never present in the repository fixtures.  Each
test checks the actual response, captured logs, model prompt, and durable non-credential data
written by the operation.  Credential files are intentionally excluded from the non-credential
scan because a captured Garmin session is the input to a later sync; the API must never echo it.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.connectors.base import ConnectorRunResult
from ai_caddie.connectors.session_material import save_garmin_cn_web_session
from ai_caddie.rounds import players
from server_v2 import reports as reports_api
from server_v2 import session as session_api
import server_v2.main as main_api
from server_v2.main import app


ADMIN = "runtime-admin-secret"
COOKIE = "JWT_WEB=runtime-cookie-4f8a"
CSRF = "runtime-csrf-91b2"
PASSWORD = "runtime-garmin-password-0d7e"
PRIVATE_PATH = "/srv/ai-caddie/private/runtime-secret.json"


def _non_credential_text(root: Path) -> str:
    chunks: list[str] = []
    if not root.exists():
        return ""
    for path in root.rglob("*"):
        if not path.is_file() or ".garmin_tokens" in path.parts:
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks)


class J7SecretTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patches = [
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(session_api, "SESSION_ROOT", self.root),
            mock.patch.object(main_api, "SYNC_ROOT", self.root),
            mock.patch.object(reports_api, "REPORT_ROOT", self.root),
            mock.patch.dict(
                os.environ,
                {"AI_CADDIE_ADMIN_TOKEN": ADMIN, "AI_CADDIE_DATA_MODE": "fixture"},
            ),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.client = TestClient(app)

    def _assert_secret_free(self, *texts: object) -> None:
        joined = "\n".join(str(value) for value in texts)
        for secret in (COOKIE, CSRF, PASSWORD, PRIVATE_PATH):
            self.assertNotIn(secret, joined, f"secret leaked: {secret}")

    def test_session_import_error_redacts_cookie_csrf_and_private_path(self) -> None:
        error = ValueError(
            f"provider failed Cookie: {COOKIE}; connect-csrf-token: {CSRF}; path={PRIVATE_PATH}"
        )
        log_messages: list[str] = []
        handler = logging.Handler()
        handler.emit = lambda record: log_messages.append(record.getMessage())
        logging.getLogger().addHandler(handler)
        try:
            with mock.patch.object(session_api, "save_garmin_cn_web_session", side_effect=error):
                response = self.client.post(
                    "/api/v2/sync/garmin/session",
                    headers={"X-AI-Caddie-Admin-Token": ADMIN},
                    json={
                        "webSessionHeader": f"Cookie: {COOKIE}",
                        "antiForgeryValue": f"connect-csrf-token: {CSRF}",
                    },
                )
        finally:
            logging.getLogger().removeHandler(handler)
        self.assertEqual(response.status_code, 422, response.text)
        self._assert_secret_free(response.text, "\n".join(log_messages), _non_credential_text(self.root))

    def test_password_source_is_rejected_without_any_durable_password(self) -> None:
        with self.assertRaises(ValueError):
            save_garmin_cn_web_session(
                web_session_header=f"Cookie: {COOKIE}",
                anti_forgery_value=f"connect-csrf-token: {CSRF}",
                source="username_password",
                root=self.root,
            )
        self.assertFalse((self.root / ".garmin_tokens").exists())
        self._assert_secret_free(_non_credential_text(self.root))
        self.assertNotIn(PASSWORD, json.dumps(self.root.as_posix()))

    def test_sync_failure_redacts_connector_metadata_and_status(self) -> None:
        connector = mock.Mock()
        connector.sync.return_value = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="error",
            detail=f"failed Cookie: {COOKIE} path={PRIVATE_PATH}",
            error_code="sync_failed",
            safe_meta={"cookie": COOKIE, "csrf": CSRF, "sourceError": f"password={PASSWORD}"},
        )
        with (
            mock.patch.object(main_api, "GarminCnWebSessionConnector", return_value=connector),
            mock.patch.object(main_api, "_history_input_signature", return_value=None),
            mock.patch.object(main_api, "warm_stats_cache_in_background"),
            mock.patch.object(main_api, "_prepare_recent_bg"),
        ):
            result = main_api._run_garmin_sync_job(
                {"playerId": "me", "request": {"withShots": True}}
            )
        self._assert_secret_free(result, _non_credential_text(self.root))
        status_files = list(self.root.rglob("*status*.json"))
        self._assert_secret_free(*(path.read_text(encoding="utf-8") for path in status_files))

    def test_report_model_input_and_stored_report_are_secret_free(self) -> None:
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
            "factsUsed": [{"label": "note", "value": f"cookie={COOKIE} path={PRIVATE_PATH}"}],
            "missingData": [],
        }
        with (
            mock.patch.object(reports_api, "build_round_report_facts", return_value=facts),
            mock.patch.object(reports_api, "build_text_provider", return_value=CaptureProvider()),
            mock.patch.object(reports_api, "_history_stats_dict", return_value={}),
            mock.patch.object(reports_api, "_history_data", return_value=None),
        ):
            report = reports_api.generate_round_report_response("round-1")
        self._assert_secret_free(captured, report.model_dump(), _non_credential_text(self.root))
        self.assertTrue((self.root / "data" / "reports" / "reports.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
