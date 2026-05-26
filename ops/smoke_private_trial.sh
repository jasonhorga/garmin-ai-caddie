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
paths: list[tuple[str, bool]] = [
    ("/api/v2/health", False),
    ("/api/v2/readiness", False),
    ("/api/v2/sync/status", False),
    ("/api/v2/history/overview", False),
    ("/api/v2/mobile/rounds/900001/package", True),
]
for path, protected in paths:
    request = Request(f"{base_url}{path}")
    if protected and admin_token:
        request.add_header("X-AI-Caddie-Admin-Token", admin_token)
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    text = json.dumps(payload).lower()
    for forbidden in ("cookie", "csrf", "connect-csrf-token", "access_token", "refresh_token"):
        if forbidden in text:
            raise SystemExit(f"secret-like term leaked from {path}: {forbidden}")
    schema = payload.get("schema")
    if not schema:
        raise SystemExit(f"missing schema from {path}")

print(f"private trial smoke ok: {base_url}")
PY
