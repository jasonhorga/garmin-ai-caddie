from __future__ import annotations

import unittest
from unittest.mock import patch

from server_v2.main import cors_allowed_origin_regex, cors_allowed_origins


class ServerV2CorsTests(unittest.TestCase):
    def test_cors_defaults_to_local_dev_origins(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            origins = cors_allowed_origins()

        self.assertIn("http://127.0.0.1:5173", origins)
        self.assertIn("http://localhost:5173", origins)

    def test_cors_can_add_staging_web_origins_from_env(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AI_CADDIE_CORS_ORIGINS": "https://ai-caddie-web.vercel.app, https://preview-ai-caddie.vercel.app/",
            },
            clear=True,
        ):
            origins = cors_allowed_origins()

        self.assertIn("http://127.0.0.1:5173", origins)
        self.assertIn("https://ai-caddie-web.vercel.app", origins)
        self.assertIn("https://preview-ai-caddie.vercel.app", origins)
        self.assertNotIn("https://preview-ai-caddie.vercel.app/", origins)

    def test_cors_origin_regex_supports_preview_domains(self) -> None:
        with patch.dict(
            "os.environ",
            {"AI_CADDIE_CORS_ORIGIN_REGEX": r"https://.*\.vercel\.app"},
            clear=True,
        ):
            regex = cors_allowed_origin_regex()

        self.assertEqual(regex, r"https://.*\.vercel\.app")

    def test_cors_origin_regex_defaults_to_none(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            regex = cors_allowed_origin_regex()

        self.assertIsNone(regex)

    def test_preflight_allows_put_for_the_club_bag_editor(self) -> None:
        # The web club-bag editor writes via PUT /api/v2/players/{id}/clubs/bag; the CORS preflight
        # from a configured browser origin must permit PUT (it was omitted from allow_methods).
        from fastapi.testclient import TestClient

        from server_v2.main import app

        resp = TestClient(app).options(
            "/api/v2/players/p_m/clubs/bag",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "PUT",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("PUT", resp.headers.get("access-control-allow-methods", ""))


if __name__ == "__main__":
    unittest.main()
