from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

DataMode = Literal["local", "fixture", "local_or_fixture"]
LLMProviderName = Literal[
    "static",
    "anthropic",
    "nvidia_nim",
    "gemini_api_key",
    "gemini_cli_oauth",
]


class Settings:
    def __init__(self) -> None:
        self.data_mode: DataMode = _data_mode(
            os.getenv("AI_CADDIE_DATA_MODE", "local_or_fixture")
        )
        self.llm_provider: LLMProviderName = _llm_provider(
            os.getenv("AI_CADDIE_LLM_PROVIDER", "static")
        )
        self.static_llm_reply = os.getenv(
            "AI_CADDIE_STATIC_LLM_REPLY", "AI Caddie fixture response"
        )
        self.nvidia_api_key_present = bool(os.getenv("NVIDIA_API_KEY"))
        self.nvidia_nim_base_url = os.getenv("NVIDIA_NIM_BASE_URL", "").rstrip("/")
        self.nvidia_nim_model = os.getenv("NVIDIA_NIM_MODEL", "")
        self.gemini_api_key_present = bool(os.getenv("GEMINI_API_KEY"))
        self.gemini_api_base_url = os.getenv(
            "GEMINI_API_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta",
        ).rstrip("/")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.gemini_oauth_credentials_file = os.getenv("GEMINI_OAUTH_CREDENTIALS_FILE")
        self.gemini_oauth_credentials_json = os.getenv("GEMINI_OAUTH_CREDENTIALS_JSON")
        self.gemini_oauth_credentials_b64 = os.getenv("GEMINI_OAUTH_CREDENTIALS_B64")
        self.gemini_oauth_configured = bool(
            self.gemini_oauth_credentials_file
            or self.gemini_oauth_credentials_json
            or self.gemini_oauth_credentials_b64
        )
        self.google_cloud_project = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.google_cloud_location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        self.anthropic_api_key_present = bool(os.getenv("ANTHROPIC_API_KEY"))


def _data_mode(value: str) -> DataMode:
    if value in {"local", "fixture", "local_or_fixture"}:
        return value  # type: ignore[return-value]
    raise ValueError(f"Unsupported AI_CADDIE_DATA_MODE: {value}")


def _llm_provider(value: str) -> LLMProviderName:
    if value in {
        "static",
        "anthropic",
        "nvidia_nim",
        "gemini_api_key",
        "gemini_cli_oauth",
    }:
        return value  # type: ignore[return-value]
    raise ValueError(f"Unsupported AI_CADDIE_LLM_PROVIDER: {value}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
