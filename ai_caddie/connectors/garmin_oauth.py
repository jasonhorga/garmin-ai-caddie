from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit


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


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _configured(env: dict[str, str], key: str) -> bool:
    return bool(str(env.get(key) or "").strip())


def _redacted_endpoint(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return "<configured endpoint>"


def _redacted_consent_preview(env: dict[str, str]) -> str | None:
    endpoint = _redacted_endpoint(env.get("AI_CADDIE_GARMIN_OAUTH_AUTH_URL"))
    if not endpoint:
        return None
    return (
        f"{endpoint}?response_type=code"
        "&client_id=<configured>"
        "&redirect_uri=<configured>"
        "&scope=<configured>"
        "&state=<generated>"
    )


def build_oauth_probe_status(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return a secret-free readiness plan for the official Garmin OAuth track.

    This intentionally does not perform network calls. It records whether the
    product has enough configuration to run a manual authorization probe later.
    """
    source = dict(os.environ if env is None else env)
    scopes = [item for item in str(source.get("AI_CADDIE_GARMIN_OAUTH_SCOPES") or "").split() if item]
    missing: list[str] = []
    if not _configured(source, "AI_CADDIE_GARMIN_OAUTH_CLIENT_ID"):
        missing.append("client_id")
    if not _configured(source, "AI_CADDIE_GARMIN_OAUTH_REDIRECT_URI"):
        missing.append("redirect_uri")
    if not _configured(source, "AI_CADDIE_GARMIN_OAUTH_AUTH_URL"):
        missing.append("consent_endpoint")
    if not _configured(source, "AI_CADDIE_GARMIN_OAUTH_TOKEN_URL"):
        missing.append("exchange_endpoint")
    if not scopes:
        missing.append("scopes")

    state = "not_configured" if missing else "ready_for_manual_consent"
    return {
        "schema": "ai-caddie-garmin-oauth-probe-v1",
        "state": state,
        "liveProbeAllowed": _truthy(source.get("AI_CADDIE_GARMIN_OAUTH_LIVE_PROBE")),
        "configured": {
            "clientId": _configured(source, "AI_CADDIE_GARMIN_OAUTH_CLIENT_ID"),
            "clientCredential": _configured(source, "AI_CADDIE_GARMIN_OAUTH_CLIENT_SECRET"),
            "redirectUri": _configured(source, "AI_CADDIE_GARMIN_OAUTH_REDIRECT_URI"),
            "consentEndpoint": _configured(source, "AI_CADDIE_GARMIN_OAUTH_AUTH_URL"),
            "exchangeEndpoint": _configured(source, "AI_CADDIE_GARMIN_OAUTH_TOKEN_URL"),
            "scopes": bool(scopes),
        },
        "missing": missing,
        "consentRequest": {
            "method": "GET",
            "endpointConfigured": _configured(source, "AI_CADDIE_GARMIN_OAUTH_AUTH_URL"),
            "parameterKeys": ["response_type", "client_id", "redirect_uri", "scope", "state"],
            "redactedPreview": _redacted_consent_preview(source),
        },
        "manualSteps": [
            "Register a Garmin OAuth client and redirect URI through the official developer path.",
            "Configure consent and code-exchange endpoints plus requested scopes in the server environment.",
            "Run a manual consent probe with a private test account and record which golf resources are actually returned.",
            "Only promote OAuth from feasibility after scorecards, golf shots, and course metadata are proven.",
        ],
    }


def build_oauth_feasibility_status(env: dict[str, str] | None = None) -> dict[str, Any]:
    return {
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
            "Can official OAuth access golf scorecards?",
            "Can official OAuth access golf GPS shot records or FIT golf data?",
            "Can official OAuth expose course or golf activity metadata for history review?",
            "Can official OAuth support identity or a future connector migration if golf data is unavailable?",
        ],
        "capabilities": _capability_matrix(),
        "probe": build_oauth_probe_status(env=env),
    }
