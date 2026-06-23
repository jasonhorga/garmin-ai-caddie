import XCTest

/// Real running-app screenshots from the iOS Simulator (XCUITest), NOT ImageRenderer view snapshots.
/// The test launches the ACTUAL app pointed at the live backend (funnel) with the owner admin token and
/// a simulated on-course GPS fix (all via launchEnvironment), then navigates and captures real screens
/// with `XCUIScreen.main.screenshot()`. PNGs + a UI element-tree dump are written to the test process
/// Documents dir; native-mobile.yml collects `*Documents/real-screenshots/*` as the `real-screenshots`
/// artifact.
///
/// Phase 1a: launch → home screenshot → dump the element tree (so the exact tappable labels/identifiers
/// are known for the deeper start-round / play-hole / history navigation added next). Taps are
/// best-effort — a missing element never fails the run, it just limits how far we get this round.
final class RealFlowUITests: XCTestCase {
    private let app = XCUIApplication()

    override func setUpWithError() throws {
        continueAfterFailure = true
        let env = ProcessInfo.processInfo.environment
        // Backend config the app already reads from its process environment (AICaddieApp.defaultAdminToken /
        // defaultAPIBaseURL). Forward what CI injected so the real app talks to the real backend.
        app.launchEnvironment["AI_CADDIE_API_BASE_URL"] = env["AI_CADDIE_API_BASE_URL"] ?? ""
        app.launchEnvironment["AI_CADDIE_ADMIN_TOKEN"] = env["AI_CADDIE_ADMIN_TOKEN"] ?? ""
        // Simulated on-course GPS so the live hole renders real distances (LocationProvider env path).
        app.launchEnvironment["UITEST_GPS_LAT"] = env["UITEST_GPS_LAT"] ?? "40.197"
        app.launchEnvironment["UITEST_GPS_LON"] = env["UITEST_GPS_LON"] ?? "116.49"
        app.launchEnvironment["UITEST_MODE"] = "1"
    }

    func testCaptureRealAppFlow() throws {
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 30), "app did not reach foreground")
        // Home package is fetched from the funnel on launch; give it time to render real data.
        Thread.sleep(forTimeInterval: 10)
        save("01-home")
        dumpElementTree("01-home")

        // Best-effort: tap into pre-round prep / start a round if a recognizable control is present.
        // Exact labels are confirmed from the element-tree dump and tightened in the next iteration.
        if tapFirst(labels: ["开始打球", "开始一场", "去备战", "继续这场", "手机记分"]) {
            Thread.sleep(forTimeInterval: 6)
            save("02-after-start")
            dumpElementTree("02-after-start")
        }
    }

    // MARK: - helpers

    @discardableResult
    private func tapFirst(labels: [String]) -> Bool {
        for label in labels {
            let byId = app.descendants(matching: .any).matching(identifier: label).firstMatch
            if byId.exists && byId.isHittable { byId.tap(); return true }
            let button = app.buttons[label]
            if button.exists && button.isHittable { button.tap(); return true }
            let staticText = app.staticTexts[label]
            if staticText.exists && staticText.isHittable { staticText.tap(); return true }
        }
        return false
    }

    private func realShotsDir() -> URL {
        let base = (try? FileManager.default.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? FileManager.default.temporaryDirectory
        let dir = base.appendingPathComponent("real-screenshots", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func save(_ name: String) {
        let shot = XCUIScreen.main.screenshot()
        // Write a PNG for artifact collection (the design-snapshot pipeline collects Documents PNGs).
        try? shot.pngRepresentation.write(to: realShotsDir().appendingPathComponent("\(name).png"))
        // Also attach to the .xcresult for local inspection.
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        print("WROTE_REAL_SCREENSHOT \(name)")
    }

    /// Dump the accessibility element tree so the deeper-navigation iteration knows exact labels.
    private func dumpElementTree(_ name: String) {
        let tree = app.debugDescription
        try? tree.data(using: .utf8)?.write(to: realShotsDir().appendingPathComponent("tree-\(name).txt"))
    }
}
