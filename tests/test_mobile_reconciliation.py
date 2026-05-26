from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.fixtures import fixture_history_data
from ai_caddie.annotations import list_annotations
from ai_caddie.mobile_live import append_event_batch
from ai_caddie.mobile_reconciliation import apply_mobile_reconciliation_suggestions, reconcile_mobile_round_events


class MobileReconciliationTests(unittest.TestCase):
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
        self.assertEqual(local_only["legacy-penalty"]["localValue"], 1)
        self.assertEqual(local_only["legacy-note"]["localValue"], "blocked by trees")
        self.assertEqual(suggestions["legacy-penalty:penalty-correction"]["payload"]["strokes"], 1)
        self.assertEqual(suggestions["legacy-note:hole-note"]["kind"], "hole_note")
        self.assertEqual(suggestions["legacy-note:hole-note"]["targetId"], "900001:2")
        self.assertEqual(suggestions["legacy-note:hole-note"]["payload"]["text"], "blocked by trees")
        self.assertEqual(suggestions["legacy-note:hole-note"]["payload"]["sourceEventId"], "legacy-note")

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
