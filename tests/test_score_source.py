"""B0 per-hole score provenance: canonical sources, round state, ingest and statistics skipping."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.history import history, history_stats, stats_cache
from ai_caddie.history.history import HistoryData
from ai_caddie.rounds import round_ingest
from ai_caddie.rounds.score_source import (
    DEFAULT,
    MANUAL_EDIT,
    PHONE_SHOTS,
    WATCH_DETECTED,
    fold_score_source,
    normalize_score_source,
)
from server_v2.main import app


class ScoreSourceRulesTest(unittest.TestCase):
    def test_canonical_values_are_kept_and_legacy_values_count_as_person_entered(self) -> None:
        for value in (WATCH_DETECTED, PHONE_SHOTS, DEFAULT, MANUAL_EDIT):
            self.assertEqual(normalize_score_source(value), value)
        self.assertEqual(normalize_score_source(" Default "), DEFAULT)
        for legacy in ("ios_score_confirmation", "apple_watch", None, "", 7, "something_new"):
            self.assertEqual(normalize_score_source(legacy), MANUAL_EDIT)

    def test_default_only_while_every_event_is_default(self) -> None:
        self.assertEqual(fold_score_source(fold_score_source(None, "default"), "default"), DEFAULT)
        self.assertEqual(fold_score_source(fold_score_source(None, "default"), "manual_edit"), MANUAL_EDIT)
        # An edited hole stays edited even if a later client event says default.
        self.assertEqual(fold_score_source(MANUAL_EDIT, "default"), MANUAL_EDIT)
        self.assertEqual(fold_score_source(WATCH_DETECTED, "default"), WATCH_DETECTED)
        self.assertEqual(fold_score_source(WATCH_DETECTED, "manual_edit"), MANUAL_EDIT)


def _event(eid: str, hole: int, kind: str, payload: dict) -> dict:
    return {
        "schema": "ai-caddie-live-round-event-v1",
        "eventId": eid,
        "roundId": "src-1",
        "clientId": "ios-phone",
        "timestamp": "2026-09-28T00:00:00Z",
        "hole": hole,
        "kind": kind,
        "payload": payload,
    }


class RoundStateScoreSourceTest(unittest.TestCase):
    def test_round_state_exposes_per_hole_score_source(self) -> None:
        client = TestClient(app)
        with tempfile.TemporaryDirectory() as tmp, patch("server_v2.mobile.MOBILE_ROOT", Path(tmp)):
            response = client.post(
                "/api/v2/mobile/rounds/src-1/events",
                headers={"Idempotency-Key": "src-b1"},
                json={"roundId": "src-1", "events": [
                    _event("s1", 1, "score", {"strokes": 4, "source": "default"}),
                    _event("s2", 1, "putt", {"putts": 2, "source": "default"}),
                    _event("s3", 2, "score", {"strokes": 5, "source": "default"}),
                    _event("s4", 2, "putt", {"putts": 1, "source": "manual_edit"}),
                    _event("s5", 3, "score", {"strokes": 4, "source": "ios_score_confirmation"}),
                    _event("s6", 4, "score", {"strokes": 3}),
                ]},
            )
            self.assertEqual(response.status_code, 200, response.text)
            state = client.get("/api/v2/mobile/rounds/src-1/state").json()
        holes = {hole["hole"]: hole for hole in state["holes"]}
        self.assertEqual(holes[1]["scoreSource"], DEFAULT)
        self.assertEqual(holes[2]["scoreSource"], MANUAL_EDIT)
        self.assertEqual(holes[3]["scoreSource"], MANUAL_EDIT)  # legacy confirmation sheet
        self.assertEqual(holes[4]["scoreSource"], MANUAL_EDIT)  # no source at all


class IngestAndStatsScoreSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patch = mock.patch.object(history, "ROOT", self.root)
        self._patch.start()
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()

    def _meta(self) -> dict:
        return {"courseGlobalId": 41825, "courseName": "Source Nine", "teeTime": "2026-09-28T08:00:00+08:00",
                "teeBox": "blue", "holePars": "444"}

    def test_scorecard_keeps_source_and_round_putts_exclude_default_holes(self) -> None:
        events = [
            {"hole": 1, "kind": "score", "payload": {"strokes": 4, "source": "default"}},
            {"hole": 1, "kind": "putt", "payload": {"putts": 2, "source": "default"}},
            {"hole": 2, "kind": "score", "payload": {"strokes": 5, "source": "manual_edit"}},
            {"hole": 2, "kind": "putt", "payload": {"putts": 3, "source": "manual_edit"}},
            {"hole": 3, "kind": "score", "payload": {"strokes": 4}},
            {"hole": 3, "kind": "putt", "payload": {"putts": 1}},
        ]
        round_ingest.ingest_round("p_src", events, self._meta(), idempotency_key="src-1", root=self.root)
        row = history.load_raw_rounds(player_id="p_src")[0]
        card = next(iter((self.root / "data" / "players" / "p_src" / "scorecards").glob("*.json")))
        detail = history.read_json(card)["scorecardDetails"][0]
        holes = {hole["number"]: hole for hole in detail["scorecard"]["holes"]}
        self.assertEqual(holes[1]["scoreSource"], DEFAULT)
        self.assertEqual(holes[2]["scoreSource"], MANUAL_EDIT)
        self.assertEqual(holes[3]["scoreSource"], MANUAL_EDIT)
        self.assertIsNotNone(row)
        self.assertEqual(detail["scorecardStats"]["round"]["putts"], 4)  # 3 + 1; the default hole's 2 were never entered

    def test_round_putts_are_absent_when_every_hole_is_default(self) -> None:
        events = [
            {"hole": 1, "kind": "score", "payload": {"strokes": 4, "source": "default"}},
            {"hole": 1, "kind": "putt", "payload": {"putts": 2, "source": "default"}},
        ]
        round_ingest.ingest_round("p_src2", events, self._meta(), idempotency_key="src-2", root=self.root)
        card = next(iter((self.root / "data" / "players" / "p_src2" / "scorecards").glob("*.json")))
        self.assertIsNone(history.read_json(card)["scorecardDetails"][0]["scorecardStats"]["round"]["putts"])

    def test_statistics_skip_putts_and_gir_of_unedited_default_holes(self) -> None:
        holes = [
            # Default hole: 2 putts and GIR only echo the client's defaults.
            {"number": 1, "par": 4, "strokes": 4, "putts": 2, "gir": True, "scoreSource": "default"},
            {"number": 2, "par": 4, "strokes": 5, "putts": 3, "gir": False, "scoreSource": "manual_edit"},
            # Garmin / legacy holes have no scoreSource and keep counting.
            {"number": 3, "par": 4, "strokes": 4, "putts": 1, "gir": False},
        ]
        rounds = [{"id": "src-round", "date": "2026-09-28", "course": "Source Nine", "courseKey": "source_nine",
                   "holesCompleted": 3, "strokes": 13, "par": 12, "holes": holes, "hasShots": False}]
        data = HistoryData(raw_rounds=[{"id": "src-round", "hasShots": False}], rounds=rounds, shots=[])
        scoring = history_stats._scoring(data)
        putting = scoring["putting"]
        self.assertEqual(putting["holesWithPutts"], 2)
        self.assertEqual(putting["totalPutts"], 4)
        self.assertEqual(putting["threePutts"], 1)
        approach = next(row for row in scoring["phaseStats"] if row["phase"] == "Approach")
        self.assertEqual(approach["girRecorded"], 2)
        self.assertEqual(approach["gir"], 0)
        self.assertEqual(scoring["approachMiss"]["recorded"], 2)


if __name__ == "__main__":
    unittest.main()
