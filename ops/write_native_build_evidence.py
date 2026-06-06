from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any


SCHEMA = "ai-caddie-native-build-evidence-v1"
DEFAULT_OUTPUT = Path("mobile/ios/native_build_evidence.json")
DEFAULT_ARTIFACT_NAME = "native-build-evidence"
IOS_SCHEME = "AICaddie"
WATCH_SCHEME = "AICaddieWatch"

PRIVATE_VALUE_MARKERS = [
    "/users/",
    "/home/",
    "\\users\\",
    ".garmin_tokens",
    "authorization",
    "cookie",
    "csrf",
    "password",
    "secret",
    "token",
]


def _utc_now_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_public_string(label: str, value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    lowered = normalized.lower()
    if any(marker in lowered for marker in PRIVATE_VALUE_MARKERS):
        raise ValueError(f"{label} contains private or secret-looking material")
    return normalized


def _optional_int(value: int | str | None) -> int | None:
    if value is None or value == "":
        return None
    parsed = int(value)
    if parsed < 0:
        raise ValueError("numeric evidence fields must be non-negative")
    return parsed


def _optional_float(value: float | str | None) -> float | None:
    if value is None or value == "":
        return None
    parsed = float(value)
    if parsed < 0:
        raise ValueError("numeric evidence fields must be non-negative")
    return round(parsed, 3)


def _scheme_evidence(
    *,
    scheme: str,
    status: str,
    destination: str | None,
    configuration: str | None = None,
    sdk: str | None = None,
    test_count: int | str | None = None,
    duration_seconds: float | str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scheme": scheme,
        "status": _validate_public_string("status", status) or "missing",
    }
    optional_fields = {
        "destination": _validate_public_string("destination", destination),
        "configuration": _validate_public_string("configuration", configuration),
        "sdk": _validate_public_string("sdk", sdk),
        "testCount": _optional_int(test_count),
        "durationSeconds": _optional_float(duration_seconds),
    }
    for key, value in optional_fields.items():
        if value is not None:
            payload[key] = value
    return payload


def build_native_build_evidence(
    *,
    created_at: str | None = None,
    commit: str | None = None,
    workflow_run_id: str | None = None,
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    ios_status: str = "passed",
    watch_status: str = "passed",
    ios_destination: str | None = None,
    watch_destination: str | None = None,
    ios_configuration: str | None = None,
    watch_configuration: str | None = None,
    ios_sdk: str | None = None,
    watch_sdk: str | None = None,
    ios_test_count: int | str | None = None,
    watch_test_count: int | str | None = None,
    ios_duration_seconds: float | str | None = None,
    watch_duration_seconds: float | str | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "createdAt": _validate_public_string("created_at", created_at) or _utc_now_stamp(),
        "commit": _validate_public_string("commit", commit),
        "workflowRunId": _validate_public_string("workflow_run_id", workflow_run_id),
        "artifactName": _validate_public_string("artifact_name", artifact_name) or DEFAULT_ARTIFACT_NAME,
        "ios": _scheme_evidence(
            scheme=IOS_SCHEME,
            status=ios_status,
            destination=ios_destination,
            configuration=ios_configuration,
            sdk=ios_sdk,
            test_count=ios_test_count,
            duration_seconds=ios_duration_seconds,
        ),
        "watch": _scheme_evidence(
            scheme=WATCH_SCHEME,
            status=watch_status,
            destination=watch_destination,
            configuration=watch_configuration,
            sdk=watch_sdk,
            test_count=watch_test_count,
            duration_seconds=watch_duration_seconds,
        ),
    }


def write_native_build_evidence(*, output_path: Path | str = DEFAULT_OUTPUT, payload: dict[str, Any]) -> Path:
    output = Path(output_path)
    _validate_public_string("output_path", output.as_posix())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def _env(name: str) -> str | None:
    return os.environ.get(name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the macOS native iOS/Watch build evidence stamp.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Evidence JSON output path")
    parser.add_argument("--created-at", default=None, help="UTC ISO timestamp; defaults to now")
    parser.add_argument("--commit", default=_env("GITHUB_SHA"), help="Commit SHA; defaults to GITHUB_SHA")
    parser.add_argument("--workflow-run-id", default=_env("GITHUB_RUN_ID"), help="Workflow run id; defaults to GITHUB_RUN_ID")
    parser.add_argument("--artifact-name", default=DEFAULT_ARTIFACT_NAME, help="Uploaded artifact name")
    parser.add_argument("--ios-status", default="passed", help="AICaddie xcodebuild status")
    parser.add_argument("--watch-status", default="passed", help="AICaddieWatch xcodebuild status")
    parser.add_argument("--ios-destination", default=_env("IOS_DESTINATION"), help="iOS simulator destination")
    parser.add_argument("--watch-destination", default=_env("WATCH_DESTINATION"), help="watchOS simulator destination")
    parser.add_argument("--ios-configuration", default=None, help="Optional iOS build configuration")
    parser.add_argument("--watch-configuration", default=None, help="Optional watchOS build configuration")
    parser.add_argument("--ios-sdk", default=None, help="Optional iOS SDK")
    parser.add_argument("--watch-sdk", default=None, help="Optional watchOS SDK")
    parser.add_argument("--ios-test-count", default=None, help="Optional iOS test count")
    parser.add_argument("--watch-test-count", default=None, help="Optional watchOS test count")
    parser.add_argument("--ios-duration-seconds", default=None, help="Optional iOS test duration")
    parser.add_argument("--watch-duration-seconds", default=None, help="Optional watchOS test duration")
    args = parser.parse_args(argv)

    payload = build_native_build_evidence(
        created_at=args.created_at,
        commit=args.commit,
        workflow_run_id=args.workflow_run_id,
        artifact_name=args.artifact_name,
        ios_status=args.ios_status,
        watch_status=args.watch_status,
        ios_destination=args.ios_destination,
        watch_destination=args.watch_destination,
        ios_configuration=args.ios_configuration,
        watch_configuration=args.watch_configuration,
        ios_sdk=args.ios_sdk,
        watch_sdk=args.watch_sdk,
        ios_test_count=args.ios_test_count,
        watch_test_count=args.watch_test_count,
        ios_duration_seconds=args.ios_duration_seconds,
        watch_duration_seconds=args.watch_duration_seconds,
    )
    write_native_build_evidence(output_path=args.output, payload=payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
