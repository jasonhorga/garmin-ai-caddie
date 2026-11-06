#!/usr/bin/env python3
"""Read-only inventory of ambiguous manual GIR/tee evidence, including existing GIR.

Run against an offline runtime-root copy. JSON goes to stdout; there is no apply mode.
Categories overlap and identify candidates, not proven historical mistakes. Round dates are
not ingest timestamps, so the audit deliberately does not filter by date.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ops.backfill_manual_gir import _hole_par, _int
from ai_caddie.rounds.round_ingest import _shot_putt_count


def _putt_prefix_unknown(rows: list[dict], clubs: list[dict]) -> bool:
    names = {c.get("id"): str(c.get("name") or "").strip().lower() for c in clubs}
    unknown = False
    for shot in rows:
        name = names.get(shot.get("clubId"), "")
        lie = str((shot.get("startLoc") or {}).get("lie") or "").strip().lower()
        putter = "putt" in name or name in {"pt", "推杆"} or "putt" in str(shot.get("shotType") or "").lower()
        if putter and lie == "green":
            return unknown
        unknown |= lie in {"", "unknown", "green"} or putter
    return False


def _flags(hole: dict, rows: list[dict], clubs: list[dict], par: int | None) -> list[str]:
    flags = []
    strokes = _int(hole.get("strokes"))
    penalties = _int(hole.get("penalties"))
    if "penalties" not in hole:
        flags.append("missingPenaltiesKey")
    if penalties is None:
        flags.append("unknownPenalties")
    elif penalties != 0:
        flags.append("nonzeroPenalties")
    if strokes is None:
        flags.append("unknownStrokes")
    elif len(rows) != strokes:
        flags.append("positionCountMismatch")
        flags.append("missingPositions" if len(rows) < strokes else "extraPositions")
        if len(rows) == strokes - 1:
            flags.append("oneMissingPosition")
    if _putt_prefix_unknown(rows, clubs):
        flags.append("unknownLieBeforeFirstPutt")
    entered_putts = _int(hole.get("putts"))
    inferred_putts = _shot_putt_count(rows, total_strokes=strokes, club_details=clubs, penalties=penalties)
    needs_landing = entered_putts is None and inferred_putts is None and par is not None and strokes is not None and strokes > par - 2
    if needs_landing and len(rows) == par - 2 and hole.get("gir") is not None:
        flags.append("storedGirWithAimOnlyCandidate")
    if needs_landing and hole.get("gir") is not None and (
        penalties != 0 or len(rows) != strokes
    ):
        flags.append("storedGirWithAmbiguousIndex")
    if par in (4, 5) and len(rows) >= 2 and (penalties != 0 or strokes is None or len(rows) != strokes):
        flags.append("ambiguousTeeIndex")
        if penalties is not None and penalties > 0:
            flags.append("penaltyTeeRecoveryUnproven")
        if strokes is not None and len(rows) > strokes:
            # Green lies in the suffix are only candidates: real putts can repeat a point.
            tail = rows[strokes:]
            if all(str((r.get("startLoc") or {}).get("lie") or "").lower() == "green" for r in tail):
                flags.append("extraGreenTailRecoveryUnproven")
    return flags


def audit(root: Path) -> dict[str, Any]:
    root = Path(root)
    data = root / "data"
    if not data.is_dir():
        raise ValueError("runtime copy must contain data/")
    paths = sorted(set(data.glob("players/*/scorecards/*.json")) | set(data.glob("scorecards/*.json")))
    counts: Counter = Counter(dict.fromkeys([
        "manualRounds", "manualHoles", "nonManualFiles", "missingShotsFiles",
        "missingPenaltiesKey", "unknownPenalties", "nonzeroPenalties", "unknownStrokes",
        "positionCountMismatch", "missingPositions", "extraPositions", "oneMissingPosition",
        "unknownLieBeforeFirstPutt", "storedGirWithAimOnlyCandidate",
        "storedGirWithAmbiguousIndex", "ambiguousTeeIndex", "penaltyTeeRecoveryUnproven",
        "extraGreenTailRecoveryUnproven",
    ], 0))
    counts["scannedScorecards"] = len(paths)
    holes = []
    errors = []
    if not paths:
        errors.append({"reason": "no scorecard files found; inventory incomplete"})
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            if any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
                raise ValueError("symlink source refused")
            card_bytes = path.read_bytes()
            raw = json.loads(card_bytes)
            if not isinstance(raw, dict):
                raise ValueError("scorecard is not an object")
            if raw.get("source") != "manual":
                counts["nonManualFiles"] += 1
                continue
            card = raw["scorecardDetails"][0]["scorecard"]
            if not isinstance(card, dict) or not isinstance(card.get("holes"), list):
                raise ValueError("manual scorecard holes missing")
            shot_path = path.parent.parent / "shots" / path.name
            if shot_path.is_symlink() or shot_path.parent.is_symlink():
                raise ValueError("symlink shots refused")
            shot_bytes = shot_path.read_bytes() if shot_path.exists() else None
            if shot_bytes is None:
                counts["missingShotsFiles"] += 1
            shots = json.loads(shot_bytes) if shot_bytes is not None else {}
            if not isinstance(shots, dict):
                raise ValueError("shots are not an object")
            by_hole: dict[int, list[dict]] = {}
            for item in shots.get("holeShots", []):
                by_hole.setdefault(_int(item.get("holeNumber")), []).extend(item.get("shots") or [])
            clubs = shots.get("clubDetails") or []
            counts["manualRounds"] += 1
            for hole in card["holes"]:
                number = _int(hole.get("number"))
                rows = by_hole.get(number, [])
                flags = _flags(hole, rows, clubs, _hole_par(raw, hole, number or 0))
                counts["manualHoles"] += 1
                counts.update(flags)
                holes.append({
                    "scorecard": relative, "roundId": card.get("id"), "hole": number,
                    "storedGir": hole.get("gir"), "storedFairway": hole.get("fairway"),
                    "positions": len(rows), "strokes": _int(hole.get("strokes")),
                    "penalties": _int(hole.get("penalties")), "flags": flags,
                    "scorecardSha256": hashlib.sha256(card_bytes).hexdigest(),
                    "shotsSha256": hashlib.sha256(shot_bytes).hexdigest() if shot_bytes is not None else None,
                })
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            errors.append({"scorecard": relative, "reason": "unreadable or malformed source; inventory incomplete"})
    return {"mode": "read-only", "summary": dict(counts), "holes": holes, "errors": errors,
            "limits": ["Flags overlap; candidates are not proven errors.",
                       "Aggregate penalties and position order cannot locate a penalty or an extra tap.",
                       "Existing GIR is inventoried without clearing or recomputing it; no ingest-date filter."]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = audit(args.root)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
