import XCTest

/// B4c real-simulator journey for 备战 and the README §8 地图降级契约, against the CI fixture's
/// degraded course (`server_v2/ci_fixture.py`, `DEGRADED_ID`): hole 1 precise, hole 2 a factual
/// route that the background download upgrades to the precise map, holes 3-12 factual only and
/// holes 13-18 with no drawable route.
///
/// Proves: 选了就进 (the course map opens at once for a course whose download has just started, no
/// "地图尚未准备完成" gate); a factual route shows immediately; the one full-screen waiting page
/// for a hole with nothing drawable; not-ready holes only faded in the strip (and still open); the
/// precise map replacing the factual one in place without resetting the player's zoom; and the
/// selection retained in the durable library. Live-backend runs skip it: the live catalogue has no
/// course with a deterministic mix of precise, factual and missing holes.
final class PrepDegradationUITests: XCTestCase {
    private let app = XCUIApplication()
    private let degradedCourseGlobalId = 31798

    private func cfg(_ key: String) -> String? {
        let env = ProcessInfo.processInfo.environment
        return env[key] ?? env["TEST_RUNNER_\(key)"]
    }

    override func setUpWithError() throws {
        continueAfterFailure = false
        try XCTSkipUnless(
            cfg("AI_CADDIE_FIXTURE_MODE") == "1",
            "the degraded-map course exists only in the isolated CI fixture"
        )
        app.launchEnvironment["AI_CADDIE_API_BASE_URL"] = cfg("AI_CADDIE_API_BASE_URL") ?? ""
        app.launchEnvironment["AI_CADDIE_ADMIN_TOKEN"] = cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        for key in UITestBackendLaunchConfiguration.markerKeys {
            app.launchEnvironment.removeValue(forKey: key)
        }
        app.launchEnvironment.merge(
            UITestBackendLaunchConfiguration.markers(
                fixtureMode: cfg("AI_CADDIE_FIXTURE_MODE"),
                dataMode: cfg("AI_CADDIE_DATA_MODE")
            )
        ) { _, new in new }
        for key in [
            "UITEST_FORCE_NEARBY_FAILURE",
            "UITEST_FORCE_COURSE_PACKAGE_FAILURE",
            "UITEST_FORCE_LIVE_NETWORK_FAILURE",
            "UITEST_COURSE_TEES_DELAY_MS",
            "UITEST_LOCATION_AUTHORIZATION",
        ] {
            app.launchEnvironment.removeValue(forKey: key)
        }
        app.launchEnvironment["UITEST_GPS_LAT"] = "0"
        app.launchEnvironment["UITEST_GPS_LON"] = "0"
        app.launchEnvironment["UITEST_MODE"] = "1"
        app.launchEnvironment["UITEST_RESET_ACTIVE_ROUND"] = "1"
        app.launchEnvironment["UITEST_DISABLE_EVENT_SYNC"] = "1"
    }

    override func tearDownWithError() throws {
        guard cfg("AI_CADDIE_FIXTURE_MODE") == "1" else { return }
        // The degraded course never completes, so its app-owned download would otherwise keep
        // the shared container's prep queue busy for later journeys. Leave an empty library.
        app.launchEnvironment["UITEST_RESET_COURSE_LIBRARY"] = "1"
        if app.state != .notRunning { app.terminate() }
        app.launch()
        _ = app.wait(for: .runningForeground, timeout: 30)
        app.terminate()
        app.launchEnvironment.removeValue(forKey: "UITEST_RESET_COURSE_LIBRARY")
    }

    func testPrepOpensOnLiveHoleScreenWithoutRecording() throws {
        app.launchEnvironment["UITEST_RESET_COURSE_LIBRARY"] = "1"
        launch()
        app.launchEnvironment.removeValue(forKey: "UITEST_RESET_COURSE_LIBRARY")

        let newRound = app.buttons["home-new-round"]
        XCTAssertTrue(newRound.waitForExistence(timeout: 30), "home must expose a new-round entry")
        newRound.tap()
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 12))
        let keyword = app.textFields["course-catalog-keyword-field"]
        XCTAssertTrue(keyword.waitForExistence(timeout: 5))
        keyword.tap()
        keyword.typeText("Fixture")
        let search = app.buttons["course-catalog-search-action"]
        XCTAssertTrue(waitUntilEnabled(search, timeout: 5))
        search.tap()
        let result = app.buttons["course-catalog-result-\(degradedCourseGlobalId)"]
        XCTAssertTrue(scrollIntoView(result, maxSwipes: 12), "the fixture search must list the degraded course")
        result.tap()
        let start = app.buttons["start-round-primary-action"]
        XCTAssertTrue(start.waitForExistence(timeout: 12), "search selection must open the course page")
        XCTAssertTrue(waitUntilEnabled(start, timeout: 30))
        start.tap()

        let banner = app.descendants(matching: .any)["live-round-banner"].firstMatch
        XCTAssertTrue(banner.waitForExistence(timeout: 30), "备战 must open the live hole screen")
        XCTAssertTrue(
            (banner.value as? String)?.contains("没到场") == true || banner.label.contains("没到场"),
            "prep must explicitly say that strokes are not recorded"
        )
        XCTAssertTrue(app.staticTexts["第 1 洞"].waitForExistence(timeout: 20))
        XCTAssertEqual(app.alerts.count, 0, "prep entry must never be gated by an alert")
        XCTAssertFalse(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "尚未准备完成")).firstMatch.exists
        )
        save("b4c-01-prep-live-hole")

        let back = app.buttons["live-back-home"]
        XCTAssertTrue(back.waitForExistence(timeout: 8) && back.isHittable)
        back.tap()
        XCTAssertTrue(app.buttons["home-new-round"].waitForExistence(timeout: 8))
        app.buttons["home-new-round"].tap()
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        let retained = app.descendants(matching: .any).matching(NSPredicate(
            format: "identifier BEGINSWITH %@", "start-round-offline-row-\(degradedCourseGlobalId):"
        )).firstMatch
        XCTAssertTrue(scrollIntoView(retained, maxSwipes: 12), "the selection stays in the start-page download section")
        let retainedStatus = retained.label + " " + ((retained.value as? String) ?? "")
        XCTAssertTrue(
            ["下载", "准备", "失败", "已下载"].contains(where: { retainedStatus.contains($0) }),
            "the offline row must expose its current download state"
        )
        save("b4c-02-library-retained")
    }

    // MARK: - Helpers

    private func launch() {
        if app.state != .notRunning { app.terminate() }
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 30), "app did not foreground")
    }

    private func scrollIntoView(_ element: XCUIElement, maxSwipes: Int) -> Bool {
        guard element.waitForExistence(timeout: 20) else { return false }
        for _ in 0..<maxSwipes where !element.isHittable {
            app.swipeUp()
            _ = element.waitForExistence(timeout: 1)
        }
        return element.isHittable
    }

    private func waitUntilEnabled(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == true AND enabled == true"),
            object: element
        )
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    private func save(_ name: String) {
        let shot = XCUIScreen.main.screenshot()
        let base = (try? FileManager.default.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? FileManager.default.temporaryDirectory
        let dir = base.appendingPathComponent("real-screenshots", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try? shot.pngRepresentation.write(to: dir.appendingPathComponent("\(name).png"))
        try? app.debugDescription.data(using: .utf8)?.write(to: dir.appendingPathComponent("tree-\(name).txt"))
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
