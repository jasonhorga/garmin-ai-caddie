from __future__ import annotations

import unittest
import os
from types import SimpleNamespace
from unittest.mock import patch

from ai_caddie.config import get_settings
from ai_caddie.llm import maybe_call_anthropic, maybe_call_llm
from ai_caddie.llm_providers import (
    LLMMessage,
    ProviderConfigurationError,
    StaticProvider,
    build_text_provider,
)


class LLMProviderTests(unittest.TestCase):
    def test_static_provider_returns_configured_reply(self) -> None:
        provider = StaticProvider(reply="fixture review")

        reply = provider.chat([LLMMessage(role="user", content="facts")])

        self.assertEqual(reply, "fixture review")
        self.assertEqual(provider.model, "static")

    def test_missing_nim_key_raises_secret_free_error(self) -> None:
        settings = SimpleNamespace(
            llm_provider="nvidia_nim",
            nvidia_api_key_present=False,
            nvidia_nim_base_url="https://integrate.api.nvidia.com/v1",
            nvidia_nim_model="meta/llama",
        )

        with self.assertRaises(ProviderConfigurationError) as raised:
            build_text_provider(settings=settings)

        text = str(raised.exception)
        self.assertIn("NVIDIA_API_KEY is not configured", text)
        self.assertNotIn("Bearer", text)
        self.assertNotIn("secret", text.lower())

    def test_provider_selection_rejects_unsupported_names(self) -> None:
        settings = SimpleNamespace(llm_provider="unsupported_vendor")

        with self.assertRaises(ProviderConfigurationError) as raised:
            build_text_provider(settings=settings)

        self.assertIn("Unsupported LLM provider", str(raised.exception))

    def test_gemini_cli_oauth_is_internal_only(self) -> None:
        settings = SimpleNamespace(llm_provider="gemini_cli_oauth")

        with self.assertRaises(ProviderConfigurationError) as raised:
            build_text_provider(settings=settings)

        self.assertIn("internal development only", str(raised.exception))

    def test_exception_text_redacts_secret_like_values(self) -> None:
        error = ProviderConfigurationError(
            "failed token=abc123 cookie=session-value connect-csrf-token=csrf-secret /home/ubuntu/private/path"
        )

        text = str(error)
        self.assertNotIn("abc123", text)
        self.assertNotIn("session-value", text)
        self.assertNotIn("csrf-secret", text)
        self.assertNotIn("/home/ubuntu/private/path", text)
        self.assertIn("[REDACTED]", text)

    def test_maybe_call_llm_uses_configured_static_provider(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AI_CADDIE_LLM_PROVIDER": "static",
                "AI_CADDIE_STATIC_LLM_REPLY": "static review",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            text, error = maybe_call_llm({"summary": "facts"})

        self.assertEqual(text, "static review")
        self.assertIsNone(error)

    def test_maybe_call_anthropic_compatibility_reports_missing_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            get_settings.cache_clear()
            text, error = maybe_call_anthropic({"summary": "facts"})

        self.assertIsNone(text)
        self.assertIn("ANTHROPIC_API_KEY is not configured", error or "")


if __name__ == "__main__":
    unittest.main()
