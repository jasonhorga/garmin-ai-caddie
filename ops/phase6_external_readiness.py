#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable
from urllib import error, parse, request
import zipfile


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
EXPECTED_HEALTH_SCHEMA = "ai-caddie-health-v2"
EXPECTED_READINESS_SCHEMA = "ai-caddie-readiness-v1"
TESTFLIGHT_TESTERS_WORKFLOW_NAME = "iOS TestFlight Testers"
TESTFLIGHT_READY_EXTERNAL_STATE = "READY_FOR_BETA_SUBMISSION"
TESTFLIGHT_ACTIONS_RUNS_PER_PAGE = 100
TESTFLIGHT_ACTIONS_LOG_SCAN_LIMIT = 50
GITHUB_LOG_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[^\s]+Z\s+")
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
API_URL_ENV_PRIORITY = (
    "AI_CADDIE_API_BASE_URL",
    "PHASE6_API_BASE_URL",
    "VITE_AI_CADDIE_API_BASE_URL",
)
NATIVE_API_URL_SOURCES = {"AI_CADDIE_API_BASE_URL", "PHASE6_API_BASE_URL"}
GITHUB_NATIVE_API_SOURCE = f"github_variable:{REQUIRED_NATIVE_API_VARIABLE}"


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


def _safe_source_label(raw: Any, *, default: str) -> str:
    source = str(raw or "").strip()
    if not source:
        return default
    source = re.sub(r"\s+", " ", source)[:160]
    source = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[redacted_email]", source)
    source = re.sub(r"(?<!\w)/(?:[^\s:/]+/)*[^\s:]*", "[redacted_path]", source)
    if any(
        term in source.lower()
        for term in (
            "access_token",
            "refresh_token",
            "private_key",
            "password",
            "secret",
            "cookie",
            "csrf",
            ".env",
            ".garmin_tokens",
        )
    ):
        return "redacted_source"
    return source


def _confirmation_source(env: dict[str, str], *, value_key: str, source_key: str) -> str | None:
    if not _bool_env(env, value_key):
        return None
    return _safe_source_label(env.get(source_key), default="environment")


def _configured_value_source(env: dict[str, str], *, value_key: str, source_key: str) -> str | None:
    if not env.get(value_key, "").strip():
        return None
    return _safe_source_label(env.get(source_key), default="environment")


def _safe_host(raw_url: str) -> tuple[str | None, str | None]:
    parsed = parse.urlparse(raw_url.strip())
    if parsed.scheme != "https":
        return None, "must be an https URL for phone/TestFlight use"
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return None, "missing URL host"
    if parsed.username or parsed.password:
        return None, "must not include URL credentials"
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        return None, "must be an API origin URL without path, query, or fragment"
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return None, "host is local-only and not phone-reachable"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host, None
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return None, "host is not a public address"
    return host, None


def _configured_api_url(env: dict[str, str]) -> tuple[str, str | None]:
    for source in API_URL_ENV_PRIORITY:
        value = env.get(source, "").strip()
        if value:
            return value, source
    return "", None


def _github_variable_value(github_snapshot: dict[str, Any] | None, name: str) -> str:
    values = (github_snapshot or {}).get("variableValues")
    if not isinstance(values, dict):
        return ""
    return str(values.get(name) or "").strip()


def _redacted_url_summary(raw_url: str, *, source: str | None = None) -> dict[str, Any]:
    if not raw_url.strip():
        return {
            "configured": False,
            "validPublicHttps": False,
            "host": None,
            "source": source,
            "reason": "not configured",
        }
    host, reason = _safe_host(raw_url)
    return {
        "configured": bool(raw_url.strip()),
        "validPublicHttps": reason is None,
        "host": host,
        "source": source,
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


def _github_api_get_bytes(url: str, token: str, *, timeout_s: float = 20.0) -> bytes:
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
        return response.read()


def _github_error_reason(label: str, exc: BaseException) -> str:
    return f"{label} unavailable: {exc.__class__.__name__}"


def _value_after(label: str, text: str) -> str:
    match = re.search(rf"\b{re.escape(label)}=([^\s]+)", text)
    return match.group(1).strip() if match else ""


def _github_log_message(line: str) -> str:
    without_timestamp = GITHUB_LOG_TIMESTAMP_RE.sub("", line.strip())
    return ANSI_ESCAPE_RE.sub("", without_timestamp).strip()


def _testflight_log_summary(run: dict[str, Any], text: str) -> dict[str, Any] | None:
    run_id = str(run.get("id") or "").strip()
    if not run_id:
        return None
    source_prefix = f"github_actions_log:{run_id}"
    summary: dict[str, Any] = {
        "available": True,
        "workflow": TESTFLIGHT_TESTERS_WORKFLOW_NAME,
        "runId": run_id,
        "runCreatedAt": str(run.get("created_at") or ""),
    }
    in_tester_group = False
    app_tester_count = 0
    for line in text.splitlines():
        message = _github_log_message(line)
        if (
            f"externalState={TESTFLIGHT_READY_EXTERNAL_STATE}" in line
            and "state=VALID" in line
            and "betaReviewReady=true" in line
        ):
            build_match = re.search(r"-\s+([^\s]+)\s+\(([^)]+)\)", line)
            summary.update(
                {
                    "build": f"{build_match.group(1)} ({build_match.group(2)})" if build_match else None,
                    "processingState": _value_after("state", line),
                    "externalState": _value_after("externalState", line),
                    "betaReviewReady": _value_after("betaReviewReady", line) == "true",
                    "usesNonExemptEncryption": _value_after("usesNonExemptEncryption", line) == "false",
                    "readyForBetaSubmission": True,
                    "source": f"{source_prefix}:{TESTFLIGHT_READY_EXTERNAL_STATE}",
                }
            )

        if (
            message == "Beta App test info already has description and feedback email."
            or message.startswith("Beta App test info updated on existing ")
            or message.startswith("Beta App test info created for ")
            or (
                message.startswith("- locale=")
                and "descriptionConfigured=true" in message
                and "feedbackEmailConfigured=true" in message
            )
        ):
            summary["feedbackEmailConfigured"] = True
            summary["feedbackEmailSource"] = f"{source_prefix}:beta_app_test_info"

        if message == "Beta App Review submission requested.":
            summary["betaReviewSubmitted"] = True
            summary["betaReviewSubmittedSource"] = f"{source_prefix}:beta_review_submission"

        if "##[group]TestFlight testers" in line:
            in_tester_group = True
            continue
        if in_tester_group and "##[endgroup]" in line:
            in_tester_group = False
            continue
        if in_tester_group and re.search(r"-\s+\S+\s+state=.*\sdevices=", line):
            app_tester_count += 1

        if re.search(r"-\s+Private Trial\b", line) and "internal=false" in line:
            summary["privateTrialGroupObserved"] = True
            summary["privateTrialGroupSource"] = f"{source_prefix}:private_trial_group"

        assignment = re.search(r"Assigned\s+(\d+)\s+external tester\(s\) to group ([^:]+):", line)
        if assignment and assignment.group(2).strip() == "Private Trial":
            summary["privateTrialAssignedTesterCount"] = int(assignment.group(1))
            summary["privateTrialAssignedTesterSource"] = f"{source_prefix}:private_trial_assignment"

    if app_tester_count:
        summary["observedAppTesterCount"] = app_tester_count
        summary["observedAppTesterCountSource"] = f"{source_prefix}:app_testers"
    return summary if len(summary) > 4 else None


def _testflight_summary_from_log_zip(run: dict[str, Any], payload: bytes) -> dict[str, Any] | None:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in archive.namelist():
            if not name.endswith(".txt"):
                continue
            text = archive.read(name).decode("utf-8", errors="replace")
            summary = _testflight_log_summary(run, text)
            if summary is not None:
                return summary
    return None


def fetch_testflight_actions_summary(
    *,
    repo: str = DEFAULT_REPO,
    token: str,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    runs_payload = _github_api_get(
        repo,
        f"/actions/runs?branch={parse.quote(DEFAULT_BRANCH)}&per_page={TESTFLIGHT_ACTIONS_RUNS_PER_PAGE}",
        token,
        timeout_s=timeout_s,
    )
    runs = [row for row in runs_payload.get("workflow_runs", []) if isinstance(row, dict)]
    relevant_runs = [
        run
        for run in runs
        if run.get("name") == TESTFLIGHT_TESTERS_WORKFLOW_NAME
        and run.get("conclusion") == "success"
        and str(run.get("logs_url") or "").strip()
    ]
    aggregate: dict[str, Any] = {
        "available": bool(runs),
        "workflow": TESTFLIGHT_TESTERS_WORKFLOW_NAME,
        "readyForBetaSubmission": False,
    }
    for run in relevant_runs[:TESTFLIGHT_ACTIONS_LOG_SCAN_LIMIT]:
        try:
            logs = _github_api_get_bytes(str(run["logs_url"]), token, timeout_s=timeout_s)
            summary = _testflight_summary_from_log_zip(run, logs)
        except (OSError, error.URLError, TimeoutError, zipfile.BadZipFile):
            summary = None
        if summary is not None:
            if summary.get("readyForBetaSubmission") is True and aggregate.get("readyForBetaSubmission") is not True:
                aggregate.update({
                    key: value
                    for key, value in summary.items()
                    if key
                    in {
                        "runId",
                        "runCreatedAt",
                        "build",
                        "processingState",
                        "externalState",
                        "betaReviewReady",
                        "usesNonExemptEncryption",
                        "readyForBetaSubmission",
                        "source",
                    }
                })
            for key in (
                "privateTrialGroupObserved",
                "privateTrialGroupSource",
                "privateTrialAssignedTesterCount",
                "privateTrialAssignedTesterSource",
                "observedAppTesterCount",
                "observedAppTesterCountSource",
                "feedbackEmailConfigured",
                "feedbackEmailSource",
                "betaReviewSubmitted",
                "betaReviewSubmittedSource",
            ):
                if key in summary and key not in aggregate:
                    aggregate[key] = summary[key]
    if any(
        key in aggregate
        for key in ("source", "privateTrialGroupObserved", "observedAppTesterCount", "betaReviewSubmitted")
    ):
        return aggregate
    return {
        **aggregate,
        "reason": "no successful TestFlight tester log proved READY_FOR_BETA_SUBMISSION",
    }


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
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": f"GitHub API unavailable: {exc.__class__.__name__}"}

    partial_reasons: dict[str, str] = {}
    try:
        secrets_payload = _github_api_get(repo, "/actions/secrets", token, timeout_s=timeout_s)
        secret_names = sorted(str(row.get("name")) for row in secrets_payload.get("secrets", []) if row.get("name"))
    except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        secret_names = []
        partial_reasons["secretNames"] = _github_error_reason("GitHub Actions secrets metadata", exc)

    try:
        variables_payload = _github_api_get(repo, "/actions/variables", token, timeout_s=timeout_s)
        variable_names = sorted(str(row.get("name")) for row in variables_payload.get("variables", []) if row.get("name"))
        variable_values = {
            str(row.get("name")): str(row.get("value") or "").strip()
            for row in variables_payload.get("variables", [])
            if row.get("name")
        }
    except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        variable_names = []
        variable_values = {}
        partial_reasons["variableNames"] = _github_error_reason("GitHub Actions variables metadata", exc)

    try:
        testflight_actions = fetch_testflight_actions_summary(repo=repo, token=token, timeout_s=timeout_s)
    except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        testflight_actions = {
            "available": False,
            "workflow": TESTFLIGHT_TESTERS_WORKFLOW_NAME,
            "readyForBetaSubmission": False,
            "reason": f"GitHub Actions logs unavailable: {exc.__class__.__name__}",
        }
        partial_reasons["testflightActions"] = testflight_actions["reason"]
    return {
        "available": True,
        "repoPrivate": bool(repo_payload.get("private")),
        "defaultBranch": str(repo_payload.get("default_branch") or ""),
        "secretNames": secret_names,
        "secretNamesUnavailableReason": partial_reasons.get("secretNames"),
        "variableNames": variable_names,
        "variableNamesUnavailableReason": partial_reasons.get("variableNames"),
        "variableValues": variable_values,
        "testflightActions": testflight_actions,
        "partialReasons": partial_reasons,
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
    schemas_match = (
        health.get("schema") == EXPECTED_HEALTH_SCHEMA
        and readiness.get("schema") == EXPECTED_READINESS_SCHEMA
    )
    ready = health_status == 200 and readiness_status == 200 and schemas_match
    reason = None
    if not ready:
        reason = (
            "unexpected backend schema"
            if health_status == 200 and readiness_status == 200
            else "unexpected backend status"
        )
    return {
        "state": "ready" if ready else "degraded",
        "reason": reason,
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
    signing_secrets_configured: bool,
    signing_secrets_known: bool,
    signing_secrets_source: str | None,
    native_api_url_configured: bool,
    native_api_source: str | None,
    native_runtime_api_configured: bool,
    native_runtime_api_source: str | None,
    feedback_email_secret_configured: bool,
    feedback_email_secret_known: bool,
    feedback_email_secret_source: str | None,
    feedback_email_filled: bool,
    feedback_email_source: str | None,
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
    secret_names_unavailable_reason = str(github_snapshot.get("secretNamesUnavailableReason") or "").strip()
    variable_names_unavailable_reason = str(github_snapshot.get("variableNamesUnavailableReason") or "").strip()
    native_api_variable_summary = _redacted_url_summary(
        _github_variable_value(github_snapshot, REQUIRED_NATIVE_API_VARIABLE),
        source=GITHUB_NATIVE_API_SOURCE,
    )
    missing_signing = [] if signing_secrets_configured else [
        name for name in REQUIRED_SIGNING_SECRETS if name not in secret_names
    ]
    unused_configured = [name for name in LEGACY_UNUSED_SECRETS if name in secret_names]
    repo_variable_ready = (
        REQUIRED_NATIVE_API_VARIABLE in variable_names
        and native_api_variable_summary["validPublicHttps"] is True
    )
    native_api_ready = repo_variable_ready or native_api_url_configured or native_runtime_api_configured
    repo_feedback_secret_configured = (
        OPTIONAL_EXTERNAL_REVIEW_SECRET in secret_names or feedback_email_secret_configured
    )
    feedback_ready = repo_feedback_secret_configured or feedback_email_filled
    if signing_secrets_configured:
        signing_state = "ready"
        signing_reason = None
    elif secret_names_unavailable_reason and not signing_secrets_known:
        signing_state = "unknown"
        signing_reason = secret_names_unavailable_reason
    elif signing_secrets_known:
        signing_state = "missing"
        signing_reason = "workflow environment reported one or more required signing secrets are missing"
    else:
        signing_state = "ready" if not missing_signing else "missing"
        signing_reason = None if not missing_signing else "required signing secret names are missing"
    if native_api_ready:
        native_api_state = "ready"
        native_api_reason = None
    elif variable_names_unavailable_reason:
        native_api_state = "unknown"
        native_api_reason = variable_names_unavailable_reason
    else:
        native_api_state = "missing"
        native_api_reason = (
            "set repo variable AI_CADDIE_API_BASE_URL, pass api_base_url when uploading, "
            "or confirm the iPhone Backend screen is configured"
        )
    if feedback_ready:
        feedback_state = "ready"
        feedback_reason = None
    elif secret_names_unavailable_reason and not feedback_email_secret_known:
        feedback_state = "unknown"
        feedback_reason = secret_names_unavailable_reason
    else:
        feedback_state = "missing"
        feedback_reason = "set TESTFLIGHT_FEEDBACK_EMAIL or fill Beta App feedback email manually in App Store Connect"

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
            "state": signing_state,
            "reason": signing_reason,
            "ready": len(REQUIRED_SIGNING_SECRETS)
            if signing_secrets_configured
            else (None if secret_names_unavailable_reason else len(REQUIRED_SIGNING_SECRETS) - len(missing_signing)),
            "total": len(REQUIRED_SIGNING_SECRETS),
            "missing": [] if secret_names_unavailable_reason else missing_signing,
            "unusedConfigured": [] if secret_names_unavailable_reason else unused_configured,
            "evidence": {
                "workflowPresenceKnown": signing_secrets_known,
                "workflowPresenceConfigured": signing_secrets_configured,
                "workflowPresenceSource": signing_secrets_source,
            },
        },
        {
            "label": "native_api_base_url_configuration",
            "state": native_api_state,
            "reason": native_api_reason,
            "evidence": {
                "repoVariableConfigured": REQUIRED_NATIVE_API_VARIABLE in variable_names,
                "repoVariableValidPublicHttps": repo_variable_ready,
                "repoVariableHost": native_api_variable_summary["host"],
                "repoVariableMetadataUnavailable": bool(variable_names_unavailable_reason),
                "workflowInputProvided": native_api_source == "PHASE6_API_BASE_URL" and native_api_url_configured,
                "nativeEnvProvided": native_api_source == "AI_CADDIE_API_BASE_URL" and native_api_url_configured,
                "githubVariableProvided": native_api_source == GITHUB_NATIVE_API_SOURCE and native_api_url_configured,
                "runtimeBackendConfigured": native_runtime_api_configured,
                "runtimeBackendSource": native_runtime_api_source,
            },
        },
        {
            "label": "external_beta_review_feedback",
            "state": feedback_state,
            "reason": feedback_reason,
            "evidence": {
                "repoSecretConfigured": repo_feedback_secret_configured,
                "repoSecretMetadataUnavailable": bool(secret_names_unavailable_reason),
                "repoSecretPresenceKnown": feedback_email_secret_known or not secret_names_unavailable_reason,
                "repoSecretPresenceSource": feedback_email_secret_source,
                "manualFeedbackEmailConfirmed": feedback_email_filled,
                "manualFeedbackEmailSource": feedback_email_source,
            },
        },
    ]


def _github_beta_review_ready_source(github_snapshot: dict[str, Any] | None) -> tuple[bool, str | None]:
    actions = (github_snapshot or {}).get("testflightActions")
    if not isinstance(actions, dict):
        return False, None
    if actions.get("readyForBetaSubmission") is not True:
        return False, None
    source = str(actions.get("source") or "").strip()
    return True, source or "github_actions_log"


def _github_feedback_email_source(github_snapshot: dict[str, Any] | None) -> tuple[bool, str | None]:
    actions = (github_snapshot or {}).get("testflightActions")
    if not isinstance(actions, dict):
        return False, None
    if actions.get("feedbackEmailConfigured") is not True:
        return False, None
    source = str(actions.get("feedbackEmailSource") or "").strip()
    return True, source or "github_actions_log:beta_app_test_info"


def _github_beta_review_submission_source(github_snapshot: dict[str, Any] | None) -> tuple[bool, str | None]:
    actions = (github_snapshot or {}).get("testflightActions")
    if not isinstance(actions, dict):
        return False, None
    if actions.get("betaReviewSubmitted") is not True:
        return False, None
    source = str(actions.get("betaReviewSubmittedSource") or "").strip()
    return True, source or "github_actions_log:beta_review_submission"


def _github_testflight_tester_observations(github_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    actions = (github_snapshot or {}).get("testflightActions")
    if not isinstance(actions, dict):
        return {}
    observed_count = _int_env({"value": str(actions.get("observedAppTesterCount") or "")}, "value")
    assigned_count = _int_env({"value": str(actions.get("privateTrialAssignedTesterCount") or "")}, "value")
    return {
        "observedAppTesterCount": observed_count,
        "observedAppTesterCountSource": actions.get("observedAppTesterCountSource"),
        "privateTrialGroupObserved": actions.get("privateTrialGroupObserved") is True,
        "privateTrialGroupSource": actions.get("privateTrialGroupSource"),
        "privateTrialAssignedTesterCount": assigned_count,
        "privateTrialAssignedTesterSource": actions.get("privateTrialAssignedTesterSource"),
    }


def build_phase6_external_readiness(
    *,
    env: dict[str, str] | None = None,
    github_snapshot: dict[str, Any] | None = None,
    backend_probe: Callable[[str, str | None], dict[str, Any]] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    env = dict(env or os.environ)
    raw_api_url, api_url_source = _configured_api_url(env)
    if not raw_api_url:
        raw_api_url = _github_variable_value(github_snapshot, REQUIRED_NATIVE_API_VARIABLE)
        api_url_source = GITHUB_NATIVE_API_SOURCE if raw_api_url else None
    api_summary = _redacted_url_summary(raw_api_url, source=api_url_source)
    native_api_url_configured = bool(
        api_summary["validPublicHttps"]
        and api_url_source in {*NATIVE_API_URL_SOURCES, GITHUB_NATIVE_API_SOURCE}
    )
    native_runtime_api_configured = _bool_env(env, "AI_CADDIE_NATIVE_RUNTIME_API_CONFIGURED")
    native_runtime_api_source = _confirmation_source(
        env,
        value_key="AI_CADDIE_NATIVE_RUNTIME_API_CONFIGURED",
        source_key="AI_CADDIE_NATIVE_RUNTIME_API_SOURCE",
    )
    signing_secrets_known = "AI_CADDIE_SIGNING_SECRETS_CONFIGURED" in env
    signing_secrets_configured = _bool_env(env, "AI_CADDIE_SIGNING_SECRETS_CONFIGURED")
    signing_secrets_source = (
        _safe_source_label(env.get("AI_CADDIE_SIGNING_SECRETS_SOURCE"), default="environment")
        if signing_secrets_known
        else None
    )
    feedback_email_secret_known = "AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_SECRET_CONFIGURED" in env
    feedback_email_secret_configured = _bool_env(
        env,
        "AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_SECRET_CONFIGURED",
    )
    feedback_email_secret_source = (
        _safe_source_label(
            env.get("AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_SECRET_SOURCE"),
            default="environment",
        )
        if feedback_email_secret_known
        else None
    )
    beta_review_ready = _bool_env(env, "AI_CADDIE_TESTFLIGHT_BETA_REVIEW_READY")
    beta_review_submitted = _bool_env(env, "AI_CADDIE_TESTFLIGHT_BETA_REVIEW_SUBMITTED")
    github_beta_review_ready, github_beta_review_ready_source = _github_beta_review_ready_source(github_snapshot)
    github_feedback_email_filled, github_feedback_email_source = _github_feedback_email_source(github_snapshot)
    github_beta_review_submitted, github_beta_review_submission_source = (
        _github_beta_review_submission_source(github_snapshot)
    )
    beta_review_ready_source = _confirmation_source(
        env,
        value_key="AI_CADDIE_TESTFLIGHT_BETA_REVIEW_READY",
        source_key="AI_CADDIE_TESTFLIGHT_BETA_REVIEW_READY_SOURCE",
    )
    beta_review_submission_source = _confirmation_source(
        env,
        value_key="AI_CADDIE_TESTFLIGHT_BETA_REVIEW_SUBMITTED",
        source_key="AI_CADDIE_TESTFLIGHT_BETA_REVIEW_SOURCE",
    ) or github_beta_review_submission_source
    beta_review_submitted = beta_review_submitted or github_beta_review_submitted
    beta_review_ready = beta_review_ready or beta_review_submitted or github_beta_review_ready
    beta_review_ready_source = (
        beta_review_ready_source
        or beta_review_submission_source
        or github_beta_review_ready_source
    )
    feedback_email_filled = (
        _bool_env(env, "AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_FILLED")
        or github_feedback_email_filled
        or beta_review_submitted
    )
    feedback_email_source = _confirmation_source(
        env,
        value_key="AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_FILLED",
        source_key="AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_SOURCE",
    ) or github_feedback_email_source or beta_review_submission_source
    checks = _github_checks(
        github_snapshot,
        signing_secrets_configured=signing_secrets_configured,
        signing_secrets_known=signing_secrets_known,
        signing_secrets_source=signing_secrets_source,
        native_api_url_configured=native_api_url_configured,
        native_api_source=api_url_source,
        native_runtime_api_configured=native_runtime_api_configured,
        native_runtime_api_source=native_runtime_api_source,
        feedback_email_secret_configured=feedback_email_secret_configured,
        feedback_email_secret_known=feedback_email_secret_known,
        feedback_email_secret_source=feedback_email_secret_source,
        feedback_email_filled=feedback_email_filled,
        feedback_email_source=feedback_email_source,
    )
    checks.append(
        {
            "label": "external_beta_review_submission_ready",
            "state": "ready" if beta_review_ready or beta_review_submitted else "manual_required",
            "reason": None
            if beta_review_ready or beta_review_submitted
            else "confirm App Store Connect shows READY_FOR_BETA_SUBMISSION before external Beta App Review",
            "evidence": {
                "readyForSubmission": beta_review_ready or beta_review_submitted,
                "source": beta_review_ready_source or beta_review_submission_source,
            },
        }
    )
    checks.append(
        {
            "label": "external_beta_review_submission",
            "state": "ready" if beta_review_submitted else "manual_required",
            "reason": None
            if beta_review_submitted
            else (
                "submit external Beta App Review"
                if beta_review_ready
                else "confirm READY_FOR_BETA_SUBMISSION, then submit external Beta App Review"
            ),
            "evidence": {
                "submittedOrExternallyReady": beta_review_submitted,
                "source": beta_review_submission_source,
            },
        }
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
    elif not env.get("AI_CADDIE_ADMIN_TOKEN", "").strip():
        checks.append(
            {
                "label": "backend_probe",
                "state": "missing",
                "reason": "AI_CADDIE_ADMIN_TOKEN is required to prove authenticated /api/v2/readiness",
                "evidence": {"host": api_summary["host"], "adminTokenProvided": False},
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
    tester_observations = _github_testflight_tester_observations(github_snapshot)
    assigned_tester_count = int(tester_observations.get("privateTrialAssignedTesterCount") or 0)
    tester_coverage_source = _confirmation_source(
        env,
        value_key="AI_CADDIE_TESTFLIGHT_TESTER_COVERAGE_CONFIRMED",
        source_key="AI_CADDIE_TESTFLIGHT_TESTER_COVERAGE_SOURCE",
    )
    testers_ready = tester_count > 0 or tester_coverage_confirmed or assigned_tester_count > 0
    checks.append(
        {
            "label": "external_testers",
            "state": "ready" if testers_ready else "manual_required",
            "reason": None
            if testers_ready
            else (
                "confirm target testers are assigned to Private Trial or confirm internal tester coverage"
                if tester_observations.get("observedAppTesterCount")
                else "add external testers or confirm internal tester coverage"
            ),
            "evidence": {
                "configuredTesterCount": tester_count,
                "configuredTesterCountSource": _configured_value_source(
                    env,
                    value_key="AI_CADDIE_TESTFLIGHT_TESTER_COUNT",
                    source_key="AI_CADDIE_TESTFLIGHT_TESTER_COUNT_SOURCE",
                ),
                "internalCoverageConfirmed": tester_coverage_confirmed,
                "internalCoverageSource": tester_coverage_source,
                **tester_observations,
            },
        }
    )
    install_verified = _bool_env(env, "AI_CADDIE_TESTFLIGHT_INSTALL_VERIFIED")
    checks.append(
        {
            "label": "device_install",
            "state": "ready" if install_verified else "manual_required",
            "reason": None
            if install_verified
            else "install the TestFlight build on iPhone/watch and record verification",
            "evidence": {
                "installVerified": install_verified,
                "installVerificationSource": _confirmation_source(
                    env,
                    value_key="AI_CADDIE_TESTFLIGHT_INSTALL_VERIFIED",
                    source_key="AI_CADDIE_TESTFLIGHT_INSTALL_SOURCE",
                ),
            },
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


def _write_output(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check AI Caddie Phase 6 external release readiness.")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub owner/repo to inspect.")
    parser.add_argument("--api-base-url", help="Public deployed API URL to check without printing secrets.")
    parser.add_argument("--output", type=Path, help="Write the JSON evidence to this path after printing it.")
    parser.add_argument(
        "--assigned-tester-count",
        type=int,
        help="Number of target testers confirmed assigned to Private Trial or covered internally.",
    )
    parser.add_argument(
        "--assigned-tester-source",
        help="Safe evidence label for --assigned-tester-count, for example app_store_connect_private_trial_group.",
    )
    parser.add_argument(
        "--tester-count",
        type=int,
        help="Compatibility alias for --assigned-tester-count; do not use app-level tester record counts.",
    )
    parser.add_argument("--feedback-email-filled", action="store_true", help="Record manual Beta App feedback email setup.")
    parser.add_argument("--feedback-email-source", help="Safe evidence label for --feedback-email-filled.")
    parser.add_argument(
        "--beta-review-ready",
        action="store_true",
        help="Record that App Store Connect shows READY_FOR_BETA_SUBMISSION.",
    )
    parser.add_argument("--beta-review-ready-source", help="Safe evidence label for --beta-review-ready.")
    parser.add_argument(
        "--beta-review-submitted",
        action="store_true",
        help="Record external Beta App Review submission or external testing readiness.",
    )
    parser.add_argument("--beta-review-source", help="Safe evidence label for --beta-review-submitted.")
    parser.add_argument(
        "--native-runtime-api-configured",
        action="store_true",
        help="Record that the TestFlight app Backend screen is configured with the deployed API origin.",
    )
    parser.add_argument("--native-runtime-api-source", help="Safe evidence label for --native-runtime-api-configured.")
    parser.add_argument("--tester-coverage-confirmed", action="store_true", help="Record internal or external tester coverage.")
    parser.add_argument("--tester-coverage-source", help="Safe evidence label for --tester-coverage-confirmed.")
    parser.add_argument("--install-verified", action="store_true", help="Record that iPhone/watch install was verified.")
    parser.add_argument("--install-source", help="Safe evidence label for --install-verified.")
    parser.add_argument("--probe-backend", action="store_true", help="Probe /api/v2/health and /api/v2/readiness.")
    parser.add_argument("--no-github", action="store_true", help="Skip GitHub API metadata lookup.")
    parser.add_argument("--no-fail", action="store_true", help="Exit 0 even when readiness is incomplete.")
    args = parser.parse_args(argv)

    env = dict(os.environ)
    if args.api_base_url:
        env["PHASE6_API_BASE_URL"] = args.api_base_url
    assigned_tester_count = args.assigned_tester_count
    assigned_tester_source = args.assigned_tester_source or "cli_arg:assigned_tester_count"
    if assigned_tester_count is None and args.tester_count is not None:
        assigned_tester_count = args.tester_count
        assigned_tester_source = args.assigned_tester_source or "cli_arg:tester_count_confirmed_target"
    if assigned_tester_count is not None:
        env["AI_CADDIE_TESTFLIGHT_TESTER_COUNT"] = str(assigned_tester_count)
        env["AI_CADDIE_TESTFLIGHT_TESTER_COUNT_SOURCE"] = assigned_tester_source
    if args.feedback_email_filled:
        env["AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_FILLED"] = "1"
        env["AI_CADDIE_TESTFLIGHT_FEEDBACK_EMAIL_SOURCE"] = args.feedback_email_source or "cli_flag"
    if args.beta_review_ready:
        env["AI_CADDIE_TESTFLIGHT_BETA_REVIEW_READY"] = "1"
        env["AI_CADDIE_TESTFLIGHT_BETA_REVIEW_READY_SOURCE"] = args.beta_review_ready_source or "cli_flag"
    if args.beta_review_submitted:
        env["AI_CADDIE_TESTFLIGHT_BETA_REVIEW_SUBMITTED"] = "1"
        env["AI_CADDIE_TESTFLIGHT_BETA_REVIEW_SOURCE"] = args.beta_review_source or "cli_flag"
    if args.native_runtime_api_configured:
        env["AI_CADDIE_NATIVE_RUNTIME_API_CONFIGURED"] = "1"
        env["AI_CADDIE_NATIVE_RUNTIME_API_SOURCE"] = args.native_runtime_api_source or "cli_flag"
    if args.tester_coverage_confirmed:
        env["AI_CADDIE_TESTFLIGHT_TESTER_COVERAGE_CONFIRMED"] = "1"
        env["AI_CADDIE_TESTFLIGHT_TESTER_COVERAGE_SOURCE"] = args.tester_coverage_source or "cli_flag"
    if args.install_verified:
        env["AI_CADDIE_TESTFLIGHT_INSTALL_VERIFIED"] = "1"
        env["AI_CADDIE_TESTFLIGHT_INSTALL_SOURCE"] = args.install_source or "cli_flag"

    github_snapshot = None if args.no_github else fetch_github_snapshot(repo=args.repo)
    backend_probe = probe_backend_url if args.probe_backend else None
    payload = build_phase6_external_readiness(
        env=env,
        github_snapshot=github_snapshot,
        backend_probe=backend_probe,
    )
    _dump(payload)
    if args.output:
        _write_output(args.output, payload)
    return 0 if args.no_fail or payload["state"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
