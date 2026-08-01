from pathlib import Path
import unittest


IOS_VIEWS = Path("mobile/ios/AICaddie/Views")
WATCH_VIEWS = Path("mobile/ios/AICaddieWatch/Views")


class NativeVisualParityTests(unittest.TestCase):
    def test_watch_score_header_reserves_system_time_area(self) -> None:
        source = (WATCH_VIEWS / "WatchScoreHoleView.swift").read_text(encoding="utf-8")

        self.assertIn("WatchScoreHoleLayout.systemTimeTrailingClearance", source)
        self.assertIn(
            ".padding(.trailing, WatchScoreHoleLayout.systemTimeTrailingClearance)",
            source,
        )

    def test_watch_round_tools_button_has_visible_boundary(self) -> None:
        source = (WATCH_VIEWS / "WatchRoundContainerView.swift").read_text(encoding="utf-8")
        button = source.split("private var roundToolsButton", 1)[1]

        self.assertIn("Circle().fill(Color.white.opacity", button)
        self.assertIn("Circle().stroke(Color.white.opacity", button)

    def test_live_hole_more_adjust_label_matches_compact_approved_card(self) -> None:
        source = (IOS_VIEWS / "CurrentHoleView.swift").read_text(encoding="utf-8")

        self.assertNotIn("更多调整(球杆 / 打法 / 球位 / 距离 / 目标 / 备注)", source)
        self.assertIn('Label("更多调整", systemImage: "slider.horizontal.3")', source)
        self.assertIn('Text("球杆 · 打法 · 球位 · 距离 · 目标 · 备注")', source)


if __name__ == "__main__":
    unittest.main()
