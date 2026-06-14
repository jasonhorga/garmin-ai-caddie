from __future__ import annotations

import unittest

from ai_caddie.report_labels_zh import data_label_zh, issue_label_zh


class ReportLabelsZhTests(unittest.TestCase):
    def test_issue_label_maps_known_tokens(self) -> None:
        self.assertEqual(issue_label_zh("rough"), "长草脱困")
        self.assertEqual(issue_label_zh("bunker"), "沙坑救球")
        self.assertEqual(issue_label_zh("double_or_worse"), "双柏忌或更差")
        self.assertEqual(issue_label_zh("missing_shots"), "缺少击球数据")
        self.assertEqual(issue_label_zh("three_putt"), "三推")

    def test_issue_label_passes_through_unknown_tokens(self) -> None:
        self.assertEqual(issue_label_zh("totally_unknown_token"), "totally_unknown_token")

    def test_data_label_maps_known_and_passes_unknown(self) -> None:
        self.assertEqual(data_label_zh("shots"), "击球数据")
        self.assertEqual(data_label_zh("putts"), "推杆数据")
        self.assertEqual(data_label_zh("round_reference"), "球局引用")
        self.assertEqual(data_label_zh("period"), "时间段")
        self.assertEqual(data_label_zh("not_a_label"), "not_a_label")

    def test_issue_vocabulary_breadth(self) -> None:
        # A representative spread across the taxonomy must resolve to Chinese, so
        # report claims never leak a raw enum (the user's complaint).
        for token in ("approach_short", "tee_left", "ob", "water", "wind", "wrong_club"):
            self.assertNotEqual(issue_label_zh(token), token, token)


if __name__ == "__main__":
    unittest.main()
