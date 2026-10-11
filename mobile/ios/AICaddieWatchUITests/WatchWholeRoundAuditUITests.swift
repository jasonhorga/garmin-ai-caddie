import XCTest

/// Issue #417. Opt-in only: ordinary Native CI does not repeat this three-face visual audit.
/// `ui-action` screenshots follow actual taps/swipes/drags. `injected-state` screenshots explicitly
/// identify fixture/hardware boundaries rather than pretending to prove GPS or physical Crown input.
final class WatchWholeRoundAuditUITests: XCTestCase {
    private let app = XCUIApplication()
    private var lastFlow = "unknown"
    private var lastStep = "unknown"
    private var auditSequence = 0
    private var output: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("watch-audit", isDirectory: true)
    }

    override func setUpWithError() throws {
        guard ProcessInfo.processInfo.environment["UITEST_WATCH_FULL_AUDIT"] == "1" else {
            throw XCTSkip("Whole-round visual audit runs only in the dedicated three-face dispatch")
        }
        continueAfterFailure = false
        lastFlow = name.replacingOccurrences(of: " ", with: "_").replacingOccurrences(of: "/", with: "_")
        lastStep = "initial-state"
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

    private func stateLabel() -> String {
        element("watch-audit-state").label
    }

    private func stateValue(_ key: String, in state: String? = nil) -> Int? {
        let source = state ?? stateLabel()
        guard let match = source.range(of: "\(key)=") else { return nil }
        let tail = source[match.upperBound...]
        let digits = tail.prefix { $0 == "-" || $0.isNumber }
        return Int(digits)
    }

    private func writeAuditJSON(_ value: [String: Any], stem: String) throws {
        auditSequence += 1
        let safe = stem.replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: " ", with: "_")
        let file = output.appendingPathComponent(String(format: "%04d-%@.json", auditSequence, safe))
        try JSONSerialization.data(withJSONObject: value, options: .sortedKeys)
            .write(to: file, options: .atomic)
    }

    private func controlMetrics(_ target: XCUIElement, role: String) -> [String: Any] {
        let frame = target.frame
        return [
            "role": role,
            "label": target.label,
            "identifier": target.identifier,
            "hittable": target.isHittable,
            "exists": target.exists,
            "framePt": [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)],
            "minDimensionPt": Double(min(frame.width, frame.height)),
            "under44Pt": frame.width < 44 || frame.height < 44,
            "under38Pt": frame.width < 38 || frame.height < 38,
        ]
    }

    @discardableResult
    private func recordInteraction(_ flow: String, _ step: String, control: XCUIElement,
                                   gesture: String, expected: String, action: () -> Void,
                                   success: (String) -> Bool) throws -> Bool {
        let before = stateLabel()
        let started = Date()
        action()
        let elapsedMs = Int(Date().timeIntervalSince(started) * 1_000)
        var after = stateLabel()
        let passed = success(after)
        after = stateLabel()
        try writeAuditJSON([
            "kind": "interaction",
            "flow": flow,
            "step": step,
            "control": controlMetrics(control, role: "interactive"),
            "gesture": gesture,
            "expected": expected,
            "before": before,
            "after": after,
            "success": passed,
            "feedbackMs": elapsedMs,
            "physicalCrownProven": false,
        ], stem: "interaction--\(flow)--\(step)")
        if !passed {
            try observe(flow, step, expected: expected, actual: after)
        }
        return passed
    }

    private func recordBoundary(_ flow: String, _ step: String, claim: String, reason: String) throws {
        try writeAuditJSON([
            "kind": "evidence-boundary",
            "flow": flow,
            "step": step,
            "claim": claim,
            "reason": reason,
            "physicalCrownProven": false,
            "realWatchProven": false,
        ], stem: "boundary--\(flow)--\(step)")
    }

    private func waitForValue(_ key: String, _ expected: Int, timeout: TimeInterval = 0.8) -> Bool {
        XCTWaiter().wait(for: [XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label CONTAINS %@", "\(key)=\(expected);"),
            object: element("watch-audit-state")
        )], timeout: timeout) == .completed
    }

    private func button(_ label: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label == %@", label)).firstMatch
    }

    private func drag(_ target: XCUIElement, distance: CGFloat, xOffset: CGFloat = 0) {
        let frame = target.frame
        let origin = app.coordinate(withNormalizedOffset: .zero)
        let start = origin.withOffset(CGVector(dx: frame.midX + xOffset, dy: frame.midY))
        let end = origin.withOffset(CGVector(dx: frame.midX + xOffset, dy: frame.midY - distance))
        start.press(forDuration: 0.05, thenDragTo: end)
    }

    private func tap(_ target: XCUIElement, scroll: Bool = true) throws {
        guard target.waitForExistence(timeout: 10) else {
            try capture(lastFlow, "\(lastStep)-missing-control", input: "failure-evidence")
            XCTFail("Missing control: \(target)")
            return
        }
        if scroll {
            // Scroll the actual container in the direction of the target. Whole-app flicks can
            // overshoot a row and the old midpoint rule could reverse direction at the viewport
            // edge, returning the scorecard to its start. Use the actual visible bounds instead.
            let container = app.scrollViews.firstMatch.exists ? app.scrollViews.firstMatch : app
            for _ in 0..<30 {
                let frame = target.frame
                // Header/footer controls are valid near the edge. Requiring every reachable
                // control to enter the middle band caused futile drags at the scroll limits.
                if target.isHittable { break }
                let top = app.frame.minY + 44
                let bottom = app.frame.maxY - 4
                if frame.maxY > bottom {
                    scrollContainer(container, towardTop: true)
                } else if frame.minY < top {
                    scrollContainer(container, towardTop: false)
                } else {
                    // The row is in the viewport but may be settling after the previous flick;
                    // keep moving toward its nearest edge instead of oscillating across the list.
                    scrollContainer(container, towardTop: true)
                }
            }
        }
        XCTAssertTrue(target.isHittable, "Control must be reachable: \(target.label)")
        // Use the visual centre explicitly; Watch accessibility activation sometimes picks a
        // different point in a rounded bottom control. This remains an actual pointer tap.
        target.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
    }

    /// watchOS's small scorecard ScrollView ignores XCTest's semantic swipe in some runtimes.
    /// A short real drag inside the visible viewport exercises the same user gesture and avoids
    /// relying on a stale off-screen element coordinate.
    private func scrollContainer(_ container: XCUIElement, towardTop: Bool) {
        let startY: CGFloat = towardTop ? 0.78 : 0.24
        let endY: CGFloat = towardTop ? 0.24 : 0.78
        let start = container.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: startY))
        let end = container.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: endY))
        start.press(forDuration: 0.05, thenDragTo: end)
    }

    private func trace(_ fragment: String, timeout: TimeInterval = 10) {
        let expected = NSPredicate(format: "label CONTAINS %@", fragment)
        let result = XCTWaiter().wait(for: [XCTNSPredicateExpectation(
            predicate: expected, object: element("watch-audit-state")
        )], timeout: timeout)
        XCTAssertEqual(result, .completed, "Expected model state \(fragment)")
    }

    @discardableResult
    private func capture(_ flow: String, _ step: String, input: String = "ui-action",
                         collectControls: Bool = true) throws -> URL {
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
        let controls: [[String: Any]] = collectControls ? app.buttons.allElementsBoundByIndex.map {
            ["label": $0.label, "identifier": $0.identifier, "hittable": $0.isHittable,
             "frame": [Double($0.frame.minX), Double($0.frame.minY),
                       Double($0.frame.width), Double($0.frame.height)]]
        } : []
        let switches: [[String: Any]] = collectControls ? app.switches.allElementsBoundByIndex.map {
            ["label": $0.label, "value": String(describing: $0.value ?? ""), "hittable": $0.isHittable]
        } : []
        let queries: [(String, XCUIElementQuery)] = [
            ("button", app.buttons), ("switch", app.switches), ("slider", app.sliders),
            ("stepper", app.steppers), ("textField", app.textFields),
            ("collection", app.collectionViews), ("scroll", app.scrollViews),
            ("other", app.otherElements),
        ]
        let interactive: [[String: Any]] = collectControls
            ? queries.flatMap { role, query in
                query.allElementsBoundByIndex.map { controlMetrics($0, role: role) }
            }
            : []
        let readableText: [[String: Any]] = collectControls
            ? app.staticTexts.allElementsBoundByIndex.map {
                let frame = $0.frame
                return [
                    "label": $0.label,
                    "identifier": $0.identifier,
                    "framePt": [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)],
                    "hittable": $0.isHittable,
                    // XCTest exposes the rendered frame, not SwiftUI's font token. Font sizes are
                    // cross-checked against the source token and 1:1 physical render downstream.
                    "fontEvidence": "frame-only; source-token-and-physical-render-required",
                ] as [String: Any]
            }
            : []
        let cgImage = screenshot.image.cgImage
        let root = element("watch-audit-state")
        let page = element("watch-hole-page-current")
        let viewport = element("watch-audit-viewport")
        let metadata: [String: Any] = ["flow": flow, "step": step, "inputMode": input,
                                       "trace": root.exists ? root.label : "not-instrumented",
                                       "shownPage": page.exists ? page.label : "not-instrumented",
                                       "viewport": viewport.exists ? viewport.label : "not-instrumented",
                                       "controlsCollected": collectControls,
                                       "controls": controls, "switches": switches,
                                       "interactive": interactive, "readableText": readableText,
                                       "face": ProcessInfo.processInfo.environment["TEST_RUNNER_UITEST_AUDIT_FACE"] ?? "unknown",
                                       "screenFramePt": [Double(app.frame.minX), Double(app.frame.minY),
                                                         Double(app.frame.width), Double(app.frame.height)],
                                       "screenshotPixels": [cgImage?.width ?? 0, cgImage?.height ?? 0],
                                       "aodInjected": ProcessInfo.processInfo.environment["UITEST_AUDIT_AOD"] == "1"]
        try JSONSerialization.data(withJSONObject: metadata, options: .sortedKeys)
            .write(to: output.appendingPathComponent(stem + ".json"), options: .atomic)
        return file
    }

    /// An audit must retain a broken product interaction and still inspect later pages. These
    /// observations are findings, not passing product assertions; any fixture recovery is named.
    private func observe(_ flow: String, _ step: String, expected: String, actual: String) throws {
        let row = ["flow": flow, "step": step, "expected": expected, "actual": actual]
        try JSONSerialization.data(withJSONObject: row, options: .sortedKeys)
            .write(to: output.appendingPathComponent("observation--\(flow)-\(step).json"), options: .atomic)
    }

    private func waitForPage(_ name: String, timeout: TimeInterval = 5) -> Bool {
        let marker = element("watch-hole-page-current")
        return XCTWaiter().wait(for: [XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label == %@", name), object: marker
        )], timeout: timeout) == .completed
    }

    private func swipePage(up: Bool, to name: String, flow: String, step: String) throws -> Bool {
        let pager = app.collectionViews["PUICPageViewController_collectionView"]
        XCTAssertTrue(pager.waitForExistence(timeout: 5))
        if up { pager.swipeUp() } else { pager.swipeDown() }
        let moved = waitForPage(name)
        try capture(flow, step)
        if !moved {
            try observe(flow, step, expected: name, actual: element("watch-hole-page-current").label)
        }
        return moved
    }

    private func openMenu() throws {
        try tap(element("watch-hole-menu"), scroll: false)
        let opened = XCTWaiter().wait(for: [XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label CONTAINS %@", "screen=menu;"),
            object: element("watch-audit-state")
        )], timeout: 3) == .completed
        if !opened {
            try capture("navigation", "menu-tap-no-transition")
            try observe("navigation", "menu-tap-no-transition", expected: "screen=menu;",
                        actual: element("watch-audit-state").label)
            // The production map also offers a long-press menu. Preserve a broken tap, then
            // continue via that real alternative so later scoring flows are still inspected.
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.73)).press(forDuration: 0.75)
            trace("screen=menu;")
            try capture("navigation", "menu-recovered-by-long-press")
        }
    }

    private func beginManualShot(_ step: String) throws {
        try tap(element("watch-hole-record-shot"), scroll: false)
        if !element("watch-shot-undo").waitForExistence(timeout: 3) {
            try capture("shots", step + "-no-transition")
            try observe("shots", step + "-no-transition", expected: "manual shot undo window",
                        actual: element("watch-audit-state").label)
            // Preserve an unresponsive + button. Inject a pending candidate only to inspect the
            // remaining undo/commit controls; this does not prove manual admission on that face.
            try launch("audit-manual-candidate", moveAfterShot: true)
            try capture("shots", step + "-recovered-candidate", input: "injected-state-after-recorded-finding",
                        collectControls: false)
        }
        XCTAssertTrue(element("watch-shot-undo").waitForExistence(timeout: 3))
    }

    private func dragWheel(at frame: CGRect) {
        let origin = app.coordinate(withNormalizedOffset: .zero)
        let start = origin.withOffset(CGVector(dx: frame.midX, dy: frame.midY))
        let end = origin.withOffset(CGVector(dx: frame.midX, dy: frame.midY - 22))
        start.press(forDuration: 0.05, thenDragTo: end)
    }

    private func selectHole(_ hole: Int) throws {
        try openMenu()
        try tap(app.buttons["选洞"])
        try tap(app.buttons[String(hole)])
        trace("hole=\(hole);")
    }

    private func scoreViaCard(_ hole: Int, flow: String) throws {
        lastFlow = flow
        lastStep = String(format: "%02d-open-scorecard", hole)
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
        if try swipePage(up: true, to: "障碍", flow: "pages", step: "04b-swipe-to-hazards") == false {
            try launch("audit-phone-18", page: 1)
            try capture("pages", "04c-recovered-hazard-page", input: "injected-state-after-recorded-finding")
        }
        XCTAssertTrue(element("watch-hazard-next").waitForExistence(timeout: 8))
        try capture("pages", "05-hazard-first")
        try tap(element("watch-hazard-next"), scroll: false)
        try capture("pages", "06-hazard-next")
        if try swipePage(up: true, to: "果岭", flow: "pages", step: "06b-swipe-to-green") == false {
            try launch("audit-phone-18", page: 2)
            try capture("pages", "06c-recovered-green-page", input: "injected-state-after-recorded-finding")
        }
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
        _ = try swipePage(up: false, to: "障碍", flow: "pages", step: "09-back-to-hazard")
    }

    func test03ZoomPanLongPressAndAOD() throws {
        for page in 0...2 {
            for zoom in 1...4 {
                try launch("audit-phone-18", page: page, zoom: zoom)
                trace("map=true;")
                let step = "p\(page)-z\(zoom)"
                try capture("zoom", step + "-before", input: "injected-state")
                if zoom > 1 {
                    let expectedPage = ["方案", "障碍", "果岭"][page]
                    app.coordinate(withNormalizedOffset: CGVector(dx: 0.84, dy: 0.65))
                        .press(forDuration: 0.1, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.66, dy: 0.37)))
                    try capture("zoom", step + "-panned")
                    if !waitForPage(expectedPage, timeout: 1) {
                        try observe("zoom", step + "-panned", expected: expectedPage,
                                    actual: element("watch-hole-page-current").label)
                        try launch("audit-phone-18", page: page, zoom: zoom)
                        try capture("zoom", step + "-recovered-page", input: "injected-state-after-recorded-finding")
                    }
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
        try beginManualShot("01-manual-button")
        try capture("shots", "01-manual-undo-window", collectControls: false)
        try tap(element("watch-shot-undo"), scroll: false)
        trace("shots=0;")
        trace("pending=false;")
        try capture("shots", "02-undone")
        try beginManualShot("03-manual-button")
        try capture("shots", "03-pending-commit", collectControls: false)
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
        let autoShot = app.switches["自动记杆"]
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
        let putts = element("watch-score-putts")
        let puttFrame = putts.frame
        try tap(putts, scroll: false)
        // The production wheel folds after idle. Keep this transient capture fast, then drag at
        // its known location without a second accessibility query racing that timer.
        try capture("scoring", "03-putts-open", collectControls: false)
        dragWheel(at: puttFrame)
        try capture("scoring", "04-putts-adjusted")
        let penalty = element("watch-score-penalty")
        let penaltyFrame = penalty.frame
        try tap(penalty, scroll: false)
        try capture("scoring", "05-penalty-open", collectControls: false)
        dragWheel(at: penaltyFrame)
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
                try tap(app.buttons["继续本场"])
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

    /// Element-level pass for the #419 replacement of the tiny in-chip wheels. The test records
    /// every attempt instead of turning a missed gesture into a green flow assertion: a golfer's
    /// first failed drag is a finding even when a second tap can recover it.
    func test11ElementLevelScorePickersAndAdversarialInput() throws {
        func inspectWheel(_ wheel: String, chip: String, name: String, wrap: Int) throws {
            try launch("audit-phone-18")
            try launch("audit-score-current")
            try capture("score-elements", "\(name)-01-root")
            let chipElement = element(chip)
            guard chipElement.waitForExistence(timeout: 5) else {
                try observe("score-elements", "\(name)-missing-chip", expected: chip, actual: stateLabel())
                return
            }
            try tap(chipElement, scroll: false)
            let picker = element("watch-score-wheel-\(wheel)")
            guard picker.waitForExistence(timeout: 3) else {
                try observe("score-elements", "\(name)-picker-not-open", expected: "full-screen picker", actual: stateLabel())
                return
            }
            try capture("score-elements", "\(name)-02-picker-open")
            let plus = button("\(name)加一")
            let minus = button("\(name)减一")
            let done = element("watch-score-wheel-done")
            try writeAuditJSON([
                "kind": "control-metrics",
                "flow": "score-elements",
                "wheel": name,
                "face": ProcessInfo.processInfo.environment["TEST_RUNNER_UITEST_AUDIT_FACE"] ?? "unknown",
                "controls": [
                    controlMetrics(chipElement, role: "closed-chip"),
                    controlMetrics(picker, role: "full-screen-picker"),
                    controlMetrics(plus, role: "plus"),
                    controlMetrics(minus, role: "minus"),
                    controlMetrics(done, role: "done"),
                ],
                "visibleRowsExpected": 3,
                "rowStepExpectedPt": 30.0,
                "crownInput": "not-simulatable-by-XCUITest",
            ], stem: "metrics--score-elements--\(name)")

            var expected = stateValue(wheel == .putts ? "putts" : "penalty") ?? 0
            for attempt in 1...5 {
                expected = (expected + 1) % wrap
                let key = wheel == "putts" ? "putts" : "penalty"
                _ = try recordInteraction(
                    "score-elements", "\(name)-plus-short-\(attempt)", control: plus,
                    gesture: "tap-centre", expected: "\(key)=\(expected);",
                    action: { plus.tap() },
                    success: { _ in self.waitForValue(key, expected) }
                )
            }
            for attempt in 1...5 {
                expected = (expected - 1 + wrap) % wrap
                let key = wheel == "putts" ? "putts" : "penalty"
                _ = try recordInteraction(
                    "score-elements", "\(name)-minus-short-\(attempt)", control: minus,
                    gesture: "tap-centre", expected: "\(key)=\(expected);",
                    action: { minus.tap() },
                    success: { _ in self.waitForValue(key, expected) }
                )
            }

            // Five 20 pt and five 60 pt drags measure one-step and two-step behaviour. The
            // production implementation uses 30 pt per step; wrapping makes the sequence bounded.
            for (distance, count, label) in [(20.0, 5, "drag-short"), (60.0, 5, "drag-long")] {
                for attempt in 1...count {
                    let key = wheel == "putts" ? "putts" : "penalty"
                    let steps = Int((distance / 30.0).rounded())
                    expected = (expected + steps) % wrap
                    _ = try recordInteraction(
                        "score-elements", "\(name)-\(label)-\(attempt)", control: picker,
                        gesture: "vertical-drag-\(Int(distance))pt", expected: "\(key)=\(expected);",
                        action: { self.drag(picker, distance: CGFloat(distance)) },
                        success: { _ in self.waitForValue(key, expected) }
                    )
                }
            }

            // Off-centre, double-tap and edge-origin gestures are deliberately adversarial. They
            // are recorded as evidence even if the intended value is ambiguous.
            let beforeOffCentre = stateValue(wheel == "putts" ? "putts" : "penalty") ?? expected
            let offCentreOrigin = app.coordinate(withNormalizedOffset: .zero)
            let plusFrame = plus.frame
            _ = try recordInteraction(
                "score-elements", "\(name)-off-centre-8pt", control: plus,
                gesture: "tap-8pt-off-centre", expected: "value changes once",
                action: {
                    offCentreOrigin.withOffset(CGVector(dx: plusFrame.midX + 8, dy: plusFrame.midY + 8)).tap()
                },
                success: { _ in
                    let after = self.stateValue(wheel == "putts" ? "putts" : "penalty") ?? beforeOffCentre
                    return after != beforeOffCentre
                }
            )
            let beforeDouble = stateValue(wheel == "putts" ? "putts" : "penalty") ?? expected
            _ = try recordInteraction(
                "score-elements", "\(name)-double-tap", control: plus,
                gesture: "double-tap", expected: "one visible step per tap, no lost feedback",
                action: { plus.doubleTap() },
                success: { _ in
                    let after = self.stateValue(wheel == "putts" ? "putts" : "penalty") ?? beforeDouble
                    return after != beforeDouble
                }
            )
            let beforeEdge = stateValue(wheel == "putts" ? "putts" : "penalty") ?? expected
            _ = try recordInteraction(
                "score-elements", "\(name)-edge-swipe", control: picker,
                gesture: "vertical-swipe-from-screen-edge", expected: "picker remains open and value is deterministic",
                action: {
                    let edge = app.coordinate(withNormalizedOffset: CGVector(dx: 0.02, dy: 0.5))
                    edge.press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.02, dy: 0.2)))
                },
                success: { _ in
                    let after = self.stateValue(wheel == "putts" ? "putts" : "penalty") ?? beforeEdge
                    return self.element("watch-score-wheel-\(wheel)").exists && after != beforeEdge
                }
            )
            try capture("score-elements", "\(name)-03-after-adversarial")
            if done.exists { try tap(done, scroll: false) }
            try recordBoundary("score-elements", "\(name)-physical-crown", claim: "Crown increments the open wheel one step per notch",
                              reason: "XCUITest has no physical Digital Crown/wrist input; validate on 41/46/49 mm hardware")
        }

        try inspectWheel("putts", chip: "watch-score-putts", name: "推杆", wrap: 6)
        try inspectWheel("penalty", chip: "watch-score-penalty", name: "罚杆", wrap: 5)
    }

    /// A golfer does not interact at test speed. This keeps the app backgrounded between shots,
    /// resumes it after a realistic walk, and retains the hardware/message-interruption boundary.
    func test12RealisticRoundTempoAndResume() throws {
        try launch("audit-phone-18", moveAfterShot: true)
        try capture("tempo", "01-tee-up")
        for interval in 1...2 {
            app.suspend()
            Thread.sleep(forTimeInterval: 20)
            app.activate()
            _ = app.wait(for: .runningForeground, timeout: 5)
            try capture("tempo", "02-wrist-up-\(interval)", input: "ui-action-after-20s-background")
            try recordBoundary("tempo", "02-phone-message-\(interval)", claim: "A phone notification does not steal or dismiss the active round",
                              reason: "Hosted Watch simulator cannot inject a real paired-phone notification")
        }
        try beginManualShot("03-manual-after-walk")
        Thread.sleep(forTimeInterval: 20)
        try capture("tempo", "04-shot-after-20s", input: "ui-action-after-20s-walk")
        try recordBoundary("tempo", "05-wrist-down-aod", claim: "AOD preserves the current hole and pending shot",
                          reason: "AOD is injected by UITEST_AUDIT_AOD; OLED luminance and wrist detection are not simulated")
    }

    /// Repeats page and plan gestures to expose swallowed drags that a single happy-path swipe can
    /// miss. Each attempt has an explicit success rate in the artifact metadata.
    func test13RepeatedPageAndPlanGestures() throws {
        try launch("audit-phone-18")
        let chip = element("watch-plan-club-tag")
        guard chip.waitForExistence(timeout: 8) else {
            try observe("repeat-gestures", "plan-chip-missing", expected: "watch-plan-club-tag", actual: stateLabel())
            return
        }
        var planSuccesses = 0
        for attempt in 1...5 {
            let before = String(describing: chip.value ?? chip.label)
            chip.tap()
            let changed = XCTWaiter().wait(for: [XCTNSPredicateExpectation(
                predicate: NSPredicate(format: "value != %@", before), object: chip
            )], timeout: 0.8) == .completed
            if changed { planSuccesses += 1 }
            try writeAuditJSON(["kind": "repeated-gesture", "screen": "方案", "control": "club-plan-chip",
                                "attempt": attempt, "before": before, "after": String(describing: chip.value ?? chip.label),
                                "success": changed, "gesture": "tap-centre"],
                               stem: "repeat--plan-chip--\(attempt)")
        }
        try writeAuditJSON(["kind": "repeated-summary", "screen": "方案", "control": "club-plan-chip",
                            "attempts": 5, "successes": planSuccesses, "successRate": Double(planSuccesses) / 5.0],
                           stem: "repeat-summary--plan-chip")

        let pager = app.collectionViews["PUICPageViewController_collectionView"]
        guard pager.waitForExistence(timeout: 5) else {
            try observe("repeat-gestures", "pager-missing", expected: "PUICPageViewController_collectionView", actual: stateLabel())
            return
        }
        var pageSuccesses = 0
        for attempt in 1...5 {
            let before = element("watch-hole-page-current").label
            pager.swipeUp()
            let afterChanged = XCTWaiter().wait(for: [XCTNSPredicateExpectation(
                predicate: NSPredicate(format: "label != %@", before), object: element("watch-hole-page-current")
            )], timeout: 1.2) == .completed
            if afterChanged { pageSuccesses += 1 }
            try writeAuditJSON(["kind": "repeated-gesture", "screen": "页面切换", "control": "hole-pager",
                                "attempt": attempt, "before": before,
                                "after": element("watch-hole-page-current").label,
                                "success": afterChanged, "gesture": "swipe-up"],
                               stem: "repeat--hole-pager--\(attempt)")
            pager.swipeDown()
            _ = waitForPage(before, timeout: 1.2)
        }
        try writeAuditJSON(["kind": "repeated-summary", "screen": "页面切换", "control": "hole-pager",
                            "attempts": 5, "successes": pageSuccesses, "successRate": Double(pageSuccesses) / 5.0],
                           stem: "repeat-summary--hole-pager")
        try capture("repeat-gestures", "final")
    }
}
