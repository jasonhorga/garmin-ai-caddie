from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ai_caddie.media import (
    MAX_MEDIA_UPLOAD_BYTES_BY_KIND,
    MAX_VIDEO_DURATION_SECONDS,
    UPLOAD_DIR,
    VALID_MEDIA_KINDS,
    resolve_media_content_path,
)
from ai_caddie.course_reference import course_reference_coverage
from ai_caddie.connectors.snapshot import validate_private_snapshot_acceptance

from .history_stats import load_history_stats_response
from .mobile import build_mobile_round_package_response
from .reports import load_trend_report_response
from .sync_status import load_sync_status_response


LIVE_ROUND_PACKAGE_CONTRACT = Path("mobile/contracts/live_round_package.schema.json")
LIVE_ROUND_EVENT_CONTRACT = Path("mobile/contracts/live_round_event.schema.json")
SMOKE_SCRIPT = Path("ops/smoke_private_trial.sh")
SMOKE_EVIDENCE = Path("logs/private_trial_smoke_latest.json")
BACKUP_SCRIPT = Path("ops/backup_data.sh")
BACKUP_MANIFEST = Path("backups/latest.json")
RUNTIME_ROOT = Path(".")
PRIVATE_SNAPSHOT_ACCEPTANCE = Path("data/snapshots/accepted_private_snapshot.json")
BACKUP_MAX_AGE = timedelta(days=7)
SMOKE_EVIDENCE_MAX_AGE = timedelta(days=3)
SNAPSHOT_ACCEPTANCE_MAX_AGE = timedelta(days=14)
NATIVE_BUILD_EVIDENCE = Path("mobile/ios/native_build_evidence.json")
NATIVE_BUILD_EVIDENCE_SCHEMA = "ai-caddie-native-build-evidence-v1"
NATIVE_BUILD_EVIDENCE_MAX_AGE = timedelta(days=14)
EXTERNAL_RELEASE_EVIDENCE = Path("logs/phase6_external_readiness_latest.json")
EXTERNAL_RELEASE_EVIDENCE_SCHEMA = "ai-caddie-phase6-external-readiness-v1"
EXTERNAL_RELEASE_EVIDENCE_MAX_AGE = timedelta(days=3)

VISION_CONFIRMATION_STATES = ["unconfirmed", "confirmed", "player_confirmed", "manual_confirmed", "rejected"]


def _check(label: str, state: str, detail: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "label": label,
        "state": state,
        "detail": detail,
        "evidence": evidence or {},
    }


def _coverage(ready: int, total: int, *, missing: int = 0) -> dict[str, Any]:
    return {
        "ready": ready,
        "total": total,
        "missing": missing,
        "pct": round(ready * 100.0 / total, 1) if total else 0.0,
    }


def _age_hours(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return round((datetime.now(UTC) - parsed.astimezone(UTC)).total_seconds() / 3600.0, 2)


def _summary_int(stats: Any, key: str) -> int | None:
    summary = getattr(stats, "summary", None)
    if not isinstance(summary, dict):
        return None
    try:
        return int(summary.get(key))
    except (TypeError, ValueError):
        return None


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
        return {"state": "missing"}
    try:
        payload = json.loads(BACKUP_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "unreadable"}
    if not isinstance(payload, dict):
        return {"state": "invalid"}
    snapshot = str(payload.get("snapshotPath") or payload.get("snapshot") or "")
    snapshot_path = Path(snapshot)
    state, freshness = _freshness_state(payload.get("createdAt"), BACKUP_MAX_AGE)
    issues = list(freshness.get("issues") or [])
    snapshot_file = _backup_snapshot_file(snapshot_path)
    snapshot_present = bool(snapshot and snapshot_file is not None and snapshot_file.is_file() and not snapshot_file.is_symlink())
    expected_size = _int_or_none(payload.get("sizeBytes"))
    actual_size = snapshot_file.stat().st_size if snapshot_present and snapshot_file is not None else None
    size_matches = expected_size is not None and actual_size == expected_size
    expected_sha256 = str(payload.get("sha256") or "").strip().lower()
    sha256_verified = False
    if payload.get("schema") != "ai-caddie-backup-manifest-v1":
        state = "invalid"
        issues.append("schema_mismatch")
    if not snapshot:
        state = "invalid"
        issues.append("snapshot_missing")
    elif not snapshot_present:
        state = "invalid"
        issues.append("snapshot_file_missing")
    if expected_size is None:
        state = "invalid"
        issues.append("size_missing")
    elif snapshot_present and not size_matches:
        state = "invalid"
        issues.append("size_mismatch")
    if not expected_sha256:
        state = "invalid"
        issues.append("sha256_missing")
    elif snapshot_present:
        sha256_verified = _sha256(snapshot_file) == expected_sha256
        if not sha256_verified:
            state = "invalid"
            issues.append("sha256_mismatch")
    return {
        "state": state,
        "schema": payload.get("schema"),
        "snapshot": snapshot_path.name if snapshot_path.is_absolute() else snapshot,
        "createdAt": payload.get("createdAt"),
        "sizeBytes": expected_size,
        "actualSizeBytes": actual_size,
        "snapshotPresent": snapshot_present,
        "sizeMatches": size_matches,
        "sha256Present": bool(expected_sha256),
        "sha256Verified": sha256_verified,
        "maxAgeHours": int(BACKUP_MAX_AGE.total_seconds() // 3600),
        **freshness,
        "issues": sorted(set(issues)),
    }


def _backup_snapshot_file(snapshot_path: Path) -> Path | None:
    if not str(snapshot_path):
        return None
    if snapshot_path.is_absolute():
        return snapshot_path
    if snapshot_path.exists():
        return snapshot_path
    return BACKUP_MANIFEST.parent / snapshot_path.name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _public_path(path: Path) -> str:
    return path.name if path.is_absolute() else path.as_posix()


def _runtime_path(path: Path) -> Path:
    return path if path.is_absolute() else RUNTIME_ROOT / path


def _parse_utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(value.strip(), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _freshness_state(created_at_value: Any, max_age: timedelta) -> tuple[str, dict[str, Any]]:
    created_at = _parse_utc_datetime(created_at_value)
    if created_at is None:
        return "invalid", {"issues": ["created_at_missing"]}
    now = datetime.now(UTC)
    age = now - created_at
    if created_at - now > timedelta(hours=6):
        return "invalid", {"createdAt": created_at_value, "issues": ["future_created_at"], "ageHours": 0}
    age_hours = round(max(age.total_seconds(), 0.0) / 3600, 2)
    if age > max_age:
        return "stale", {"createdAt": created_at_value, "issues": ["stale"], "ageHours": age_hours}
    return "ready", {"createdAt": created_at_value, "issues": [], "ageHours": age_hours}


def _latest_smoke_evidence() -> dict[str, Any]:
    if not SMOKE_EVIDENCE.exists():
        return {"state": "missing"}
    try:
        payload = json.loads(SMOKE_EVIDENCE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "unreadable"}
    if not isinstance(payload, dict):
        return {"state": "invalid"}
    state, freshness = _freshness_state(payload.get("createdAt"), SMOKE_EVIDENCE_MAX_AGE)
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    admin_checks = payload.get("adminProtectedChecks") if isinstance(payload.get("adminProtectedChecks"), list) else []
    endpoint_count = _int_or_none(payload.get("endpointCount"))
    admin_endpoint_count = _int_or_none(payload.get("adminProtectedEndpointCount"))
    secret_free = payload.get("secretFree") is True
    evidence = {
        "state": state,
        "schema": payload.get("schema"),
        "createdAt": payload.get("createdAt"),
        "baseUrl": payload.get("baseUrl"),
        "checks": [str(check) for check in checks],
        "adminProtectedChecks": [str(check) for check in admin_checks],
        "endpointCount": endpoint_count if endpoint_count is not None else len(checks),
        "adminProtectedEndpointCount": admin_endpoint_count if admin_endpoint_count is not None else len(admin_checks),
        "mediaRoundTrip": payload.get("mediaRoundTrip") is True,
        "secretFree": secret_free,
        "maxAgeHours": int(SMOKE_EVIDENCE_MAX_AGE.total_seconds() // 3600),
        **freshness,
    }
    if payload.get("schema") != "ai-caddie-private-trial-smoke-evidence-v1":
        evidence["state"] = "invalid"
        evidence["issues"] = sorted({*evidence.get("issues", []), "schema_mismatch"})
    if not secret_free:
        evidence["state"] = "invalid"
        evidence["issues"] = sorted({*evidence.get("issues", []), "secret_free_missing"})
    if endpoint_count is None:
        evidence["issues"] = sorted({*evidence.get("issues", []), "endpoint_count_missing"})
    if admin_endpoint_count is None:
        evidence["issues"] = sorted({*evidence.get("issues", []), "admin_endpoint_count_missing"})
    return evidence


def _accepted_private_snapshot_evidence() -> dict[str, Any] | None:
    evidence_path = _runtime_path(PRIVATE_SNAPSHOT_ACCEPTANCE)
    if not evidence_path.exists():
        return None
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "state": "unreadable",
            "evidenceStamp": _public_path(PRIVATE_SNAPSHOT_ACCEPTANCE),
            "issues": ["evidence_unreadable"],
        }
    if not isinstance(payload, dict):
        return {
            "state": "invalid",
            "evidenceStamp": _public_path(PRIVATE_SNAPSHOT_ACCEPTANCE),
            "issues": ["evidence_invalid"],
        }

    state, freshness = _freshness_state(payload.get("acceptedAt"), SNAPSHOT_ACCEPTANCE_MAX_AGE)
    issues = list(freshness.get("issues") or [])
    schema = payload.get("schema")
    if schema != "ai-caddie-private-snapshot-acceptance-v1":
        state = "invalid"
        issues.append("schema_mismatch")
    secret_free = payload.get("secretFree") is True
    if not secret_free:
        state = "invalid"
        issues.append("secret_free_missing")
    snapshot_path = str(payload.get("snapshotPath") or "").strip()
    if not snapshot_path:
        state = "invalid"
        issues.append("snapshot_path_missing")

    public_snapshot_path = _public_path(Path(snapshot_path)) if snapshot_path else None
    return {
        "schema": schema,
        "state": state,
        "acceptedAt": payload.get("acceptedAt"),
        "snapshotPath": public_snapshot_path,
        "secretFree": secret_free,
        "evidenceStamp": _public_path(PRIVATE_SNAPSHOT_ACCEPTANCE),
        "maxAgeHours": int(SNAPSHOT_ACCEPTANCE_MAX_AGE.total_seconds() // 3600),
        **freshness,
        "issues": sorted(set(issues)),
    }


def _native_scheme_evidence(payload: dict[str, Any], key: str, expected_scheme: str) -> tuple[dict[str, Any], list[str]]:
    raw = payload.get(key)
    if not isinstance(raw, dict):
        return {"scheme": expected_scheme, "status": "missing"}, [f"{key}_missing"]

    scheme = str(raw.get("scheme") or expected_scheme)
    status = str(raw.get("status") or "missing")
    evidence: dict[str, Any] = {
        "scheme": scheme,
        "status": status,
    }
    for field in ("destination", "configuration", "sdk", "testCount", "durationSeconds"):
        if field in raw and raw[field] is not None:
            evidence[field] = raw[field]

    issues: list[str] = []
    if scheme != expected_scheme:
        issues.append(f"{key}_scheme_mismatch")
    if status != "passed":
        issues.append(f"{key}_not_passed")
    return evidence, issues


def _native_build_evidence() -> tuple[str, dict[str, Any]]:
    base: dict[str, Any] = {
        "nativeBuild": "environment_blocked",
        "evidenceStamp": _public_path(NATIVE_BUILD_EVIDENCE),
        "evidenceSchema": NATIVE_BUILD_EVIDENCE_SCHEMA,
        "evidenceMaxAgeDays": NATIVE_BUILD_EVIDENCE_MAX_AGE.days,
    }
    if not NATIVE_BUILD_EVIDENCE.exists():
        return "degraded", base

    try:
        payload = json.loads(NATIVE_BUILD_EVIDENCE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        base["nativeBuild"] = "invalid_evidence"
        return "degraded", base
    if not isinstance(payload, dict):
        base["nativeBuild"] = "invalid_evidence"
        return "degraded", base

    created_at = _parse_utc_datetime(payload.get("createdAt"))
    now = datetime.now(UTC)
    issues: list[str] = []
    if payload.get("schema") != NATIVE_BUILD_EVIDENCE_SCHEMA:
        issues.append("schema_mismatch")
    if created_at is None:
        issues.append("created_at_missing")
    elif now - created_at > NATIVE_BUILD_EVIDENCE_MAX_AGE:
        issues.append("stale")
    elif created_at - now > timedelta(hours=6):
        issues.append("future_created_at")

    ios, ios_issues = _native_scheme_evidence(payload, "ios", "AICaddie")
    watch, watch_issues = _native_scheme_evidence(payload, "watch", "AICaddieWatch")
    issues.extend(ios_issues)
    issues.extend(watch_issues)

    evidence = {
        **base,
        "createdAt": payload.get("createdAt"),
        "commit": payload.get("commit"),
        "workflowRunId": payload.get("workflowRunId"),
        "artifactName": payload.get("artifactName"),
        "ios": ios,
        "watch": watch,
        "issues": issues,
    }
    if created_at is not None:
        evidence["ageHours"] = round(max((now - created_at).total_seconds(), 0.0) / 3600, 2)

    if issues:
        evidence["nativeBuild"] = "stale_evidence" if issues == ["stale"] else "invalid_evidence"
        return "degraded", evidence

    evidence["nativeBuild"] = "passed"
    return "ready", evidence


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
    build_state, build_evidence = _native_build_evidence()
    evidence = {
        **build_evidence,
        "projectManifest": "mobile/ios/project.yml",
        "missing": missing,
        "linuxContractCommand": "uv run python -m unittest tests.test_mobile_contracts -v",
        "macosCommands": [
            "xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddie -destination 'platform=iOS Simulator,name=iPhone 16'",
            "xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddieWatch -destination 'platform=watchOS Simulator,name=Apple Watch Series 10 (46mm)'",
        ],
    }
    if missing:
        evidence["nativeBuild"] = "source_missing"
    return _check(
        "native_mobile",
        "ready" if build_state == "ready" and not missing else "degraded",
        (
            "iOS and Watch app source plus a current macOS native test evidence stamp are present."
            if build_state == "ready" and not missing
            else (
                "iOS and Watch app source plus project manifest are present; native Xcode build must run on macOS."
                if not missing
                else "Some native iOS/Watch packaging files are missing."
            )
        ),
        evidence,
    )


def _credential_safe_text(value: Any) -> str:
    text = str(value or "").strip()
    replacements = (
        ("AI_CADDIE_ADMIN_TOKEN", "admin credential"),
        ("GH_TOKEN or GITHUB_TOKEN", "GitHub metadata credential"),
        ("GITHUB_TOKEN", "GitHub metadata credential"),
        ("GH_TOKEN", "GitHub metadata credential"),
        ("TOKEN", "CREDENTIAL"),
        ("Token", "Credential"),
        ("token", "credential"),
    )
    for source, replacement in replacements:
        text = text.replace(source, replacement)
    return text


def _external_release_check_summary(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    label = str(raw.get("label") or "").strip()
    state = str(raw.get("state") or "").strip()
    if not label or not state:
        return None

    summary: dict[str, Any] = {
        "label": label,
        "state": state,
    }
    for key in ("ready", "total"):
        value = _int_or_none(raw.get(key))
        if value is not None:
            summary[key] = value
    for key in ("missing", "unusedConfigured"):
        values = raw.get(key)
        if isinstance(values, list):
            summary[key] = [str(value) for value in values if str(value).strip()]

    evidence = raw.get("evidence")
    safe_evidence: dict[str, Any] = {}
    if isinstance(evidence, dict):
        if label == "github_repo":
            safe_evidence = {
                "public": evidence.get("public") is True,
                "defaultBranch": evidence.get("defaultBranch"),
            }
        elif label == "native_api_base_url_configuration":
            safe_evidence = {
                "repoVariableConfigured": evidence.get("repoVariableConfigured") is True,
                "workflowInputProvided": evidence.get("workflowInputProvided") is True,
                "nativeEnvProvided": evidence.get("nativeEnvProvided") is True,
            }
        elif label == "external_beta_review_feedback":
            safe_evidence = {
                "repoSecretConfigured": evidence.get("repoSecretConfigured") is True,
                "manualFeedbackEmailConfirmed": evidence.get("manualFeedbackEmailConfirmed") is True,
                "manualFeedbackEmailSource": evidence.get("manualFeedbackEmailSource"),
            }
        elif label == "phone_reachable_backend_url":
            safe_evidence = {
                "configured": evidence.get("configured") is True,
                "validPublicHttps": evidence.get("validPublicHttps") is True,
                "host": evidence.get("host"),
                "source": evidence.get("source"),
                "reason": _credential_safe_text(evidence.get("reason")),
            }
        elif label == "backend_probe":
            safe_evidence = {
                "host": evidence.get("host"),
                "healthStatus": evidence.get("healthStatus"),
                "healthSchema": evidence.get("healthSchema"),
                "readinessStatus": evidence.get("readinessStatus"),
                "readinessSchema": evidence.get("readinessSchema"),
                "readinessState": evidence.get("readinessState"),
            }
        elif label == "external_testers":
            safe_evidence = {
                "configuredTesterCount": _int_or_none(evidence.get("configuredTesterCount")) or 0,
                "internalCoverageConfirmed": evidence.get("internalCoverageConfirmed") is True,
                "internalCoverageSource": evidence.get("internalCoverageSource"),
            }
        elif label == "device_install":
            safe_evidence = {
                "installVerified": evidence.get("installVerified") is True,
                "installVerificationSource": evidence.get("installVerificationSource"),
            }
    if safe_evidence:
        summary["evidence"] = {key: value for key, value in safe_evidence.items() if value not in (None, "")}
    return summary


def _external_release_evidence() -> tuple[str, dict[str, Any]]:
    base: dict[str, Any] = {
        "externalRelease": "missing_evidence",
        "evidenceStamp": _public_path(EXTERNAL_RELEASE_EVIDENCE),
        "evidenceSchema": EXTERNAL_RELEASE_EVIDENCE_SCHEMA,
        "maxAgeHours": int(EXTERNAL_RELEASE_EVIDENCE_MAX_AGE.total_seconds() // 3600),
        "command": "uv run python ops/phase6_external_readiness.py --output logs/phase6_external_readiness_latest.json",
        "issues": ["evidence_missing"],
    }
    if not EXTERNAL_RELEASE_EVIDENCE.exists():
        return "degraded", base

    try:
        payload = json.loads(EXTERNAL_RELEASE_EVIDENCE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "degraded", {
            **base,
            "externalRelease": "invalid_evidence",
            "issues": ["evidence_unreadable"],
        }
    if not isinstance(payload, dict):
        return "degraded", {
            **base,
            "externalRelease": "invalid_evidence",
            "issues": ["evidence_invalid"],
        }

    freshness_state, freshness = _freshness_state(payload.get("createdAt"), EXTERNAL_RELEASE_EVIDENCE_MAX_AGE)
    issues = list(freshness.get("issues") or [])
    if payload.get("schema") != EXTERNAL_RELEASE_EVIDENCE_SCHEMA:
        issues.append("schema_mismatch")

    payload_state = str(payload.get("state") or "unknown").strip()
    if payload_state != "ready":
        issues.append(f"phase6_state_{payload_state or 'unknown'}")

    raw_missing_actions = payload.get("missingExternalActions")
    raw_checks = payload.get("checks")
    missing_action_values = raw_missing_actions if isinstance(raw_missing_actions, list) else []
    check_values = raw_checks if isinstance(raw_checks, list) else []
    missing_actions = [
        action
        for action in (_credential_safe_text(value) for value in missing_action_values)
        if action
    ]
    check_summaries = [
        summary
        for summary in (_external_release_check_summary(row) for row in check_values)
        if summary is not None
    ]
    evidence = {
        **base,
        "schema": payload.get("schema"),
        "createdAt": payload.get("createdAt"),
        "state": payload_state,
        "missingExternalActions": list(dict.fromkeys(missing_actions)),
        "checks": check_summaries,
        **freshness,
        "issues": sorted(set(issues)),
    }

    if payload.get("schema") != EXTERNAL_RELEASE_EVIDENCE_SCHEMA or freshness_state == "invalid":
        evidence["externalRelease"] = "invalid_evidence"
        return "degraded", evidence
    if freshness_state == "stale":
        evidence["externalRelease"] = "stale_evidence"
        return "degraded", evidence
    if payload_state != "ready":
        evidence["externalRelease"] = payload_state
        return "degraded", evidence

    evidence["externalRelease"] = "ready"
    return "ready", evidence


def _external_release_check() -> dict[str, Any]:
    state, evidence = _external_release_evidence()
    return _check(
        "external_release",
        state,
        "External Phase 6 release preflight is current and ready."
        if state == "ready"
        else "External Phase 6 release preflight is missing, stale, or incomplete.",
        evidence,
    )


def _offline_seed_quality(package: Any) -> dict[str, Any]:
    seeds = [seed for seed in package.caddieContextSeeds if isinstance(seed, dict)]
    option_count = 0
    seeds_with_options = 0
    selected_count = 0
    selected_confidence_counts = {"high": 0, "medium": 0, "low": 0, "missing": 0}
    selected_coverages: list[float] = []
    missing_labels: set[str] = set()
    source_refs: list[str] = []

    for seed in seeds:
        source_ref = str(seed.get("sourceRef") or "").strip()
        if source_ref:
            source_refs.append(source_ref)
        options = [row for row in seed.get("offlineOptions") or [] if isinstance(row, dict)]
        option_count += len(options)
        if options:
            seeds_with_options += 1
        selected_id = str(seed.get("selectedOfflineOptionId") or "").strip()
        selected = next((row for row in options if str(row.get("id") or "") == selected_id), None)
        if selected is None and options:
            selected = options[0]
        if selected is None:
            selected_confidence_counts["missing"] += 1
            missing_labels.add("selected_offline_option")
            continue
        selected_count += 1
        confidence = str(selected.get("confidence") or "").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "missing"
        selected_confidence_counts[confidence] += 1
        coverage = selected.get("coverage") if isinstance(selected.get("coverage"), dict) else {}
        try:
            selected_coverages.append(round(float(coverage.get("pct") or 0), 1))
        except (TypeError, ValueError):
            selected_coverages.append(0.0)
        for row in selected.get("missingData") or []:
            if isinstance(row, dict) and str(row.get("label") or "").strip():
                missing_labels.add(str(row["label"]))

    seed_count = len(seeds)
    min_selected_coverage = min(selected_coverages) if selected_coverages else 0.0
    avg_selected_coverage = round(sum(selected_coverages) / len(selected_coverages), 1) if selected_coverages else 0.0
    if not seed_count:
        state = "missing"
    elif selected_count < seed_count or selected_confidence_counts["missing"]:
        state = "missing"
    elif selected_confidence_counts["low"] or min_selected_coverage < 50.0:
        state = "degraded"
    else:
        state = "ready"

    return {
        "schema": "ai-caddie-offline-seed-quality-v1",
        "state": state,
        "seedCount": seed_count,
        "seedWithOptions": seeds_with_options,
        "selectedOptionCount": selected_count,
        "optionCount": option_count,
        "selectedConfidenceCounts": selected_confidence_counts,
        "minSelectedCoveragePct": min_selected_coverage,
        "avgSelectedCoveragePct": avg_selected_coverage,
        "missingDataLabels": sorted(missing_labels),
        "sourceRefs": source_refs[:12],
    }


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
                    "lastSuccessfulSyncAt": sync.snapshot.lastSuccessfulSyncAt,
                    "lastRunState": sync.lastRun.state if sync.lastRun else None,
                    "lastRunErrorCode": sync.lastRun.errorCode if sync.lastRun else None,
                    "lastRunUpdatedAt": sync.lastRun.updatedAt if sync.lastRun else None,
                    "lastRunAgeHours": _age_hours(sync.lastRun.updatedAt if sync.lastRun else None),
                    "normalizedShotCount": _summary_int(stats, "shotCount"),
                    "dataFreshness": {
                        "lastSuccessfulSyncAt": sync.snapshot.lastSuccessfulSyncAt,
                        "lastRunUpdatedAt": sync.lastRun.updatedAt if sync.lastRun else None,
                    },
                    "shotCoverage": {
                        "scorecards": sync.snapshot.scorecardCount,
                        "shotFiles": sync.snapshot.shotFileCount,
                    },
                    "geometryCoverage": _coverage(
                        sync.snapshot.geometryReadyCount,
                        sync.snapshot.geometryDependencyCount,
                        missing=sync.snapshot.geometryMissingCount,
                    ),
                },
            )
        )
    except Exception as exc:  # pragma: no cover - defensive health surface
        checks.append(_check("sync", "error", exc.__class__.__name__))

    try:
        coverage = course_reference_coverage()
        total = int(coverage.get("total") or 0)
        ready = int(coverage.get("ready") or 0)
        state = "ready" if total and ready == total else "degraded"
        checks.append(
            _check(
                "course_reference",
                state,
                "Course-reference cache covers played course nines."
                if state == "ready"
                else "Course-reference cache is incomplete for played course nines.",
                coverage,
            )
        )
    except Exception as exc:  # pragma: no cover - defensive health surface
        checks.append(_check("course_reference", "error", exc.__class__.__name__))

    try:
        accepted_evidence = _accepted_private_snapshot_evidence()
        if accepted_evidence is not None:
            ready = accepted_evidence.get("state") == "ready"
            checks.append(
                _check(
                    "private_snapshot_acceptance",
                    "ready" if ready else "degraded",
                    "Latest accepted private snapshot evidence is current and secret-free."
                    if ready
                    else "Accepted private snapshot evidence is missing, stale, or invalid.",
                    accepted_evidence,
                )
            )
        else:
            acceptance = validate_private_snapshot_acceptance()
            checks.append(
                _check(
                    "private_snapshot_acceptance",
                    "ready" if acceptance.get("hardGate") else "degraded",
                    "Latest Garmin CN snapshot passes the private-data hard gate."
                    if acceptance.get("hardGate")
                    else "Latest Garmin CN snapshot does not yet pass the private-data hard gate.",
                    {
                        "schema": acceptance.get("schema"),
                        "state": acceptance.get("state"),
                        "snapshotId": acceptance.get("snapshotId"),
                        "failureLabels": acceptance.get("failureLabels"),
                        "checks": acceptance.get("checks"),
                        "cli": "uv run python ops/accept_private_snapshot.py",
                    },
                )
            )
    except Exception as exc:  # pragma: no cover - defensive health surface
        checks.append(_check("private_snapshot_acceptance", "error", exc.__class__.__name__))

    try:
        round_id = _first_round_id(stats) if stats is not None else "live-round-1"
        package = build_mobile_round_package_response(round_id)
        seed_quality = _offline_seed_quality(package)
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
                    "readinessChecks": package.readinessChecks,
                    "caddieSeedCount": len(package.caddieContextSeeds),
                    "offlineSeedQuality": seed_quality,
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
                    "replay": "/api/v2/mobile/rounds/{round_id}/events/replay",
                    "ack": "/api/v2/mobile/rounds/{round_id}/events/ack",
                    "reconciliation": "/api/v2/mobile/rounds/{round_id}/reconciliation",
                    "reconciliationApply": "/api/v2/mobile/rounds/{round_id}/reconciliation/apply",
                },
                "reconcilesOfflineEvents": True,
                "clientAwareCursor": True,
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
                "maxUploadBytesByKind": MAX_MEDIA_UPLOAD_BYTES_BY_KIND,
                "maxVideoDurationSeconds": MAX_VIDEO_DURATION_SECONDS,
                "confirmationStates": VISION_CONFIRMATION_STATES,
                "findingsRedactLocalPath": True,
            },
        )
    )
    checks.append(_native_mobile_check())
    checks.append(_external_release_check())
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
        "ops/accept_private_snapshot.py",
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
    last_backup = _latest_backup()
    last_smoke = _latest_smoke_evidence()
    ops_issues = []
    if missing_ops:
        ops_issues.append("missing_ops_files")
    if last_backup is None or last_backup.get("state") != "ready":
        ops_issues.append("backup_not_fresh")
    if last_smoke.get("state") != "ready":
        ops_issues.append("smoke_not_fresh")
    checks.append(
        _check(
            "operations",
            "ready" if not ops_issues else "degraded",
            "Private trial operations files, backup, and smoke evidence are current."
            if not ops_issues
            else "Private trial operations need fresh backup/smoke evidence or missing files resolved.",
            {
                "scripts": required_scripts,
                "docs": required_docs,
                "deploymentManifests": deployment_manifests,
                "smokeCommand": SMOKE_SCRIPT.as_posix(),
                "smokeCovers": _smoke_covers(),
                "smokeEvidence": _public_path(SMOKE_EVIDENCE),
                "lastSmoke": last_smoke,
                "backupCommand": BACKUP_SCRIPT.as_posix(),
                "backupManifest": _public_path(BACKUP_MANIFEST),
                "backupMaxAgeHours": int(BACKUP_MAX_AGE.total_seconds() // 3600),
                "smokeMaxAgeHours": int(SMOKE_EVIDENCE_MAX_AGE.total_seconds() // 3600),
                "lastBackup": last_backup,
                "redactionPolicy": "no credential material or private filesystem paths in status responses",
                "missing": missing_ops,
                "issues": ops_issues,
            },
        )
    )

    overall = "ready" if all(check["state"] == "ready" for check in checks) else "degraded"
    return {
        "schema": "ai-caddie-readiness-v1",
        "status": overall,
        "checks": checks,
    }
