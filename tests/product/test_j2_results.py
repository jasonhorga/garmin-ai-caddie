"""J2 results/review product checks (U/I).

The fixture is deliberately small enough to audit by hand.  Its ``hand_calculations`` and
``expected`` sections are the oracle; no expected number below is obtained by calling the code
under test first.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_caddie.history.history import HistoryData
from ai_caddie.history.history_drilldown import resolve_history_ref
from ai_caddie.history.history_round_detail import build_history_round_detail
from ai_caddie.history.history_stats import (
    _handicap_estimate,
    build_history_stats,
    windowed_history_data,
)
from ai_caddie.history.mobile_stats import build_mobile_previous, build_mobile_stats
from server_v2.history_rounds import build_history_rounds_response
from ai_caddie.reports.reports import generate_deterministic_report, generate_report


FIXTURE = Path(__file__).parent / "fixtures" / "c16b" / "results.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class J2ResultsProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _load_fixture()
        rows = cls.fixture["rounds"]
        cls.data = HistoryData(raw_rounds=rows, rounds=rows, shots=cls.fixture["shots"])
        cls.tmp = tempfile.TemporaryDirectory(prefix="j2-results-")
        root = Path(cls.tmp.name)
        (root / "data" / "annotations").mkdir(parents=True)
        annotation_file = root / "data" / "annotations" / "annotations.jsonl"
        annotation_file.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in cls.fixture["annotations"]) + "\n",
            encoding="utf-8",
        )
        cls.stats = build_history_stats(
            cls.data,
            data_mode="fixture",
            annotations_root=root,
            weather_root=root,
            reports_root=root,
            decision_audit_root=root,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_21_home_windows_use_handwritten_sample_and_handicap_oracle(self) -> None:
        expected = self.fixture["expected"]
        summary = self.stats["summary"]
        self.assertEqual(summary["totalRounds"], expected["summary"]["totalRounds"])
        self.assertEqual(summary["eighteenHoleRounds"], expected["summary"]["eighteenHoleRounds"])
        self.assertEqual(summary["nineHoleRounds"], expected["summary"]["nineHoleRounds"])
        self.assertEqual(summary["mergedRounds"], expected["summary"]["mergedRounds"])
        self.assertEqual(summary["courseCount"], expected["summary"]["courseCount"])
        self.assertEqual(summary["handicapEstimate"], expected["summary"]["handicapEstimate"])
        self.assertEqual(summary["handicapChangeRecent20"], expected["summary"]["handicapChangeRecent20"])
        self.assertEqual(_handicap_estimate(self.data.rounds), expected["summary"]["handicapEstimate"])
        # The implementation preserves source order inside a selected window; the fixture records
        # the same selected set in newest-first UI order.
        for window in ("last10", "last20"):
            actual = [str(r.get("id")) for r in windowed_history_data(self.data, window).rounds]
            self.assertEqual(set(actual), set(expected["windows"][window]))
            self.assertEqual(len(actual), len(expected["windows"][window]))

        mobile = build_mobile_stats(build_history_stats(windowed_history_data(self.data, "last20"), data_mode="fixture"))
        self.assertEqual(mobile["summary"]["totalRounds"], 20)
        self.assertLessEqual(len(mobile["scoring"]["roundSequences"]), 20)
        self.assertEqual([row["roundId"] for row in mobile["scoring"]["roundSequences"]], expected["windows"]["last20"])

    def test_22_range_and_previous_period_never_invent_a_comparison(self) -> None:
        last10 = windowed_history_data(self.data, "last10")
        previous10 = windowed_history_data(self.data, "prev10")
        self.assertEqual(set(str(r.get("id")) for r in previous10.rounds), set(self.fixture["expected"]["windows"]["previous10"]))
        previous_stats = build_history_stats(previous10, data_mode="fixture")
        previous = build_mobile_previous(previous_stats, "prev10")
        self.assertEqual(previous["roundCount"], 10)
        self.assertEqual(previous["requiredRounds"], 10)
        self.assertIn("scoring", previous)
        self.assertIsNone(build_mobile_previous({"summary": {"totalRounds": 0}}, "prev20"))

        # A five-round previous window is explicitly a short sample, not a false delta.
        short = {"summary": {"totalRounds": 5}, "scoring": {"putting": {"averagePutts": 2.0}}}
        short_previous = build_mobile_previous(short, "prev10")
        self.assertEqual(short_previous, {"window": "prev10", "roundCount": 5, "requiredRounds": 10})
        self.assertEqual(len(last10.rounds), 10)

    def test_23_every_drilldown_ref_is_the_handwritten_round_set(self) -> None:
        expected = self.fixture["expected"]["drilldown_round_ids"]
        self.assertEqual(self.stats["drillDown"]["roundIds"], expected)
        sections = self.fixture["expected"]["drilldown_sections"]
        for name in ("byYear", "byQuarter", "byMonth"):
            actual = {row["key"]: row["roundIds"] for row in self.stats["time"][name]}
            self.assertEqual(actual, sections[name])
        self.assertEqual(
            {row["courseKey"]: row["roundIds"] for row in self.stats["courses"]},
            sections["courses"],
        )
        self.assertEqual(
            {row["club"]: row["roundIds"] for row in self.stats["clubs"]},
            sections["clubs"],
        )
        self.assertEqual(
            {row["label"]: row["roundIds"] for row in self.stats["scoring"]["scoreBands"]},
            sections["scoreBands"],
        )
        resolved = resolve_history_ref(self.data, "r01:1")
        self.assertTrue(resolved["found"])
        self.assertEqual(resolved["round"]["id"], "r01")
        self.assertEqual(resolved["hole"]["number"], 1)

    def test_24_all_rounds_search_filters_and_month_groups(self) -> None:
        response = build_history_rounds_response(self.data, year="2025", course="mega", search="Mega", limit=120)
        ids = [card.id for group in response.groups for card in group.rounds]
        self.assertEqual(ids, ["r06", "r05", "r04", "r03", "r02", "r01"])
        self.assertEqual(response.total, 6)
        no_shots = build_history_rounds_response(self.data, has_shots=False)
        no_shot_ids = {card.id for group in no_shots.groups for card in group.rounds}
        self.assertIn("r04", no_shot_ids)
        self.assertNotIn("r01", no_shot_ids)
        quarter = build_history_rounds_response(self.data, period="2025-Q1")
        quarter_ids = [card.id for group in quarter.groups for card in group.rounds]
        self.assertEqual(quarter_ids, ["r07", "r06", "r05", "r04", "r03", "r02", "r01"])
        self.assertEqual(sum(group.count for group in response.groups), 6)

    def test_25_statistics_keep_unknowns_out_of_denominators_and_apply_correction(self) -> None:
        scoring = self.stats["scoring"]
        putting = scoring["putting"]
        self.assertNotIn("r01:18", putting["holeRefs"])  # default 2-putt is not evidence
        self.assertNotIn("r02:5", putting["holeRefs"])  # missing putt remains unknown
        self.assertIn("r03:1", putting["holeRefs"])  # correction re-enters the denominator
        self.assertEqual(putting["correctedRefs"], ["r03:1"])
        self.assertEqual(
            putting["zeroPutts"] + putting["onePutts"] + putting["twoPutts"] + putting["threePlusPutts"],
            putting["holesWithPutts"],
        )
        self.assertAlmostEqual(putting["zeroPuttPct"] + putting["onePuttPct"] + putting["twoPuttPct"] + putting["threePlusPuttPct"], 100.0, places=1)
        expected = self.fixture["expected"]["scoring"]
        for key, value in expected["putting"].items():
            self.assertEqual(putting[key], value)
        self.assertEqual(scoring["penalties"], self.fixture["expected"]["penalties"])
        self.assertEqual(scoring["scrambling"], expected["scrambling"])
        self.assertEqual(scoring["byPar"][0]["parOrBetter"], expected["byParPar3"]["parOrBetter"])
        self.assertEqual(scoring["byPar"][0]["parOrBetterPct"], expected["byParPar3"]["parOrBetterPct"])
        outcomes = scoring["outcomes"]
        self.assertEqual({key: outcomes[key] for key in expected["outcomes"]}, expected["outcomes"])
        self.assertEqual(outcomes["parOrBetter"], outcomes["eagleOrBetter"] + outcomes["birdie"] + outcomes["par"])
        self.assertEqual(outcomes["bogeyOrWorse"], outcomes["bogey"] + outcomes["doubleOrWorse"])
        self.assertEqual(sum(outcomes[key] for key in ("eagleOrBetter", "birdie", "par", "bogey", "doubleOrWorse")), expected["outcomesTotal"])
        self.assertEqual([row["coverage"]["ready"] for row in scoring["phaseStats"][:2]], expected["phaseReady"])
        self.assertEqual([row["coverage"]["total"] for row in scoring["phaseStats"][:2]], expected["phaseTotal"])

    def test_26_loops_are_physical_and_ordered(self) -> None:
        scoring = self.stats["scoring"]
        loop_keys = {row["loopKey"] for row in scoring["loops"]}
        self.assertIn("gid:2701:1-9", loop_keys)
        self.assertIn("gid:2702:1-9", loop_keys)
        self.assertIn("course:solo18:1-9", loop_keys)
        self.assertIn("course:solo18:10-18", loop_keys)
        expected = self.fixture["expected"]["scoring"]
        self.assertEqual(scoring["nineOnlyRounds"], expected["nineOnlyRounds"])
        combos = {(row["frontKey"], row["backKey"]): row["rounds"] for row in scoring["nineCombos"]}
        self.assertEqual(
            {f"{front}|{back}": rounds for (front, back), rounds in combos.items()},
            expected["nineCombos"],
        )
        self.assertTrue(all(row["samples"] >= expected["hardestHoleMinimumSamples"] for row in scoring["hardestHoles"]), scoring["hardestHoles"])

    def test_27_round_review_preserves_hole_numbers_and_missing_values(self) -> None:
        detail = build_history_round_detail(self.data, "r02")
        self.assertTrue(detail["found"])
        self.assertEqual(detail["roundRef"], "r02")
        self.assertEqual([cell["hole"] for cell in detail["scorecard"]], list(range(1, 19)))
        hole5 = detail["scorecard"][4]
        self.assertIsNone(hole5.get("putts"))
        self.assertNotEqual(hole5.get("putts"), 0)
        self.assertNotIn("OUT", json.dumps(detail, ensure_ascii=False))
        self.assertNotIn("IN", json.dumps(detail, ensure_ascii=False))
        missing = build_history_round_detail(self.data, "not-a-round")
        self.assertFalse(missing["found"])

    def test_28_club_ladder_cleans_names_unknowns_and_uses_handwritten_percentiles(self) -> None:
        profile = next(row for row in self.stats["clubs"] if row["club"] == "7 iron")
        expected = self.fixture["expected"]["club"]
        for key in ("sampleCount", "median", "p10", "p90"):
            self.assertEqual(profile[key], expected[key])
        self.assertEqual(profile["roundIds"], expected["roundIds"])
        self.assertEqual(len(self.stats["clubs"]), 1)
        self.assertEqual(profile["dispersionRange"], expected["dispersionRange"])

    def test_29_structured_report_keeps_facts_missing_and_resolvable_sources_separate(self) -> None:
        facts = {
            "schema": "ai-caddie-report-facts-v1",
            "kind": "round",
            "subjectId": "r01",
            "factsUsed": [{"label": "score", "value": 78, "sourceRefs": ["r01"]}],
            "missingData": [{"label": "putts", "state": "missing", "sourceRefs": ["r01:5"]}],
        }
        report = generate_deterministic_report(facts)
        self.assertEqual(report["factsUsed"], facts["factsUsed"])
        self.assertEqual(report["missingData"], facts["missingData"])
        self.assertEqual(set(report["sourceRefs"]), {"r01", "r01:5"})
        self.assertEqual(report["unsupportedClaims"], [])

    def test_210_model_receives_only_structured_facts(self) -> None:
        seen: list[str] = []

        class RecordingProvider:
            model = "fake-structured"

            def chat(self, messages, *, max_tokens):
                seen.append(messages[-1].content)
                return "只根据 factsUsed：该场成绩为 78 杆；推杆数据缺失。"

        facts = {"kind": "round", "factsUsed": [{"label": "score", "value": 78, "sourceRefs": ["r01"]}], "missingData": []}
        report = generate_report(facts, RecordingProvider())
        self.assertEqual(report["provider"], "RecordingProvider")
        self.assertIn("factsUsed", seen[0])
        self.assertNotIn("password", seen[0].lower())
        self.assertNotIn("cookie", seen[0].lower())

    def test_211_failed_supplier_falls_back_to_static_report(self) -> None:
        from server_v2 import reports as reports_api

        class FailingProvider:
            model = "fake-down"

            def chat(self, messages, *, max_tokens):
                raise RuntimeError("fake provider down")

        facts = {"kind": "round", "factsUsed": [{"label": "score", "value": 78, "sourceRefs": ["r01"]}], "missingData": []}
        with mock.patch.object(reports_api, "build_text_provider", return_value=FailingProvider()):
            with mock.patch.object(reports_api, "generate_report", side_effect=RuntimeError("fake provider down")):
                report = reports_api._generate_provider_report_or_fallback(facts)
        self.assertEqual(report["provider"], "DeterministicReportProvider")
        self.assertEqual(report["confidence"], "low")
        self.assertEqual(report["factsUsed"], facts["factsUsed"])
        self.assertEqual(report["missingData"][-1]["label"], "report_provider")
        self.assertEqual(report["missingData"][-1]["state"], "missing")


if __name__ == "__main__":
    unittest.main()
