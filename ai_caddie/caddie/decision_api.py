"""Request helpers for deterministic caddie decisions."""

from __future__ import annotations

from typing import Any, Literal

from ai_caddie.caddie.decision import build_decision_plan, generate_decision_explanation, recommend_approach, recommend_recovery


ShotType = Literal["tee", "approach", "recovery"]
VALID_SHOT_TYPES: set[str] = {"tee", "approach", "recovery"}


def validate_shot_type(value: str) -> ShotType:
    if value not in VALID_SHOT_TYPES:
        raise ValueError(f"unsupported shotType: {value}")
    return value  # type: ignore[return-value]


def normalize_decision_request(payload: dict[str, Any]) -> dict[str, Any]:
    shot_type = validate_shot_type(str(payload.get("shotType") or ""))
    context = payload.get("context") or {}
    if not isinstance(context, dict):
        raise ValueError("context must be an object")
    normalized_context = dict(context)
    normalized_context["shotType"] = shot_type
    return {"shotType": shot_type, "context": normalized_context}


def build_decision_from_request(payload: dict[str, Any]) -> dict[str, Any]:
    request = normalize_decision_request(payload)
    shot_type = request["shotType"]
    context = request["context"]
    if shot_type == "tee":
        decision = build_decision_plan(context)
    elif shot_type == "approach":
        decision = recommend_approach(context)
    else:
        decision = recommend_recovery(context)
    if payload.get("includeExplanation", True) is not False and context.get("includeExplanation", True) is not False:
        decision["explanation"] = generate_decision_explanation(decision)
    return decision


def build_decision_request_from_fixture(shot_type: ShotType = "approach") -> dict[str, Any]:
    validate_shot_type(shot_type)
    if shot_type == "tee":
        context = {
            "roundId": "fixture-round",
            "source": "fixture",
            "courseName": "Fixture Links",
            "hole": 1,
            "globalId": 31795,
            "localHole": 1,
            "teeBox": "blue",
            "geometry": {"hasHazards": True, "hasMeshes": True, "hazardCount": 6},
            "dataQuality": {"confidence": "high", "issues": []},
            "clubProfiles": {
                "3H": {"clubName": "3H", "sampleSize": 36, "median": 178.0, "p10": 158.0, "p90": 198.0},
                "1W": {"clubName": "1W", "sampleSize": 75, "median": 221.0, "p10": 190.0, "p90": 249.0},
            },
            "candidateRoutes": [
                {
                    "id": "conservative_layup",
                    "label": "safe layup",
                    "carry_m": 170.0,
                    "landingLocal": [0.0, 170.0],
                    "expectedSurface": {"kind": "fairway"},
                    "nearRisks": [],
                    "lineRisks": [],
                    "riskScore": 0,
                },
                {
                    "id": "stock_line",
                    "label": "stock line",
                    "carry_m": 180.0,
                    "landingLocal": [0.0, 180.0],
                    "expectedSurface": {"kind": "fairway"},
                    "nearRisks": [],
                    "lineRisks": [{"kind": "bunker", "id": "bunker_1"}],
                    "riskScore": 1,
                },
                {
                    "id": "aggressive_line",
                    "label": "attack line",
                    "carry_m": 221.0,
                    "landingLocal": [0.0, 221.0],
                    "expectedSurface": {"kind": "rough"},
                    "nearRisks": [{"kind": "water", "distance_m": 9.0}],
                    "lineRisks": [{"kind": "water", "id": "water_1"}],
                    "riskScore": 4,
                },
            ],
        }
    elif shot_type == "approach":
        context = {
            "roundId": "fixture-round",
            "source": "fixture",
            "courseName": "Fixture Links",
            "hole": 4,
            "globalId": 31795,
            "localHole": 4,
            "distanceToPin_m": 142.0,
            "lie": "fairway",
            "geometry": {"hasHazards": True, "hasMeshes": True, "hazardCount": 3},
            "hazards": [{"kind": "water", "id": "water_front", "carryToClear_m": 126.0, "distance_m": 14.0}],
            "clubProfiles": {
                "9I": {"clubName": "9I", "sampleSize": 24, "median": 132.0, "p10": 120.0, "p90": 140.0},
                "8I": {"clubName": "8I", "sampleSize": 24, "median": 144.0, "p10": 132.0, "p90": 153.0},
                "7I": {"clubName": "7I", "sampleSize": 24, "median": 156.0, "p10": 142.0, "p90": 168.0},
            },
        }
    else:
        context = {
            "roundId": "fixture-round",
            "source": "fixture",
            "courseName": "Fixture Links",
            "hole": 11,
            "globalId": 31795,
            "localHole": 11,
            "distanceToPin_m": 178.0,
            "lie": "rough",
            "blockedView": True,
            "geometry": {"hasHazards": True, "hasMeshes": True, "hazardCount": 3},
            "hazards": [{"kind": "tree_area", "id": "trees_right", "distance_m": 6.0}],
            "clubProfiles": {
                "9I": {"clubName": "9I", "sampleSize": 24, "median": 132.0, "p10": 120.0, "p90": 140.0},
                "8I": {"clubName": "8I", "sampleSize": 24, "median": 144.0, "p10": 132.0, "p90": 153.0},
                "7I": {"clubName": "7I", "sampleSize": 24, "median": 156.0, "p10": 142.0, "p90": 168.0},
            },
        }
    return {"shotType": shot_type, "context": context}
