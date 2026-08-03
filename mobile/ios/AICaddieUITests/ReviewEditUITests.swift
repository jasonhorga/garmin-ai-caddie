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
/// **Safe by default:** every step that would WRITE a correction to the owner's real history is gated
/// behind `UITEST_ALLOW_EDIT_WRITES=1`. Routine evidence runs launch the real app in a strict Debug-only
/// read-only drag mode: the production gesture and local rubber-band run, but its correction POST is skipped.
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
        if !allowWrites {
            app.launchEnvironment["UITEST_READ_ONLY_DRAG_PREVIEW"] = "1"
        }
    }

    func testCaptureReviewEditFlow() throws {
        let reviewEvidence = try resolveReviewEvidence()
        // ---- Navigate to a round review, then into one hole's 落点图 ----
        launchFresh()
        save("00-home"); dump("00-home")

        guard tapContaining(["历史复盘", "逐场逐洞"]) else {
            save("nohistory"); dump("nohistory"); return
        }
        settle(6)
        save("01-history-list"); dump("01-history-list")
        // The newest owner rows can be CI-polluted manual rounds with coincident Tee coordinates.
        // Open the read-only Garmin round verified against the live scorecard + shot-map contracts,
        // so edit evidence has real separated landings and clubs without mutating Production history.
        app.launchEnvironment["UITEST_REVIEW_ROUND_REF"] = reviewEvidence.roundRef
        app.launchEnvironment["UITEST_REVIEW_COURSE_NAME"] = reviewEvidence.courseName
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
        // The resolver selected this hole only after proving multiple separated, club-labelled GPS
        // positions; they must remain editable before the add-shot flow counts.
        let holeButton = app.buttons["round-review-hole-\(reviewEvidence.hole)"]
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
            XCTFail("review-edit evidence must load the verified evidence-hole topo")
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
        editTopoReady.coordinate(withNormalizedOffset: CGVector(
            dx: reviewEvidence.emptyMapPoint.x,
            dy: reviewEvidence.emptyMapPoint.y
        )).tap()
        let addSheet = app.navigationBars["补一杆"]
        XCTAssertTrue(addSheet.waitForExistence(timeout: 5), "05 must be the real 补一杆 sheet")
        settle(2); save("05-add-sheet"); dump("05-add-sheet")
        let cancelAdd = addSheet.buttons["取消"]
        XCTAssertTrue(cancelAdd.exists && cancelAdd.isHittable, "the add sheet must expose its own cancel action")
        cancelAdd.tap()
        XCTAssertTrue(waitUntilGone(addSheet, timeout: 5), "cancel must dismiss the add sheet before editing a landing")
        settle(1)

        // ---- 改这一杆: tap a landing → the edit sheet appears; dismiss with 完成 (no write) ----
        // Use the real topo element as the coordinate frame and the endpoint verified by the same
        // live shot-map response. A screen-centre guess can hit empty map and silently reopen 补一杆.
        editTopoReady.coordinate(withNormalizedOffset: CGVector(
            dx: reviewEvidence.landing.x,
            dy: reviewEvidence.landing.y
        )).tap()
        let editSheet = app.navigationBars["改这一杆"]
        XCTAssertTrue(editSheet.waitForExistence(timeout: 5), "06 must edit a recorded landing, not reopen 补一杆")
        settle(2); save("06-edit-sheet"); dump("06-edit-sheet")
        let finishEditSheet = editSheet.buttons["完成"]
        XCTAssertTrue(finishEditSheet.exists && finishEditSheet.isHittable, "the edit sheet must expose its own completion action")
        finishEditSheet.tap()
        XCTAssertTrue(waitUntilGone(editSheet, timeout: 5), "sheet completion must return to the editable map")
        settle(1)

        // ---- Drag a real handle. Routine runs preserve the local preview but skip the correction POST. ----
        // Reuse the verified landing coordinate that opened 改这一杆 above. Move inward so an edge
        // landing still produces a real handle drag rather than an off-map gesture.
        let dragDestination = dragDestination(from: reviewEvidence.landing)
        let dragStart = editTopoReady.coordinate(withNormalizedOffset: CGVector(
            dx: reviewEvidence.landing.x,
            dy: reviewEvidence.landing.y
        ))
        let dragEnd = editTopoReady.coordinate(withNormalizedOffset: CGVector(
            dx: dragDestination.x,
            dy: dragDestination.y
        ))
        // Hold the real gesture at its destination long enough for the workflow's simulator video
        // to retain a clean frame of the product loupe before release. The still captured below is
        // intentionally the committed post-drag state; the held video frame is the same-state I30
        // evidence for the approved magnifier instead of mislabelling that still as an active drag.
        dragStart.press(
            forDuration: 0.7,
            thenDragTo: dragEnd,
            withVelocity: .slow,
            thenHoldForDuration: 2
        )
        settle(2); save("07-drag-move"); dump("07-drag-move")

        // Leave edit mode (unlocks 翻洞). 完成 is the same nav button toggled.
        let finishMapEdit = app.buttons["完成"].firstMatch
        XCTAssertTrue(
            finishMapEdit.waitForExistence(timeout: 5) && finishMapEdit.isHittable,
            "the parent edit mode must still expose 完成 after the child sheet closes"
        )
        finishMapEdit.tap()
        XCTAssertTrue(
            app.buttons["编辑"].waitForExistence(timeout: 12),
            "08 may be captured only after the map has returned to read-only mode"
        )
        XCTAssertFalse(app.navigationBars["补一杆"].exists, "08 must never retain a mislabeled add sheet")
        XCTAssertFalse(app.navigationBars["改这一杆"].exists, "08 must never retain a mislabeled edit sheet")
        // Switching from RoundShotEditContent back to the read-only RoundShotMapView creates a new
        // AsyncImage.  The 编辑 button returns before that image has finished loading, so waiting a
        // fixed two seconds can capture the transient "球场地图加载中…" overlay as if it were I31.
        // A fast cache hit may make the loading element too brief to observe; either way, the final
        // gate is a newly-ready real topo with no loading element left in the hierarchy.
        let readOnlyTopoLoading = app.descendants(matching: .any)
            .matching(identifier: "topo-hole-base-loading").firstMatch
        _ = readOnlyTopoLoading.waitForExistence(timeout: 5)
        XCTAssertTrue(
            waitUntilGone(readOnlyTopoLoading, timeout: 75),
            "08 may be captured only after the read-only topo loading overlay disappears"
        )
        let readOnlyTopoReady = app.descendants(matching: .any)
            .matching(identifier: "topo-hole-base-ready").firstMatch
        XCTAssertTrue(
            readOnlyTopoReady.waitForExistence(timeout: 75),
            "08 requires the real read-only topo after leaving edit mode"
        )
        XCTAssertFalse(readOnlyTopoLoading.exists, "08 must not contain 球场地图加载中…")
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

    private func waitUntilGone(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        if !element.exists { return true }
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"),
            object: element
        )
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    private func resolveReviewEvidence() throws -> RealEvidenceRound {
        let resolver = try RealEvidenceRoundResolver(
            baseURL: cfg("AI_CADDIE_API_BASE_URL") ?? "",
            adminToken: cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        )
        let evidence = try resolver.resolve()
        if let data = evidence.diagnosticText.data(using: .utf8) {
            try data.write(to: realShotsDir().appendingPathComponent("edit-review-evidence-round.txt"))
        }
        return evidence
    }

    private func dragDestination(from point: RealEvidencePoint) -> RealEvidencePoint {
        RealEvidencePoint(
            x: min(max(point.x + (point.x > 0.72 ? -0.08 : 0.08), 0.06), 0.94),
            y: min(max(point.y + (point.y > 0.72 ? -0.08 : 0.08), 0.06), 0.94)
        )
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
