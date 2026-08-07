import XCTest

/// Real running-app screenshots of the 发球台 (tee) picker on 开始一场 (XCUITest, not ImageRenderer).
/// Launches the ACTUAL app pointed at the live backend (funnel) with the owner admin token + a
/// simulated on-course GPS fix (all via launchEnvironment), navigates 打球 → 开始一场, opens the tee
/// selector and captures it. The tee options come from `GET /api/v2/courses/{id}/tees` (colour + total
/// yards + default), so the open menu shows real tee choices with yardage. PNGs + per-screen
/// accessibility-tree dumps are written to the test process Documents dir; native-mobile.yml collects
/// `*Documents/real-screenshots/*`.
final class TeeSelectionUITests: XCTestCase {
    private let app = XCUIApplication()

    /// Read a config value the test runner may receive either plain or TEST_RUNNER_-prefixed.
    private func cfg(_ key: String) -> String? {
        let env = ProcessInfo.processInfo.environment
        return env[key] ?? env["TEST_RUNNER_\(key)"]
    }

    override func setUpWithError() throws {
        continueAfterFailure = false
        app.launchEnvironment["AI_CADDIE_API_BASE_URL"] = cfg("AI_CADDIE_API_BASE_URL") ?? ""
        app.launchEnvironment["AI_CADDIE_ADMIN_TOKEN"] = cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        // 北京丽宫第 1 洞蓝 T: a real CourseView tee on the same course this flow verifies.
        app.launchEnvironment["UITEST_GPS_LAT"] = cfg("UITEST_GPS_LAT") ?? "40.0454995"
        app.launchEnvironment["UITEST_GPS_LON"] = cfg("UITEST_GPS_LON") ?? "116.5461531"
        app.launchEnvironment["UITEST_MODE"] = "1"
    }

    func testCaptureTeeSelector() throws {
        writeDiagnostics()
        launchFresh()
        save("01-home"); dump("01-home")

        // 打球 → 开始一场 (StartRoundView). The wide primary tile opens the start screen.
        guard tapContaining(["打球", "开始一场", "开始记分"]) else {
            save("02-start-missing"); dump("02-start-missing")
            XCTFail("the real home must expose and open 开始一场")
            return
        }
        settle(9)
        save("02-start-round"); dump("02-start-round")  // 选球场 + 发球台 row + 开始记分

        // This injected coordinate can legitimately return several nearby venues. Reaching the Tee
        // selector therefore requires an explicit venue/segment choice; history must never silently
        // select one for the player. Use the real Beijing Palace catalogue row verified by the same GPS.
        let palace = app.buttons["start-round-course-segment-31793"]
        guard palace.waitForExistence(timeout: 15), palace.isHittable else {
            XCTFail("the production nearby response must expose Beijing Palace segment 31793")
            return
        }
        XCTAssertEqual(
            palace.value as? String,
            "未选择",
            "multiple nearby venues must wait for the player's explicit choice"
        )
        XCTAssertFalse(
            app.buttons["start-round-primary-action"].isEnabled,
            "a course from history must not become the implicit nearby selection"
        )
        palace.tap()
        let becameSelected = waitForValue("已选择", on: palace, timeout: 8)
        save("02b-start-round-selected"); dump("02b-start-round-selected")
        XCTAssertTrue(
            becameSelected,
            "the explicit nearby-course choice must become the active segment"
        )
        XCTAssertTrue(
            waitUntilEnabled(app.buttons["start-round-primary-action"], timeout: 90),
            "the selected nearby course must load its Tee authority and become startable"
        )
        XCTAssertTrue(
            app.staticTexts["选择全场开始 18 洞球局。"].waitForExistence(timeout: 5),
            "an 18-hole whole-course selection must not describe itself as a 9-hole loop"
        )

        // Open the 发球台 selector (a SwiftUI Menu whose label is the current tee, e.g. "蓝 T · 6412 码"
        // or "默认"). Tapping it reveals the tee options with yardage from GET /courses/{id}/tees.
        if tapTeeSelector() {
            settle(2)
            save("03-tee-menu"); dump("03-tee-menu")  // open menu: colour + yards choices
            let cancel = app.buttons["取消"]
            XCTAssertTrue(
                cancel.waitForExistence(timeout: 5),
                "the open tee menu must offer an explicit non-mutating dismissal"
            )
            cancel.tap()
            XCTAssertTrue(waitUntilGone(cancel, timeout: 5), "cancelling the Tee menu must close it")

            // Opening a menu is not enough evidence that the player's Tee choice is usable. Change
            // from the real default to the real white Tee and prove the selected label survives the
            // menu dismissal while the course remains startable.
            XCTAssertTrue(tapTeeSelector(), "the Tee menu must remain reopenable after cancellation")
            let whiteTee = app.buttons.matching(
                NSPredicate(format: "label BEGINSWITH %@", "白 T")
            ).firstMatch
            XCTAssertTrue(
                whiteTee.waitForExistence(timeout: 5) && whiteTee.isHittable,
                "the real Beijing Palace Tee authority must expose its white Tee"
            )
            whiteTee.tap()
            XCTAssertTrue(waitUntilGone(cancel, timeout: 5), "selecting a Tee must dismiss the menu")
            XCTAssertTrue(
                app.descendants(matching: .any).matching(
                    NSPredicate(format: "label BEGINSWITH %@", "白 T")
                ).firstMatch.waitForExistence(timeout: 5),
                "the start form must retain the newly selected white Tee"
            )
            XCTAssertTrue(app.buttons["start-round-primary-action"].isEnabled)
            save("04-white-tee-selected"); dump("04-white-tee-selected")
        } else {
            dump("03-tee-menu-missing")
            XCTFail("the selected real course must expose a tappable Tee menu")
        }
    }

    func testDeniedGPSStillOffersCatalogueSearchInsteadOfHistory() throws {
        app.launchEnvironment.removeValue(forKey: "UITEST_GPS_LAT")
        app.launchEnvironment.removeValue(forKey: "UITEST_GPS_LON")
        app.launchEnvironment["UITEST_LOCATION_AUTHORIZATION"] = "denied"
        launchFresh()

        guard tapContaining(["打球", "开始一场", "开始记分"]) else {
            XCTFail("the home must keep the new-round entry available when GPS is denied")
            return
        }
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        save("denied-01-start-round"); dump("denied-01-start-round")
        XCTAssertTrue(
            app.staticTexts["定位权限未开启；可以直接按城市或球场名搜索。"]
                .waitForExistence(timeout: 12),
            "denied GPS must explain the manual catalogue fallback"
        )
        let search = app.buttons["start-round-search-all-courses"]
        XCTAssertTrue(
            search.waitForExistence(timeout: 5) && search.isHittable,
            "denied GPS must never strand the player without city/name search"
        )
        let start = app.buttons["start-round-primary-action"]
        XCTAssertTrue(start.exists)
        XCTAssertFalse(start.isEnabled, "no historical course may be silently selected as nearby")

        search.tap()
        XCTAssertTrue(app.navigationBars["找球场"].waitForExistence(timeout: 8))
        let nearby = app.buttons["course-catalog-nearby-action"]
        XCTAssertTrue(nearby.exists, "the start-round catalogue must retain the nearby affordance")
        XCTAssertFalse(nearby.isEnabled, "denied GPS must not issue a nearby query with invented coordinates")

        // Do not stop at proving that a text field exists. Exercise the complete fallback against the
        // live Garmin catalogue: city-only search -> factual provider row -> selection -> real Tee load.
        let city = app.textFields["course-catalog-city-field"]
        XCTAssertTrue(city.waitForExistence(timeout: 5))
        city.tap()
        city.typeText("北京")
        let submit = app.buttons["course-catalog-search-action"]
        XCTAssertTrue(waitUntilEnabled(submit, timeout: 5))
        submit.tap()
        XCTAssertTrue(waitUntilGone(app.keyboards.firstMatch, timeout: 8))

        let palaceResult = app.buttons["course-catalog-result-31793"]
        XCTAssertTrue(
            bringIntoView(palaceResult, maxSwipes: 30),
            "city-only search must return the real Beijing Palace catalogue row while GPS is denied"
        )
        palaceResult.tap()

        let selectedPalace = app.buttons["start-round-course-segment-31793"]
        XCTAssertTrue(selectedPalace.waitForExistence(timeout: 12))
        XCTAssertTrue(
            waitForValue("已选择", on: selectedPalace, timeout: 8),
            "the manual fallback result must become the explicit start-round selection"
        )
        XCTAssertTrue(
            waitUntilEnabled(app.buttons["start-round-primary-action"], timeout: 90),
            "the denied-GPS fallback must load real Tee authority and leave the round startable"
        )
    }

    func testAuthorizedGPSWithoutFixStillOffersCompleteCatalogueFallback() throws {
        app.launchEnvironment.removeValue(forKey: "UITEST_GPS_LAT")
        app.launchEnvironment.removeValue(forKey: "UITEST_GPS_LON")
        app.launchEnvironment["UITEST_LOCATION_AUTHORIZATION"] = "authorized"
        launchFresh()

        guard tapContaining(["打球", "开始一场", "开始记分"]) else {
            XCTFail("the home must keep the new-round entry available while an authorized GPS waits for a fix")
            return
        }
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        XCTAssertTrue(
            app.staticTexts["正在定位并查找附近球场…"].waitForExistence(timeout: 12),
            "authorized Core Location without a fix must be represented honestly"
        )
        let search = app.buttons["start-round-search-all-courses"]
        XCTAssertTrue(
            search.waitForExistence(timeout: 5) && search.isHittable,
            "waiting for a GPS fix must never block city/name search"
        )
        XCTAssertFalse(app.buttons["start-round-primary-action"].isEnabled)
        save("no-fix-01-start-round"); dump("no-fix-01-start-round")

        search.tap()
        XCTAssertTrue(app.navigationBars["找球场"].waitForExistence(timeout: 8))
        XCTAssertFalse(
            app.buttons["course-catalog-nearby-action"].isEnabled,
            "the app must not invent coordinates merely because permission is granted"
        )
        try searchAndSelectBeijingPalace(field: "course-catalog-keyword-field", text: "北京丽宫")
        XCTAssertTrue(
            waitUntilEnabled(app.buttons["start-round-primary-action"], timeout: 90),
            "an authorized-but-fixless player must still reach a startable real course"
        )
    }

    func testNoCourseWithinFiftyKilometresStillOffersCompleteCatalogueFallback() throws {
        // 0,0 is open ocean. This drives the production nearby endpoint to an honest empty result
        // without a fake response or a test-only app route.
        app.launchEnvironment["UITEST_GPS_LAT"] = "0"
        app.launchEnvironment["UITEST_GPS_LON"] = "0"
        app.launchEnvironment.removeValue(forKey: "UITEST_LOCATION_AUTHORIZATION")
        launchFresh()

        guard tapContaining(["打球", "开始一场", "开始记分"]) else {
            XCTFail("the home must open a new round even when the current area has no course")
            return
        }
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        XCTAssertTrue(
            app.staticTexts["当前位置 50 km 内没有找到球场；可以扩大范围或按名称搜索。"]
                .waitForExistence(timeout: 60),
            "a valid remote coordinate with no nearby course must settle to an empty result, not spin forever"
        )
        XCTAssertFalse(
            app.buttons["start-round-course-segment-31793"].exists,
            "the empty nearby result must not be repopulated from play history"
        )
        XCTAssertFalse(app.buttons["start-round-primary-action"].isEnabled)
        save("empty-nearby-01-start-round"); dump("empty-nearby-01-start-round")

        let search = app.buttons["start-round-search-all-courses"]
        XCTAssertTrue(search.exists && search.isHittable)
        search.tap()
        XCTAssertTrue(app.navigationBars["找球场"].waitForExistence(timeout: 8))
        try searchAndSelectBeijingPalace(field: "course-catalog-city-field", text: "北京")
        XCTAssertTrue(
            waitUntilEnabled(app.buttons["start-round-primary-action"], timeout: 90),
            "an empty nearby result must still reach a startable real course through city search"
        )
    }

    func testNearbyServiceFailureWithoutLocalCacheStillOffersCompleteCatalogueFallback() throws {
        // A remote failure is different from an honest empty result. Use an ocean coordinate so
        // any course cached by another test is factually outside the local 50 km fallback.
        app.launchEnvironment["UITEST_GPS_LAT"] = "0"
        app.launchEnvironment["UITEST_GPS_LON"] = "0"
        app.launchEnvironment["UITEST_FORCE_NEARBY_FAILURE"] = "1"
        app.launchEnvironment.removeValue(forKey: "UITEST_LOCATION_AUTHORIZATION")
        launchFresh()

        guard tapContaining(["打球", "开始一场", "开始记分"]) else {
            XCTFail("the home must keep the new-round entry available when nearby discovery fails")
            return
        }
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        XCTAssertTrue(
            app.staticTexts["附近球场暂时读取失败；可以先按城市或球场名搜索。"]
                .waitForExistence(timeout: 20),
            "a transport failure without a factual local candidate must settle to the manual fallback"
        )
        XCTAssertFalse(
            app.buttons.matching(
                NSPredicate(format: "identifier BEGINSWITH %@", "start-round-course-segment-")
            ).firstMatch.exists,
            "a failed request at an ocean coordinate must not repopulate the picker from history"
        )
        XCTAssertFalse(app.buttons["start-round-primary-action"].isEnabled)

        let search = app.buttons["start-round-search-all-courses"]
        XCTAssertTrue(search.exists && search.isHittable)
        search.tap()
        XCTAssertTrue(app.navigationBars["找球场"].waitForExistence(timeout: 8))
        try searchAndSelectBeijingPalace(field: "course-catalog-keyword-field", text: "北京丽宫")
        XCTAssertTrue(
            waitUntilEnabled(app.buttons["start-round-primary-action"], timeout: 90),
            "nearby transport failure must still reach a startable real course through name search"
        )
    }

    func testDownloadedNearbyCourseStartsACompletelyNewRoundWithAllLiveServicesOffline() throws {
        // Phase 1: use the production path once to retain the selected course's all-hole lightweight
        // facts and topo bitmaps. Start remains immediate; this marker arrives from its background
        // download and proves that the later offline launch is not relying on another test's cache.
        launchFresh()
        guard tapContaining(["打球", "开始一场", "开始记分"]) else {
            XCTFail("the real home must open a course for the offline-cache setup")
            return
        }
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        let palace = app.buttons["start-round-course-segment-31793"]
        XCTAssertTrue(
            palace.waitForExistence(timeout: 20),
            "the production nearby result must expose the real Beijing Palace segment"
        )
        if palace.value as? String != "已选择" {
            palace.tap()
        }
        XCTAssertTrue(waitForValue("已选择", on: palace, timeout: 8))
        let onlineStart = app.buttons["start-round-primary-action"]
        XCTAssertTrue(
            waitUntilEnabled(onlineStart, timeout: 90),
            "the selected real course must load Tee authority"
        )
        XCTAssertTrue(bringIntoView(onlineStart, maxSwipes: 20))
        onlineStart.tap()
        XCTAssertTrue(app.staticTexts["第 1 洞"].waitForExistence(timeout: 90))
        let cacheReady = app.descendants(matching: .any)["live-hole-offline-course-ready"]
        let becameReady = cacheReady.waitForExistence(timeout: 240)
        if !becameReady {
            // Preserve the actual screen and accessibility state before XCTest aborts this method.
            // A failed cache gate must be diagnosable without guessing or merely extending timeouts.
            save("offline-cache-01-timeout")
            dump("offline-cache-01-timeout")
        }
        XCTAssertTrue(
            becameReady,
            "the selected course must retain every drawable hole and available topo before offline acceptance"
        )
        save("offline-cache-01-online-ready"); dump("offline-cache-01-online-ready")
        let back = app.buttons["返回球局首页"]
        XCTAssertTrue(back.waitForExistence(timeout: 5))
        back.tap()
        XCTAssertTrue(app.staticTexts["打球"].waitForExistence(timeout: 8))
        app.terminate()

        // Phase 2: disable bootstrap refresh, nearby discovery, Tee lookup, course package, per-hole
        // prep, online caddie, topo fetch, and map-upgrade polling. The only valid source now is the
        // local template and local bitmaps produced above.
        app.launchEnvironment["UITEST_FORCE_NEARBY_FAILURE"] = "1"
        app.launchEnvironment["UITEST_FORCE_COURSE_PACKAGE_FAILURE"] = "1"
        app.launchEnvironment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] = "1"
        launchFresh()

        guard tapContaining(["打球", "开始一场", "开始记分"]) else {
            XCTFail("the home must open a new round with all live services offline")
            return
        }
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        XCTAssertTrue(
            app.staticTexts["附近服务不可用；已显示下载到本机的附近球场。"]
                .waitForExistence(timeout: 20)
        )

        let downloaded = firstDownloadedCourseSegment()
        XCTAssertTrue(
            downloaded.waitForExistence(timeout: 8),
            "only a genuinely downloaded nearby course may survive the service failure"
        )
        if downloaded.value as? String != "已选择" {
            downloaded.tap()
        }
        XCTAssertTrue(waitForValue("已选择", on: downloaded, timeout: 8))

        let start = app.buttons["start-round-primary-action"]
        XCTAssertTrue(
            waitUntilEnabled(start, timeout: 20),
            "a downloaded course must remain startable without any live metadata request"
        )
        if !start.isHittable { app.swipeUp() }
        XCTAssertTrue(start.isHittable)
        start.tap()

        XCTAssertTrue(
            app.staticTexts["第 1 洞"].waitForExistence(timeout: 30),
            "the fully offline action must enter the factual first hole"
        )
        XCTAssertTrue(
            app.descendants(matching: .any)["topo-hole-base-ready"].waitForExistence(timeout: 10),
            "the offline first hole must render the retained topo bitmap, not a network loading state"
        )
        XCTAssertTrue(
            app.staticTexts.matching(
                NSPredicate(format: "label CONTAINS %@", "离线模式")
            ).firstMatch.waitForExistence(timeout: 10),
            "the live caddie must explicitly use the retained offline decision"
        )
        XCTAssertFalse(
            app.buttons["编辑第 1 洞成绩"].exists,
            "rebasing a downloaded course must not inherit a previous round's score events"
        )
        save("offline-start-01-new-first-hole"); dump("offline-start-01-new-first-hole")
    }

    // MARK: - navigation helpers

    private func launchFresh() {
        if app.state == .runningForeground { app.terminate() }
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 30), "app did not foreground")
        // Home renders cached/fixture instantly, then the funnel fetch swaps in real data.
        settle(20)
    }

    private func settle(_ seconds: TimeInterval) { Thread.sleep(forTimeInterval: seconds) }

    private func waitForValue(_ expected: String, on element: XCUIElement, timeout: TimeInterval) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        repeat {
            if (element.value as? String) == expected { return true }
            Thread.sleep(forTimeInterval: 0.2)
        } while Date() < deadline
        return (element.value as? String) == expected
    }

    private func waitUntilEnabled(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        if element.exists, element.isEnabled { return true }
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == true AND enabled == true"),
            object: element
        )
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    private func waitUntilGone(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        if !element.exists { return true }
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"),
            object: element
        )
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    private func searchAndSelectBeijingPalace(field identifier: String, text: String) throws {
        let field = app.textFields[identifier]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText(text)
        let submit = app.buttons["course-catalog-search-action"]
        XCTAssertTrue(waitUntilEnabled(submit, timeout: 5))
        submit.tap()
        XCTAssertTrue(waitUntilGone(app.keyboards.firstMatch, timeout: 8))

        let result = app.buttons["course-catalog-result-31793"]
        XCTAssertTrue(
            bringIntoView(result, maxSwipes: 30),
            "manual catalogue fallback must return the real Beijing Palace row"
        )
        result.tap()
        let selected = app.buttons["start-round-course-segment-31793"]
        XCTAssertTrue(selected.waitForExistence(timeout: 12))
        XCTAssertTrue(
            waitForValue("已选择", on: selected, timeout: 8),
            "the manually found course must become the explicit start-round selection"
        )
    }

    private func bringIntoView(_ element: XCUIElement, maxSwipes: Int) -> Bool {
        for _ in 0..<maxSwipes {
            if element.exists, element.isHittable { return true }
            app.swipeUp()
            settle(0.6)
        }
        return element.exists && element.isHittable
    }

    private func firstDownloadedCourseSegment() -> XCUIElement {
        app.buttons.matching(
            NSPredicate(format: "identifier BEGINSWITH %@", "start-round-course-segment-")
        ).firstMatch
    }

    /// Tap the first button/cell/text whose label CONTAINS any of the given fragments.
    @discardableResult
    private func tapContaining(_ fragments: [String]) -> Bool {
        for fragment in fragments {
            let predicate = NSPredicate(format: "label CONTAINS %@", fragment)
            for query in [app.buttons, app.cells, app.staticTexts, app.otherElements] {
                let match = query.matching(predicate).firstMatch
                if match.waitForExistence(timeout: 4), match.isHittable { match.tap(); return true }
            }
        }
        return false
    }

    /// Tap the tee-selector Menu. Its label is the current tee ("默认" or a colour + yardage), so try
    /// the known tee labels; fall back to any button carrying the "码" (yards) suffix.
    @discardableResult
    private func tapTeeSelector() -> Bool {
        if tapContaining(["默认", "蓝 T", "白 T", "红 T", "金 T", "黑 T", "黄 T", "绿 T", "银 T"]) {
            return true
        }
        let predicate = NSPredicate(format: "label CONTAINS '码'")
        let byYards = app.buttons.matching(predicate).firstMatch
        if byYards.waitForExistence(timeout: 4), byYards.isHittable { byYards.tap(); return true }
        return false
    }

    // MARK: - diagnostics

    /// Probe GET /courses/{gid}/tees so a "no tee options" result is diagnosable as
    /// funnel-unreachable / bad-token / geometry-absent (token length only — never the token itself).
    private func writeDiagnostics() {
        let url = cfg("AI_CADDIE_API_BASE_URL") ?? ""
        let token = cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        var lines = ["resolvedURL=\(url)", "tokenLen=\(token.count)"]
        // 北京丽宫 (gid 31793) — the real course selected by the injected blue-tee fix.
        if let probeURL = URL(string: url + "/api/v2/courses/31793/tees") {
            var request = URLRequest(url: probeURL)
            request.timeoutInterval = 40
            request.setValue(token, forHTTPHeaderField: "x-ai-caddie-admin-token")
            let semaphore = DispatchSemaphore(value: 0)
            URLSession.shared.dataTask(with: request) { data, response, error in
                let code = (response as? HTTPURLResponse)?.statusCode ?? -1
                lines.append("tees.status=\(code)")
                if let error { lines.append("tees.error=\(error.localizedDescription)") }
                if let data, let body = String(data: data, encoding: .utf8) {
                    lines.append("tees.body=\(String(body.prefix(400)))")
                }
                semaphore.signal()
            }.resume()
            _ = semaphore.wait(timeout: .now() + 45)
        } else {
            lines.append("tees.skipped=invalid-url")
        }
        try? lines.joined(separator: "\n").data(using: .utf8)?
            .write(to: realShotsDir().appendingPathComponent("tees-diagnostics.txt"))
    }

    // MARK: - capture helpers

    private func realShotsDir() -> URL {
        let base = (try? FileManager.default.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? FileManager.default.temporaryDirectory
        let dir = base.appendingPathComponent("real-screenshots", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func save(_ name: String) {
        let shot = XCUIScreen.main.screenshot()
        try? shot.pngRepresentation.write(to: realShotsDir().appendingPathComponent("\(name).png"))
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        print("WROTE_REAL_SCREENSHOT \(name)")
    }

    private func dump(_ name: String) {
        try? app.debugDescription.data(using: .utf8)?
            .write(to: realShotsDir().appendingPathComponent("tree-\(name).txt"))
    }
}
