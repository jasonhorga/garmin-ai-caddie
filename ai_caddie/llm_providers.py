from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable, Literal, Protocol, runtime_checkable

from ai_caddie.config import get_settings


@dataclass(frozen=True)
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@runtime_checkable
class TextProvider(Protocol):
    model: str

    def chat(self, messages: Iterable[LLMMessage], max_tokens: int | None = None) -> str: ...


def redact_secret_text(text: object) -> str:
    value = str(text)
    value = re.sub(
        r"(?i)(authorization|cookie|connect-csrf-token|csrf|token|api[_-]?key)\s*[:=]\s*[^,\s]+",
        r"\1=[REDACTED]",
        value,
    )
    value = re.sub(r"(?i)bearer\s+[a-z0-9._~+/=-]+", "Bearer [REDACTED]", value)
    value = re.sub(r"/(?:home|Users)/[^\s,)]+", "[REDACTED_PATH]", value)
    return value


class ProviderConfigurationError(RuntimeError):
    def __init__(self, message: object) -> None:
        super().__init__(redact_secret_text(message))


class ProviderRuntimeError(RuntimeError):
    def __init__(self, message: object) -> None:
        super().__init__(redact_secret_text(message))


class StaticProvider:
    model = "static"

    def __init__(self, reply: str = "AI Caddie fixture response") -> None:
        self.reply = reply

    def chat(self, messages: Iterable[LLMMessage], max_tokens: int | None = None) -> str:
        list(messages)
        return self.reply


class NvidiaNimProvider:
    def __init__(self, *, api_key: str, base_url: str, model: str) -> None:
        if not api_key:
            raise ProviderConfigurationError("NVIDIA_API_KEY is not configured")
        if not base_url:
            raise ProviderConfigurationError("NVIDIA_NIM_BASE_URL is not configured")
        if not model:
            raise ProviderConfigurationError("NVIDIA_NIM_MODEL is not configured")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages: Iterable[LLMMessage], max_tokens: int | None = None) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
            "max_tokens": max_tokens or 1800,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ProviderRuntimeError(exc) from exc
        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderRuntimeError("NVIDIA NIM response did not include choices[0].message.content") from exc


class AnthropicProvider:
    def __init__(self, *, api_key_present: bool, model: str | None = None) -> None:
        if not api_key_present:
            raise ProviderConfigurationError("ANTHROPIC_API_KEY is not configured")
        self.model = model or os.getenv("AI_CADDIE_MODEL", "claude-sonnet-4-5-20250929")

    def chat(self, messages: Iterable[LLMMessage], max_tokens: int | None = None) -> str:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens or 1800,
            messages=[{"role": item.role, "content": item.content} for item in messages if item.role != "system"],
            system="\n\n".join(item.content for item in messages if item.role == "system") or None,
        )
        try:
            return str(response.content[0].text)
        except (AttributeError, IndexError) as exc:
            raise ProviderRuntimeError("Anthropic response did not include content[0].text") from exc


def build_text_provider(settings: object | None = None) -> TextProvider:
    resolved = settings or get_settings()
    provider_name = getattr(resolved, "llm_provider", "static")

    if provider_name == "static":
        return StaticProvider(reply=getattr(resolved, "static_llm_reply", "AI Caddie fixture response"))
    if provider_name == "nvidia_nim":
        return NvidiaNimProvider(
            api_key=os.getenv("NVIDIA_API_KEY", "") if getattr(resolved, "nvidia_api_key_present", False) else "",
            base_url=getattr(resolved, "nvidia_nim_base_url", ""),
            model=getattr(resolved, "nvidia_nim_model", ""),
        )
    if provider_name == "anthropic":
        return AnthropicProvider(api_key_present=bool(getattr(resolved, "anthropic_api_key_present", False)))
    if provider_name == "gemini_api_key":
        raise ProviderConfigurationError("gemini_api_key provider is not configured in this build")
    if provider_name == "gemini_cli_oauth":
        raise ProviderConfigurationError("gemini_cli_oauth provider is internal development only")
    raise ProviderConfigurationError(f"Unsupported LLM provider: {provider_name}")
