from __future__ import annotations

import json
import stat
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.connectors.session_material import save_garmin_cn_web_session


SECRET_VALUES = ("JWT_WEB=abc123", "csrf-secret-value", ".garmin_tokens")


class GarminSessionImportTests(unittest.TestCase):
    def test_saves_manual_web_session_material_without_echoing_values(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = save_garmin_cn_web_session(
                web_session_header="Cookie: JWT_WEB=abc123; GARMIN=two",
                anti_forgery_value="connect-csrf-token: csrf-secret-value",
                root=root,
            )

            session_dir = root / ".garmin_tokens"
            web_session_file = session_dir / "web_cookie.txt"
            anti_forgery_file = session_dir / "csrf.txt"

            self.assertEqual(result["schema"], "ai-caddie-garmin-session-import-v1")
            self.assertEqual(result["connector"], "garmin_cn_web_session")
            self.assertEqual(result["state"], "stored")
            self.assertEqual(result["sessionFieldCount"], 2)
            self.assertTrue(result["antiForgeryPresent"])
            self.assertEqual(result["source"], "manual_paste")
            self.assertIn("ios_web_login", result["acceptedSources"])
            self.assertEqual(web_session_file.read_text(encoding="utf-8").strip(), "JWT_WEB=abc123; GARMIN=two")
            self.assertEqual(anti_forgery_file.read_text(encoding="utf-8").strip(), "csrf-secret-value")
            self.assertEqual(stat.S_IMODE(session_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(web_session_file.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(anti_forgery_file.stat().st_mode), 0o600)

            response_text = json.dumps(result, ensure_ascii=False)
            for value in SECRET_VALUES:
                self.assertNotIn(value, response_text)

    def test_accepts_replaceable_ios_session_material_source_without_changing_secret_storage(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = save_garmin_cn_web_session(
                web_session_header="Cookie: JWT_WEB=abc123",
                anti_forgery_value="connect-csrf-token: csrf-secret-value",
                source="ios_keychain_replay",
                root=root,
            )

        self.assertEqual(result["source"], "ios_keychain_replay")
        self.assertEqual(result["sessionFieldCount"], 1)
        self.assertTrue(result["antiForgeryPresent"])
        response_text = json.dumps(result, ensure_ascii=False)
        for value in SECRET_VALUES:
            self.assertNotIn(value, response_text)

    def test_rejects_empty_or_multiline_session_values(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaises(ValueError):
                save_garmin_cn_web_session(
                    web_session_header="",
                    anti_forgery_value="csrf-secret-value",
                    root=root,
                )
            with self.assertRaises(ValueError):
                save_garmin_cn_web_session(
                    web_session_header="JWT_WEB=abc123\nOther=value",
                    anti_forgery_value="csrf-secret-value",
                    root=root,
                )
            with self.assertRaises(ValueError):
                save_garmin_cn_web_session(
                    web_session_header="JWT_WEB=abc123",
                    anti_forgery_value="csrf-secret-value",
                    source="username_password",
                    root=root,
                )

            self.assertFalse((root / ".garmin_tokens").exists())


if __name__ == "__main__":
    unittest.main()
