from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.annotations import add_annotation
from ai_caddie.history import HistoryData
from ai_caddie.history_round_detail import build_history_round_detail
from server_v2.main import app


def round_detail_data() -> HistoryData:
    round_row = {
        "id": "700001",
        "ids": ["alias-700001"],
        "date": "2026-05-25",
        "course": "Scorecard Links",
        "courseKey": "scorecard_links",
        "courseId": 31795,
        "holesCompleted": 4,
        "strokes": 17,
        "par": 16,
        "holePars": "4444",
        "holes": [
            {"number": 1, "strokes": 4, "par": 4, "putts": 2, "gir": True, "fairway": "hit"},
            {"number": 2, "strokes": 5, "par": 4, "putts": 2, "gir": False, "fairway": "right"},
            {"number": 3, "strokes": 3, "par": 4, "putts": 1, "gir": True, "fairway": "hit"},
            {"number": 4, "strokes": 5, "par": 4, "putts": 3, "gir": False, "fairway": "left"},
        ],
        "hasShots": True,
        "shotStatus": "ready",
        "provenance": {"sourceRefs": ["garmin:scorecard:700001"], "confidence": "high"},
    }
    shots = [
        {"roundId": "700001", "hole": 1, "club": "1D", "distance": 248, "surface": "fairway"},
        {"roundId": "700001", "hole": 1, "club": "8I", "distance": 142, "surface": "green"},
        {"roundId": "700001", "hole": 2, "club": "1D", "distance": 235, "surface": "rough"},
        {"roundId": "700001", "hole": 2, "club": "54", "distance": 42, "surface": "green"},
        {
            "roundId": "700001",
            "hole": 4,
            "club": "Putter",
            "distance": 8,
            "surface": "hole",
            "type": "PUTT",
            "provenance": {"sourceRefs": ["garmin:shot:700001:4:putt"]},
        },
    ]
    return HistoryData(raw_rounds=[{"id": "700001", "hasShots": True}], rounds=[round_row], shots=shots)


class ServerV2HistoryRoundDetailTests(unittest.TestCase):
    def test_round_detail_is_scorecard_first_and_source_linked(self) -> None:
        payload = build_history_round_detail(round_detail_data(), "700001")

        self.assertEqual(payload["schema"], "ai-caddie-history-round-detail-v1")
        self.assertTrue(payload["found"])
        self.assertEqual(payload["roundRef"], "700001")
        self.assertEqual(payload["round"]["courseName"], "Scorecard Links")
        self.assertEqual(payload["round"]["toPar"], 1)
        self.assertEqual(payload["round"]["coverage"]["shots"], "ready")
        self.assertEqual([cell["hole"] for cell in payload["scorecard"]], [1, 2, 3, 4])
        self.assertEqual(payload["scorecard"][0]["className"], "par")
        self.assertEqual(payload["scorecard"][1]["className"], "bogey")
        self.assertEqual(payload["scorecard"][2]["className"], "birdie")
        self.assertEqual(payload["scorecard"][3]["putts"], 3)
        self.assertEqual(payload["scorecard"][1]["holeRef"], "700001:2")
        self.assertEqual(payload["scorecard"][1]["shotRefs"], ["700001:2:2", "700001:2:3"])
        self.assertIn("700001:2", payload["relatedRefs"]["holeRefs"])
        self.assertIn("700001:4:4", payload["relatedRefs"]["shotRefs"])
        self.assertIn("garmin:scorecard:700001", payload["relatedRefs"]["sourceRefs"])

    def test_round_detail_summarizes_phase_coverage(self) -> None:
        payload = build_history_round_detail(round_detail_data(), "700001")
        phases = {row["phase"]: row for row in payload["phaseSummary"]}

        self.assertEqual(phases["Tee"]["metrics"]["fairwaysHit"], 2)
        self.assertEqual(phases["Approach"]["metrics"]["gir"], 2)
        self.assertEqual(phases["Short Game"]["metrics"]["shots"], 1)
        self.assertEqual(phases["Putting"]["metrics"]["totalPutts"], 8)
        self.assertEqual(phases["Penalty / Damage"]["metrics"]["doubleOrWorseHoles"], 0)

    def test_round_detail_accepts_round_alias_and_attaches_round_annotations(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = add_annotation("round", "700001", "round_note", {"text": "Wind into the last four holes"}, root=root)
            correction = add_annotation("round", "alias-700001", "score_correction", {"from": 18, "to": 17}, root=root)

            payload = build_history_round_detail(round_detail_data(), "alias-700001", annotations_root=root)

        self.assertEqual(payload["roundRef"], "700001")
        self.assertEqual([row["id"] for row in payload["annotations"]], [note["id"], correction["id"]])
        self.assertEqual([row["id"] for row in payload["corrections"]], [correction["id"]])

    def test_missing_round_detail_degrades_cleanly(self) -> None:
        payload = build_history_round_detail(round_detail_data(), "missing-round")

        self.assertEqual(payload["schema"], "ai-caddie-history-round-detail-v1")
        self.assertFalse(payload["found"])
        self.assertEqual(payload["round"], None)
        self.assertEqual(payload["scorecard"], [])
        self.assertEqual(payload["relatedRefs"], {"roundRefs": [], "holeRefs": [], "shotRefs": [], "sourceRefs": []})
        self.assertEqual(payload["missingData"][0]["label"], "round_ref")

    def test_round_detail_endpoint_uses_public_schema_alias(self) -> None:
        with patch(
            "server_v2.history_round_detail.load_history_data_for_mode",
            return_value=(round_detail_data(), "fixture"),
        ):
            response = TestClient(app).get("/api/v2/history/rounds/700001")
            payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schema"], "ai-caddie-history-round-detail-v1")
        self.assertNotIn("schema_", payload)
        self.assertEqual(payload["roundRef"], "700001")


if __name__ == "__main__":
    unittest.main()
