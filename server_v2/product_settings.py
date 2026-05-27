from __future__ import annotations

from typing import Any

from ai_caddie.config import get_settings
from ai_caddie.connectors.garmin_oauth import build_oauth_feasibility_status


def _provider_state(provider_id: str, configured: bool | None = None) -> str:
    if provider_id == "static":
        return "ready"
    return "configured" if configured else "missing_key"


def build_product_settings_response() -> dict[str, Any]:
    settings = get_settings()
    oauth = build_oauth_feasibility_status()
    providers = [
        {
            "id": "static",
            "label": "Static",
            "state": _provider_state("static"),
            "supports": ["reports", "caddie_explanations", "vision_fallback"],
        },
        {
            "id": "nvidia_nim",
            "label": "NVIDIA NIM",
            "state": _provider_state("nvidia_nim", settings.nvidia_api_key_present),
            "supports": ["reports", "caddie_explanations", "vision"],
        },
        {
            "id": "gemini_api_key",
            "label": "Gemini API",
            "state": _provider_state("gemini_api_key", settings.gemini_api_key_present),
            "supports": ["reports", "caddie_explanations", "vision"],
        },
        {
            "id": "anthropic",
            "label": "Anthropic",
            "state": _provider_state("anthropic", settings.anthropic_api_key_present),
            "supports": ["reports", "caddie_explanations"],
        },
        {
            "id": "gemini_cli_oauth",
            "label": "Gemini CLI OAuth",
            "state": "configured" if settings.gemini_oauth_configured and settings.google_cloud_project else "missing_config",
            "supports": ["reports", "caddie_explanations", "local_development_only"],
            "credentialPolicy": "oauth_token_cache_only",
        },
    ]
    return {
        "schema": "ai-caddie-product-settings-v1",
        "dataSources": [
            {
                "id": "garmin_cn_web_session",
                "label": "Garmin CN Web Session",
                "track": "primary",
                "state": "available",
                "credentialPolicy": "session_material_only",
                "capabilities": ["scorecards", "shot_rows", "course_geometry", "local_snapshots"],
                "actions": [
                    {"label": "Sync status", "endpoint": "/api/v2/sync/status"},
                    {"label": "Import session", "endpoint": "/api/v2/sync/garmin/session"},
                    {"label": "Run sync", "endpoint": "/api/v2/sync/garmin"},
                ],
            },
            {
                "id": "garmin_oauth",
                "label": "Official Garmin OAuth",
                "track": "feasibility",
                "state": "not_syncable",
                "credentialPolicy": "pkce_only_if_golf_data_is_proven",
                "capabilities": ["identity_feasibility", "future_connector_replacement"],
                "feasibilityQuestions": oauth["feasibilityQuestions"],
                "capabilityMatrix": oauth["capabilities"],
                "probe": oauth["probe"],
                "actions": [],
            },
        ],
        "aiProviders": {
            "activeProvider": settings.llm_provider,
            "factBindingRequired": True,
            "providers": providers,
        },
        "liveApps": {
            "ios": {
                "state": "contract_ready",
                "offlineFirst": True,
                "captures": ["gps", "score", "club", "putt", "penalty", "note", "photo", "video"],
                "packageEndpoint": "/api/v2/mobile/rounds/{round_id}/package",
            },
            "watch": {
                "state": "contract_ready",
                "requiresIphoneBridge": True,
                "inputs": ["club", "score", "putt", "penalty"],
            },
            "vision": {
                "state": "bounded_context",
                "confirmationRequired": True,
                "endpoint": "/api/v2/media/{media_id}/analyze",
            },
        },
        "privacy": {
            "noGarminPasswordStorage": True,
            "adminProtectedWrites": True,
            "mediaRedaction": True,
            "localSnapshotsSurviveReauth": True,
            "secretFreeStatusResponses": True,
        },
        "endpoints": {
            "syncStatus": "/api/v2/sync/status",
            "caddieDecision": "/api/v2/caddie/decision",
            "reports": "/api/v2/reports",
            "annotations": "/api/v2/annotations",
            "readiness": "/api/v2/readiness",
        },
    }
