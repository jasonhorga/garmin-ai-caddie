#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:9000}"

uv run python - "${BASE_URL}" "${AI_CADDIE_ADMIN_TOKEN:-}" <<'PY'
from __future__ import annotations

import json
import sys
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
    for forbidden in ("cookie", "csrf", "connect-csrf-token", "access_token", "refresh_token"):
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
    ("/api/v2/history/overview", False),
    ("/api/v2/mobile/rounds/900001/package", True),
    ("/api/v2/reports/trend/recent_10", True),
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

call_json(
    "POST",
    "/api/v2/media",
    protected=True,
    payload={
        "targetType": "round",
        "targetId": "900001",
        "mediaKind": "photo",
        "fileName": "private-trial-smoke.jpg",
        "contentBase64": "c21va2U=",
        "capturedAt": "2026-05-27T00:00:00Z",
    },
)

print(f"private trial smoke ok: {base_url}")
PY
