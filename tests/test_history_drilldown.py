from __future__ import annotations

import unittest

from ai_caddie.fixtures import fixture_history_data
from ai_caddie.history import HistoryData
from ai_caddie.history_drilldown import build_drilldown_index, resolve_history_ref


def raw_garmin_drilldown_data() -> HistoryData:
    round_row = {
        "id": "700001",
        "date": "2026-05-25",
        "course": "Raw Shape Course",
        "courseKey": "raw_shape",
        "holesCompleted": 18,
        "strokes": 80,
        "par": 72,
        "holes": [{"number": 1, "strokes": 4, "par": 4, "putts": 2, "fairway": "hit"}],
        "hasShots": True,
    }
    shots = [
        {
            "id": 11,
            "scorecardId": 700001,
            "hole": 1,
            "clubName": "8I",
            "meters": 141.8,
            "endLie": "green",
        }
    ]
    return HistoryData(raw_rounds=[{"id": "700001", "hasShots": True}], rounds=[round_row], shots=shots)


class HistoryDrilldownTests(unittest.TestCase):
    def test_drilldown_index_lists_round_hole_and_shot_refs(self) -> None:
        index = build_drilldown_index(fixture_history_data())

        self.assertEqual(index["roundRefs"], ["900001", "900002", "900003"])
        self.assertIn("900001:1", index["holeRefs"])
        self.assertIn("900001:1:0", index["shotRefs"])
        self.assertIn("900002:5:4", index["shotRefs"])

    def test_resolves_round_ref_with_source_fields_and_related_holes(self) -> None:
        detail = resolve_history_ref(fixture_history_data(), "900001")

        self.assertTrue(detail["found"])
        self.assertEqual(detail["schema"], "ai-caddie-history-drilldown-v1")
        self.assertEqual(detail["ref"], "900001")
        self.assertEqual(detail["refType"], "round")
        self.assertEqual(detail["title"], "Black Knight B/C - 2026-05-18")
        self.assertEqual(detail["round"]["id"], "900001")
        self.assertEqual(detail["round"]["score"], 77)
        self.assertIn("strokes", detail["sourceFields"])
        self.assertIn("900001:1", detail["relatedRefs"]["holeRefs"])
        self.assertIn("900001:1:0", detail["relatedRefs"]["shotRefs"])

    def test_resolves_hole_ref_with_score_context_and_shots(self) -> None:
        detail = resolve_history_ref(fixture_history_data(), "900001:1")

        self.assertTrue(detail["found"])
        self.assertEqual(detail["refType"], "hole")
        self.assertEqual(detail["round"]["id"], "900001")
        self.assertEqual(detail["hole"]["number"], 1)
        self.assertEqual(detail["hole"]["par"], 4)
        self.assertEqual(detail["hole"]["strokes"], 4)
        self.assertEqual(detail["hole"]["toPar"], 0)
        self.assertEqual(detail["relatedRefs"]["shotRefs"], ["900001:1:0", "900001:1:1"])

    def test_resolves_shot_ref_with_round_and_hole_context(self) -> None:
        detail = resolve_history_ref(fixture_history_data(), "900001:1:1")

        self.assertTrue(detail["found"])
        self.assertEqual(detail["refType"], "shot")
        self.assertEqual(detail["round"]["id"], "900001")
        self.assertEqual(detail["hole"]["number"], 1)
        self.assertEqual(detail["shot"]["club"], "8I")
        self.assertEqual(detail["shot"]["distance"], 142)
        self.assertEqual(detail["shot"]["surface"], "green")
        self.assertEqual(detail["sourceFields"]["globalShotIndex"], 1)

    def test_resolves_local_raw_garmin_shot_shape(self) -> None:
        data = raw_garmin_drilldown_data()

        index = build_drilldown_index(data)
        detail = resolve_history_ref(data, "700001:1:0")

        self.assertEqual(index["shotRefs"], ["700001:1:0"])
        self.assertTrue(detail["found"])
        self.assertEqual(detail["round"]["id"], "700001")
        self.assertEqual(detail["shot"]["club"], "8I")
        self.assertEqual(detail["shot"]["distance"], 141.8)
        self.assertEqual(detail["shot"]["surface"], "green")
        self.assertEqual(detail["sourceFields"]["scorecardId"], 700001)
        self.assertEqual(detail["sourceFields"]["meters"], 141.8)
        self.assertEqual(detail["sourceFields"]["endLie"], "green")

    def test_missing_ref_degrades_with_missing_data(self) -> None:
        detail = resolve_history_ref(fixture_history_data(), "900404:9:1")

        self.assertFalse(detail["found"])
        self.assertEqual(detail["ref"], "900404:9:1")
        self.assertEqual(detail["refType"], "shot")
        self.assertEqual(detail["missingData"][0]["label"], "source_ref")


if __name__ == "__main__":
    unittest.main()
