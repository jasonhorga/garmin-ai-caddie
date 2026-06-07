#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "ai-caddie-roadmap-completion-status-v1"
ROADMAP = Path("docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md")
EXTERNAL_RELEASE_EVIDENCE = Path("logs/phase6_external_readiness_latest.json")
EXTERNAL_RELEASE_SCHEMA = "ai-caddie-phase6-external-readiness-v1"
PHASE6_GATES = (
    {
        "key": "phone_reachable_backend",
        "roadmapItem": "Deploy a phone-reachable backend host and point the native app at it.",
        "checks": (
            "native_api_base_url_configuration",
            "phone_reachable_backend_url",
            "backend_probe",
        ),
    },
    {
        "key": "external_beta_review_submission",
        "roadmapItem": "Submit external Beta App Review.",
        "checks": (
            "external_beta_review_submission_ready",
            "external_beta_review_submission",
        ),
    },
    {
        "key": "target_tester_coverage",
        "roadmapItem": (
            "Add/confirm target tester emails for the external group or confirm the "
            "user is covered by the existing internal group."
        ),
        "checks": ("external_testers",),
    },
    {
        "key": "device_install",
        "roadmapItem": "Verify installation from TestFlight on iPhone/watch.",
        "checks": ("device_install",),
    },
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)[:240]
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[redacted_email]", text)
    text = re.sub(r"(?<!\w)/(?:[^\s:/]+/)*[^\s:]*", "[redacted_path]", text)
    if any(
        term in text.lower()
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
        return "redacted_text"
    return text


def _safe_label(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "_", text)[:120]
    return text or "unknown"


def _open_checklist_items(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("- [ ] "):
            if current is not None:
                items.append(" ".join(current))
            current = [line.removeprefix("- [ ] ").strip()]
            continue
        if line.startswith("- [x] ") or line.startswith("### "):
            if current is not None:
                items.append(" ".join(current))
                current = None
            continue
        if current is not None and line.startswith("  ") and line.strip():
            current.append(line.strip())
            continue
        if current is not None and not line.strip():
            items.append(" ".join(current))
            current = None
    if current is not None:
        items.append(" ".join(current))
    return items


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _external_release_summary(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if payload is None:
        return {
            "available": False,
            "path": path.as_posix(),
            "state": "missing",
            "schema": EXTERNAL_RELEASE_SCHEMA,
            "missingExternalActions": ["run ops/phase6_external_readiness.py"],
            "checks": [],
        }

    raw_checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    checks = []
    for row in raw_checks:
        if not isinstance(row, dict):
            continue
        checks.append(
            {
                "label": _safe_label(row.get("label")),
                "state": _safe_label(row.get("state")),
                "reason": _safe_text(row.get("reason")),
            }
        )

    raw_missing = payload.get("missingExternalActions")
    missing = raw_missing if isinstance(raw_missing, list) else []
    return {
        "available": True,
        "path": path.as_posix(),
        "schema": payload.get("schema"),
        "createdAt": payload.get("createdAt"),
        "state": _safe_text(payload.get("state") or "unknown"),
        "missingExternalActions": [_safe_text(item) for item in missing if _safe_text(item)],
        "checks": checks,
    }


def _phase6_gate_summary(external_release: dict[str, Any]) -> list[dict[str, Any]]:
    checks = {
        str(row.get("label") or ""): row
        for row in external_release.get("checks", [])
        if isinstance(row, dict)
    }
    gates: list[dict[str, Any]] = []
    for gate in PHASE6_GATES:
        gate_checks = []
        for label in gate["checks"]:
            row = checks.get(label)
            gate_checks.append(
                {
                    "label": label,
                    "state": row.get("state") if row else "missing",
                    "reason": row.get("reason") if row else "check missing from external release evidence",
                }
            )
        ready = bool(gate_checks) and all(row["state"] == "ready" for row in gate_checks)
        gates.append(
            {
                "key": gate["key"],
                "state": "ready" if ready else "incomplete",
                "roadmapItem": gate["roadmapItem"],
                "checks": gate_checks,
                "remainingActions": [
                    row["reason"]
                    for row in gate_checks
                    if row["state"] != "ready" and str(row.get("reason") or "").strip()
                ],
            }
        )
    return gates


def build_status(
    *,
    roadmap_path: Path = ROADMAP,
    external_release_path: Path = EXTERNAL_RELEASE_EVIDENCE,
    created_at: str | None = None,
) -> dict[str, Any]:
    roadmap_text = roadmap_path.read_text(encoding="utf-8")
    open_items = _open_checklist_items(roadmap_text)
    external_release = _external_release_summary(external_release_path)
    phase6_gates = _phase6_gate_summary(external_release)
    external_ready = (
        external_release.get("available") is True
        and external_release.get("schema") == EXTERNAL_RELEASE_SCHEMA
        and external_release.get("state") == "ready"
        and all(gate["state"] == "ready" for gate in phase6_gates)
    )
    completion_ready = not open_items and external_ready
    return {
        "schema": SCHEMA,
        "createdAt": created_at or _utc_now(),
        "roadmap": {
            "path": roadmap_path.as_posix(),
            "openItemCount": len(open_items),
            "openItems": open_items,
        },
        "externalRelease": external_release,
        "phase6Gates": phase6_gates,
        "completionReady": completion_ready,
        "state": "ready" if completion_ready else "incomplete",
        "remainingRequirements": [
            *open_items,
            *external_release.get("missingExternalActions", []),
        ],
    }


def _dump(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _write_output(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize AI Caddie roadmap completion readiness.")
    parser.add_argument("--roadmap", type=Path, default=ROADMAP)
    parser.add_argument("--external-release-evidence", type=Path, default=EXTERNAL_RELEASE_EVIDENCE)
    parser.add_argument("--output", type=Path, help="Write JSON status to this path after printing it.")
    parser.add_argument("--no-fail", action="store_true", help="Exit 0 even when completion is incomplete.")
    args = parser.parse_args(argv)

    payload = build_status(roadmap_path=args.roadmap, external_release_path=args.external_release_evidence)
    _dump(payload)
    if args.output:
        _write_output(args.output, payload)
    return 0 if args.no_fail or payload["completionReady"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
