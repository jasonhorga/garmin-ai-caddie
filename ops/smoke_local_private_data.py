from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any

FORBIDDEN_TERMS = (
    "cookie",
    "csrf",
    "connect-csrf-token",
    "access_token",
    "refresh_token",
    "password",
    "authorization",
    "/home/",
    "/users/",
    ".garmin_tokens",
    ".env",
)

DEFAULT_OUTPUT = Path("logs/local_private_smoke_latest.json")


def assert_secret_free(payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False, default=str).lower()
    for term in FORBIDDEN_TERMS:
        if term in text:
            raise AssertionError(f"secret-like term leaked: {term}")


def _get_json(client: Any, path: str) -> dict[str, Any]:
    response = client.get(path)
    if response.status_code != 200:
        raise RuntimeError(f"{path} returned HTTP {response.status_code}")
    payload = response.json()
    assert_secret_free(payload)
    return payload


def build_smoke_evidence(client: Any, *, base_url: str) -> dict[str, Any]:
    checks: list[str] = []
    endpoints = [
        "/api/v2/health",
        "/api/v2/readiness",
        "/api/v2/history/overview",
        "/api/v2/history/rounds",
        "/api/v2/history/stats",
        "/api/v2/sync/status",
    ]
    payloads: dict[str, dict[str, Any]] = {}
    for path in endpoints:
        payloads[path] = _get_json(client, path)
        checks.append(f"GET {path}")
    round_detail_checked = False
    rounds = payloads["/api/v2/history/rounds"].get("rounds")
    if isinstance(rounds, list) and rounds:
        round_id = str((rounds[0] or {}).get("id") or "").strip()
        if round_id:
            path = f"/api/v2/history/rounds/{round_id}"
            _get_json(client, path)
            checks.append(f"GET {path}")
            round_detail_checked = True
    evidence = {
        "schema": "ai-caddie-local-private-smoke-evidence-v1",
        "createdAt": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "baseUrl": base_url,
        "dataMode": "local",
        "checks": checks,
        "roundDetailChecked": round_detail_checked,
        "endpointCount": len(checks),
    }
    assert_secret_free(evidence)
    return evidence


def write_smoke_evidence(*, client: Any, output: Path = DEFAULT_OUTPUT, base_url: str = "testclient") -> dict[str, Any]:
    evidence = build_smoke_evidence(client, base_url=base_url)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def main() -> int:
    os.environ["AI_CADDIE_DATA_MODE"] = "local"
    from fastapi.testclient import TestClient
    from server_v2.main import app

    output = Path(os.environ.get("AI_CADDIE_LOCAL_SMOKE_EVIDENCE", str(DEFAULT_OUTPUT)))
    write_smoke_evidence(client=TestClient(app), output=output, base_url="testclient")
    print(f"local private smoke ok: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
