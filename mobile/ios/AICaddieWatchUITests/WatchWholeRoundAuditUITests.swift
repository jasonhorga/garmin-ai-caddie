import XCTest

/// Issue #417. Opt-in only: ordinary Native CI does not repeat this three-face visual audit.
/// `ui-action` screenshots follow actual taps/swipes/drags. `injected-state` screenshots explicitly
/// identify fixture/hardware boundaries rather than pretending to prove GPS or physical Crown input.
final class WatchWholeRoundAuditUITests: XCTestCase {
    private let app = XCUIApplication()
    private var lastFlow = "unknown"
    private var lastStep = "unknown"
    private var output: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("watch-audit", isDirectory: true)
    }

    override func setUpWithError() throws {
        guard ProcessInfo.processInfo.environment["UITEST_WATCH_FULL_AUDIT"] == "1" else {
            throw XCTSkip("Whole-round visual audit runs only in the dedicated three-face dispatch")
        }
        continueAfterFailure = false
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        if let run = testRun, run.failureCount > 0 {
            try capture(lastFlow, "\(lastStep)-FAILURE", input: "failure-evidence")
            print("Watch audit failure hierarchy:\n\(app.debugDescription)")
        }
        app.terminate()
    }

    private func launch(_ screen: String, range: String = "fresh", page: Int = 0,
                        zoom: Int = 1, aod: Bool = false, moveAfterShot: Bool = false,
                        supportsAutoShot: Bool = false) throws {
        app.terminate()
        app.launchArguments = ["-uitest-screen", screen]
        app.launchEnvironment = [
            "UITEST_GPS_LAT": "40.0454995", "UITEST_GPS_LON": "116.5461531",
            "UITEST_AUDIT_RANGE": range, "UITEST_AUDIT_PAGE": String(page),
            "UITEST_AUDIT_ZOOM": String(zoom), "UITEST_AUDIT_AOD": aod ? "1" : "0",
            "UITEST_AUDIT_MOVE_AFTER_SHOT": moveAfterShot ? "1" : "0",
            "UITEST_AUDIT_AUTOSHOT_SUPPORTED": supportsAutoShot ? "1" : "0",
            "UITEST_AUDIT_ANCHORS": "1",
        ]
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 20))
        if screen.hasPrefix("audit-") {
            XCTAssertTrue(element("watch-audit-state").waitForExistence(timeout: 20))
            trace("ready=true;")
        }
    }

    private func element(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: identifier).firstMatch
    }

    private func tap(_ target: XCUIElement, scroll: Bool = true) throws {
        guard target.waitForExistence(timeout: 10) else {
            try capture(lastFlow, "\(lastStep)-missing-control", input: "failure-evidence")
            XCTFail("Missing control: \(target)")
            return
        }
        if scroll {
            for _ in 0..<10 where !target.isHittable { app.swipeUp() }
            for _ in 0..<10 where !target.isHittable { app.swipeDown() }
        }
        XCTAssertTrue(target.isHittable, "Control must be reachable: \(target.label)")
        target.tap()
    }

    private func trace(_ fragment: String, timeout: TimeInterval = 10) {
        let expected = NSPredicate(format: "label CONTAINS %@", fragment)
        let result = XCTWaiter().wait(for: [XCTNSPredicateExpectation(
            predicate: expected, object: element("watch-audit-state")
        )], timeout: timeout)
        XCTAssertEqual(result, .completed, "Expected model state \(fragment)")
    }

    @discardableResult
    private func capture(_ flow: String, _ step: String, input: String = "ui-action") throws -> URL {
        lastFlow = flow
        lastStep = step
        let stem = "\(flow)--\(step)"
        let screenshot = XCUIScreen.main.screenshot()
        let file = output.appendingPathComponent(stem + ".png")
        try screenshot.pngRepresentation.write(to: file, options: .atomic)
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = stem
        attachment.lifetime = .keepAlways
        add(attachment)
        let controls: [[String: Any]] = app.buttons.allElementsBoundByIndex.map {
            ["label": $0.label, "identifier": $0.identifier, "hittable": $0.isHittable,
             "frame": [Double($0.frame.minX), Double($0.frame.minY),
                       Double($0.frame.width), Double($0.frame.height)]]
        }
        let root = element("watch-audit-state")
        let metadata: [String: Any] = ["flow": flow, "step": step, "inputMode": input,
                                       "trace": root.exists ? root.label : "not-instrumented",
                                       "controls": controls]
        try JSONSerialization.data(withJSONObject: metadata, options: .sortedKeys)
            .write(to: output.appendingPathComponent(stem + ".json"), options: .atomic)
        return file
    }

    private func openMenu() throws { try tap(element("watch-hole-menu"), scroll: false) }

    private func selectHole(_ hole: Int) throws {
        try openMenu()
        try tap(app.buttons["选洞"])
        try tap(app.buttons[String(hole)])
        trace("hole=\(hole);")
    }

    private func scoreViaCard(_ hole: Int, flow: String) throws {
        try openMenu()
        try tap(app.buttons["计分卡"])
        try capture(flow, String(format: "%02d-scorecard", hole))
        try tap(app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", String(hole))).firstMatch)
        try capture(flow, String(format: "%02d-score", hole))
        try tap(element("watch-score-save"), scroll: false)
        try tap(app.buttons["返回"])
        try tap(app.buttons["返回球洞"])
        trace("scored=\(hole);")
        trace("strokes=\(hole * 5);")
        try capture(flow, String(format: "%02d-root", hole))
    }

    private func finish(_ flow: String) throws {
        try openMenu()
        try tap(app.buttons["结束本场"])
        try capture(flow, "91-summary")
        try tap(app.buttons["保存并结束"])
        try capture(flow, "92-confirmation")
        try tap(app.buttons["确认"])
        trace("round=false;")
        try capture(flow, "93-saved-offline-home")
    }

    func test01LaunchAndColdStates() throws {
        try launch("audit-empty")
        try capture("launch", "01-empty-offline", input: "injected-state")
        app.terminate()
        app.launchArguments = []
        app.launchEnvironment = ["UITEST_LOCATION_AUTHORIZATION": "denied"]
        app.launch()
        try capture("launch", "02-permission-denied", input: "injected-state")
        for (index, range) in ["none", "stale", "fresh"].enumerated() {
            try launch("audit-phone-18", range: range)
            trace("map=true;")
            try capture("launch", "0\(index + 3)-map-\(range)", input: "injected-state")
        }
        try launch("audit-map-pending", range: "none")
        XCTAssertTrue(element("watch-map-preparing-root").waitForExistence(timeout: 10))
        try capture("launch", "06-map-pending", input: "injected-state")
    }

    func test02HolePagesPlansHazardsAndMeasurement() throws {
        try launch("audit-phone-18")
        trace("map=true;")
        try capture("pages", "01-plan")
        let chip = app.buttons["watch-plan-club-tag"]
        XCTAssertTrue(chip.waitForExistence(timeout: 10))
        let oldPlan = String(describing: chip.value ?? "")
        try tap(chip, scroll: false)
        let changed = NSPredicate(format: "value != %@", oldPlan)
        XCTAssertEqual(XCTWaiter().wait(for: [XCTNSPredicateExpectation(predicate: changed, object: chip)], timeout: 6), .completed)
        try capture("pages", "02-switched-plan")
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.65, dy: 0.45)).tap()
        try capture("pages", "03-tap-measure")
        let ring = element("watch-audit-target-anchor")
        XCTAssertTrue(ring.waitForExistence(timeout: 5))
        ring.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        XCTAssertEqual(XCTWaiter().wait(for: [XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"), object: ring
        )], timeout: 5), .completed, "tapping the actual measure ring clears it")
        try capture("pages", "04-cleared-measure")
        let pager = app.collectionViews["PUICPageViewController_collectionView"]
        pager.swipeUp()
        XCTAssertTrue(element("watch-hazard-next").waitForExistence(timeout: 8))
        try capture("pages", "05-hazard-first")
        try tap(element("watch-hazard-next"), scroll: false)
        try capture("pages", "06-hazard-next")
        pager.swipeUp()
        try capture("pages", "07-green")
        let flagAnchor = element("watch-audit-flag-anchor")
        XCTAssertTrue(flagAnchor.waitForExistence(timeout: 8))
        let originalFlag = flagAnchor.frame
        flagAnchor.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            .press(forDuration: 0.5, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.86, dy: 0.43)))
        XCTAssertNotEqual(flagAnchor.frame, originalFlag, "dragging the actual flag base moves the flag")
        try capture("pages", "08-flag-boundary")
        flagAnchor.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            .press(forDuration: 0.5, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.92, dy: 0.23)))
        try capture("pages", "08b-flag-edge-slide")
        pager.swipeDown()
        try capture("pages", "09-back-to-hazard")
    }

    func test03ZoomPanLongPressAndAOD() throws {
        for page in 0...2 {
            for zoom in 1...4 {
                try launch("audit-phone-18", page: page, zoom: zoom)
                trace("map=true;")
                let step = "p\(page)-z\(zoom)"
                try capture("zoom", step + "-before", input: "injected-state")
                if zoom > 1 {
                    app.coordinate(withNormalizedOffset: CGVector(dx: 0.84, dy: 0.65))
                        .press(forDuration: 0.1, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.66, dy: 0.37)))
                    try capture("zoom", step + "-panned")
                    app.coordinate(withNormalizedOffset: CGVector(dx: 0.67, dy: 0.37)).press(forDuration: 0.6)
                    try capture("zoom", step + "-long-press")
                    if page == 1 {
                        try tap(element("watch-hazard-next"), scroll: false)
                        try capture("zoom", step + "-switched-hazard")
                    }
                }
            }
            try launch("audit-phone-18", page: page, aod: true)
            try capture("always-on", "page-\(page)", input: "injected-state")
        }
        try launch("standalone-course-seed")
        try launch("standalone-course-touch-target")
        try capture("touch-target", "01-before", input: "injected-state")
        let target = element("watch-audit-target-anchor")
        XCTAssertTrue(target.waitForExistence(timeout: 10))
        let before = target.frame
        target.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            .press(forDuration: 0.2, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.72, dy: 0.36)))
        XCTAssertNotEqual(target.frame, before, "the actual Touch Target follows the drag")
        try capture("touch-target", "02-dragged")
    }

    func test04ShotsUndoCommitAutoAndNextTee() throws {
        try launch("audit-phone-18", moveAfterShot: true)
        try tap(element("watch-hole-record-shot"), scroll: false)
        XCTAssertTrue(element("watch-shot-undo").waitForExistence(timeout: 5))
        try capture("shots", "01-manual-undo-window")
        try tap(element("watch-shot-undo"), scroll: false)
        trace("shots=0;")
        trace("pending=false;")
        try capture("shots", "02-undone")
        try tap(element("watch-hole-record-shot"), scroll: false)
        try capture("shots", "03-pending-commit")
        trace("shots=1;", timeout: 30)
        // The next synthetic fix advances the fixture Driver's 201.2 m / 220 yd carry.
        sleep(4)
        try capture("shots", "04-committed")
        try openMenu()
        try tap(app.buttons["更多工具"])
        try tap(app.buttons["设置"])
        try capture("shots", "05-auto-shot-settings")
        try launch("audit-phone-18", supportsAutoShot: true)
        try openMenu()
        try tap(app.buttons["更多工具"])
        try tap(app.buttons["设置"])
        try capture("shots", "05b-supported-settings", input: "injected-state")
        let autoShot = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "自动记杆")).firstMatch
        try tap(autoShot)
        trace("auto=true;")
        try capture("shots", "05c-auto-enabled")
        try tap(autoShot)
        trace("auto=false;")
        try capture("shots", "05d-auto-disabled")
        try launch("audit-auto-candidate")
        try capture("shots", "06-injected-auto-candidate", input: "injected-state")
        try launch("audit-next-tee")
        trace("screen=scoring;")
        try capture("shots", "07-next-tee-score-popup", input: "injected-state")
        try tap(element("watch-score-save"), scroll: false)
        trace("hole=2;")
        try capture("shots", "08-next-tee-accepted")
    }

    func test05ScorePickersAndAbandon() throws {
        try launch("audit-phone-18")
        try launch("audit-score-current")
        try capture("scoring", "01-auto-popup", input: "injected-state")
        element("watch-score-band").swipeLeft()
        try capture("scoring", "02-total-drag")
        try tap(element("watch-score-putts"), scroll: false)
        try capture("scoring", "03-putts-open")
        element("watch-score-wheel-putts").swipeUp()
        try capture("scoring", "04-putts-adjusted")
        try tap(element("watch-score-penalty"), scroll: false)
        try capture("scoring", "05-penalty-open")
        element("watch-score-wheel-penalty").swipeUp()
        try capture("scoring", "06-penalty-adjusted")
        try tap(element("watch-score-save"), scroll: false)
        try capture("scoring", "07-saved")
        try openMenu()
        try tap(app.buttons["结束本场"])
        try capture("abandon", "01-summary")
        try tap(app.buttons["放弃本场"])
        try capture("abandon", "02-confirm")
        try tap(app.buttons["返回"])
        try capture("abandon", "03-cancelled")
        try tap(app.buttons["放弃本场"])
        try tap(app.buttons["放弃"])
        trace("round=false;")
        try capture("abandon", "04-abandoned-home")
    }

    func test06CompletePhoneNineHoleRound() throws {
        try launch("audit-phone-9")
        for hole in 1...9 {
            if hole > 1 { try selectHole(hole) }
            try scoreViaCard(hole, flow: "phone-nine")
        }
        try finish("phone-nine")
    }

    func test07CompletePhoneEighteenHoleRoundAndRelaunch() throws {
        try launch("audit-phone-18")
        for hole in 1...18 {
            if hole > 1 { try selectHole(hole) }
            try scoreViaCard(hole, flow: "phone-eighteen")
            if hole == 9 {
                try launch("audit-restore")
                try capture("phone-eighteen", "09-offline-resume")
                try tap(app.buttons["继续打球"])
                trace("scored=9;")
                trace("strokes=45;")
                try capture("phone-eighteen", "09-restored-root")
            }
        }
        try finish("phone-eighteen")
    }

    func test08WatchStartAndNineToEighteenTurn() throws {
        try launch("audit-start")
        try capture("watch-start", "01-venue-and-nines")
        try tap(app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "模拟审查球场")).firstMatch)
        try capture("watch-start", "02-half-selection")
        try tap(element("watch-setup-half-front"))
        try capture("watch-start", "03-tees")
        try tap(element("watch-setup-start"))
        trace("round=true;")
        trace("map=true;")
        try capture("watch-start", "04-hole-root")
        for hole in 1...8 {
            if hole > 1 { try selectHole(hole) }
            try scoreViaCard(hole, flow: "watch-turn")
        }
        try selectHole(9)
        try launch("audit-score-current")
        try capture("watch-turn", "09-hole-end-popup", input: "injected-state")
        try tap(element("watch-score-save"), scroll: false)
        XCTAssertTrue(element("watch-turn-half-back").waitForExistence(timeout: 10))
        try capture("watch-turn", "10-turn-choices")
        try tap(element("watch-turn-half-front"))
        try capture("watch-turn", "11-same-half-choice")
        try tap(element("watch-turn-half-back"))
        try tap(element("watch-turn-continue"))
        trace("hole=10;")
        try capture("watch-turn", "12-second-nine-root")
        for hole in 10...18 {
            if hole > 10 { try selectHole(hole) }
            try scoreViaCard(hole, flow: "watch-turn-back-nine")
        }
        try finish("watch-turn-back-nine")
    }

    func test09PhoneDeliveryAndFlagDirectionBoundaries() throws {
        try launch("audit-late-map")
        try capture("sync", "01-before-map-delivery", input: "injected-state")
        trace("map=true;", timeout: 15)
        try capture("sync", "02-map-arrived", input: "injected-state")
        try launch("audit-out-of-order")
        trace("hole=2;")
        trace("strokes=6;")
        try capture("sync", "03-late-old-hole-snapshot", input: "injected-state")
        try launch("audit-heading")
        trace("headingWanted=true;")
        try capture("flag-direction", "01-valid-heading", input: "injected-state")
        try tap(app.buttons["返回菜单"])
        trace("headingWanted=false;")
        try capture("flag-direction", "02-left-page")
        try launch("audit-heading", range: "none")
        try capture("flag-direction", "03-unavailable-location", input: "injected-state")
        try launch("audit-heading", range: "far")
        try capture("flag-direction", "04-off-course", input: "injected-state")
    }

    func test10WatchNineLoopOwnStart() throws {
        try launch("audit-start-nine")
        try capture("watch-nine-start", "01-venue-and-nines")
        try tap(app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "模拟审查球场")).firstMatch)
        try capture("watch-nine-start", "02-nine-loop-choices")
        try tap(element("loop:front:32001"))
        try capture("watch-nine-start", "03-tees")
        try tap(element("watch-setup-start"))
        trace("round=true;")
        trace("map=true;")
        try capture("watch-nine-start", "04-hole-root")
    }
}
