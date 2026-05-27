#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:9000}"

uv run python - "${BASE_URL}" "${AI_CADDIE_ADMIN_TOKEN:-}" <<'PY'
from __future__ import annotations

import base64
import json
import sys
from uuid import uuid4
from urllib.request import Request, urlopen

base_url = sys.argv[1].rstrip("/")
admin_token = sys.argv[2]


def call_json(method: str, path: str, *, payload: dict[str, object] | None = None, protected: bool = False) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if protected and admin_token:
        headers["X-AI-Caddie-Admin-Token"] = admin_token
    request = Request(f"{base_url}{path}", data=body, headers=headers, method=method)
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    text = json.dumps(payload).lower()
    for forbidden in (
        "cookie",
        "csrf",
        "connect-csrf-token",
        "access_token",
        "refresh_token",
        "password=",
        "secret=",
        "/home/",
        "/users/",
        ".garmin_tokens",
        ".env",
    ):
        if forbidden in text:
            raise SystemExit(f"secret-like term leaked from {path}: {forbidden}")
    schema = payload.get("schema") if isinstance(payload, dict) else None
    if not schema:
        raise SystemExit(f"missing schema from {path}")
    return payload


for path, protected in [
    ("/api/v2/health", False),
    ("/api/v2/readiness", False),
    ("/api/v2/sync/status", False),
    ("/api/v2/history/overview", True),
    ("/api/v2/mobile/rounds/900001/package", True),
    ("/api/v2/reports/trend/recent_10", True),
    ("/api/v2/media/target/round/900001", True),
]:
    call_json("GET", path, protected=protected)

call_json(
    "POST",
    "/api/v2/caddie/decision",
    protected=True,
    payload={
        "shotType": "tee",
        "includeExplanation": False,
        "context": {
            "roundId": "900001",
            "sourceRef": "900001:7",
            "courseName": "Private trial smoke",
            "hole": 7,
            "distanceToPin_m": 360,
            "clubProfiles": {
                "1D": {"clubName": "1D", "sampleSize": 10, "median": 230, "p10": 205, "p90": 250},
                "3W": {"clubName": "3W", "sampleSize": 8, "median": 205, "p10": 185, "p90": 225},
                "58": {"clubName": "58", "sampleSize": 6, "median": 75, "p10": 65, "p90": 85},
            },
            "candidateRoutes": [{"id": "stock_line", "label": "stock line", "carry_m": 230, "riskScore": 1}],
        },
    },
)

media_target_id = f"smoke-media-{uuid4().hex}"
media_create = call_json(
    "POST",
    "/api/v2/media",
    protected=True,
    payload={
        "targetType": "shot",
        "targetId": media_target_id,
        "mediaKind": "photo",
        "fileName": "smoke-lie.jpg",
        "contentBase64": base64.b64encode(b"ai-caddie-private-trial-smoke-media").decode("ascii"),
        "capturedAt": "2026-05-25T00:00:00Z",
        "privacyState": "private_local",
    },
)
media = media_create.get("media") if isinstance(media_create.get("media"), dict) else {}
media_id = str(media.get("id") or "")
if not media_id:
    raise SystemExit("media create did not return media.id")
local_path = str(media.get("localPath") or "")
if not local_path.startswith("data/media/uploads/"):
    raise SystemExit(f"media create returned unexpected localPath: {local_path}")

analysis = call_json("POST", f"/api/v2/media/{media_id}/analyze", protected=True)
findings = analysis.get("findings") if isinstance(analysis.get("findings"), list) else []
if not findings:
    raise SystemExit("media analysis did not return at least one bounded finding")
if "mediaBytesBase64" in json.dumps(analysis):
    raise SystemExit("media analysis leaked raw media bytes")

findings_list = call_json("GET", f"/api/v2/media/target/shot/{media_target_id}/findings", protected=True)
stored_findings = findings_list.get("findings") if isinstance(findings_list.get("findings"), list) else []
if not stored_findings:
    raise SystemExit("stored media findings list is empty")
findings_text = json.dumps(findings_list)
if "localPath" in findings_text or "mediaBytesBase64" in findings_text:
    raise SystemExit("stored media findings exposed local path or raw media bytes")
finding = stored_findings[0] if isinstance(stored_findings[0], dict) else {}
finding_id = str(finding.get("id") or "")
if not finding_id:
    raise SystemExit("stored media finding did not include id")

confirmation = call_json(
    "POST",
    f"/api/v2/media/findings/{finding_id}/confirmation",
    protected=True,
    payload={"confirmationState": "manual_confirmed", "confirmedBy": "private-trial-smoke"},
)
confirmed = confirmation.get("finding") if isinstance(confirmation.get("finding"), dict) else {}
if confirmed.get("confirmationState") != "manual_confirmed":
    raise SystemExit("media finding confirmation did not persist")

redaction = call_json("POST", f"/api/v2/media/{media_id}/redact", protected=True)
redacted_media = redaction.get("media") if isinstance(redaction.get("media"), dict) else {}
if redacted_media.get("privacyState") != "redacted" or redacted_media.get("localPath") != "[redacted]":
    raise SystemExit("media redaction did not return redacted metadata")

redacted_list = call_json("GET", f"/api/v2/media/target/shot/{media_target_id}", protected=True)
media_rows = redacted_list.get("media") if isinstance(redacted_list.get("media"), list) else []
if not media_rows:
    raise SystemExit("redacted media was not listed for its target")
if not any(isinstance(row, dict) and row.get("id") == media_id and row.get("localPath") == "[redacted]" for row in media_rows):
    raise SystemExit("media list did not expose latest redacted metadata")

print(f"private trial smoke ok: {base_url}")
PY
