from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import unittest
import os
import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_caddie.config import get_settings
from ai_caddie.llm import maybe_call_anthropic, maybe_call_llm
from ai_caddie.llm_providers import (
    GeminiApiKeyProvider,
    GeminiCliOAuthProvider,
    LLMMediaPart,
    LLMMessage,
    NvidiaNimProvider,
    ProviderConfigurationError,
    StaticProvider,
    build_text_provider,
)


class FakeCodeAssistHttpClient:
    def __init__(self, json_responses: list[dict[str, object]]) -> None:
        self.json_responses = list(json_responses)
        self.calls: list[dict[str, object]] = []

    def post_json(self, url: str, *, headers: dict[str, str], body: dict[str, object]) -> dict[str, object]:
        self.calls.append({"url": url, "headers": headers, "body": body})
        if not self.json_responses:
            raise AssertionError(f"unexpected Code Assist call: {url}")
        return self.json_responses.pop(0)


def _write_cli_oauth_token_cache(path: Path, *, token: str = "test-token", expires_in_seconds: int = 3600) -> None:
    expiry = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
    path.write_text(
        json.dumps(
            {
                "access_token": token,
                "expiry_date": expiry.isoformat().replace("+00:00", "Z"),
                "scope": "https://www.googleapis.com/auth/cloud-platform",
                "token_type": "Bearer",
            }
        ),
        encoding="utf-8",
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

    def test_nvidia_nim_provider_serializes_multimodal_parts_for_openai_compatible_vision(self) -> None:
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "choices": [
                            {"message": {"content": "nim vision review"}}
                        ]
                    }
                ).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        provider = NvidiaNimProvider(
            api_key="nim-secret-key",
            base_url="https://integrate.api.nvidia.com/v1",
            model="meta/llama-3.2-11b-vision-instruct",
        )
        with patch("ai_caddie.llm_providers.urllib.request.urlopen", fake_urlopen):
            reply = provider.chat_multimodal(
                [
                    LLMMessage(role="system", content="facts only"),
                    LLMMessage(role="user", content="inspect the lie photo"),
                ],
                [LLMMediaPart(media_type="image", mime_type="image/jpeg", data=b"image-bytes")],
                max_tokens=333,
            )

        self.assertEqual(reply, "nim vision review")
        self.assertEqual(captured["timeout"], 60)
        request = captured["request"]
        self.assertEqual(request.full_url, "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertEqual(request.headers["Authorization"], "Bearer nim-secret-key")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "meta/llama-3.2-11b-vision-instruct")
        self.assertEqual(payload["max_tokens"], 333)
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "facts only"})
        content = payload["messages"][1]["content"]
        self.assertEqual(content[0], {"type": "text", "text": "inspect the lie photo"})
        self.assertEqual(
            content[1],
            {
                "type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64,aW1hZ2UtYnl0ZXM="},
            },
        )
        self.assertNotIn("mediaBytesBase64", request.data.decode("utf-8"))
        self.assertNotIn("image-bytes", request.data.decode("utf-8"))

    def test_gemini_api_key_provider_calls_generate_content_without_leaking_key(self) -> None:
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "candidates": [
                            {"content": {"parts": [{"text": "gemini review"}]}}
                        ]
                    }
                ).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        provider = GeminiApiKeyProvider(
            api_key="gemini-secret-key",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            model="gemini-2.5-flash",
        )
        with patch("ai_caddie.llm_providers.urllib.request.urlopen", fake_urlopen):
            reply = provider.chat(
                [
                    LLMMessage(role="system", content="facts only"),
                    LLMMessage(role="user", content="round facts"),
                ],
                max_tokens=321,
            )

        self.assertEqual(reply, "gemini review")
        request = captured["request"]
        self.assertEqual(captured["timeout"], 60)
        self.assertEqual(
            request.full_url,
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        )
        self.assertEqual(request.headers["X-goog-api-key"], "gemini-secret-key")
        self.assertNotIn("gemini-secret-key", request.data.decode("utf-8"))
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], "facts only")
        self.assertEqual(payload["contents"][0]["parts"][0]["text"], "round facts")
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 321)

    def test_gemini_api_key_provider_serializes_multimodal_parts_as_inline_data(self) -> None:
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "candidates": [
                            {"content": {"parts": [{"text": "vision review"}]}}
                        ]
                    }
                ).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        provider = GeminiApiKeyProvider(
            api_key="gemini-secret-key",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            model="models/gemini-2.5-flash",
        )
        with patch("ai_caddie.llm_providers.urllib.request.urlopen", fake_urlopen):
            reply = provider.chat_multimodal(
                [
                    LLMMessage(role="system", content="facts only"),
                    LLMMessage(role="user", content="inspect the shot photo"),
                ],
                [
                    LLMMediaPart(
                        media_type="image",
                        mime_type="image/jpeg",
                        data=b"image-bytes",
                    ),
                    LLMMediaPart(
                        media_type="video",
                        mime_type="video/mp4",
                        data=b"video-bytes",
                    ),
                ],
                max_tokens=222,
            )

        self.assertEqual(reply, "vision review")
        self.assertEqual(captured["timeout"], 60)
        request = captured["request"]
        payload = json.loads(request.data.decode("utf-8"))
        parts = payload["contents"][0]["parts"]
        self.assertEqual(parts[0], {"text": "inspect the shot photo"})
        self.assertEqual(
            parts[1],
            {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": "aW1hZ2UtYnl0ZXM=",
                }
            },
        )
        self.assertEqual(
            parts[2],
            {
                "inline_data": {
                    "mime_type": "video/mp4",
                    "data": "dmlkZW8tYnl0ZXM=",
                }
            },
        )
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], "facts only")
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 222)
        self.assertNotIn("mediaBytesBase64", parts[0]["text"])
        self.assertNotIn("aW1hZ2UtYnl0ZXM=", parts[0]["text"])
        self.assertNotIn("dmlkZW8tYnl0ZXM=", parts[0]["text"])
        self.assertNotIn("image-bytes", request.data.decode("utf-8"))
        self.assertNotIn("video-bytes", request.data.decode("utf-8"))

    def test_missing_gemini_key_raises_secret_free_error(self) -> None:
        settings = SimpleNamespace(
            llm_provider="gemini_api_key",
            gemini_api_key_present=False,
            gemini_api_base_url="https://generativelanguage.googleapis.com/v1beta",
            gemini_model="gemini-2.5-flash",
        )

        with self.assertRaises(ProviderConfigurationError) as raised:
            build_text_provider(settings=settings)

        self.assertIn("GEMINI_API_KEY is not configured", str(raised.exception))

    def test_provider_selection_rejects_unsupported_names(self) -> None:
        settings = SimpleNamespace(llm_provider="unsupported_vendor")

        with self.assertRaises(ProviderConfigurationError) as raised:
            build_text_provider(settings=settings)

        self.assertIn("Unsupported LLM provider", str(raised.exception))

    def test_gemini_cli_oauth_provider_posts_to_code_assist_with_bearer_token_and_project(self) -> None:
        with TemporaryDirectory() as tmp:
            credentials_file = Path(tmp) / "oauth.json"
            _write_cli_oauth_token_cache(credentials_file)
            http_client = FakeCodeAssistHttpClient(
                [
                    {"cloudaicompanionProject": "server-project"},
                    {"response": {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}},
                ]
            )
            provider = GeminiCliOAuthProvider(
                model="gemini-test",
                oauth_credentials_file=str(credentials_file),
                google_cloud_project="gemini-jason-he-o",
                http_client=http_client,
            )

            response = provider.chat(
                [
                    LLMMessage(role="system", content="Answer briefly."),
                    LLMMessage(role="user", content="ping"),
                ],
                max_tokens=12,
            )

        self.assertEqual(response, "ok")
        load_call, generate_call = http_client.calls
        self.assertEqual(load_call["url"], "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist")
        self.assertEqual(load_call["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(load_call["body"]["cloudaicompanionProject"], "gemini-jason-he-o")
        self.assertEqual(load_call["body"]["metadata"]["pluginType"], "GEMINI")
        self.assertEqual(load_call["body"]["metadata"]["duetProject"], "gemini-jason-he-o")
        self.assertEqual(generate_call["url"], "https://cloudcode-pa.googleapis.com/v1internal:generateContent")
        self.assertEqual(generate_call["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(generate_call["body"]["model"], "gemini-test")
        self.assertEqual(generate_call["body"]["project"], "server-project")
        request_body = generate_call["body"]["request"]
        self.assertEqual(request_body["contents"], [{"role": "user", "parts": [{"text": "ping"}]}])
        self.assertEqual(request_body["systemInstruction"], {"role": "user", "parts": [{"text": "Answer briefly."}]})
        self.assertEqual(request_body["generationConfig"], {"maxOutputTokens": 12})
        serialized_body = json.dumps(generate_call["body"])
        self.assertNotIn("test-token", serialized_body)
        self.assertNotIn("refresh_token", serialized_body)

    def test_gemini_cli_oauth_provider_accepts_base64_credentials_json(self) -> None:
        credentials_json = json.dumps(
            {
                "access_token": "encoded-token",
                "expiry_date": (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                "scope": "https://www.googleapis.com/auth/cloud-platform",
            }
        )
        http_client = FakeCodeAssistHttpClient(
            [
                {"cloudaicompanionProject": "server-project"},
                {"response": {"candidates": [{"content": {"parts": [{"text": "encoded ok"}]}}]}},
            ]
        )
        provider = GeminiCliOAuthProvider(
            model="gemini-test",
            oauth_credentials_b64=base64.b64encode(credentials_json.encode("utf-8")).decode("ascii"),
            google_cloud_project="gemini-jason-he-o",
            http_client=http_client,
        )

        response = provider.chat([LLMMessage(role="user", content="ping")])

        self.assertEqual(response, "encoded ok")
        self.assertEqual(http_client.calls[0]["headers"]["Authorization"], "Bearer encoded-token")

    def test_build_text_provider_supports_configured_gemini_cli_oauth(self) -> None:
        settings = SimpleNamespace(
            llm_provider="gemini_cli_oauth",
            gemini_model="gemini-test",
            gemini_oauth_credentials_file="/tmp/oauth.json",
            gemini_oauth_credentials_json=None,
            gemini_oauth_credentials_b64=None,
            google_cloud_project="gemini-jason-he-o",
            google_cloud_location="global",
        )

        provider = build_text_provider(settings=settings)

        self.assertIsInstance(provider, GeminiCliOAuthProvider)
        self.assertEqual(provider.model, "gemini-test")

    def test_gemini_cli_oauth_requires_credentials_when_called(self) -> None:
        settings = SimpleNamespace(llm_provider="gemini_cli_oauth", gemini_model="gemini-test", google_cloud_project="project")
        provider = build_text_provider(settings=settings)

        with self.assertRaises(ProviderConfigurationError) as raised:
            provider.chat([LLMMessage(role="user", content="ping")])

        self.assertIn("requires GEMINI_OAUTH_CREDENTIALS", str(raised.exception))

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

    def test_maybe_call_anthropic_compatibility_uses_configured_provider(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AI_CADDIE_LLM_PROVIDER": "static",
                "AI_CADDIE_STATIC_LLM_REPLY": "static compatibility review",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            text, error = maybe_call_anthropic({"summary": "facts"})

        self.assertEqual(text, "static compatibility review")
        self.assertIsNone(error)

    def test_maybe_call_anthropic_reports_missing_key_when_configured_provider_is_anthropic(self) -> None:
        with patch.dict(os.environ, {"AI_CADDIE_LLM_PROVIDER": "anthropic"}, clear=True):
            get_settings.cache_clear()
            text, error = maybe_call_anthropic({"summary": "facts"})

        self.assertIsNone(text)
        self.assertIn("ANTHROPIC_API_KEY is not configured", error or "")


if __name__ == "__main__":
    unittest.main()
