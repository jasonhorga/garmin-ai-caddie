from __future__ import annotations

import unittest

from ai_caddie.reports.report_labels_zh import (
    audit_class_zh,
    audit_status_zh,
    data_label_zh,
    form_direction_zh,
    issue_label_zh,
    trend_dimension_zh,
)


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

    def test_audit_and_trend_closed_enums_map(self) -> None:
        self.assertEqual(audit_status_zh("fail"), "未达标")
        self.assertEqual(audit_status_zh("review"), "需复核")
        self.assertEqual(audit_class_zh("execution"), "执行偏差")
        self.assertEqual(audit_class_zh("strategy"), "策略偏差")
        self.assertEqual(trend_dimension_zh("issue"), "问题")
        self.assertEqual(trend_dimension_zh("club"), "球杆")
        self.assertEqual(form_direction_zh("improving"), "进步中")
        self.assertEqual(form_direction_zh("declining"), "下滑")

    def test_closed_enums_pass_through_open_identifiers(self) -> None:
        # Open decision identifiers (criterion labels, option ids) stay raw.
        self.assertEqual(audit_status_zh("avoid_zones"), "avoid_zones")
        self.assertEqual(audit_class_zh("stock"), "stock")
        self.assertEqual(trend_dimension_zh("1D"), "1D")

    def test_issue_vocabulary_breadth(self) -> None:
        # A representative spread across the taxonomy must resolve to Chinese, so
        # report claims never leak a raw enum (the user's complaint).
        for token in ("approach_short", "tee_left", "ob", "water", "wind", "wrong_club"):
            self.assertNotEqual(issue_label_zh(token), token, token)


if __name__ == "__main__":
    unittest.main()
