"""Replay the checked-in caddie cases and emit a deterministic evidence record.

This intentionally reports failures instead of asserting the desired algorithm. The first run is
the pre-CADDIE-P0 baseline; the same fixture becomes the regression gate once the hard-feasibility
implementation is complete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from ai_caddie.caddie.decision import build_decision_plan, _route_evidence_zones, _shift_hazard_zones


FIXTURE = Path(__file__).parent / "fixtures" / "caddie_golden_cases.json"


def _club_name(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("clubName") or value.get("club") or "").strip()


def _is_driver(value: Any) -> bool:
    return _club_name(value).casefold() in {"driver", "1w", "1d"}


def _routes(case: dict[str, Any], profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {_club_name(row).casefold(): row for row in profiles}
    rows: list[dict[str, Any]] = []
    ids = ("conservative_layup", "stock_line", "aggressive_line")
    for index, name in enumerate(case.get("candidateClubs") or []):
        profile = by_name.get(str(name).casefold())
        if not profile:
            continue
        carry = float(profile.get("median") or profile.get("median_m") or 0)
        if carry <= 0:
            continue
        hazard_rows = [
            {
                "id": str(zone.get("id") or "hazard"),
                "kind": str(zone.get("kind") or "hazard"),
                **(
                    {"carryToFront_m": zone["carryToFrontM"]}
                    if zone.get("carryToFrontM") is not None
                    else {}
                ),
                **(
                    {"carryToClear_m": zone["carryToClearM"]}
                    if zone.get("carryToClearM") is not None
                    else {}
                ),
            }
            for zone in case.get("hazards") or []
        ]
        route_id = ids[min(index, len(ids) - 1)]
        rows.append(
            {
                "id": route_id,
                "label": route_id,
                "club": name,
                "carry_m": carry,
                "landingLocal": [0.0, carry],
                "expectedSurface": {"kind": "fairway"},
                "nearRisks": [],
                "lineRisks": hazard_rows,
                "riskScore": float(index),
                "source": "golden_fixture",
            }
        )
    return rows


def _context(case: dict[str, Any], profiles: list[dict[str, Any]]) -> dict[str, Any]:
    hazards = [
        {
            "id": str(zone.get("id") or "hazard"),
            "kind": str(zone.get("kind") or "hazard"),
            **(
                {"carryToFront_m": zone["carryToFrontM"]}
                if zone.get("carryToFrontM") is not None
                else {}
            ),
            **(
                {"carryToClear_m": zone["carryToClearM"]}
                if zone.get("carryToClearM") is not None
                else {}
            ),
        }
        for zone in case.get("hazards") or []
    ]
    return {
        "roundId": f"golden:{case['id']}",
        "source": "golden_fixture",
        "sourceRef": f"golden:{case['id']}",
        "courseName": "Golden Course",
        "hole": 1,
        "globalId": int(case.get("globalId") or 900000),
        "localHole": 1,
        "teeBox": "blue",
        "par": int(case.get("par") or 4),
        "holeRemaining_m": float(case.get("distanceM") or 0),
        "distanceToPin_m": float(case.get("distanceM") or 0),
        "lie": case.get("lie") or "tee",
        "windSpeedMps": case.get("windSpeedMps"),
        "slopeAdjustmentM": case.get("slopeAdjustmentM"),
        "geometry": {"hasHazards": bool(hazards), "hasMeshes": True, "hazardCount": len(hazards)},
        "hazards": hazards,
        "clubProfiles": {
            _club_name(row): {
                "clubName": _club_name(row),
                "sampleSize": int(row.get("sampleSize") or 0),
                "median": row.get("median"),
                "p10": row.get("p10"),
                "p90": row.get("p90"),
            }
            for row in profiles
        },
        "candidateRoutes": _routes(case, profiles),
    }


def _plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    selected = plan.get("selected") if isinstance(plan.get("selected"), dict) else {}
    sequences = plan.get("sequences") if isinstance(plan.get("sequences"), list) else []
    sequence_rows = []
    for sequence in sequences:
        if not isinstance(sequence, dict):
            continue
        clubs = [
            _club_name(step)
            for step in sequence.get("clubs") or []
            if isinstance(step, dict)
        ]
        sequence_rows.append({"id": sequence.get("id"), "clubs": clubs, "expectedRemaining_m": sequence.get("expectedRemaining_m")})
    selected_sequence = plan.get("selectedSequence") if isinstance(plan.get("selectedSequence"), dict) else {}
    selected_clubs = [
        _club_name(step)
        for step in selected_sequence.get("clubs") or []
        if isinstance(step, dict)
    ]
    all_sequences = [row["clubs"] for row in sequence_rows]
    driver_non_tee = sum(1 for clubs in all_sequences for index, club in enumerate(clubs) if index > 0 and club.casefold() in {"driver", "1w", "1d"})
    return {
        "selectedOptionId": plan.get("selectedOptionId"),
        "selectedClub": selected.get("club") or (selected.get("clubRecommendation") or {}).get("clubs", [{}])[0].get("clubName") if selected else None,
        "optionIds": [row.get("id") for row in plan.get("options") or [] if isinstance(row, dict)],
        "sequences": sequence_rows,
        "selectedSequence": selected_clubs,
        "driverNonTee": driver_non_tee,
        "confidence": (plan.get("confidence") or {}).get("level"),
        "missingLabels": sorted(str(row.get("label") or "") for row in plan.get("missingData") or [] if isinstance(row, dict)),
        "selectedMissingLabels": sorted(str(row.get("label") or "") for row in selected.get("missingData") or [] if isinstance(row, dict)),
        "selectedReason": selected.get("rationale") if selected else None,
    }


def _checks(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    expect = case.get("expect") or {}
    selected_sequence = output.get("selectedSequence") or []
    checks: dict[str, bool] = {}
    if expect.get("firstClub"):
        checks["firstClub"] = bool(selected_sequence) and selected_sequence[0] == expect["firstClub"]
    if expect.get("firstClubNot"):
        checks["firstClubNot"] = bool(selected_sequence) and selected_sequence[0] != expect["firstClubNot"]
    if "driverNonTee" in expect:
        checks["driverNonTee"] = output.get("driverNonTee") == expect["driverNonTee"]
    if expect.get("maxSteps") is not None:
        checks["maxSteps"] = len(selected_sequence) <= int(expect["maxSteps"])
    if expect.get("confidenceNotHigh"):
        checks["confidenceNotHigh"] = output.get("confidence") != "high"
    if expect.get("reasonRequired"):
        checks["reasonRequired"] = bool(output.get("missingLabels") or output.get("selectedMissingLabels") or output.get("selectedReason"))
    if expect.get("distinctAlternatives"):
        signatures = {tuple(row.get("clubs") or []) for row in output.get("sequences") or []}
        checks["distinctAlternatives"] = len(signatures) == len(output.get("sequences") or [])
    if expect.get("waterIntervals") is not None:
        checks["waterIntervals"] = output.get("intervalCount") == expect["waterIntervals"]
    return {"checks": checks, "failedChecks": sorted(name for name, passed in checks.items() if not passed)}


def replay(fixture: dict[str, Any]) -> dict[str, Any]:
    results = []
    profile_sets = fixture.get("profileSets") or {}
    for case in fixture.get("cases") or []:
        profiles = profile_sets.get(case.get("profileSet")) or []
        if case.get("kind") == "hazard_projection":
            zones = [
                {
                    "id": row.get("id"),
                    "kind": row.get("kind"),
                    "carryToFront_m": row.get("carryToFrontM"),
                    "carryToClear_m": row.get("carryToClearM"),
                    "intervalIndex": index,
                }
                for index, row in enumerate(case.get("hazards") or [])
            ]
            evidence = {"hazardClearances": zones, "avoidZones": zones}
            kept = _route_evidence_zones(evidence)
            projected = _shift_hazard_zones(kept, 197.5)
            output = {"intervalCount": len(kept), "projectedIntervalCount": len(projected), "intervalIndexes": [row.get("intervalIndex") for row in kept]}
            output.update(_checks(case, output))
            results.append({"id": case["id"], "kind": case["kind"], "output": output})
            continue
        plan = build_decision_plan(_context(case, profiles))
        output = _plan_summary(plan)
        output.update(_checks(case, output))
        results.append({"id": case["id"], "kind": case.get("kind"), "output": output})
    return {
        "schema": "ai-caddie-caddie-golden-replay-v1",
        "fixtureSha256": hashlib.sha256(json.dumps(fixture, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "caseCount": len(results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    output = replay(fixture)
    text = json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
