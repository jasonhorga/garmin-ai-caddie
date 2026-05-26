from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.annotations import (
    add_annotation,
    annotation_file,
    annotations_for_target,
    list_annotations,
)


class AnnotationStoreTests(unittest.TestCase):
    def test_creates_supported_manual_annotation_records_append_only(self) -> None:
        cases = [
            ("round", "round-1", "round_note", {"text": "good tempo"}),
            ("hole", "round-1:7", "hole_note", {"text": "left miss recurring"}),
            ("shot", "round-1:7:2", "shot_note", {"text": "blocked by tree"}),
            ("hole", "round-1:7", "issue_tag", {"tag": "approach_short"}),
            ("shot", "round-1:7:2", "club_correction", {"from": "8I", "to": "7I"}),
            ("shot", "round-1:7:2", "lie_correction", {"from": "rough", "to": "fairway"}),
            ("hole", "round-1:7", "penalty_correction", {"strokes": 1, "reason": "water"}),
            ("hole", "round-1:7", "putt_correction", {"from": 2, "to": 4}),
            ("hole", "round-1:7", "score_correction", {"from": 5, "to": 4}),
            ("hole", "round-1:7", "weather_context_note", {"text": "wind into from the left"}),
            ("hole", "round-1:7", "strategy_note", {"text": "intended target was right center"}),
            ("decision", "round-1:7:2", "caddie_feedback", {"rating": "too_aggressive"}),
        ]

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [
                add_annotation(target_type, target_id, kind, payload, root=root)
                for target_type, target_id, kind, payload in cases
            ]

            self.assertEqual(len(records), 12)
            self.assertEqual(len(list_annotations(root=root)), 12)
            self.assertEqual(len(annotation_file(root).read_text(encoding="utf-8").splitlines()), 12)
            for record, (target_type, target_id, kind, payload) in zip(records, cases):
                self.assertTrue(record["id"])
                self.assertTrue(record["createdAt"].endswith("Z"))
                self.assertEqual(record["targetType"], target_type)
                self.assertEqual(record["targetId"], target_id)
                self.assertEqual(record["kind"], kind)
                self.assertEqual(record["payload"], payload)
                self.assertEqual(record["source"], "manual")

            target_records = annotations_for_target("hole", "round-1:7", root=root)
            self.assertEqual(
                [row["kind"] for row in target_records],
                [
                    "hole_note",
                    "issue_tag",
                    "penalty_correction",
                    "putt_correction",
                    "score_correction",
                    "weather_context_note",
                    "strategy_note",
                ],
            )

    def test_rejects_invalid_target_type_and_kind(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaises(ValueError):
                add_annotation("course", "course-1", "round_note", {"text": "bad"}, root=root)
            with self.assertRaises(ValueError):
                add_annotation("round", "round-1", "swing_thought", {"text": "bad"}, root=root)

            self.assertEqual(list_annotations(root=root), [])

    def test_issue_tag_removal_records_are_append_only(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            added = add_annotation(
                "hole",
                "round-1:7",
                "issue_tag",
                {"tag": "approach_short"},
                root=root,
            )
            removed = add_annotation(
                "hole",
                "round-1:7",
                "issue_tag_removed",
                {"tag": "approach_short"},
                root=root,
            )

            records = list_annotations(root=root)

        self.assertEqual([row["kind"] for row in records], ["issue_tag", "issue_tag_removed"])
        self.assertEqual([row["id"] for row in records], [added["id"], removed["id"]])
        self.assertEqual(records[0]["payload"], {"tag": "approach_short"})
        self.assertEqual(records[1]["payload"], {"tag": "approach_short"})
        self.assertNotEqual(added["id"], removed["id"])

    def test_annotation_notes_redact_secret_like_values_before_storage(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = add_annotation(
                "hole",
                "round-1:7",
                "hole_note",
                {
                    "text": "cookie=session-value token=abc123 /home/player/raw.json",
                    "nested": {"summary": "connect-csrf-token: csrf-value"},
                },
                root=root,
            )
            raw = annotation_file(root).read_text(encoding="utf-8")

        combined = f"{record} {raw}"
        for forbidden in ["session-value", "abc123", "/home/player/raw.json", "csrf-value"]:
            self.assertNotIn(forbidden, combined)
        self.assertIn("[REDACTED]", combined)
        self.assertIn("[REDACTED_PATH]", combined)

    def test_existing_annotation_payloads_are_redacted_on_read(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = annotation_file(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                (
                    '{"id":"legacy","createdAt":"2026-05-25T00:00:00Z","targetType":"hole",'
                    '"targetId":"round-1:7","kind":"strategy_note",'
                    '"payload":{"text":"cookie=session-value token=abc123 /home/player/raw.json",'
                    '"nested":{"summary":"connect-csrf-token: csrf-value"}},'
                    '"source":"manual"}\n'
                ),
                encoding="utf-8",
            )

            records = list_annotations(root=root)
            target_records = annotations_for_target("hole", "round-1:7", root=root)

        combined = f"{records} {target_records}"
        for forbidden in ["session-value", "abc123", "/home/player/raw.json", "csrf-value"]:
            self.assertNotIn(forbidden, combined)
        self.assertIn("[REDACTED]", combined)
        self.assertIn("[REDACTED_PATH]", combined)


if __name__ == "__main__":
    unittest.main()
