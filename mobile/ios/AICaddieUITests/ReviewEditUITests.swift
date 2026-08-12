import XCTest

/// Real running-app screenshots of the **复盘编辑** flow (PR2) from the iOS Simulator (XCUITest).
/// Launches the ACTUAL app against the live backend (funnel) with the owner admin token, navigates
/// 成绩 → 全部球局 → a round → a hole's 落点图, taps 「编辑」, and captures each edit affordance: drag handles
/// on every landing, the 「补一杆」 add sheet, the 「改这一杆」 edit sheet, and (optionally) a handle drag.
///
/// Runs on-demand only (`native-mobile.yml` gates the AICaddieUITests scheme behind workflow_dispatch),
/// same as ``RealFlowUITests``. PNGs + per-screen element-tree dumps land in the test process Documents
/// dir; the workflow collects `*Documents/real-screenshots/*`.
///
/// **Safe by default:** every step that would WRITE a correction to the owner's real history (confirming
/// an add, committing a drag) is gated behind `UITEST_ALLOW_EDIT_WRITES=1`. Without it, the test only
/// opens sheets and cancels/dismisses them — it never mutates data — so a routine capture run is read-only.
final class ReviewEditUITests: XCTestCase {
    private let app = XCUIApplication()

    private func cfg(_ key: String) -> String? {
        let env = ProcessInfo.processInfo.environment
        return env[key] ?? env["TEST_RUNNER_\(key)"]
    }

    private var allowWrites: Bool { (cfg("UITEST_ALLOW_EDIT_WRITES") ?? "0") == "1" }

    override func setUpWithError() throws {
        continueAfterFailure = true
        app.launchEnvironment["AI_CADDIE_API_BASE_URL"] = cfg("AI_CADDIE_API_BASE_URL") ?? ""
        app.launchEnvironment["AI_CADDIE_ADMIN_TOKEN"] = cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        app.launchEnvironment["UITEST_GPS_LAT"] = cfg("UITEST_GPS_LAT") ?? "40.083"
        app.launchEnvironment["UITEST_GPS_LON"] = cfg("UITEST_GPS_LON") ?? "116.585"
        app.launchEnvironment["UITEST_MODE"] = "1"
    }

    func testCaptureReviewEditFlow() throws {
        // ---- Navigate to a round review, then into one hole's 落点图 ----
        launchFresh()
        save("00-home"); dump("00-home")

        guard tapContaining(["成绩", "球局 · 统计"]) else {
            save("nohistory"); dump("nohistory"); return
        }
        settle(6)
        guard tapContaining(["全部球局", "搜索 · 年份"]) else {
            save("noarchive"); dump("noarchive"); return
        }
        settle(6); save("01-history-list"); dump("01-history-list")

        guard tapFirstRoundRow() else { save("noround"); dump("noround"); return }
        settle(6); save("02-round-review"); dump("02-round-review")

        // The scorecard rows are buttons ("点一洞看落点图 →"); tapping one opens the 落点图 pager sheet.
        guard tapFirstHoleRow() else { save("nohole"); dump("nohole"); return }
        settle(6); save("03-shot-map"); dump("03-shot-map")

        // Some holes are "这一洞暂无落点数据" (no geometry → no 编辑 toggle). Swipe the pager to a hole
        // that actually has a map so the edit affordances are reachable (try up to 12 holes).
        var reachedEdit = false
        for i in 0..<12 {
            if app.buttons["编辑"].waitForExistence(timeout: 3) { reachedEdit = true; break }
            app.swipeLeft(); settle(2)
            if i == 3 || i == 7 { save("03b-hole-\(i)"); dump("03b-hole-\(i)") }
        }
        guard reachedEdit else { save("noeditbtn"); dump("noeditbtn"); return }

        // ---- Enter edit mode → drag handles appear on every landing ----
        guard tapButton("编辑") else { save("noeditbtn2"); dump("noeditbtn2"); return }
        settle(3); save("04-edit-handles"); dump("04-edit-handles")

        // ---- 补一杆: tap empty map → the add sheet appears; cancel (no write) ----
        mapPoint(dx: 0.5, dy: 0.30).tap()
        settle(2); save("05-add-sheet"); dump("05-add-sheet")
        _ = tapButton("取消")
        settle(1)

        // ---- 改这一杆: tap a landing → the edit sheet appears; dismiss with 完成 (no write) ----
        mapPoint(dx: 0.5, dy: 0.5).tap()
        settle(2); save("06-edit-sheet"); dump("06-edit-sheet")
        _ = tapButton("完成")
        settle(1)

        // ---- Drag a handle (WRITES a move) — gated so routine runs stay read-only ----
        if allowWrites {
            let start = mapPoint(dx: 0.5, dy: 0.5)
            let end = mapPoint(dx: 0.56, dy: 0.44)
            start.press(forDuration: 0.7, thenDragTo: end)
            settle(2); save("07-drag-move"); dump("07-drag-move")
        }

        // Leave edit mode (unlocks 翻洞). 完成 is the same nav button toggled.
        _ = tapButton("完成")
        settle(2); save("08-edit-done"); dump("08-edit-done")
    }

    // MARK: - navigation helpers

    private func launchFresh() {
        if app.state == .runningForeground { app.terminate() }
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 30), "app did not foreground")
        settle(20)
    }

    private func settle(_ seconds: TimeInterval) { Thread.sleep(forTimeInterval: seconds) }

    /// A screen coordinate at a normalized offset of the app window — used to tap/drag the Canvas map
    /// (its landings/handles are drawn, not accessibility elements, so there's nothing to query).
    private func mapPoint(dx: Double, dy: Double) -> XCUICoordinate {
        app.coordinate(withNormalizedOffset: CGVector(dx: dx, dy: dy))
    }

    @discardableResult
    private func tapButton(_ label: String) -> Bool {
        let button = app.buttons[label]
        if button.waitForExistence(timeout: 5), button.isHittable { button.tap(); return true }
        // Fallback: any element whose label EQUALS the target.
        let predicate = NSPredicate(format: "label == %@", label)
        for query in [app.buttons, app.staticTexts, app.otherElements] {
            let match = query.matching(predicate).firstMatch
            if match.waitForExistence(timeout: 3), match.isHittable { match.tap(); return true }
        }
        return false
    }

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

    @discardableResult
    private func tapFirstRoundRow() -> Bool {
        let cell = app.cells.firstMatch
        if cell.waitForExistence(timeout: 6), cell.isHittable { cell.tap(); return true }
        let predicate = NSPredicate(format: "label CONTAINS '杆' OR label CONTAINS '20' OR label MATCHES '.*[0-9]+.*'")
        let row = app.buttons.matching(predicate).firstMatch
        if row.waitForExistence(timeout: 4), row.isHittable { row.tap(); return true }
        return false
    }

    /// A scorecard hole row inside the round review — buttons carrying "P<par>" / a score chip. Prefer
    /// a button whose label mentions par, else the first hittable button in the scorecard area.
    @discardableResult
    private func tapFirstHoleRow() -> Bool {
        let predicate = NSPredicate(format: "label CONTAINS 'P' OR label MATCHES '.*[0-9]+.*'")
        let holeButton = app.buttons.matching(predicate).firstMatch
        if holeButton.waitForExistence(timeout: 5), holeButton.isHittable { holeButton.tap(); return true }
        let anyButton = app.buttons.firstMatch
        if anyButton.waitForExistence(timeout: 3), anyButton.isHittable { anyButton.tap(); return true }
        return false
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
        try? shot.pngRepresentation.write(to: realShotsDir().appendingPathComponent("edit-\(name).png"))
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = "edit-\(name)"
        attachment.lifetime = .keepAlways
        add(attachment)
        print("WROTE_REAL_SCREENSHOT edit-\(name)")
    }

    private func dump(_ name: String) {
        try? app.debugDescription.data(using: .utf8)?
            .write(to: realShotsDir().appendingPathComponent("tree-edit-\(name).txt"))
    }
}
