"""C16b J2 成绩/复盘 product tests.

Every numeric oracle is written in ``fixtures/c16b/results.json`` before this module is run.
The fixture is seven deliberately small, physically legal rounds; no expected value calls a
production function. Comments beside each assertion name the arithmetic used by the oracle.
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
from ai_caddie.history.history_stats import build_history_stats, windowed_history_data
from ai_caddie.history.mobile_stats import build_mobile_previous, build_mobile_stats
from ai_caddie.reports.reports import generate_deterministic_report, generate_report
from ai_caddie.rounds.round_shot_map import build_round_hole_shot_map
from server_v2.history_round_detail import load_round_hole_shot_map_response
from server_v2.history_rounds import build_history_rounds_response
from server_v2 import history_stats as history_stats_api

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
        (root / "data" / "annotations" / "annotations.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in cls.fixture["annotations"]) + "\n", encoding="utf-8")
        cls.stats = build_history_stats(cls.data, data_mode="fixture", annotations_root=root, weather_root=root,
                                        reports_root=root, decision_audit_root=root)
    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_j2_1_home_windows_and_recent_score_oracle(self) -> None:
        expected = self.fixture["expected"]["summary"]
        summary = self.stats["summary"]
        for key in ("totalRounds", "eighteenHoleRounds", "nineHoleRounds", "mergedRounds", "courseCount"):
            with self.subTest(key=key): self.assertEqual(summary[key], expected[key])
        # Differentials [10,10,8,17,15]; ceil(5*.4)=2; ((8+10)/2)*.96=8.64 -> 8.6.
        self.assertEqual(summary["handicapEstimate"], 8.6)
        # Complete 18-hole scores 82+82+80+89+87=420; 420/5=84.0; best=min=80.
        self.assertEqual(summary["recent10Average"], 84.0)
        self.assertEqual(summary["bestScore"], 80)
        points = self.stats["trend"]["points"]
        self.assertEqual([p["roundId"] for p in points[-3:]], ["r3", "r5", "r6"])
        self.assertEqual(["+", "+", "+"], ["+" if p["toPar"] > 0 else "0" for p in points[-3:]])
        for window, ids in (("last10", ["r1","r2","r3","r4","r5","r6","None"]),
                            ("last20", ["r1","r2","r3","r4","r5","r6","None"])):
            actual = [str(r.get("id")) for r in windowed_history_data(self.data, window).rounds]
            self.assertEqual(set(actual), set(ids)); self.assertEqual(len(actual), len(ids))
        self.assertEqual(build_mobile_stats(self.stats)["summary"]["recent10Average"], 84.0)

    def test_j2_2_ranges_granularities_and_complete_previous_only(self) -> None:
        for window in ("last10", "last20", "12m", "all"):
            with self.subTest(window=window): self.assertEqual(len(windowed_history_data(self.data, window).rounds), 7)
        with self.assertRaises(ValueError): windowed_history_data(self.data, "last5")
        previous = build_mobile_previous(build_history_stats(windowed_history_data(self.data, "prev10"), data_mode="fixture"), "prev10")
        self.assertIsNone(previous)
        short_data = HistoryData(self.data.raw_rounds[:5], self.data.rounds[:5], self.data.shots)
        short_stats = build_history_stats(short_data, data_mode="fixture")
        self.assertEqual(build_mobile_previous(short_stats, "prev10"), {"window":"prev10","roundCount":5,"requiredRounds":10})
        year = self.stats["time"]["byYear"][0]
        self.assertEqual((year["roundCount"], year["eighteenHoleRounds"], year["nineHoleRounds"]), (7,5,2))
        self.assertEqual((year["average18"], year["bestScore"], year["worstScore"]), (84.0,80,89))
        # Six season/year card facts are all checked against hand arithmetic: count, mean,
        # best, worst, birdies/round and doubles+/round.
        self.assertEqual(year["outcomes"]["birdie"] / 5, 0)
        self.assertEqual(year["outcomes"]["doubleOrWorse"] / 5, 14 / 5)
        quarter = next(q for q in self.stats["time"]["byQuarter"] if q["key"] == "2025-Q1")
        self.assertEqual((quarter["roundCount"], quarter["average18"], quarter["bestScore"], quarter["worstScore"]), (5,83.2,80,89))
        self.assertEqual(quarter["outcomes"]["birdie"] / 4, 0)
        self.assertEqual(quarter["outcomes"]["doubleOrWorse"] / 4, 10 / 4)
        self.assertEqual(self.stats["time"]["playFrequency"], {"totalMonths":4,"roundsPerMonth":1.8,"mostActiveMonth":{"key":"2025-04","roundCount":2}})
        # Exercise the real mobile endpoint wiring: PREVIOUS_WINDOW has no ``all`` entry.
        # A mutant adding ``all`` must make this endpoint attach a previous block and fail.
        with mock.patch.object(history_stats_api, "load_history_data_for_mode", return_value=(self.data, "fixture")), \
             mock.patch.object(history_stats_api, "cached_build_history_stats", side_effect=lambda data, **kw: build_history_stats(windowed_history_data(data, kw["window"]), data_mode="fixture")):
            all_payload = history_stats_api.load_mobile_stats_response("all")
        self.assertIsNone(all_payload.previous)

    def test_j2_3_each_drilldown_segment_has_handwritten_round_ids(self) -> None:
        golden = self.fixture["expected"]["drilldown"]
        self.assertEqual(self.stats["drillDown"]["roundIds"], self.fixture["expected"]["drilldown_round_ids"])
        self.assertEqual({r["key"]: r["roundIds"] for r in self.stats["time"]["byYear"]}, golden["byYear"])
        self.assertEqual({r["key"]: r["roundIds"] for r in self.stats["time"]["byQuarter"]}, golden["byQuarter"])
        self.assertEqual({r["key"]: r["roundIds"] for r in self.stats["time"]["byMonth"]}, golden["byMonth"])
        self.assertEqual({self.stats["courses"][0]["courseKey"]: self.stats["courses"][0]["roundIds"]}, golden["courses"])
        score_bands = {row["label"]: row["roundIds"] for row in self.stats["time"]["byYear"][0]["scoreBands"]}
        self.assertEqual({"80s": score_bands["80s"]}, {"80s": golden["scoreBands"]["80s"]})
        self.assertEqual(resolve_history_ref(self.data, "r1:1")["round"]["id"], "r1")
        self.assertEqual(resolve_history_ref(self.data, "r1:1")["hole"]["number"], 1)

    def test_j2_4_round_search_filters_and_month_groups(self) -> None:
        march = build_history_rounds_response(self.data, search="2025-03", limit=20)
        self.assertEqual([c.id for g in march.groups for c in g.rounds], ["r5","r4"])
        self.assertEqual(build_history_rounds_response(self.data, course="pine").total, 7)
        no_shots = build_history_rounds_response(self.data, has_shots=False)
        self.assertEqual({c.id for g in no_shots.groups for c in g.rounds}, {"None","r6","r5","r4","r3"})
        self.assertEqual([g.label for g in build_history_rounds_response(self.data, period="2025-Q1").groups], ["March 2025","February 2025","January 2025"])

    def test_j2_5_statistics_are_honest_across_pars_and_phases(self) -> None:
        scoring = self.stats["scoring"]; putts = scoring["putting"]
        self.assertIn("r1:2", putts["correctedRefs"]); self.assertNotIn("r2:3", putts["holeRefs"])
        self.assertEqual(putts["holesWithPutts"], 107)  # 108 holes - default 1 - missing 1.
        self.assertEqual(putts["totalPutts"], 190)  # 36*1 + 59*2 + 12*3 = 190.
        self.assertEqual(sum(putts[k] for k in ("zeroPutts","onePutts","twoPutts","threePlusPutts")), 107)
        self.assertEqual(scoring["penalties"], self.fixture["expected"]["penalties"])
        self.assertEqual((scoring["scrambling"]["chances"], scoring["scrambling"]["saves"]), (53,0))
        by_par = {row["par"]: row for row in scoring["byPar"]}
        self.assertEqual((by_par[3]["holeCount"],by_par[3]["parOrBetter"],by_par[3]["parOrBetterPct"]),(24,12,50.0))
        self.assertEqual((by_par[4]["holeCount"],by_par[4]["parOrBetter"],by_par[4]["parOrBetterPct"]),(60,32,53.3))
        self.assertEqual((by_par[5]["holeCount"],by_par[5]["parOrBetter"],by_par[5]["parOrBetterPct"]),(24,10,41.7))
        outcomes = scoring["outcomes"]
        self.assertEqual({k:outcomes[k] for k in ("eagleOrBetter","birdie","par","bogey","doubleOrWorse")},{"eagleOrBetter":0,"birdie":0,"par":54,"bogey":40,"doubleOrWorse":14})
        self.assertEqual([p["coverage"]["ready"] for p in scoring["phaseStats"][:2]], [108,107])
        self.assertEqual([p["coverage"]["total"] for p in scoring["phaseStats"][:2]], [108,107])
        phase_names = {p["phase"] for p in scoring["phaseStats"]}
        self.assertTrue({"Tee", "Approach", "Short Game", "Putting"}.issubset(phase_names))
        for phase in scoring["phaseStats"]:
            self.assertLessEqual(phase["coverage"]["ready"], phase["coverage"]["total"])

    def test_j2_6_course_loops_order_hardest_and_nine_only(self) -> None:
        scoring = self.stats["scoring"]; combos = {(r["frontKey"],r["backKey"]):r["rounds"] for r in scoring["nineCombos"]}
        self.assertEqual(combos[("gid:101:1-9","gid:102:1-9")],1); self.assertEqual(combos[("gid:102:1-9","gid:101:1-9")],1); self.assertEqual(combos[("gid:101:1-9","gid:101:1-9")],1)
        self.assertEqual(scoring["nineOnlyRounds"],2); self.assertEqual(len(scoring["hardestHoles"]),5); self.assertTrue(all(h["samples"] >= 2 for h in scoring["hardestHoles"]))
        course = self.stats["courses"][0]
        self.assertEqual((course["roundCount"],course["nineOnlyRounds"]),(7,2))
        self.assertEqual(set(course["loopKeys"]), {"gid:101:1-9","gid:102:1-9","gid:103:1-9","course:pine:1-9","course:pine:10-18"})
        self.assertEqual({x["label"] for x in course["nineBreakdown"]}, {"全部","A/A","A/B","B/A","C/A"})

    def test_j2_7_club_ladder_quality_and_manual_override_precedence(self) -> None:
        clubs = {c["club"]:c for c in self.stats["clubs"]}; iron = clubs["7 iron"]
        self.assertEqual((iron["sampleCount"],iron["median"],iron["p10"],iron["p90"],iron["dispersionRange"]),(4,135.0,125.0,145.0,20.0))
        self.assertEqual(iron["roundIds"],["r1","r2"]); self.assertEqual(clubs["driver"]["confidence"],"low"); self.assertEqual(clubs["driver"]["distanceTrend"]["direction"],"insufficient_data")
        self.assertNotIn("Unknown",clubs); self.assertEqual(iron["distanceTrend"]["sampleCount"],4)

    def test_j2_8_round_review_uses_two_ring_cards_and_structured_four_cells(self) -> None:
        detail = build_history_round_detail(self.data,"r2"); self.assertTrue(detail["found"]); self.assertEqual(len(detail["scorecard"]),18); self.assertEqual([c["hole"] for c in detail["scorecard"]],list(range(1,19))); self.assertIsNone(detail["scorecard"][2]["putts"])
        phases = {p["phase"]:p for p in detail["phaseSummary"]}; self.assertEqual(set(phases),{"Tee","Approach","Short Game","Putting","Penalty / Damage"}); self.assertEqual(phases["Putting"]["metrics"]["totalPutts"],31); self.assertEqual(phases["Putting"]["metrics"]["holesWithPutts"],17); self.assertEqual(phases["Approach"]["metrics"]["gir"],10)
        self.assertNotIn("OUT",detail); self.assertNotIn("IN",detail); self.assertEqual(len(build_history_round_detail(self.data,"r4")["scorecard"]),9); self.assertFalse(build_history_round_detail(self.data,"missing")["found"])

    @unittest.expectedFailure
    def test_j2_9_shot_map_labels_points_and_putt_count(self) -> None:
        expected=self.fixture["expected"]["shotMap"]; payload=build_round_hole_shot_map(self.data,expected["roundRef"],expected["hole"],include_image=False); self.assertTrue(payload["found"]); self.assertEqual([s["order"] for s in payload["shots"]],expected["orders"]); self.assertEqual([s["club"] for s in payload["shots"]],expected["clubs"]); self.assertEqual([s["gpsAvailable"] for s in payload["shots"]],expected["gpsAvailable"]); self.assertIsNone(payload["map"]); self.assertEqual(payload["missingData"][0]["label"],"geometry")
        with mock.patch("server_v2.history_round_detail.load_history_data_for_mode",return_value=(self.data,"fixture")): response=load_round_hole_shot_map_response("r1",1,include_image=False)
        self.assertEqual([s.order for s in response.shots],[1,2,3,4]); self.assertEqual(response.shots[0].club,"7 iron"); self.assertEqual(response.shots[0].distance,130); self.assertTrue(response.shots[0].gpsAvailable)

    def test_j2_10_structured_report_keeps_facts_missing_and_sources(self) -> None:
        facts={"schema":"ai-caddie-report-facts-v1","kind":"round","subjectId":"r1","factsUsed":[{"label":"score","value":82,"sourceRefs":["r1"]}],"missingData":[{"label":"putts","state":"missing","sourceRefs":["r2:3"]}]}; report=generate_deterministic_report(facts); self.assertEqual(report["factsUsed"],facts["factsUsed"]); self.assertEqual(report["missingData"],facts["missingData"]); self.assertEqual(set(report["sourceRefs"]),{"r1","r2:3"})
        seen=[]
        class RecordingProvider:
            model="fake-structured"
            def chat(self,messages,*,max_tokens): seen.append(messages[-1].content); return "只根据 factsUsed：82 杆；推杆缺失。"
        generated=generate_report({"kind":"round","factsUsed":facts["factsUsed"],"missingData":[]},RecordingProvider()); self.assertEqual(generated["provider"],"RecordingProvider"); self.assertIn("factsUsed",seen[0]); self.assertIn('"r1"',seen[0])

    def test_j2_11_failed_supplier_keeps_score_and_review_interfaces_alive(self) -> None:
        from server_v2 import reports as reports_api
        class FailingProvider:
            model="fake-down"
            def chat(self,messages,*,max_tokens): raise RuntimeError("fake provider down")
        facts={"kind":"round","factsUsed":[{"label":"score","value":82,"sourceRefs":["r1"]}],"missingData":[]}
        with mock.patch.object(reports_api,"build_text_provider",return_value=FailingProvider()): report=reports_api._generate_provider_report_or_fallback(facts)
        self.assertEqual(report["provider"],"DeterministicReportProvider"); self.assertEqual(report["confidence"],"low"); self.assertEqual(report["factsUsed"],facts["factsUsed"]); self.assertEqual(report["missingData"][-1]["label"],"report_provider")
        self.assertEqual(self.stats["summary"]["totalRounds"],7); self.assertTrue(build_history_round_detail(self.data,"r1")["found"])

if __name__ == "__main__": unittest.main()
