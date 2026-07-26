import XCTest

/// Real running-app screenshots from the iOS Simulator (XCUITest) — NOT ImageRenderer view snapshots.
/// Launches the ACTUAL app pointed at the live backend (funnel) with the owner admin token and a
/// simulated on-course GPS fix (all via launchEnvironment), navigates the real UI, and captures real
/// screens with `XCUIScreen.main.screenshot()`. PNGs + per-screen accessibility-tree dumps are written
/// to the test process Documents dir; native-mobile.yml collects `*Documents/real-screenshots/*`.
///
/// Each section relaunches from a known home state (back-navigation in SwiftUI is fragile), captures the
/// screen, and dumps its element tree so any tap that misses is fixable next iteration without guessing.
final class RealFlowUITests: XCTestCase {
    private let app = XCUIApplication()

    /// Read a config value the test runner may receive either plain or TEST_RUNNER_-prefixed (xcodebuild
    /// reliably forwards TEST_RUNNER_<VAR> into the UI-test runner environment; the plain form is a
    /// fallback in case it propagates too).
    private func cfg(_ key: String) -> String? {
        let env = ProcessInfo.processInfo.environment
        return env[key] ?? env["TEST_RUNNER_\(key)"]
    }

    override func setUpWithError() throws {
        continueAfterFailure = true
        app.launchEnvironment["AI_CADDIE_API_BASE_URL"] = cfg("AI_CADDIE_API_BASE_URL") ?? ""
        app.launchEnvironment["AI_CADDIE_ADMIN_TOKEN"] = cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        app.launchEnvironment["UITEST_GPS_LAT"] = cfg("UITEST_GPS_LAT") ?? "40.0454995"
        app.launchEnvironment["UITEST_GPS_LON"] = cfg("UITEST_GPS_LON") ?? "116.5461531"
        app.launchEnvironment["UITEST_MODE"] = "1"
    }

    func testCaptureRealAppFlow() throws {
        writeDiagnostics()
        // ---- Section 1: home + the two macro tiles (stats) ----
        launchFresh()
        save("01-home"); dump("01-home")
        XCTAssertFalse(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Unknown course")).firstMatch.exists,
            "UI-test bootstrap must load the real home course, not auto-activate the implicit DEBUG round 900001"
        )
        if tapContaining(["数据统计", "均杆 · 趋势"]) {
            settle(7); save("02-stats"); dump("02-stats")
        }

        // ---- Section 2: history list → a round review → shot-map → review-edit (merged #276) ----
        launchFresh()
        if tapContaining(["历史复盘", "逐场逐洞"]) {
            settle(6); save("03-history-list"); dump("03-history-list")
            if tapFirstRoundRow() {
                settle(6); save("04-round-review"); dump("04-round-review")
                // Tap a hole row (label like "1, 推 2, P5, 8") → that hole's shot-map (has the 编辑 toggle).
                let holeRow = app.buttons.matching(NSPredicate(format: "label CONTAINS ', P'")).firstMatch
                if holeRow.waitForExistence(timeout: 5), holeRow.isHittable {
                    holeRow.tap()
                    settle(6); save("04b-shot-map"); dump("04b-shot-map")
                    if tapContaining(["编辑"]) {
                        settle(3); save("04c-edit-mode"); dump("04c-edit-mode")
                        // Tap the map render area to open the 补一杆/改杆 sheet (best-effort centre tap).
                        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.42)).tap()
                        settle(2); save("04d-edit-sheet"); dump("04d-edit-sheet")
                    }
                }
            }
        }

        // ---- Section 3: last-round review shortcut from home ----
        launchFresh()
        if tapContaining(["上一场"]) {
            settle(6); save("05-last-round-review"); dump("05-last-round-review")
        }

        // ---- Section 4: pre-round prep on the nearest real course (黑骑士 via injected GPS) ----
        // READ-ONLY (GET /courses/{id}/prep) — shows real geometry F/M/B + caddie + hazards WITHOUT
        // starting a live round, so CI never writes a junk round into the owner's real history.
        launchFresh()
        if tapContaining(["赛前攻略", "选球场 · 逐洞"]) {
            settle(9); save("06-prep-overview"); dump("06-prep-overview")
            // Enter a real course (黑骑士 A 场, or the first 全场) → per-hole prep carries real geometry.
            if tapCourseSegment() {
                settle(9); save("07-prep-course"); dump("07-prep-course")
                if tapContaining(["逐洞攻略"]) {
                    settle(8); save("08-prep-hole"); dump("08-prep-hole")  // F/M/B + caddie + hazards
                }
                if tapContaining(["针对你"]) {
                    settle(7); save("09-prep-foryou"); dump("09-prep-foryou")
                }
            }
        }

        // ---- Section 5: start the selected real course — GET package only, no score/backend write ----
        launchFresh()
        XCTAssertTrue(tapContaining(["打球", "开始一场"]), "home must expose the real start-round path")
        settle(9)
        XCTAssertTrue(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "北京丽宫")).firstMatch.exists,
            "simulated course location must select 北京丽宫"
        )
        XCTAssertTrue(tapContaining(["开始记分"]), "selected real course must be startable")
        XCTAssertTrue(
            app.staticTexts["363"].waitForExistence(timeout: 60),
            "cold-loaded 北京丽宫 hole prep must expose the blue-tee center-green distance"
        )
        save("10-live-hole"); dump("10-live-hole")
        XCTAssertTrue(app.staticTexts["第 1 洞"].exists, "starting 北京丽宫 must enter its real first hole")
        XCTAssertTrue(app.staticTexts["342"].exists, "front-green distance must render")
        XCTAssertTrue(app.staticTexts["379"].exists, "back-green distance must render")
        if tapContaining(["展开", "看完整方案", "换打法", "备选打法"]) {
            settle(3); save("11-caddie-plan"); dump("11-caddie-plan")
        }
    }

    // MARK: - navigation helpers

    private func launchFresh() {
        if app.state == .runningForeground { app.terminate() }
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 30), "app did not foreground")
        // Home renders cached/fixture instantly, then the funnel fetch (Phase 2) swaps in real data.
        settle(20)
    }

    private func settle(_ seconds: TimeInterval) { Thread.sleep(forTimeInterval: seconds) }

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

    /// Tap a course-segment row BUTTON (not the inner static text — that wouldn't fire the NavigationLink)
    /// so the prep detail actually opens. Exact labels first (黑骑士 A 场 / a 全场), then any "…场" button.
    @discardableResult
    private func tapCourseSegment() -> Bool {
        // Prefer the stable accessibilityIdentifier (now a full-row tap target) → reliable navigation.
        let byId = app.buttons.matching(identifier: "prep-course-row").firstMatch
        if byId.waitForExistence(timeout: 6) { byId.tap(); return true }
        for label in ["A 场, 9 洞", "全场, 18 洞"] {
            let button = app.buttons[label]
            if button.waitForExistence(timeout: 4) { button.tap(); return true }
        }
        return false
    }

    /// First list row in a history list — try cells then buttons (SwiftUI List rows surface either way).
    @discardableResult
    private func tapFirstRoundRow() -> Bool {
        let cell = app.cells.firstMatch
        if cell.waitForExistence(timeout: 6), cell.isHittable { cell.tap(); return true }
        // a date/score-bearing button row
        let predicate = NSPredicate(format: "label CONTAINS '杆' OR label CONTAINS '20' OR label MATCHES '.*[0-9]+.*'")
        let row = app.buttons.matching(predicate).firstMatch
        if row.waitForExistence(timeout: 4), row.isHittable { row.tap(); return true }
        return false
    }

    // MARK: - diagnostics

    /// Writes what the test runner resolved for backend config + a live probe of the funnel, so a
    /// "still showing fixtures" result is immediately diagnosable as env-not-propagated vs.
    /// funnel-unreachable vs. bad-token (without leaking the token — only its length is recorded).
    private func writeDiagnostics() {
        let url = cfg("AI_CADDIE_API_BASE_URL") ?? ""
        let token = cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        var lines = [
            "resolvedURL=\(url)",
            "tokenLen=\(token.count)",
            "gps=\(cfg("UITEST_GPS_LAT") ?? "-"),\(cfg("UITEST_GPS_LON") ?? "-")",
        ]
        if let probeURL = URL(string: url + "/api/v2/history/summary") {
            var request = URLRequest(url: probeURL)
            request.timeoutInterval = 40
            request.setValue(token, forHTTPHeaderField: "x-ai-caddie-admin-token")
            let semaphore = DispatchSemaphore(value: 0)
            URLSession.shared.dataTask(with: request) { data, response, error in
                let code = (response as? HTTPURLResponse)?.statusCode ?? -1
                lines.append("probe.status=\(code)")
                if let error { lines.append("probe.error=\(error.localizedDescription)") }
                if let data, let body = String(data: data, encoding: .utf8) {
                    lines.append("probe.body=\(String(body.prefix(240)))")
                }
                semaphore.signal()
            }.resume()
            _ = semaphore.wait(timeout: .now() + 45)
        } else {
            lines.append("probe.skipped=invalid-url")
        }
        try? lines.joined(separator: "\n").data(using: .utf8)?
            .write(to: realShotsDir().appendingPathComponent("diagnostics.txt"))
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
