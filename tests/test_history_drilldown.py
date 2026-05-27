from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.annotations import add_annotation
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


def provenance_drilldown_data() -> HistoryData:
    round_row = {
        "id": "merged_710001_710002",
        "ids": [710001, 710002],
        "date": "2026-05-25",
        "course": "Provenance Course",
        "courseKey": "provenance_course",
        "holesCompleted": 18,
        "strokes": 83,
        "par": 72,
        "holes": [{"number": 10, "strokes": 5, "par": 4, "putts": 2}],
        "hasShots": True,
        "provenance": {
            "sourceConnector": "garmin_cn_web_session",
            "snapshotId": "snap_provenance",
            "sourceRecordType": "scorecard_merge",
            "sourceRecordIds": ["710001", "710002"],
            "sourceFiles": ["data/scorecards/710001.json", "data/scorecards/710002.json"],
            "sourceRefs": [
                "garmin_cn_web_session:snap_provenance:scorecard:710001",
                "garmin_cn_web_session:snap_provenance:scorecard:710002",
            ],
            "fieldRefs": {"mergeRule": "same_day_two_9_hole_halves"},
            "confidence": "high",
            "status": "normalized",
        },
    }
    shot = {
        "id": "back-shot",
        "roundId": "merged_710001_710002",
        "scorecardId": 710002,
        "hole": 10,
        "club": "8I",
        "distance": 142,
        "surface": "green",
        "provenance": {
            "sourceConnector": "garmin_cn_web_session",
            "snapshotId": "snap_provenance",
            "sourceRecordType": "shot",
            "sourceRecordId": "back-shot",
            "parentRecordId": "710002",
            "sourceFiles": ["data/shots/710002.json"],
            "sourceRefs": ["garmin_cn_web_session:snap_provenance:shot:710002:back-shot"],
            "fieldRefs": {"meters": "holeShots[].shots[].meters"},
            "confidence": "high",
            "status": "normalized",
        },
    }
    return HistoryData(raw_rounds=[], rounds=[round_row], shots=[shot])


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

    def test_resolved_ref_includes_manual_annotations_and_corrections(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = add_annotation(
                "shot",
                "900001:1:1",
                "shot_note",
                {"text": "ball was above feet"},
                root=root,
            )
            correction = add_annotation(
                "shot",
                "900001:1:1",
                "club_correction",
                {"from": "8I", "to": "7I", "note": "watch picked wrong club"},
                root=root,
            )

            detail = resolve_history_ref(fixture_history_data(), "900001:1:1", annotations_root=root)

        self.assertEqual([row["id"] for row in detail["annotations"]], [note["id"], correction["id"]])
        self.assertEqual([row["id"] for row in detail["corrections"]], [correction["id"]])
        self.assertEqual(detail["annotations"][0]["payload"]["text"], "ball was above feet")
        self.assertEqual(detail["corrections"][0]["payload"]["to"], "7I")

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

    def test_drilldown_index_lists_normalized_provenance_refs(self) -> None:
        index = build_drilldown_index(provenance_drilldown_data())

        self.assertIn("garmin_cn_web_session:snap_provenance:scorecard:710002", index["sourceRefs"])
        self.assertIn("garmin_cn_web_session:snap_provenance:shot:710002:back-shot", index["sourceRefs"])

    def test_resolves_normalized_scorecard_provenance_ref_to_merged_round(self) -> None:
        detail = resolve_history_ref(
            provenance_drilldown_data(),
            "garmin_cn_web_session:snap_provenance:scorecard:710002",
        )

        self.assertTrue(detail["found"])
        self.assertEqual(detail["refType"], "round")
        self.assertEqual(detail["ref"], "garmin_cn_web_session:snap_provenance:scorecard:710002")
        self.assertEqual(detail["round"]["id"], "merged_710001_710002")
        self.assertEqual(detail["sourceFields"]["ids"], [710001, 710002])
        self.assertEqual(detail["sourceFields"]["provenance"]["sourceRecordType"], "scorecard_merge")
        self.assertIn("merged_710001_710002:10", detail["relatedRefs"]["holeRefs"])

    def test_resolves_normalized_shot_provenance_ref_to_shot_context(self) -> None:
        detail = resolve_history_ref(
            provenance_drilldown_data(),
            "garmin_cn_web_session:snap_provenance:shot:710002:back-shot",
        )

        self.assertTrue(detail["found"])
        self.assertEqual(detail["refType"], "shot")
        self.assertEqual(detail["round"]["id"], "merged_710001_710002")
        self.assertEqual(detail["hole"]["number"], 10)
        self.assertEqual(detail["shot"]["club"], "8I")
        self.assertEqual(detail["sourceFields"]["provenance"]["sourceRecordId"], "back-shot")
        self.assertEqual(detail["sourceFields"]["scorecardId"], 710002)

    def test_missing_ref_degrades_with_missing_data(self) -> None:
        detail = resolve_history_ref(fixture_history_data(), "900404:9:1")

        self.assertFalse(detail["found"])
        self.assertEqual(detail["ref"], "900404:9:1")
        self.assertEqual(detail["refType"], "shot")
        self.assertEqual(detail["missingData"][0]["label"], "source_ref")


if __name__ == "__main__":
    unittest.main()
