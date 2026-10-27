"""Read and ingest the small, privacy-safe timing records used by the mobile client."""

from __future__ import annotations

from datetime import datetime
import math
import re
from typing import Any

from ai_caddie.core import request_timing

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
_CLIENT_FIELDS = {"request_id", "path", "client_total_ms", "status", "error", "started_at", "network_type"}
_MAX_BATCH = 50


def _parse_iso(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return text


def sanitize_client_record(value: Any) -> dict[str, Any] | None:
    """Return a bounded record, or ``None`` when any client supplied field is invalid."""
    if not isinstance(value, dict) or set(value) - _CLIENT_FIELDS:
        return None
    request_id = value.get("request_id")
    path = value.get("path")
    total = value.get("client_total_ms")
    started_at = _parse_iso(value.get("started_at"))
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        return None
    if not isinstance(path, str) or not path.strip() or len(path) > 512:
        return None
    if isinstance(total, bool) or not isinstance(total, (int, float)) or not math.isfinite(float(total)):
        return None
    if total < 0 or total > 86_400_000 or started_at is None:
        return None
    has_status = "status" in value and value.get("status") is not None
    has_error = "error" in value and value.get("error") is not None
    if not has_status and not has_error:
        return None
    if has_status:
        status = value.get("status")
        if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
            return None
    if has_error and (not isinstance(value.get("error"), str) or len(value["error"]) > 500):
        return None
    network = value.get("network_type")
    if network is not None and (not isinstance(network, str) or len(network) > 64):
        return None
    record: dict[str, Any] = {
        "ts": request_timing._now().isoformat(timespec="milliseconds"),
        "request_id": request_id,
        "path": request_timing.template_path(path),
        "client_total_ms": round(float(total), 1),
        "started_at": started_at,
    }
    if has_status:
        record["status"] = value["status"]
    if has_error:
        record["error"] = value["error"]
    if network is not None:
        record["network_type"] = network
    return record


def append_client_records(values: list[Any]) -> tuple[int, int]:
    accepted = 0
    rejected = 0
    for value in values:
        record = sanitize_client_record(value)
        if record is None:
            rejected += 1
            continue
        accepted += 1
        request_timing.append_client_timing(record)
    return accepted, rejected


def query_server_records(
    *,
    since: datetime | None = None,
    path_prefix: str | None = None,
    min_ms: float | None = None,
    request_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    rows = request_timing.read_timing_rows()
    rows.sort(key=lambda row: str(row.get("ts") or ""), reverse=True)
    result: list[dict[str, Any]] = []
    for row in rows:
        if request_id is not None and row.get("request_id") != request_id:
            continue
        row_path = row.get("path")
        if path_prefix is not None and (not isinstance(row_path, str) or not row_path.startswith(path_prefix)):
            continue
        if min_ms is not None:
            try:
                if float(row.get("total_ms")) < min_ms:
                    continue
            except (TypeError, ValueError):
                continue
        if since is not None:
            try:
                ts = datetime.fromisoformat(str(row.get("ts")).replace("Z", "+00:00"))
                if ts.tzinfo is None or ts < since:
                    continue
            except ValueError:
                continue
        result.append(row)
        if len(result) >= limit:
            break
    return result


__all__ = ["_MAX_BATCH", "append_client_records", "query_server_records", "sanitize_client_record"]
