from pathlib import Path
import unittest


IOS_VIEWS = Path("mobile/ios/AICaddie/Views")
WATCH_VIEWS = Path("mobile/ios/AICaddieWatch/Views")


class NativeVisualParityTests(unittest.TestCase):
    def test_real_review_capture_selects_current_history_instead_of_expired_date(self) -> None:
        ui_tests = Path("mobile/ios/AICaddieUITests")
        real_flow = (ui_tests / "RealFlowUITests.swift").read_text(encoding="utf-8")
        review_edit = (ui_tests / "ReviewEditUITests.swift").read_text(encoding="utf-8")

        for source in (real_flow, review_edit):
            self.assertNotIn("2026-06-11", source)
            self.assertIn("tapFirstRoundRow", source)

    def test_watch_score_header_reserves_system_time_area(self) -> None:
        source = (WATCH_VIEWS / "WatchScoreHoleView.swift").read_text(encoding="utf-8")

        self.assertIn("WatchScoreHoleLayout.systemTimeTrailingClearance", source)
        self.assertIn(
            ".padding(.trailing, WatchScoreHoleLayout.systemTimeTrailingClearance)",
            source,
        )

    def test_watch_round_tools_use_the_approved_shallow_long_press_entry(self) -> None:
        source = (WATCH_VIEWS / "WatchRoundContainerView.swift").read_text(encoding="utf-8")

        self.assertIn(".onLongPressGesture(minimumDuration: 0.6) { model.openMenu() }", source)
        self.assertIn('accessibilityAction(named: Text("球局工具"))', source)
        self.assertNotIn("private var roundToolsButton", source)

    def test_live_hole_more_adjust_label_matches_compact_approved_card(self) -> None:
        source = (IOS_VIEWS / "CurrentHoleView.swift").read_text(encoding="utf-8")

        self.assertNotIn("更多调整(球杆 / 打法 / 球位 / 距离 / 目标 / 备注)", source)
        self.assertIn('Label("更多调整", systemImage: "slider.horizontal.3")', source)
        self.assertIn('Text("球杆 · 打法 · 球位 · 距离 · 目标 · 备注")', source)

    def test_cached_watch_course_drives_the_approved_root_caddie_plan(self) -> None:
        store = Path("mobile/ios/AICaddieWatch/Services/WatchCourseStore.swift").read_text(
            encoding="utf-8"
        )
        container = (WATCH_VIEWS / "WatchRoundContainerView.swift").read_text(encoding="utf-8")

        self.assertIn("preparedCaddieOptions", store)
        self.assertIn("preparedRootCaddieLayerAvailable", container)
        self.assertIn("showPreparedPlan:", container)

    def test_real_review_capture_uses_the_same_first_hole_state_as_the_approved_edit_render(self) -> None:
        for relative_path in [
            "mobile/ios/AICaddieUITests/RealFlowUITests.swift",
            "mobile/ios/AICaddieUITests/ReviewEditUITests.swift",
        ]:
            source = Path(relative_path).read_text(encoding="utf-8")
            self.assertIn('app.buttons["round-review-hole-1"]', source)
            self.assertNotIn('app.buttons["round-review-hole-4"]', source)

    def test_watch_runtime_captures_caddie_from_the_downloaded_production_course(self) -> None:
        root = Path("mobile/ios/AICaddieWatch/Views/WatchUITestRoot.swift").read_text(
            encoding="utf-8"
        )
        workflow = Path(".github/workflows/watch-runtime.yml").read_text(encoding="utf-8")

        self.assertIn('"real-course-download-caddie"', root)
        self.assertIn('screen == "real-course-download-caddie"', root)
        self.assertIn(
            "launch_and_capture real-course-download-caddie watch-real-course-caddie.png",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
