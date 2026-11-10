"""A hand-recorded round and the Garmin round of the same play reconcile into one round (test-plan S-20).

Drives the real HTTP routes: POST /api/v2/players/me/rounds (manual phone round), the mobile
event batch route, GET /api/v2/mobile/rounds/{rid}/reconciliation, POST .../reconciliation/apply
and GET /api/v2/history/rounds. Garmin scorecards are written as the Garmin sync stores them
(ROOT/data/scorecards/<id>.json) under a temporary ROOT; nothing reaches Garmin or the network.

Spec rules the expected values come from:
  * product-test-spec 1.3: a manual round and its Garmin round are neither duplicated nor lost;
    two same-day 9-hole cards become one 18-hole round; a front card Garmin numbered 10-18 is
    displayed 1-9; reconciliation rows report ``hole`` on the Garmin display axis.
  * multiplayer spec: same player + same calendar day + same course -> Garmin wins and the manual
    round is superseded (kept on disk, hidden from history).
"""
from __future__ import annotations

import json
import os
import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.core.config import get_settings
from ai_caddie.history import history
from server_v2 import annotations, caddie, course_install, history_round_detail, history_rounds, main, mobile

COURSE = "Example Links"
OTHER_COURSE = "Harbour Park"
GLOBAL_ID = 81001
# Active-round leases left in these globals block background work in later modules.
ACTIVE_ROUND_STATE = (
    (main, ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_START_TIMES",
            "_ROUND_START_CACHE", "_ACTIVE_EVENT_DEVICES", "_ACTIVE_SELECTIONS")),
    (course_install, ("_CURRENT_COURSE_IDS",)),
    (mobile, ("_PACKAGE_SINGLEFLIGHT",)),
)


def score_event(round_id: str, hole: int, strokes: int, *, event_id: str | None = None) -> dict:
    return {"schema": "ai-caddie-live-round-event-v1", "eventId": event_id or f"score-h{hole}",
            "roundId": round_id, "timestamp": "2026-01-02T08:00:00Z", "hole": hole,
            "kind": "score", "payload": {"strokes": strokes, "source": "manual_edit"}}


class Reconcile(unittest.TestCase):
    """S-20: manual vs Garmin rounds through the real ingest, history and reconciliation routes."""

    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.root = Path(stack.enter_context(TemporaryDirectory()))
        stack.enter_context(patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture",
                                                    "AI_CADDIE_ADMIN_TOKEN": "",
                                                    "AI_CADDIE_SECURITY_PROFILE": ""}))
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        for module, attribute in ((history, "ROOT"), (main, "ROOT"), (mobile, "MOBILE_ROOT"),
                                  (mobile, "ANNOTATION_ROOT"), (mobile, "DECISION_AUDIT_ROOT"),
                                  (annotations, "ANNOTATION_ROOT"), (history_round_detail, "ANNOTATION_ROOT"),
                                  (caddie, "DECISION_LEDGER_ROOT")):
            stack.enter_context(patch.object(module, attribute, self.root))
        # Owner Garmin shot files would otherwise be looked up in the real data directory.
        stack.enter_context(patch.object(history, "SHOT_DIR", self.root / "data" / "shots"))
        stack.enter_context(patch.object(history, "load_shot_file", return_value=None))
        # Fixture mode serves the shared demo data; read this test's own temp ROOT instead.
        for module in (main, mobile, annotations, history_round_detail, history_rounds):
            stack.enter_context(patch.object(module, "load_history_data_for_mode",
                                             side_effect=lambda *a, **kw: (history.load_history_data("me"),
                                                                           "fixture")))
        stack.enter_context(patch.object(main, "_prepare_recent_bg"))
        stack.enter_context(patch.object(mobile, "warm_stats_cache_in_background"))
        stack.enter_context(patch.object(main, "_ACTIVE_PACKAGED_ROUNDS", set()))
        for module, names in ACTIVE_ROUND_STATE:
            for name in names:
                stack.enter_context(patch.dict(getattr(module, name), clear=True))
        stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("unexpected network")))
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    # -- data builders ---------------------------------------------------------------------
    def garmin_card(self, sid: int, start: str, strokes: list[int], *, first_hole: int = 1,
                    course: str = COURSE, global_id: int = GLOBAL_ID) -> None:
        """Store one completed Garmin scorecard the way the Garmin sync writes it."""
        holes = [{"number": first_hole + i, "strokes": s, "putts": 2} for i, s in enumerate(strokes)]
        card = {"id": sid, "startTime": start, "formattedStartTime": start, "holesCompleted": len(holes),
                "strokes": sum(strokes), "courseGlobalId": global_id, "inProgress": False, "holes": holes}
        pars = "4" * (18 if first_hole > 1 else len(holes))
        path = Path(history.ROOT) / "data" / "scorecards" / f"{sid}.json"  # the current (patched) ROOT
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"scorecardDetails": [{"scorecard": card}],
                                    "courseSnapshots": [{"name": course, "holePars": pars}]}))

    def manual_round(self, tee_time: str, *, key: str, course: str = COURSE, strokes: int = 5) -> str:
        """Record a 9-hole round by hand through the phone ingest route; returns its id."""
        events = [score_event("phone", hole, strokes, event_id=f"{key}-h{hole}") for hole in range(1, 10)]
        response = self.client.post(
            "/api/v2/players/me/rounds", headers={"Idempotency-Key": key},
            json={"events": events, "meta": {"courseName": course, "courseGlobalId": GLOBAL_ID,
                                             "holePars": "444444444444444444", "teeTime": tee_time}})
        self.assertIn(response.status_code, (200, 201), response.text[:400])
        return str(response.json()["id"])

    # -- route helpers ---------------------------------------------------------------------
    def history_cards(self) -> dict[str, dict]:
        response = self.client.get("/api/v2/history/rounds")
        self.assertEqual(response.status_code, 200, response.text[:400])
        return {row["id"]: row for group in response.json()["groups"] for row in group["rounds"]}

    def send_events(self, round_id: str, events: list[dict], *, key: str) -> None:
        response = self.client.post(f"/api/v2/mobile/rounds/{round_id}/events",
                                    headers={"Idempotency-Key": key},
                                    json={"roundId": round_id, "events": events})
        self.assertEqual(response.status_code, 200, response.text[:400])

    def reconciliation(self, round_id: str) -> dict:
        response = self.client.get(f"/api/v2/mobile/rounds/{round_id}/reconciliation")
        self.assertEqual(response.status_code, 200, response.text[:400])
        return response.json()

    def apply(self, round_id: str, suggestion_ids: list[str]) -> dict:
        response = self.client.post(f"/api/v2/mobile/rounds/{round_id}/reconciliation/apply",
                                    json={"suggestionIds": suggestion_ids})
        self.assertEqual(response.status_code, 200, response.text[:400])
        return response.json()

    def holes_by_number(self, round_id: str) -> dict[int, int]:
        response = self.client.get(f"/api/v2/history/rounds/{round_id}")
        self.assertEqual(response.status_code, 200, response.text[:400])
        return {int(row["hole"]): row.get("score") for row in response.json()["scorecard"]}

    # -- tests -----------------------------------------------------------------------------
    def test_manual_vs_garmin_merge(self):
        """S-20 [main]: manual + Garmin double card of one play -> one 18-hole round, phone scores reconciled and applied once."""
        # Garmin double card of one play: two 9-hole cards on 2026-01-02, both numbered 1..9.
        self.garmin_card(880101, "2026-01-02T08:00:00", [3, 4, 4, 4, 4, 4, 4, 4, 4])  # 35
        self.garmin_card(880102, "2026-01-02T10:30:00", [5, 5, 6, 5, 5, 5, 5, 5, 5])  # 46
        # The same play recorded by hand, tee time later on the same calendar day.
        manual_id = self.manual_round("2026-01-02T13:00:00Z", key="manual-play")

        merged = "merged_880101_880102"  # product id of two merged halves: merged_<front>_<back>
        cards = self.history_cards()
        self.assertEqual([merged], list(cards))  # no duplicate (manual hidden), no loss (both halves)
        self.assertNotIn(manual_id, cards)
        self.assertEqual(18, cards[merged]["holesCompleted"])
        self.assertEqual(81, cards[merged]["score"])  # 35 + 46
        holes = self.holes_by_number(merged)
        self.assertEqual(list(range(1, 19)), sorted(holes))  # back card offset 9 -> holes 10..18
        self.assertEqual(3, holes[1])  # front card hole 1, offset 0
        self.assertEqual(6, holes[12])  # back card hole 3 shown as 3 + 9

        self.send_events(merged, [score_event(merged, 1, 3), score_event(merged, 12, 6),
                                  score_event(merged, 15, 4)], key="phone-batch")
        report = self.reconciliation(merged)
        summary = report["summary"]
        self.assertEqual(3, summary["eventCount"])
        self.assertEqual(2, summary["matchedCount"])  # holes 1 and 12 agree with Garmin
        self.assertEqual(1, summary["conflictCount"])  # hole 15: phone 4, Garmin 5
        self.assertEqual(0, summary["localOnlyCount"])
        self.assertEqual({1, 12}, {row["hole"] for row in report["matched"]})
        conflict = report["conflicts"][0]
        self.assertEqual((15, 4, 5), (conflict["hole"], conflict["localValue"], conflict["garminValue"]))
        suggestion = "score-h15:score-correction"  # <eventId>:score-correction for a plain conflict
        self.assertIn(suggestion, [row["id"] for row in report["annotationSuggestions"]])

        first = self.apply(merged, [suggestion])
        self.assertEqual(1, first["appliedCount"])
        second = self.apply(merged, [suggestion])  # replay of the same apply
        self.assertEqual(0, second["appliedCount"])
        self.assertEqual([suggestion], second["skippedSuggestionIds"])
        self.assertEqual(80, self.history_cards()[merged]["score"])  # 81 - 1, corrected once only
        after = self.reconciliation(merged)["summary"]
        self.assertEqual((3, 0), (after["matchedCount"], after["conflictCount"]))  # hole 15 now agrees

    def test_same_play_time_window(self):
        """S-20: the manual round is merged into the Garmin round by calendar day, whatever the hour."""
        cases = (
            # (label, Garmin start, manual tee time, rounds expected in history)
            # Same day, morning Garmin vs evening phone: one play -> only the Garmin round.
            ("same day, different times", "2026-01-02T06:00:00", "2026-01-02T17:30:00Z", ["880201"]),
            # First and last minute of one date are still the same day.
            ("same date edges", "2026-01-02T00:05:00", "2026-01-02T23:55:00Z", ["880201"]),
            # A night round crossing midnight: both devices stamp the start (before midnight).
            ("night play across midnight", "2026-01-02T23:40:00", "2026-01-02T23:45:00Z", ["880201"]),
            # Starts on consecutive dates are different days by the calendar-day rule: both kept.
            ("starts either side of midnight", "2026-01-02T23:50:00", "2026-01-03T00:10:00Z", ["880201", "manual"]),
        )
        for label, garmin_start, tee_time, expected in cases:
            with self.subTest(label), patch.object(history, "ROOT", self.root / label.replace(" ", "-")):
                self.garmin_card(880201, garmin_start, [5] * 9)
                manual_id = self.manual_round(tee_time, key=f"manual-{label}")
                ids = sorted(self.history_cards())
                self.assertEqual(sorted(manual_id if row == "manual" else row for row in expected), ids)

    def test_nine_hole_double_card_offsets(self):
        """S-20: two same-day 9-hole cards merge to 18 holes; front offset 0 (or 1-9 display), back offset 9."""
        cases = (
            # (label, front card first hole number, front display holes expected)
            # Front card numbered 1..9: offset 0, displayed 1..9.
            ("front numbered 1-9", 1, list(range(1, 10))),
            # Front card Garmin numbered 10..18 (back nine played first): displayed 1..9 (spec 1.3).
            ("front numbered 10-18", 10, list(range(1, 10))),
        )
        for index, (label, first_hole, front_display) in enumerate(cases):
            with self.subTest(label), patch.object(history, "ROOT", self.root / f"offset-{index}"):
                front, back = 880300 + 2 * index, 880301 + 2 * index
                self.garmin_card(front, "2026-01-02T08:00:00", [4, 4, 4, 4, 4, 4, 4, 4, 3], first_hole=first_hole)
                self.garmin_card(back, "2026-01-02T10:00:00", [6, 5, 5, 5, 5, 5, 5, 5, 5])
                merged = f"merged_{front}_{back}"
                cards = self.history_cards()
                self.assertEqual([merged], list(cards))
                self.assertEqual(18, cards[merged]["holesCompleted"])
                self.assertEqual(81, cards[merged]["score"])  # 35 + 46
                holes = self.holes_by_number(merged)
                self.assertEqual(front_display + list(range(10, 19)), sorted(holes))
                self.assertEqual(3, holes[9])  # last front hole keeps its 3
                self.assertEqual(6, holes[10])  # first back-card hole (its own hole 1) + offset 9
                # Phone scores on the display axis line up with the right card.
                self.send_events(merged, [score_event(merged, 9, 3, event_id=f"o{index}-h9"),
                                          score_event(merged, 10, 6, event_id=f"o{index}-h10")],
                                 key=f"offset-batch-{index}")
                summary = self.reconciliation(merged)["summary"]
                self.assertEqual((2, 0, 0), (summary["matchedCount"], summary["conflictCount"],
                                             summary["localOnlyCount"]))

    def test_non_matching_garmin_round_is_not_merged(self):
        """S-20: a Garmin round of another course or another day leaves the manual round alone."""
        cases = (
            # (label, Garmin course, Garmin start): only same course AND same date may merge.
            ("other course, same day", OTHER_COURSE, "2026-01-02T08:00:00"),
            ("same course, other day", COURSE, "2026-01-05T08:00:00"),
        )
        for index, (label, course, start) in enumerate(cases):
            with self.subTest(label), patch.object(history, "ROOT", self.root / f"nomatch-{index}"):
                self.garmin_card(880400 + index, start, [5] * 9, course=course,
                                 global_id=GLOBAL_ID + 1 if course != COURSE else GLOBAL_ID)
                manual_id = self.manual_round("2026-01-02T13:00:00Z", key=f"nomatch-{index}")
                cards = self.history_cards()
                # Both rounds survive as two separate 9-hole rounds: nothing merged, nothing lost.
                self.assertEqual(sorted([str(880400 + index), manual_id]), sorted(cards))
                self.assertEqual({9}, {row["holesCompleted"] for row in cards.values()})

    def test_apply_is_idempotent_and_manual_ingest_replay_is_one_round(self):
        """S-20: replaying the manual upload and the apply call never creates a second round or correction."""
        self.garmin_card(880501, "2026-01-02T08:00:00", [5, 5, 5, 5, 5, 5, 5, 5, 5])  # 45
        first_id = self.manual_round("2026-01-02T13:00:00Z", key="replayed-upload")
        again_id = self.manual_round("2026-01-02T13:00:00Z", key="replayed-upload")
        self.assertEqual(first_id, again_id)  # same Idempotency-Key -> same manual round
        self.assertEqual(["880501"], list(self.history_cards()))

        rid = "880501"
        self.send_events(rid, [score_event(rid, 2, 4), score_event(rid, 7, 6)], key="batch")
        report = self.reconciliation(rid)
        ids = sorted(row["id"] for row in report["annotationSuggestions"]
                     if row["id"].endswith(":score-correction"))
        self.assertEqual(["score-h2:score-correction", "score-h7:score-correction"], ids)
        cases = (
            # (label, selection, appliedCount, skipped) - the second and third calls replay the first.
            ("first apply", ids, 2, []),
            ("same selection again", ids, 0, ids),
            ("one id again", ids[:1], 0, ids[:1]),
        )
        for label, selection, applied, skipped in cases:
            with self.subTest(label):
                result = self.apply(rid, selection)
                self.assertEqual(applied, result["appliedCount"])
                self.assertEqual(skipped, sorted(result["skippedSuggestionIds"]))
                self.assertEqual(45, self.history_cards()[rid]["score"])  # 45 - 1 + 1 -> unchanged total
        holes = self.holes_by_number(rid)
        self.assertEqual((4, 6), (holes[2], holes[7]))  # each correction applied exactly once


if __name__ == "__main__":
    unittest.main()
