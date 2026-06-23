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
        app.launchEnvironment["UITEST_GPS_LAT"] = cfg("UITEST_GPS_LAT") ?? "40.083"
        app.launchEnvironment["UITEST_GPS_LON"] = cfg("UITEST_GPS_LON") ?? "116.585"
        app.launchEnvironment["UITEST_MODE"] = "1"
    }

    func testCaptureRealAppFlow() throws {
        writeDiagnostics()
        // ---- Section 1: home + the two macro tiles (stats) ----
        launchFresh()
        save("01-home"); dump("01-home")
        if tapContaining(["数据统计", "均杆 · 趋势"]) {
            settle(7); save("02-stats"); dump("02-stats")
        }

        // ---- Section 2: history list → a round review ----
        launchFresh()
        if tapContaining(["历史复盘", "逐场逐洞"]) {
            settle(6); save("03-history-list"); dump("03-history-list")
            if tapFirstRoundRow() {
                settle(6); save("04-round-review"); dump("04-round-review")
            }
        }

        // ---- Section 3: last-round review shortcut from home ----
        launchFresh()
        if tapContaining(["上一场"]) {
            settle(6); save("05-last-round-review"); dump("05-last-round-review")
        }

        // ---- Section 4: start a round → live hole (the real round simulation) ----
        launchFresh()
        // Prefer continuing a real in-progress round straight into the live hole; else start fresh.
        if tapContaining(["进行中", "继续这场"]) {
            settle(8); save("06-live-hole"); dump("06-live-hole")
            captureLiveHoleDetails()
        } else if tapButton(exact: "开始一场") {
            settle(6); save("06a-start-round"); dump("06a-start-round")
            // Pick the first real course, then start scoring.
            _ = tapFirstCourseRow()
            settle(3)
            if tapContaining(["开始记分"]) {
                settle(8); save("07-live-hole"); dump("07-live-hole")
                captureLiveHoleDetails()
            }
        }
    }

    /// On the live hole, expand the caddie / more-adjustments so the recommendation + sequence show.
    private func captureLiveHoleDetails() {
        if tapContaining(["看完整方案", "换打法", "备选打法"]) {
            settle(3); save("08-caddie-plan"); dump("08-caddie-plan")
        }
        if tapContaining(["更多调整"]) {
            settle(2); save("09-more-adjust"); dump("09-more-adjust")
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

    @discardableResult
    private func tapButton(exact label: String) -> Bool {
        let b = app.buttons[label]
        if b.waitForExistence(timeout: 6), b.isHittable { b.tap(); return true }
        return false
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

    @discardableResult
    private func tapFirstCourseRow() -> Bool {
        // The course list rows are buttons/cells carrying a course name; tap the first hittable one
        // that isn't the start/tee control.
        for query in [app.cells, app.buttons] {
            for i in 0..<min(query.count, 8) {
                let el = query.element(boundBy: i)
                guard el.exists, el.isHittable else { continue }
                let label = el.label
                if label.contains("开始记分") || label.contains("发球台") || label.contains("T") { continue }
                el.tap(); return true
            }
        }
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
