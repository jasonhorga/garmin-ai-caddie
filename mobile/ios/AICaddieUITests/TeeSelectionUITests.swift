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
        continueAfterFailure = true
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
            return
        }
        settle(9)
        save("02-start-round"); dump("02-start-round")  // 选球场 + 发球台 row + 开始记分
        XCTAssertTrue(
            app.staticTexts["选择全场开始 18 洞球局。"].waitForExistence(timeout: 5),
            "an 18-hole whole-course selection must not describe itself as a 9-hole loop"
        )

        // Open the 发球台 selector (a SwiftUI Menu whose label is the current tee, e.g. "蓝 T · 6412 码"
        // or "默认"). Tapping it reveals the tee options with yardage from GET /courses/{id}/tees.
        if tapTeeSelector() {
            settle(2)
            save("03-tee-menu"); dump("03-tee-menu")  // open menu: colour + yards choices
            XCTAssertTrue(
                app.buttons["取消"].waitForExistence(timeout: 5),
                "the open tee menu must offer an explicit non-mutating dismissal"
            )
        } else {
            dump("03-tee-menu-missing")
        }
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
