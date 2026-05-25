from __future__ import annotations

import unittest

from ai_caddie.llm_providers import LLMMessage
from ai_caddie.reports import build_round_report_facts, generate_report, redact_private_text


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
                "scoring": {"scoreBands": [{"label": "70s", "count": 1, "roundIds": ["900001"]}]},
                "dataQuality": [{"label": "shots", "state": "partial", "ready": 2, "total": 3}],
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


if __name__ == "__main__":
    unittest.main()
