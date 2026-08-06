#!/usr/bin/env python3
"""Fail fast when the production course catalogue cannot support the native journey."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_health(payload: Any) -> None:
    _require(isinstance(payload, dict), "health response must be an object")
    _require(payload.get("schema") == "ai-caddie-health-v2", "health schema mismatch")


def validate_matches(
    payload: Any,
    *,
    schema: str,
    expected_global_id: int | None = None,
    require_distance_order: bool = False,
) -> list[dict[str, Any]]:
    _require(isinstance(payload, dict), f"{schema} response must be an object")
    _require(payload.get("schema") == schema, f"expected schema {schema}")
    matches = payload.get("matches")
    _require(isinstance(matches, list), f"{schema}.matches must be an array")
    _require(bool(matches), f"{schema}.matches must not be empty for the CI probe")
    _require(all(isinstance(row, dict) for row in matches), f"{schema}.matches rows must be objects")
    ids = [row.get("globalId") for row in matches]
    _require(all(isinstance(value, int) and value > 0 for value in ids), "every match needs a positive globalId")
    _require(len(ids) == len(set(ids)), "catalogue response contains duplicate globalIds")
    if expected_global_id is not None:
        _require(expected_global_id in ids, f"expected globalId {expected_global_id} is missing")
    if require_distance_order:
        distances = [row.get("distanceKm") for row in matches]
        _require(
            all(isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 for value in distances),
            "nearby result needs a non-negative distanceKm on every row",
        )
        _require(distances == sorted(distances), "nearby matches are not nearest-first")
    return matches


def _headers() -> dict[str, str]:
    mode = os.environ.get("AI_CADDIE_PREFLIGHT_AUTH_MODE", "admin").strip().lower()
    token = os.environ.get("AI_CADDIE_PREFLIGHT_TOKEN", "").strip()
    _require(len(token) >= 16 and token != "-", "catalogue preflight token is missing")
    if mode == "admin":
        return {"X-AI-Caddie-Admin-Token": token}
    if mode == "bearer":
        return {"Authorization": f"Bearer {token}"}
    raise ValueError("AI_CADDIE_PREFLIGHT_AUTH_MODE must be admin or bearer")


def _get_json(base_url: str, path: str, params: dict[str, str] | None, headers: dict[str, str]) -> Any:
    query = "?" + urllib.parse.urlencode(params) if params else ""
    url = base_url.rstrip("/") + path + query
    last_error: Exception | None = None
    for attempt in range(1, 7):
        request = urllib.request.Request(url, headers={"Accept": "application/json", **headers})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                _require(response.status == 200, f"{path} returned HTTP {response.status}")
                return json.load(response)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
            if status is not None and status not in {408, 425, 429, 500, 502, 503, 504}:
                break
            if attempt < 6:
                time.sleep(min(2 ** (attempt - 1), 30))
    raise RuntimeError(f"{path} failed after retries: {last_error}") from last_error


def main() -> int:
    base_url = os.environ.get("AI_CADDIE_PREFLIGHT_BASE_URL", "").strip()
    _require(base_url.startswith("https://"), "AI_CADDIE_PREFLIGHT_BASE_URL must be an HTTPS origin")
    headers = _headers()
    latitude = os.environ.get("AI_CADDIE_PREFLIGHT_LATITUDE", "40.0454995")
    longitude = os.environ.get("AI_CADDIE_PREFLIGHT_LONGITUDE", "116.5461531")
    search_name = os.environ.get("AI_CADDIE_PREFLIGHT_SEARCH_NAME", "北京丽宫")
    nearby_gid = int(os.environ.get("AI_CADDIE_PREFLIGHT_NEARBY_GID", "31793"))
    search_gid = int(os.environ.get("AI_CADDIE_PREFLIGHT_SEARCH_GID", str(nearby_gid)))

    health = _get_json(base_url, "/api/v2/health", None, {})
    validate_health(health)
    nearby = _get_json(
        base_url,
        "/api/v2/courses/nearby",
        {"latitude": latitude, "longitude": longitude, "radius_km": "50"},
        headers,
    )
    nearby_matches = validate_matches(
        nearby,
        schema="ai-caddie-course-nearby-v1",
        expected_global_id=nearby_gid,
        require_distance_order=True,
    )
    search = _get_json(
        base_url,
        "/api/v2/courses/search",
        {"name": search_name, "latitude": latitude, "longitude": longitude},
        headers,
    )
    search_matches = validate_matches(
        search,
        schema="ai-caddie-course-search-v1",
        expected_global_id=search_gid,
    )
    print(
        "course-catalogue-preflight ok "
        f"health={health['schema']} nearby={len(nearby_matches)} search={len(search_matches)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"course-catalogue-preflight failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
