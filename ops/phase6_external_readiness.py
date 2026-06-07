#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import ipaddress
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable
from urllib import error, parse, request


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


SCHEMA = "ai-caddie-phase6-external-readiness-v1"
DEFAULT_REPO = "jasonhorga/garmin-ai-caddie"
DEFAULT_BRANCH = "integration/v2"
REQUIRED_SIGNING_SECRETS = (
    "ASC_KEY_ID",
    "ASC_ISSUER_ID",
    "ASC_PRIVATE_KEY",
    "MATCH_GIT_URL",
    "MATCH_GIT_PRIVATE_KEY",
    "MATCH_PASSWORD",
)
LEGACY_UNUSED_SECRETS = ("MATCH_KEYCHAIN_PASSWORD",)
REQUIRED_NATIVE_API_VARIABLE = "AI_CADDIE_API_BASE_URL"
OPTIONAL_EXTERNAL_REVIEW_SECRET = "TESTFLIGHT_FEEDBACK_EMAIL"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _state_from_checks(checks: list[dict[str, Any]]) -> str:
    if all(check.get("state") == "ready" for check in checks):
        return "ready"
    return "incomplete"


def _bool_env(env: dict[str, str], key: str) -> bool:
    return env.get(key, "").strip().lower() in {"1", "true", "yes", "y"}


def _int_env(env: dict[str, str], key: str) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _safe_host(raw_url: str) -> tuple[str | None, str | None]:
    parsed = parse.urlparse(raw_url.strip())
    if parsed.scheme != "https":
        return None, "must be an https URL for phone/TestFlight use"
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return None, "missing URL host"
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return None, "host is local-only and not phone-reachable"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host, None
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return None, "host is not a public address"
    return host, None


def _redacted_url_summary(raw_url: str) -> dict[str, Any]:
    host, reason = _safe_host(raw_url)
    return {
        "configured": bool(raw_url.strip()),
        "validPublicHttps": reason is None,
        "host": host,
        "reason": reason,
    }


def _github_api_get(repo: str, path: str, token: str, *, timeout_s: float = 20.0) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}{path}"
    req = request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-caddie-phase6-readiness",
        },
    )
    with request.urlopen(req, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_github_snapshot(
    *,
    repo: str = DEFAULT_REPO,
    token: str | None = None,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    token = (token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return {"available": False, "reason": "GH_TOKEN or GITHUB_TOKEN is not configured"}
    try:
        repo_payload = _github_api_get(repo, "", token, timeout_s=timeout_s)
        secrets_payload = _github_api_get(repo, "/actions/secrets", token, timeout_s=timeout_s)
        variables_payload = _github_api_get(repo, "/actions/variables", token, timeout_s=timeout_s)
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": f"GitHub API unavailable: {exc.__class__.__name__}"}
    return {
        "available": True,
        "repoPrivate": bool(repo_payload.get("private")),
        "defaultBranch": str(repo_payload.get("default_branch") or ""),
        "secretNames": sorted(str(row.get("name")) for row in secrets_payload.get("secrets", []) if row.get("name")),
        "variableNames": sorted(str(row.get("name")) for row in variables_payload.get("variables", []) if row.get("name")),
    }


def probe_backend_url(
    base_url: str,
    admin_token: str | None = None,
    *,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    root = base_url.rstrip("/")

    def get_json(path: str, *, admin: bool = False) -> tuple[int, dict[str, Any]]:
        headers = {"Accept": "application/json", "User-Agent": "ai-caddie-phase6-readiness"}
        if admin and admin_token:
            headers["X-AI-Caddie-Admin-Token"] = admin_token
        req = request.Request(root + path, headers=headers)
        with request.urlopen(req, timeout=timeout_s) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))

    try:
        health_status, health = get_json("/api/v2/health")
        readiness_status, readiness = get_json("/api/v2/readiness", admin=True)
    except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "state": "degraded",
            "reason": f"backend probe failed: {exc.__class__.__name__}",
            "healthStatus": None,
            "readinessStatus": None,
        }
    return {
        "state": "ready" if health_status == 200 and readiness_status == 200 else "degraded",
        "reason": None if health_status == 200 and readiness_status == 200 else "unexpected backend status",
        "healthStatus": health_status,
        "healthSchema": health.get("schema"),
        "readinessStatus": readiness_status,
        "readinessSchema": readiness.get("schema"),
        "readinessState": readiness.get("status"),
        "adminTokenProvided": bool(admin_token),
    }


def _github_checks(
    github_snapshot: dict[str, Any] | None,
    *,
    native_api_url_configured: bool,
    feedback_email_filled: bool,
) -> list[dict[str, Any]]:
    if not github_snapshot or not github_snapshot.get("available"):
        return [
            {
                "label": "github_metadata",
                "state": "unknown",
                "reason": (github_snapshot or {}).get("reason", "GitHub metadata was not provided"),
            }
        ]

    secret_names = set(github_snapshot.get("secretNames") or [])
    variable_names = set(github_snapshot.get("variableNames") or [])
    missing_signing = [name for name in REQUIRED_SIGNING_SECRETS if name not in secret_names]
    unused_configured = [name for name in LEGACY_UNUSED_SECRETS if name in secret_names]
    native_api_ready = REQUIRED_NATIVE_API_VARIABLE in variable_names or native_api_url_configured
    feedback_ready = OPTIONAL_EXTERNAL_REVIEW_SECRET in secret_names or feedback_email_filled

    return [
        {
            "label": "github_repo",
            "state": "ready"
            if github_snapshot.get("repoPrivate") is False and github_snapshot.get("defaultBranch") == DEFAULT_BRANCH
            else "degraded",
            "reason": None
            if github_snapshot.get("repoPrivate") is False and github_snapshot.get("defaultBranch") == DEFAULT_BRANCH
            else "repo should be public with integration/v2 as default branch for current Actions assumptions",
            "evidence": {
                "public": github_snapshot.get("repoPrivate") is False,
                "defaultBranch": github_snapshot.get("defaultBranch"),
            },
        },
        {
            "label": "signing_secrets",
            "state": "ready" if not missing_signing else "missing",
            "reason": None if not missing_signing else "required signing secret names are missing",
            "ready": len(REQUIRED_SIGNING_SECRETS) - len(missing_signing),
            "total": len(REQUIRED_SIGNING_SECRETS),
            "missing": missing_signing,
            "unusedConfigured": unused_configured,
        },
        {
            "label": "native_api_base_url_configuration",
            "state": "ready" if native_api_ready else "missing",
            "reason": None
            if native_api_ready
            else "set repo variable AI_CADDIE_API_BASE_URL or pass api_base_url when uploading a connected TestFlight build",
            "evidence": {
                "repoVariableConfigured": REQUIRED_NATIVE_API_VARIABLE in variable_names,
                "workflowInputProvided": native_api_url_configured,
            },
        },
        {
            "label": "external_beta_review_feedback",
            "state": "ready" if feedback_ready else "missing",
            "reason": None
            if feedback_ready
            else "set TESTFLIGHT_FEEDBACK_EMAIL or fill Beta App feedback email manually in App Store Connect",
            "evidence": {
                "repoSecretConfigured": OPTIONAL_EXTERNAL_REVIEW_SECRET in secret_names,
                "manualFeedbackEmailConfirmed": feedback_email_filled,
            },
        },
    ]


def build_phase6_external_readiness(
    *,
    env: dict[str, str] | None = None,
    github_snapshot: dict[str, Any] | None = None,
    backend_probe: Callable[[str, str | None], dict[str, Any]] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    env = dict(env or os.environ)
    raw_api_url = (
        env.get("AI_CADDIE_API_BASE_URL")
        or env.get("VITE_AI_CADDIE_API_BASE_URL")
        or env.get("PHASE6_API_BASE_URL")
        or ""
    ).strip()
    api_summary = _redacted_url_summary(raw_api_url)
    checks = _github_checks(
        github_snapshot,
        native_api_url_configured=bool(api_summary["validPublicHttps"]),
        feedback_email_filled=_bool_env(env, "AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_FILLED"),
    )
    if not api_summary["configured"]:
        api_check = {
            "label": "phone_reachable_backend_url",
            "state": "missing",
            "reason": "configure AI_CADDIE_API_BASE_URL or pass PHASE6_API_BASE_URL for the deployed API",
            "evidence": api_summary,
        }
    elif not api_summary["validPublicHttps"]:
        api_check = {
            "label": "phone_reachable_backend_url",
            "state": "degraded",
            "reason": api_summary["reason"],
            "evidence": api_summary,
        }
    else:
        api_check = {
            "label": "phone_reachable_backend_url",
            "state": "ready",
            "reason": None,
            "evidence": api_summary,
        }
    checks.append(api_check)

    if api_check["state"] != "ready":
        checks.append(
            {
                "label": "backend_probe",
                "state": "missing",
                "reason": "backend probe requires a public https API URL",
            }
        )
    elif backend_probe is None:
        checks.append(
            {
                "label": "backend_probe",
                "state": "manual_required",
                "reason": "run with --probe-backend and AI_CADDIE_ADMIN_TOKEN to prove /health and /readiness",
                "evidence": {"host": api_summary["host"]},
            }
        )
    else:
        probe = backend_probe(raw_api_url, env.get("AI_CADDIE_ADMIN_TOKEN"))
        checks.append(
            {
                "label": "backend_probe",
                "state": probe.get("state", "degraded"),
                "reason": probe.get("reason"),
                "evidence": {
                    "host": api_summary["host"],
                    "healthStatus": probe.get("healthStatus"),
                    "healthSchema": probe.get("healthSchema"),
                    "readinessStatus": probe.get("readinessStatus"),
                    "readinessSchema": probe.get("readinessSchema"),
                    "readinessState": probe.get("readinessState"),
                    "adminTokenProvided": bool(env.get("AI_CADDIE_ADMIN_TOKEN")),
                },
            }
        )

    tester_count = _int_env(env, "AI_CADDIE_TESTFLIGHT_TESTER_COUNT")
    tester_coverage_confirmed = _bool_env(env, "AI_CADDIE_TESTFLIGHT_TESTER_COVERAGE_CONFIRMED")
    checks.append(
        {
            "label": "external_testers",
            "state": "ready" if tester_count > 0 or tester_coverage_confirmed else "manual_required",
            "reason": None
            if tester_count > 0 or tester_coverage_confirmed
            else "add external testers or confirm internal tester coverage",
            "evidence": {
                "configuredTesterCount": tester_count,
                "internalCoverageConfirmed": tester_coverage_confirmed,
            },
        }
    )
    checks.append(
        {
            "label": "device_install",
            "state": "ready" if _bool_env(env, "AI_CADDIE_TESTFLIGHT_INSTALL_VERIFIED") else "manual_required",
            "reason": None
            if _bool_env(env, "AI_CADDIE_TESTFLIGHT_INSTALL_VERIFIED")
            else "install the TestFlight build on iPhone/watch and record verification",
        }
    )

    missing_actions = [
        check["reason"]
        for check in checks
        if check.get("state") != "ready" and check.get("reason")
    ]
    payload = {
        "schema": SCHEMA,
        "createdAt": created_at or _utc_now(),
        "state": _state_from_checks(checks),
        "checks": checks,
        "missingExternalActions": missing_actions,
    }
    return payload


def _dump(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check AI Caddie Phase 6 external release readiness.")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub owner/repo to inspect.")
    parser.add_argument("--api-base-url", help="Public deployed API URL to check without printing secrets.")
    parser.add_argument("--tester-count", type=int, help="Number of configured TestFlight testers to record.")
    parser.add_argument("--feedback-email-filled", action="store_true", help="Record manual Beta App feedback email setup.")
    parser.add_argument("--tester-coverage-confirmed", action="store_true", help="Record internal or external tester coverage.")
    parser.add_argument("--install-verified", action="store_true", help="Record that iPhone/watch install was verified.")
    parser.add_argument("--probe-backend", action="store_true", help="Probe /api/v2/health and /api/v2/readiness.")
    parser.add_argument("--no-github", action="store_true", help="Skip GitHub API metadata lookup.")
    parser.add_argument("--no-fail", action="store_true", help="Exit 0 even when readiness is incomplete.")
    args = parser.parse_args(argv)

    env = dict(os.environ)
    if args.api_base_url:
        env["PHASE6_API_BASE_URL"] = args.api_base_url
    if args.tester_count is not None:
        env["AI_CADDIE_TESTFLIGHT_TESTER_COUNT"] = str(args.tester_count)
    if args.feedback_email_filled:
        env["AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_FILLED"] = "1"
    if args.tester_coverage_confirmed:
        env["AI_CADDIE_TESTFLIGHT_TESTER_COVERAGE_CONFIRMED"] = "1"
    if args.install_verified:
        env["AI_CADDIE_TESTFLIGHT_INSTALL_VERIFIED"] = "1"

    github_snapshot = None if args.no_github else fetch_github_snapshot(repo=args.repo)
    backend_probe = probe_backend_url if args.probe_backend else None
    payload = build_phase6_external_readiness(
        env=env,
        github_snapshot=github_snapshot,
        backend_probe=backend_probe,
    )
    _dump(payload)
    return 0 if args.no_fail or payload["state"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
