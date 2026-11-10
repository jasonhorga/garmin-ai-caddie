"""History home, stats, search and round review over the real HTTP routes (test-plan S-15..S-17).

Every test serves an in-memory round history through the production loader seam
(``load_history_data_for_mode``) and reads it back through ``server_v2.main.app``.
Expected numbers are written by hand from the rows built below.
"""
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.core.config import get_settings
from ai_caddie.history import hole_history_shots, stats_cache
from ai_caddie.history.history import HistoryData
from server_v2 import (annotations, course_install, history_drilldown, history_overview,
                       history_round_detail, history_rounds, history_stats)
from server_v2 import main as server_main
from tests.support.clock import FakeClock

# A history request must not leave a live-round lease behind (same state the package contract clears).
ACTIVE_ROUND_STATE = (
    (server_main, ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_START_TIMES",
                   "_ROUND_START_CACHE", "_ACTIVE_EVENT_DEVICES", "_ACTIVE_SELECTIONS")),
    (course_install, ("_CURRENT_COURSE_IDS",)),
)
LOADER_MODULES = (history_stats, history_overview, history_drilldown, history_round_detail,
                  history_rounds, annotations, server_main)
ROOT_ATTRIBUTES = ("ANNOTATION_ROOT", "WEATHER_ROOT", "REPORTS_ROOT", "DECISION_AUDIT_ROOT")
TODAY = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)


def hole(number, strokes, *, putts=2, gir=True):
    return {"number": number, "strokes": strokes, "par": 4, "putts": putts, "gir": gir}


def round_row(rid, day, holes, *, course="Alpha Links", key="alpha", gid=111, has_shots=False):
    # Every hole is a par 4, so an 18-hole card is par 72 and a nine is par 36.
    return {"id": rid, "ids": [rid], "date": day, "course": course, "courseKey": key, "globalId": gid,
            "holesCompleted": len(holes), "par": 4 * len(holes), "holePars": "4" * len(holes),
            "strokes": sum(h["strokes"] for h in holes if h["strokes"] is not None),
            "holes": holes, "hasShots": has_shots}


def history(rounds, shots=()):
    return HistoryData(raw_rounds=[{"id": row["id"], "hasShots": row["hasShots"]} for row in rounds],
                       rounds=list(rounds), shots=list(shots))


def low_round():
    # 73: hole 1 is a bogey without GIR, the rest are pars. Hole 17's putts were never entered
    # (unknown, not zero); hole 18 is a chip-in (a real zero) whose GIR was never recorded.
    holes = [hole(1, 5, gir=False)] + [hole(n, 4) for n in range(2, 17)]
    holes += [hole(17, 4, putts=None), hole(18, 4, putts=0, gir=None)]
    return round_row("low18", "2026-03-14", holes)


def high_round():
    # 90: eighteen bogeys, two putts each, no green in regulation.
    return round_row("high18", "2026-02-07", [hole(n, 5, gir=False) for n in range(1, 19)])


def nine_round():
    # 45 over nine holes on another course; GIR was not recorded on any hole.
    return round_row("nine", "2026-01-10", [hole(n, 5, gir=None) for n in range(1, 10)],
                     course="Bravo Nine", key="bravo", gid=333)


def mixed_history():
    return history([low_round(), high_round(), nine_round()])


def ladder_history(count):
    # `count` 18-hole rounds on consecutive days; the newest scores 80 and each older one 1 more.
    start = date(2025, 1, 1)
    rows = []
    for index in range(count):
        score = 80 + (count - 1 - index)
        rows.append({"id": f"r{index:02d}", "ids": [f"r{index:02d}"],
                     "date": (start + timedelta(days=index)).isoformat(), "course": "Alpha Links",
                     "courseKey": "alpha", "globalId": 111, "holesCompleted": 18, "strokes": score,
                     "par": 72, "holes": [], "hasShots": False})
    return history(rows)


class HistoryRouteCase(unittest.TestCase):
    """Real app and routers; only the history loader, storage roots and clock are replaced."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.data = history([])
        clock = FakeClock(TODAY)
        patches = [
            mock.patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture", "AI_CADDIE_ADMIN_TOKEN": "",
                                         "AI_CADDIE_SECURITY_PROFILE": ""}),
            # The hole-history window ("last N days") reads today's date from this production seam.
            mock.patch.object(hole_history_shots, "_today", side_effect=lambda: clock.now().date()),
            mock.patch.object(server_main, "_ACTIVE_PACKAGED_ROUNDS", set()),
            *(mock.patch.dict(getattr(module, name), clear=True)
              for module, names in ACTIVE_ROUND_STATE for name in names),
        ]
        for module in LOADER_MODULES:
            patches.append(mock.patch.object(module, "load_history_data_for_mode",
                                             side_effect=lambda *a, **kw: (self.data, "fixture")))
            patches += [mock.patch.object(module, name, root) for name in ROOT_ATTRIBUTES if hasattr(module, name)]
        for target in patches:
            target.start()
            self.addCleanup(target.stop)
        for clear in (get_settings.cache_clear, stats_cache.clear):
            clear()
            self.addCleanup(clear)
        self.client = TestClient(server_main.app)
        self.addCleanup(self.client.close)

    def get(self, path, **params):
        response = self.client.get(path, params=params)
        self.assertEqual(response.status_code, 200, response.text[:500])
        return response.json()

    def serve(self, data):
        self.data = data
        stats_cache.clear()


def phase(stats, name):
    return next(row for row in stats["scoring"]["phaseStats"] if row["phase"] == name)


class HistoryStatsTests(HistoryRouteCase):
    def test_overview_and_stats_count_rounds_putts_and_gir_honestly(self):
        """S-15 [main]: home and stats agree on round counts and averages, and unknown putts or GIR never count as zero."""
        self.serve(mixed_history())
        overview = self.get("/api/v2/history/overview")["metrics"]
        stats = self.get("/api/v2/history/stats")
        summary, putting, approach = stats["summary"], stats["scoring"]["putting"], phase(stats, "Approach")

        expected_counts = {
            "totalRounds": 3,         # low18 + high18 + nine
            "eighteenHoleRounds": 2,  # low18, high18
            "nineHoleRounds": 1,      # nine
            "average18": 81.5,        # (73 + 90) / 2; the nine never enters an 18-hole average
            "bestScore": 73,          # best 18-hole score
        }
        for field, expected in expected_counts.items():
            with self.subTest(field=field):
                self.assertEqual(overview[field], expected)
                self.assertEqual(summary[field], expected)
        self.assertEqual(overview["recent10Average"], 81.5)  # only two 18-hole rounds exist
        self.assertEqual(overview["recent20Average"], 81.5)

        expected_putting = {
            "holesWithPutts": 44,  # 45 holes minus low18 hole 17, whose putts are unknown
            "totalPutts": 86,      # 16x2 + 0 (chip-in) on low18, 18x2 on high18, 9x2 on the nine
            "zeroPutts": 1,        # only the real chip-in; the unknown hole is not a zero
            "twoPutts": 43,        # 16 + 18 + 9
            "roundsWithPutts": 3,
            "averagePuttsPerRound": 28.7,  # 86 / 3
        }
        for field, expected in expected_putting.items():
            with self.subTest(field=field):
                self.assertEqual(putting[field], expected)
        self.assertNotIn("low18:17", putting["holeRefs"])
        self.assertEqual(putting["coverage"], {"ready": 44, "total": 45, "pct": 97.8})  # 44/45

        # GIR recorded on 35 holes: low18 holes 1-17 and all of high18; hit on low18 holes 2-17.
        self.assertEqual((approach["girRecorded"], approach["gir"], approach["missedGir"], approach["girPct"]),
                         (35, 16, 19, 45.7))  # 16/35 = 45.71%
        self.assertNotIn("low18:18", approach["holeRefs"])

    def test_round_classes_are_counted_honestly(self):
        """S-15: a full round, a nine, unknown putts, undeterminable GIR and an empty history each report what is known."""
        unknown_putts = round_row("nop", "2026-04-01", [hole(n, 4, putts=None) for n in range(1, 19)])
        unknown_gir = round_row("nogir", "2026-04-02", [hole(n, 4, gir=None) for n in range(1, 19)])
        rows = [
            # label, rounds, (total, eighteen, nine, average18, holesWithPutts, zeroPutts, girRecorded, girPct)
            ("full_18", [low_round()], (1, 1, 0, 73.0, 17, 1, 17, 94.1)),  # GIR 16/17 = 94.12%
            ("nine_only", [nine_round()], (1, 0, 1, None, 9, 0, 0, None)),  # no 18-hole average from a nine
            ("unknown_putts", [unknown_putts], (1, 1, 0, 72.0, 0, 0, 18, 100.0)),  # 18 pars, putts unknown
            ("unknown_gir", [unknown_gir], (1, 1, 0, 72.0, 18, 0, 0, None)),  # GIR cannot be determined
            ("no_rounds", [], (0, 0, 0, None, 0, 0, 0, None)),
        ]
        for label, rounds, expected in rows:
            with self.subTest(case=label):
                self.serve(history(rounds))
                stats = self.get("/api/v2/history/stats")
                summary, putting, approach = stats["summary"], stats["scoring"]["putting"], phase(stats, "Approach")
                self.assertEqual((summary["totalRounds"], summary["eighteenHoleRounds"], summary["nineHoleRounds"],
                                  summary["average18"], putting["holesWithPutts"], putting["zeroPutts"],
                                  approach["girRecorded"], approach["girPct"]), expected)
                if not putting["holesWithPutts"]:
                    self.assertIsNone(putting["averagePutts"])  # unknown is "no value", never 0.0
                overview = self.get("/api/v2/history/overview")
                self.assertEqual(overview["metrics"]["average18"], expected[3])
                self.assertEqual(overview["emptyState"] is not None, label == "no_rounds")

    def test_recent_windows_at_boundaries(self):
        """S-15: recent-10 and recent-20 averages and the windowed stats use exactly the newest N rounds."""
        # Newest round scores 80 and each older one 1 more, so the newest k rounds average 80 + (k-1)/2.
        rows = [
            # rounds, recent10Average (k=min(n,10)), recent20Average (k=min(n,20))
            (0, None, None),
            (1, 80.0, 80.0),
            (9, 84.0, 84.0),    # 80 + 8/2
            (10, 84.5, 84.5),   # 80 + 9/2
            (11, 84.5, 85.0),   # recent-10 still 10 rounds; recent-20 80 + 10/2
            (19, 84.5, 89.0),   # 80 + 18/2
            (20, 84.5, 89.5),   # 80 + 19/2
            (21, 84.5, 89.5),   # recent-20 still 20 rounds
        ]
        for count, recent10, recent20 in rows:
            with self.subTest(rounds=count):
                self.serve(ladder_history(count))
                metrics = self.get("/api/v2/history/overview")["metrics"]
                self.assertEqual((metrics["recent10Average"], metrics["recent20Average"]), (recent10, recent20))
                for window, size, average in (("last10", 10, recent10), ("last20", 20, recent20)):
                    with self.subTest(window=window):
                        summary = self.get("/api/v2/history/stats", window=window)["summary"]
                        # Same newest rounds as home: the count and the average both match the row.
                        self.assertEqual((summary["totalRounds"], summary["average18"]), (min(count, size), average))

    def test_mobile_stats_window_matches_full_stats(self):
        """S-15: the phone stats payload reports the same windowed counts as the full stats page."""
        self.serve(ladder_history(12))
        for window, expected_rounds in (("all", 12), ("last10", 10), ("last20", 12)):  # 12 rounds available
            with self.subTest(window=window):
                full = self.get("/api/v2/history/stats", window=window)["summary"]
                mobile = self.get("/api/v2/history/stats/mobile", window=window)
                self.assertEqual(full["totalRounds"], expected_rounds)
                self.assertEqual(mobile["summary"]["totalRounds"], expected_rounds)
                self.assertEqual(mobile["summary"]["average18"], full["average18"])


class Overview(HistoryRouteCase):
    def test_home_stats_drilldown_same_rounds(self):
        """S-16 [main]: a score band on home or stats drills down to exactly the rounds it counted."""
        self.serve(mixed_history())
        overview = self.get("/api/v2/history/overview")
        stats = self.get("/api/v2/history/stats")
        families = {row["label"]: row["roundRefs"] for row in overview["distribution"]["families"]}
        bands = {row["label"]: row["roundRefs"] for row in stats["scoring"]["scoreBands"]}
        # low18 (73) is a 70s round, high18 (90) a 90s round; the nine belongs to no 18-hole band.
        expected = {"70s": ["low18"], "80s": [], "90s": ["high18"], "100+": []}
        self.assertEqual(families, expected)
        self.assertEqual(bands, expected)
        for ref, score in (("low18", 73), ("high18", 90)):
            with self.subTest(ref=ref):
                drill = self.get(f"/api/v2/history/drilldown/{ref}")
                self.assertEqual((drill["refType"], drill["found"], drill["round"]["id"], drill["round"]["score"]),
                                 ("round", True, ref, score))
                self.assertEqual(drill["relatedRefs"]["roundRefs"], [ref])

    def test_round_list_filters_and_groups_by_month(self):
        """S-16: the round list searches, filters by score band and period, and groups by month."""
        self.serve(mixed_history())
        rows = [
            ({}, ["low18", "high18", "nine"]),          # newest first
            ({"search": "Bravo"}, ["nine"]),            # course name match
            ({"scoreBand": "90s"}, ["high18"]),
            ({"scoreBand": "70s"}, ["low18"]),
            ({"period": "2026-02"}, ["high18"]),
            ({"period": "2026-Q1"}, ["low18", "high18", "nine"]),  # Jan-Mar
            ({"period": "2025"}, []),
        ]
        for params, expected in rows:
            with self.subTest(params=params):
                body = self.get("/api/v2/history/rounds", **params)
                ids = [card["id"] for group in body["groups"] for card in group["rounds"]]
                self.assertEqual(ids, expected)
                self.assertEqual(body["total"], len(expected))
        months = [group["key"] for group in self.get("/api/v2/history/rounds")["groups"]]
        self.assertEqual(months, ["2026-03", "2026-02", "2026-01"])

    def test_round_list_rejects_unknown_filters(self):
        """S-16: an unknown score band or malformed period is refused instead of silently matching everything."""
        self.serve(mixed_history())
        for params in ({"scoreBand": "60s"}, {"period": "2026-Q5"}, {"period": "March"}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/api/v2/history/rounds", params=params).status_code, 422)


def gps_shot(rid, number, order, club, lat):
    # Two GPS shots per hole: tee shot then approach, walking north along one longitude.
    return {"roundId": rid, "hole": number, "order": order, "clubName": club, "club": club,
            "distance": 200 if order == 1 else 120, "surface": "fairway" if order == 1 else "green",
            "start": {"lat": lat, "lon": 116.5, "lie": "Tee" if order == 1 else "Fairway"},
            "end": {"lat": lat + 0.0018, "lon": 116.5}}


SHOT_HOLES = (1, 9, 10, 18)


def review_history():
    # One 18-hole round on course 222 (2026-06-01). Hole 10's score was never entered and hole 9's
    # putts are unknown; GPS shots exist on holes 1, 9, 10 and 18 only.
    holes = [hole(n, 4) for n in range(1, 19)]
    holes[9 - 1] = hole(9, 4, putts=None)
    holes[10 - 1] = hole(10, None, putts=None, gir=None)
    row = round_row("rev", "2026-06-01", holes, gid=222, has_shots=True)
    shots = [gps_shot("rev", number, order, club, 40.0 + number * 0.01)
             for number in SHOT_HOLES for order, club in ((1, "Driver"), (2, "8I"))]
    return history([row], shots)


class RoundReviewTests(HistoryRouteCase):
    def test_round_detail_and_shotmaps_cover_first_turn_and_last_hole(self):
        """S-17 [main]: a round review shows every hole's card and its own GPS shots, and missing values stay empty."""
        self.serve(review_history())
        detail = self.get("/api/v2/history/rounds/rev")
        self.assertTrue(detail["found"])
        card = {row["hole"]: row for row in detail["scorecard"]}
        self.assertEqual(sorted(card), list(range(1, 19)))
        self.assertIsNone(card[10]["score"])   # never entered: empty, not 0
        self.assertIsNone(card[9]["putts"])    # unknown putts: empty, not 0
        self.assertEqual((card[1]["score"], card[1]["par"], card[1]["putts"]), (4, 4, 2))
        self.assertEqual(card[1]["holeRef"], "rev:1")

        rows = [
            # hole, par, number of GPS shots
            (1, 4, 2),
            (9, 4, 2),
            (10, 4, 2),
            (18, 4, 2),
            (19, None, 0),  # beyond an 18-hole card: nothing invented
        ]
        for number, par, shot_count in rows:
            with self.subTest(hole=number):
                shotmap = self.get(f"/api/v2/history/rounds/rev/holes/{number}/shotmap", includeImage="false")
                self.assertEqual((shotmap["hole"], shotmap["par"], len(shotmap["shots"])), (number, par, shot_count))
                self.assertEqual([shot["club"] for shot in shotmap["shots"]], ["Driver", "8I"][:shot_count])
                self.assertTrue(all(shot["gpsAvailable"] for shot in shotmap["shots"]))
                if not shot_count:
                    self.assertTrue(shotmap["missingData"])

    def test_course_hole_history_lists_shots_inside_the_day_window(self):
        """S-17: a course hole's history returns this player's shots on that physical hole within the chosen days."""
        self.serve(review_history())
        rows = [
            # hole, days, rounds, shots  (today is 2026-11-10; the round was played 2026-06-01, 162 days ago)
            (1, 730, 1, 2),
            (9, 730, 1, 2),
            (10, 730, 1, 2),
            (18, 730, 1, 2),
            (19, 730, 0, 0),   # no 19th hole on this course
            (1, 162, 1, 2),    # window starts exactly on the round day
            (1, 161, 0, 0),    # window starts the day after
        ]
        for number, days, rounds, shots in rows:
            with self.subTest(hole=number, days=days):
                body = self.get(f"/api/v2/history/courses/222/holes/{number}/shots", days=days)
                self.assertEqual((body["roundCount"], len(body["shots"])), (rounds, shots))
                self.assertEqual({shot["roundHole"] for shot in body["shots"]}, {number} if shots else set())
        self.assertEqual(self.client.get("/api/v2/history/courses/222/holes/37/shots").status_code, 422)

    def test_round_card_strip_marks_missing_holes(self):
        """S-17: the round card's hole strip marks a hole without a score as missing instead of scoring it."""
        self.serve(review_history())
        card = self.get("/api/v2/history/overview")["recentRounds"][0]
        strip = {cell["hole"]: cell for cell in card["scoreStrip"]}
        self.assertEqual((strip[10]["score"], strip[10]["className"]), (None, "missing"))
        self.assertEqual((strip[1]["score"], strip[1]["par"], strip[1]["toPar"]), (4, 4, 0))
        self.assertEqual(self.client.get("/api/v2/history/rounds/nope").json()["found"], False)
