from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.reports.annotations import add_annotation
from ai_caddie.caddie.decision import store_decision_audit
from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.history.history import HistoryData
from ai_caddie.history.history_drilldown import (
    _matching_weather_snapshots,
    build_drilldown_index,
    resolve_history_ref,
)
from ai_caddie.reports.reports import store_report
from ai_caddie.llm.weather_context import build_weather_snapshot, store_weather_snapshot


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


def split_nine_geometry_drilldown_data() -> HistoryData:
    round_row = {
        "id": "split-geometry",
        "date": "2026-05-26",
        "course": "Split Geometry Course",
        "courseKey": "split_geometry",
        "courseId": 111111,
        "frontNineGlobalCourseId": 111111,
        "backNineGlobalCourseId": 222222,
        "holesCompleted": 18,
        "strokes": 83,
        "par": 72,
        "holePars": "444444444555555555",
        "holes": [
            {"number": 1, "strokes": 4, "par": 4, "putts": 2},
            {"number": 10, "strokes": 5, "par": 5, "putts": 2},
        ],
        "hasShots": True,
    }
    return HistoryData(raw_rounds=[], rounds=[round_row], shots=[])


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

    def test_hole_drilldown_exposes_front_and_back_nine_geometry_targets(self) -> None:
        front = resolve_history_ref(split_nine_geometry_drilldown_data(), "split-geometry:1")
        back = resolve_history_ref(split_nine_geometry_drilldown_data(), "split-geometry:10")

        self.assertEqual(front["round"]["globalId"], 111111)
        self.assertEqual(front["round"]["frontNineGlobalCourseId"], 111111)
        self.assertEqual(front["round"]["backNineGlobalCourseId"], 222222)
        self.assertEqual(front["hole"]["globalId"], 111111)
        self.assertEqual(front["hole"]["localHole"], 1)
        self.assertEqual(front["sourceFields"]["globalId"], 111111)
        self.assertEqual(front["sourceFields"]["localHole"], 1)
        self.assertEqual(back["hole"]["globalId"], 222222)
        self.assertEqual(back["hole"]["localHole"], 1)
        self.assertEqual(back["sourceFields"]["globalId"], 222222)
        self.assertEqual(back["sourceFields"]["localHole"], 1)

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

    def test_resolved_hole_ref_includes_report_weather_audit_and_geometry_evidence(self) -> None:
        def ready_geometry(global_id: int, local_hole: int) -> dict[str, object]:
            return {
                "schema": "ai-caddie-geometry-evidence-v1",
                "globalId": global_id,
                "localHole": local_hole,
                "coverage": "ready",
                "hasHazards": True,
                "hasMeshes": True,
                "evidence": [{"label": "hazards", "ref": f"gid{global_id}_h{local_hole:02d}_hazards.json"}],
                "missingData": [],
            }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            correction = add_annotation(
                "hole",
                "900001:7",
                "score_correction",
                {"from": 6, "to": 5},
                root=root,
            )
            report = store_report(
                {
                    "schema": "ai-caddie-review-report-v1",
                    "kind": "hole",
                    "subjectId": "black_knight:7",
                    "provider": "static",
                    "model": "static",
                    "confidence": "medium",
                    "sourceRefs": ["900001:7"],
                    "factsUsed": [{"label": "hole score", "sourceRefs": ["900001:7"]}],
                    "missingData": [],
                    "unsupportedClaims": [],
                    "narrative": "Hole 7 was costly.",
                },
                kind="hole",
                subject_id="black_knight:7",
                root=root,
            )
            store_weather_snapshot(
                build_weather_snapshot(
                    round_id="900001",
                    hole=7,
                    captured_at="2026-05-25T09:00:00Z",
                    latitude=22.279,
                    longitude=114.162,
                    source="manual",
                    observed={"windSpeedMps": 6.0, "windDirectionDeg": 120},
                ),
                root=root,
            )
            audit = store_decision_audit(
                {
                    "decisionSourceRef": "900001:7",
                    "selectedOptionId": "stock",
                    "actualOptionId": "attack",
                    "actualShotRefs": ["900001:7:0"],
                    "evidenceRefs": ["900001:7"],
                    "classification": "strategy",
                },
                decision_id="decision-900001-7",
                root=root,
            )

            from unittest.mock import patch

            with patch("ai_caddie.history.history_drilldown.geometry_coverage_for_hole", side_effect=ready_geometry):
                detail = resolve_history_ref(
                    fixture_history_data(),
                    "900001:7",
                    annotations_root=root,
                    reports_root=root,
                    weather_root=root,
                    decision_audit_root=root,
                )

            serialized = str(detail)

        self.assertEqual([row["id"] for row in detail["corrections"]], [correction["id"]])
        self.assertEqual(detail["reports"][0]["id"], report["id"])
        self.assertEqual(detail["reports"][0]["subjectId"], "black_knight:7")
        self.assertEqual(detail["reports"][0]["sourceRefs"], ["900001:7"])
        self.assertEqual(detail["reports"][0]["factsUsedCount"], 1)
        self.assertEqual(detail["weatherSnapshots"][0]["roundId"], "900001")
        self.assertEqual(detail["weatherSnapshots"][0]["hole"], 7)
        self.assertEqual(detail["weatherSnapshots"][0]["windSpeedMps"], 6.0)
        self.assertEqual(detail["decisionAudits"][0]["id"], audit["id"])
        self.assertEqual(detail["decisionAudits"][0]["actualShotRefs"], ["900001:7:0"])
        self.assertEqual(detail["decisionAudits"][0]["evidenceRefs"], ["900001:7"])
        self.assertEqual(detail["geometryEvidence"][0]["coverage"], "ready")
        self.assertNotIn(str(root), serialized)

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


class DrilldownMissingRefEvidenceGuardTests(unittest.TestCase):
    def _seed_evidence(self, root: Path) -> None:
        add_annotation("round", "900001", "round_note", {"text": "owner note"}, root=root)
        store_report(
            {
                "schema": "ai-caddie-review-report-v1",
                "kind": "round",
                "subjectId": "900001",
                "provider": "static",
                "model": "static",
                "confidence": "medium",
                "sourceRefs": ["900001"],
                "factsUsed": [],
                "missingData": [],
                "unsupportedClaims": [],
                "narrative": "Round 900001 summary.",
            },
            kind="round",
            subject_id="900001",
            root=root,
        )
        store_decision_audit(
            {
                "decisionSourceRef": "900001",
                "selectedOptionId": "stock",
                "actualOptionId": "attack",
                "actualShotRefs": ["900001:7:0"],
                "evidenceRefs": ["900001"],
                "classification": "strategy",
            },
            decision_id="decision-900001",
            root=root,
        )
        store_weather_snapshot(
            build_weather_snapshot(
                round_id="900001",
                hole=7,
                captured_at="2026-05-25T09:00:00Z",
                latitude=22.279,
                longitude=114.162,
                source="manual",
                observed={"windSpeedMps": 6.0, "windDirectionDeg": 120},
            ),
            root=root,
        )

    def test_missing_ref_attaches_no_evidence_and_no_weather_dump(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_evidence(root)

            detail = resolve_history_ref(
                fixture_history_data(),
                "999999",
                annotations_root=root,
                reports_root=root,
                weather_root=root,
                decision_audit_root=root,
            )

        self.assertFalse(detail["found"])
        self.assertEqual(detail["weatherSnapshots"], [])
        self.assertEqual(detail["reports"], [])
        self.assertEqual(detail["decisionAudits"], [])
        self.assertEqual(detail["annotations"], [])
        self.assertEqual(detail["corrections"], [])

    def test_matching_weather_returns_empty_without_concrete_round_id(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_evidence(root)

            self.assertEqual(_matching_weather_snapshots({"refType": "round", "round": {}}, root), [])

    def test_found_round_still_attaches_its_weather_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_evidence(root)

            detail = resolve_history_ref(
                fixture_history_data(),
                "900001",
                annotations_root=root,
                reports_root=root,
                weather_root=root,
                decision_audit_root=root,
            )

        self.assertTrue(detail["found"])
        self.assertEqual(len(detail["weatherSnapshots"]), 1)
        self.assertEqual(detail["weatherSnapshots"][0]["roundId"], "900001")


if __name__ == "__main__":
    unittest.main()
