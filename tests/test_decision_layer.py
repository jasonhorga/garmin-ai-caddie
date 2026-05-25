from __future__ import annotations

import unittest

from ai_caddie.analysis import _hole_summary, llm_brief
from ai_caddie.decision import build_decision_plan, judge_decision_outcome
from ai_caddie_web import INDEX_HTML


def analysis_fixture(*, stock_risk=1, first_shot=None):
    return {
        "roundId": "round-1",
        "source": "garmin",
        "courseName": "Test Course",
        "hole": 1,
        "globalId": 100,
        "localHole": 1,
        "teeBox": "blue",
        "geometry": {"hasHazards": True, "hasMeshes": True, "hazardCount": 8},
        "dataQuality": {"confidence": "high", "issues": []},
        "clubProfiles": {
            "3H": {"clubName": "3H", "sampleSize": 44, "median": 178.0, "p10": 158.0, "p90": 198.0},
            "1W": {"clubName": "1W", "sampleSize": 81, "median": 220.0, "p10": 190.0, "p90": 248.0},
            "Putter": {"clubName": "Putter", "sampleSize": 200, "median": 8.0, "p10": 1.0, "p90": 20.0},
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
                "lineRisks": [{"kind": "bunker", "id": "bunker_1"}] if stock_risk else [],
                "riskScore": stock_risk,
            },
            {
                "id": "aggressive_line",
                "label": "attack line",
                "carry_m": 220.0,
                "landingLocal": [0.0, 220.0],
                "expectedSurface": {"kind": "rough"},
                "nearRisks": [{"kind": "water", "distance_m": 9.0}],
                "lineRisks": [{"kind": "water", "id": "water_1"}],
                "riskScore": 4,
            },
        ],
        "shots": [first_shot] if first_shot else [],
    }


class DecisionLayerTests(unittest.TestCase):
    def test_decision_payload_uses_v2_contract(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))

        self.assertEqual(plan["schema"], "ai-caddie-decision-v2")
        self.assertEqual(plan["shotType"], "tee")
        self.assertIn(plan["shotType"], {"tee", "approach", "recovery"})
        self.assertIsInstance(plan["options"], list)
        self.assertIsInstance(plan["selected"], dict)
        self.assertEqual(plan["selected"]["id"], "stock")
        self.assertIn("avoidZones", plan)
        self.assertIn("evidence", plan)
        self.assertIn("confidence", plan)
        self.assertIn("missingData", plan)
        self.assertIn("auditCriteria", plan)
        self.assertGreaterEqual(len(plan["auditCriteria"]), 1)

    def test_selects_stock_when_nearly_as_safe_as_safe(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))
        self.assertEqual(plan["selectedOptionId"], "stock")
        self.assertEqual(plan["selectedOption"]["routeId"], "stock_line")

    def test_selects_safe_when_stock_is_materially_riskier(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=3))
        self.assertEqual(plan["selectedOptionId"], "safe")

    def test_recommends_clubs_near_option_carry(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))
        clubs = [club["clubName"] for club in plan["selectedOption"]["clubRecommendation"]["clubs"]]
        self.assertIn("3H", clubs)
        self.assertNotIn("Putter", clubs)

    def test_outcome_execution_when_selected_plan_hits_known_risk(self) -> None:
        shot = {
            "shotOrder": 1,
            "clubName": "3H",
            "meters": 181.0,
            "end": {
                "lie": "Bunker",
                "feature": {
                    "surface": {"kind": "bunker"},
                    "nearRisks": [{"kind": "bunker", "distance_m": 0.0}],
                },
            },
        }
        analysis = analysis_fixture(stock_risk=1, first_shot=shot)
        plan = build_decision_plan(analysis)
        outcome = judge_decision_outcome(plan, analysis)
        self.assertEqual(outcome["failureType"], "execution")
        self.assertTrue(outcome["executionMatch"]["riskTriggered"])

    def test_outcome_strategy_when_player_takes_riskier_option_and_hits_risk(self) -> None:
        shot = {
            "shotOrder": 1,
            "clubName": "1W",
            "meters": 221.0,
            "end": {
                "lie": "Water",
                "feature": {
                    "surface": {"kind": "water"},
                    "nearRisks": [{"kind": "water", "distance_m": 0.0}],
                },
            },
        }
        analysis = analysis_fixture(stock_risk=1, first_shot=shot)
        plan = build_decision_plan(analysis)
        outcome = judge_decision_outcome(plan, analysis)
        self.assertEqual(outcome["actualOptionId"], "attack")
        self.assertEqual(outcome["failureType"], "strategy")

    def test_outcome_info_gap_without_first_shot(self) -> None:
        analysis = analysis_fixture(stock_risk=1)
        plan = build_decision_plan(analysis)
        outcome = judge_decision_outcome(plan, analysis)
        self.assertEqual(outcome["failureType"], "info_gap")

    def test_hole_summary_exposes_decision_audit(self) -> None:
        shot = {
            "shotOrder": 1,
            "clubName": "3H",
            "meters": 181.0,
            "start": {"local": [0.0, 0.0], "lie": "TeeBox"},
            "end": {
                "lie": "Fairway",
                "feature": {"surface": {"kind": "fairway"}, "nearRisks": []},
            },
        }
        analysis = analysis_fixture(stock_risk=1, first_shot=shot)
        analysis["decisionPlan"] = build_decision_plan(analysis)
        analysis["decisionOutcome"] = judge_decision_outcome(analysis["decisionPlan"], analysis)
        analysis["review"] = "review"
        summary = _hole_summary(analysis)
        self.assertEqual(summary["decision"]["selectedOptionId"], "stock")
        self.assertEqual(summary["decision"]["failureType"], "variance")

    def test_llm_brief_includes_decision_facts(self) -> None:
        analysis = analysis_fixture(stock_risk=1)
        analysis["decisionPlan"] = build_decision_plan(analysis)
        analysis["decisionOutcome"] = judge_decision_outcome(analysis["decisionPlan"], analysis)
        brief = llm_brief(analysis)
        self.assertEqual(brief["facts"]["decision"]["selectedOptionId"], "stock")
        self.assertEqual(brief["facts"]["decision"]["failureType"], "info_gap")

    def test_web_app_has_decision_card_entrypoint(self) -> None:
        self.assertIn('id="decisionCard"', INDEX_HTML)
        self.assertIn("function decisionCard", INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
