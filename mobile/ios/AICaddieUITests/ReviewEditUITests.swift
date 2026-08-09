import XCTest

/// Real running-app screenshots of the **复盘编辑** flow (PR2) from the iOS Simulator (XCUITest).
/// Launches the ACTUAL app against the live backend (funnel) with the owner admin token, navigates
/// 历史复盘 → a round → a hole's 落点图, taps 「编辑」, and captures the whole-hole draft flow:
/// numbered landings, tap-to-add, long-press move, details, count-list delete/reorder, then Cancel or final Save.
///
/// Runs on-demand only (`native-mobile.yml` gates the AICaddieUITests scheme behind workflow_dispatch),
/// same as ``RealFlowUITests``. PNGs + per-screen element-tree dumps land in the test process Documents
/// dir; the workflow collects `*Documents/real-screenshots/*`.
///
/// **Safe by default:** every draft gesture is local and the journey ends with Cancel. A dedicated
/// writable fixture may set `UITEST_ALLOW_EDIT_WRITES=1` to exercise the single final snapshot POST.
final class ReviewEditUITests: XCTestCase {
    private let app = XCUIApplication()

    private func cfg(_ key: String) -> String? {
        let env = ProcessInfo.processInfo.environment
        return env[key] ?? env["TEST_RUNNER_\(key)"]
    }

    private var allowWrites: Bool { (cfg("UITEST_ALLOW_EDIT_WRITES") ?? "0") == "1" }

    override func setUpWithError() throws {
        // Every later coordinate depends on the prior real screen. Stop at the first missing product
        // prerequisite instead of letting taps on a different screen create misleading evidence.
        continueAfterFailure = false
        app.launchEnvironment["AI_CADDIE_API_BASE_URL"] = cfg("AI_CADDIE_API_BASE_URL") ?? ""
        app.launchEnvironment["AI_CADDIE_ADMIN_TOKEN"] = cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        app.launchEnvironment["UITEST_GPS_LAT"] = cfg("UITEST_GPS_LAT") ?? "40.0454995"
        app.launchEnvironment["UITEST_GPS_LON"] = cfg("UITEST_GPS_LON") ?? "116.5461531"
        app.launchEnvironment["UITEST_MODE"] = "1"
    }

    func testCaptureReviewEditFlow() throws {
        let reviewEvidence = try resolveReviewEvidence()
        // ---- Navigate to a round review, then into one hole's 落点图 ----
        launchFresh()
        let historyTile = app.buttons.matching(
            NSPredicate(format: "label CONTAINS %@", "历史复盘")
        ).firstMatch
        guard historyTile.waitForExistence(timeout: 60) else {
            XCTFail("edit-00-home may be captured only after the real home replaces the launch screen")
            return
        }
        settle(2)
        save("00-home"); dump("00-home")

        guard historyTile.isHittable else {
            save("nohistory"); dump("nohistory")
            XCTFail("review-edit evidence must expose the history entry")
            return
        }
        historyTile.tap()
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
            save("nohole"); dump("nohole")
            XCTFail("review-edit evidence must open its resolver-verified real hole")
            return
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
            save("noeditbtn"); dump("noeditbtn")
            XCTFail("review-edit evidence must expose the map edit action")
            return
        }

        // ---- Enter edit mode → drag handles appear on every landing ----
        guard tapButton("编辑") else {
            save("noeditbtn2"); dump("noeditbtn2")
            XCTFail("review-edit evidence must enter map edit mode")
            return
        }
        XCTAssertTrue(
            waitUntilGone(app.buttons["关闭"], timeout: 5),
            "edit mode must expose only the explicit zero-write Cancel and final Save actions"
        )
        let editTopoReady = app.descendants(matching: .any)
            .matching(identifier: "topo-hole-base-ready").firstMatch
        let lastBaselineRow = app.descendants(matching: .any)
            .matching(identifier: "shot-draft-row-\(reviewEvidence.shotCount)").firstMatch
        guard editTopoReady.waitForExistence(timeout: 75), lastBaselineRow.waitForExistence(timeout: 12) else {
            XCTFail("edit evidence requires the real topo and the two real recorded shots returned for this hole")
            return
        }
        settle(2); save("04-edit-handles"); dump("04-edit-handles")

        // ---- 连续草稿: tap verified empty topo once to append a numbered point; no sheet/no write ----
        // The resolver computes the point farthest from every real landing in this exact map, so this
        // proves tap-to-add rather than accidentally selecting an existing numbered handle.
        editTopoReady.coordinate(withNormalizedOffset: CGVector(
            dx: reviewEvidence.emptyMapPoint.x,
            dy: reviewEvidence.emptyMapPoint.y
        )).tap()
        let addedCount = app.staticTexts.matching(
            NSPredicate(format: "label BEGINSWITH %@", "共 \(reviewEvidence.shotCount + 1) 杆")
        ).firstMatch
        XCTAssertTrue(addedCount.waitForExistence(timeout: 5), "one empty-map tap must append a numbered local draft")
        XCTAssertFalse(app.navigationBars["补一杆"].exists, "adding a draft point must not interrupt with the old sheet")
        settle(2); save("05-add-draft"); dump("05-add-draft")

        // ---- 改这一杆: tap selects the landing first; the explicit details button opens the sheet ----
        // A landing tap must remain available for a drag and therefore must not unexpectedly replace
        // the map with a sheet. Use the real topo coordinate, prove selection via the newly exposed
        // 第 N 杆详情 action, then open the editor deliberately.
        editTopoReady.coordinate(withNormalizedOffset: CGVector(
            dx: reviewEvidence.landing.x,
            dy: reviewEvidence.landing.y
        )).tap()
        let editSheet = app.navigationBars["改这一杆"]
        XCTAssertFalse(
            editSheet.waitForExistence(timeout: 1),
            "a landing tap must select for drag instead of immediately covering the map"
        )
        let detailsButton = app.buttons.matching(
            NSPredicate(format: "label BEGINSWITH '第 ' AND label CONTAINS '杆详情'")
        ).firstMatch
        XCTAssertTrue(
            detailsButton.waitForExistence(timeout: 5) && detailsButton.isHittable,
            "the selected landing must expose its explicit details action"
        )
        XCTAssertTrue(editTopoReady.exists, "the selected landing must remain on the editable map")
        detailsButton.tap()
        XCTAssertTrue(editSheet.waitForExistence(timeout: 5), "06 must edit the deliberately selected recorded landing")
        let deleteShot = app.buttons["删除这一杆"]
        XCTAssertTrue(
            deleteShot.waitForExistence(timeout: 5) && deleteShot.isHittable,
            "the destructive action must be visible and tappable without scrolling into the Home Indicator"
        )
        XCTAssertLessThanOrEqual(
            deleteShot.frame.maxY,
            app.windows.firstMatch.frame.maxY - 30,
            "the destructive action must remain above the iPhone Home Indicator safe area"
        )
        let clubPicker = app.descendants(matching: .any)
            .matching(identifier: "shot-edit-club-picker").firstMatch
        XCTAssertTrue(
            clubPicker.waitForExistence(timeout: 5),
            "the edit sheet must expose the recorded club picker"
        )
        let recordedClub = (clubPicker.value as? String) ?? ""
        XCTAssertFalse(
            recordedClub.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
            "a Garmin raw club token must resolve to a visible picker value"
        )
        XCTAssertNotEqual(recordedClub, "未知", "verified club-labelled evidence must not render as unknown")
        settle(2); save("06-edit-sheet"); dump("06-edit-sheet")
        let finishEditSheet = editSheet.buttons["完成"]
        XCTAssertTrue(finishEditSheet.exists && finishEditSheet.isHittable, "the edit sheet must expose its own completion action")
        finishEditSheet.tap()
        XCTAssertTrue(waitUntilGone(editSheet, timeout: 5), "sheet completion must return to the editable map")
        settle(1)

        // ---- Long-press drag a real numbered handle. Finger-up still stays in the local draft. ----
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

        // ---- Delete from the count list. The other draft points stay available until final action. ----
        let addedDraftRow = app.descendants(matching: .any)
            .matching(identifier: "shot-draft-row-\(reviewEvidence.shotCount + 1)").firstMatch
        XCTAssertTrue(addedDraftRow.waitForExistence(timeout: 5), "the added point must exist in the count list")
        let editScroll = app.scrollViews["round-shot-edit-scroll"]
        XCTAssertTrue(editScroll.waitForExistence(timeout: 5), "edit mode must expose its vertical review scroll")
        for _ in 0..<4 where !addedDraftRow.isHittable {
            // Start below the topo on the penalty/instruction lane. A generic app-level swipe begins
            // in the centre of the editable map and correctly belongs to its landing gesture layer,
            // so it cannot prove that the count list itself is reachable.
            let start = editScroll.coordinate(withNormalizedOffset: CGVector(dx: 0.28, dy: 0.90))
            let end = editScroll.coordinate(withNormalizedOffset: CGVector(dx: 0.28, dy: 0.34))
            start.press(forDuration: 0.05, thenDragTo: end)
            settle(0.5)
        }
        XCTAssertTrue(addedDraftRow.isHittable, "the count-list row must be reachable in the review scroll")
        let baselineCount = app.staticTexts.matching(
            NSPredicate(format: "label BEGINSWITH %@", "共 \(reviewEvidence.shotCount) 杆")
        ).firstMatch
        // SwiftUI suppresses row swipe actions while `EditMode.active` is exposing its reorder
        // handles. The shipping count list therefore gives every row a simultaneous, visible trash
        // action instead of advertising an unreachable swipe gesture.
        let deleteAdded = app.buttons["shot-draft-delete-\(reviewEvidence.shotCount + 1)"]
        XCTAssertTrue(
            deleteAdded.waitForExistence(timeout: 5) && deleteAdded.isHittable,
            "the reorderable row must expose its visible destructive action"
        )
        deleteAdded.tap()
        XCTAssertTrue(baselineCount.waitForExistence(timeout: 5), "delete must renumber the same local list")
        settle(2); save("08-delete-draft"); dump("08-delete-draft")

        // ---- Reorder the same count list through SwiftUI's real trailing drag controls. ----
        // Model tests already prove the resulting payload order; this gesture gate proves the
        // shipping nested List actually lets a finger move a row instead of merely drawing handles.
        let upperIndex = max(1, reviewEvidence.shotCount - 1)
        let upperDraftRow = app.descendants(matching: .any)
            .matching(identifier: "shot-draft-row-\(upperIndex)").firstMatch
        let lastDraftRow = app.descendants(matching: .any)
            .matching(identifier: "shot-draft-row-\(reviewEvidence.shotCount)").firstMatch
        let upperReorder = app.buttons["Reorder \(upperIndex)"]
        let lastReorder = app.buttons["Reorder \(reviewEvidence.shotCount)"]
        XCTAssertTrue(upperDraftRow.waitForExistence(timeout: 5) && lastDraftRow.waitForExistence(timeout: 5))
        XCTAssertTrue(upperReorder.waitForExistence(timeout: 5) && lastReorder.waitForExistence(timeout: 5))
        XCTAssertTrue(upperReorder.isHittable && lastReorder.isHittable)
        let upperLabelBeforeReorder = upperDraftRow.label
        let lastLabelBeforeReorder = lastDraftRow.label
        lastReorder.press(forDuration: 0.7, thenDragTo: upperReorder)
        settle(2)
        XCTAssertNotEqual(
            upperDraftRow.label,
            upperLabelBeforeReorder,
            "dragging the last reorder control upward must change the preceding visible shot"
        )
        XCTAssertNotEqual(
            lastDraftRow.label,
            lastLabelBeforeReorder,
            "the list must renumber the displaced row after a real reorder gesture"
        )
        XCTAssertTrue(baselineCount.exists, "reordering must retain every draft point")
        save("09-reorder-draft"); dump("09-reorder-draft")

        // Routine evidence must leave the owner's history untouched. A dedicated writable fixture
        // takes the identical path through the one final Save action.
        let finalAction = app.descendants(matching: .any).matching(
            identifier: allowWrites ? "round-edit-save" : "round-edit-cancel"
        ).firstMatch
        XCTAssertTrue(finalAction.waitForExistence(timeout: 5) && finalAction.isHittable)
        finalAction.tap()
        XCTAssertTrue(
            app.buttons["编辑"].waitForExistence(timeout: 12),
            "10 may be captured only after Save/Cancel returns to read-only mode"
        )
        XCTAssertFalse(app.navigationBars["补一杆"].exists, "10 must never retain the removed add sheet")
        XCTAssertFalse(app.navigationBars["改这一杆"].exists, "10 must never retain the detail sheet")
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
            "10 may be captured only after the read-only topo loading overlay disappears"
        )
        let readOnlyTopoReady = app.descendants(matching: .any)
            .matching(identifier: "topo-hole-base-ready").firstMatch
        XCTAssertTrue(
            readOnlyTopoReady.waitForExistence(timeout: 75),
            "10 requires the real read-only topo after leaving edit mode"
        )
        XCTAssertFalse(readOnlyTopoLoading.exists, "10 must not contain 球场地图加载中…")
        settle(2); save("10-edit-done"); dump("10-edit-done")
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
