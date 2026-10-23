import XCTest

/// Layout checks use accessibility frames and state, never reference images or pixel colours.
/// The sole backend is ProductFixtureServer. These tests require a serial, idle simulator.
@MainActor
final class ProductPhoneUITests: XCTestCase {
    private var server: ProductFixtureServer!
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        server = try ProductFixtureServer(test: self)
        app = XCUIApplication()
    }

    override func tearDownWithError() throws {
        app?.terminate()
        server?.stop()
    }

    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    private func launch(reset: Bool = true, latitude: String? = nil) {
        app.launchEnvironment = [
            "UITEST_MODE": "1", "AI_CADDIE_FIXTURE_MODE": "1", "AI_CADDIE_DATA_MODE": "fixture",
            "AI_CADDIE_ADMIN_TOKEN": "synthetic-ui-only", "AI_CADDIE_API_BASE_URL": "http://127.0.0.1:9000",
            "UITEST_DISABLE_EVENT_SYNC": "1",
        ]
        if reset {
            app.launchEnvironment["UITEST_RESET_ACTIVE_ROUND"] = "1"
            app.launchEnvironment["UITEST_RESET_COURSE_LIBRARY"] = "1"
        }
        if let latitude {
            app.launchEnvironment["UITEST_GPS_LAT"] = latitude
            app.launchEnvironment["UITEST_GPS_LON"] = "0"
        } else { app.launchEnvironment["UITEST_LOCATION_AUTHORIZATION"] = "denied" }
        app.launch()
        XCTAssertTrue(element("home-tile-scores").waitForExistence(timeout: 15), "synthetic home bootstrapped")
    }

    private func reveal(_ target: XCUIElement) {
        for _ in 0..<7 {
            if target.exists && target.isHittable { return }
            app.swipeUp()
        }
        XCTAssertTrue(target.exists && target.isHittable, "reachable control \(target.identifier)")
    }

    private func tap(_ id: String) {
        let target = element(id)
        XCTAssertTrue(target.waitForExistence(timeout: 10), id)
        reveal(target)
        target.tap()
    }

    private func scores() { tap("home-tile-scores"); XCTAssertTrue(element("results-handicap").waitForExistence(timeout: 10)) }
    private func review() {
        scores()
        tap("results-all-rounds")
        let row = app.buttons.containing(.staticText, identifier: "80").firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10), "r1 = 80 strokes")
        reveal(row)
        row.tap()
        XCTAssertTrue(element("round-review-content-ready").waitForExistence(timeout: 10))
    }

    private func insideWindow(_ target: XCUIElement, _ row: String, file: StaticString = #filePath, line: UInt = #line) {
        reveal(target)
        let frame = target.frame
        XCTAssertGreaterThan(frame.width, 0, row, file: file, line: line)
        XCTAssertGreaterThan(frame.height, 0, row, file: file, line: line)
        XCTAssertTrue(app.windows.firstMatch.frame.insetBy(dx: -1, dy: -1).contains(frame), row, file: file, line: line)
    }

    func test_j2_1_results_entries_remain_enabled_for_zero_one_and_many_rounds() {
        for (name, count) in [("empty", 0), ("single", 1), ("several", 3)] {
            var state = ProductFixtureServer.State(); state.roundCount = count
            server.configure(state)
            launch()
            scores()
            for id in ["results-entry-analysis", "results-entry-time", "results-entry-distribution", "results-entry-courses", "results-all-rounds"] {
                let entry = element(id)
                insideWindow(entry, name + id)
                XCTAssertTrue(entry.isEnabled, name + id)
            }
            let empty = element("results-empty")
            let settled = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in empty.exists == (count == 0) }, object: nil)
            XCTAssertEqual(XCTWaiter.wait(for: [settled], timeout: 10), .completed, name)
            app.terminate()
        }
    }

    func test_j2_2_range_and_grain_disable_illegal_combinations_without_changing_range() {
        launch(); scores(); tap("results-entry-time")
        let grain = element("time-grain")
        XCTAssertTrue(grain.waitForExistence(timeout: 10))
        XCTAssertTrue(grain.isEnabled, "grain must remain interactive")
        // Selection labels identify semantic controls; they are not copy assertions.
        let range = app.segmentedControls.containing(.button, identifier: "近10场").firstMatch
        XCTExpectFailure("C16e J2.2: time page has no independent range control") {
            XCTAssertTrue(range.exists, "range must be selectable independently of grain")
        }
        guard range.exists else { return }
        // Count windows draw rounds; twelve months draw round/month/quarter; all draws month/quarter/year.
        let rows: [(String, [Bool])] = [
            ("近10场", [true, false, false, false]), ("近20场", [true, false, false, false]),
            ("近12月", [true, true, true, false]), ("全部", [false, true, true, true]),
        ]
        for (name, allowed) in rows {
            range.buttons[name].tap()
            for (index, enabled) in allowed.enumerated() {
                let button = grain.buttons.element(boundBy: index)
                XCTAssertEqual(button.isEnabled, enabled, name + " grain \(index)")
                if !enabled { XCTAssertTrue(range.buttons[name].isSelected, name + " remains selected") }
            }
        }
    }

    func test_j2_3_quarter_drilldown_opens_only_its_two_real_rounds_then_review() {
        launch(); scores(); tap("results-entry-time")
        let grain = element("time-grain")
        XCTAssertTrue(grain.waitForExistence(timeout: 10))
        grain.buttons.element(boundBy: 2).tap()
        tap("time-period-2026-Q2")
        // Explicit Q2 sample r1=80, r2=82; r3=84 belongs to Q3.
        for score in ["80", "82"] { XCTAssertTrue(app.staticTexts[score].waitForExistence(timeout: 10), score) }
        XCTAssertFalse(app.staticTexts["84"].exists)
        app.buttons.containing(.staticText, identifier: "80").firstMatch.tap()
        XCTAssertTrue(element("round-review-content-ready").waitForExistence(timeout: 10))
        XCTAssertTrue(server.requestedPaths().contains { $0.hasPrefix("/api/v2/history/rounds?") && $0.contains("period=2026-Q2") })
        XCTAssertTrue(server.requestedPaths().contains { $0.hasPrefix("/api/v2/history/rounds/r1") })
    }

    func test_j2_6_course_sections_fit_and_keep_ordered_combinations_separate() {
        launch(); scores(); tap("results-entry-courses")
        let course = app.buttons.containing(.staticText, identifier: "Example").firstMatch
        XCTAssertTrue(course.waitForExistence(timeout: 10)); course.tap()
        for id in ["course-header", "course-average", "course-dots", "course-hard-holes", "course-combos", "course-all-combos"] {
            insideWindow(element(id), id)
        }
        XCTAssertEqual(element("course-combos").descendants(matching: .staticText).matching(NSPredicate(format: "label CONTAINS %@", "→")).count, 2,
                       "front/back and back/front are separate rows")
        XCTAssertFalse(element("course-hard-gid:81001:10-18-10").exists, "one-sample hole excluded")
        XCTAssertTrue(element("course-hard-gid:81001:1-9-1").exists)
    }

    func test_j2_8_review_cards_missing_metrics_and_share_fit_for_three_round_shapes() {
        for (name, holes, shots) in [("with-shots", 18, true), ("score-only", 18, false), ("nine", 9, false)] {
            var state = ProductFixtureServer.State(); state.reviewHoles = holes; state.hasShots = shots
            server.configure(state); launch(); review()
            insideWindow(element("round-review-hole-1"), name)
            let last = element("round-review-hole-18")
            let refreshed = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in last.exists == (holes == 18) }, object: nil)
            XCTAssertEqual(XCTWaiter.wait(for: [refreshed], timeout: 10), .completed, name)
            XCTAssertFalse(element("round-review-metric-gir").exists, name + " unknown GIR omitted")
            insideWindow(element("round-review-share"), name + " share")
            XCTAssertTrue(element("round-review-share").isEnabled, name)
            if holes == 18 {
                XCTExpectFailure("C16e J2.8: physical loop identity still rendered as OUT/IN") {
                    XCTAssertFalse(app.staticTexts["OUT"].exists || app.staticTexts["IN"].exists, name)
                }
            }
            app.terminate()
        }
    }

    func test_j2_9_landing_labels_hole_switch_zoom_pan_and_visibility() {
        var state = ProductFixtureServer.State(); state.includePutts = true
        server.configure(state)
        launch(); review(); tap("round-review-hole-1")
        let shot = element("round-map-shot-s1-1")
        XCTAssertTrue(shot.waitForExistence(timeout: 10))
        for id in ["round-map-shot-s1-1", "round-map-shot-s1-2"] { insideWindow(element(id), id) }
        XCTAssertTrue(shot.label.contains("1") && shot.label.contains("七号铁") && shot.label.contains("164"), "150m = 164yd; first shot")
        XCTAssertTrue(element("round-map-putts").label.contains("2"), "recorded two putts at the green")
        XCTAssertFalse(element("round-map-shot-s1-1").frame.intersects(element("round-map-shot-s1-2").frame), "shot labels do not overlap")
        let labels = element("round-map-labels")
        labels.tap(); XCTAssertFalse(shot.exists)
        labels.tap(); XCTAssertTrue(shot.waitForExistence(timeout: 5))
        let zoom = element("round-map-zoom-state")
        let initial = zoom.value as? String
        shot.coordinate(withNormalizedOffset: CGVector(dx: 0, dy: 0)).doubleTap()
        XCTAssertNotEqual(zoom.value as? String, initial, "double tap zooms")
        let origin = shot.frame.origin
        let start = shot.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
        start.press(forDuration: 0.05, thenDragTo: start.withOffset(CGVector(dx: 40, dy: 30)))
        XCTAssertNotEqual(shot.frame.origin, origin, "zoomed map pans")
        XCTAssertTrue(element("round-hole-strip-1").isSelected, "pan does not change hole")
        tap("round-hole-strip-2")
        XCTAssertTrue(element("round-map-shot-s2-1").waitForExistence(timeout: 10))
        XCTAssertFalse(shot.exists, "previous hole's points removed")
    }

    func test_j2_11_provider_failure_leaves_results_and_review_usable() throws {
        var state = ProductFixtureServer.State(); state.providerFailure = true
        server.configure(state)
        let completed = expectation(description: "fake provider actually fails")
        URLSession.shared.dataTask(with: URL(string: "http://127.0.0.1:9000/api/v2/reports/decision")!) { _, response, error in
            XCTAssertNil(error)
            XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 503)
            completed.fulfill()
        }.resume()
        wait(for: [completed], timeout: 5)
        launch(); review()
        insideWindow(element("round-review-hole-1"), "provider unavailable")
        insideWindow(element("round-review-share"), "provider unavailable")
        XCTAssertTrue(element("round-review-share").isEnabled)
    }

    func test_j5_4_live_tee_and_post_shot_ranges_recompute_after_position_change() {
        launch(latitude: "0")
        startRound()
        assertRanges([243, 365, 486], row: "tee")
        XCTAssertFalse(element("selected-hazard-1").exists, "hazards hidden by default")
        let toggle = element("live-hazard-toggle")
        XCTAssertTrue(toggle.exists, "fixture actually contains a water hazard")
        XCTAssertFalse(toggle.isSelected)
        toggle.tap()
        XCTAssertTrue(toggle.isSelected)
        toggle.tap()
        XCTAssertFalse(toggle.isSelected)
        let map = element("live-open-map-from-hero")
        map.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.55)).tap()
        XCTAssertTrue(element("live-map-target-marker").waitForExistence(timeout: 5), "single tap places target")
        tap("live-open-green-from-hero")
        for id in ["live-green-edge-front", "live-green-edge-back", "live-green-edge-left", "live-green-edge-right"] {
            insideWindow(element(id), id)
        }
        app.buttons["关闭果岭地图"].tap()
        tap("live-record-shot")
        // Empty synthetic bag still allows position recording and skipping club selection.
        let skip = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "跳过球杆")).firstMatch
        XCTAssertTrue(skip.waitForExistence(timeout: 5)); skip.tap()
        app.terminate()
        launch(reset: false, latitude: "0.001")
        tap("home-in-progress-round")
        XCTAssertTrue(element("live-hole-title").waitForExistence(timeout: 15))
        // .001 latitude further north = 111.1949m; golden is measured from the new fix.
        assertRanges([122, 243, 365], row: "after-tee restart")
    }

    private func startRound() {
        tap("home-new-round")
        tap("start-round-venue-82001")
        let start = element("start-round-primary-action")
        reveal(start)
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: start)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 15), .completed)
        start.tap()
        XCTAssertTrue(element("live-hole-title").waitForExistence(timeout: 15))
    }

    func test_j4_5_phone_three_map_states_have_visible_content() {
        for (name, expected) in [("ready", "live-hole-map-ready"), ("partial", "live-hole-map-partial"), ("missing", "live-map-preparing-surface")] {
            var state = ProductFixtureServer.State(); state.coverage = name
            server.configure(state); launch(); startRound()
            let map = element(expected)
            XCTAssertTrue(map.waitForExistence(timeout: 15), name)
            insideWindow(map, name)
            app.terminate()
        }
    }

    func test_j5_5_phone_score_remains_saveable_with_and_without_gps() {
        for (name, latitude) in [("no-fix", Optional<String>.none), ("accurate-fix", "0")] {
            launch(latitude: latitude); startRound()
            XCTAssertEqual(element("live-record-shot").isEnabled, latitude != nil, name)
            tap("live-score-hole")
            let save = element("score-save")
            insideWindow(save, name)
            XCTAssertTrue(save.isEnabled, name)
            save.tap()
            XCTAssertTrue(element("live-hole-title").waitForExistence(timeout: 10))
            app.terminate()
        }
    }

    func test_j5_10_nine_hole_finish_uses_par_thirty_six_and_fits() {
        launch(); startRound()
        for hole in 1...9 {
            let title = element("live-hole-title")
            let advanced = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in title.label.contains(String(hole)) }, object: nil)
            XCTAssertEqual(XCTWaiter.wait(for: [advanced], timeout: 10), .completed, "play order \(hole)")
            tap("live-score-hole")
            tap("score-save")
        }
        if element("turn-stop").waitForExistence(timeout: 5) {
            tap("turn-stop"); tap("turn-go")
        }
        XCTAssertTrue(element("live-finish-to-par").waitForExistence(timeout: 10))
        XCTAssertEqual(element("live-finish-to-par").label, "E", "nine par fours = 36/36")
        let par = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Par 36")).firstMatch
        insideWindow(par, "nine recorded holes")
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Par 72")).firstMatch.exists)
        insideWindow(element("live-finish-save"), "save summary")
    }

    func test_j5_2_home_active_card_replaces_new_round_and_can_resume() {
        launch(); startRound()
        tap("live-back-home")
        tap("live-scorecard-leave-home")
        insideWindow(element("home-in-progress-round"), "active round hero")
        XCTAssertFalse(element("home-new-round").exists)
        XCTAssertTrue(element("home-end-round").isEnabled)
        tap("home-in-progress-round")
        XCTAssertTrue(element("live-hole-title").waitForExistence(timeout: 10))
    }

    func test_j5_3_home_secondary_tiles_fit_without_weather_or_archive_strip() {
        var state = ProductFixtureServer.State(); state.roundCount = 0
        server.configure(state); launch()
        for id in ["home-tile-scores", "home-tile-prep", "home-tile-bag", "home-tile-weather"] {
            insideWindow(element(id), id)
        }
        XCTAssertFalse(element("home-tile-weather").label.contains("°"), "failed weather cannot invent a temperature")
        XCTAssertFalse(element("home-last-round-strip").exists, "no archived round to attach the strip to")
    }

    private func assertRanges(_ expected: [Int], row: String) {
        for (id, yards) in zip(["live-green-front", "live-green-middle", "live-green-back"], expected) {
            let distance = element(id)
            XCTAssertTrue(distance.waitForExistence(timeout: 5), row + id)
            XCTAssertTrue(distance.label.contains(String(yards)), row + id + " = \(yards)yd")
            insideWindow(distance, row + id)
        }
    }
}
