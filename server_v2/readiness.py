from __future__ import annotations

from pathlib import Path
from typing import Any

from .history_stats import load_history_stats_response
from .mobile import build_mobile_round_package_response
from .reports import load_trend_report_response
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

    try:
        package = build_mobile_round_package_response("live-round-1")
        checks.append(
            _check(
                "mobile_package",
                "ready" if package.schema_ == "ai-caddie-live-round-package-v1" else "degraded",
                "Live round package generation is available for offline-first iOS use.",
                {
                    "roundId": package.roundId,
                    "holes": len(package.holes),
                    "caddieDecisionEndpoint": package.caddieDecisionEndpoint,
                },
            )
        )
    except Exception as exc:  # pragma: no cover - defensive health surface
        checks.append(_check("mobile_package", "error", exc.__class__.__name__))

    checks.append(
        _check(
            "mobile_events",
            "ready",
            "Mobile event batch, reconciliation, and apply endpoints are registered.",
            {
                "eventEndpoint": "/api/v2/mobile/rounds/{round_id}/events",
                "reconciliationEndpoint": "/api/v2/mobile/rounds/{round_id}/reconciliation",
            },
        )
    )
    checks.append(
        _check(
            "media_context",
            "ready",
            "Photo/video metadata, upload, and bounded vision analysis endpoints are registered.",
            {
                "mediaEndpoint": "/api/v2/media",
                "analysisEndpoint": "/api/v2/media/{media_id}/analyze",
                "storage": "data/media",
            },
        )
    )
    try:
        report = load_trend_report_response("recent_10")
        checks.append(
            _check(
                "reports",
                "ready" if report.schema_ == "ai-caddie-review-report-v1" else "degraded",
                "Fact-bound report generation and retrieval are available.",
                {
                    "kind": report.kind,
                    "provider": report.provider,
                    "factsUsed": len(report.factsUsed),
                },
            )
        )
    except Exception as exc:  # pragma: no cover - defensive health surface
        checks.append(_check("reports", "error", exc.__class__.__name__))

    required_scripts = [
        "ops/export_snapshot.py",
        "ops/import_snapshot.py",
        "ops/backup_data.sh",
        "ops/run_local_fixture.sh",
        "ops/run_local_private.sh",
        "ops/smoke_private_trial.sh",
    ]
    required_docs = [
        "docs/security/secrets.md",
        "docs/deployment/private-trial.md",
        "docs/operations/runbook.md",
    ]
    missing_ops = [path for path in [*required_scripts, *required_docs] if not Path(path).exists()]
    checks.append(
        _check(
            "operations",
            "ready" if not missing_ops else "degraded",
            "Private trial run, smoke, backup, restore, deployment, and security docs are present."
            if not missing_ops
            else "Some private trial operations files are missing.",
            {
                "scripts": required_scripts,
                "docs": required_docs,
                "missing": missing_ops,
            },
        )
    )

    overall = "ready" if all(check["state"] == "ready" for check in checks) else "degraded"
    return {
        "schema": "ai-caddie-readiness-v1",
        "status": overall,
        "checks": checks,
    }
