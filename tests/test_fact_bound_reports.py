from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.fixtures import fixture_history_data
from ai_caddie.llm_providers import LLMMessage
from ai_caddie.history_stats import build_history_stats
from ai_caddie.reports import (
    build_round_report_facts,
    build_trend_report_facts,
    generate_report,
    latest_report_record,
    list_report_records,
    redact_private_text,
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
