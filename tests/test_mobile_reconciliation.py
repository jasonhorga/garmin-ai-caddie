from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.reports.annotations import add_annotation, list_annotation_records, list_annotations
from ai_caddie.caddie.decision import list_decision_audits, store_decision
from ai_caddie.history.history import HistoryData
from ai_caddie.caddie.mobile_live import append_event_batch
from ai_caddie.caddie.mobile_reconciliation import (
    _event_rows,
    apply_mobile_reconciliation_suggestions,
    reconcile_mobile_round_events,
)
from ai_caddie.history.corrected_history import corrected_history_data
from ai_caddie.caddie.mobile_round_identity import (
    MobileRoundIdentityError, load_mobile_round_identity, save_mobile_round_identity,
)
from ai_caddie.caddie.round_loops import round_loop_key, round_loops_table


def _save_identity(root: Path, round_id: str, loops: list[tuple[int, str]], player_id: str = "me") -> None:
    # Input adapter: a complete package identity without geometry/weather enrichment.
    holes = []
    for index, (gid, half) in enumerate(loops):
        for offset in range(9):
            number = index * 9 + offset + 1
            local = offset + (10 if half == "back" else 1)
            holes.append({"number": number, "sourceGlobalId": gid, "sourceLocalHole": local,
                          "courseHoleNumber": number if half == "all" else local})
    save_mobile_round_identity(round_id, round_loops_table(loops), round_loop_key(loops), holes,
                               root=root, player_id=player_id)


class MobileReconciliationTests(unittest.TestCase):
    def test_saved_identity_keeps_missing_garmin_back_nine_local_only(self) -> None:
        # R3: an 18-hole phone round and a nine-hole Garmin upload share exactly holes 1..9.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _save_identity(root, "partial", [(55555, "front"), (55555, "back")])
            append_event_batch("partial", [{
                "eventId": f"score-{n}", "roundId": "partial", "hole": n,
                "kind": "score", "payload": {"strokes": 5},
            } for n in range(1, 19)], idempotency_key="partial", root=root)
            data = HistoryData(raw_rounds=[], rounds=[{
                "id": "partial", "globalId": 55555,
                "holes": [{"number": n, "strokes": 5} for n in range(1, 10)],
            }], shots=[])
            result = reconcile_mobile_round_events("partial", data, root=root)
            self.assertEqual([r["ref"] for r in result["matched"]],
                             [f"partial:{n}" for n in range(1, 10)])
            self.assertEqual([r["hole"] for r in result["localOnly"]], list(range(10, 19)))
            self.assertEqual(result["conflicts"], [])
            self.assertEqual([r["targetId"] for r in result["annotationSuggestions"]],
                             [f"partial:{n}" for n in range(10, 19)])

    def test_saved_identity_matches_merged_front_then_back_of_eighteen_hole_course(self) -> None:
        self._assert_merged_eighteen_hole_halves_match("front")

    def test_saved_identity_matches_merged_two_back_nines_of_eighteen_hole_course(self) -> None:
        self._assert_merged_eighteen_hole_halves_match("back")

    def _assert_merged_eighteen_hole_halves_match(self, first_half: str) -> None:
        from ai_caddie.history.history import merge_same_day_halves

        # Garmin's two real nine-hole cards are merged by the production history adapter.
        # First lap scores 5, second 7; both laps retain canonical display refs 1..18.
        first_numbers = range(1, 10) if first_half == "front" else range(10, 19)
        cards = [{
            "id": name, "date": f"2026-05-25T{hour}:00:00Z", "courseCanonical": "Fixture Course",
            "globalId": 55555, "holesCompleted": 9,
            "holes": [{"number": n, "strokes": score} for n in numbers],
        } for name, hour, score, numbers in (
            ("first", "08", 5, first_numbers), ("second", "10", 7, range(10, 19)),
        )]
        rows = merge_same_day_halves(cards)
        round_id = rows[0]["id"]
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _save_identity(root, round_id, [(55555, first_half), (55555, "back")])
            append_event_batch(round_id, [{
                "eventId": f"score-{n}", "roundId": round_id, "hole": n,
                "kind": "score", "payload": {"strokes": 5 if n <= 9 else 7},
            } for n in range(1, 19)], idempotency_key="merged", root=root)
            result = reconcile_mobile_round_events(
                round_id, HistoryData(raw_rounds=cards, rounds=rows, shots=[]), root=root,
            )
            self.assertEqual([r["ref"] for r in result["matched"]],
                             [f"{round_id}:{n}" for n in range(1, 19)])
            self.assertEqual(result["localOnly"], [])
            self.assertEqual(result["conflicts"], [])
            self.assertEqual(result["annotationSuggestions"], [])

    def test_saved_identity_falls_back_for_garmin_card_without_any_course_id(self) -> None:
        # R3: missing course authority must preserve the legacy display-based match.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _save_identity(root, "no-gid", [(55555, "back")])
            append_event_batch("no-gid", [{
                "eventId": f"score-{n}", "roundId": "no-gid", "hole": n,
                "kind": "score", "payload": {"strokes": 5},
            } for n in range(1, 10)], idempotency_key="no-gid", root=root)
            data = HistoryData(raw_rounds=[], rounds=[{
                "id": "no-gid", "holes": [{"number": n, "strokes": 5} for n in range(1, 10)],
            }], shots=[])
            result = reconcile_mobile_round_events("no-gid", data, root=root)
            self.assertEqual([r["ref"] for r in result["matched"]],
                             [f"no-gid:{n}" for n in range(1, 10)])
            self.assertEqual(result["annotationSuggestions"], [])

    def test_identity_expands_after_locally_added_second_nine_events_arrive(self) -> None:
        # R3 setSecondLoop: phone holes 10 and 11 may arrive before package validation.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _save_identity(root, "expand", [(55555, "front")])
            append_event_batch("expand", [{
                "eventId": f"score-{n}", "roundId": "expand", "hole": n,
                "kind": "score", "payload": {"strokes": 5 if n <= 9 else 7},
            } for n in range(1, 12)], idempotency_key="first-eleven", root=root)
            _save_identity(root, "expand", [(55555, "front"), (55555, "back")])
            self.assertEqual(load_mobile_round_identity("expand", root=root)["loopKey"],
                             "55555:front+55555:back")
            append_event_batch("expand", [{
                "eventId": f"score-{n}", "roundId": "expand", "hole": n,
                "kind": "score", "payload": {"strokes": 7},
            } for n in range(12, 19)], idempotency_key="remaining", root=root)
            data = HistoryData(raw_rounds=[], rounds=[{
                "id": "expand", "globalId": 55555,
                "holes": [{"number": n, "strokes": 5 if n <= 9 else 7} for n in range(1, 19)],
            }], shots=[])
            result = reconcile_mobile_round_events("expand", data, root=root)
            self.assertEqual([r["ref"] for r in result["matched"]],
                             [f"expand:{n}" for n in range(1, 19)])
            self.assertEqual(result["annotationSuggestions"], [])

    def test_mapped_suggestion_applies_to_original_garmin_ref_and_reconciles_all_facts(self) -> None:
        data = HistoryData(raw_rounds=[], rounds=[{
            "id": "back", "globalId": 55555, "holesCompleted": 9,
            "holes": [{"number": n, "strokes": 4, "putts": 2, "penalties": 0}
                      for n in range(10, 19)],
        }], shots=[{"roundId": "back", "hole": 10, "clubName": "7I"}])
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _save_identity(root, "back", [(55555, "back")])
            append_event_batch("back", [{
                "eventId": kind, "roundId": "back", "hole": 1, "startHole": 1,
                "kind": kind, "payload": {field: value},
            } for kind, field, value in (("score", "strokes", 5), ("putt", "putts", 2),
                                         ("penalty", "penalties", 0), ("club", "clubName", "7I"))],
                idempotency_key="facts", root=root)
            result = reconcile_mobile_round_events("back", data, root=root)
            self.assertEqual([(r["kind"], r["ref"]) for r in result["matched"]],
                             [("putt", "back:10"), ("penalty", "back:10"), ("club", "back:10:1")])
            self.assertEqual(result["garminOnly"], [])  # There is a real shot to consume here.
            self.assertEqual(result["annotationSuggestions"][0]["targetId"], "back:10")
            applied = apply_mobile_reconciliation_suggestions(
                "back", data, root=root, annotations_root=root, data_loader=lambda: data,
            )
            self.assertEqual(applied["appliedCount"], 1)
            self.assertEqual(list_annotation_records(root=root)[0]["targetId"], "back:10")
            after = reconcile_mobile_round_events("back", data, root=root)
            self.assertEqual(len(after["matched"]), 4)
            self.assertEqual(after["annotationSuggestions"], [])
            self.assertEqual(after["localOnly"], [])
            self.assertEqual(after["conflicts"], [])
            self.assertEqual(data.rounds[0]["holes"][0]["strokes"], 4)

    def test_saved_physical_course_and_visit_distinguish_mixed_nines_and_second_laps(self) -> None:
        cases = (
            # Phone A+B, Garmin B+A: the course id must participate in the match.
            ("mixed", [(31796, "all"), (31794, "all")], 31794, 31796,
             (7, 5), list(range(10, 19)) + list(range(1, 10))),
            ("repeat", [(31796, "all"), (31796, "all")], 31796, 31796,
             (5, 7), list(range(1, 19))),
            # Garmin may omit the back id when one nine is played twice.
            ("repeat-no-back-id", [(31796, "all"), (31796, "all")], 31796, None,
             (5, 7), list(range(1, 19))),
        )
        for name, loops, front_gid, back_gid, totals, targets in cases:
            with self.subTest(shape=name), TemporaryDirectory() as tmp:
                root = Path(tmp)
                data = HistoryData(raw_rounds=[], rounds=[{
                    "id": name, "globalId": front_gid, "frontNineGlobalCourseId": front_gid,
                    "backNineGlobalCourseId": back_gid, "holesCompleted": 18,
                    "holes": [{"number": n, "strokes": totals[0 if n <= 9 else 1]}
                              for n in range(1, 19)],
                }], shots=[])
                _save_identity(root, name, loops)
                append_event_batch(name, [{
                    "eventId": f"score-{n}", "roundId": name, "hole": n, "kind": "score",
                    "payload": {"strokes": 5 if n <= 9 else 7},
                } for n in range(1, 19)], idempotency_key=name, root=root)
                result = reconcile_mobile_round_events(name, data, root=root)
                self.assertEqual([r["ref"] for r in result["matched"]], [f"{name}:{n}" for n in targets])
                self.assertEqual(result["annotationSuggestions"], [])
                self.assertEqual(result["localOnly"], [])
                self.assertEqual(result["conflicts"], [])

    def test_identity_changes_preserve_played_holes_and_player_partitions(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _save_identity(root, "same-id", [(55555, "back")], player_id="member-a")
            self.assertIsNone(load_mobile_round_identity("same-id", root=root))
            self.assertIsNone(load_mobile_round_identity("same-id", root=root, player_id="member-b"))
            append_event_batch("same-id", [{
                "eventId": "first", "roundId": "same-id", "hole": 1,
                "kind": "score", "payload": {"strokes": 4},
            }], idempotency_key="first", root=root, player_id="member-a")
            _save_identity(root, "same-id", [(55555, "back"), (55555, "front")], player_id="member-a")
            # The unplayed second nine may change. The already played first nine cannot.
            _save_identity(root, "same-id", [(55555, "back"), (55555, "back")], player_id="member-a")
            with self.assertRaises(MobileRoundIdentityError):
                _save_identity(root, "same-id", [(55555, "front")], player_id="member-a")
            stored = load_mobile_round_identity("same-id", root=root, player_id="member-a")
            self.assertEqual(stored["loopKey"], "55555:back+55555:back")
            data = HistoryData(raw_rounds=[], rounds=[{
                "id": "same-id", "globalId": 55555, "holes": [{"number": 10, "strokes": 4}],
            }], shots=[])
            result = reconcile_mobile_round_events("same-id", data, root=root, player_id="member-a")
            self.assertEqual([r["ref"] for r in result["matched"]], ["same-id:10"])
            self.assertEqual(reconcile_mobile_round_events("same-id", data, root=root)["matched"], [])

    def test_saved_identity_preserves_merged_display_refs_and_manual_round_numbers(self) -> None:
        for shape in ("legacy", "normalized", "manual"):
            with self.subTest(shape=shape), TemporaryDirectory() as tmp:
                root = Path(tmp)
                row = {
                    "id": shape, "globalId": 55555, "frontNineGlobalCourseId": 55555,
                    "backNineGlobalCourseId": 55555, "merged": True,
                    "holes": [
                        {"number": n + 9 if shape == "legacy" else n, "localHole": n + 9, "strokes": 5}
                        for n in range(1, 10)
                    ] + [{"number": n, "strokes": 7} for n in range(10, 19)],
                }
                if shape == "manual":
                    row.update(source="manual", merged=False)
                    row["holes"] = [{"number": n, "strokes": 5 if n <= 9 else 7} for n in range(1, 19)]
                data = HistoryData(raw_rounds=[], rounds=[row], shots=[])
                _save_identity(root, shape, [(55555, "back"), (55555, "front")])
                append_event_batch(shape, [{
                    "eventId": f"score-{n}", "roundId": shape, "hole": n, "kind": "score",
                    "payload": {"strokes": 5 if n <= 9 else 7},
                } for n in range(1, 19)], idempotency_key=shape, root=root)
                result = reconcile_mobile_round_events(shape, data, root=root)
                self.assertEqual([r["ref"] for r in result["matched"]], [f"{shape}:{n}" for n in range(1, 19)])
                self.assertEqual(result["annotationSuggestions"], [])
                self.assertEqual(result["localOnly"], [])
                self.assertEqual(result["conflicts"], [])

    def test_unresolved_physical_identity_refuses_wrong_hole_suggestions(self) -> None:
        from fastapi import HTTPException
        from server_v2 import mobile as mobile_service
        from server_v2.models import MobileReconciliationApplyRequest

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _save_identity(root, "mismatch", [(55555, "back")])
            append_event_batch("mismatch", [{
                "eventId": "score", "roundId": "mismatch", "hole": 1,
                "kind": "score", "payload": {"strokes": 5},
            }], idempotency_key="mismatch", root=root)
            # The same numeric display hole on another course is not a matching physical hole.
            data = HistoryData(raw_rounds=[], rounds=[{
                "id": "mismatch", "globalId": 66666, "holes": [{"number": 1, "strokes": 4}],
            }], shots=[])
            with (
                patch.object(mobile_service, "MOBILE_ROOT", root),
                patch.object(mobile_service, "load_history_data_for_mode", return_value=(data, "fixture")),
            ):
                for operation in (
                    lambda: mobile_service.reconcile_mobile_round_response("mismatch"),
                    lambda: mobile_service.apply_mobile_round_reconciliation_response(
                        "mismatch", MobileReconciliationApplyRequest(suggestionIds=[]),
                    ),
                ):
                    with self.assertRaises(HTTPException) as caught:
                        operation()
                    self.assertEqual(caught.exception.status_code, 409)
                    self.assertEqual(caught.exception.detail, "mobile_round_hole_identity_unresolved")
            self.assertEqual(list_annotation_records(root=root), [])

    def test_back_start_package_events_match_physical_numbered_garmin_cards(self) -> None:
        """Exercise the real package -> event append -> reconciliation service boundary.

        The nine-hole case is documented in merge_same_day_halves: Garmin records a standalone
        back nine as 10..18. The eighteen-hole case is a defensive counterexample, not evidence
        that Garmin stores a back-start eighteen this way. In both, loop order proves that phone
        holes 1..9 mean physical 10..18; a startHole of 1 alone cannot prove that mapping.
        """
        from ai_caddie.caddie import mobile_live
        from ai_caddie.courses import course_reference
        from server_v2 import mobile as mobile_service
        from server_v2.models import LiveRoundEventBatchRequest

        for count in (9, 18):
            with self.subTest(holes=count), TemporaryDirectory() as tmp:
                root = Path(tmp)
                round_id = f"physical-back-{count}"
                numbers = range(10, 19) if count == 9 else range(1, 19)
                data = HistoryData(raw_rounds=[], rounds=[{
                    "id": round_id, "globalId": 55555, "course": "Fixture Course",
                    "courseCanonical": "Fixture Course", "courseKey": "fixture-course",
                    "holesCompleted": count, "holePars": "4" * 18,
                    "holes": [{"number": n, "par": 4, "strokes": 4 if n > 9 else 6,
                               "putts": 2, "penalties": 0} for n in numbers],
                }], shots=[])
                loops = [(55555, "back")] + ([(55555, "front")] if count == 18 else [])
                with (
                    patch.object(mobile_service, "MOBILE_ROOT", root),
                    patch.object(mobile_service, "load_history_data_for_mode", return_value=(data, "fixture")),
                    patch.object(mobile_service, "_refresh_course_release_authority", return_value=[]),
                    patch.object(mobile_live, "_courseview_segment_resolver", return_value=("Fixture Course", 18)),
                    patch.object(course_reference, "courseview_par", return_value=[4] * 18),
                ):
                    package = mobile_service.build_mobile_course_package_response(
                        55555, round_id=round_id, loops=loops, include_event_cursor=False,
                    ).model_dump(by_alias=True)
                    # Independent hand table: back first, then front. Do not derive the oracle
                    # from the package's sourceLocalHole or the reconciliation mapping.
                    expected_physical = list(range(10, 19)) + (list(range(1, 10)) if count == 18 else [])
                    self.assertEqual([h["number"] for h in package["holes"]], list(range(1, count + 1)))
                    self.assertEqual([h["sourceLocalHole"] for h in package["holes"]], expected_physical)
                    events = [{
                        "schema": "ai-caddie-live-round-event-v1",
                        "eventId": f"score-{h['number']}", "roundId": round_id,
                        "clientId": "ios-phone", "timestamp": "2026-05-25T00:00:00Z",
                        "startHole": 1, "hole": h["number"], "kind": "score",
                        "payload": {"strokes": 4 if h["number"] <= 9 else 6},
                    } for h in package["holes"]]
                    ack = mobile_service.append_mobile_events_response(
                        round_id, LiveRoundEventBatchRequest(roundId=round_id, events=events),
                        idempotency_key=round_id,
                    )
                    self.assertEqual(ack.accepted, count)
                    result = mobile_service.reconcile_mobile_round_response(round_id).model_dump(by_alias=True)

                self.assertEqual(
                    [(r["eventId"], r["ref"]) for r in result["matched"]],
                    [(f"score-{i}", f"{round_id}:{n}") for i, n in enumerate(expected_physical, 1)],
                    result["summary"],
                )
                self.assertEqual(result["localOnly"], [])
                self.assertEqual(result["conflicts"], [])
                self.assertEqual(result["annotationSuggestions"], [])

    def test_start_hole_alone_keeps_legacy_card_display_references(self) -> None:
        # C63 startHole is on the SAME axis as event.hole, not an offset to apply to it.
        # Without a persisted package loop table these events already name Garmin display holes.
        for count, start in ((9, None), (9, 10), (18, 10)):
            with self.subTest(holes=count, start=start), TemporaryDirectory() as tmp:
                root = Path(tmp)
                numbers = list(range(10, 19)) if count == 9 else list(range(1, 19))
                data = HistoryData(raw_rounds=[], rounds=[{
                    "id": "legacy-card", "globalId": 55555, "holesCompleted": count,
                    "holes": [{"number": n, "strokes": 4 if n > 9 else 6} for n in numbers],
                }], shots=[])
                events = [{
                    "eventId": f"legacy-{n}", "roundId": "legacy-card", "hole": n,
                    "kind": "score", "payload": {"strokes": 4 if n > 9 else 6},
                    **({"startHole": start} if start is not None else {}),
                } for n in numbers]
                append_event_batch("legacy-card", events, idempotency_key="legacy", root=root)
                result = reconcile_mobile_round_events("legacy-card", data, root=root)
                self.assertEqual([r["ref"] for r in result["matched"]], [f"legacy-card:{n}" for n in numbers])
                self.assertEqual(result["localOnly"], [])
                self.assertEqual(result["conflicts"], [])
                self.assertEqual(result["annotationSuggestions"], [])
                # A later package request must not retroactively reinterpret a legacy stream.
                _save_identity(root, "legacy-card", [(55555, "back")])
                self.assertIsNone(load_mobile_round_identity("legacy-card", root=root))

    def test_missing_hole_number_matches_score_and_putts_by_original_position(self) -> None:
        # C76: the unnumbered second hole is display 2, scored 5 with 3 putts.
        data = HistoryData(raw_rounds=[], rounds=[{
            "id": "ordinal", "holes": [
                {"number": 1, "strokes": 4, "putts": 2},
                {"strokes": 5, "putts": 3},
                {"number": 3, "strokes": 4, "putts": 2},
            ],
        }], shots=[])
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch("ordinal", [
                {"eventId": "ordinal-score", "roundId": "ordinal", "hole": 2,
                 "kind": "score", "payload": {"strokes": 5}},
                {"eventId": "ordinal-putt", "roundId": "ordinal", "hole": 2,
                 "kind": "putt", "payload": {"putts": 3}},
            ], idempotency_key="ordinal", root=root)
            result = reconcile_mobile_round_events("ordinal", data, root=root)
        self.assertEqual([(r["eventId"], r["ref"]) for r in result["matched"]],
                         [("ordinal-score", "ordinal:2"), ("ordinal-putt", "ordinal:2")])
        self.assertEqual(result["localOnly"], [])
        self.assertEqual(result["annotationSuggestions"], [])

    def test_package_display_holes_reconcile_three_garmin_round_shapes(self) -> None:
        """Phone events use package display holes for back starts, mixed nines, and A+A laps.

        The first shape is Garmin's legacy merged representation when the player started on the
        physical back nine: both scorecards are stored as 10..18, while the package presents the
        first card as display holes 1..9. The other two shapes use the normal merged 1..9 + 10..18
        display storage; the second shape has two different course ids and the third visits one
        course twice. merge_same_day_halves does not add localHole to the second card.
        """
        cases = (
            {
                "name": "legacy-back-then-front-merge",
                "front_gid": 55555, "back_gid": 55555,
                "package_numbers": list(range(1, 19)),
                "garmin_holes": [
                    *[
                        {"number": number + 9, "strokes": 5, "putts": 2, "penalties": 0}
                        for number in range(1, 10)
                    ],
                    *[
                        {"number": number + 9, "strokes": 7, "putts": 3, "penalties": 1}
                        for number in range(1, 10)
                    ],
                ],
            },
            {
                "name": "two-nine-combo",
                "front_gid": 31796, "back_gid": 31794,
                "package_numbers": list(range(1, 19)),
                "garmin_holes": [
                    *[
                        {"number": number, "strokes": 5, "putts": 2, "penalties": 0}
                        for number in range(1, 10)
                    ],
                    *[
                        {"number": number + 9, "strokes": 7, "putts": 3, "penalties": 1}
                        for number in range(1, 10)
                    ],
                ],
            },
            {
                "name": "nine-loop-second-lap",
                "front_gid": 31796, "back_gid": 31796,
                "package_numbers": list(range(1, 19)),
                "garmin_holes": [
                    *[
                        {"number": number, "strokes": 5, "putts": 2, "penalties": 0}
                        for number in range(1, 10)
                    ],
                    *[
                        {"number": number + 9, "strokes": 7, "putts": 3, "penalties": 1}
                        for number in range(1, 10)
                    ],
                ],
            },
        )

        for case in cases:
            with self.subTest(shape=case["name"]), TemporaryDirectory() as tmp:
                root = Path(tmp)
                round_id = f"display-{case['name']}"
                data = HistoryData(
                    raw_rounds=[],
                    rounds=[
                        {
                            "id": round_id,
                            "merged": True,
                            "frontNineGlobalCourseId": case["front_gid"],
                            "backNineGlobalCourseId": case["back_gid"],
                            "holes": case["garmin_holes"],
                        }
                    ],
                    shots=[],
                )
                append_event_batch(
                    round_id,
                    [
                        {
                            "eventId": f"{round_id}-{hole}",
                            "roundId": round_id,
                            "hole": hole,
                            "kind": "score",
                            "payload": {"strokes": 5 if hole <= 9 else 7},
                        }
                        for hole in case["package_numbers"]
                    ],
                    idempotency_key=round_id,
                    root=root,
                )

                result = reconcile_mobile_round_events(round_id, data, root=root)

                self.assertEqual(result["annotationSuggestions"], [])
                self.assertEqual(result["localOnly"], [])
                self.assertEqual(result["conflicts"], [])
                self.assertEqual(
                    [row["hole"] for row in result["matched"]],
                    case["package_numbers"],
                )

    def test_missing_penalty_matches_local_zero_without_writing_a_correction(self) -> None:
        # C74 / C53: an absent Garmin penalty has effective value 0.
        data = HistoryData(raw_rounds=[], rounds=[{
            "id": "empty-penalty", "holes": [
                {"number": 1, "strokes": 4, "putts": 2, "penalties": None},
            ],
        }], shots=[])
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch("empty-penalty", [{
                "eventId": "zero-penalty", "roundId": "empty-penalty", "hole": 1,
                "kind": "penalty", "payload": {"penalties": 0},
            }], idempotency_key="empty-penalty", root=root)
            result = reconcile_mobile_round_events("empty-penalty", data, root=root)
            self.assertEqual(result["annotationSuggestions"], [])
            self.assertEqual([row["eventId"] for row in result["matched"]], ["zero-penalty"])
            applied = apply_mobile_reconciliation_suggestions(
                "empty-penalty", data, root=root, annotations_root=root, data_loader=lambda: data,
            )
            self.assertEqual(applied["appliedCount"], 0)
            self.assertEqual(list_annotation_records(root=root), [])

    def test_score_and_putts_match_corrections_written_elsewhere(self) -> None:
        # C74: raw 6/3 corrected to 5/2 must match local 5/2, with no new suggestions.
        data = HistoryData(raw_rounds=[], rounds=[{
            "id": "corrected", "ids": ["source-card"], "holes": [
                {"number": 1, "strokes": 6, "putts": 3, "penalties": 0},
            ],
        }], shots=[])
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for kind, value in (("score", 5), ("putt", 2)):
                add_annotation("hole", "source-card:1", f"{kind}_correction", {"to": value},
                               root=root, data_loader=lambda: data)
            append_event_batch("corrected", [
                {"eventId": "local-score", "roundId": "corrected", "hole": 1,
                 "kind": "score", "payload": {"strokes": 5}},
                {"eventId": "local-putt", "roundId": "corrected", "hole": 1,
                 "kind": "putt", "payload": {"putts": 2}},
            ], idempotency_key="corrected", root=root)
            result = reconcile_mobile_round_events("corrected", data, root=root)
            for kind in ("score", "putt"):
                with self.subTest(kind=kind):
                    self.assertEqual([s for s in result["annotationSuggestions"] if s["kind"] == f"{kind}_correction"], [])
            self.assertEqual({row["eventId"] for row in result["matched"]}, {"local-score", "local-putt"})

    def test_back_then_front_nines_use_display_holes_for_reconciliation_and_audit(self) -> None:
        # C74 / hole_sides: first physical 10 -> display 1; second physical 1 -> display 10.
        # Legacy merged rows repeat 10..18; normalised rows retain physical numbers in localHole.
        for legacy in (True, False):
            with self.subTest(legacy=legacy), TemporaryDirectory() as tmp:
                root = Path(tmp)
                data = HistoryData(raw_rounds=[], rounds=[{
                    "id": "merged", "ids": ["back-card", "front-card"], "merged": True,
                    "holes": [
                        {"number": n + 9 if legacy else n, "localHole": n + 9,
                         "strokes": 5, "putts": 2, "penalties": 1} for n in range(1, 10)
                    ] + [
                        {"number": n + 9, "strokes": 7, "putts": 3, "penalties": 0}
                        for n in range(1, 10)
                    ],
                }], shots=[])
                append_event_batch("merged", [
                    {"eventId": f"{hole}-{kind}", "roundId": "merged", "hole": hole,
                     "kind": kind, "payload": {field: value}}
                    for hole, values in ((1, (5, 2, 1)), (10, (7, 3, 0)))
                    for kind, field, value in zip(
                        ("score", "putt", "penalty"), ("strokes", "putts", "penalties"), values,
                    )
                ], idempotency_key="merged", root=root)
                result = reconcile_mobile_round_events("merged", data, root=root)
                self.assertEqual(result["annotationSuggestions"], [])
                self.assertEqual({row["ref"] for row in result["matched"]}, {"merged:1", "merged:10"})
                self.assertEqual(len(result["matched"]), 6)
                for hole, total in ((1, 6), (10, 8)):
                    add_annotation("hole", f"merged:{hole}", "score_correction", {"to": total},
                                   root=root, data_loader=lambda: data)
                records = list_annotation_records(root=root)
                self.assertEqual(
                    [(r["audit"]["entries"][0]["hole"], r["audit"]["entries"][0]["before"])
                     for r in records], [(1, 5), (10, 7)],
                )
                corrected = corrected_history_data(data, annotations_root=root, corrections_root=root)
                self.assertEqual([corrected.rounds[0]["holes"][i]["strokes"] for i in (0, 9)], [6, 8])

    def test_penalty_reconciliation_only_suggests_effective_value_conflicts(self) -> None:
        data = HistoryData(
            raw_rounds=[{"id": "penalty-round", "hasShots": False}],
            rounds=[
                {
                    "id": "penalty-round",
                    "ids": ["penalty-round"],
                    "holes": [
                        {"number": 1, "strokes": 6, "putts": 2, "penalties": 1},
                        {"number": 2, "strokes": 6, "putts": 2, "penalties": 0},
                    ],
                }
            ],
            shots=[],
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "penalty-round",
                [
                    {
                        "eventId": "same-penalty",
                        "roundId": "penalty-round",
                        "hole": 1,
                        "kind": "penalty",
                        "payload": {"penalties": 1},
                    },
                    {
                        "eventId": "different-penalty",
                        "roundId": "penalty-round",
                        "hole": 2,
                        "kind": "penalty",
                        "payload": {"penalties": 1},
                    },
                ],
                idempotency_key="penalty-reconciliation",
                root=root,
            )

            result = reconcile_mobile_round_events("penalty-round", data, root=root)
            applied = apply_mobile_reconciliation_suggestions(
                "penalty-round",
                data,
                suggestion_ids=["different-penalty:penalty-correction"],
                root=root,
                annotations_root=root,
            )
            corrected = corrected_history_data(data, annotations_root=root, corrections_root=root)

        suggestions = {row["id"]: row for row in result["annotationSuggestions"]}
        self.assertNotIn("same-penalty:penalty-correction", suggestions)
        self.assertEqual(suggestions["different-penalty:penalty-correction"]["payload"]["strokes"], 1)
        self.assertEqual(applied["appliedCount"], 1)
        self.assertEqual(corrected.rounds[0]["holes"][1]["penalties"], 1)

    def test_concurrent_reconciliation_apply_dedupes_annotation_and_decision_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "concurrent-audit",
                        "roundId": "900001",
                        "hole": 3,
                        "kind": "club",
                        "payload": {
                            "clubName": "9I",
                            "decisionId": "900001:3:concurrent",
                            "decision": {
                                "decisionId": "900001:3:concurrent",
                                "sourceRef": "900001:3",
                                "shotType": "tee",
                                "phase": "tee_shot",
                                "selectedOptionId": "stock",
                                "selectedOption": {"id": "stock"},
                                "options": [{"id": "safe"}, {"id": "stock"}, {"id": "attack"}],
                                "confidence": {"level": "medium"},
                                "evidence": [{"sourceRefs": ["900001:3"]}],
                            },
                            "actualShot": {
                                "roundId": "900001",
                                "hole": 3,
                                "shotOrder": 1,
                                "clubName": "9I",
                                "meters": 146.0,
                                "end": {"lie": "Bunker"},
                            },
                        },
                    },
                ],
                idempotency_key="concurrent-reconciliation",
                root=root,
            )
            barrier = threading.Barrier(2)
            results: list[dict[str, object]] = []

            from ai_caddie.caddie import mobile_reconciliation

            original_add = mobile_reconciliation.add_annotation

            def wait_then_add(*args: object, **kwargs: object) -> dict[str, object]:
                barrier.wait(timeout=5)
                return original_add(*args, **kwargs)

            def apply_once() -> None:
                results.append(
                    apply_mobile_reconciliation_suggestions(
                        "900001",
                        fixture_history_data(),
                        suggestion_ids=["concurrent-audit:caddie-feedback"],
                        root=root,
                        annotations_root=root,
                        decision_audit_root=root,
                    )
                )

            with patch.object(mobile_reconciliation, "add_annotation", side_effect=wait_then_add):
                threads = [threading.Thread(target=apply_once) for _ in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

            annotations = list_annotations(root=root)
            audits = list_decision_audits(root=root)

        self.assertEqual(len(results), 2)
        self.assertEqual(sorted(result["decisionAuditCount"] for result in results), [0, 1])
        self.assertEqual(len(annotations), 1)
        self.assertEqual(len(audits), 1)
    def test_reconciliation_skips_non_utf8_torn_bytes_and_processes_later_row(self) -> None:
        from ai_caddie.caddie.mobile_live import mobile_event_log

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = mobile_event_log(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            durable_row = {
                "roundId": "900001",
                "idempotencyKey": "later-note",
                "serverSequence": 7,
                "event": {
                    "eventId": "later-note",
                    "roundId": "900001",
                    "hole": 7,
                    "kind": "note",
                    "payload": {"note": "Process the valid row after corrupt bytes."},
                },
            }
            path.write_bytes(
                b'\xff\xfe{"torn":\n'
                + json.dumps(durable_row, sort_keys=True).encode("utf-8")
                + b"\n"
            )

            try:
                rows = _event_rows("900001", root=root)
                result = reconcile_mobile_round_events(
                    "900001",
                    fixture_history_data(),
                    root=root,
                )
            except UnicodeDecodeError as exc:
                self.fail(f"reconciliation raised UnicodeDecodeError: {exc}")

        self.assertEqual(rows[0]["eventId"], "later-note")
        self.assertEqual(rows[0]["serverSequence"], 7)
        suggestions = {row["id"]: row for row in result["annotationSuggestions"]}
        self.assertEqual(
            suggestions["later-note:hole-note"]["payload"]["text"],
            "Process the valid row after corrupt bytes.",
        )

    def test_reconciles_local_events_against_synced_round_facts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "score-conflict",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "score",
                        "payload": {"strokes": 5},
                    },
                    {
                        "eventId": "club-match",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "club",
                        "payload": {"clubName": "1D"},
                    },
                    {
                        "eventId": "local-only-club",
                        "roundId": "900001",
                        "hole": 3,
                        "kind": "club",
                        "payload": {
                            "clubName": "9I",
                            "decisionId": "900001:3:1",
                            "actualShot": {"club": "9I", "result": "short"},
                        },
                    },
                    {
                        "eventId": "putt-conflict",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "putt",
                        "payload": {"putts": 3},
                    },
                    {
                        "eventId": "club-correction",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "club",
                        "payload": {"clubName": "9I"},
                    },
                ],
                idempotency_key="batch-1",
                root=root,
            )

            result = reconcile_mobile_round_events(
                "900001",
                fixture_history_data(),
                root=root,
            )

        self.assertEqual(result["schema"], "ai-caddie-mobile-reconciliation-v1")
        self.assertEqual(result["roundId"], "900001")
        self.assertEqual(result["summary"]["conflictCount"], 2)
        self.assertEqual(result["conflicts"][0]["eventId"], "score-conflict")
        self.assertEqual(result["conflicts"][0]["kind"], "score")
        self.assertEqual(result["conflicts"][0]["localValue"], 5)
        self.assertEqual(result["conflicts"][0]["garminValue"], 4)
        self.assertEqual(result["matched"][0]["eventId"], "club-match")
        self.assertEqual(result["localOnly"][0]["eventId"], "local-only-club")
        self.assertIn("900001:2:1", {row["ref"] for row in result["garminOnly"]})
        self.assertEqual(result["candidateDecisionAudits"][0]["decisionId"], "900001:3:1")
        suggestions = {row["id"]: row for row in result["annotationSuggestions"]}
        self.assertEqual(result["summary"]["annotationSuggestionCount"], 4)
        self.assertEqual(suggestions["score-conflict:score-correction"]["kind"], "score_correction")
        self.assertEqual(suggestions["score-conflict:score-correction"]["targetId"], "900001:1")
        self.assertEqual(suggestions["putt-conflict:putt-correction"]["kind"], "putt_correction")
        self.assertEqual(suggestions["putt-conflict:putt-correction"]["payload"]["from"], 2)
        self.assertEqual(suggestions["putt-conflict:putt-correction"]["payload"]["to"], 3)
        self.assertEqual(suggestions["club-correction:club-correction"]["kind"], "club_correction")
        self.assertEqual(suggestions["club-correction:club-correction"]["targetId"], "900001:1:2")
        self.assertEqual(suggestions["local-only-club:caddie-feedback"]["kind"], "caddie_feedback")

    def test_reconciliation_normalizes_legacy_mobile_payload_aliases(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "legacy-putt-conflict",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "putt",
                        "payload": {"count": 3},
                    },
                    {
                        "eventId": "legacy-penalty",
                        "roundId": "900001",
                        "hole": 2,
                        "kind": "penalty",
                        "payload": {"count": 1},
                    },
                    {
                        "eventId": "legacy-note",
                        "roundId": "900001",
                        "hole": 2,
                        "kind": "note",
                        "payload": {"text": "blocked by trees"},
                    },
                ],
                idempotency_key="legacy-aliases",
                root=root,
            )

            result = reconcile_mobile_round_events("900001", fixture_history_data(), root=root)

        conflicts = {row["eventId"]: row for row in result["conflicts"]}
        local_only = {row["eventId"]: row for row in result["localOnly"]}
        suggestions = {row["id"]: row for row in result["annotationSuggestions"]}
        self.assertEqual(conflicts["legacy-putt-conflict"]["localValue"], 3)
        # C74: absent Garmin penalty is effective 0, so local 1 is a 0 -> 1 conflict.
        self.assertEqual(conflicts["legacy-penalty"]["localValue"], 1)
        self.assertEqual(conflicts["legacy-penalty"]["garminValue"], 0)
        self.assertEqual(local_only["legacy-note"]["localValue"], "blocked by trees")
        self.assertEqual(suggestions["legacy-penalty:penalty-correction"]["payload"]["strokes"], 1)
        self.assertEqual(suggestions["legacy-note:hole-note"]["kind"], "hole_note")
        self.assertEqual(suggestions["legacy-note:hole-note"]["targetId"], "900001:2")
        self.assertEqual(suggestions["legacy-note:hole-note"]["payload"]["text"], "blocked by trees")
        self.assertEqual(suggestions["legacy-note:hole-note"]["payload"]["sourceEventId"], "legacy-note")

    def test_reconciliation_preserves_local_score_and_putts_when_garmin_hole_is_missing(self) -> None:
        data = HistoryData(
            raw_rounds=[{"id": "live-local", "hasShots": False}],
            rounds=[{"id": "live-local", "ids": ["live-local"], "holes": []}],
            shots=[],
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "live-local",
                [
                    {
                        "eventId": "offline-score",
                        "roundId": "live-local",
                        "hole": 4,
                        "kind": "score",
                        "payload": {"strokes": 5},
                    },
                    {
                        "eventId": "offline-putt",
                        "roundId": "live-local",
                        "hole": 4,
                        "kind": "putt",
                        "payload": {"putts": 2},
                    },
                ],
                idempotency_key="offline-score-putt",
                root=root,
            )

            result = reconcile_mobile_round_events("live-local", data, root=root)
            applied = apply_mobile_reconciliation_suggestions("live-local", data, root=root, annotations_root=root)

        suggestions = {row["id"]: row for row in result["annotationSuggestions"]}
        self.assertEqual(result["summary"]["localOnlyCount"], 2)
        self.assertEqual(result["summary"]["annotationSuggestionCount"], 2)
        self.assertEqual(suggestions["offline-score:score-correction"]["targetId"], "live-local:4")
        self.assertEqual(suggestions["offline-score:score-correction"]["payload"]["from"], None)
        self.assertEqual(suggestions["offline-score:score-correction"]["payload"]["to"], 5)
        self.assertEqual(suggestions["offline-putt:putt-correction"]["targetId"], "live-local:4")
        self.assertEqual(suggestions["offline-putt:putt-correction"]["payload"]["to"], 2)
        self.assertEqual(applied["appliedCount"], 2)
        annotations = {row["kind"]: row for row in applied["annotations"]}
        self.assertEqual(annotations["score_correction"]["targetId"], "live-local:4")
        self.assertEqual(annotations["putt_correction"]["targetId"], "live-local:4")

    def test_reconciliation_matches_scorecard_id_club_name_shots(self) -> None:
        data = HistoryData(
            raw_rounds=[{"id": "700001", "hasShots": True}],
            rounds=[{"id": "700001", "ids": ["700001"], "holes": [{"number": 1, "strokes": 4, "putts": 2}]}],
            shots=[{"scorecardId": 700001, "hole": 1, "clubName": "8I"}],
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "700001",
                [
                    {
                        "eventId": "raw-shape-club",
                        "roundId": "700001",
                        "hole": 1,
                        "kind": "club",
                        "payload": {"clubName": "8I"},
                    },
                ],
                idempotency_key="raw-shape-club",
                root=root,
            )

            result = reconcile_mobile_round_events("700001", data, root=root)

        self.assertEqual(result["matched"], [{"eventId": "raw-shape-club", "kind": "club", "hole": 1, "ref": "700001:1:1"}])
        self.assertEqual(result["localOnly"], [])
        self.assertEqual(result["garminOnly"], [])

    def test_reconciliation_suggests_hole_note_annotations_from_mobile_note_events(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "wind-note",
                        "roundId": "900001",
                        "hole": 7,
                        "kind": "note",
                        "payload": {"note": "Wind hurting; favor center green."},
                    },
                ],
                idempotency_key="note-batch",
                root=root,
            )

            result = reconcile_mobile_round_events("900001", fixture_history_data(), root=root)

        suggestions = {row["id"]: row for row in result["annotationSuggestions"]}
        self.assertEqual(result["summary"]["annotationSuggestionCount"], 1)
        self.assertEqual(suggestions["wind-note:hole-note"]["targetType"], "hole")
        self.assertEqual(suggestions["wind-note:hole-note"]["targetId"], "900001:7")
        self.assertEqual(suggestions["wind-note:hole-note"]["kind"], "hole_note")
        self.assertEqual(suggestions["wind-note:hole-note"]["payload"]["text"], "Wind hurting; favor center green.")
        self.assertEqual(suggestions["wind-note:hole-note"]["payload"]["sourceEventId"], "wind-note")

    def test_reconciliation_suggests_media_context_annotations_from_photo_video_events(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "photo-lie",
                        "roundId": "900001",
                        "hole": 7,
                        "kind": "photo",
                        "payload": {
                            "assetLocalId": "900001-7-photo.bin",
                            "mediaType": "photo",
                            "source": "ios_camera",
                            "fileURL": "file:///private/var/mobile/tmp/lie.jpg",
                            "mediaId": "media-photo-1",
                            "note": "Ball sitting down in rough.",
                        },
                    },
                    {
                        "eventId": "video-slope",
                        "roundId": "900001",
                        "hole": 7,
                        "kind": "video",
                        "payload": {
                            "assetLocalId": "900001-7-video.bin",
                            "mediaType": "video",
                            "source": "ios_camera",
                            "fileURL": "file:///private/var/mobile/tmp/slope.mov",
                            "mediaId": "media-video-1",
                            "durationS": 8,
                            "note": "Green slopes hard left.",
                        },
                    },
                    {
                        "eventId": "photo-not-uploaded",
                        "roundId": "900001",
                        "hole": 8,
                        "kind": "photo",
                        "payload": {
                            "assetLocalId": "900001-8-photo.bin",
                            "mediaType": "photo",
                            "source": "ios_camera",
                            "fileURL": "file:///private/var/mobile/tmp/not-uploaded.jpg",
                            "note": "Offline capture not uploaded yet.",
                        },
                    },
                    {
                        "eventId": "photo-blank-media-id",
                        "roundId": "900001",
                        "hole": 8,
                        "kind": "photo",
                        "payload": {
                            "assetLocalId": "900001-8-blank-photo.bin",
                            "mediaType": "photo",
                            "source": "ios_camera",
                            "fileURL": "file:///private/var/mobile/tmp/blank.jpg",
                            "mediaId": "   ",
                            "note": "Blank media id should not be durable.",
                        },
                    },
                ],
                idempotency_key="media-context",
                root=root,
            )

            result = reconcile_mobile_round_events("900001", fixture_history_data(), root=root)

        local_only = {row["eventId"]: row for row in result["localOnly"]}
        suggestions = {row["id"]: row for row in result["annotationSuggestions"]}
        response_text = str(result)

        self.assertEqual(local_only["photo-lie"]["kind"], "photo")
        self.assertEqual(local_only["photo-lie"]["localValue"], "media-photo-1")
        self.assertEqual(local_only["photo-lie"]["mediaType"], "photo")
        self.assertEqual(local_only["photo-not-uploaded"]["localValue"], "photo")
        self.assertEqual(local_only["photo-not-uploaded"]["mediaState"], "missing_media_id")
        self.assertEqual(local_only["photo-blank-media-id"]["localValue"], "photo")
        self.assertEqual(local_only["photo-blank-media-id"]["mediaState"], "missing_media_id")
        self.assertNotIn("mediaId", local_only["photo-blank-media-id"])
        self.assertNotIn("fileURL", response_text)
        self.assertNotIn("file://", response_text)
        self.assertNotIn("/private/var", response_text)
        self.assertNotIn("lie.jpg", response_text)
        self.assertNotIn("slope.mov", response_text)
        self.assertNotIn("not-uploaded.jpg", response_text)
        self.assertNotIn("blank.jpg", response_text)
        self.assertNotIn("900001-7-photo.bin", response_text)
        self.assertNotIn("900001-7-video.bin", response_text)
        self.assertNotIn("900001-8-photo.bin", response_text)
        self.assertNotIn("900001-8-blank-photo.bin", response_text)

        self.assertEqual(result["summary"]["annotationSuggestionCount"], 2)
        self.assertNotIn("photo-not-uploaded:media-context", suggestions)
        self.assertNotIn("photo-blank-media-id:media-context", suggestions)
        self.assertEqual(suggestions["photo-lie:media-context"]["targetType"], "hole")
        self.assertEqual(suggestions["photo-lie:media-context"]["targetId"], "900001:7")
        self.assertEqual(suggestions["photo-lie:media-context"]["kind"], "hole_note")
        self.assertEqual(suggestions["photo-lie:media-context"]["confidence"], "medium")
        self.assertEqual(
            suggestions["photo-lie:media-context"]["payload"],
            {
                "mediaType": "photo",
                "mediaId": "media-photo-1",
                "text": "Ball sitting down in rough.",
                "sourceEventId": "photo-lie",
                "source": "mobile_reconciliation",
                "sourceSuggestionId": "photo-lie:media-context",
            },
        )
        self.assertEqual(suggestions["video-slope:media-context"]["payload"]["durationS"], 8)

    def test_apply_reconciliation_writes_media_context_as_hole_note_idempotently(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "photo-lie",
                        "roundId": "900001",
                        "hole": 7,
                        "kind": "photo",
                        "payload": {
                            "assetLocalId": "900001-7-photo.bin",
                            "mediaType": "photo",
                            "source": "ios_camera",
                            "fileURL": "file:///private/var/mobile/tmp/lie.jpg",
                            "mediaId": "media-photo-1",
                            "note": "Ball sitting down in rough.",
                        },
                    },
                ],
                idempotency_key="media-context-apply",
                root=root,
            )

            first = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["photo-lie:media-context"],
                root=root,
                annotations_root=root,
            )
            second = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["photo-lie:media-context"],
                root=root,
                annotations_root=root,
            )
            annotations = list_annotations(root=root)

        self.assertEqual(first["appliedCount"], 1)
        self.assertEqual(second["appliedCount"], 0)
        self.assertEqual(second["skippedSuggestionIds"], ["photo-lie:media-context"])
        self.assertEqual(annotations[0]["targetType"], "hole")
        self.assertEqual(annotations[0]["targetId"], "900001:7")
        self.assertEqual(annotations[0]["kind"], "hole_note")
        self.assertEqual(annotations[0]["payload"]["mediaType"], "photo")
        self.assertEqual(annotations[0]["payload"]["mediaId"], "media-photo-1")
        self.assertEqual(annotations[0]["payload"]["text"], "Ball sitting down in rough.")
        self.assertNotIn("fileURL", str(annotations[0]["payload"]))
        self.assertNotIn("assetLocalId", str(annotations[0]["payload"]))
        self.assertNotIn("900001-7-photo.bin", str(annotations[0]["payload"]))

    def test_applies_selected_reconciliation_suggestions_as_annotations_idempotently(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "putt-conflict",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "putt",
                        "payload": {"putts": 3},
                    },
                    {
                        "eventId": "score-conflict",
                        "roundId": "900001",
                        "hole": 1,
                        "kind": "score",
                        "payload": {"strokes": 5},
                    },
                ],
                idempotency_key="batch-apply",
                root=root,
            )

            first = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["putt-conflict:putt-correction", "score-conflict:score-correction"],
                root=root,
                annotations_root=root,
            )
            second = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["putt-conflict:putt-correction"],
                root=root,
                annotations_root=root,
            )
            annotations = list_annotations(root=root)

        self.assertEqual(first["schema"], "ai-caddie-mobile-reconciliation-apply-v1")
        self.assertEqual(first["appliedCount"], 2)
        self.assertEqual(first["skippedCount"], 0)
        self.assertEqual(second["appliedCount"], 0)
        self.assertEqual(second["skippedCount"], 1)
        self.assertEqual([row["kind"] for row in annotations], ["putt_correction", "score_correction"])
        self.assertEqual(annotations[0]["payload"]["sourceSuggestionId"], "putt-conflict:putt-correction")

    def test_apply_reconciliation_persists_caddie_feedback_as_decision_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "offline-shot-audit",
                        "roundId": "900001",
                        "hole": 3,
                        "kind": "club",
                        "payload": {
                            "clubName": "9I",
                            "decisionId": "900001:3:tee",
                            "decision": {
                                "decisionId": "900001:3:tee",
                                "sourceRef": "900001:3",
                                "shotType": "tee",
                                "phase": "tee_shot",
                                "selectedOptionId": "stock",
                                "selectedOption": {
                                    "id": "stock",
                                    "carry_m": 145.0,
                                    "clubRecommendation": {"clubs": [{"clubName": "9I"}]},
                                },
                                "options": [
                                    {"id": "safe", "carry_m": 120.0},
                                    {"id": "stock", "carry_m": 145.0},
                                    {"id": "attack", "carry_m": 175.0},
                                ],
                                "confidence": {"level": "medium"},
                                "evidence": [{"sourceRefs": ["900001:3"]}],
                            },
                            "actualShot": {
                                "roundId": "900001",
                                "hole": 3,
                                "shotOrder": 1,
                                "clubName": "9I",
                                "meters": 146.0,
                                "end": {"lie": "Bunker", "feature": {"surface": {"kind": "bunker"}, "nearRisks": []}},
                            },
                        },
                    },
                ],
                idempotency_key="audit-apply",
                root=root,
            )

            result = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["offline-shot-audit:caddie-feedback"],
                root=root,
                annotations_root=root,
                decision_audit_root=root,
            )
            audits = list_decision_audits(root=root)

        self.assertEqual(result["appliedCount"], 1)
        self.assertEqual(result["decisionAuditCount"], 1)
        self.assertEqual(result["decisionAudits"][0]["decisionId"], "900001:3:tee")
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0]["classification"], "execution")
        self.assertEqual(audits[0]["sourceRef"], "900001:3")
        self.assertEqual(audits[0]["actualShotRefs"], ["900001:3:1"])

    def test_apply_reconciliation_resolves_online_decision_id_without_embedded_copy(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_decision(
                {
                    "decisionId": "900001:3:tee-online",
                    "sourceRef": "900001:3",
                    "shotType": "tee",
                    "phase": "tee_shot",
                    "selectedOptionId": "stock",
                    "selectedOption": {
                        "id": "stock",
                        "carry_m": 145.0,
                        "clubRecommendation": {"clubs": [{"clubName": "9I"}]},
                    },
                    "options": [
                        {"id": "safe", "carry_m": 120.0},
                        {"id": "stock", "carry_m": 145.0},
                        {"id": "attack", "carry_m": 175.0},
                    ],
                    "confidence": {"level": "medium"},
                    "evidenceRefs": ["900001:3"],
                    "auditCriteria": [
                        {"label": "club_match", "rule": "match selected club"},
                        {"label": "carry_window", "rule": "match selected carry"},
                        {"label": "avoid_zones", "rule": "avoid known risks"},
                    ],
                },
                root=root,
            )
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "online-shot-audit",
                        "roundId": "900001",
                        "hole": 3,
                        "kind": "club",
                        "payload": {
                            "clubName": "9I",
                            "decisionId": "900001:3:tee-online",
                            "actualShot": {
                                "roundId": "900001",
                                "hole": 3,
                                "shotOrder": 1,
                                "clubName": "9I",
                                "meters": 146.0,
                                "end": {"lie": "fairway"},
                            },
                        },
                    },
                ],
                idempotency_key="online-audit-apply",
                root=root,
            )

            result = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["online-shot-audit:caddie-feedback"],
                root=root,
                annotations_root=root,
                decision_audit_root=root,
                decision_ledger_root=root,
            )
            audits = list_decision_audits(root=root)

        self.assertEqual(result["decisionAuditCount"], 1)
        self.assertEqual(audits[0]["decisionId"], "900001:3:tee-online")
        self.assertEqual(audits[0]["classification"], "unknown")
        self.assertEqual(audits[0]["selectedOptionId"], "stock")
        self.assertEqual(audits[0]["actualShotRefs"], ["900001:3:1"])

    def test_apply_reconciliation_writes_mobile_note_as_hole_note_idempotently(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_event_batch(
                "900001",
                [
                    {
                        "eventId": "strategy-note",
                        "roundId": "900001",
                        "hole": 7,
                        "kind": "note",
                        "payload": {"note": "Good miss is long-left today."},
                    },
                ],
                idempotency_key="note-apply",
                root=root,
            )

            first = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["strategy-note:hole-note"],
                root=root,
                annotations_root=root,
            )
            second = apply_mobile_reconciliation_suggestions(
                "900001",
                fixture_history_data(),
                suggestion_ids=["strategy-note:hole-note"],
                root=root,
                annotations_root=root,
            )
            annotations = list_annotations(root=root)

        self.assertEqual(first["appliedCount"], 1)
        self.assertEqual(second["appliedCount"], 0)
        self.assertEqual(second["skippedSuggestionIds"], ["strategy-note:hole-note"])
        self.assertEqual(annotations[0]["targetType"], "hole")
        self.assertEqual(annotations[0]["targetId"], "900001:7")
        self.assertEqual(annotations[0]["kind"], "hole_note")
        self.assertEqual(annotations[0]["payload"]["text"], "Good miss is long-left today.")
        self.assertEqual(annotations[0]["payload"]["sourceEventId"], "strategy-note")


if __name__ == "__main__":
    unittest.main()
