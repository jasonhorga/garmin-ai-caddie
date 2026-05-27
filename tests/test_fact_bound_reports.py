from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.fixtures import fixture_history_data
from ai_caddie.history import HistoryData
from ai_caddie.llm_providers import LLMMessage, StaticProvider
from ai_caddie.history_stats import build_history_stats
from ai_caddie.reports import (
    build_round_report_facts,
    build_trend_report_facts,
    generate_report,
    latest_report_record,
    list_report_records,
    redact_private_text,
    report_source_refs,
    store_report,
)


class RecordingProvider:
    model = "recording-model"

    def __init__(self) -> None:
        self.messages: list[LLMMessage] = []

    def chat(self, messages, max_tokens=None):  # type: ignore[no-untyped-def]
        self.messages = list(messages)
        return "事实复盘"


class FactBoundReportTests(unittest.TestCase):
    def test_round_report_includes_facts_missing_data_and_provider_metadata(self) -> None:
        facts = build_round_report_facts(
            {
                "schema": "ai-caddie-history-stats-v1",
                "summary": {"totalRounds": 3, "average18": 86.0, "bestScore": 77},
                "scoring": {
                    "scoreBands": [{"label": "70s", "count": 1, "roundIds": ["900001"]}],
                    "putting": {"totalPutts": 88, "threePutts": 4, "threePuttRefs": ["900001:7"]},
                    "phaseStats": [{"phase": "Approach", "gir": 21, "missedGir": 24, "holeRefs": ["900001:7"]}],
                },
                "courseDistribution": [{"courseKey": "black_knight", "roundCount": 2, "pct": 66.7}],
                "issues": [{"issue": "approach_short", "phase": "Approach", "count": 2, "sourceRefs": ["900001:7"]}],
                "records": {
                    "best18": {"score": 77, "roundRef": "900001"},
                    "longestShots": [{"club": "1D", "distance": 238.0, "shotRef": "900001:1:0"}],
                },
                "dataQuality": [
                    {"label": "shots", "state": "partial", "ready": 2, "total": 3, "refs": ["900002"]},
                    {"label": "weather", "state": "partial", "ready": 1, "total": 45, "refs": ["900001:7"]},
                ],
                "drillDown": {"roundIds": ["900001"]},
            },
            "900001",
        )
        provider = RecordingProvider()

        band_fact = next(row for row in facts["factsUsed"] if row["label"] == "round_score_band")
        self.assertEqual(band_fact["value"]["roundRefs"], ["900001"])
        missing_by_label = {row["label"]: row for row in facts["missingData"]}
        self.assertEqual(missing_by_label["shots"]["refs"], ["900002"])
        self.assertEqual(missing_by_label["weather"]["refs"], ["900001:7"])

        report = generate_report(facts, provider)

        self.assertEqual(report["schema"], "ai-caddie-review-report-v1")
        self.assertEqual(report["kind"], "round")
        self.assertEqual(report["provider"], "RecordingProvider")
        self.assertEqual(report["model"], "recording-model")
        self.assertEqual(report["narrative"], "事实复盘")
        self.assertIn("factsUsed", report)
        self.assertIn("missingData", report)
        self.assertGreaterEqual(len(report["factsUsed"]), 3)
        labels = {row["label"] for row in report["factsUsed"]}
        self.assertIn("putting", labels)
        self.assertIn("phase_Approach", labels)
        self.assertIn("top_issue", labels)
        self.assertIn("course_distribution", labels)
        self.assertIn("record_book", labels)
        self.assertIn(report["confidence"], {"low", "medium", "high"})

    def test_generated_report_exposes_structured_inferences_bound_to_facts(self) -> None:
        facts = {
            "schema": "ai-caddie-report-facts-v1",
            "kind": "trend",
            "subjectId": "recent_10",
            "factsUsed": [
                {
                    "label": "summary_trend",
                    "source": "summary",
                    "value": {"totalRounds": 6, "recent10Average": 84.0},
                    "sourceRefs": ["round-1", "round-2"],
                    "confidence": "medium",
                },
                {
                    "label": "top_issues",
                    "source": "issues",
                    "value": [{"issue": "three_putt", "phase": "Putting", "count": 4, "sourceRefs": ["round-2:7"]}],
                    "sourceRefs": ["round-2:7"],
                    "confidence": "medium",
                },
                {
                    "label": "decision_audit_trends",
                    "source": "diagnosis.decisionAuditTrends",
                    "value": {
                        "totalAudits": 2,
                        "recentCostDrivers": [
                            {"classification": "execution", "estimatedStrokesLost": 1.8, "sourceRefs": ["round-2:7"]}
                        ],
                    },
                    "sourceRefs": ["round-2:7"],
                    "confidence": "medium",
                },
            ],
            "missingData": [
                {
                    "label": "weather",
                    "state": "partial",
                    "sourceRefs": ["round-2:7"],
                    "coverage": {"ready": 1, "total": 6, "pct": 16.7},
                }
            ],
        }

        report = generate_report(facts, StaticProvider("trend narrative"))

        inferences = report["inferencesMade"]
        self.assertGreaterEqual(len(inferences), 3)
        self.assertTrue(all(row["claim"] for row in inferences))
        self.assertTrue(all(row["confidence"] in {"low", "medium", "high"} for row in inferences))
        self.assertTrue(all("sourceRefs" in row for row in inferences))
        self.assertTrue(all("factLabels" in row for row in inferences))
        self.assertIn(
            {
                "claim": "Recent review is based on 6 rounds.",
                "factLabels": ["summary_trend"],
                "sourceRefs": ["round-1", "round-2"],
                "confidence": "medium",
                "missingDataRefs": ["round-2:7"],
                "missingDataLabels": ["weather"],
            },
            inferences,
        )
        self.assertTrue(any("three_putt" in row["claim"] and row["sourceRefs"] == ["round-2:7"] for row in inferences))
        self.assertTrue(any("execution" in row["claim"] and row["factLabels"] == ["decision_audit_trends"] for row in inferences))

    def test_generated_report_flags_sensitive_claims_not_supported_by_facts(self) -> None:
        facts = {
            "schema": "ai-caddie-report-facts-v1",
            "kind": "trend",
            "subjectId": "recent_10",
            "factsUsed": [
                {
                    "label": "summary_trend",
                    "source": "summary",
                    "value": {"totalRounds": 3, "recent10Average": 84.0},
                    "sourceRefs": ["900001", "900002", "900003"],
                }
            ],
            "missingData": [
                {
                    "label": "weather",
                    "state": "missing",
                    "sourceRefs": ["900001"],
                }
            ],
        }

        report = generate_report(
            facts,
            StaticProvider("Wind was strong all day. The rough lie caused a penalty and 8I was the wrong club."),
        )

        unsupported = report["unsupportedClaims"]
        self.assertEqual(report["factBinding"]["state"], "needs_review")
        self.assertEqual(report["factBinding"]["unsupportedClaimCount"], len(unsupported))
        self.assertEqual(report["confidence"], "low")
        self.assertIn("weather", {row["category"] for row in unsupported})
        self.assertIn("lie", {row["category"] for row in unsupported})
        self.assertIn("penalty", {row["category"] for row in unsupported})
        self.assertIn("club", {row["category"] for row in unsupported})
        self.assertTrue(all(row["claim"] for row in unsupported))
        self.assertTrue(all(row["missingDataLabels"] == ["weather"] for row in unsupported))

    def test_generated_report_allows_missing_data_callouts(self) -> None:
        facts = {
            "schema": "ai-caddie-report-facts-v1",
            "kind": "trend",
            "subjectId": "recent_10",
            "factsUsed": [
                {
                    "label": "summary_trend",
                    "source": "summary",
                    "value": {"totalRounds": 3, "recent10Average": 84.0},
                    "sourceRefs": ["900001", "900002", "900003"],
                }
            ],
            "missingData": [{"label": "weather", "state": "missing", "sourceRefs": ["900001"]}],
        }

        report = generate_report(facts, StaticProvider("Weather is missing, so wind should stay uncertain."))

        self.assertEqual(report["unsupportedClaims"], [])
        self.assertEqual(report["factBinding"], {"state": "bound", "unsupportedClaimCount": 0})
        self.assertEqual(report["confidence"], "medium")

    def test_report_audit_requires_specific_supported_fact_values(self) -> None:
        facts = {
            "schema": "ai-caddie-report-facts-v1",
            "kind": "round",
            "subjectId": "900001",
            "factsUsed": [
                {
                    "label": "round_shots",
                    "source": "history.shots",
                    "value": [{"shotRef": "900001:1:0", "club": None, "surface": None}],
                    "sourceRefs": ["900001:1:0"],
                }
            ],
            "missingData": [],
        }

        report = generate_report(facts, StaticProvider("The 8I was the wrong club. The rough lie caused the miss."))

        self.assertIn("club", {row["category"] for row in report["unsupportedClaims"]})
        self.assertIn("lie", {row["category"] for row in report["unsupportedClaims"]})

    def test_report_audit_does_not_flag_benign_observed_text_as_ob_penalty(self) -> None:
        facts = {
            "schema": "ai-caddie-report-facts-v1",
            "kind": "trend",
            "subjectId": "recent_10",
            "factsUsed": [{"label": "summary_trend", "source": "summary", "value": {"totalRounds": 3}}],
            "missingData": [],
        }

        report = generate_report(facts, StaticProvider("Observed scoring improved across the sample."))

        self.assertEqual(report["unsupportedClaims"], [])
        self.assertEqual(report["factBinding"], {"state": "bound", "unsupportedClaimCount": 0})

    def test_report_audit_flags_assertion_after_missing_data_callout(self) -> None:
        facts = {
            "schema": "ai-caddie-report-facts-v1",
            "kind": "trend",
            "subjectId": "recent_10",
            "factsUsed": [{"label": "summary_trend", "source": "summary", "value": {"totalRounds": 3}}],
            "missingData": [{"label": "weather", "state": "missing", "sourceRefs": ["900001"]}],
        }

        report = generate_report(facts, StaticProvider("Weather is missing, but wind was strong all day."))

        self.assertIn("weather", {row["category"] for row in report["unsupportedClaims"]})
        self.assertTrue(any("wind was strong" in row["claim"] for row in report["unsupportedClaims"]))

    def test_report_audit_flags_uncited_strategy_practice_and_causal_advice(self) -> None:
        facts = {
            "schema": "ai-caddie-report-facts-v1",
            "kind": "trend",
            "subjectId": "recent_10",
            "factsUsed": [
                {
                    "label": "summary_trend",
                    "source": "summary",
                    "value": {"totalRounds": 3, "recent10Average": 84.0},
                    "sourceRefs": ["900001", "900002", "900003"],
                }
            ],
            "missingData": [],
        }

        report = generate_report(
            facts,
            StaticProvider(
                "You should practice 30-yard bunker shots. The main cause is poor strategy, "
                "so aim away from flags on every approach."
            ),
        )

        categories = {row["category"] for row in report["unsupportedClaims"]}
        self.assertIn("practice_advice", categories)
        self.assertIn("strategy_advice", categories)
        self.assertIn("causal_claim", categories)
        self.assertEqual(report["factBinding"]["state"], "needs_review")

    def test_report_audit_does_not_let_broad_facts_support_unrelated_advice(self) -> None:
        facts = {
            "schema": "ai-caddie-report-facts-v1",
            "kind": "trend",
            "subjectId": "recent_10",
            "factsUsed": [
                {
                    "label": "top_issues",
                    "source": "issues",
                    "value": [{"issue": "three_putt", "phase": "Putting", "count": 4, "sourceRefs": ["900002:7"]}],
                    "sourceRefs": ["900002:7"],
                },
                {
                    "label": "decision_audit_trends",
                    "source": "diagnosis.decisionAuditTrends",
                    "value": {
                        "totalAudits": 2,
                        "recentCostDrivers": [
                            {"classification": "execution", "estimatedStrokesLost": 1.8, "sourceRefs": ["900002:7"]}
                        ],
                    },
                    "sourceRefs": ["900002:7"],
                },
            ],
            "missingData": [],
        }

        report = generate_report(
            facts,
            StaticProvider("The main cause is poor strategy, so aim away from every flag."),
        )

        categories = {row["category"] for row in report["unsupportedClaims"]}
        self.assertIn("strategy_advice", categories)
        self.assertIn("causal_claim", categories)
        self.assertEqual(report["factBinding"]["state"], "needs_review")

    def test_report_source_refs_include_inference_missing_data_refs(self) -> None:
        refs = report_source_refs(
            {
                "inferencesMade": [
                    {
                        "claim": "Weather is missing for one source.",
                        "sourceRefs": ["round-1"],
                        "missingDataRefs": ["round-2"],
                    }
                ]
            }
        )

        self.assertEqual(refs, ["round-1", "round-2"])

    def test_round_report_facts_bind_requested_scorecard_holes_shots_and_issues(self) -> None:
        data = fixture_history_data()
        stats = build_history_stats(data, data_mode="fixture")

        facts = build_round_report_facts(stats, "900001", history_data=data)

        by_label = {row["label"]: row for row in facts["factsUsed"]}
        self.assertEqual(by_label["round_scorecard"]["value"]["roundRef"], "900001")
        self.assertEqual(by_label["round_scorecard"]["value"]["course"], "Black Knight B/C")
        self.assertEqual(by_label["round_scorecard"]["value"]["score"], 77)
        self.assertEqual(by_label["round_scorecard"]["value"]["toPar"], 5)
        self.assertEqual(by_label["round_hole_outcomes"]["value"][0]["holeRef"], "900001:1")
        self.assertEqual(by_label["round_hole_outcomes"]["value"][0]["toPar"], 0)
        self.assertEqual(by_label["round_shots"]["value"][0]["shotRef"], "900001:1:0")
        self.assertEqual(by_label["round_shots"]["value"][0]["club"], "1D")
        self.assertIn("round_issues", by_label)
        self.assertNotIn({"label": "round_reference", "reason": "900001 not present in drillDown.roundIds"}, facts["missingData"])

    def test_round_report_facts_expose_normalized_provenance_source_refs(self) -> None:
        data = HistoryData(
            raw_rounds=[],
            rounds=[
                {
                    "id": "910001",
                    "ids": ["910001"],
                    "date": "2026-05-25T08:00:00",
                    "course": "Evidence Links",
                    "courseKey": "c_evidence",
                    "holesCompleted": 1,
                    "strokes": 4,
                    "par": 4,
                    "putts": 2,
                    "hasShots": True,
                    "shotStatus": "ready",
                    "holes": [{"number": 1, "strokes": 4, "par": 4, "putts": 2}],
                    "provenance": {
                        "sourceConnector": "garmin_cn_web_session",
                        "snapshotId": "snap_report",
                        "sourceRecordType": "scorecard",
                        "sourceRecordId": "910001",
                        "sourceRecordIds": ["910001"],
                        "sourceFiles": ["data/scorecards/910001.json"],
                        "sourceRefs": ["garmin_cn_web_session:snap_report:scorecard:910001"],
                        "confidence": "high",
                        "status": "normalized",
                    },
                }
            ],
            shots=[
                {
                    "id": "shot-report-1",
                    "roundId": "910001",
                    "scorecardId": "910001",
                    "hole": 1,
                    "club": "8I",
                    "distance": 142,
                    "surface": "green",
                    "provenance": {
                        "sourceConnector": "garmin_cn_web_session",
                        "snapshotId": "snap_report",
                        "sourceRecordType": "shot",
                        "sourceRecordId": "shot-report-1",
                        "parentRecordId": "910001",
                        "sourceRecordIds": ["shot-report-1"],
                        "sourceFiles": ["data/shots/910001.json"],
                        "sourceRefs": ["garmin_cn_web_session:snap_report:shot:910001:shot-report-1"],
                        "confidence": "high",
                        "status": "normalized",
                    },
                }
            ],
        )

        facts = build_round_report_facts(
            {
                "schema": "ai-caddie-history-stats-v1",
                "summary": {"totalRounds": 1, "average18": None, "bestScore": None},
                "scoring": {},
                "dataQuality": [],
                "drillDown": {"roundIds": ["910001"]},
            },
            "910001",
            history_data=data,
        )

        by_label = {row["label"]: row for row in facts["factsUsed"]}
        self.assertEqual(
            by_label["round_scorecard"]["sourceRefs"],
            ["garmin_cn_web_session:snap_report:scorecard:910001"],
        )
        self.assertEqual(by_label["round_scorecard"]["provenance"]["snapshotId"], "snap_report")
        self.assertEqual(by_label["round_scorecard"]["provenance"]["sourceFiles"], ["data/scorecards/910001.json"])
        self.assertEqual(
            by_label["round_shots"]["sourceRefs"],
            ["garmin_cn_web_session:snap_report:shot:910001:shot-report-1"],
        )
        self.assertEqual(
            by_label["round_shots"]["value"][0]["sourceRefs"],
            ["garmin_cn_web_session:snap_report:shot:910001:shot-report-1"],
        )

    def test_round_report_facts_include_scorecard_id_shot_rows(self) -> None:
        data = HistoryData(
            raw_rounds=[{"id": "700001", "hasShots": True}],
            rounds=[
                {
                    "id": "700001",
                    "ids": ["700001"],
                    "course": "Raw Shape Links",
                    "courseKey": "raw_shape_links",
                    "holesCompleted": 1,
                    "strokes": 4,
                    "par": 4,
                    "holes": [{"number": 1, "strokes": 4, "par": 4, "putts": 2}],
                }
            ],
            shots=[
                {
                    "scorecardId": 700001,
                    "hole": 1,
                    "clubName": "8I",
                    "meters": 141.8,
                    "endLie": "green",
                }
            ],
        )

        facts = build_round_report_facts(
            {
                "schema": "ai-caddie-history-stats-v1",
                "summary": {"totalRounds": 1, "average18": None, "bestScore": None},
                "scoring": {},
                "dataQuality": [],
                "drillDown": {"roundIds": ["700001"]},
            },
            "700001",
            history_data=data,
        )

        by_label = {row["label"]: row for row in facts["factsUsed"]}
        self.assertIn("round_shots", by_label)
        self.assertEqual(
            by_label["round_shots"]["value"],
            [{"shotRef": "700001:1:0", "hole": 1, "club": "8I", "distance": 141.8, "surface": "green"}],
        )

    def test_trend_report_facts_bind_period_trends_issues_and_drilldown_refs(self) -> None:
        facts = build_trend_report_facts(
            {
                "schema": "ai-caddie-history-stats-v1",
                "summary": {"totalRounds": 3, "average18": 86.0, "recent10Average": 86.0, "bestScore": 77},
                "time": {
                    "byYear": [{"key": "2026", "year": "2026", "roundCount": 3, "average18": 86.0, "roundIds": ["900001"]}],
                    "byQuarter": [{"key": "2026-Q2", "roundCount": 2, "average18": 86.0, "roundIds": ["900001", "900002"]}],
                    "byMonth": [{"key": "2026-05", "roundCount": 1, "average18": 77.0, "roundIds": ["900001"]}],
                },
                "scoring": {
                    "scoreBands": [{"label": "70s", "count": 1, "roundIds": ["900001"]}],
                    "phaseStats": [{"phase": "Tee", "fairwaysRecorded": 45, "fairwaysHit": 28, "holeRefs": ["900001:1"]}],
                },
                "courseDistribution": [{"courseKey": "black_knight", "roundCount": 2, "roundRefs": ["900001", "900002"]}],
                "issues": [{"issue": "approach_short", "count": 2, "sourceRefs": ["900001:7"]}],
                "records": {
                    "best18": {"score": 77, "roundRef": "900001"},
                    "mostPlayedCourse": {"courseKey": "black_knight", "roundCount": 2},
                },
                "dataQuality": [{"label": "weather", "state": "partial", "ready": 1, "total": 45}],
                "drillDown": {"roundRefs": ["900001", "900002", "900003"], "holeRefs": ["900001:1"], "shotRefs": ["900001:1:0"]},
            },
            "quarter:2026-Q2",
        )

        self.assertEqual(facts["schema"], "ai-caddie-report-facts-v1")
        self.assertEqual(facts["kind"], "trend")
        self.assertEqual(facts["subjectId"], "quarter:2026-Q2")
        labels = {row["label"] for row in facts["factsUsed"]}
        self.assertIn("summary_trend", labels)
        self.assertIn("time_period", labels)
        self.assertIn("phase_Tee", labels)
        self.assertIn("top_issues", labels)
        self.assertIn("record_book", labels)
        self.assertIn("drilldown_refs", labels)
        self.assertEqual(facts["missingData"][0]["label"], "weather")

    def test_report_facts_include_decision_audit_diagnosis(self) -> None:
        stats = {
            "schema": "ai-caddie-history-stats-v1",
            "summary": {"totalRounds": 3, "average18": 86.0, "recent10Average": 86.0, "bestScore": 77},
            "time": {"byYear": [{"key": "2026", "year": "2026", "roundCount": 3, "roundRefs": ["900001"]}]},
            "scoring": {},
            "issues": [],
            "dataQuality": [],
            "drillDown": {"roundIds": ["900001", "900002"]},
            "diagnosis": {
                "decisionAuditTrends": {
                    "totalAudits": 2,
                    "auditedRoundRefs": ["900001", "900002"],
                    "classificationCounts": [
                        {
                            "classification": "execution",
                            "count": 1,
                            "pct": 50.0,
                            "sourceRefs": ["900001:7"],
                            "decisionIds": ["900001:7:tee"],
                            "actualShotRefs": ["900001:7:1"],
                        },
                        {
                            "classification": "strategy",
                            "count": 1,
                            "pct": 50.0,
                            "sourceRefs": ["900002:7"],
                            "decisionIds": ["900002:7:tee"],
                            "actualShotRefs": ["900002:7:1"],
                        },
                    ],
                    "recentCostDrivers": [
                        {
                            "classification": "execution",
                            "phase": "tee_shot",
                            "recentCount": 1,
                            "deltaCount": 1,
                            "estimatedStrokesLost": 0.9,
                            "sourceRefs": ["900001:7"],
                            "recentRefs": ["900001:7"],
                            "decisionIds": ["900001:7:tee"],
                            "actualShotRefs": ["900001:7:1"],
                        }
                    ],
                }
            },
        }

        round_facts = build_round_report_facts(stats, "900001")
        trend_facts = build_trend_report_facts(stats, "year:2026")

        round_by_label = {row["label"]: row for row in round_facts["factsUsed"]}
        self.assertEqual(round_by_label["round_decision_audits"]["sourceRefs"], ["900001:7", "900001:7:1"])
        self.assertEqual(round_by_label["round_decision_audits"]["value"][0]["classification"], "execution")
        self.assertEqual(round_by_label["round_decision_audits"]["value"][0]["decisionIds"], ["900001:7:tee"])

        trend_by_label = {row["label"]: row for row in trend_facts["factsUsed"]}
        self.assertEqual(trend_by_label["decision_audit_trends"]["value"]["totalAudits"], 2)
        self.assertEqual(trend_by_label["decision_audit_trends"]["sourceRefs"], ["900001", "900002", "900001:7", "900002:7", "900001:7:1", "900002:7:1"])
        self.assertEqual(trend_by_label["decision_audit_trends"]["value"]["recentCostDrivers"][0]["classification"], "execution")

    def test_report_facts_preserve_stat_source_refs_coverage_and_confidence(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")
        stats["dataQuality"].append(
            {
                "label": "weather",
                "state": "partial",
                "ready": 1,
                "total": 45,
                "refs": ["900001:7"],
                "sourceRefs": ["900001:7"],
                "coverage": {"ready": 1, "total": 45, "pct": 2.2},
                "confidence": "low",
            }
        )

        facts = build_trend_report_facts(stats, "year:2026")

        by_label = {row["label"]: row for row in facts["factsUsed"]}
        self.assertEqual(by_label["summary_trend"]["sourceRefs"], ["900001", "900002", "900003"])
        self.assertEqual(by_label["summary_trend"]["coverage"], {"ready": 3, "total": 3, "pct": 100.0})
        self.assertEqual(by_label["summary_trend"]["confidence"], "medium")
        self.assertEqual(by_label["time_period"]["sourceRefs"], ["900001", "900002", "900003"])
        self.assertEqual(by_label["score_distribution"]["sourceRefs"], ["900001", "900002"])
        self.assertEqual(by_label["phase_Putting"]["coverage"], {"ready": 45, "total": 45, "pct": 100.0})

        weather_missing = next(row for row in facts["missingData"] if row["label"] == "weather" and row.get("sourceRefs") == ["900001:7"])
        self.assertEqual(weather_missing["sourceRefs"], ["900001:7"])
        self.assertEqual(weather_missing["coverage"], {"ready": 1, "total": 45, "pct": 2.2})
        self.assertEqual(weather_missing["confidence"], "low")

    def test_trend_report_facts_expose_missing_period(self) -> None:
        facts = build_trend_report_facts(
            {
                "schema": "ai-caddie-history-stats-v1",
                "summary": {"totalRounds": 1},
                "time": {"byYear": [{"key": "2026", "roundCount": 1}]},
                "scoring": {},
                "issues": [],
                "dataQuality": [],
                "drillDown": {"roundRefs": ["900001"]},
            },
            "year:2025",
        )

        self.assertIn({"label": "period", "reason": "year:2025 not present in history time aggregates"}, facts["missingData"])

    def test_prompt_excludes_cookie_csrf_token_secret_and_private_paths(self) -> None:
        facts = {
            "schema": "ai-caddie-report-facts-v1",
            "kind": "round",
            "subjectId": "900001",
            "factsUsed": [
                {
                    "label": "raw",
                    "value": "cookie=session-value connect-csrf-token=csrf-secret token=abc123 /home/ubuntu/private/file",
                    "source": "test",
                }
            ],
            "missingData": [],
        }
        provider = RecordingProvider()

        generate_report(facts, provider)

        prompt = "\n".join(message.content for message in provider.messages)
        self.assertNotIn("session-value", prompt)
        self.assertNotIn("csrf-secret", prompt)
        self.assertNotIn("abc123", prompt)
        self.assertNotIn("/home/ubuntu/private/file", prompt)
        self.assertIn("[REDACTED]", prompt)

    def test_generated_report_exposes_subject_and_deduped_source_refs(self) -> None:
        facts = {
            "schema": "ai-caddie-report-facts-v1",
            "kind": "trend",
            "subjectId": "recent_10",
            "factsUsed": [
                {"label": "summary", "source": "summary", "value": 1, "sourceRefs": ["900001", "900002"]},
                {"label": "hole", "source": "holes", "value": {"holeRef": "900001:7", "sourceRefs": ["900001", "900001:7"]}},
            ],
            "missingData": [{"label": "weather", "sourceRefs": ["900002"]}],
        }
        report = generate_report(facts, StaticProvider("identity review"))

        self.assertEqual(report["subjectId"], "recent_10")
        self.assertEqual(report["sourceRefs"], ["900001", "900002", "900001:7"])
        self.assertEqual(report["narrative"], "identity review")

    def test_redact_private_text_is_public_helper(self) -> None:
        redacted = redact_private_text("api_key=my-key /Users/me/Library/token")

        self.assertNotIn("my-key", redacted)
        self.assertNotIn("/Users/me/Library/token", redacted)

    def test_report_store_round_trips_secret_free_jsonl(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = store_report(
                {
                    "schema": "ai-caddie-review-report-v1",
                    "kind": "round",
                    "provider": "StaticProvider",
                    "model": "static",
                    "factsUsed": [{"label": "round", "value": "token=abc123", "source": "test"}],
                    "missingData": [],
                    "narrative": "stored review",
                    "confidence": "high",
                },
                kind="round",
                subject_id="900001",
                root=root,
            )
            loaded = latest_report_record("round", "900001", root=root)
            records = list_report_records(root=root)
            raw = (root / "data" / "reports" / "reports.jsonl").read_text(encoding="utf-8")

        self.assertEqual(record["kind"], "round")
        self.assertEqual(record["subjectId"], "900001")
        self.assertTrue(record["storedAt"].endswith("Z"))
        self.assertEqual(loaded["report"]["narrative"], "stored review")
        self.assertEqual(len(records), 1)
        self.assertNotIn("abc123", raw)


if __name__ == "__main__":
    unittest.main()
