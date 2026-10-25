"""C16b product tests — J2 看成绩与复盘 (spec 2.1-2.11, U/I layers).

Inputs: tests/product/fixtures/c16b/player/ (raw Garmin-shaped scorecards + shot files, made by
make_fixture.py). Expected values: tests/product/fixtures/c16b/golden.json, computed by the
independent reference.py from the product docs BEFORE the product was ever run (see git history).

Harness: one family member whose data partition is the fixture. Every request goes through the
real FastAPI app, the real auth gate (member bearer token), the real loader
(history.load_history_data over data/players/<id>/) and the real stats build. Nothing in the
product is mocked except the model provider in 2.10/2.11, which is a real provider object.
"""
from __future__ import annotations

import http.server
import json
import os
import random
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.core import data as core_data
from ai_caddie.core.config import get_settings
from ai_caddie.courses import course_prep, prep_cache
from ai_caddie.history import history, stats_cache
from ai_caddie.history.history import HistoryData, load_history_data
from ai_caddie.history.history_stats import build_history_stats
from ai_caddie.rounds import players
import server_v2.annotations
import server_v2.caddie
import server_v2.history_drilldown
import server_v2.history_rounds
import server_v2.history_stats
import server_v2.mobile
import server_v2.prep_tips
import server_v2.reports
from server_v2 import data_source
from server_v2.main import app

FIX = Path(__file__).resolve().parent / "fixtures" / "c16b"
G = json.loads((FIX / "golden.json").read_text())
ANNOTATIONS = json.loads((FIX / "annotations.json").read_text())
ID = G["roundIdByPos"]


def V(section: str, *path: str):
    node = G[section]
    for key in path:
        node = node[key]
    return node["value"] if isinstance(node, dict) and "value" in node else node


class _Env:
    """Module-wide harness: a tmp data root holding the fixture as one member's partition."""

    def start(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        env = {"AI_CADDIE_ADMIN_TOKEN": "c16b-admin", "AI_CADDIE_DATA_MODE": "local", "AI_CADDIE_LLM_PROVIDER": "static"}
        self.patches = [
            mock.patch.dict(os.environ, env),
            mock.patch.object(players, "ROOT", self.root),
            mock.patch.object(history, "ROOT", self.root),
            mock.patch.object(core_data, "DATA_DIR", self.root / "data"),
            mock.patch.object(stats_cache, "_PLAYERS_DIR", self.root / "data" / "players"),
            mock.patch.object(data_source, "load_latest_snapshot_history", return_value=None),
        ]
        for module in (server_v2.annotations, server_v2.caddie, server_v2.history_drilldown, server_v2.history_rounds,
                       server_v2.history_stats, server_v2.mobile, server_v2.prep_tips, server_v2.reports):
            for name in dir(module):
                if name.endswith("_ROOT") and getattr(module, name) == Path("."):
                    self.patches.append(mock.patch.object(module, name, self.root))
        for p in self.patches:
            p.start()
        get_settings.cache_clear()
        stats_cache.clear()
        prep_cache.clear()
        member = players.create_player("C16b", root=self.root)
        self.pid, self.token = member["id"], member["token"]
        shutil.copytree(FIX / "player", self.root / "data" / "players" / self.pid)
        other = players.create_player("C16b-empty", root=self.root)
        self.empty_token = other["token"]
        self.client = TestClient(app)
        for row in ANNOTATIONS:
            response = self.post("/api/v2/annotations", row)
            assert response.status_code in (200, 201), response.text
        stats_cache.clear()

    def stop(self) -> None:
        for p in reversed(self.patches):
            p.stop()
        get_settings.cache_clear()
        stats_cache.clear()
        prep_cache.clear()
        self.tmp.cleanup()

    def headers(self, token: str | None = None) -> dict:
        return {"Authorization": f"Bearer {token or self.token}"}

    def get(self, path: str, token: str | None = None, **params):
        response = self.client.get(path, headers=self.headers(token), params=params)
        assert response.status_code == 200, f"{path} {params} -> {response.status_code} {response.text[:300]}"
        return response.json()

    def post(self, path: str, body: dict, token: str | None = None):
        return self.client.post(path, headers=self.headers(token), json=body)

    def put(self, path: str, body: dict, token: str | None = None):
        return self.client.put(path, headers=self.headers(token), json=body)


ENV = _Env()


def setUpModule() -> None:
    ENV.start()


def tearDownModule() -> None:
    ENV.stop()


def mobile(window: str = "all") -> dict:
    return ENV.get("/api/v2/history/stats/mobile", window=window)


def full(window: str = "all") -> dict:
    return ENV.get("/api/v2/history/stats", window=window)


def archive(**params) -> dict:
    params.setdefault("limit", 2000)
    return ENV.get("/api/v2/history/rounds", **params)


def archive_ids(**params) -> list[str]:
    return [card["id"] for group in archive(**params)["groups"] for card in group["rounds"]]


def phase(scoring: dict, name: str) -> dict:
    return next(row for row in scoring["phaseStats"] if row["phase"] == name)


def by_key(rows: list[dict], key: str) -> dict:
    return {row[key]: row for row in rows}


def resolves(ref: str) -> bool:
    """A cited ref resolves when it names real data: a period that exists and holds rounds, or a
    round / hole / shot the drill-down finds."""
    if ref.startswith("trend:recent_"):
        count = int(ref.rsplit("_", 1)[1])
        return mobile(f"last{count}")["summary"]["totalRounds"] == min(count, V("2.1", "totalRounds"))
    if ref.startswith("trend:"):
        _trend, grain, key = ref.split(":", 2)
        bucket = {"quarter": "byQuarter", "year": "byYear", "month": "byMonth", "day": "byDay"}[grain]
        rows = by_key(mobile("all")["time"][bucket], "key")
        return key in rows and bool(rows[key]["roundIds"]) and sorted(archive_ids(period=key)) == sorted(rows[key]["roundIds"])
    return bool(ENV.get(f"/api/v2/history/drilldown/{ref}")["found"])


class J2ResultsTests(unittest.TestCase):
    maxDiff = None

    # ------------------------------------------------------------------ 2.1
    def test_j2_1_results_home_numbers(self) -> None:
        stats = mobile("all")
        summary = stats["summary"]
        rows = [
            ("recent10Average", summary["recent10Average"], V("2.1", "recent10Average")),
            ("career average18 (not shown as recent)", summary["average18"], V("2.1", "careerAverage18")),
            ("bestScore", summary["bestScore"], V("2.1", "bestScore")),
            ("totalRounds", summary["totalRounds"], V("2.1", "totalRounds")),
            ("courseCount", summary["courseCount"], V("2.1", "courseCount")),
        ]
        for label, actual, expected in rows:
            with self.subTest(label):
                self.assertEqual(actual, expected)
        with self.subTest("recent 10 != career"):
            self.assertNotEqual(summary["recent10Average"], summary["average18"])
        with self.subTest("10-round line ends at recent10Average"):
            self.assertEqual(V("2.1", "line10")[-1], summary["recent10Average"])
        with self.subTest("last 20 trend points (id, score, oldest->newest)"):
            points = [p for p in stats["trend"]["points"] if p.get("score") is not None][-20:]
            self.assertEqual([(str(p["roundId"]), p["score"]) for p in points],
                             [(row["roundId"], row["score"]) for row in V("2.1", "trendLast20")])
        recent = [card for group in archive()["groups"] for card in group["rounds"]][:3]
        for index, want in enumerate(V("2.1", "recentThree")):
            with self.subTest(f"recent round {index + 1} score strip"):
                self.assertEqual(recent[index]["id"], want["roundId"])
                self.assertEqual(recent[index]["score"], want["score"])
                self.assertEqual([cell["toPar"] for cell in recent[index]["scoreStrip"]], want["toPar"])
        with self.subTest("全部 N 场"):
            self.assertEqual(archive()["total"], V("2.4", "total"))

    def test_j2_1_handicap_estimate_is_whs(self) -> None:
        """Was KNOWN-RED (known-red/C16b.md #1): manual §3 says WHS; B5a says unpriceable rounds count toward
        the 20 but the estimate ignores unusable records (no score-par stand-in, no 0.96)."""
        summary = mobile("all")["summary"]
        self.assertEqual((summary["handicapEstimate"], summary["handicapChangeRecent20"]),
                         (V("2.1", "handicapEstimate"), V("2.1", "handicapChangeRecent20")))

    # ------------------------------------------------------------------ 2.2
    def test_j2_2_range_granularity_and_previous(self) -> None:
        for window in ("all", "last10", "last20", "12m"):
            stats = mobile(window)
            want = V("2.2", "windows")[window]
            with self.subTest(f"{window} sample size"):
                self.assertEqual(stats["summary"]["totalRounds"], want["roundCount"]["value"])
            with self.subTest(f"{window} sample = these rounds"):
                got = sorted({rid for row in stats["time"]["byMonth"] for rid in row["roundIds"]})
                self.assertEqual(got, sorted(want["roundIds"]["value"]))
            want_prev = V("2.2", "previous")[window]["value"]
            with self.subTest(f"{window} previous period"):
                prev = stats.get("previous")
                if want_prev is None:
                    self.assertIsNone(prev)
                else:
                    self.assertIsNotNone(prev)
                    self.assertEqual(prev["window"], want_prev["window"])
                    self.assertEqual(prev["roundCount"], want_prev["roundCount"])
                    self.assertEqual(prev.get("requiredRounds"), want_prev["requiredRounds"])
                    self.assertEqual("scoring" in prev, want_prev["hasScoring"])
        with self.subTest("range defines sample: last10 months"):
            self.assertEqual([row["key"] for row in mobile("last10")["time"]["byMonth"]], V("2.2", "last10Months"))
        cmp = V("2.2", "compareScoring")
        sources = {"last10": mobile("last10")["scoring"], "prev10": mobile("last10")["previous"]["scoring"],
                   "prev12m": mobile("12m")["previous"]["scoring"]}
        for window, scoring in sources.items():
            want = cmp[window]
            putting, tee, approach = scoring["putting"], phase(scoring, "Tee"), phase(scoring, "Approach")
            pairs = {
                "totalPutts": putting["totalPutts"], "holesWithPutts": putting["holesWithPutts"],
                "zeroPutts": putting["zeroPutts"], "onePutts": putting["onePutts"], "twoPutts": putting["twoPutts"],
                "threePlusPutts": putting["threePlusPutts"], "fairwaysRecorded": tee["fairwaysRecorded"],
                "fairwaysHit": tee["fairwaysHit"], "fairwayMissLeft": tee["fairwayMissLeft"],
                "fairwayMissRight": tee["fairwayMissRight"],
            }
            if window != "last10":
                # last10 holds the putt-corrected holes P2#12 / P4#5, whose GIR is known-red #2/#3
                # (test_j2_5_corrected_*); its GIR / scrambling are asserted there.
                pairs.update({"girRecorded": approach["girRecorded"], "gir": approach["gir"],
                              "scrambleChances": scoring["scrambling"]["chances"],
                              "scrambleSaves": scoring["scrambling"]["saves"]})
            for key, actual in pairs.items():
                with self.subTest(f"{window} {key}"):
                    self.assertEqual(actual, want[key]["value"])
        time = mobile("all")["time"]
        for bucket in ("byQuarter", "byYear"):
            rows = by_key(time[bucket], "key")
            for key, want in V("2.2", "periods")[bucket].items():
                with self.subTest(f"{bucket} {key}"):
                    row = rows[key]
                    self.assertEqual(
                        (row["roundCount"], sorted(row["roundIds"]), row["average18"], row["bestScore"], row["worstScore"],
                         row["outcomes"]["birdie"], row["outcomes"]["doubleOrWorse"]),
                        (want["roundCount"], want["roundIds"], want["average18"], want["bestScore"], want["worstScore"],
                         want["birdies"], want["doubleOrWorse"]))
        freq = time["playFrequency"]
        with self.subTest("calendar 月均场数"):
            self.assertEqual(freq["roundsPerMonth"], V("2.2", "playFrequency", "roundsPerMonth"))
        with self.subTest("calendar 最活跃月"):
            self.assertEqual(freq["mostActiveMonth"], V("2.2", "playFrequency", "mostActiveMonth"))
        with self.subTest("calendar day cells"):
            days = by_key(time["byDay"], "key")
            for key, want in V("2.2", "periods")["byDay"].items():
                self.assertEqual(sorted(days[key]["roundIds"]), want["roundIds"], key)

    # ------------------------------------------------------------------ 2.3
    def test_j2_3_every_summary_drills_to_the_same_rounds(self) -> None:
        stats = mobile("all")
        quarter = by_key(stats["time"]["byQuarter"], "key")["2026-Q2"]
        want_q = V("2.3", "quarter2026Q2")
        with self.subTest("period card 2026-Q2"):
            self.assertEqual(sorted(quarter["roundIds"]), want_q)
            self.assertEqual(sorted(archive_ids(period="2026-Q2")), want_q)
        bands = by_key(stats["scoring"]["scoreBands"], "label")
        for label, want in V("2.3", "scoreBands").items():
            with self.subTest(f"distribution bar {label}"):
                self.assertEqual(sorted(bands[label]["roundIds"]), want)
                self.assertEqual(sorted(archive_ids(scoreBand=label)), want)
        with self.subTest("calendar cell 2026-06-14"):
            day = by_key(stats["time"]["byDay"], "key")["2026-06-14"]
            self.assertEqual(sorted(day["roundIds"]), V("2.3", "day20260614"))
            self.assertEqual(sorted(archive_ids(period="2026-06-14")), V("2.3", "day20260614"))
        with self.subTest("course Lark Valley"):
            course = by_key(stats["courses"], "courseKey")[V("2.3", "larkCourseKey")]
            self.assertEqual(course["roundIds"], V("2.3", "larkCourseRounds"))
            self.assertEqual(archive_ids(course=V("2.3", "larkCourseKey")), V("2.3", "larkCourseRounds"))
        for point in V("2.1", "trendLast20")[-3:]:
            with self.subTest(f"trend point {point['pos']} -> round"):
                detail = ENV.get(f"/api/v2/history/rounds/{point['roundId']}")
                self.assertTrue(detail["found"])
                self.assertEqual(detail["round"]["score"], point["score"])
        hardest = V("2.6", "hardestHoles")[0]
        for visit in V("2.3", "hardestHoleVisits"):
            with self.subTest(f"hardest hole visit {visit['pos']}#{visit['displayHole']}"):
                shotmap = ENV.get(f"/api/v2/history/rounds/{visit['roundId']}/holes/{visit['displayHole']}/shotmap",
                                  includeImage="false")
                self.assertTrue(shotmap["found"])
                self.assertEqual(shotmap["par"], hardest["par"])
                course_round = next(r for r in by_key(stats["courses"], "courseKey")[V("2.3", "larkCourseKey")]["rounds"]
                                    if r["roundId"] == visit["roundId"])
                self.assertIn(hardest["loopKey"], (course_round.get("frontLoopKey"), course_round.get("backLoopKey")))

    # ------------------------------------------------------------------ 2.4
    def test_j2_4_archive_search_filter_group(self) -> None:
        rows = [
            ("search course 'Lark'", dict(search="Lark"), "searchLark"),
            ("search date '2026-06'", dict(search="2026-06"), "searchDate202606"),
            ("filter year 2025", dict(year="2025"), "year2025"),
            ("filter has shots", dict(hasShots="true"), "hasShots"),
            ("Kestrel x 2026", dict(course=V("2.3", "kestrelCourseKey"), year="2026"), "kestrel2026"),
            ("Lark x no shots", dict(course=V("2.3", "larkCourseKey"), hasShots="false"), "larkNoShots"),
        ]
        for label, params, key in rows:
            with self.subTest(label):
                self.assertEqual(archive_ids(**params), V("2.4", key))
        with self.subTest("grouped by month"):
            groups = archive(year="2026")["groups"]
            self.assertEqual([(g["key"], [c["id"] for c in g["rounds"]]) for g in groups],
                             [(g["key"], g["roundIds"]) for g in V("2.4", "monthGroups2026")])

    # ------------------------------------------------------------------ 2.5
    def test_j2_5_stat_honesty(self) -> None:
        want = G["2.5"]["all"]
        scoring = full("all")["scoring"]
        putting, tee, approach = scoring["putting"], phase(scoring, "Tee"), phase(scoring, "Approach")
        composition = {row["key"]: row["count"] for row in scoring["outcomeDistribution"]}
        product_key = {"eagle": "eagleOrBetter", "birdie": "birdie", "par": "par", "bogey": "bogey",
                       "double": "double", "triple": "triple", "quadPlus": "quadPlus"}
        for dim, count in want["composition"]["value"].items():
            with self.subTest(f"成绩构成 {dim}"):
                self.assertEqual(composition[product_key[dim]], count)
        par_rows = by_key(scoring["byPar"], "key")
        for key, w in want["byPar"]["value"].items():
            with self.subTest(f"{key} 均杆/保帕"):
                row = par_rows[key]
                self.assertEqual((row["holeCount"], row["averageScore"], row["parOrBetter"]),
                                 (w["holeCount"], w["averageScore"], w["parOrBetter"]))
        rows = [
            ("putting denominator (default holes out, corrected in)", putting["coverage"]["total"], "puttEligibleHoles"),
            ("holes with putts", putting["holesWithPutts"], "holesWithPutts"),
            ("total putts (corrections applied)", putting["totalPutts"], "totalPutts"),
            ("0 putts", putting["zeroPutts"], "zeroPutts"),
            ("1 putt", putting["onePutts"], "onePutts"),
            ("2 putts", putting["twoPutts"], "twoPutts"),
            ("3+ putts", putting["threePlusPutts"], "threePlusPutts"),
            ("fairways recorded (unknown not counted)", tee["fairwaysRecorded"], "fairwaysRecorded"),
            ("fairways hit", tee["fairwaysHit"], "fairwaysHit"),
            ("fairway left", tee["fairwayMissLeft"], "fairwayMissLeft"),
            ("fairway right", tee["fairwayMissRight"], "fairwayMissRight"),
            ("penalties total", scoring["penalties"]["total"], "penaltiesTotal"),
            ("penalty holes recorded (Garmin missing != 0)", scoring["penalties"]["holesRecorded"], "penaltyHolesRecorded"),
            ("penalty rounds", scoring["penalties"]["roundsRecorded"], "penaltyRoundsRecorded"),
            ("penalties per round", scoring["penalties"]["averagePerRound"], "penaltyAveragePerRound"),
        ]
        for label, actual, key in rows:
            with self.subTest(label):
                self.assertEqual(actual, want[key]["value"])
        with self.subTest("putt buckets total 100%"):
            self.assertAlmostEqual(sum(putting[k] for k in ("zeroPuttPct", "onePuttPct", "twoPuttPct", "threePlusPuttPct")), 100.0, delta=0.2)
        sequences = {seq["roundId"]: seq for seq in scoring["roundSequences"]}
        for label, row in G["2.5"]["holeStates"].items():
            w = row["value"]
            if label in ("defaultCorrected", "normalCorrected"):
                continue  # GIR of corrected holes: test_j2_5_corrected_putts_drive_gir
            with self.subTest(f"hole state {label}"):
                seq = sequences[w["roundId"]]
                index = seq["holes"].index(w["hole"])
                self.assertEqual((seq["putts"][index], seq["gir"][index]), (w["putts"], w["gir"]))
        for label in ("defaultCorrected", "normalCorrected"):
            w = G["2.5"]["holeStates"][label]["value"]
            with self.subTest(f"hole state {label} putts"):
                seq = sequences[w["roundId"]]
                self.assertEqual(seq["putts"][seq["holes"].index(w["hole"])], w["putts"])

    @unittest.expectedFailure
    def test_j2_5_corrected_default_hole_counts_in_gir(self) -> None:
        """KNOWN-RED #2. Spec 2.5 / B0c: a default hole leaves putting AND GIR, and a putt correction
        brings it back ("订正过则计入"; B0c "对该洞做过推杆更正则重新计入"). Product re-admits it to
        putting only; GIR (and so scrambling) keeps skipping P2#12."""
        scoring = full("all")["scoring"]
        seq = {s["roundId"]: s for s in scoring["roundSequences"]}
        w = G["2.5"]["holeStates"]["defaultCorrected"]["value"]
        self.assertEqual(seq[w["roundId"]]["gir"][seq[w["roundId"]]["holes"].index(w["hole"])], w["gir"])
        approach = phase(scoring, "Approach")
        self.assertEqual(approach["coverage"]["total"], G["2.5"]["all"]["girEligibleHoles"]["value"])
        last10 = mobile("last10")["scoring"]
        self.assertEqual((last10["scrambling"]["chances"], last10["scrambling"]["saves"]),
                         (V("2.2", "compareScoring", "last10", "scrambleChances"), V("2.2", "compareScoring", "last10", "scrambleSaves")))

    @unittest.expectedFailure
    def test_j2_5_putt_correction_recomputes_gir(self) -> None:
        """KNOWN-RED #3. GIR is 按推杆推算 (README §4: 第一推是第几杆 <= Par-1) and a correction is used at
        once by the statistics (spec 3.1). P4#5: 5 strokes, putts corrected 2 -> 3, so GIR becomes true."""
        scoring = full("all")["scoring"]
        seq = {s["roundId"]: s for s in scoring["roundSequences"]}
        w = G["2.5"]["holeStates"]["normalCorrected"]["value"]
        self.assertEqual(seq[w["roundId"]]["gir"][seq[w["roundId"]]["holes"].index(w["hole"])], w["gir"])
        approach = phase(scoring, "Approach")
        self.assertEqual((approach["girRecorded"], approach["gir"]),
                         (G["2.5"]["all"]["girRecorded"]["value"], G["2.5"]["all"]["gir"]["value"]))
        self.assertEqual((scoring["scrambling"]["chances"], scoring["scrambling"]["saves"]),
                         (G["2.5"]["all"]["scrambleChances"]["value"], G["2.5"]["all"]["scrambleSaves"]["value"]))

    # ------------------------------------------------------------------ 2.6
    def _check_loops(self, scoring: dict, courses: list[dict], tag: str) -> None:
        loops = by_key(scoring["loops"], "loopKey")
        for key, want in V("2.6", "loops").items():
            with self.subTest(f"{tag} loop {key}"):
                row = loops[key]
                self.assertEqual((row["label"], row["roundCount"]), (want["label"], want["roundCount"]))
                self.assertEqual([(h["hole"], h["par"], h["samples"]) for h in row["holes"]],
                                 [(h["hole"], h["par"], h["samples"]) for h in want["holes"]])
                for got, exp in zip(row["holes"], want["holes"]):
                    self.assertAlmostEqual(got["averageToPar"], exp["averageToPar"], delta=0.0051, msg=f"hole {exp['hole']}")
        with self.subTest(f"{tag} loop set"):
            self.assertEqual(sorted(loops), sorted(V("2.6", "loops")))
        combos = [(c["frontKey"], c["backKey"], c["rounds"], c["average"]) for c in scoring["nineCombos"]]
        want_combos = [(c["frontKey"], c["backKey"], c["rounds"], c["average"]) for c in V("2.6", "nineCombos")]
        with self.subTest(f"{tag} combos A/B != B/A, only full 18"):
            self.assertEqual(sorted(combos), sorted(want_combos))
            multi = [c for c in want_combos if c[2] > 1]
            self.assertEqual(combos[: len(multi)], multi)
        with self.subTest(f"{tag} only-9 count"):
            self.assertEqual(scoring["nineOnlyRounds"], V("2.6", "nineOnlyRounds"))
        with self.subTest(f"{tag} hardest holes (>=2 samples, by average over par)"):
            got = [(h["loopKey"], h["hole"], h["par"], h["samples"]) for h in scoring["hardestHoles"]]
            self.assertEqual(got, [(h["loopKey"], h["hole"], h["par"], h["samples"]) for h in V("2.6", "hardestHoles")])
            for h, w in zip(scoring["hardestHoles"], V("2.6", "hardestHoles")):
                self.assertAlmostEqual(h["averageToPar"], w["averageToPar"], delta=0.0051)
        kestrel = by_key(courses, "courseKey")[V("2.3", "kestrelCourseKey")]
        with self.subTest(f"{tag} Kestrel loops + only-9 M"):
            self.assertEqual(sorted(kestrel["loopKeys"]), V("2.6", "kestrelLoopKeys"))
            self.assertEqual(kestrel["nineOnlyRounds"], V("2.6", "kestrelNineOnly"))
        with self.subTest(f"{tag} Kestrel 全部 N 种 + 常打三种"):
            keys = set(kestrel["loopKeys"])
            mine = [c for c in scoring["nineCombos"] if c["frontKey"] in keys and c["backKey"] in keys]
            self.assertEqual(len(mine), V("2.6", "kestrelComboCount"))
            self.assertEqual([{"frontKey": c["frontKey"], "backKey": c["backKey"], "rounds": c["rounds"]} for c in mine[:3]],
                             V("2.6", "kestrelTopThreeCombos"))

    def test_j2_6_course_page(self) -> None:
        stats = mobile("all")
        self._check_loops(stats["scoring"], stats["courses"], "served")
        data = load_history_data(ENV.pid)
        for seed in (1, 2):
            shuffled = list(data.rounds)
            random.Random(seed).shuffle(shuffled)
            built = build_history_stats(HistoryData(raw_rounds=list(reversed(data.raw_rounds)), rounds=shuffled, shots=data.shots),
                                        data_mode="local", player_id=ENV.pid)
            self._check_loops(built["scoring"], built["courses"], f"history order shuffled seed {seed}")

    # ------------------------------------------------------------------ 2.7
    def test_j2_7_club_ladder_and_bag(self) -> None:
        clubs = mobile("all")["clubs"]
        want = V("2.7", "clubs")
        with self.subTest("one row per club (case merged, Unknown dropped)"):
            self.assertEqual(sorted(c["club"].lower() for c in clubs), sorted(want))
        for club in clubs:
            w = want[club["club"].lower()]
            with self.subTest(f"ladder {club['club']}"):
                self.assertEqual((club["sampleCount"], club["median"], club["p10"], club["p90"]),
                                 (w["sampleCount"], w["median"], w["p10"], w["p90"]))
        bag_path = f"/api/v2/players/{ENV.pid}/clubs/bag"
        def bag(token=None, pid=None):
            body = ENV.get(f"/api/v2/players/{pid or ENV.pid}/clubs/bag", token=token)
            return {"source": body["source"], "clubs": [{"token": c["token"], "distanceM": c["distanceM"]} for c in body["clubs"]]}
        with self.subTest("nothing -> empty"):
            empty_pid = next(p["id"] for p in players.load_registry(ENV.root)["players"] if p.get("name") == "C16b-empty")
            self.assertEqual(bag(token=ENV.empty_token, pid=empty_pid), V("2.7", "bagNone"))
        with self.subTest("Garmin bag when no manual"):
            self.assertEqual(bag(), V("2.7", "bagGarmin"))
        response = ENV.put(bag_path, {"clubs": [{"token": "driver"}, {"token": "iron7", "distanceM": 150}, {"token": "pw"}]})
        self.addCleanup(lambda: ENV.put(bag_path, {"clubs": []}))
        self.assertEqual(response.status_code, 200, response.text)
        with self.subTest("manual > Garmin"):
            got = bag()
            want_manual = V("2.7", "bagManual")
            self.assertEqual(got["source"], want_manual["source"])
            self.assertEqual([c["token"] for c in got["clubs"]], [c["token"] for c in want_manual["clubs"]])
            self.assertEqual(got["clubs"][1]["distanceM"], 150)
        with self.subTest("typed distance reaches the caddie ladder"):
            ladder = dict(course_prep.effective_club_ladder(ENV.pid))
            want = dict((name, dist) for name, dist in V("2.7", "ladderAfterManual"))
            self.assertEqual(sorted(ladder), sorted(want))
            self.assertEqual(ladder["iron7"], want["iron7"])   # manual 150 beats measured 148
            self.assertEqual(ladder["pw"], want["pw"])         # no typed distance -> own measured median

    def test_j2_7_measured_ladder_merges_case(self) -> None:
        """Was KNOWN-RED #4. Spec 2.7 球包距离阶梯 合并大小写: Driver(6 shots) + driver(5 shots) are one club of
        11 (median 220) in the caddie ladder's measured median too, not only the larger spelling."""
        bag_path = f"/api/v2/players/{ENV.pid}/clubs/bag"
        ENV.put(bag_path, {"clubs": [{"token": "driver"}, {"token": "iron7", "distanceM": 150}, {"token": "pw"}]})
        self.addCleanup(lambda: ENV.put(bag_path, {"clubs": []}))
        self.assertEqual(dict(course_prep.effective_club_ladder(ENV.pid))["driver"],
                         dict((n, d) for n, d in V("2.7", "ladderAfterManual"))["driver"])

    # ------------------------------------------------------------------ 2.8
    def test_j2_8_round_review(self) -> None:
        for pos, item in G["2.8"].items():
            want = item["value"]
            detail = ENV.get(f"/api/v2/history/rounds/{want['roundId']}")
            with self.subTest(f"{pos} found / score"):
                self.assertTrue(detail["found"])
                self.assertEqual((detail["round"]["score"], detail["round"]["par"], detail["round"]["holesCompleted"]),
                                 (want["score"], want["par"], want["holesCompleted"]))
            played = {c["hole"] for c in want["cells"]}
            with self.subTest(f"{pos} unplayed holes stay empty (never 0)"):
                for c in detail["scorecard"]:
                    if c["hole"] not in played:
                        self.assertEqual((c["score"], c["putts"], c["penalties"]), (None, None, None), c["hole"])
            cells = [c for c in detail["scorecard"] if c["hole"] in played]
            with self.subTest(f"{pos} cells (hole, par, score, putts, penalties)"):
                self.assertEqual([(c["hole"], c["par"], c["score"], c["toPar"], c["putts"], c["penalties"]) for c in cells],
                                 [(c["hole"], c["par"], c["score"], c["toPar"], c["putts"], c["penalties"]) for c in want["cells"]])
            with self.subTest(f"{pos} two loop cards in course hole numbers"):
                self.assertEqual([(c["globalId"], c["localHole"]) for c in cells],
                                 [(c["globalId"], c["localHole"]) for c in want["cells"]])
            grid = by_key(detail["phaseSummary"], "phase")
            four = want["four"]
            with self.subTest(f"{pos} four cells: missing stays missing, never 0"):
                self.assertEqual(grid["Tee"]["state"], four["tee"]["state"])
                if four["tee"]["state"] == "ready":
                    self.assertEqual((grid["Tee"]["metrics"]["fairwaysHit"], grid["Tee"]["metrics"]["fairwaysRecorded"]),
                                     (four["tee"]["fairwaysHit"], four["tee"]["fairwaysRecorded"]))
                self.assertEqual(grid["Approach"]["state"], four["approach"]["state"])
                if four["approach"]["state"] == "ready":
                    self.assertEqual((grid["Approach"]["metrics"]["gir"], grid["Approach"]["metrics"]["girRecorded"]),
                                     (four["approach"]["gir"], four["approach"]["girRecorded"]))
                self.assertEqual(grid["Putting"]["state"], four["putting"]["state"])
                self.assertEqual(grid["Putting"]["metrics"]["totalPutts"], four["putting"]["totalPutts"])
                self.assertEqual(grid["Penalty / Damage"]["metrics"]["totalPenalties"], four["penalty"]["totalPenalties"])

    # ------------------------------------------------------------------ 2.9
    def test_j2_9_shot_map(self) -> None:
        for key, item in G["2.9"].items():
            want = item["value"]
            shotmap = ENV.get(f"/api/v2/history/rounds/{want['roundId']}/holes/{want['hole']}/shotmap", includeImage="false")
            real = [s for s in shotmap["shots"] if not s.get("synthetic")]
            with self.subTest(f"{key} numbering follows stroke order"):
                self.assertEqual([s["order"] for s in real], want["orders"])
            with self.subTest(f"{key} dot colour = landing lie"):
                self.assertEqual([s["endLie"] for s in real], want["endLies"])
            with self.subTest(f"{key} club label"):
                self.assertEqual([s["club"] for s in real], want["clubs"])
            detail = ENV.get(f"/api/v2/history/rounds/{want['roundId']}")
            hole = next(h for h in detail["holeDetails"] if h["hole"] == want["hole"])
            with self.subTest(f"{key} label distance"):
                self.assertEqual([s["distance"] for s in hole["shots"]], want["meters"])
            with self.subTest(f"{key} green 推 xN"):
                self.assertEqual(hole["putts"], want["putts"])

    # ------------------------------------------------------------------ 2.10
    def test_j2_10_report_facts_inferences_missing_sources(self) -> None:
        captured: list[list] = []

        class RecordingProvider:
            model = "recording"

            def chat(self, messages, max_tokens=None):
                captured.append(list(messages))
                return "复盘：见事实。"

        kestrel = V("2.3", "kestrelCourseKey")
        targets = [("round", f"/api/v2/reports/round/{ID['P1']}"), ("course", f"/api/v2/reports/course/{kestrel}"),
                   ("hole", f"/api/v2/reports/hole/{kestrel}/8"), ("club", "/api/v2/reports/club/Driver"),
                   ("trend", "/api/v2/reports/trend/all")]
        for kind, path in targets:
            with self.subTest(f"{kind} static report keeps facts/inferences/missing/sources apart"):
                report = ENV.get(path)
                for key in ("factsUsed", "inferencesMade", "missingData", "sourceRefs"):
                    self.assertIsInstance(report[key], list, key)
                for ref in report["sourceRefs"]:
                    self.assertTrue(resolves(ref), f"{kind} cites unresolvable {ref}")
            with self.subTest(f"{kind} model input = structured facts only"):
                captured.clear()
                with mock.patch.object(server_v2.reports, "build_text_provider", return_value=RecordingProvider()):
                    response = ENV.post(path + "/generate", {})
                self.assertEqual(response.status_code, 200, response.text)
                report = response.json()
                self.assertEqual(len(captured), 1)
                user = next(m for m in captured[0] if m.role == "user").content
                payload = json.loads(user[user.index("{"):])
                self.assertEqual(payload["factsUsed"], report["factsUsed"])
                self.assertNotIn("scorecardDetails", user)
                self.assertNotIn("holeShots", user)
        facts = {f["label"]: f for f in ENV.get(f"/api/v2/reports/round/{ID['P1']}")["factsUsed"]}
        with self.subTest("round facts = golden"):
            self.assertEqual(facts["total_rounds"]["value"], V("2.10", "totalRounds"))
            self.assertEqual(facts["average_18"]["value"], V("2.10", "average18"))
            self.assertEqual(facts["best_score"]["value"], V("2.10", "bestScore"))
            card = facts["round_scorecard"]["value"]
            self.assertEqual((card.get("score", card.get("strokes")), card.get("par")), (V("2.10", "roundP1")["score"], V("2.10", "roundP1")["par"]))
        with self.subTest("no-shot round cites no shots"):
            labels = [f["label"] for f in ENV.get(f"/api/v2/reports/round/{V('2.10', 'noShotRound')}")["factsUsed"]]
            self.assertNotIn("round_shots", labels)

    # ------------------------------------------------------------------ 2.11
    def test_j2_11_provider_failure_keeps_pages(self) -> None:
        class Failing(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b'{"error": "overloaded"}')

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Failing)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {"AI_CADDIE_LLM_PROVIDER": "nvidia_nim", "NVIDIA_API_KEY": "c16b-fake-key",
               "NVIDIA_NIM_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1", "NVIDIA_NIM_MODEL": "fake-model"}
        with mock.patch.dict(os.environ, env):
            get_settings.cache_clear()
            try:
                response = ENV.post(f"/api/v2/reports/round/{ID['P1']}/generate", {})
                with self.subTest("generate answers with an honest fallback"):
                    self.assertEqual(response.status_code, 200, response.text)
                    report = response.json()
                    self.assertIn("report_provider", [row.get("label") for row in report["missingData"]])
                    self.assertEqual(report["confidence"], "low")
                with self.subTest("成绩 home unchanged"):
                    summary = mobile("all")["summary"]
                    self.assertEqual((summary["recent10Average"], summary["bestScore"], summary["totalRounds"]),
                                     (V("2.1", "recent10Average"), V("2.1", "bestScore"), V("2.1", "totalRounds")))
                with self.subTest("复盘 unchanged"):
                    want = V("2.8", "P12")
                    detail = ENV.get(f"/api/v2/history/rounds/{want['roundId']}")
                    self.assertEqual([c["score"] for c in detail["scorecard"]], [c["score"] for c in want["cells"]])
                    shotmap = ENV.get(f"/api/v2/history/rounds/{ID['P12']}/holes/12/shotmap", includeImage="false")
                    self.assertTrue(shotmap["found"])
                with self.subTest("stored report readable"):
                    self.assertEqual(ENV.get(f"/api/v2/reports/round/{ID['P1']}")["confidence"], "low")
            finally:
                get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
