import XCTest

/// B4c real-simulator journey for 备战 and the README §8 地图降级契约, against the CI fixture's
/// degraded course (`server_v2/ci_fixture.py`, `DEGRADED_ID`): hole 1 precise, hole 2 a factual
/// route that the background download upgrades to the precise map, holes 3-12 factual only and
/// holes 13-18 with no drawable route.
///
/// Proves: 选了就进 (the prep map opens at once for a course whose download has just started, no
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
        app.launchEnvironment["UITEST_GPS_LAT"] = cfg("UITEST_GPS_LAT") ?? "40.0454995"
        app.launchEnvironment["UITEST_GPS_LON"] = cfg("UITEST_GPS_LON") ?? "116.5461531"
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

    func testPrepOpensAtOnceAndDegradesPerHole() throws {
        // Start from an empty course library so the selection is a genuinely fresh download.
        app.launchEnvironment["UITEST_RESET_COURSE_LIBRARY"] = "1"
        launch()
        app.launchEnvironment.removeValue(forKey: "UITEST_RESET_COURSE_LIBRARY")

        let prepTile = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "备战")).firstMatch
        XCTAssertTrue(prepTile.waitForExistence(timeout: 30), "home must expose 备战")
        prepTile.tap()
        XCTAssertTrue(app.navigationBars["备战球场"].waitForExistence(timeout: 12))
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

        // 选了就进: the prep map, not the library and never a "地图尚未准备完成" alert.
        XCTAssertTrue(
            app.navigationBars["赛前球场攻略"].waitForExistence(timeout: 10),
            "selecting a course whose download has just started opens 赛前球场攻略 at once"
        )
        XCTAssertEqual(app.alerts.count, 0, "prep entry must never be gated by an alert")
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "尚未准备完成")).firstMatch.exists)
        // Never an empty hole: the first hole is a map or the one waiting page from the first frame.
        let firstHoleVisible = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier IN %@", ["prep-hole-map-1", "prep-map-waiting-1"])
        ).firstMatch
        XCTAssertTrue(firstHoleVisible.waitForExistence(timeout: 5), "hole 1 shows a map or the waiting page")
        save("b4c-01-prep-opened")

        // Hole 2: the factual route draws as soon as its facts are installed, without its topo.
        try openStripHole(2)
        let header2 = element("prep-hole-header-2")
        XCTAssertTrue(
            waitForValue(beginningWith: "路线", on: header2, timeout: 20),
            "hole 2 must show its factual route before the precise map exists (got \(String(describing: header2.value)))"
        )
        let map2 = element("prep-hole-map-2")
        XCTAssertTrue(map2.waitForExistence(timeout: 5))
        XCTAssertFalse(descendant("topo-hole-base-ready", of: map2).exists, "no precise topo yet")
        XCTAssertEqual(
            element("prep-club-order").label,
            "一号木 230 → 八号铁 164",
            "the panel shows this hole's club order"
        )
        // The player zooms the factual map.
        map2.pinch(withScale: 2.0, velocity: 1.0)
        let reset = app.buttons["prep-map-reset-rotation"]
        XCTAssertTrue(reset.waitForExistence(timeout: 5), "the factual map must accept a pinch")
        save("b4c-02-factual-route-zoomed")

        // The background download installs hole 2's precise map: it replaces the factual one in
        // place and the zoom the player set is kept.
        XCTAssertTrue(
            waitForValue(beginningWith: "精确地图", on: header2, timeout: 150),
            "hole 2's precise map must replace its factual route (got \(String(describing: header2.value)))"
        )
        XCTAssertTrue(
            descendant("topo-hole-base-ready", of: element("prep-hole-map-2")).waitForExistence(timeout: 30),
            "the precise topo bitmap must be drawn"
        )
        XCTAssertTrue(reset.exists, "the precise map replacement must not reset the zoom")
        save("b4c-03-precise-replaced-zoom-kept")

        // Hole 5 stays a factual route (its precise map is still coming): faded in the strip, but
        // it opens and draws its route.
        let strip5 = app.buttons["prep-hole-strip-5"]
        XCTAssertTrue(scrollStripTo(strip5))
        XCTAssertEqual(strip5.value as? String, "未就绪", "a hole without its precise map is faded")
        strip5.tap()
        XCTAssertTrue(waitForValue(beginningWith: "路线", on: element("prep-hole-header-5"), timeout: 20))
        XCTAssertTrue(element("prep-hole-map-5").exists)
        XCTAssertFalse(reset.exists, "a newly selected hole starts fitted")

        // Hole 14 has nothing drawable: the one full-screen waiting page, never an empty hole.
        try openStripHole(14)
        XCTAssertTrue(element("prep-map-waiting-14").waitForExistence(timeout: 10))
        XCTAssertTrue(waitForValue(beginningWith: "等待地图", on: element("prep-hole-header-14"), timeout: 5))
        XCTAssertEqual(app.buttons["prep-hole-strip-14"].value as? String, "未就绪")
        XCTAssertFalse(element("prep-club-order").exists, "the waiting page has no plan yet")
        XCTAssertFalse(element("prep-hole-map-14").exists)
        save("b4c-04-waiting-page")

        // The precise holes are not faded; the Tee dots are top right.
        let strip1 = app.buttons["prep-hole-strip-1"]
        XCTAssertTrue(scrollStripTo(strip1))
        XCTAssertTrue(waitForValue(beginningWith: "已就绪", on: strip1, timeout: 60))
        XCTAssertEqual(app.buttons["prep-tee-blue"].value as? String, "已选择")
        XCTAssertTrue(app.buttons["prep-tee-white"].exists)

        // Back in the library the selection is retained with its durable download state.
        let prepBar = app.navigationBars["赛前球场攻略"]
        let back = prepBar.buttons["备战球场"].exists ? prepBar.buttons["备战球场"] : prepBar.buttons.element(boundBy: 0)
        back.tap()
        XCTAssertTrue(app.navigationBars["备战球场"].waitForExistence(timeout: 8))
        let retained = app.buttons.matching(NSPredicate(
            format: "identifier BEGINSWITH %@",
            "prep-download-row-\(degradedCourseGlobalId):"
        )).firstMatch
        XCTAssertTrue(scrollIntoView(retained, maxSwipes: 12), "the selection stays in 最近选择")
        let retainedState = (retained.value as? String) ?? ""
        XCTAssertFalse(retainedState.isEmpty, "the retained row exposes its durable download state")
        save("b4c-05-library-retained")
    }

    // MARK: - Helpers

    private func launch() {
        if app.state != .notRunning { app.terminate() }
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 30), "app did not foreground")
    }

    private func element(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "identifier == %@", identifier)).firstMatch
    }

    private func descendant(_ identifier: String, of parent: XCUIElement) -> XCUIElement {
        parent.descendants(matching: .any).matching(NSPredicate(format: "identifier == %@", identifier)).firstMatch
    }

    private func openStripHole(_ number: Int) throws {
        let button = app.buttons["prep-hole-strip-\(number)"]
        XCTAssertTrue(scrollStripTo(button), "strip hole \(number) must be reachable")
        button.tap()
    }

    /// The 18-hole strip is a horizontal scroller; bring the hole's button on screen.
    private func scrollStripTo(_ button: XCUIElement) -> Bool {
        guard button.waitForExistence(timeout: 10) else { return false }
        let strip = element("prep-hole-strip")
        for _ in 0..<6 {
            if button.isHittable { return true }
            let window = app.windows.firstMatch.frame
            if button.frame.minX > window.midX {
                strip.swipeLeft()
            } else {
                strip.swipeRight()
            }
            _ = button.waitForExistence(timeout: 1)
        }
        return button.isHittable
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

    private func waitForValue(beginningWith prefix: String, on element: XCUIElement, timeout: TimeInterval) -> Bool {
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == true AND value BEGINSWITH %@", prefix),
            object: element
        )
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    private func save(_ name: String) {
        let shot = XCUIScreen.main.screenshot()
        let base = (try? FileManager.default.url(
            for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true
        )) ?? FileManager.default.temporaryDirectory
        let dir = base.appendingPathComponent("real-screenshots", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try? shot.pngRepresentation.write(to: dir.appendingPathComponent("\(name).png"))
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        try? app.debugDescription.data(using: .utf8)?
            .write(to: dir.appendingPathComponent("tree-\(name).txt"))
    }
}
