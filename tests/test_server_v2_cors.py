from __future__ import annotations

import unittest
from unittest.mock import patch

from server_v2.main import cors_allowed_origins


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


if __name__ == "__main__":
    unittest.main()
