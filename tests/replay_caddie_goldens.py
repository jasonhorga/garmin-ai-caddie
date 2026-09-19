"""Replay the checked-in caddie cases and emit deterministic gate evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from ai_caddie.caddie.decision import (
    _club_water_safety,
    _route_evidence_zones,
    _shift_hazard_zones,
    build_decision_plan,
)
from ai_caddie.caddie.mobile_live import _tee_candidate_routes


FIXTURE = Path(__file__).parent / "fixtures" / "caddie_golden_cases.json"


def _club_name(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("clubName") or value.get("club") or "").strip()


def _is_driver_name(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"driver", "1w", "1d"}


def _profile_rows(case: dict[str, Any], profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize the fixture bag to the exact shape consumed by the production scorer."""
    requested = {
        str(name).strip().casefold()
        for name in case.get("candidateClubs") or []
        if str(name).strip()
    }
    rows: list[dict[str, Any]] = []
    for raw in profiles:
        name = _club_name(raw)
        if not name or (requested and name.casefold() not in requested):
            continue
        median = raw.get("median_m") if raw.get("median_m") is not None else raw.get("median")
        if median is None or float(median) <= 0:
            continue
        row = dict(raw)
        row["clubName"] = name
        row["median_m"] = float(median)
        row["p10_m"] = float(
            raw.get("p10_m")
            if raw.get("p10_m") is not None
            else raw.get("p10")
            if raw.get("p10") is not None
            else median
        )
        row["p90_m"] = float(
            raw.get("p90_m")
            if raw.get("p90_m") is not None
            else raw.get("p90")
            if raw.get("p90") is not None
            else median
        )
        if _is_driver_name(name) and case.get("driverLateralP10P90M") is not None:
            row["lateralP10P90_m"] = float(case["driverLateralP10P90M"])
        rows.append(row)
    return rows


def _hazard_rows(case: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, zone in enumerate(case.get("hazards") or []):
        if not isinstance(zone, dict):
            continue
        row = {
            "id": str(zone.get("id") or f"hazard-{index}"),
            "kind": str(zone.get("kind") or "hazard"),
            "intervalIndex": int(zone.get("intervalIndex") if zone.get("intervalIndex") is not None else index),
        }
        if zone.get("carryToFrontM") is not None:
            row["carryToFront_m"] = float(zone["carryToFrontM"])
        if zone.get("carryToClearM") is not None:
            row["carryToClear_m"] = float(zone["carryToClearM"])
        if zone.get("side") is not None:
            row["side"] = str(zone["side"])
        if case.get("courseWidthM") is not None and row["kind"] in {"out_of_bounds", "ob"}:
            row["corridorWidth_m"] = float(case["courseWidthM"])
        rows.append(row)
    return rows


def _routes(
    case: dict[str, Any],
    profiles: list[dict[str, Any]],
    hazards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    distance_m = float(case.get("distanceM") or 0)
    lie = str(case.get("lie") or "tee").strip().lower().replace("-", "_").replace(" ", "_")
    route_profiles = (
        [row for row in profiles if not _is_driver_name(_club_name(row))]
        if lie not in {"", "tee", "tee_box", "teebox", "unknown"}
        else profiles
    )
    return _tee_candidate_routes(
        {"yards": round(distance_m / 0.9144, 1) if distance_m > 0 else 0},
        route_profiles,
        hazards,
        par=int(case.get("par") or 4),
        target_m=distance_m,
        avoid_zones=hazards,
    )


def _context(
    case: dict[str, Any],
    profiles: list[dict[str, Any]],
    hazards: list[dict[str, Any]],
) -> dict[str, Any]:
    distance_m = float(case.get("distanceM") or 0)
    wind_speed = float(case.get("windSpeedMps") or 0)
    candidate_routes = _routes(case, profiles, hazards)
    candidate_state = "ready" if candidate_routes else "missing"
    if hazards and not candidate_routes:
        candidate_state = "infeasible"
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
        "holeRemaining_m": distance_m,
        "distanceToPin_m": distance_m,
        "currentLocation": {"latitude": 39.0, "longitude": 116.0},
        "lie": case.get("lie") or "tee",
        "slopeAdjustmentM": case.get("slopeAdjustmentM"),
        "courseWidthM": case.get("courseWidthM"),
        "driverLateralP10P90M": case.get("driverLateralP10P90M"),
        "weatherSnapshot": {
            "state": "ready",
            "windSpeedMps": wind_speed,
            "windDirectionDeg": 0,
        },
        "dataQuality": {"confidence": "high", "issues": []},
        "geometry": {
            "coverage": "ready",
            "hasHazards": True,
            "hasMeshes": True,
            "hazardCount": len(hazards),
        },
        "hazards": hazards,
        "routeEvidence": {
            "routeLength_m": distance_m,
            "hazardClearances": hazards,
            "avoidZones": hazards,
        },
        "clubProfiles": {
            _club_name(row): {
                **row,
                "median": row["median_m"],
                "p10": row["p10_m"],
                "p90": row["p90_m"],
            }
            for row in profiles
        },
        "candidateRoutes": candidate_routes,
        "candidateRoutesState": candidate_state,
        **(
            {"candidateRoutesReason": "No measured club can safely satisfy the current route hazards."}
            if candidate_state == "infeasible"
            else {}
        ),
    }


def _profile_by_name(profiles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_club_name(row).casefold(): row for row in profiles if _club_name(row)}


def _sequence_audit(
    sequence: dict[str, Any],
    profiles: list[dict[str, Any]],
    hazards: list[dict[str, Any]],
) -> dict[str, Any]:
    by_name = _profile_by_name(profiles)
    travelled_m = 0.0
    steps: list[dict[str, Any]] = []
    water_crossings = 0
    for index, raw_step in enumerate(sequence.get("clubs") or []):
        if not isinstance(raw_step, dict):
            continue
        name = _club_name(raw_step)
        carry_m = float(raw_step.get("targetCarry_m") or 0)
        projected = _shift_hazard_zones(hazards, travelled_m)
        profile = by_name.get(name.casefold()) or {
            "clubName": name,
            "median_m": carry_m,
            "p10_m": raw_step.get("p10_m", carry_m),
            "p90_m": raw_step.get("p90_m", carry_m),
        }
        water_state = _club_water_safety(profile, projected)
        if water_state == "risk":
            water_crossings += 1
        production_projection = raw_step.get("hazardProjection")
        steps.append(
            {
                "index": index,
                "club": name,
                "carry_m": round(carry_m, 1),
                "originOffset_m": round(travelled_m, 1),
                "waterState": water_state,
                "projectedIntervals": [
                    {
                        "id": row.get("id"),
                        "intervalIndex": row.get("intervalIndex"),
                        "front_m": row.get("carryToFront_m"),
                        "clear_m": row.get("carryToClear_m"),
                    }
                    for row in projected
                ],
                "productionOriginOffset_m": (
                    production_projection.get("originOffset_m")
                    if isinstance(production_projection, dict)
                    else None
                ),
            }
        )
        travelled_m += carry_m
    production_reprojected = all(
        math.isclose(
            float(step["productionOriginOffset_m"]),
            float(step["originOffset_m"]),
            abs_tol=0.1,
        )
        for step in steps[1:]
        if step.get("productionOriginOffset_m") is not None
    ) and all(step.get("productionOriginOffset_m") is not None for step in steps[1:])
    return {
        "steps": steps,
        "waterCrossings": water_crossings,
        "productionReprojected": bool(steps) and production_reprojected,
    }


def _reason_signals(plan: dict[str, Any], selected: dict[str, Any], selected_sequence: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for value in selected.get("selectionReasons") or []:
        if isinstance(value, dict):
            reason = str(value.get("reason") or value.get("text") or value.get("label") or "").strip()
        else:
            reason = str(value or "").strip()
        if reason:
            reasons.append(reason)
    for zone in selected.get("avoidZones") or selected.get("forbiddenZones") or []:
        if isinstance(zone, dict) and str(zone.get("reason") or "").strip():
            reasons.append(str(zone["reason"]).strip())
    recommendation = selected.get("clubRecommendation") if isinstance(selected.get("clubRecommendation"), dict) else {}
    if str(recommendation.get("infeasibleReason") or "").strip():
        reasons.append(str(recommendation["infeasibleReason"]).strip())
    confidence = plan.get("confidence") if isinstance(plan.get("confidence"), dict) else {}
    for value in confidence.get("reasons") or []:
        reason = str(value or "").strip()
        if reason.startswith("selected club") or reason.startswith("no candidate route"):
            reasons.append(reason)
    if selected_sequence.get("completion") == "replan_required":
        reasons.append(str(selected_sequence.get("rationale") or "re-plan required").strip())
    return sorted(set(reasons))


def _plan_summary(
    plan: dict[str, Any],
    profiles: list[dict[str, Any]],
    hazards: list[dict[str, Any]],
) -> dict[str, Any]:
    selected = plan.get("selected") if isinstance(plan.get("selected"), dict) else {}
    sequences = plan.get("sequences") if isinstance(plan.get("sequences"), list) else []
    sequence_rows: list[dict[str, Any]] = []
    water_crossings = 0
    driver_non_tee = 0
    max_second_increase_m = -math.inf
    production_reprojected = True
    context = plan.get("context") if isinstance(plan.get("context"), dict) else {}
    initial_lie = str(context.get("lie") or "tee").strip().lower().replace("-", "_").replace(" ", "_")
    initial_non_tee = initial_lie not in {"", "tee", "tee_box", "teebox", "unknown"}
    for sequence in sequences:
        if not isinstance(sequence, dict):
            continue
        audit = _sequence_audit(sequence, profiles, hazards)
        steps = [row for row in sequence.get("clubs") or [] if isinstance(row, dict)]
        clubs = [_club_name(step) for step in steps]
        carries = [float(step.get("targetCarry_m") or 0) for step in steps]
        driver_non_tee += sum(
            1
            for index, club in enumerate(clubs)
            if (index > 0 or initial_non_tee) and _is_driver_name(club)
        )
        if len(carries) >= 2:
            max_second_increase_m = max(max_second_increase_m, carries[1] - carries[0])
        water_crossings += int(audit["waterCrossings"])
        if len(steps) >= 2:
            production_reprojected = production_reprojected and bool(audit["productionReprojected"])
        sequence_rows.append(
            {
                "id": sequence.get("id"),
                "clubs": clubs,
                "carries_m": carries,
                "expectedRemaining_m": sequence.get("expectedRemaining_m"),
                "completion": sequence.get("completion"),
                "audit": audit,
            }
        )

    selected_sequence = plan.get("selectedSequence") if isinstance(plan.get("selectedSequence"), dict) else {}
    selected_sequence_id = selected_sequence.get("id")
    selected_clubs = [
        _club_name(step)
        for step in selected_sequence.get("clubs") or []
        if isinstance(step, dict)
    ]
    recommendation = selected.get("clubRecommendation") if isinstance(selected.get("clubRecommendation"), dict) else {}
    recommended_clubs = recommendation.get("clubs") if isinstance(recommendation.get("clubs"), list) else []
    selected_club = str(
        selected.get("club")
        or (_club_name(recommended_clubs[0]) if recommended_clubs else "")
    )
    selected_first_club = selected_clubs[0] if selected_clubs else selected_club

    option_rows = []
    for option in plan.get("options") or []:
        if not isinstance(option, dict):
            continue
        option_recommendation = option.get("clubRecommendation") if isinstance(option.get("clubRecommendation"), dict) else {}
        option_clubs = option_recommendation.get("clubs") if isinstance(option_recommendation.get("clubs"), list) else []
        option_club = str(
            option.get("club")
            or (_club_name(option_clubs[0]) if option_clubs else "")
        )
        option_rows.append(
            {
                "id": option.get("id"),
                "club": option_club,
                "carry_m": option.get("carry_m"),
                "riskScore": option.get("riskScore"),
                "avoidZones": option.get("avoidZones") or [],
                "confidence": option.get("confidence"),
                "infeasibleReason": option_recommendation.get("infeasibleReason"),
            }
        )
    by_id = {str(row.get("id")): row for row in option_rows}
    ordered_risks = [
        float(by_id[option_id].get("riskScore") or 0)
        for option_id in ("safe", "stock", "attack")
        if option_id in by_id
    ]
    labels_monotonic = all(
        current <= following + 1e-9
        for current, following in zip(ordered_risks, ordered_risks[1:])
    )
    option_signatures = {
        (str(row.get("club") or "").casefold(), round(float(row.get("carry_m") or 0), 1))
        for row in option_rows
    }
    sequence_signatures = {tuple(row["clubs"]) for row in sequence_rows}
    distinct_alternatives = (
        len(option_signatures) == len(option_rows)
        and len(sequence_signatures) == len(sequence_rows)
    )
    if not sequence_rows and initial_non_tee and _is_driver_name(selected_first_club):
        driver_non_tee += 1
    return {
        "selectedOptionId": plan.get("selectedOptionId"),
        "selectedSequenceId": selected_sequence_id,
        "selectionAligned": selected_sequence_id is None or selected_sequence_id == plan.get("selectedOptionId"),
        "selectedClub": selected_club or None,
        "selectedFirstClub": selected_first_club or None,
        "options": option_rows,
        "optionIds": [row.get("id") for row in option_rows],
        "sequences": sequence_rows,
        "selectedSequence": selected_clubs,
        "driverNonTee": driver_non_tee,
        "maxSecondIncreaseM": None if max_second_increase_m == -math.inf else round(max_second_increase_m, 1),
        "waterCrossings": water_crossings,
        "labelsMonotonic": labels_monotonic,
        "distinctAlternatives": distinct_alternatives,
        "productionReprojected": bool(sequence_rows) and production_reprojected,
        "confidence": (plan.get("confidence") or {}).get("level"),
        "missingLabels": sorted(
            str(row.get("label") or "")
            for row in plan.get("missingData") or []
            if isinstance(row, dict)
        ),
        "selectedMissingLabels": sorted(
            str(row.get("label") or "")
            for row in selected.get("missingData") or []
            if isinstance(row, dict)
        ),
        "reasonSignals": _reason_signals(plan, selected, selected_sequence),
        "originGlobalId": context.get("globalId"),
    }


def _checks(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    expect = case.get("expect") or {}
    selected_sequence = output.get("selectedSequence") or []
    checks: dict[str, bool] = {}
    if expect.get("firstClub"):
        checks["firstClub"] = output.get("selectedFirstClub") == expect["firstClub"]
    if expect.get("firstClubNot"):
        checks["firstClubNot"] = bool(output.get("selectedFirstClub")) and output.get("selectedFirstClub") != expect["firstClubNot"]
    if "driverNonTee" in expect:
        checks["driverNonTee"] = output.get("driverNonTee") == expect["driverNonTee"]
    if expect.get("maxSteps") is not None:
        checks["maxSteps"] = bool(selected_sequence) and len(selected_sequence) <= int(expect["maxSteps"])
    if expect.get("confidenceNotHigh"):
        checks["confidenceNotHigh"] = output.get("confidence") != "high"
    if expect.get("reasonRequired"):
        checks["reasonRequired"] = bool(output.get("reasonSignals"))
    if expect.get("distinctAlternatives"):
        checks["distinctAlternatives"] = bool(output.get("distinctAlternatives"))
    if expect.get("secondLongerThanFirstByM") is not None:
        increase = output.get("maxSecondIncreaseM")
        checks["secondLongerThanFirstByM"] = increase is not None and float(increase) <= float(expect["secondLongerThanFirstByM"])
    if expect.get("waterCrossings") is not None:
        checks["waterCrossings"] = output.get("waterCrossings") == expect["waterCrossings"]
    if expect.get("labelsMonotonic"):
        checks["labelsMonotonic"] = bool(output.get("labelsMonotonic"))
    if expect.get("backNineMustKeepOrigin"):
        origin = output.get("originGlobalId")
        checks["backNineMustKeepOrigin"] = origin == case.get("globalId") and origin != case.get("backGlobalId")
    if expect.get("reprojected"):
        checks["reprojected"] = bool(output.get("productionReprojected"))
    if expect.get("waterIntervals") is not None:
        checks["waterIntervals"] = output.get("intervalCount") == expect["waterIntervals"]
    if expect.get("mergedIntervals") is not None:
        checks["mergedIntervals"] = output.get("mergedIntervals") is expect["mergedIntervals"]
    return {
        "checks": checks,
        "failedChecks": sorted(name for name, passed in checks.items() if not passed),
        "uncheckedExpectations": sorted(set(expect) - set(checks)),
    }


def replay(fixture: dict[str, Any]) -> dict[str, Any]:
    results = []
    profile_sets = fixture.get("profileSets") or {}
    for case in fixture.get("cases") or []:
        profiles = _profile_rows(case, profile_sets.get(case.get("profileSet")) or [])
        hazards = _hazard_rows(case)
        if case.get("kind") == "hazard_projection":
            evidence = {"hazardClearances": hazards, "avoidZones": hazards}
            kept = _route_evidence_zones(evidence)
            projected = _shift_hazard_zones(kept, 197.5)
            output = {
                "inputIntervalCount": len(hazards),
                "intervalCount": len(kept),
                "projectedIntervalCount": len(projected),
                "intervalIndexes": [row.get("intervalIndex") for row in kept],
                "mergedIntervals": len(kept) < len(hazards),
            }
            output.update(_checks(case, output))
            results.append({"id": case["id"], "kind": case["kind"], "output": output})
            continue
        plan = build_decision_plan(_context(case, profiles, hazards))
        output = _plan_summary(plan, profiles, hazards)
        output.update(_checks(case, output))
        results.append({"id": case["id"], "kind": case.get("kind"), "output": output})
    return {
        "schema": "ai-caddie-caddie-golden-replay-v2",
        "fixtureSha256": hashlib.sha256(
            json.dumps(fixture, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
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
