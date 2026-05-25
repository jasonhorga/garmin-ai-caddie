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
            ("decision", "round-1:7:2", "caddie_feedback", {"rating": "too_aggressive"}),
        ]

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [
                add_annotation(target_type, target_id, kind, payload, root=root)
                for target_type, target_id, kind, payload in cases
            ]

            self.assertEqual(len(records), 8)
            self.assertEqual(len(list_annotations(root=root)), 8)
            self.assertEqual(len(annotation_file(root).read_text(encoding="utf-8").splitlines()), 8)
            for record, (target_type, target_id, kind, payload) in zip(records, cases):
                self.assertTrue(record["id"])
                self.assertTrue(record["createdAt"].endswith("Z"))
                self.assertEqual(record["targetType"], target_type)
                self.assertEqual(record["targetId"], target_id)
                self.assertEqual(record["kind"], kind)
                self.assertEqual(record["payload"], payload)
                self.assertEqual(record["source"], "manual")

            target_records = annotations_for_target("hole", "round-1:7", root=root)
            self.assertEqual([row["kind"] for row in target_records], ["hole_note", "issue_tag", "penalty_correction"])

    def test_rejects_invalid_target_type_and_kind(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaises(ValueError):
                add_annotation("course", "course-1", "round_note", {"text": "bad"}, root=root)
            with self.assertRaises(ValueError):
                add_annotation("round", "round-1", "swing_thought", {"text": "bad"}, root=root)

            self.assertEqual(list_annotations(root=root), [])


if __name__ == "__main__":
    unittest.main()
