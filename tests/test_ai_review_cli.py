from __future__ import annotations

import unittest

import ai_review
from ai_caddie.fixtures import fixture_history_data
from ai_caddie.llm_providers import LLMMessage


class RecordingProvider:
    model = "recording-model"

    def __init__(self) -> None:
        self.messages: list[LLMMessage] = []

    def chat(self, messages, max_tokens=None):  # type: ignore[no-untyped-def]
        self.messages = list(messages)
        return "事实复盘"


class AiReviewCliTests(unittest.TestCase):
    def test_legacy_ai_review_uses_fact_bound_report_prompt(self) -> None:
        provider = RecordingProvider()

        report = ai_review.build_fact_bound_round_report(
            "900001",
            history_data=fixture_history_data(),
            provider=provider,
            data_mode="fixture",
        )

        self.assertEqual(report["schema"], "ai-caddie-review-report-v1")
        self.assertEqual(report["kind"], "round")
        self.assertEqual(report["subjectId"], "900001")
        self.assertEqual(report["narrative"], "事实复盘")
        self.assertIn("factsUsed", report)
        self.assertTrue(report["sourceRefs"])
        prompt = provider.messages[-1].content
        self.assertIn('"factsUsed"', prompt)
        self.assertIn("Do not invent weather, lie, intent, club, penalties, or private data.", prompt)
        self.assertNotIn("可能的根因猜测", prompt)
        self.assertNotIn("下一场该试", prompt)

    def test_legacy_ai_review_markdown_keeps_fact_binding_visible(self) -> None:
        report = ai_review.build_fact_bound_round_report(
            "900001",
            history_data=fixture_history_data(),
            provider=RecordingProvider(),
            data_mode="fixture",
        )

        rendered = ai_review.render_report_markdown(report)

        self.assertIn("Fact binding:", rendered)
        self.assertIn("Source refs:", rendered)
        self.assertIn("## Missing data", rendered)
        self.assertIn("## Facts used", rendered)
        self.assertIn('"factsUsed"', rendered)
        self.assertNotIn("Source brief", rendered)


if __name__ == "__main__":
    unittest.main()
