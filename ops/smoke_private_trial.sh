#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:9000}"

uv run python - "${BASE_URL}" <<'PY'
from __future__ import annotations

import json
import sys
from urllib.request import urlopen

base_url = sys.argv[1].rstrip("/")
paths = [
    "/api/v2/health",
    "/api/v2/readiness",
    "/api/v2/sync/status",
    "/api/v2/history/overview",
]
for path in paths:
    with urlopen(f"{base_url}{path}", timeout=10) as response:
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
