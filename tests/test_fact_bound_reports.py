from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.llm_providers import LLMMessage
from ai_caddie.reports import (
    build_round_report_facts,
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
                "dataQuality": [
                    {"label": "shots", "state": "partial", "ready": 2, "total": 3},
                    {"label": "weather", "state": "partial", "ready": 1, "total": 45},
                ],
                "drillDown": {"roundIds": ["900001"]},
            },
            "900001",
        )
        provider = RecordingProvider()

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
        self.assertIn(report["confidence"], {"low", "medium", "high"})

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
