from pathlib import Path
import unittest


IOS_VIEWS = Path("mobile/ios/AICaddie/Views")
WATCH_VIEWS = Path("mobile/ios/AICaddieWatch/Views")


class NativeVisualParityTests(unittest.TestCase):
    def test_real_review_capture_selects_known_spatial_garmin_round(self) -> None:
        ui_tests = Path("mobile/ios/AICaddieUITests")
        real_flow = (ui_tests / "RealFlowUITests.swift").read_text(encoding="utf-8")
        review_edit = (ui_tests / "ReviewEditUITests.swift").read_text(encoding="utf-8")

        for source in (real_flow, review_edit):
            self.assertNotIn("2026-06-11", source)
            self.assertIn("17534238", source)
            self.assertNotIn("tapFirstRoundRow", source)

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

    def test_watch_menu_removes_the_automatic_vertical_scroll_content_margin(self) -> None:
        source = (WATCH_VIEWS / "WatchMenuView.swift").read_text(encoding="utf-8")

        self.assertIn(
            ".contentMargins(.vertical, 0, for: .scrollContent)",
            source,
        )

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

    def test_real_course_visual_player_has_a_measured_bag_before_download(self) -> None:
        workflow = Path(".github/workflows/watch-runtime.yml").read_text(encoding="utf-8")

        seed = "seed_isolated_visual_player_bag"
        setup_exit = 'if [[ "$WATCH_RUNTIME_SCOPE" == "setup-visual" ]]; then'
        download = "launch_and_capture real-course-download-seed watch-real-course-download.png"

        self.assertIn(seed, workflow)
        self.assertIn("/api/v2/history/overview", workflow)
        self.assertIn("/api/v2/players/$CI_PLAYER_ID/clubs/bag", workflow)
        self.assertIn('"token":"driver","distanceM":220', workflow)
        self.assertIn('"token":"wood3","distanceM":200', workflow)
        self.assertIn('"token":"iron8","distanceM":125', workflow)
        self.assertLess(workflow.index(setup_exit), workflow.index(seed))
        self.assertLess(workflow.index(seed), workflow.index(download))


if __name__ == "__main__":
    unittest.main()
