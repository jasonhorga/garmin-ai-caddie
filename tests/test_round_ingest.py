from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_caddie.history import history, stats_cache
from ai_caddie.rounds import round_ingest
from ai_caddie.core.data import semicircle_to_deg


def _events() -> list[dict]:
    """A small 2-hole manual round: hole 1 (two shots + 2 putts, score 4),
    hole 2 (one shot + penalty + 2 putts, score 5). 3 location events => 3 shots."""
    return [
        {"hole": 1, "kind": "club", "payload": {"clubName": "1D", "shotType": "tee", "lie": "TeeBox"}},
        {"hole": 1, "kind": "location", "payload": {"latitude": 47.7334, "longitude": 138.8915}},
        {"hole": 1, "kind": "club", "payload": {"clubName": "8I", "shotType": "approach", "lie": "Fairway"}},
        {"hole": 1, "kind": "location", "payload": {"latitude": 47.7349, "longitude": 138.8930,
                                                    "targetLatitude": 47.7351, "targetLongitude": 138.8931}},
        {"hole": 1, "kind": "putt", "payload": {"putts": 2}},
        {"hole": 1, "kind": "score", "payload": {"strokes": 4, "fairway": "left"}},
        {"hole": 2, "kind": "club", "payload": {"clubName": "7I", "shotType": "tee", "lie": "TeeBox"}},
        {"hole": 2, "kind": "location", "payload": {"latitude": 47.7400, "longitude": 138.9000}},
        {"hole": 2, "kind": "penalty", "payload": {"penalties": 1}},
        {"hole": 2, "kind": "score", "payload": {"strokes": 5}},
        {"hole": 2, "kind": "putt", "payload": {"putts": 2}},
    ]


def _meta() -> dict:
    return {
        "courseGlobalId": 41825,
        "courseName": "Bay Practice Nine",
        "teeTime": "2026-06-13T08:00:00+08:00",
        "teeBox": "blue",
        "holePars": "43",
    }


class RoundIngestCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patches = [mock.patch.object(history, "ROOT", self.root)]
        for p in self._patches:
            p.start()
        stats_cache.clear()
        self.addCleanup(stats_cache.clear)

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def _player_dir(self, player_id: str) -> Path:
        return self.root / "data" / "players" / player_id

    def test_ingest_writes_garmin_isomorphic_files(self) -> None:
        summary = round_ingest.ingest_round(
            "p_friend", _events(), _meta(), idempotency_key="rnd-1", root=self.root
        )
        rid = summary["id"]
        sc_path = self._player_dir("p_friend") / "scorecards" / f"{rid}.json"
        shot_path = self._player_dir("p_friend") / "shots" / f"{rid}.json"
        self.assertTrue(sc_path.exists())
        self.assertTrue(shot_path.exists())
        self.assertEqual(summary["holesCompleted"], 2)
        self.assertEqual(summary["strokes"], 9)
        self.assertEqual(summary["source"], "manual")
        self.assertFalse(summary["idempotent"])

    def test_round_is_consumable_by_load_raw_rounds(self) -> None:
        round_ingest.ingest_round(
            "p_friend", _events(), _meta(), idempotency_key="rnd-1", root=self.root
        )
        rounds = history.load_raw_rounds(player_id="p_friend")
        self.assertEqual(len(rounds), 1)
        row = rounds[0]
        self.assertEqual(row["strokes"], 9)
        self.assertEqual(row["holesCompleted"], 2)
        self.assertEqual(row["source"], "manual")
        self.assertTrue(row["hasShots"])
        self.assertEqual(row["shotStatus"], "ready")
        # holePars "43" -> par sum over the two played holes = 7
        self.assertEqual(row["par"], 7)
        # per-hole strokes come straight from the score events
        strokes_by_hole = {h["number"]: h["strokes"] for h in row["holes"]}
        self.assertEqual(strokes_by_hole, {1: 4, 2: 5})
        first_hole = next(h for h in row["holes"] if h["number"] == 1)
        second_hole = next(h for h in row["holes"] if h["number"] == 2)
        self.assertEqual(first_hole["putts"], 2)
        self.assertEqual(first_hole["fairway"], "left")
        self.assertEqual(second_hole["penalties"], 1)

    def test_shots_are_consumable_by_load_shot_history(self) -> None:
        round_ingest.ingest_round(
            "p_friend", _events(), _meta(), idempotency_key="rnd-1", root=self.root
        )
        shots = history.load_shot_history(player_id="p_friend")
        # one shot row per location event
        self.assertEqual(len(shots), 3)
        self.assertEqual({s["clubName"] for s in shots}, {"1D", "8I", "7I"})
        self.assertCountEqual([s["hole"] for s in shots], [1, 1, 2])
        self.assertEqual(
            {hole: sorted(s["order"] for s in shots if s["hole"] == hole) for hole in (1, 2)},
            {1: [1, 2], 2: [1]},
        )
        # coordinates round-trip back to ~the input degrees (stored as semicircles)
        first = shots[0]
        self.assertIsNotNone(first["start"])
        self.assertAlmostEqual(first["start"]["lat"], 47.7334, places=3)
        self.assertAlmostEqual(first["start"]["lon"], 138.8915, places=3)
        # the non-final shot of hole 1 has an end (next location) and a positive distance
        self.assertIsNotNone(first["end"])
        self.assertGreater(first["meters"], 0)

    def test_ios_location_first_uses_confirmed_actual_club_not_prior_recommendation(self) -> None:
        """The phone durably records GPS before asking for the actual club.

        A prior club-selection event only drives the caddie/map and must not be attached to the
        shot. The later actualShot event explicitly references the already-saved location event.
        """
        events = [
            {
                "eventId": "recommended-selection",
                "clientId": "ios-phone",
                "hole": 1,
                "kind": "club",
                "payload": {"clubName": "1W", "shotType": "tee", "lie": "tee"},
            },
            {
                "eventId": "shot-location-1",
                "clientId": "ios-phone",
                "hole": 1,
                "kind": "location",
                "payload": {"latitude": 47.7334, "longitude": 138.8915},
            },
            {
                "eventId": "actual-club-1",
                "clientId": "ios-phone",
                "hole": 1,
                "kind": "club",
                "payload": {
                    "clubName": "3W",
                    "shotType": "tee",
                    "lie": "tee",
                    "actualShot": {"sourceLocationEventId": "shot-location-1", "shotOrder": 1},
                },
            },
        ]

        parsed = round_ingest._parse_events(events)

        self.assertEqual(len(parsed[1].shots), 1)
        self.assertEqual(parsed[1].shots[0]["club"]["clubName"], "3W")
        self.assertEqual(parsed[1].shots[0]["locationEventId"], "shot-location-1")

    def test_ios_skipped_actual_club_keeps_location_without_using_recommendation(self) -> None:
        events = [
            {
                "eventId": "recommended-selection",
                "clientId": "ios-phone",
                "hole": 1,
                "kind": "club",
                "payload": {"clubName": "1W", "shotType": "tee", "lie": "tee"},
            },
            {
                "eventId": "shot-location-1",
                "clientId": "ios-phone",
                "hole": 1,
                "kind": "location",
                "payload": {"latitude": 47.7334, "longitude": 138.8915},
            },
        ]

        parsed = round_ingest._parse_events(events)

        self.assertEqual(len(parsed[1].shots), 1)
        self.assertIsNone(parsed[1].shots[0]["club"])
        self.assertEqual(parsed[1].shots[0]["locationEventId"], "shot-location-1")

    def test_idempotent_repeat_does_not_duplicate(self) -> None:
        first = round_ingest.ingest_round(
            "p_friend", _events(), _meta(), idempotency_key="rnd-1", root=self.root
        )
        scorecards_dir = self._player_dir("p_friend") / "scorecards"
        self.assertEqual(len(list(scorecards_dir.glob("*.json"))), 1)
        second = round_ingest.ingest_round(
            "p_friend", _events(), _meta(), idempotency_key="rnd-1", root=self.root
        )
        self.assertEqual(second["id"], first["id"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(len(list(scorecards_dir.glob("*.json"))), 1)
        self.assertEqual(len(history.load_raw_rounds(player_id="p_friend")), 1)

    def test_owner_manual_round_lands_under_players_me(self) -> None:
        summary = round_ingest.ingest_round(
            "me", _events(), _meta(), idempotency_key="owner-1", root=self.root
        )
        rid = summary["id"]
        sc_path = self._player_dir("me") / "scorecards" / f"{rid}.json"
        self.assertTrue(sc_path.exists())
        # owner load folds the manual round in via the players/me source
        rounds = history.load_raw_rounds(player_id="me")
        self.assertEqual([r["id"] for r in rounds], [rid])
        self.assertEqual(rounds[0]["source"], "manual")

    def test_empty_events_rejected(self) -> None:
        with self.assertRaises(round_ingest.RoundIngestError):
            round_ingest.ingest_round("p_friend", [], _meta(), idempotency_key="x", root=self.root)


if __name__ == "__main__":
    unittest.main()
