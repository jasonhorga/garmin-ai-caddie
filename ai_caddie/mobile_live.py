"""Shared live mobile package and event log helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from ai_caddie.fixtures import fixture_history_data
from ai_caddie.history import HistoryData
from ai_caddie.history_stats import build_history_stats


EVENT_LOG = Path("data") / "mobile_events" / "events.jsonl"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_live_round_package(round_id: str, data: HistoryData | None = None) -> dict[str, Any]:
    source = data or fixture_history_data()
    stats = build_history_stats(source, data_mode="fixture", annotations_root=Path("/nonexistent-ai-caddie-annotations"))
    round_row = source.rounds[0] if source.rounds else {}
    holes = [
        {
            "number": int(hole.get("number") or index),
            "par": int(hole.get("par") or 4),
            "yards": int(hole.get("yards") or 0) if hole.get("yards") is not None else None,
            "geometryCoverage": next(
                (
                    str(row.get("geometryCoverage") or "missing")
                    for row in stats["holes"]
                    if row.get("hole") == int(hole.get("number") or index)
                ),
                "missing",
            ),
        }
        for index, hole in enumerate(round_row.get("holes") or [], start=1)
    ]
    if not holes:
        holes = [{"number": index, "par": 4, "yards": None, "geometryCoverage": "missing"} for index in range(1, 19)]
    club_profiles = [
        {
            "clubName": row.get("club"),
            "sampleSize": int(row.get("sampleCount") or 0),
            "median_m": float(row.get("median") or 0),
            "p10_m": float(row.get("p10") or row.get("median") or 0),
            "p90_m": float(row.get("p90") or row.get("median") or 0),
        }
        for row in stats["clubs"]
        if row.get("club") and row.get("median") is not None
    ]
    if not club_profiles:
        club_profiles = [{"clubName": "8I", "sampleSize": 0, "median_m": 140.0, "p10_m": 130.0, "p90_m": 150.0}]
    ready_holes = sum(1 for hole in holes if hole["geometryCoverage"] == "ready")
    return {
        "schema": "ai-caddie-live-round-package-v1",
        "roundId": round_id,
        "playerProfile": {"playerId": "local-player", "displayName": "Local Player", "handedness": "unknown"},
        "course": {
            "globalId": int(round_row.get("globalId") or 0),
            "name": str(round_row.get("course") or round_row.get("courseName") or "Unknown course"),
            "teeBox": str(round_row.get("teeBox") or "unknown"),
        },
        "holes": holes,
        "geometryCoverage": {
            "state": "ready" if ready_holes == len(holes) else "partial" if ready_holes else "missing",
            "readyHoles": ready_holes,
            "totalHoles": len(holes),
        },
        "clubProfiles": club_profiles,
        "caddieDecisionEndpoint": "/api/v2/caddie/decision",
        "generatedAt": _now(),
    }


def mobile_event_log(root: Path | str | None = None) -> Path:
    return Path(root or ".") / EVENT_LOG


def append_event_batch(
    round_id: str,
    events: list[dict[str, Any]],
    *,
    idempotency_key: str,
    root: Path | str | None = None,
) -> dict[str, Any]:
    path = mobile_event_log(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_keys = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            existing_keys.add(str(json.loads(line).get("idempotencyKey") or ""))
    if idempotency_key in existing_keys:
        return {"accepted": 0, "duplicate": True}
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps({"roundId": round_id, "idempotencyKey": idempotency_key, "event": event}, sort_keys=True) + "\n")
    return {"accepted": len(events), "duplicate": False}
