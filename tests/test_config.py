from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ai_caddie.config import get_settings


class ConfigTests(unittest.TestCase):
    def test_settings_default_to_local_or_fixture(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.data_mode, "local_or_fixture")
        self.assertEqual(settings.llm_provider, "static")
        self.assertEqual(settings.static_llm_reply, "AI Caddie fixture response")

    def test_settings_read_env_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AI_CADDIE_DATA_MODE": "fixture",
                "AI_CADDIE_LLM_PROVIDER": "nvidia_nim",
                "AI_CADDIE_STATIC_LLM_REPLY": "fixture ok",
                "GEMINI_OAUTH_CREDENTIALS_FILE": "/tmp/gemini-oauth.json",
                "GOOGLE_CLOUD_PROJECT": "gemini-project",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.data_mode, "fixture")
        self.assertEqual(settings.llm_provider, "nvidia_nim")
        self.assertEqual(settings.static_llm_reply, "fixture ok")
        self.assertTrue(settings.gemini_oauth_configured)
        self.assertEqual(settings.gemini_oauth_credentials_file, "/tmp/gemini-oauth.json")
        self.assertEqual(settings.google_cloud_project, "gemini-project")


if __name__ == "__main__":
    unittest.main()
