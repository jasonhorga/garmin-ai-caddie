from __future__ import annotations

import base64
import binascii
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Protocol, runtime_checkable
from uuid import uuid4

from ai_caddie.config import get_settings


CODE_ASSIST_ENDPOINT = "https://cloudcode-pa.googleapis.com"
CODE_ASSIST_API_VERSION = "v1internal"
GOOGLE_OAUTH_TOKEN_URI = "https://oauth2.googleapis.com/token"
GEMINI_CLI_OAUTH_CLIENT_ID = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
GEMINI_CLI_OAUTH_CLIENT_SECRET = "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"
GEMINI_CLI_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
OAUTH_EXPIRY_SKEW_SECONDS = 60


@dataclass(frozen=True)
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMMediaPart:
    media_type: Literal["image", "video"]
    mime_type: str
    data: bytes


@runtime_checkable
class TextProvider(Protocol):
    model: str

    def chat(self, messages: Iterable[LLMMessage], max_tokens: int | None = None) -> str: ...


@runtime_checkable
class MultimodalProvider(Protocol):
    model: str

    def chat(self, messages: Iterable[LLMMessage], max_tokens: int | None = None) -> str: ...

    def chat_multimodal(
        self,
        messages: Iterable[LLMMessage],
        media_parts: Iterable[LLMMediaPart],
        max_tokens: int | None = None,
    ) -> str: ...


def redact_secret_text(text: object) -> str:
    value = str(text)
    value = re.sub(
        r"(?i)(authorization|cookie|connect-csrf-token|csrf|token|access[_-]?token|refresh[_-]?token|client[_-]?secret|api[_-]?key)\s*[:=]\s*[^,\s]+",
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

    def chat_multimodal(
        self,
        messages: Iterable[LLMMessage],
        media_parts: Iterable[LLMMediaPart],
        max_tokens: int | None = None,
    ) -> str:
        list(messages)
        list(media_parts)
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

    @staticmethod
    def _media_content_part(media_part: LLMMediaPart) -> dict[str, object]:
        encoded = base64.b64encode(media_part.data).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{media_part.mime_type};base64,{encoded}"},
        }

    def _chat_completion(self, payload: dict[str, object]) -> str:
        payload = {
            **payload,
            "model": self.model,
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

    def chat(self, messages: Iterable[LLMMessage], max_tokens: int | None = None) -> str:
        return self._chat_completion(
            {
                "messages": [{"role": item.role, "content": item.content} for item in messages],
                "max_tokens": max_tokens or 1800,
            }
        )

    def chat_multimodal(
        self,
        messages: Iterable[LLMMessage],
        media_parts: Iterable[LLMMediaPart],
        max_tokens: int | None = None,
    ) -> str:
        media_content = [self._media_content_part(item) for item in media_parts]
        media_attached = not media_content
        payload_messages: list[dict[str, object]] = []
        for item in messages:
            if item.role == "user" and not media_attached:
                payload_messages.append(
                    {
                        "role": item.role,
                        "content": [{"type": "text", "text": item.content}, *media_content],
                    }
                )
                media_attached = True
            else:
                payload_messages.append({"role": item.role, "content": item.content})
        if not media_attached:
            payload_messages.append({"role": "user", "content": media_content})
        return self._chat_completion({"messages": payload_messages, "max_tokens": max_tokens or 1800})


class GeminiApiKeyProvider:
    def __init__(self, *, api_key: str, base_url: str, model: str) -> None:
        if not api_key:
            raise ProviderConfigurationError("GEMINI_API_KEY is not configured")
        if not base_url:
            raise ProviderConfigurationError("GEMINI_API_BASE_URL is not configured")
        if not model:
            raise ProviderConfigurationError("GEMINI_MODEL is not configured")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    @staticmethod
    def _inline_data_part(media_part: LLMMediaPart) -> dict[str, object]:
        return {
            "inline_data": {
                "mime_type": media_part.mime_type,
                "data": base64.b64encode(media_part.data).decode("ascii"),
            }
        }

    def _contents_from_messages(
        self,
        messages: Iterable[LLMMessage],
        media_parts: Iterable[LLMMediaPart] = (),
    ) -> tuple[str, list[dict[str, object]]]:
        message_list = list(messages)
        system_text = "\n\n".join(item.content for item in message_list if item.role == "system")
        inline_parts = [self._inline_data_part(item) for item in media_parts]
        media_attached = not inline_parts
        contents: list[dict[str, object]] = []
        for item in message_list:
            if item.role == "system":
                continue
            parts: list[dict[str, object]] = [{"text": item.content}]
            if item.role == "user" and not media_attached:
                parts.extend(inline_parts)
                media_attached = True
            contents.append(
                {
                    "role": "model" if item.role == "assistant" else "user",
                    "parts": parts,
                }
            )
        if not media_attached:
            contents.append({"role": "user", "parts": inline_parts})
        return system_text, contents

    def _generate_content(
        self,
        messages: Iterable[LLMMessage],
        max_tokens: int | None = None,
        media_parts: Iterable[LLMMediaPart] = (),
    ) -> str:
        system_text, contents = self._contents_from_messages(messages, media_parts)
        payload: dict[str, object] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens or 1800},
        }
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        model_path = urllib.parse.quote(self.model.removeprefix("models/"), safe="")
        request = urllib.request.Request(
            f"{self.base_url}/models/{model_path}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ProviderRuntimeError(exc) from exc
        try:
            return str(body["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderRuntimeError("Gemini response did not include candidates[0].content.parts[0].text") from exc

    def chat(self, messages: Iterable[LLMMessage], max_tokens: int | None = None) -> str:
        return self._generate_content(messages, max_tokens=max_tokens)

    def chat_multimodal(
        self,
        messages: Iterable[LLMMessage],
        media_parts: Iterable[LLMMediaPart],
        max_tokens: int | None = None,
    ) -> str:
        return self._generate_content(messages, max_tokens=max_tokens, media_parts=media_parts)


class CodeAssistHttpClient(Protocol):
    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        body: Mapping[str, Any],
    ) -> dict[str, Any]: ...


class UrllibCodeAssistHttpClient:
    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        body: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = _read_http_error(exc)
            raise ProviderRuntimeError(f"Gemini Code Assist request failed ({exc.code}) for {url}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ProviderRuntimeError(f"Gemini Code Assist request failed for {url}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ProviderRuntimeError(f"Gemini Code Assist returned non-object JSON for {url}")
        return payload


class GeminiCliOAuthProvider:
    def __init__(
        self,
        *,
        model: str,
        oauth_credentials_file: str | None = None,
        oauth_credentials_json: str | None = None,
        oauth_credentials_b64: str | None = None,
        google_cloud_project: str | None = None,
        google_cloud_location: str = "global",
        http_client: CodeAssistHttpClient | None = None,
    ) -> None:
        if not model:
            raise ProviderConfigurationError("GEMINI_MODEL is not configured")
        self.model = model
        self.oauth_credentials_file = oauth_credentials_file
        self.oauth_credentials_json = oauth_credentials_json
        self.oauth_credentials_b64 = oauth_credentials_b64
        self.google_cloud_project = google_cloud_project
        self.google_cloud_location = google_cloud_location
        self._http_client = http_client or UrllibCodeAssistHttpClient()
        self._token: str | None = None
        self._code_assist_loaded = False
        self._resolved_project: str | None = None
        self._session_id = str(uuid4())

    def chat(self, messages: Iterable[LLMMessage], max_tokens: int | None = None) -> str:
        self._ensure_code_assist_loaded()
        response = self._post_json(
            "generateContent",
            _to_code_assist_generate_content_request(
                model=self.model,
                project=self._get_resolved_project(),
                messages=messages,
                max_tokens=max_tokens,
                session_id=self._session_id,
            ),
        )
        return _extract_code_assist_text(response)

    def _ensure_code_assist_loaded(self) -> None:
        if self._code_assist_loaded:
            return
        if not self.google_cloud_project:
            raise ProviderConfigurationError("gemini_cli_oauth requires GOOGLE_CLOUD_PROJECT to be configured")
        response = self._post_json(
            "loadCodeAssist",
            {
                "cloudaicompanionProject": self.google_cloud_project,
                "metadata": _code_assist_metadata(self.google_cloud_project),
            },
        )
        self._resolved_project = _optional_str(response.get("cloudaicompanionProject")) or self.google_cloud_project
        self._code_assist_loaded = True

    def _get_resolved_project(self) -> str:
        if not self._resolved_project:
            raise ProviderRuntimeError("Gemini Code Assist project has not been initialized")
        return self._resolved_project

    def _post_json(self, method: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._http_client.post_json(
            _code_assist_method_url(method),
            headers=self._auth_headers(),
            body=body,
        )

    def _auth_headers(self) -> dict[str, str]:
        token = self._token or _load_oauth_access_token(
            oauth_credentials_file=self.oauth_credentials_file,
            oauth_credentials_json=self.oauth_credentials_json,
            oauth_credentials_b64=self.oauth_credentials_b64,
        )
        self._token = token
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }


def _load_oauth_access_token(
    *,
    oauth_credentials_file: str | None,
    oauth_credentials_json: str | None = None,
    oauth_credentials_b64: str | None = None,
) -> str:
    data, path = _load_oauth_credentials_data(
        oauth_credentials_file=oauth_credentials_file,
        oauth_credentials_json=oauth_credentials_json,
        oauth_credentials_b64=oauth_credentials_b64,
    )
    token = _optional_str(data.get("access_token")) or _optional_str(data.get("token"))
    expiry = _parse_expiry(data.get("expiry_date") or data.get("expiry"))
    if token and not _token_is_expired(expiry):
        return token

    refresh_token = _optional_str(data.get("refresh_token"))
    if not refresh_token:
        raise ProviderConfigurationError(
            "Gemini OAuth access token is expired or missing, and credentials do not include refresh_token"
        )

    refreshed = _refresh_oauth_token(data, refresh_token)
    if path is not None:
        _write_refreshed_token_cache(path, data, refreshed)
    return refreshed["access_token"]


def _load_oauth_credentials_data(
    *,
    oauth_credentials_file: str | None,
    oauth_credentials_json: str | None,
    oauth_credentials_b64: str | None,
) -> tuple[dict[str, Any], Path | None]:
    if oauth_credentials_file:
        path = Path(oauth_credentials_file).expanduser()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ProviderConfigurationError(f"Gemini OAuth credentials file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderConfigurationError(f"Gemini OAuth credentials file is not valid JSON: {path}") from exc
        if not isinstance(data, dict):
            raise ProviderConfigurationError(f"Gemini OAuth credentials file must contain a JSON object: {path}")
        return data, path

    if oauth_credentials_json:
        try:
            data = json.loads(oauth_credentials_json)
        except json.JSONDecodeError as exc:
            raise ProviderConfigurationError("GEMINI_OAUTH_CREDENTIALS_JSON is not valid JSON") from exc
        if not isinstance(data, dict):
            raise ProviderConfigurationError("GEMINI_OAUTH_CREDENTIALS_JSON must contain a JSON object")
        return data, None

    if oauth_credentials_b64:
        try:
            decoded = base64.b64decode(oauth_credentials_b64, validate=True).decode("utf-8")
            data = json.loads(decoded)
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderConfigurationError("GEMINI_OAUTH_CREDENTIALS_B64 is not valid base64 JSON") from exc
        if not isinstance(data, dict):
            raise ProviderConfigurationError("GEMINI_OAUTH_CREDENTIALS_B64 must contain a JSON object")
        return data, None

    raise ProviderConfigurationError(
        "gemini_cli_oauth requires GEMINI_OAUTH_CREDENTIALS_FILE, GEMINI_OAUTH_CREDENTIALS_JSON, or GEMINI_OAUTH_CREDENTIALS_B64"
    )


def _refresh_oauth_token(source_data: dict[str, Any], refresh_token: str) -> dict[str, Any]:
    client_id = _optional_str(source_data.get("client_id")) or GEMINI_CLI_OAUTH_CLIENT_ID
    client_secret = _optional_str(source_data.get("client_secret")) or GEMINI_CLI_OAUTH_CLIENT_SECRET
    token_uri = _optional_str(source_data.get("token_uri")) or GOOGLE_OAUTH_TOKEN_URI
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        token_uri,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = _read_http_error(exc)
        raise ProviderRuntimeError(f"Gemini OAuth token refresh failed ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ProviderRuntimeError(f"Gemini OAuth token refresh failed: {exc}") from exc
    if not isinstance(payload, dict) or not _optional_str(payload.get("access_token")):
        raise ProviderRuntimeError("Gemini OAuth token refresh did not return an access_token")
    expires_in = payload.get("expires_in")
    expiry = datetime.now(UTC) + timedelta(seconds=int(expires_in or 3600))
    return {
        "access_token": str(payload["access_token"]),
        "refresh_token": _optional_str(payload.get("refresh_token")) or refresh_token,
        "expiry_date": _format_expiry(expiry),
        "token_type": _optional_str(payload.get("token_type")) or "Bearer",
    }


def _write_refreshed_token_cache(path: Path, source_data: dict[str, Any], refreshed: dict[str, str]) -> None:
    payload = dict(source_data)
    payload.update(refreshed)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _token_is_expired(expiry: datetime | None) -> bool:
    if expiry is None:
        return False
    return datetime.now(UTC) + timedelta(seconds=OAUTH_EXPIRY_SKEW_SECONDS) >= expiry


def _parse_expiry(value: object) -> datetime | None:
    if isinstance(value, int | float):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp, tz=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def _format_expiry(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _code_assist_method_url(method: str) -> str:
    endpoint = os.getenv("CODE_ASSIST_ENDPOINT", CODE_ASSIST_ENDPOINT).rstrip("/")
    version = os.getenv("CODE_ASSIST_API_VERSION") or CODE_ASSIST_API_VERSION
    return f"{endpoint}/{version}:{method}"


def _code_assist_metadata(project: str) -> dict[str, str]:
    return {
        "ideType": "IDE_UNSPECIFIED",
        "platform": "PLATFORM_UNSPECIFIED",
        "pluginType": "GEMINI",
        "duetProject": project,
    }


def _to_code_assist_generate_content_request(
    *,
    model: str,
    project: str,
    messages: Iterable[LLMMessage],
    max_tokens: int | None,
    session_id: str,
) -> dict[str, Any]:
    system_instruction: str | None = None
    contents: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "system":
            system_instruction = message.content if system_instruction is None else f"{system_instruction}\n\n{message.content}"
            continue
        contents.append(
            {
                "role": "model" if message.role == "assistant" else "user",
                "parts": [{"text": message.content}],
            }
        )
    request: dict[str, Any] = {
        "contents": contents,
        "session_id": session_id,
    }
    if system_instruction:
        request["systemInstruction"] = {"role": "user", "parts": [{"text": system_instruction}]}
    if max_tokens is not None:
        request["generationConfig"] = {"maxOutputTokens": max_tokens}
    return {
        "model": model,
        "project": project,
        "user_prompt_id": str(uuid4()),
        "request": request,
    }


def _extract_code_assist_text(response: Mapping[str, Any]) -> str:
    code_assist_response = response.get("response")
    if not isinstance(code_assist_response, Mapping):
        return ""
    candidates = code_assist_response.get("candidates")
    if not isinstance(candidates, list):
        return ""
    chunks: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        content = candidate.get("content")
        if not isinstance(content, Mapping):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if isinstance(part, Mapping) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "".join(chunks)


def _read_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
        data = json.loads(body)
    except (ValueError, OSError):
        return str(exc.reason or "unknown error")[:500]
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"][:500]
        if isinstance(data.get("message"), str):
            return str(data["message"])[:500]
    return str(exc.reason or "unknown error")[:500]


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


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
        return GeminiApiKeyProvider(
            api_key=os.getenv("GEMINI_API_KEY", "") if getattr(resolved, "gemini_api_key_present", False) else "",
            base_url=getattr(
                resolved,
                "gemini_api_base_url",
                "https://generativelanguage.googleapis.com/v1beta",
            ),
            model=getattr(resolved, "gemini_model", "gemini-2.5-flash"),
        )
    if provider_name == "gemini_cli_oauth":
        return GeminiCliOAuthProvider(
            model=getattr(resolved, "gemini_model", "gemini-2.5-flash"),
            oauth_credentials_file=getattr(resolved, "gemini_oauth_credentials_file", None),
            oauth_credentials_json=getattr(resolved, "gemini_oauth_credentials_json", None),
            oauth_credentials_b64=getattr(resolved, "gemini_oauth_credentials_b64", None),
            google_cloud_project=getattr(resolved, "google_cloud_project", None),
            google_cloud_location=getattr(resolved, "google_cloud_location", "global"),
        )
    raise ProviderConfigurationError(f"Unsupported LLM provider: {provider_name}")
