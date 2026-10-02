"""B7 step 1 (IMPLEMENTATION_PLAN B7): auto-shot swing candidates collected on the Watch.

Only derived features travel: the Watch keeps raw motion samples on the wrist. A candidate never
changes a score; this store exists so step 2 can label candidates against the round's corrections
and measure thresholds offline. One upload per round replaces the previous one (the Watch resends
its whole round after a retry), so the write is idempotent.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_caddie.history import history as _history

MAX_CANDIDATES = 600
KINDS = {"fullSwing", "groundPracticeSwing", "airSwing", "putt", "riding", "unknown"}
# Feature name -> (minimum, maximum). Anything else is rejected: raw samples never leave the Watch.
FEATURE_BOUNDS: dict[str, tuple[float, float]] = {
    "stillnessBeforeS": (0, 60),
    "swingDurationS": (0, 10),
    "cumulativeRotationRad": (0, 100),
    "peakRotationRadS": (0, 60),
    "impactPeakG": (0, 32),
    "impactDurationMs": (0, 2000),
}
_SAFE_REF = re.compile(r"[^A-Za-z0-9._-]+")


class SwingCandidateError(ValueError):
    pass


def _number(value: Any, name: str, low: float, high: float, *, optional: bool) -> float | None:
    if value is None:
        if optional:
            return None
        raise SwingCandidateError(f"{name} is required")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SwingCandidateError(f"{name} must be a finite number")
    if not low <= value <= high:
        raise SwingCandidateError(f"{name} out of range")
    return float(value)


_ISO_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$"
)


def _is_iso_timestamp(value: Any) -> bool:
    """The Watch's ISO8601DateFormatter output: a full date-time with a zone, e.g. 2026-10-02T08:00:00Z."""
    if not isinstance(value, str) or not _ISO_TIMESTAMP.match(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise SwingCandidateError(f"{name} must be a boolean")
    return value


def validate_candidates(candidates: Any) -> list[dict[str, Any]]:
    """The accepted shape, rebuilt field by field so no unknown key is stored."""
    if not isinstance(candidates, list):
        raise SwingCandidateError("candidates must be a list")
    if len(candidates) > MAX_CANDIDATES:
        raise SwingCandidateError(f"at most {MAX_CANDIDATES} candidates per round")
    clean: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            raise SwingCandidateError("candidate must be an object")
        candidate_id = item.get("id")
        captured_at = item.get("capturedAt")
        if not isinstance(candidate_id, str) or not 1 <= len(candidate_id) <= 64:
            raise SwingCandidateError("candidate id must be a short string")
        if not _is_iso_timestamp(captured_at):
            raise SwingCandidateError("capturedAt must be an ISO-8601 timestamp with a time zone")
        hole = item.get("hole")
        if isinstance(hole, bool) or not isinstance(hole, int) or not 1 <= hole <= 36:
            raise SwingCandidateError("hole must be 1-36")
        features = item.get("features")
        if not isinstance(features, dict):
            raise SwingCandidateError("features must be an object")
        unknown = set(features) - set(FEATURE_BOUNDS) - {"kind"}
        if unknown:
            raise SwingCandidateError(f"unknown feature fields: {sorted(unknown)}")
        kind = features.get("kind")
        if kind not in KINDS:
            raise SwingCandidateError("unknown candidate kind")
        clean_features: dict[str, Any] = {"kind": kind}
        for name, (low, high) in FEATURE_BOUNDS.items():
            value = _number(features.get(name), name, low, high, optional=name.startswith("impact"))
            if value is not None:
                clean_features[name] = value
        clean.append({
            "id": candidate_id,
            "capturedAt": captured_at,
            "hole": hole,
            "features": clean_features,
            "horizontalAccuracyM": _number(item.get("horizontalAccuracyM"), "horizontalAccuracyM", 0, 10_000, optional=True),
            "speedMps": _number(item.get("speedMps"), "speedMps", 0, 100, optional=True),
            "proposedShot": _boolean(item.get("proposedShot", False), "proposedShot"),
        })
    return clean


def candidates_dir(player_id: str, root: Path | str | None = None) -> Path:
    base = Path(root) if root is not None else _history.ROOT
    return base / "data" / "players" / str(player_id) / "swing-candidates"


def candidates_path(player_id: str, round_id: str, root: Path | str | None = None) -> Path:
    safe = (_SAFE_REF.sub("_", str(round_id)) or "round")[:80]
    digest = hashlib.sha256(str(round_id).encode("utf-8")).hexdigest()[:16]
    return candidates_dir(player_id, root) / f"{safe}--{digest}.json"


def store_candidates(
    player_id: str, round_id: str, candidates: Any, root: Path | str | None = None
) -> dict[str, Any]:
    clean = validate_candidates(candidates)
    path = candidates_path(player_id, round_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": "ai-caddie-swing-candidates-v1", "roundId": round_id, "candidates": clean}
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".swing-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return {"roundId": round_id, "stored": len(clean)}


def load_candidates(player_id: str, round_id: str, root: Path | str | None = None) -> list[dict[str, Any]]:
    path = candidates_path(player_id, round_id, root)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("candidates", [])
