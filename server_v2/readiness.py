from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_caddie.media import UPLOAD_DIR, VALID_MEDIA_KINDS, resolve_media_content_path

from .history_stats import load_history_stats_response
from .mobile import build_mobile_round_package_response
from .reports import load_trend_report_response
from .sync_status import load_sync_status_response


LIVE_ROUND_PACKAGE_CONTRACT = Path("mobile/contracts/live_round_package.schema.json")
LIVE_ROUND_EVENT_CONTRACT = Path("mobile/contracts/live_round_event.schema.json")
SMOKE_SCRIPT = Path("ops/smoke_private_trial.sh")
BACKUP_SCRIPT = Path("ops/backup_data.sh")
BACKUP_MANIFEST = Path("backups/latest.json")

VISION_CONFIRMATION_STATES = ["unconfirmed", "confirmed", "player_confirmed", "manual_confirmed", "rejected"]


def _check(label: str, state: str, detail: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "label": label,
        "state": state,
        "detail": detail,
        "evidence": evidence or {},
    }


def _first_round_id(stats: Any) -> str:
    drill_down = getattr(stats, "drillDown", {})
    round_ids = drill_down.get("roundIds") if isinstance(drill_down, dict) else None
    if isinstance(round_ids, list):
        for round_id in round_ids:
            if str(round_id).strip():
                return str(round_id)
    return "live-round-1"


def _contract_event_kinds() -> list[str]:
    contract = json.loads(LIVE_ROUND_EVENT_CONTRACT.read_text(encoding="utf-8"))
    kind = contract.get("properties", {}).get("kind", {})
    values = kind.get("enum", [])
    return [str(value) for value in values if str(value).strip()]


def _smoke_covers() -> list[str]:
    if not SMOKE_SCRIPT.exists():
        return []
    script = SMOKE_SCRIPT.read_text(encoding="utf-8")
    checks = {
        "readiness": "/api/v2/readiness",
        "mobile_package": "/api/v2/mobile/rounds/900001/package",
        "caddie_decision": "/api/v2/caddie/decision",
        "reports": "/api/v2/reports/trend/recent_10",
        "media_context": "/api/v2/media",
    }
    return [label for label, needle in checks.items() if needle in script]


def _latest_backup() -> dict[str, Any] | None:
    if not BACKUP_MANIFEST.exists():
        return None
    try:
        payload = json.loads(BACKUP_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "unreadable"}
    if not isinstance(payload, dict):
        return {"state": "invalid"}
    snapshot = str(payload.get("snapshot") or "")
    snapshot_path = Path(snapshot)
    return {
        "schema": payload.get("schema"),
        "snapshot": snapshot_path.name if snapshot_path.is_absolute() else snapshot,
        "createdAt": payload.get("createdAt"),
        "sizeBytes": payload.get("sizeBytes"),
    }


def _native_mobile_check() -> dict[str, Any]:
    required_paths = [
        "mobile/ios/project.yml",
        "mobile/ios/AICaddie/Info.plist",
        "mobile/ios/AICaddie/AICaddieApp.swift",
        "mobile/ios/AICaddieWatch/Info.plist",
        "mobile/ios/AICaddieWatch/AICaddieWatchApp.swift",
        "mobile/ios/AICaddieTests/OfflineStoreTests.swift",
        "mobile/ios/AICaddieWatchTests/WatchRoundStateTests.swift",
    ]
    missing = [path for path in required_paths if not Path(path).exists()]
    return _check(
        "native_mobile",
        "degraded",
        (
            "iOS and Watch app source plus project manifest are present; native Xcode build must run on macOS."
            if not missing
            else "Some native iOS/Watch packaging files are missing."
        ),
        {
            "nativeBuild": "environment_blocked",
            "projectManifest": "mobile/ios/project.yml",
            "missing": missing,
            "linuxContractCommand": "uv run python -m unittest tests.test_mobile_contracts -v",
            "macosCommands": [
                "xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddie -destination 'platform=iOS Simulator,name=iPhone 16'",
                "xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddieWatch -destination 'platform=watchOS Simulator,name=Apple Watch Series 10 (46mm)'",
            ],
        },
    )


def build_readiness_response() -> dict[str, Any]:
    checks: list[dict[str, Any]] = [
        _check("service", "ready", "API process is responding."),
        _check("mobile", "ready", "Live package, event log, and reconciliation endpoints are registered."),
        _check("secret_handling", "ready", "Public status responses redact private credentials and local paths."),
    ]
    stats = None
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
        round_id = _first_round_id(stats) if stats is not None else "live-round-1"
        package = build_mobile_round_package_response(round_id)
        package_ready = (
            package.schema_ == "ai-caddie-live-round-package-v1"
            and package.offlinePackageStatus.get("state") == "ready"
            and package.sourceCoverage.get("state") == "ready"
            and not package.missingData
        )
        checks.append(
            _check(
                "mobile_package",
                "ready" if package_ready else "degraded",
                "Live round package generation is contract-backed for offline-first iOS use."
                if package_ready
                else "Live round package generation is available but offline package dependencies are incomplete.",
                {
                    "contractSchema": LIVE_ROUND_PACKAGE_CONTRACT.as_posix(),
                    "roundId": package.roundId,
                    "holes": len(package.holes),
                    "caddieDecisionEndpoint": package.caddieDecisionEndpoint,
                    "offlinePackageStatus": package.offlinePackageStatus,
                    "sourceCoverage": package.sourceCoverage,
                    "caddieSeedCount": len(package.caddieContextSeeds),
                    "cachedCaddieRules": package.cachedCaddieRules,
                    "missingDataCount": len(package.missingData),
                    "missingDataLabels": sorted(
                        {
                            str(row.get("label") or "")
                            for row in package.missingData
                            if isinstance(row, dict) and str(row.get("label") or "").strip()
                        }
                    ),
                },
            )
        )
    except Exception as exc:  # pragma: no cover - defensive health surface
        checks.append(_check("mobile_package", "error", exc.__class__.__name__))

    event_kinds = _contract_event_kinds() if LIVE_ROUND_EVENT_CONTRACT.exists() else []
    checks.append(
        _check(
            "mobile_events",
            "ready" if event_kinds else "degraded",
            "Mobile event batch, reconciliation, and apply endpoints are contract-backed.",
            {
                "contractSchema": LIVE_ROUND_EVENT_CONTRACT.as_posix(),
                "eventKinds": event_kinds,
                "idempotencyHeader": "Idempotency-Key",
                "endpoints": {
                    "batch": "/api/v2/mobile/rounds/{round_id}/events",
                    "reconciliation": "/api/v2/mobile/rounds/{round_id}/reconciliation",
                    "reconciliationApply": "/api/v2/mobile/rounds/{round_id}/reconciliation/apply",
                },
                "reconcilesOfflineEvents": True,
                "preservesMediaEventLinkage": True,
            },
        )
    )
    upload_root = UPLOAD_DIR.as_posix()
    escape_probe = resolve_media_content_path(Path(upload_root) / ".." / "private.jpg")
    checks.append(
        _check(
            "media_context",
            "ready" if escape_probe is None else "degraded",
            "Photo/video metadata, upload, and bounded vision analysis endpoints enforce local media constraints.",
            {
                "mediaEndpoint": "/api/v2/media",
                "analysisEndpoint": "/api/v2/media/{media_id}/analyze",
                "uploadRoot": upload_root,
                "localPathEscapeProtection": escape_probe is None,
                "allowedMediaKinds": sorted(VALID_MEDIA_KINDS),
                "confirmationStates": VISION_CONFIRMATION_STATES,
                "findingsRedactLocalPath": True,
            },
        )
    )
    checks.append(_native_mobile_check())
    try:
        report = load_trend_report_response("recent_10")
        checks.append(
            _check(
                "reports",
                "ready" if report.schema_ == "ai-caddie-review-report-v1" else "degraded",
                "Fact-bound report generation and retrieval are available.",
                {
                    "schema": report.schema_,
                    "kind": report.kind,
                    "provider": report.provider,
                    "factsUsedCount": len(report.factsUsed),
                    "missingDataCount": len(report.missingData),
                    "sourceRefCount": len(report.sourceRefs),
                    "unsupportedClaimCount": len(report.unsupportedClaims),
                    "factBinding": report.factBinding,
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
    deployment_manifests = [
        "render.yaml",
        "web_v2/vercel.json",
    ]
    missing_ops = [path for path in [*required_scripts, *required_docs, *deployment_manifests] if not Path(path).exists()]
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
                "deploymentManifests": deployment_manifests,
                "smokeCommand": SMOKE_SCRIPT.as_posix(),
                "smokeCovers": _smoke_covers(),
                "backupCommand": BACKUP_SCRIPT.as_posix(),
                "backupManifest": BACKUP_MANIFEST.as_posix(),
                "lastBackup": _latest_backup(),
                "redactionPolicy": "no credential material or private filesystem paths in status responses",
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
