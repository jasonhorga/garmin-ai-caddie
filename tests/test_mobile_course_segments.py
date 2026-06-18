"""Course-segment enrichment for build_mobile_course_options: list each playable nine
(黑骑士 A/B/C) under its venue with the CourseView loop label + true 9/18 hole count.

This is the fix for "选完黑骑士 ABC 怎么算" — the round-derived name is a played combo
('~ C/A'); CourseView gives the clean per-gid loop name ('~ C') + true hole count. The
CourseView resolver is INJECTED here so the test is hermetic (no network / no data dir).
"""
from __future__ import annotations

import unittest

from ai_caddie.history import HistoryData
from ai_caddie.mobile_live import _merge_nines, build_mobile_course_options


def _nine_package(label: str, ready: int) -> dict:
    return {
        "course": {"globalId": 1, "name": f"黑骑士 ~ {label}", "teeBox": "blue"},
        "holes": [
            {"number": n, "par": 4, "geometryCoverage": "ready" if n <= ready else "missing"}
            for n in range(1, 10)
        ],
        "caddieContextSeeds": [{"hole": n, "shotTypes": ["tee"]} for n in range(1, 10)],
        "coursePrep": {"schema": "x", "holes": [{"hole": n, "par": 4} for n in range(1, 10)]},
        "geometryCoverage": {"state": "partial", "readyHoles": ready, "totalHoles": 9},
        "weatherSnapshot": {"label": label},
        "nine": "all",
    }


class CompositeNineMergeTests(unittest.TestCase):
    def test_merge_two_nines_renumbers_back_to_10_18(self) -> None:
        merged = _merge_nines(_nine_package("C", 9), _nine_package("A", 4))
        self.assertEqual([h["number"] for h in merged["holes"]], list(range(1, 19)))
        self.assertEqual([s["hole"] for s in merged["caddieContextSeeds"]], list(range(1, 19)))
        self.assertEqual([p["hole"] for p in merged["coursePrep"]["holes"]], list(range(1, 19)))

    def test_merge_combines_geometry_and_names_front_shared_sections(self) -> None:
        merged = _merge_nines(_nine_package("C", 9), _nine_package("A", 4))
        self.assertEqual(merged["geometryCoverage"], {"state": "partial", "readyHoles": 13, "totalHoles": 18})
        self.assertEqual(merged["course"]["name"], "黑骑士 ~ C/A")
        self.assertEqual(merged["weatherSnapshot"], {"label": "C"})  # shared section from the front loop
        self.assertEqual(merged["nine"], "all")


def _round(rid: str, gid: int, course: str) -> dict:
    return {
        "id": rid, "date": "2026-06-0" + rid[-1], "globalId": gid,
        "courseKey": f"gid_{gid}", "course": course, "courseName": course,
        "holesCompleted": 18, "strokes": 90, "par": 72, "holePars": "4" * 18,
        "holes": [{"number": h, "par": 4} for h in range(1, 19)],
    }


# Injected CourseView resolver: (clean name, hole count) per globalId — what inspect_release gives.
_FAKE_CV = {
    31794: ("The Players Club ~ A", 9),
    31795: ("The Players Club ~ B", 9),
    31796: ("The Players Club ~ C", 9),
    41825: ("Beijing Bayhood No 9 International Golf Club", 18),
}


def _resolver(gid: int, *, allow_fetch: bool = False):
    return _FAKE_CV.get(int(gid))


class MobileCourseSegmentTests(unittest.TestCase):
    def _options(self) -> dict[int, dict]:
        data = HistoryData(
            raw_rounds=[],
            rounds=[
                _round("r1", 31794, "北京天竺黑骑士球员俱乐部 ~ C/A"),
                _round("r2", 31795, "北京天竺黑骑士球员俱乐部 ~ A/B"),
                _round("r3", 31796, "北京天竺黑骑士球员俱乐部 ~ C/A"),
                _round("r4", 41825, "北京北湖九号国际高尔夫俱乐部"),
            ],
            shots=[],
        )
        resp = build_mobile_course_options(data, data_mode="played", segment_resolver=_resolver)
        return {c["globalId"]: c for c in resp["courses"]}

    def test_loops_get_courseview_label_and_nine_holes(self) -> None:
        opts = self._options()
        self.assertEqual(opts[31794]["segmentLabel"], "A")
        self.assertEqual(opts[31795]["segmentLabel"], "B")
        self.assertEqual(opts[31796]["segmentLabel"], "C")
        for gid in (31794, 31795, 31796):
            self.assertEqual(opts[gid]["segmentHoles"], 9)
            self.assertEqual(opts[gid]["venueName"], "北京天竺黑骑士球员俱乐部")

    def test_single_18_course_has_no_loop_label(self) -> None:
        opts = self._options()
        self.assertIsNone(opts[41825]["segmentLabel"])
        self.assertEqual(opts[41825]["segmentHoles"], 18)
        self.assertEqual(opts[41825]["venueName"], "北京北湖九号国际高尔夫俱乐部")

    def test_three_loops_group_under_one_venue(self) -> None:
        opts = self._options()
        loop_gids = sorted(g for g, c in opts.items() if c["venueName"] == "北京天竺黑骑士球员俱乐部")
        self.assertEqual(loop_gids, [31794, 31795, 31796])

    def test_course_options_carry_real_tee_colours(self) -> None:
        # Real tee colours come from Garmin CourseView (release field 6) — what Garmin's own
        # new-round tee picker shows. Injected here so the test is hermetic.
        fake_tees = {31794: ["Gold", "Blue", "White", "Red"], 41825: ["Black", "Blue", "White", "Red"]}
        data = HistoryData(
            raw_rounds=[],
            rounds=[
                _round("r1", 31794, "北京天竺黑骑士球员俱乐部 ~ A"),
                _round("r2", 41825, "北京北湖九号国际高尔夫俱乐部"),
            ],
            shots=[],
        )
        resp = build_mobile_course_options(
            data, data_mode="played", segment_resolver=_resolver,
            tee_resolver=lambda gid, **_: fake_tees.get(int(gid), []),
        )
        opts = {c["globalId"]: c for c in resp["courses"]}
        self.assertEqual(opts[31794]["tees"], ["Gold", "Blue", "White", "Red"])
        self.assertEqual(opts[41825]["tees"], ["Black", "Blue", "White", "Red"])

    def test_missing_courseview_falls_back_to_played_holes(self) -> None:
        # gid with no CourseView record → segmentLabel None, segmentHoles falls back to played count.
        data = HistoryData(
            raw_rounds=[],
            rounds=[_round("r1", 99999, "某未知球场")],
            shots=[],
        )
        resp = build_mobile_course_options(data, data_mode="played", segment_resolver=_resolver)
        course = resp["courses"][0]
        self.assertIsNone(course["segmentLabel"])
        self.assertEqual(course["segmentHoles"], course["holes"])
        self.assertEqual(course["venueName"], "某未知球场")


if __name__ == "__main__":
    unittest.main()
