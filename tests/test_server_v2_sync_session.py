from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server_v2.main import app


class ServerV2SyncSessionTests(unittest.TestCase):
    def test_sync_session_endpoint_requires_admin_token_when_configured(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}),
                patch("server_v2.session.SESSION_ROOT", root),
            ):
                response = client.post(
                    "/api/v2/sync/garmin/session",
                    json={
                        "webSessionHeader": "Cookie: JWT_WEB=abc123",
                        "antiForgeryValue": "connect-csrf-token: csrf-secret-value",
                    },
                )
                token_dir_exists = (root / ".garmin_tokens").exists()

        self.assertEqual(response.status_code, 401)
        self.assertFalse(token_dir_exists)
        self.assertNotIn("admin-secret", response.text)

    def test_sync_session_endpoint_accepts_admin_token_header_when_configured(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.dict("os.environ", {"AI_CADDIE_ADMIN_TOKEN": "admin-secret"}),
                patch("server_v2.session.SESSION_ROOT", root),
            ):
                response = client.post(
                    "/api/v2/sync/garmin/session",
                    headers={"X-AI-Caddie-Admin-Token": "admin-secret"},
                    json={
                        "webSessionHeader": "Cookie: JWT_WEB=abc123",
                        "antiForgeryValue": "connect-csrf-token: csrf-secret-value",
                    },
                )
                web_cookie_exists = (root / ".garmin_tokens" / "web_cookie.txt").exists()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(web_cookie_exists)

    def test_sync_session_endpoint_stores_material_without_echoing_secrets(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.session.SESSION_ROOT", root):
                response = client.post(
                    "/api/v2/sync/garmin/session",
                    json={
                        "webSessionHeader": "Cookie: JWT_WEB=abc123; GARMIN=two",
                        "antiForgeryValue": "connect-csrf-token: csrf-secret-value",
                    },
                )

            payload = response.json()
            session_file = root / ".garmin_tokens" / "web_cookie.txt"
            anti_forgery_file = root / ".garmin_tokens" / "csrf.txt"
            session_text = session_file.read_text(encoding="utf-8").strip()
            anti_forgery_text = anti_forgery_file.read_text(encoding="utf-8").strip()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schema"], "ai-caddie-garmin-session-import-v1")
        self.assertEqual(payload["state"], "stored")
        self.assertEqual(payload["sessionFieldCount"], 2)
        self.assertTrue(payload["antiForgeryPresent"])
        self.assertEqual(session_text, "JWT_WEB=abc123; GARMIN=two")
        self.assertEqual(anti_forgery_text, "csrf-secret-value")
        self.assertNotIn("abc123", response.text)
        self.assertNotIn("csrf-secret-value", response.text)
        self.assertNotIn(".garmin_tokens", response.text)

    def test_sync_session_endpoint_rejects_invalid_material_without_writing(self) -> None:
        client = TestClient(app)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("server_v2.session.SESSION_ROOT", root):
                response = client.post(
                    "/api/v2/sync/garmin/session",
                    json={
                        "webSessionHeader": "JWT_WEB=abc123\nbad=value",
                        "antiForgeryValue": "csrf-secret-value",
                    },
                )
                token_dir_exists = (root / ".garmin_tokens").exists()

        self.assertEqual(response.status_code, 422)
        self.assertFalse(token_dir_exists)


if __name__ == "__main__":
    unittest.main()
