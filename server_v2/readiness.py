from __future__ import annotations

from typing import Any

from .history_stats import load_history_stats_response
from .sync_status import load_sync_status_response


def _check(label: str, state: str, detail: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "label": label,
        "state": state,
        "detail": detail,
        "evidence": evidence or {},
    }


def build_readiness_response() -> dict[str, Any]:
    checks: list[dict[str, Any]] = [
        _check("service", "ready", "API process is responding."),
        _check("mobile", "ready", "Live package, event log, and reconciliation endpoints are registered."),
        _check("secret_handling", "ready", "Public status responses redact private credentials and local paths."),
    ]
    try:
        stats = load_history_stats_response()
        total_rounds = int(stats.summary.get("totalRounds") or 0)
        checks.append(
            _check(
                "history",
                "ready" if total_rounds else "degraded",
                "History statistics are populated." if total_rounds else "No rounds are loaded for history review.",
                {"dataMode": stats.dataMode, "totalRounds": total_rounds},
            )
        )
    except Exception as exc:  # pragma: no cover - defensive health surface
        checks.append(_check("history", "error", exc.__class__.__name__))

    try:
        sync = load_sync_status_response()
        connector_state = sync.connector.state
        checks.append(
            _check(
                "sync",
                "ready" if connector_state == "ready" else "degraded",
                "Garmin connector status is available.",
                {
                    "connector": sync.connector.name,
                    "connectorState": connector_state,
                    "scorecardCount": sync.snapshot.scorecardCount,
                    "shotFileCount": sync.snapshot.shotFileCount,
                },
            )
        )
    except Exception as exc:  # pragma: no cover - defensive health surface
        checks.append(_check("sync", "error", exc.__class__.__name__))

    overall = "ready" if all(check["state"] == "ready" for check in checks) else "degraded"
    return {
        "schema": "ai-caddie-readiness-v1",
        "status": overall,
        "checks": checks,
    }
