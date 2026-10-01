import XCTest

/// Real running-app screenshots of the **复盘编辑** flow (PR2) from the iOS Simulator (XCUITest).
/// Launches the ACTUAL app against the live backend (funnel) with the owner admin token, navigates
/// 成绩 → 全部球局 → a round → a hole's full-screen 落点图, taps 「编辑」, and captures the B3 in-place
/// whole-hole draft flow: numbered handles, tap-to-add, select + drag move, the bottom edit bar (club
/// pills, 击球时球位, ‹ › order, 删除, 推杆 −/+), then Cancel or final Save.
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
        for key in UITestBackendLaunchConfiguration.markerKeys {
            app.launchEnvironment.removeValue(forKey: key)
        }
        app.launchEnvironment.merge(
            UITestBackendLaunchConfiguration.markers(
                fixtureMode: cfg("AI_CADDIE_FIXTURE_MODE"),
                dataMode: cfg("AI_CADDIE_DATA_MODE")
            )
        ) { _, new in new }
        app.launchEnvironment["UITEST_GPS_LAT"] = cfg("UITEST_GPS_LAT") ?? "40.0454995"
        app.launchEnvironment["UITEST_GPS_LON"] = cfg("UITEST_GPS_LON") ?? "116.5461531"
        app.launchEnvironment["UITEST_MODE"] = "1"
    }

    func testCaptureReviewEditFlow() throws {
        let reviewEvidence = try resolveReviewEvidence()
        // ---- Navigate to a round review, then into one hole's 落点图 ----
        launchFresh()
        let historyTile = app.buttons.matching(
            NSPredicate(format: "label CONTAINS %@", "成绩")
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
        guard scrollAndTapContaining(["场 ›", "全部球局 ›"]) else {
            save("noarchive"); dump("noarchive")
            XCTFail("review-edit evidence must expose the complete archive")
            return
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

        // The scorecard cells are buttons (`round-review-hole-N`); tapping one opens the full-screen
        // hole pager. The resolver selected this hole only after proving multiple separated,
        // club-labelled GPS positions; they must remain editable before the add-shot flow counts.
        let holeButton = app.buttons["round-review-hole-\(reviewEvidence.hole)"]
        guard holeButton.waitForExistence(timeout: 60), bringIntoViewAndTap(holeButton, maxSwipes: 4) else {
            save("nohole"); dump("nohole")
            XCTFail("review-edit evidence must open its resolver-verified real hole")
            return
        }
        // B3: the hole is full screen with the navigation bar hidden; the glass close button is the
        // stable proof that the pager was presented.
        let closeButton = app.buttons["round-shot-map-close"]
        guard closeButton.waitForExistence(timeout: 12) else {
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
        XCTAssertTrue(
            element("round-shot-score-box").waitForExistence(timeout: 5),
            "the full-screen hole must show its glass score box"
        )
        settle(2); save("03-shot-map"); dump("03-shot-map")

        let editButton = app.buttons["round-edit-begin"]
        guard editButton.waitForExistence(timeout: 12) else {
            save("noeditbtn"); dump("noeditbtn")
            XCTFail("review-edit evidence must expose the map edit action")
            return
        }

        // ---- Enter edit mode on the same screen → numbered landings become drag handles ----
        guard editButton.isHittable else {
            save("noeditbtn2"); dump("noeditbtn2")
            XCTFail("review-edit evidence must enter map edit mode")
            return
        }
        editButton.tap()
        XCTAssertTrue(
            app.buttons["round-edit-cancel"].waitForExistence(timeout: 5)
                && app.buttons["round-edit-save"].exists,
            "edit mode must expose the explicit zero-write Cancel and final Save actions"
        )
        XCTAssertTrue(
            waitUntilGone(closeButton, timeout: 5),
            "edit mode must expose only the explicit zero-write Cancel and final Save actions"
        )
        // A downward pull must not silently discard the local whole-hole draft. Start in the top
        // score-box lane rather than on the editable map, whose empty-ground gesture adds a shot.
        let dismissStart = app.coordinate(withNormalizedOffset: CGVector(dx: 0.50, dy: 0.11))
        let dismissEnd = app.coordinate(withNormalizedOffset: CGVector(dx: 0.50, dy: 0.92))
        dismissStart.press(forDuration: 0.15, thenDragTo: dismissEnd)
        XCTAssertTrue(
            app.buttons["round-edit-cancel"].waitForExistence(timeout: 5)
                && app.buttons["round-edit-save"].exists,
            "a pull-down must not become an implicit third Cancel action while editing"
        )
        // A precise map is edited in place; the fact-only draft list exists only without a map.
        let editMap = element("round-shot-edit-map")
        let editTopoReady = app.descendants(matching: .any)
            .matching(identifier: "topo-hole-base-ready").firstMatch
        guard editTopoReady.waitForExistence(timeout: 75), editMap.waitForExistence(timeout: 12) else {
            XCTFail("edit evidence requires the real topo and the in-place edit map for this hole")
            return
        }
        XCTAssertTrue(
            waitForLabel(editMap, containing: "共 \(reviewEvidence.shotCount) 杆", timeout: 5),
            "the edit map must carry one handle for every real recorded shot returned for this hole"
        )
        XCTAssertFalse(
            element("shot-draft-row-1").exists,
            "a precise map must not fall back to the fact-only draft list"
        )
        XCTAssertTrue(
            element("round-edit-putts-value").waitForExistence(timeout: 5)
                && element("round-edit-penalty-value").exists,
            "with nothing selected the edit bar must offer 推杆 and 罚杆 −/+"
        )
        settle(2); save("04-edit-handles"); dump("04-edit-handles")

        // ---- 连续草稿: tap verified empty topo once to append a numbered point; no sheet/no write ----
        // The resolver computes the point farthest from every real landing in this exact map, so this
        // proves tap-to-add rather than accidentally selecting an existing numbered handle.
        editMap.coordinate(withNormalizedOffset: CGVector(
            dx: reviewEvidence.emptyMapPoint.x,
            dy: reviewEvidence.emptyMapPoint.y
        )).tap()
        let addedNumber = reviewEvidence.shotCount + 1
        XCTAssertTrue(
            waitForLabel(editMap, containing: "共 \(addedNumber) 杆", timeout: 5),
            "one empty-map tap must append a numbered local draft"
        )
        XCTAssertFalse(app.navigationBars["补一杆"].exists, "adding a draft point must not interrupt with the old sheet")
        let selectedShot = element("round-edit-selected")
        XCTAssertTrue(
            selectedShot.waitForExistence(timeout: 5)
                && selectedShot.label.hasPrefix("第 \(addedNumber) 杆"),
            "the added shot must be selected in the bottom bar as the last shot"
        )
        let clubPills = app.buttons.matching(
            NSPredicate(format: "identifier BEGINSWITH %@", "round-edit-club-")
        )
        XCTAssertTrue(
            clubPills.firstMatch.waitForExistence(timeout: 5),
            "the selected added shot must offer club pills (the distance guess first)"
        )
        settle(2); save("05-add-draft"); dump("05-add-draft")

        // ---- 改这一杆: tap a recorded landing handle to select it; the bottom bar edits it ----
        editMap.coordinate(withNormalizedOffset: CGVector(
            dx: reviewEvidence.landing.x,
            dy: reviewEvidence.landing.y
        )).tap()
        XCTAssertTrue(
            waitForLabel(selectedShot, notPrefixed: "第 \(addedNumber) 杆", timeout: 5),
            "a landing tap must select that recorded shot"
        )
        XCTAssertTrue(
            waitForLabel(editMap, containing: "共 \(addedNumber) 杆", timeout: 2),
            "a tap on a handle must select it, never add another shot"
        )
        XCTAssertFalse(app.navigationBars["改这一杆"].exists, "selection must not cover the map with the old sheet")
        let deleteShot = app.buttons["round-edit-delete"]
        XCTAssertTrue(
            deleteShot.waitForExistence(timeout: 5) && deleteShot.isHittable,
            "the destructive action must be visible and tappable in the bottom bar"
        )
        XCTAssertLessThanOrEqual(
            deleteShot.frame.maxY,
            app.windows.firstMatch.frame.maxY - 30,
            "the destructive action must remain above the iPhone Home Indicator safe area"
        )
        let recordedClubPill = app.buttons.matching(
            NSPredicate(format: "identifier BEGINSWITH %@ AND selected == true", "round-edit-club-")
        ).firstMatch
        XCTAssertTrue(
            recordedClubPill.waitForExistence(timeout: 5),
            "the selected recorded shot must highlight its recorded club pill"
        )
        let recordedClub = recordedClubPill.label
        XCTAssertFalse(
            recordedClub.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
            "a Garmin raw club token must resolve to a visible club pill"
        )
        XCTAssertNotEqual(recordedClub, "未知", "verified club-labelled evidence must not render as unknown")
        XCTAssertTrue(
            app.buttons["round-edit-lie-unknown"].exists,
            "the bottom bar must expose the 击球时球位 grid"
        )
        settle(2); save("06-selected-shot"); dump("06-selected-shot")

        // ---- Drag the selected real numbered handle. Finger-up still stays in the local draft. ----
        // Reuse the verified landing coordinate selected above. Move inward so an edge landing still
        // produces a real handle drag rather than an off-map gesture.
        let dragDestination = dragDestination(from: reviewEvidence.landing)
        let dragStart = editMap.coordinate(withNormalizedOffset: CGVector(
            dx: reviewEvidence.landing.x,
            dy: reviewEvidence.landing.y
        ))
        let dragEnd = editMap.coordinate(withNormalizedOffset: CGVector(
            dx: dragDestination.x,
            dy: dragDestination.y
        ))
        // Hold the real gesture at its destination long enough for the workflow's simulator video
        // to retain a clean frame of the product loupe before release. The still captured below is
        // intentionally the committed post-drag state.
        dragStart.press(
            forDuration: 0.7,
            thenDragTo: dragEnd,
            withVelocity: .slow,
            thenHoldForDuration: 2
        )
        XCTAssertTrue(
            waitForLabel(editMap, containing: "共 \(addedNumber) 杆", timeout: 3),
            "dragging a handle must move it, never add a shot"
        )
        XCTAssertTrue(selectedShot.exists, "the dragged shot must stay selected")
        settle(2); save("07-drag-move"); dump("07-drag-move")

        // ---- Reorder with the bottom bar's ‹ › arrows: one place later, then back. ----
        let orderLater = app.buttons["round-edit-order-later"]
        let orderEarlier = app.buttons["round-edit-order-earlier"]
        XCTAssertTrue(
            orderLater.waitForExistence(timeout: 5) && orderEarlier.exists,
            "the selected shot must expose its ‹ › order arrows"
        )
        let numberBeforeReorder = shotNumber(selectedShot.label)
        // The added shot is last, so the recorded landing can always move one place later.
        XCTAssertTrue(orderLater.isEnabled, "a recorded shot before the added one must be movable later")
        orderLater.tap()
        XCTAssertTrue(
            waitForLabel(selectedShot, notPrefixed: numberBeforeReorder, timeout: 5),
            "› must move the selected shot one place later and keep it selected"
        )
        let numberAfterReorder = shotNumber(selectedShot.label)
        XCTAssertTrue(waitForLabel(editMap, containing: "共 \(addedNumber) 杆", timeout: 2), "reordering must retain every draft point")
        settle(1); save("08-reorder-draft"); dump("08-reorder-draft")
        XCTAssertTrue(orderEarlier.isEnabled)
        orderEarlier.tap()
        XCTAssertTrue(
            waitForLabel(selectedShot, notPrefixed: numberAfterReorder, timeout: 5)
                && shotNumber(selectedShot.label) == numberBeforeReorder,
            "‹ must move the same shot back to its original place"
        )

        // ---- Delete the added point. The other draft points stay available until final action. ----
        editMap.coordinate(withNormalizedOffset: CGVector(
            dx: reviewEvidence.emptyMapPoint.x,
            dy: reviewEvidence.emptyMapPoint.y
        )).tap()
        XCTAssertTrue(
            waitForLabel(selectedShot, prefixed: "第 \(addedNumber) 杆", timeout: 5),
            "a tap on the added handle must select it instead of adding another shot"
        )
        XCTAssertTrue(deleteShot.waitForExistence(timeout: 5) && deleteShot.isHittable)
        deleteShot.tap()
        XCTAssertTrue(
            waitForLabel(editMap, containing: "共 \(reviewEvidence.shotCount) 杆", timeout: 5),
            "delete must renumber the same local draft"
        )
        XCTAssertTrue(waitUntilGone(selectedShot, timeout: 5), "deleting the selected shot must clear the selection")
        settle(2); save("09-delete-draft"); dump("09-delete-draft")

        // ---- 推杆 −/+ with nothing selected: change once and restore (a local draft only). ----
        let puttsValue = element("round-edit-putts-value")
        XCTAssertTrue(puttsValue.waitForExistence(timeout: 5), "with nothing selected the bar must return to 推杆 / 罚杆")
        let puttsBefore = puttsValue.label
        // An unrecorded count ("–") cannot be restored by −/+; never fabricate a putt count here.
        if !puttsBefore.hasSuffix("–") {
            // Step up first unless the count is already at the bar's maximum (9).
            let increaseFirst = !puttsBefore.hasSuffix(" 9")
            let first = app.buttons[increaseFirst ? "round-edit-putts-plus" : "round-edit-putts-minus"]
            let second = app.buttons[increaseFirst ? "round-edit-putts-minus" : "round-edit-putts-plus"]
            XCTAssertTrue(first.waitForExistence(timeout: 5) && first.isEnabled)
            first.tap()
            XCTAssertTrue(
                waitForLabel(puttsValue, notEqual: puttsBefore, timeout: 5),
                "推杆 −/+ must change the draft putt count"
            )
            settle(1); save("09b-putts-draft"); dump("09b-putts-draft")
            second.tap()
            XCTAssertTrue(
                waitForLabel(puttsValue, equal: puttsBefore, timeout: 5),
                "the opposite step must restore the recorded putt count"
            )
        }

        // Routine evidence must leave the owner's history untouched. A dedicated writable fixture
        // takes the identical path through the one final Save action.
        let finalAction = app.descendants(matching: .any).matching(
            identifier: allowWrites ? "round-edit-save" : "round-edit-cancel"
        ).firstMatch
        XCTAssertTrue(finalAction.waitForExistence(timeout: 5) && finalAction.isHittable)
        finalAction.tap()
        XCTAssertTrue(
            app.buttons["round-edit-begin"].waitForExistence(timeout: 12),
            "10 may be captured only after Save/Cancel returns to read-only mode"
        )
        XCTAssertTrue(
            app.buttons["round-shot-map-close"].waitForExistence(timeout: 5),
            "leaving edit mode must restore the close button"
        )
        XCTAssertFalse(app.navigationBars["补一杆"].exists, "10 must never retain the removed add sheet")
        XCTAssertFalse(app.navigationBars["改这一杆"].exists, "10 must never retain the removed detail sheet")
        // Switching from the edit map back to the read-only RoundShotMapView creates a new topo image
        // view. The 编辑 button returns before that image has finished loading, so waiting a fixed
        // two seconds can capture the transient loading overlay as if it were I31. A fast cache hit
        // may make the loading element too brief to observe; either way, the final gate is a
        // newly-ready real topo with no loading element left in the hierarchy.
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

    // MARK: - element helpers

    private func element(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: identifier).firstMatch
    }

    /// "第 3 杆 · 150 码" → "第 3 杆".
    private func shotNumber(_ label: String) -> String {
        label.components(separatedBy: " · ").first ?? label
    }

    private func waitForLabel(_ element: XCUIElement, matching predicate: NSPredicate, timeout: TimeInterval) -> Bool {
        let expectation = XCTNSPredicateExpectation(predicate: predicate, object: element)
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    private func waitForLabel(_ element: XCUIElement, containing text: String, timeout: TimeInterval) -> Bool {
        waitForLabel(element, matching: NSPredicate(format: "label CONTAINS %@", text), timeout: timeout)
    }

    private func waitForLabel(_ element: XCUIElement, prefixed text: String, timeout: TimeInterval) -> Bool {
        waitForLabel(element, matching: NSPredicate(format: "label BEGINSWITH %@", text), timeout: timeout)
    }

    private func waitForLabel(_ element: XCUIElement, notPrefixed text: String, timeout: TimeInterval) -> Bool {
        waitForLabel(
            element,
            matching: NSPredicate(format: "exists == true AND NOT (label BEGINSWITH %@)", text),
            timeout: timeout
        )
    }

    private func waitForLabel(_ element: XCUIElement, equal text: String, timeout: TimeInterval) -> Bool {
        waitForLabel(element, matching: NSPredicate(format: "label == %@", text), timeout: timeout)
    }

    private func waitForLabel(_ element: XCUIElement, notEqual text: String, timeout: TimeInterval) -> Bool {
        waitForLabel(element, matching: NSPredicate(format: "exists == true AND label != %@", text), timeout: timeout)
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
        let evidence: RealEvidenceRound
        do {
            evidence = try resolver.resolve(preferredRoundRef: cfg("UITEST_REVIEW_ROUND_REF"))
        } catch {
            if let data = resolver.diagnosticsText.data(using: .utf8) {
                try? data.write(to: realShotsDir().appendingPathComponent("edit-review-evidence-rejections.txt"))
            }
            throw error
        }
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
    private func scrollAndTapContaining(_ fragments: [String], maxSwipes: Int = 5) -> Bool {
        for attempt in 0...maxSwipes {
            if tapContaining(fragments) { return true }
            guard attempt < maxSwipes else { break }
            app.swipeUp()
            settle(1)
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
