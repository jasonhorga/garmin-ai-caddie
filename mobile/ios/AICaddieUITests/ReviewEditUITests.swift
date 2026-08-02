import XCTest

/// Real running-app screenshots of the **复盘编辑** flow (PR2) from the iOS Simulator (XCUITest).
/// Launches the ACTUAL app against the live backend (funnel) with the owner admin token, navigates
/// 历史复盘 → a round → a hole's 落点图, taps 「编辑」, and captures each edit affordance: drag handles
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
        app.launchEnvironment["UITEST_GPS_LAT"] = cfg("UITEST_GPS_LAT") ?? "40.0454995"
        app.launchEnvironment["UITEST_GPS_LON"] = cfg("UITEST_GPS_LON") ?? "116.5461531"
        app.launchEnvironment["UITEST_MODE"] = "1"
    }

    func testCaptureReviewEditFlow() throws {
        // ---- Navigate to a round review, then into one hole's 落点图 ----
        launchFresh()
        save("00-home"); dump("00-home")

        guard tapContaining(["历史复盘", "逐场逐洞"]) else {
            save("nohistory"); dump("nohistory"); return
        }
        settle(6)
        save("01-history-list"); dump("01-history-list")
        // The newest owner rows can be CI-polluted manual rounds with coincident Tee coordinates.
        // Open a known read-only Garmin round through the DEBUG navigation seed so edit evidence
        // contains real spatially separated landings and clubs without mutating Production history.
        app.launchEnvironment["UITEST_REVIEW_ROUND_REF"] = "17534238"
        app.launchEnvironment["UITEST_REVIEW_COURSE_NAME"] = "北京天竺黑骑士球员俱乐部"
        launchFresh()
        app.launchEnvironment.removeValue(forKey: "UITEST_REVIEW_ROUND_REF")
        app.launchEnvironment.removeValue(forKey: "UITEST_REVIEW_COURSE_NAME")
        let roundReview = app.navigationBars["单场复盘"]
        guard roundReview.waitForExistence(timeout: 12) else {
            XCTFail("review-edit evidence must enter 单场复盘 before capture")
            return
        }
        settle(2); save("02-round-review"); dump("02-round-review")

        // The scorecard rows are buttons ("点一洞看落点图 →"); tapping one opens the 落点图 pager sheet.
        // The approved edit evidence is hole 1. Garmin round 17534238 returns multiple separated
        // non-putt GPS positions there; they must remain editable before the add-shot flow counts.
        let holeButton = app.buttons["round-review-hole-1"]
        guard holeButton.waitForExistence(timeout: 60), bringIntoViewAndTap(holeButton, maxSwipes: 4) else {
            save("nohole"); dump("nohole"); return
        }
        guard app.buttons["关闭"].waitForExistence(timeout: 12) else {
            XCTFail("review-edit evidence must enter the shot-map pager before capture")
            return
        }
        // As in RealFlowUITests, leave a quiet main-thread window for the real response to decode
        // and commit before XCUITest begins repeated accessibility hierarchy snapshots.
        settle(12)
        let topoReady = app.descendants(matching: .any)
            .matching(identifier: "topo-hole-base-ready").firstMatch
        guard topoReady.waitForExistence(timeout: 75) else {
            XCTFail("review-edit evidence must load the real first-hole topo")
            return
        }
        settle(2); save("03-shot-map"); dump("03-shot-map")

        guard app.buttons["编辑"].waitForExistence(timeout: 12) else {
            save("noeditbtn"); dump("noeditbtn"); return
        }

        // ---- Enter edit mode → drag handles appear on every landing ----
        guard tapButton("编辑") else { save("noeditbtn2"); dump("noeditbtn2"); return }
        let editTopoReady = app.descendants(matching: .any)
            .matching(identifier: "topo-hole-base-ready").firstMatch
        guard editTopoReady.waitForExistence(timeout: 75), app.buttons["Reorder 2"].waitForExistence(timeout: 12) else {
            XCTFail("edit evidence requires the real topo and the two real recorded shots returned for this hole")
            return
        }
        settle(2); save("04-edit-handles"); dump("04-edit-handles")

        // ---- 补一杆: tap empty map → the add sheet appears; cancel (no write) ----
        mapPoint(dx: 0.18, dy: 0.42).tap()
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
    private func bringIntoViewAndTap(_ element: XCUIElement, maxSwipes: Int) -> Bool {
        for _ in 0..<maxSwipes {
            if element.exists, element.isHittable { element.tap(); return true }
            app.swipeUp()
            settle(0.6)
        }
        if element.exists, element.isHittable { element.tap(); return true }
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
