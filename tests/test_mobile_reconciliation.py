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


class MobileReconciliationTests(unittest.TestCase):
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
        display storage; the second shape has two different nines and the third visits one nine
        twice (both still keep physical source holes in ``localHole``).
        """
        cases = (
            {
                "name": "back-nine-start",
                "package_numbers": list(range(1, 10)),
                "garmin_holes": [
                    *[
                        {"number": number + 9, "localHole": number + 9, "strokes": 5, "putts": 2, "penalties": 0}
                        for number in range(1, 10)
                    ],
                    *[
                        {"number": number + 9, "localHole": number, "strokes": 7, "putts": 3, "penalties": 1}
                        for number in range(1, 10)
                    ],
                ],
            },
            {
                "name": "two-nine-combo",
                "package_numbers": list(range(1, 19)),
                "garmin_holes": [
                    *[
                        {"number": number, "localHole": number, "strokes": 5, "putts": 2, "penalties": 0}
                        for number in range(1, 10)
                    ],
                    *[
                        {"number": number + 9, "localHole": number, "strokes": 7, "putts": 3, "penalties": 1}
                        for number in range(1, 10)
                    ],
                ],
            },
            {
                "name": "nine-loop-second-lap",
                "package_numbers": list(range(1, 19)),
                "garmin_holes": [
                    *[
                        {"number": number, "localHole": number, "strokes": 5, "putts": 2, "penalties": 0}
                        for number in range(1, 10)
                    ],
                    *[
                        {"number": number + 9, "localHole": number, "strokes": 7, "putts": 3, "penalties": 1}
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
            self.assertEqual(result["garminOnly"], [])
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
