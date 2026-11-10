"""AI round reports keep facts, inferences and missing data apart, and never take stats down (test-plan S-18).

The language model is replaced by in-process fake providers at the server's provider factory; no
network is reachable. History is the shared fixture: round 900001 (18 holes, 77, with shots),
round 900002 (18 holes, 95) and round 900003 (9 holes, no shots).
"""
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.core.config import get_settings
from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.history import stats_cache
from server_v2 import annotations, course_install, history_overview, history_stats
from server_v2 import main as server_main
from server_v2 import reports as report_routes

SECRET = "abc123"
# Live-round leases are cleared so a report request cannot see or leave one behind.
ACTIVE_ROUND_STATE = (
    (server_main, ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_START_TIMES",
                   "_ROUND_START_CACHE", "_ACTIVE_EVENT_DEVICES", "_ACTIVE_SELECTIONS")),
    (course_install, ("_CURRENT_COURSE_IDS",)),
)


class RecordingProvider:
    """Stands in for the language model and remembers the prompt it was given."""

    model = "recording-model"

    def __init__(self, reply):
        self.reply = reply
        self.messages = []

    def chat(self, messages, max_tokens=None):
        self.messages = list(messages)
        return self.reply


class FailingProvider:
    model = "failing-model"

    def chat(self, messages, max_tokens=None):
        raise RuntimeError(f"provider down token={SECRET} /srv/private/key.txt")


class ReportRouteCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        loader = mock.Mock(side_effect=lambda *a, **kw: (fixture_history_data(), "fixture"))
        patches = [
            mock.patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture", "AI_CADDIE_ADMIN_TOKEN": "",
                                         "AI_CADDIE_SECURITY_PROFILE": ""}),
            mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network is off in this test")),
            # Reports and stats share one ledger, so stats reads whatever the report route just stored.
            mock.patch.object(report_routes, "REPORT_ROOT", root),
            mock.patch.object(report_routes, "MEDIA_ROOT", root),
            mock.patch.object(annotations, "ANNOTATION_ROOT", root),
            *(mock.patch.object(history_stats, name, root)
              for name in ("REPORTS_ROOT", "ANNOTATION_ROOT", "WEATHER_ROOT", "DECISION_AUDIT_ROOT")),
            *(mock.patch.object(module, "load_history_data_for_mode", loader)
              for module in (report_routes, history_stats, history_overview, annotations, server_main)),
            mock.patch.object(server_main, "_ACTIVE_PACKAGED_ROUNDS", set()),
            *(mock.patch.dict(getattr(module, name), clear=True)
              for module, names in ACTIVE_ROUND_STATE for name in names),
        ]
        for target in patches:
            target.start()
            self.addCleanup(target.stop)
        for clear in (get_settings.cache_clear, stats_cache.clear):
            clear()
            self.addCleanup(clear)
        self.client = TestClient(server_main.app)
        self.addCleanup(self.client.close)

    def generate(self, round_id, **provider):
        with mock.patch.object(report_routes, "build_text_provider", **provider):
            response = self.client.post(f"/api/v2/reports/round/{round_id}/generate")
        self.assertEqual(response.status_code, 200, response.text[:500])
        return response


def labels(rows):
    return {row["label"] for row in rows}


class Reports(ReportRouteCase):
    def test_provider_failure_keeps_results(self):
        """S-18 [main]: when the AI provider fails, the report falls back to plain facts and stats and home keep working."""
        failures = (
            ("chat_raises", {"return_value": FailingProvider()}),
            ("factory_raises", {"side_effect": RuntimeError(f"no provider token={SECRET} /srv/private/k.txt")}),
        )
        for label, provider in failures:
            with self.subTest(failure=label):
                response = self.generate("900001", **provider)
                report = response.json()
                self.assertEqual((report["provider"], report["model"], report["confidence"]),
                                 ("DeterministicReportProvider", "deterministic-facts-v1", "low"))
                failure = next(row for row in report["missingData"] if row["label"] == "report_provider")
                self.assertEqual(failure["state"], "missing")
                self.assertNotIn(SECRET, response.text)        # the provider error is redacted
                self.assertNotIn("/srv/private", response.text)
                self.assertIn("round_scorecard", labels(report["factsUsed"]))  # facts survive the outage
                self.assertTrue(report["narrative"])

                stored = self.client.get("/api/v2/reports/round/900001").json()
                self.assertEqual(stored["provider"], "DeterministicReportProvider")
                stats = self.client.get("/api/v2/history/stats")
                overview = self.client.get("/api/v2/history/overview")
                self.assertEqual((stats.status_code, overview.status_code), (200, 200))
                # Fixture: 3 rounds; the two 18-hole rounds score 77 and 95, so the 18-hole average is 86.0.
                self.assertEqual((stats.json()["summary"]["totalRounds"], stats.json()["summary"]["average18"]),
                                 (3, 86.0))
                self.assertEqual((overview.json()["metrics"]["totalRounds"], overview.json()["metrics"]["average18"]),
                                 (3, 86.0))

    def test_report_separates_facts_inferences_and_missing_data(self):
        """S-18: a generated report lists the facts it used, inferences citing those facts, and what data is missing."""
        provider = RecordingProvider("Bogey on hole 5, otherwise steady.")
        report = self.generate("900001", return_value=provider).json()
        facts = labels(report["factsUsed"])
        self.assertTrue({"round_scorecard", "round_hole_outcomes", "round_shots"} <= facts)
        self.assertTrue(all(row["source"] for row in report["factsUsed"]))  # every fact names its source
        scorecard = next(row for row in report["factsUsed"] if row["label"] == "round_scorecard")
        self.assertEqual((scorecard["value"]["roundRef"], scorecard["value"]["date"]), ("900001", "2026-05-18"))

        self.assertTrue(report["inferencesMade"])
        for inference in report["inferencesMade"]:
            with self.subTest(claim=inference["claim"]):
                self.assertTrue(inference["sourceRefs"])              # an inference cites evidence
                self.assertTrue(set(inference["factLabels"]) <= facts)  # ...that is in the fact list

        missing = labels(report["missingData"])
        self.assertTrue({"weather", "rating_slope"} <= missing)  # the fixture has neither
        self.assertFalse(missing & facts)  # nothing is both a fact and missing

        self.assertEqual((report["provider"], report["model"]), ("RecordingProvider", "recording-model"))
        self.assertEqual(report["narrative"], "Bogey on hole 5, otherwise steady.")
        self.assertEqual(report["factBinding"], {"state": "bound", "unsupportedClaimCount": 0})
        prompt = provider.messages[-1].content
        self.assertIn("900001", prompt)          # the model is fed the structured facts
        self.assertIn("round_scorecard", prompt)

    def test_unsupported_narrative_claim_is_flagged(self):
        """S-18: a model sentence with no supporting fact is listed as unsupported and lowers confidence."""
        report = self.generate("900001", return_value=RecordingProvider("Wind was strong all day.")).json()
        self.assertEqual(report["factBinding"], {"state": "needs_review", "unsupportedClaimCount": 1})
        self.assertEqual(report["confidence"], "low")
        claim = report["unsupportedClaims"][0]
        # The fixture has no weather facts, so the wind sentence cannot be bound to anything.
        self.assertEqual((claim["category"], claim["claim"], claim["sourceRefs"]),
                         ("weather", "Wind was strong all day.", []))

    def test_round_classes_report_what_is_missing(self):
        """S-18: a nine without shots and an unknown round say which data is missing instead of inventing it."""
        rows = [
            # round, facts that must be present, facts that must be absent, missing labels that must appear
            ("900001", {"round_scorecard", "round_shots"}, set(), {"weather"}),
            ("900003", {"round_scorecard"}, {"round_shots"}, {"shots"}),  # 9 holes, no shots recorded
            ("does-not-exist", set(), {"round_scorecard", "round_shots"}, {"round_reference", "round_scorecard"}),
        ]
        for round_id, present, absent, missing in rows:
            with self.subTest(round=round_id):
                report = self.generate(round_id, return_value=RecordingProvider("Steady round.")).json()
                facts = labels(report["factsUsed"])
                self.assertTrue(present <= facts, facts)
                self.assertFalse(absent & facts, facts)
                self.assertTrue(missing <= labels(report["missingData"]))
