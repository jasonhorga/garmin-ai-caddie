from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

from ai_caddie.connectors.redaction import sanitize_secret_text

DEFAULT_AUTH_URL = "https://connect.garmin.com/oauth2Confirm"
DEFAULT_TOKEN_URL = "https://connectapi.garmin.com/di-oauth2-service/oauth/token"
DEFAULT_API_BASE_URL = "https://apis.garmin.com/wellness-api/rest"
DEFAULT_USER_ID_PATH = "/user/id"
DEFAULT_PERMISSIONS_PATH = "/user/permissions"

SECRET_FREE_PROBE_SCHEMA = "ai-caddie-garmin-oauth-probe-v2"
LIVE_PROBE_SCHEMA = "ai-caddie-garmin-oauth-live-probe-v1"


class OAuthProbeError(RuntimeError):
    pass


class UrlLibOAuthClient:
    def post_form(self, url: str, data: dict[str, str], *, timeout_s: float) -> tuple[int, dict[str, Any] | list[Any] | str]:
        encoded = urlencode(data).encode("utf-8")
        request = Request(
            url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        return _read_json_response(request, timeout_s=timeout_s)

    def get_json(self, url: str, access_token: str, *, timeout_s: float) -> tuple[int, dict[str, Any] | list[Any] | str]:
        request = Request(
            url,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            method="GET",
        )
        return _read_json_response(request, timeout_s=timeout_s)


def _read_json_response(request: Request, *, timeout_s: float) -> tuple[int, dict[str, Any] | list[Any] | str]:
    try:
        with urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - user-triggered feasibility probe only.
            body = response.read().decode("utf-8", errors="replace")
            return int(response.status), _parse_json_body(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), _parse_json_body(body)
    except URLError as exc:
        raise OAuthProbeError(sanitize_secret_text(exc.reason)) from exc


def _parse_json_body(body: str) -> dict[str, Any] | list[Any] | str:
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return sanitize_secret_text(body)
    if isinstance(parsed, (dict, list)):
        return parsed
    return sanitize_secret_text(parsed)


def _capability_matrix() -> list[dict[str, Any]]:
    return [
        {
            "key": "scorecards",
            "label": "Golf scorecards",
            "state": "unproven",
            "evidence": "Official Garmin OAuth access to golf scorecard records is not documented for this build.",
            "nextStep": "Verify whether the developer program can read golf scorecard records for a consented account.",
            "canReplaceCnConnector": False,
            "migrationValue": True,
        },
        {
            "key": "golf_shots",
            "label": "Golf GPS shots",
            "state": "unproven",
            "evidence": "The public OAuth track has not proven access to Garmin Golf GPS shot records.",
            "nextStep": "Probe whether activity details or golf-specific endpoints expose shot coordinates and club metadata.",
            "canReplaceCnConnector": False,
            "migrationValue": True,
        },
        {
            "key": "fit_golf_activity",
            "label": "FIT golf activity",
            "state": "unproven",
            "evidence": "FIT download availability for golf score and shot payloads is not confirmed through official OAuth.",
            "nextStep": "Test whether OAuth-authorized activity export includes golf FIT files with scorecard or shot fields.",
            "canReplaceCnConnector": False,
            "migrationValue": True,
        },
        {
            "key": "course_metadata",
            "label": "Course metadata",
            "state": "unproven",
            "evidence": "Course identity and geometry metadata access is not proven through official OAuth.",
            "nextStep": "Check whether official activity metadata includes stable course identifiers or hole context.",
            "canReplaceCnConnector": False,
            "migrationValue": True,
        },
        {
            "key": "identity",
            "label": "Identity",
            "state": "possible",
            "evidence": "OAuth can still be useful for account identity or future migration even if golf data is unavailable.",
            "nextStep": "Keep connector interfaces replaceable so identity-only OAuth can coexist with CN Web Session sync.",
            "canReplaceCnConnector": False,
            "migrationValue": True,
        },
    ]


def _capability_matrix_from_permissions(permissions: list[str], *, identity_proven: bool) -> list[dict[str, Any]]:
    permission_set = {str(item).strip().upper() for item in permissions if str(item).strip()}
    activity_export = "ACTIVITY_EXPORT" in permission_set
    course_import = "COURSE_IMPORT" in permission_set
    rows = _capability_matrix()
    for row in rows:
        key = row["key"]
        if key == "identity" and identity_proven:
            row.update(
                {
                    "state": "proven",
                    "evidence": "OAuth token can fetch the stable Garmin API user id.",
                    "nextStep": "Keep identity as supporting evidence; it does not prove golf scorecard access.",
                }
            )
        elif key == "fit_golf_activity" and activity_export:
            row.update(
                {
                    "state": "needs_golf_fit_validation",
                    "evidence": (
                        "The consented account reports ACTIVITY_EXPORT, and Garmin Activity API documents FIT file access. "
                        "A real golf activity FIT file still must be inspected for scorecard and shot fields."
                    ),
                    "nextStep": "Probe a known golf activity export and decode the FIT payload for score and shot records.",
                }
            )
        elif key == "course_metadata" and course_import:
            row.update(
                {
                    "state": "not_replacement",
                    "evidence": (
                        "The consented account reports COURSE_IMPORT, but Garmin's Courses API is for publishing courses "
                        "to Garmin Connect, not reading Garmin Golf course geometry for history review."
                    ),
                    "nextStep": "Continue using CN Web Session/prodgeometry for course geometry until read access is proven.",
                }
            )
    return rows


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _configured(env: dict[str, str], key: str) -> bool:
    return bool(str(env.get(key) or "").strip())


def _env_value(env: dict[str, str], key: str, default: str | None = None) -> str | None:
    value = str(env.get(key) or "").strip()
    return value or default


def _defaulted_url(env: dict[str, str], key: str, default: str) -> str:
    return _env_value(env, key, default) or default


def _api_endpoint(env: dict[str, str], key: str, default_path: str) -> str:
    explicit = _env_value(env, key)
    if explicit:
        return explicit
    base = _defaulted_url(env, "AI_CADDIE_GARMIN_OAUTH_API_BASE_URL", DEFAULT_API_BASE_URL)
    return urljoin(base.rstrip("/") + "/", default_path.lstrip("/"))


def _redacted_endpoint(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return "<configured endpoint>"


def _base64url_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def generate_pkce_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def build_pkce_authorization_url(
    env: dict[str, str] | None = None,
    *,
    state: str | None = None,
    code_verifier: str | None = None,
) -> dict[str, str]:
    source = dict(os.environ if env is None else env)
    client_id = _env_value(source, "AI_CADDIE_GARMIN_OAUTH_CLIENT_ID")
    redirect_uri = _env_value(source, "AI_CADDIE_GARMIN_OAUTH_REDIRECT_URI")
    if not client_id:
        raise OAuthProbeError("Garmin OAuth client id is required to build a consent URL")
    if not redirect_uri:
        raise OAuthProbeError("Garmin OAuth redirect URI is required to build a consent URL")

    verifier = code_verifier or generate_pkce_verifier()
    challenge = _base64url_sha256(verifier)
    resolved_state = state or secrets.token_urlsafe(32)
    auth_url = _defaulted_url(source, "AI_CADDIE_GARMIN_OAUTH_AUTH_URL", DEFAULT_AUTH_URL)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": resolved_state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return {
        "authorizationUrl": f"{auth_url}?{urlencode(params)}",
        "state": resolved_state,
        "codeVerifier": verifier,
        "codeChallenge": challenge,
        "codeChallengeMethod": "S256",
    }


def _redacted_consent_preview(env: dict[str, str]) -> str | None:
    endpoint = _redacted_endpoint(_defaulted_url(env, "AI_CADDIE_GARMIN_OAUTH_AUTH_URL", DEFAULT_AUTH_URL))
    if not endpoint:
        return None
    return (
        f"{endpoint}?response_type=code"
        "&client_id=<configured>"
        "&redirect_uri=<configured>"
        "&state=<generated>"
        "&code_challenge=<generated>"
        "&code_challenge_method=S256"
    )


def build_oauth_probe_status(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return a secret-free readiness plan for the official Garmin OAuth track."""
    source = dict(os.environ if env is None else env)
    scopes = [item for item in str(source.get("AI_CADDIE_GARMIN_OAUTH_SCOPES") or "").split() if item]
    missing: list[str] = []
    if not _configured(source, "AI_CADDIE_GARMIN_OAUTH_CLIENT_ID"):
        missing.append("client_id")
    if not _configured(source, "AI_CADDIE_GARMIN_OAUTH_REDIRECT_URI"):
        missing.append("redirect_uri")

    state = "not_configured" if missing else "ready_for_manual_consent"
    token_exchange_missing = []
    if missing:
        token_exchange_missing.extend(missing)
    if not _configured(source, "AI_CADDIE_GARMIN_OAUTH_CLIENT_SECRET"):
        token_exchange_missing.append("client_credential")
    if not _configured(source, "AI_CADDIE_GARMIN_OAUTH_CODE"):
        token_exchange_missing.append("authorization_code")
    if not _configured(source, "AI_CADDIE_GARMIN_OAUTH_CODE_VERIFIER"):
        token_exchange_missing.append("code_verifier")

    return {
        "schema": SECRET_FREE_PROBE_SCHEMA,
        "state": state,
        "liveProbeAllowed": _truthy(source.get("AI_CADDIE_GARMIN_OAUTH_LIVE_PROBE")),
        "configured": {
            "clientId": _configured(source, "AI_CADDIE_GARMIN_OAUTH_CLIENT_ID"),
            "redirectUri": _configured(source, "AI_CADDIE_GARMIN_OAUTH_REDIRECT_URI"),
            "clientCredential": _configured(source, "AI_CADDIE_GARMIN_OAUTH_CLIENT_SECRET"),
            "consentEndpoint": True,
            "exchangeEndpoint": True,
            "apiBase": True,
            "requestedScopes": bool(scopes),
            "authorizationCode": _configured(source, "AI_CADDIE_GARMIN_OAUTH_CODE"),
            "codeVerifier": _configured(source, "AI_CADDIE_GARMIN_OAUTH_CODE_VERIFIER"),
        },
        "missing": missing,
        "consentRequest": {
            "method": "GET",
            "endpoint": _redacted_endpoint(_defaulted_url(source, "AI_CADDIE_GARMIN_OAUTH_AUTH_URL", DEFAULT_AUTH_URL)),
            "endpointConfigured": True,
            "parameterKeys": [
                "response_type",
                "client_id",
                "redirect_uri",
                "state",
                "code_challenge",
                "code_challenge_method",
            ],
            "redactedPreview": _redacted_consent_preview(source),
        },
        "tokenExchange": {
            "method": "POST",
            "endpoint": _redacted_endpoint(_defaulted_url(source, "AI_CADDIE_GARMIN_OAUTH_TOKEN_URL", DEFAULT_TOKEN_URL)),
            "ready": not token_exchange_missing,
            "missing": token_exchange_missing,
            "parameterKeys": [
                "grant_type",
                "client_id",
                "client_credential",
                "authorization_code",
                "code_verifier",
                "redirect_uri",
            ],
        },
        "resourceProbe": {
            "userIdEndpoint": _redacted_endpoint(_api_endpoint(source, "AI_CADDIE_GARMIN_OAUTH_USER_ID_URL", DEFAULT_USER_ID_PATH)),
            "permissionsEndpoint": _redacted_endpoint(
                _api_endpoint(source, "AI_CADDIE_GARMIN_OAUTH_PERMISSIONS_URL", DEFAULT_PERMISSIONS_PATH)
            ),
            "checks": ["user_id", "permissions", "golf_data_replacement_gap"],
        },
        "manualSteps": [
            "Register a Garmin OAuth client and redirect URI through the official developer path.",
            "Generate a PKCE consent URL locally and keep the generated code verifier private.",
            "Exchange the one-time authorization code only when live probing is explicitly enabled.",
            "Fetch the Garmin API user id and granted permissions, then separately inspect a real golf activity export if available.",
            "Only promote OAuth from feasibility after scorecards, golf shots, and course metadata are proven.",
        ],
    }


def _permission_values(payload: dict[str, Any] | list[Any] | str) -> list[str]:
    if isinstance(payload, dict):
        raw = payload.get("permissions", [])
    else:
        raw = payload
    if not isinstance(raw, list):
        return []
    return sorted({str(item).strip().upper() for item in raw if str(item).strip()})


def _user_id_fingerprint(payload: dict[str, Any] | list[Any] | str) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = str(payload.get("userId") or payload.get("user_id") or "").strip()
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _public_endpoint_result(status: int, payload: dict[str, Any] | list[Any] | str) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status, "ok": 200 <= status < 300}
    if not result["ok"]:
        result["detail"] = sanitize_secret_text(payload)
    return result


def run_oauth_live_probe(
    env: dict[str, str] | None = None,
    *,
    http_client: Any | None = None,
    timeout_s: float = 10.0,
    now_s: float | None = None,
) -> dict[str, Any]:
    """Exchange a one-time OAuth code and probe identity/permission resources.

    The returned object is deliberately secret-free. It never includes the
    authorization code, verifier, client credential, access token, refresh token,
    or raw Garmin user id.
    """
    source = dict(os.environ if env is None else env)
    status = build_oauth_probe_status(source)
    if not status["liveProbeAllowed"]:
        return {
            "schema": LIVE_PROBE_SCHEMA,
            "state": "disabled",
            "detail": "Set AI_CADDIE_GARMIN_OAUTH_LIVE_PROBE=1 to allow a one-time official OAuth probe.",
            "probe": status,
        }
    missing = list(status["tokenExchange"]["missing"])
    if missing:
        return {
            "schema": LIVE_PROBE_SCHEMA,
            "state": "not_ready",
            "detail": f"Live OAuth probe is missing: {', '.join(missing)}.",
            "missing": missing,
            "probe": status,
        }

    client = http_client or UrlLibOAuthClient()
    token_url = _defaulted_url(source, "AI_CADDIE_GARMIN_OAUTH_TOKEN_URL", DEFAULT_TOKEN_URL)
    form = {
        "grant_type": "authorization_code",
        "client_id": str(source["AI_CADDIE_GARMIN_OAUTH_CLIENT_ID"]),
        "client_secret": str(source["AI_CADDIE_GARMIN_OAUTH_CLIENT_SECRET"]),
        "code": str(source["AI_CADDIE_GARMIN_OAUTH_CODE"]),
        "code_verifier": str(source["AI_CADDIE_GARMIN_OAUTH_CODE_VERIFIER"]),
    }
    redirect_uri = _env_value(source, "AI_CADDIE_GARMIN_OAUTH_REDIRECT_URI")
    if redirect_uri:
        form["redirect_uri"] = redirect_uri

    try:
        token_status, token_payload = client.post_form(token_url, form, timeout_s=timeout_s)
    except Exception as exc:  # pragma: no cover - exercised through returned HTTP failures in tests.
        return {
            "schema": LIVE_PROBE_SCHEMA,
            "state": "error",
            "detail": sanitize_secret_text(exc),
            "stage": "token_exchange",
        }
    token_meta = _public_endpoint_result(token_status, token_payload)
    if not token_meta["ok"] or not isinstance(token_payload, dict) or not token_payload.get("access_token"):
        return {
            "schema": LIVE_PROBE_SCHEMA,
            "state": "error",
            "detail": "Garmin OAuth token exchange did not return a usable bearer credential.",
            "tokenExchange": token_meta,
        }

    access_token = str(token_payload["access_token"])
    user_id_url = _api_endpoint(source, "AI_CADDIE_GARMIN_OAUTH_USER_ID_URL", DEFAULT_USER_ID_PATH)
    permissions_url = _api_endpoint(source, "AI_CADDIE_GARMIN_OAUTH_PERMISSIONS_URL", DEFAULT_PERMISSIONS_PATH)

    user_status, user_payload = client.get_json(user_id_url, access_token, timeout_s=timeout_s)
    permission_status, permission_payload = client.get_json(permissions_url, access_token, timeout_s=timeout_s)
    user_result = _public_endpoint_result(user_status, user_payload)
    permission_result = _public_endpoint_result(permission_status, permission_payload)
    permissions = _permission_values(permission_payload) if permission_result["ok"] else []
    user_fingerprint = _user_id_fingerprint(user_payload) if user_result["ok"] else None
    identity_proven = bool(user_fingerprint)

    user_result.update(
        {
            "idReceived": identity_proven,
            "idFingerprint": user_fingerprint,
        }
    )
    permission_result.update(
        {
            "permissionCount": len(permissions),
            "permissions": permissions,
        }
    )
    expires_in = token_payload.get("expires_in")
    refresh_expires_in = token_payload.get("refresh_token_expires_in")
    now = int(now_s if now_s is not None else time.time())
    result_state = "completed" if user_result["ok"] and permission_result["ok"] else "partial"
    return {
        "schema": LIVE_PROBE_SCHEMA,
        "state": result_state,
        "tokenExchange": {
            "status": token_status,
            "ok": True,
            "bearerReceived": True,
            "refreshCredentialReceived": bool(token_payload.get("refresh_token")),
            "expiresAt": now + int(expires_in) if isinstance(expires_in, int) else None,
            "refreshExpiresAt": now + int(refresh_expires_in) if isinstance(refresh_expires_in, int) else None,
            "scopeReceived": bool(token_payload.get("scope")),
        },
        "resourceProbe": {
            "userId": user_result,
            "permissions": permission_result,
        },
        "capabilities": _capability_matrix_from_permissions(permissions, identity_proven=identity_proven),
        "summary": {
            "identityProven": identity_proven,
            "activityExportGranted": "ACTIVITY_EXPORT" in permissions,
            "courseImportGranted": "COURSE_IMPORT" in permissions,
            "scorecardsProven": False,
            "golfShotsProven": False,
            "canReplaceCnConnector": False,
            "nextStep": "Decode an exported real golf FIT payload before changing connector priority.",
        },
    }


def build_oauth_feasibility_status(env: dict[str, str] | None = None, *, include_probe: bool = True) -> dict[str, Any]:
    status = {
        "name": "garmin_oauth_feasibility",
        "state": "not_available",
        "detail": (
            "Official Garmin OAuth is tracked as a replaceable connector path, "
            "but golf scorecard and shot access are not proven for this product yet."
        ),
        "canSync": False,
        "reauthRequired": False,
        "track": "official_oauth",
        "feasibilityQuestions": [
            "官方 OAuth 能否读取高尔夫记分卡?",
            "官方 OAuth 能否读取高尔夫 GPS 击球记录或 FIT 高尔夫数据?",
            "官方 OAuth 能否提供球场或高尔夫活动元数据以供历史回顾?",
            "若高尔夫数据不可用,官方 OAuth 能否支持身份或未来的连接器迁移?",
        ],
        "capabilities": _capability_matrix(),
    }
    if include_probe:
        status["probe"] = build_oauth_probe_status(env=env)
    return status
