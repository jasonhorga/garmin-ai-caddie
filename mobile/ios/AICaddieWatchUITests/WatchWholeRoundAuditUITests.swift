import XCTest

/// Issue #417. Opt-in only: ordinary Native CI does not repeat this three-face visual audit.
/// `ui-action` screenshots follow actual taps/swipes/drags. `injected-state` screenshots explicitly
/// identify fixture/hardware boundaries rather than pretending to prove GPS or physical Crown input.
final class WatchWholeRoundAuditUITests: XCTestCase {
    private let app = XCUIApplication()
    private var lastFlow = "unknown"
    private var lastStep = "unknown"
    private var auditSequence = 0
    private var inventoriedStates = Set<String>()
    private var injectedAOD = false
    private var face: String {
        ProcessInfo.processInfo.environment["UITEST_AUDIT_FACE"]
            ?? ProcessInfo.processInfo.environment["TEST_RUNNER_UITEST_AUDIT_FACE"] ?? "unknown"
    }
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
        inventoriedStates.removeAll()
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
                        supportsAutoShot: Bool = false, modelScreen: String? = nil,
                        initialScore: Int? = nil, initialPutts: Int? = nil,
                        initialPenalty: Int? = nil, inputTraceTrial: String? = nil,
                        observeRawInput: Bool = false,
                        fixAgeSeconds: Int? = nil, fixSpeedMps: Double? = nil,
                        safeAreaScope: String? = nil, safeAreaY: CGFloat? = nil) throws {
        app.terminate()
        injectedAOD = aod
        app.launchArguments = ["-uitest-screen", screen]
        app.launchEnvironment = [
            "UITEST_GPS_LAT": "40.0454995", "UITEST_GPS_LON": "116.5461531",
            "UITEST_AUDIT_RANGE": range, "UITEST_AUDIT_PAGE": String(page),
            "UITEST_AUDIT_ZOOM": String(zoom), "UITEST_AUDIT_AOD": aod ? "1" : "0",
            "UITEST_AUDIT_MOVE_AFTER_SHOT": moveAfterShot ? "1" : "0",
            "UITEST_AUDIT_AUTOSHOT_SUPPORTED": supportsAutoShot ? "1" : "0",
            "UITEST_AUDIT_ANCHORS": "1",
        ]
        app.launchEnvironment["UITEST_AUDIT_MODEL_SCREEN"] = modelScreen
        app.launchEnvironment["UITEST_AUDIT_INPUT_TRIAL"] = inputTraceTrial
        app.launchEnvironment["UITEST_AUDIT_INPUT_TRACE"] = observeRawInput ? "1" : "0"
        app.launchEnvironment["UITEST_AUDIT_SCORE"] = initialScore.map { String($0) }
        app.launchEnvironment["UITEST_AUDIT_PUTTS"] = initialPutts.map { String($0) }
        app.launchEnvironment["UITEST_AUDIT_PENALTY"] = initialPenalty.map { String($0) }
        app.launchEnvironment["UITEST_AUDIT_FIX_AGE_SECONDS"] = fixAgeSeconds.map { String($0) }
        app.launchEnvironment["UITEST_AUDIT_FIX_SPEED_MPS"] = fixSpeedMps.map { String($0) }
        app.launchEnvironment["UITEST_AUDIT_SAFE_AREA_SCOPE"] = safeAreaScope
        app.launchEnvironment["UITEST_AUDIT_SAFE_AREA_Y"] = safeAreaY.map { String(Double($0)) }
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
        guard let snapshot = try? target.snapshot() else {
            return ["role": role, "exists": false, "identifier": "unavailable",
                    "hittable": false, "frameEvidence": "absent; not a measured hit target"]
        }
        let frame = snapshot.frame
        guard [frame.minX, frame.minY, frame.width, frame.height].allSatisfy({ $0.isFinite }) else {
            return ["role": role, "exists": true, "identifier": snapshot.identifier,
                    "label": snapshot.label, "frameEvidence": "not currently rendered; non-finite accessibility frame"]
        }
        return [
            "role": role,
            "label": snapshot.label,
            "identifier": snapshot.identifier,
            "hittable": NSNull(),
            "hitTestEvidence": "immutable accessibility snapshot; actual activation is measured separately",
            "exists": true,
            "framePt": [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)],
            "minDimensionPt": Double(min(frame.width, frame.height)),
            "under44Pt": frame.width < 44 || frame.height < 44,
            "under38Pt": frame.width < 38 || frame.height < 38,
        ]
    }

    @discardableResult
    private func recordInteraction(_ flow: String, _ step: String, control: XCUIElement,
                                   gesture: String, expected: String, action: () -> Void,
                                   success: (String) -> Bool,
                                   cachedMetrics: [String: Any]? = nil,
                                   freshPickerOpen: (() -> Void)? = nil) throws -> Bool {
        let before = stateLabel()
        let metrics = cachedMetrics ?? controlMetrics(control, role: "interactive")
        // A fresh-open sequence measures the chip tap and the immediate pointer gesture together.
        // No state/tree query may spend the production timeout between these two actions.
        // Failure to open is an actual first-try failure, never an injected recovery or invalid trial.
        if freshPickerOpen == nil, !control.exists {
            try writeAuditJSON([
                "kind": "interaction", "flow": flow, "step": step, "face": face,
                "control": metrics, "gesture": gesture, "expected": expected,
                "before": before, "after": stateLabel(), "success": false,
                "attemptValid": false, "reason": "control absent/unhittable before dispatch; do not count as a product gesture failure",
            ], stem: "interaction--\(flow)--\(step)")
            return false
        }
        let started = Date()
        freshPickerOpen?()
        action()
        let elapsedMs = Int(Date().timeIntervalSince(started) * 1_000)
        var after = stateLabel()
        let passed = success(after)
        after = stateLabel()
        try writeAuditJSON([
            "kind": "interaction",
            "flow": flow,
            "step": step,
            "control": metrics,
            "face": face,
            "attemptValid": true,
            "gesture": gesture,
            "expected": expected,
            "before": before,
            "after": after,
            "success": passed,
            "xctestActionMs": elapsedMs,
            "uiFeedbackMs": NSNull(),
            "latencyEvidence": "XCTest synchronization overhead; not a 300ms UI feedback measurement",
            "physicalCrownProven": false,
            "includesFreshOpen": freshPickerOpen != nil,
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

    private func waitForValue(_ key: String, _ expected: Int, timeout: TimeInterval = 2) -> Bool {
        if stateValue(key) == expected { return true }
        return XCTWaiter().wait(for: [XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label CONTAINS %@", "\(key)=\(expected);"),
            object: element("watch-audit-state")
        )], timeout: timeout) == .completed
    }

    private func waitForFragment(_ fragment: String, timeout: TimeInterval = 1.2) -> Bool {
        if stateLabel().contains(fragment) { return true }
        return XCTWaiter().wait(for: [XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label CONTAINS %@", fragment),
            object: element("watch-audit-state")
        )], timeout: timeout) == .completed
    }

    private func reach(_ target: XCUIElement, flow: String, step: String) throws -> Bool {
        guard target.exists else {
            try observe(flow, step, expected: "control exists", actual: stateLabel())
            return false
        }
        let container = app.scrollViews.firstMatch.exists ? app.scrollViews.firstMatch : app
        var scrolls = 0
        while !target.isHittable && scrolls < 6 {
            let towardTop = target.frame.maxY > app.frame.maxY - 4
            scrollContainer(container, towardTop: towardTop)
            scrolls += 1
        }
        try writeAuditJSON([
            "kind": "reachability", "flow": flow, "step": step, "face": face,
            "scrollGestures": scrolls, "reachable": target.isHittable,
            "control": controlMetrics(target, role: "interactive"),
        ], stem: "reach--\(flow)--\(step)")
        if !target.isHittable {
            try capture(flow, step + "-unreachable", collectControls: false)
        }
        return target.isHittable
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
        let root = element("watch-audit-state")
        let page = element("watch-hole-page-current")
        let currentTrace = root.exists ? root.label : "not-instrumented"
        let screen = currentTrace.components(separatedBy: ";").first { $0.hasPrefix("screen=") } ?? "unknown"
        let inventoryKey = "\(flow)|\(screen)|\(page.exists ? page.label : "none")|\(input)|\(injectedAOD)"
        // One inventory per distinct state. Full accessibility enumeration can exceed transient
        // picker/undo timers; it must not run in every screenshot/gesture or silently hold UI open.
        let inventory = collectControls && inventoriedStates.insert(inventoryKey).inserted
        let queries: [(String, XCUIElementQuery)] = [
            ("button", app.buttons), ("switch", app.switches), ("slider", app.sliders),
            ("stepper", app.steppers), ("textField", app.textFields),
            ("collection", app.collectionViews), ("scroll", app.scrollViews),
            ("picker", app.pickers), ("pickerWheel", app.pickerWheels),
        ]
        var interactive: [[String: Any]] = inventory
            ? queries.flatMap { role, query in
                query.allElementsBoundByIndex.map { controlMetrics($0, role: role) }
            }
            : []
        if inventory {
            interactive += app.otherElements.allElementsBoundByIndex.filter {
                $0.identifier.hasPrefix("watch-") && $0.identifier != "watch-audit-state"
            }.map { controlMetrics($0, role: "custom-gesture-or-container") }
        }
        let controls = interactive.filter { ($0["role"] as? String) == "button" }.map { metric in
            ["label": metric["label"] ?? "", "identifier": metric["identifier"] ?? "",
             "hittable": metric["hittable"] ?? false, "frame": metric["framePt"] ?? [Double]()] as [String: Any]
        }
        let switches = interactive.filter { ($0["role"] as? String) == "switch" }
        let readableText: [[String: Any]] = inventory
            ? app.staticTexts.allElementsBoundByIndex.map {
                guard let snapshot = try? $0.snapshot() else { return ["exists": false] as [String: Any] }
                let frame = snapshot.frame
                guard [frame.minX, frame.minY, frame.width, frame.height].allSatisfy({ $0.isFinite }) else {
                    return ["label": snapshot.label, "frameEvidence": "not currently rendered"] as [String: Any]
                }
                return [
                    "label": snapshot.label,
                    "identifier": snapshot.identifier,
                    "framePt": [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)],
                    "hittable": NSNull(),
                    // XCTest exposes the rendered frame, not SwiftUI's font token. Font sizes are
                    // cross-checked against the source token and 1:1 physical render downstream.
                    "fontEvidence": "frame-only; source-token-and-physical-render-required",
                ] as [String: Any]
            }
            : []
        let cgImage = screenshot.image.cgImage
        let viewport = activeViewport()
        let metadata: [String: Any] = ["flow": flow, "step": step, "inputMode": input,
                                       "trace": root.exists ? root.label : "not-instrumented",
                                       "shownPage": page.exists ? page.label : "not-instrumented",
                                       "viewport": viewport.exists ? viewport.label : "not-instrumented",
                                       "controlsCollected": inventory,
                                       "inventoryKey": inventoryKey,
                                       "controls": controls, "switches": switches,
                                       "interactive": interactive, "readableText": readableText,
                                       "face": face,
                                       "screenFramePt": [Double(app.frame.minX), Double(app.frame.minY),
                                                         Double(app.frame.width), Double(app.frame.height)],
                                       "screenshotPixels": [cgImage?.width ?? 0, cgImage?.height ?? 0],
                                       "aodInjected": injectedAOD]
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
        if marker.exists && marker.label == name { return true }
        return XCTWaiter().wait(for: [XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label == %@", name), object: marker
        )], timeout: timeout) == .completed
    }

    private func activeViewport() -> XCUIElement {
        let page = element("watch-hole-page-current")
        let id = page.exists && page.label == "障碍" ? "hazard" : "plan"
        return element("watch-audit-viewport-\(id)")
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
        try tap(putts, scroll: false)
        // The production wheel folds after idle. Keep this transient capture fast, then drag at
        // its known location without a second accessibility query racing that timer.
        try capture("scoring", "03-putts-open", collectControls: false)
        drag(element("watch-score-wheel-putts"), distance: 20)
        try capture("scoring", "04-putts-adjusted", collectControls: false)
        if element("watch-score-wheel-done").exists { element("watch-score-wheel-done").tap() }
        let penalty = element("watch-score-penalty")
        try tap(penalty, scroll: false)
        try capture("scoring", "05-penalty-open", collectControls: false)
        drag(element("watch-score-wheel-penalty"), distance: 20)
        try capture("scoring", "06-penalty-adjusted", collectControls: false)
        if element("watch-score-wheel-done").exists { element("watch-score-wheel-done").tap() }
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

    /// The production picker still closes after 4 s idle / 2.5 s after dragging. Inventory is
    /// sampled separately; each trial explicitly reopens if needed. Reopens are not gesture passes.
    func test11ElementLevelScorePickersAndAdversarialInput() throws {
        func inspectWheel(_ wheel: String, chip: String, name: String, wrap: Int) throws {
            try launch("audit-phone-18", modelScreen: "scoring")
            try capture("score-elements", "\(name)-01-root", input: "injected-screen-production-controls")
            let chipElement = element(chip)
            let chipMetrics = controlMetrics(chipElement, role: "closed-chip")
            let picker = element("watch-score-wheel-\(wheel)")
            let plus = button("\(name)加一")
            let minus = button("\(name)减一")
            let done = element("watch-score-wheel-done")
            var reopens = 0
            func openPicker() -> Bool {
                if !picker.exists {
                    guard chipElement.exists, chipElement.isHittable else { return false }
                    chipElement.tap()
                    reopens += 1
                }
                return picker.waitForExistence(timeout: 1)
            }
            guard openPicker() else {
                try observe("score-elements", "\(name)-missing-picker", expected: "full-screen picker", actual: stateLabel())
                return
            }
            try capture("score-elements", "\(name)-02-picker-open", collectControls: false)
            // Never enumerate a complete tree inside a production timeout window.
            var measured: [[String: Any]] = [chipMetrics]
            for (role, target) in [("full-screen-picker", picker), ("plus", plus), ("minus", minus), ("done", done)] {
                // Each geometry sample gets a fresh production open. Otherwise the previous
                // snapshot can leave a still-visible overlay just milliseconds from closing.
                if picker.exists { Thread.sleep(forTimeInterval: 4.3) }
                guard openPicker() else { continue }
                measured.append(controlMetrics(target, role: role))
            }
            try writeAuditJSON([
                "kind": "control-metrics", "flow": "score-elements", "wheel": name, "face": face,
                "controls": measured, "visibleRowsExpected": 3, "dragStepSourcePt": 30,
                "visibleRowHeight": "font dependent; read screenshot/source, not a 30pt row-height claim",
                "crownInput": "not-simulatable-by-XCUITest", "productionIdleSeconds": 4.0,
                "productionSettledSeconds": 2.5, "heldOpen": false,
            ], stem: "metrics--score-elements--\(name)")
            let pickerMetrics = measured.first { ($0["role"] as? String) == "full-screen-picker" } ?? [:]
            let plusMetrics = measured.first { ($0["role"] as? String) == "plus" } ?? [:]
            let minusMetrics = measured.first { ($0["role"] as? String) == "minus" } ?? [:]
            // Reading a live frame after preparing the overlay can outlast its real idle timer.
            // Freeze only measured geometry; all following input is still real pointer input.
            func frozenFrame(_ metrics: [String: Any]) throws -> CGRect {
                let values = try XCTUnwrap(metrics["framePt"] as? [Double], "Missing measured picker geometry")
                XCTAssertEqual(values.count, 4)
                return CGRect(x: values[0], y: values[1], width: values[2], height: values[3])
            }
            let pickerFrame = try frozenFrame(pickerMetrics)
            let plusFrame = try frozenFrame(plusMetrics)
            let minusFrame = try frozenFrame(minusMetrics)
            let origin = app.coordinate(withNormalizedOffset: .zero)
            let plusPoint = origin.withOffset(CGVector(dx: plusFrame.midX, dy: plusFrame.midY))
            let minusPoint = origin.withOffset(CGVector(dx: minusFrame.midX, dy: minusFrame.midY))
            let chipFrame = try frozenFrame(chipMetrics)
            let chipPoint = origin.withOffset(CGVector(dx: chipFrame.midX, dy: chipFrame.midY))
            let doneMetrics = measured.first { ($0["role"] as? String) == "done" } ?? [:]
            let doneFrame = try frozenFrame(doneMetrics)
            let donePoint = origin.withOffset(CGVector(dx: doneFrame.midX, dy: doneFrame.midY))

            let groups = ["plus", "minus", "20pt", "60pt", "off-centre-8pt", "double-tap", "edge-60pt", "long-press"]
            for group in groups {
                var valid = 0
                var successes = 0
                for attempt in 1...5 {
                    try launch("audit-phone-18", modelScreen: "scoring")
                    let before = stateValue(wheel) ?? -1
                    let delta = group == "minus" ? -1 : (group == "60pt" || group == "edge-60pt" || group == "double-tap" ? 2 : 1)
                    let expected = (before + delta + wrap) % wrap
                    let control = group == "minus" ? minus
                        : (["plus", "off-centre-8pt", "double-tap", "long-press"].contains(group) ? plus : picker)
                    let metrics = group == "minus" ? minusMetrics : (control == picker ? pickerMetrics : plusMetrics)
                    // State is sampled immediately before dispatch. No stale expected sequence is
                    // carried across a failed attempt: later trials still test their own exact step.
                    let passed = try recordInteraction(
                        "score-elements", "\(name)-\(group)-\(attempt)", control: control,
                        gesture: group, expected: "\(wheel)=\(expected);",
                        action: {
                            switch group {
                            case "plus": plusPoint.tap()
                            case "minus": minusPoint.tap()
                            case "20pt", "60pt":
                                let distance: CGFloat = group == "20pt" ? 20 : 60
                                origin.withOffset(CGVector(dx: pickerFrame.midX, dy: pickerFrame.midY))
                                    .press(forDuration: 0.05, thenDragTo: origin.withOffset(CGVector(
                                        dx: pickerFrame.midX, dy: pickerFrame.midY - distance)))
                            case "off-centre-8pt":
                                origin.withOffset(CGVector(dx: plusFrame.midX + 8, dy: plusFrame.midY + 8)).tap()
                            case "double-tap": plusPoint.doubleTap()
                            case "long-press": plusPoint.press(forDuration: 0.7)
                            default:
                                let point = origin.withOffset(CGVector(dx: pickerFrame.minX + 7, dy: pickerFrame.midY + 15))
                                point.press(forDuration: 0.05, thenDragTo:
                                    origin.withOffset(CGVector(dx: pickerFrame.minX + 7, dy: pickerFrame.midY - 45)))
                            }
                        },
                        success: { _ in self.waitForValue(wheel, expected) },
                        cachedMetrics: metrics,
                        freshPickerOpen: { chipPoint.tap() }
                    )
                    reopens += 1
                    valid += 1
                    if passed { successes += 1 }
                    if attempt == 1 || attempt == 5 {
                        try capture("score-elements", "\(name)-\(group)-\(attempt)", collectControls: false)
                    }
                }
                try writeAuditJSON([
                    "kind": "repeated-summary", "screen": "本洞成绩", "control": name, "face": face,
                    "gesture": group, "attempts": 5, "validPreparedTrials": valid, "successes": successes,
                    "successRate": valid > 0 ? Double(successes) / Double(valid) : 0,
                    "reopensSoFar": reopens, "firstTryHardwareProven": false,
                ], stem: "repeat-summary--\(wheel)--\(group)")
            }
            for attempt in 1...5 {
                try launch("audit-phone-18", modelScreen: "scoring")
                let before = stateValue(wheel) ?? -1
                _ = try recordInteraction(
                    "score-elements", "\(name)-done-\(attempt)", control: done, gesture: "tap",
                    expected: "picker closed, selected \(wheel) retained",
                    action: { donePoint.tap() },
                    success: { state in state.contains("screen=scoring;") && !picker.exists && self.stateValue(wheel, in: state) == before },
                    cachedMetrics: doneMetrics,
                    freshPickerOpen: { chipPoint.tap() }
                )
            }
            guard openPicker() else { return }
            Thread.sleep(forTimeInterval: 4.5)
            try capture("score-elements", "\(name)-idle-auto-close", collectControls: false)
            try writeAuditJSON([
                "kind": "idle-timeout", "screen": "本洞成绩", "control": name, "face": face,
                "delaySeconds": 4.5, "pickerStillVisible": picker.exists, "state": stateLabel(),
            ], stem: "timeout--\(wheel)")
            try recordBoundary("score-elements", "\(name)-physical-crown",
                               claim: "Crown increments the open wheel one step per notch",
                               reason: "XCUITest does not expose physical Digital Crown/wrist input")
        }
        try inspectWheel("putts", chip: "watch-score-putts", name: "推杆", wrap: 6)
        try inspectWheel("penalty", chip: "watch-score-penalty", name: "罚杆", wrap: 5)
    }

    /// Every start/target pair uses a new draft, a real chip tap and at most one real drag.
    /// Values are observed immediately. Timers are not held open and Crown input is not claimed.
    func test18PickerRangeReachability() throws {
        for (wheel, count) in [("putts", 6), ("penalty", 5)] {
            try launch("audit-phone-18", modelScreen: "scoring")
            let chip = element("watch-score-\(wheel)")
            let chipSnapshot = try chip.snapshot()
            let chipFrame = chipSnapshot.frame
            chip.tap()
            let picker = element("watch-score-wheel-\(wheel)")
            XCTAssertTrue(picker.waitForExistence(timeout: 1))
            let pickerFrame = try picker.snapshot().frame
            let origin = app.coordinate(withNormalizedOffset: .zero)
            for start in 0..<count {
                for target in 0..<count {
                    try launch("audit-phone-18", modelScreen: "scoring",
                               initialPutts: wheel == "putts" ? start : 0,
                               initialPenalty: wheel == "penalty" ? start : 0)
                    let before = stateValue(wheel) ?? -1
                    origin.withOffset(CGVector(dx: chipFrame.midX, dy: chipFrame.midY)).tap()
                    var delta = (target - start + count) % count
                    if delta > count / 2 { delta -= count }
                    if delta != 0 {
                        origin.withOffset(CGVector(dx: pickerFrame.midX, dy: pickerFrame.midY))
                            .press(forDuration: 0.05, thenDragTo: origin.withOffset(CGVector(
                                dx: pickerFrame.midX, dy: pickerFrame.midY - CGFloat(delta) * 30)))
                    }
                    let after = stateValue(wheel) ?? -1
                    try writeAuditJSON([
                        "kind": "value-reachability", "screen": "本洞成绩", "control": wheel,
                        "face": face, "start": start, "before": before, "requested": target,
                        "gestures": delta == 0 ? 1 : 2, "includesOpen": true,
                        "attemptValid": before == start, "after": after,
                        "withinThree": before == start && after == target,
                        "input": "real-pointer; seeded-start-draft; measured-cached-frame",
                        "dispatch": "fresh chip tap then immediate drag; no intervening state/tree query",
                        "physicalCrownProven": false,
                    ], stem: "range--\(wheel)--\(start)--\(target)")
                    if target == 0 || target == count - 1 {
                        try capture("picker-range", "\(wheel)-start-\(start)-target-\(target)", collectControls: false)
                    }
                }
            }
        }
    }

    /// A golfer does not interact at test speed. This keeps the app backgrounded between shots,
    /// resumes it after a realistic walk, and retains the hardware/message-interruption boundary.
    func test12RealisticRoundTempoAndResume() throws {
        try launch("audit-phone-18", moveAfterShot: true)
        try capture("tempo", "01-tee-up")
        for interval in 1...2 {
            // XCTest has no XCUIApplication.suspend on watchOS. Pressing Home exercises the
            // actual background/resume boundary; the paired-phone notification remains an
            // explicit evidence gap below.
            XCUIDevice.shared.press(.home)
            Thread.sleep(forTimeInterval: interval == 1 ? 20 : 60)
            app.activate()
            _ = app.wait(for: .runningForeground, timeout: 5)
            try capture("tempo", "02-wrist-up-\(interval)", input: interval == 1
                ? "ui-action-after-20s-background" : "ui-action-after-60s-background")
            try recordBoundary("tempo", "02-phone-message-\(interval)", claim: "A phone notification does not steal or dismiss the active round",
                              reason: "Hosted Watch simulator cannot inject a real paired-phone notification")
        }
        try beginManualShot("03-manual-after-walk")
        Thread.sleep(forTimeInterval: 20)
        try capture("tempo", "04-shot-after-20s", input: "ui-action-after-20s-walk")
        try recordBoundary("tempo", "05-wrist-down-aod", claim: "AOD preserves the current hole and pending shot",
                          reason: "AOD is injected by UITEST_AUDIT_AOD; OLED luminance and wrist detection are not simulated")
        try launch("audit-score-current")
        try capture("tempo", "06-score-after-walk")
        let save = element("watch-score-save")
        if save.exists {
            save.tap()
            _ = waitForValue("hole", 2)
            try capture("tempo", "07-next-tee")
        }
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
            let changed = String(describing: chip.value ?? chip.label) != before || XCTWaiter().wait(for: [XCTNSPredicateExpectation(
                predicate: NSPredicate(format: "value != %@", before), object: chip
            )], timeout: 2) == .completed
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
            let afterChanged = waitForPage("障碍", timeout: 1.2)
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
        for page in [0, 1] {
            for attempt in 1...5 {
                // A failed hazard pan can turn the page. Every trial must start on the intended
                // page again; four later drags on 果岭 are not four more hazard-pan failures.
                try launch("audit-phone-18", page: page, zoom: 2)
                let viewportID = "watch-audit-viewport-\(page == 0 ? "plan" : "hazard")"
                let beforePage = element("watch-hole-page-current").label
                let before = (try? element(viewportID).snapshot().label) ?? "not-instrumented"
                let expectedPage = page == 0 ? "方案" : "障碍"
                let valid = beforePage == expectedPage && before.contains("zoom=2.")
                try capture("map-elements", "page-\(page)-before-\(attempt)",
                            input: "injected-zoom-real-pan", collectControls: false)
                let from = app.coordinate(withNormalizedOffset: CGVector(dx: 0.46, dy: 0.65))
                let to = app.coordinate(withNormalizedOffset: CGVector(dx: 0.46, dy: attempt.isMultiple(of: 2) ? 0.76 : 0.54))
                from.press(forDuration: 0.05, thenDragTo: to)
                // Keep pager rubber-band motion out of the settled-image comparison. This delay
                // is evidence collection only, never a visible-feedback latency measurement.
                Thread.sleep(forTimeInterval: 0.8)
                let after = (try? element(viewportID).snapshot().label) ?? "not-instrumented"
                let afterPage = element("watch-hole-page-current").label
                try writeAuditJSON(["kind": "repeated-gesture", "screen": expectedPage, "face": face,
                    "control": "zoomed-map", "gesture": "vertical-pan", "attempt": attempt,
                    "before": before, "after": after, "beforePage": beforePage, "page": afterPage,
                    "attemptValid": valid, "preparation": "fresh launch on intended page for every trial",
                    "settleSeconds": 0.8, "uiFeedbackMs": NSNull(),
                    "success": valid && after != before && afterPage == expectedPage,
                    "imageAdjudicationRequired": true],
                    stem: "repeat--map-\(page)--\(attempt)")
                try capture("map-elements", "page-\(page)-pan-\(attempt)", collectControls: false)
                if page == 1 {
                    // Switch independently of the pan result, preserving the failed pan above.
                    try launch("audit-phone-18", page: 1, zoom: 2)
                    let viewport = element(viewportID)
                    let next = element("watch-hazard-next")
                    if next.exists {
                        let label = next.label
                        let viewBefore = viewport.exists ? viewport.label : "not-instrumented"
                        next.tap()
                        let viewAfter = viewport.exists ? viewport.label : "not-instrumented"
                        try writeAuditJSON(["kind": "repeated-gesture", "screen": "障碍", "face": face,
                            "control": "watch-hazard-next", "gesture": "tap", "attempt": attempt,
                            "before": label, "after": next.label, "viewportBefore": viewBefore,
                            "viewportAfter": viewAfter, "success": next.label != label && viewBefore == viewAfter],
                            stem: "repeat--hazard-next--\(attempt)")
                        try capture("map-elements", "hazard-next-\(attempt)", collectControls: false)
                    }
                }
            }
        }
    }

    /// Real navigation callbacks, five attempts each. A failed return is retained; only then may
    /// a named injected screen restore coverage. It never counts as successful navigation.
    func test14RepeatedNavigationAndRecovery() throws {
        try launch("audit-phone-18")
        try capture("nav-elements", "root")
        for attempt in 1...5 {
            let menu = element("watch-hole-menu")
            _ = try recordInteraction("nav-elements", "root-menu-\(attempt)", control: menu,
                gesture: attempt.isMultiple(of: 2) ? "tap-8pt-off-centre" : "tap-centre",
                expected: "screen=menu;", action: {
                    let frame = menu.frame
                    self.app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(
                        dx: frame.midX + (attempt.isMultiple(of: 2) ? 8 : 0), dy: frame.midY)).tap()
                }, success: { _ in self.waitForFragment("screen=menu;") })
            if !stateLabel().contains("screen=menu;") {
                try launch("audit-phone-18", modelScreen: "menu")
                try capture("nav-elements", "menu-\(attempt)-injected-recovery", input: "injected-screen-after-failed-navigation")
            }
            let back = button("返回球洞")
            if back.exists {
                _ = try recordInteraction("nav-elements", "root-back-\(attempt)", control: back, gesture: "tap",
                    expected: "screen=home;", action: { back.tap() },
                    success: { _ in self.waitForFragment("screen=home;") })
            }
            if !stateLabel().contains("screen=home;") { try launch("audit-phone-18") }
        }
        let routes = [
            ("查看果岭", "viewGreen", "返回菜单"), ("球童建议", "caddie", "返回球洞"),
            ("选洞", "holeSelect", "返回菜单"), ("计分卡", "scorecard", "返回"),
            ("障碍", "hazards", "返回菜单"), ("结束本场", "finishing", "继续打球"),
        ]
        for (label, destination, returnLabel) in routes {
            try launch("audit-phone-18", modelScreen: "menu")
            try capture("nav-elements", "menu-\(destination)", input: "injected-screen-production-controls")
            for attempt in 1...5 {
                let target = button(label)
                guard try reach(target, flow: "nav-elements", step: "\(destination)-\(attempt)") else { break }
                _ = try recordInteraction("nav-elements", "\(destination)-open-\(attempt)", control: target,
                    gesture: "tap", expected: "screen=\(destination);", action: { target.tap() },
                    success: { _ in self.waitForFragment("screen=\(destination);") })
                if attempt == 1 {
                    try capture("nav-elements", "\(destination)-opened")
                }
                let back = button(returnLabel)
                if back.exists, try reach(back, flow: "nav-elements", step: "\(destination)-back-\(attempt)") {
                    let expectedScreen = returnLabel == "返回球洞" || returnLabel == "继续打球" ? "home" : "menu"
                    _ = try recordInteraction("nav-elements", "\(destination)-back-\(attempt)", control: back,
                        gesture: "tap", expected: "screen=\(expectedScreen);", action: { back.tap() },
                        success: { _ in self.waitForFragment("screen=\(expectedScreen);") })
                }
                if stateLabel().contains("screen=home;"), element("watch-hole-menu").exists {
                    element("watch-hole-menu").tap()
                }
                if !waitForFragment("screen=menu;") {
                    try capture("nav-elements", "\(destination)-\(attempt)-before-recovery", collectControls: false)
                    try launch("audit-phone-18", modelScreen: "menu")
                }
            }
        }
        for (label, destination) in [("旗向指引", "flagDirection"), ("球杆数据", "clubStats")] {
            try launch("audit-phone-18", modelScreen: "menu")
            for attempt in 1...5 {
                let tools = button("更多工具")
                guard try reach(tools, flow: "tools-elements", step: "more-\(destination)-\(attempt)") else { break }
                tools.tap()
                if attempt == 1 { try capture("tools-elements", "more-\(destination)") }
                let target = button(label)
                guard try reach(target, flow: "tools-elements", step: "\(destination)-\(attempt)") else { break }
                _ = try recordInteraction("tools-elements", "\(destination)-\(attempt)", control: target,
                    gesture: "tap", expected: "screen=\(destination);", action: { target.tap() },
                    success: { _ in self.waitForFragment("screen=\(destination);") })
                if attempt == 1 { try capture("tools-elements", destination) }
                let back = button("返回菜单")
                if back.exists { back.tap() }
                if !waitForFragment("screen=menu;") { try launch("audit-phone-18", modelScreen: "menu") }
            }
        }
        try launch("audit-phone-18", supportsAutoShot: true, modelScreen: "settings")
        try capture("settings-elements", "supported", input: "injected-screen-production-controls")
        let settingLabels = ["GPS 预热", "大字模式", "自动记杆"]
        for label in settingLabels {
            let target = element(label)
            guard try reach(target, flow: "settings-elements", step: label) else { continue }
            for attempt in 1...5 {
                let before = String(describing: target.value ?? "")
                let enabled = before == "开启" || before == "1"
                _ = try recordInteraction("settings-elements", "\(label)-\(attempt)", control: target,
                    gesture: "tap", expected: enabled ? "关闭" : "开启", action: { target.tap() },
                    success: { _ in
                        let after = String(describing: target.value ?? "")
                        return enabled ? ["关闭", "0"].contains(after) : ["开启", "1"].contains(after)
                    })
            }
        }
        try capture("settings-elements", "after-toggles")
    }

    func test15ScoreBandFairwayAndCancel() throws {
        for axis in ["horizontal", "vertical"] {
            for distance in [20, 60] {
                try launch("audit-phone-18", modelScreen: "scoring", initialScore: 4, initialPutts: 0)
                try capture("band-elements", "\(axis)-\(distance)-root", input: "injected-draft-production-controls")
                let band = element("watch-score-band")
                let metrics = controlMetrics(band, role: "total-band")
                for attempt in 1...5 {
                    let before = stateValue("score") ?? -1
                    let expected = min(15, before + Int((Double(distance) / 28).rounded()))
                    _ = try recordInteraction("band-elements", "\(axis)-\(distance)-\(attempt)",
                        control: band, gesture: "\(axis)-drag-\(distance)pt", expected: "score=\(expected);",
                        action: {
                            let frame = band.frame
                            let origin = self.app.coordinate(withNormalizedOffset: .zero)
                            let from = origin.withOffset(CGVector(dx: frame.midX + 20, dy: frame.midY))
                            let to = origin.withOffset(CGVector(
                                dx: frame.midX + 20 - (axis == "horizontal" ? CGFloat(distance) : 0),
                                dy: frame.midY - (axis == "vertical" ? CGFloat(distance) : 0)))
                            from.press(forDuration: 0.05, thenDragTo: to)
                        }, success: { _ in self.waitForValue("score", expected) }, cachedMetrics: metrics)
                }
                try capture("band-elements", "\(axis)-\(distance)-final")
            }
        }
        for initial in [1, 10, 15] {
            try launch("audit-phone-18", modelScreen: "scoring", initialScore: initial, initialPutts: 0)
            let band = element("watch-score-band")
            for requested in 10...20 {
                let before = stateValue("score") ?? -1
                let delta = requested - before
                // A single continuous band drag, bounded to the visible screen, then at most two
                // more. Reaching the product cap is evidence, not a skipped requested value.
                var gestures = 0
                while stateValue("score") != requested && gestures < 3 {
                    let now = stateValue("score") ?? -1
                    let steps = min(5, max(-5, requested - now))
                    if steps == 0 { break }
                    let frame = band.frame
                    let origin = app.coordinate(withNormalizedOffset: .zero)
                    let from = origin.withOffset(CGVector(dx: steps > 0 ? frame.maxX - 8 : frame.minX + 8, dy: frame.midY))
                    from.press(forDuration: 0.05, thenDragTo: origin.withOffset(CGVector(
                        dx: (steps > 0 ? frame.maxX - 8 : frame.minX + 8) - CGFloat(steps) * 28,
                        dy: frame.midY)))
                    gestures += 1
                }
                try writeAuditJSON(["kind": "value-reachability", "screen": "本洞成绩", "face": face,
                    "start": initial, "before": before, "requested": requested, "delta": delta,
                    "gestures": gestures, "after": stateValue("score") ?? -1,
                    "withinThree": stateValue("score") == requested],
                    stem: "range--score--\(initial)--\(requested)")
                if requested == 10 || requested == 15 || requested == 20 {
                    try capture("band-elements", "start-\(initial)-requested-\(requested)", collectControls: false)
                }
            }
        }
        try launch("audit-phone-18", modelScreen: "scoring")
        try capture("fairway-elements", "root", input: "injected-screen-production-controls")
        for result in ["LEFT", "HIT", "RIGHT"] {
            let target = element("watch-score-fairway-\(result)")
            for attempt in 1...5 {
                let selected = stateLabel().contains("fairway=\(result);")
                let expected = selected ? "fairway=none;" : "fairway=\(result);"
                _ = try recordInteraction("fairway-elements", "\(result)-\(attempt)", control: target,
                    gesture: attempt.isMultiple(of: 2) ? "tap-8pt-off-centre" : "tap-centre",
                    expected: expected, action: {
                        let frame = target.frame
                        self.app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(
                            dx: frame.midX + (attempt.isMultiple(of: 2) ? 8 : 0), dy: frame.midY + 6)).tap()
                    }, success: { _ in self.waitForFragment(expected) })
            }
        }
        for attempt in 1...5 {
            if attempt > 1 { try launch("audit-score-current", initialScore: 11) }
            let cancel = button("取消记分")
            _ = try recordInteraction("fairway-elements", "cancel-\(attempt)", control: cancel, gesture: "tap",
                expected: "screen=home;scored=0;strokes=0",
                action: { cancel.tap() },
                success: { _ in self.waitForFragment("screen=home;")
                    && self.stateValue("scored") == 0 && self.stateValue("strokes") == 0 })
            try capture("fairway-elements", "cancelled-\(attempt)", collectControls: false)
        }
    }

    func test16HoleGridScorecardAndFinishRecovery() throws {
        for hole in [1, 9, 10, 18] {
            try launch("audit-phone-18", modelScreen: "holeSelect")
            try capture("select-elements", "hole-\(hole)-grid", input: "injected-screen-production-controls")
            for attempt in 1...5 {
                if attempt > 1 { try launch("audit-phone-18", modelScreen: "holeSelect") }
                let target = button(String(hole))
                guard try reach(target, flow: "select-elements", step: "hole-\(hole)-\(attempt)") else { break }
                _ = try recordInteraction("select-elements", "hole-\(hole)-\(attempt)", control: target,
                    gesture: "tap", expected: "hole=\(hole);screen=home;",
                    action: { target.tap() },
                    success: { _ in self.waitForValue("hole", hole) && self.waitForFragment("screen=home;") })
            }
        }
        for hole in [1, 4, 9, 18] {
            try launch("audit-phone-18", modelScreen: "scorecard")
            try capture("card-elements", "row-\(hole)-card", input: "injected-screen-production-controls")
            for attempt in 1...5 {
                if attempt > 1 { try launch("audit-phone-18", modelScreen: "scorecard") }
                let target = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "\(hole),")).firstMatch
                // Label punctuation varies by OS; constrain the integer token rather than matching
                // '1' to row 10. Keep the actual selected hole in DEBUG telemetry for verification.
                let row = target.exists ? target
                    : app.buttons.matching(NSPredicate(format: "label MATCHES %@", "^\(hole)([^0-9].*)?$")).firstMatch
                guard try reach(row, flow: "card-elements", step: "row-\(hole)-\(attempt)") else { break }
                _ = try recordInteraction("card-elements", "row-\(hole)-\(attempt)", control: row,
                    gesture: "tap", expected: "screen=scoring;scoringHole=\(hole)",
                    action: { row.tap() },
                    success: { _ in self.waitForFragment("screen=scoring;") && self.stateValue("editing") == hole })
                try capture("card-elements", "row-\(hole)-\(attempt)-edit", collectControls: false)
                let save = element("watch-score-save")
                if save.exists {
                    _ = try recordInteraction("card-elements", "row-\(hole)-save-\(attempt)", control: save,
                        gesture: "tap", expected: "screen=scorecard;hole=1;scored=1",
                        action: { save.tap() },
                        success: { _ in self.waitForFragment("screen=scorecard;")
                            && self.stateValue("hole") == 1 && self.stateValue("scored") == 1 })
                }
            }
        }
        for attempt in 1...5 {
            try launch("audit-phone-18", modelScreen: "finishing")
            try capture("finish-elements", "summary-\(attempt)", input: "injected-screen-production-controls")
            let abandon = button("放弃本场")
            guard try reach(abandon, flow: "finish-elements", step: "abandon-\(attempt)") else { continue }
            _ = try recordInteraction("finish-elements", "abandon-\(attempt)", control: abandon, gesture: "tap",
                expected: "screen=abandonConfirmation;", action: { abandon.tap() },
                success: { _ in self.waitForFragment("screen=abandonConfirmation;") })
            try capture("finish-elements", "confirmation-\(attempt)")
            let back = button("返回")
            if back.exists {
                _ = try recordInteraction("finish-elements", "cancel-\(attempt)", control: back,
                    gesture: "tap", expected: "screen=finishing;round=true;",
                    action: { back.tap() },
                    success: { _ in self.waitForFragment("screen=finishing;")
                        && self.stateLabel().contains("round=true;") })
            }
        }
        for attempt in 1...5 {
            try launch("audit-turn")
            try capture("turn-elements", "root-\(attempt)", input: "injected-turn-production-controls")
            for identifier in ["watch-turn-half-front", "watch-turn-half-back", "watch-turn-stop-after-nine"] {
                let target = element(identifier)
                guard try reach(target, flow: "turn-elements", step: "\(identifier)-\(attempt)") else { continue }
                _ = try recordInteraction("turn-elements", "\(identifier)-\(attempt)", control: target,
                    gesture: "tap", expected: "choice selected", action: { target.tap() },
                    success: { _ in String(describing: target.value ?? "") == "已选择" })
            }
            let back = button("返回第 9 洞")
            if back.exists, try reach(back, flow: "turn-elements", step: "back-\(attempt)") {
                _ = try recordInteraction("turn-elements", "back-\(attempt)", control: back,
                    gesture: "tap", expected: "hole=9;screen=home;", action: { back.tap() },
                    success: { _ in self.waitForFragment("screen=home;") && self.stateValue("hole") == 9 })
            }
        }
    }

    /// Do not spend the four-second undo window capturing/reading a complete tree. Record the
    /// first pointer tap and undo immediately, then attach evidence after the state transition.
    func test17FirstTryManualShotAndUndo() throws {
        for attempt in 1...5 {
            try launch("audit-phone-18")
            let record = element("watch-hole-record-shot")
            let metrics = controlMetrics(record, role: "manual-record")
            let frame = record.frame
            let before = stateLabel()
            app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(
                dx: frame.midX + (attempt.isMultiple(of: 2) ? 8 : 0), dy: frame.midY)).tap()
            let afterRecord = stateLabel()
            var undone = false
            var undoFrame: [Double] = []
            let undo = element("watch-shot-undo")
            if afterRecord.contains("pending=true;"), undo.exists {
                let frame = undo.frame
                undoFrame = [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)]
                app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: frame.midX, dy: frame.midY)).tap()
                undone = waitForValue("shots", 0) && stateLabel().contains("pending=false;")
            }
            try writeAuditJSON(["kind": "first-try-shot", "face": face, "attempt": attempt,
                "control": metrics, "gesture": attempt.isMultiple(of: 2) ? "tap-8pt-off-centre" : "tap-centre",
                "before": before, "afterRecord": afterRecord, "afterUndo": stateLabel(),
                "recordSucceeded": afterRecord.contains("pending=true;"),
                "undoSucceeded": undone, "undoFramePt": undoFrame,
                "capturedBeforeUndo": false, "realWatchProven": false],
                stem: "first-try--manual--\(attempt)")
            try capture("first-try-shots", "attempt-\(attempt)", collectControls: false)
        }
        // Product behavior at the PR's new source boundary. Only input GPS facts are injected:
        // live shotLocation is nil for a 20 s sample, so acceptance must come from latestWatchFix.
        // One trial per state is supplemental evidence, never a five-trial success claim.
        let cases: [(name: String, range: String, age: Int?, speed: Double?, shouldRecord: Bool)] = [
            ("older-walking", "fresh", 20, 0, true),
            ("older-cart", "fresh", 20, 6, false),
            ("expired", "fresh", 31, 0, false),
            ("missing", "none", nil, nil, false),
        ]
        for sample in cases {
            try launch("audit-phone-18", range: sample.range,
                       fixAgeSeconds: sample.age, fixSpeedMps: sample.speed)
            let record = element("watch-hole-record-shot")
            let frame = record.frame
            let before = stateLabel()
            app.coordinate(withNormalizedOffset: .zero)
                .withOffset(CGVector(dx: frame.midX, dy: frame.midY)).tap()
            // Capture transient visual feedback before state/tree enumeration. A simulator
            // screenshot does not prove the physical haptic; absence after this tool's latency
            // does not by itself prove the short-lived product message was never shown.
            let stem = "shot-origin--\(sample.name)-after-tap"
            let screenshot = app.screenshot()
            let visual = XCTAttachment(screenshot: screenshot)
            visual.name = stem
            visual.lifetime = .keepAlways
            add(visual)
            let screenshotFile = output.appendingPathComponent(stem + ".png")
            try screenshot.pngRepresentation.write(to: screenshotFile, options: .atomic)
            let after = stateLabel()
            let recorded = after.contains("pending=true;") || (stateValue("shots", in: after) ?? 0) > 0
            let feedback = element("watch-hole-record-shot-needs-gps")
            let feedbackSeen = feedback.exists
            if after.contains("pending=true;"), element("watch-shot-undo").exists {
                element("watch-shot-undo").tap()
            }
            try writeAuditJSON(["kind": "shot-origin-boundary", "face": face,
                "case": sample.name, "inputAgeSeconds": sample.age.map { $0 as Any } ?? NSNull(),
                "inputSpeedMps": sample.speed.map { $0 as Any } ?? NSNull(), "range": sample.range,
                "before": before, "after": after, "recorded": recorded,
                "expectedRecord": sample.shouldRecord, "success": recorded == sample.shouldRecord,
                "transientGPSMessageSeen": feedbackSeen, "physicalHapticProven": false],
                stem: "shot-origin--\(sample.name)")
            XCTAssertEqual(recorded, sample.shouldRecord, "\(sample.name): \(after)")
        }
    }

    /// #417 / 6117411661. Explicit coordinates plus native dispatcher and action receipts separate
    /// an XCTest coordinate problem from interception, recognizer competition and GPS/model gating.
    /// No injected pending, new gesture recognizer or product hit-area/timer change. Trace-off
    /// centre trials check that observing the dispatcher has not repaired the original failure.
    func test19NativeInputDispatchAndControlCoordinates() throws {
        let railOffsets: [CGFloat] = face == "49mm" ? [0, -8, 8, -16, 16] : [0]
        for identifier in ["watch-hole-menu", "watch-hole-record-shot"] {
            let controlName = identifier == "watch-hole-menu" ? "menu" : "shot"
            let cases = railOffsets.map { (offset: $0, traced: true) } + [(offset: CGFloat(0), traced: false)]
            for (number, sample) in cases.enumerated() {
                let trial = "rail-\(controlName)-\(number + 1)-\(sample.traced ? "trace-on" : "trace-off")"
                try launch("audit-phone-18", inputTraceTrial: trial, observeRawInput: sample.traced)
                let control = element(identifier)
                XCTAssertTrue(control.waitForExistence(timeout: 8))
                let appFrame = app.frame
                let frame = control.frame
                let metrics = controlMetrics(control, role: "root-input-probe")
                let point = CGPoint(x: frame.midX, y: frame.midY + sample.offset)
                let local = CGPoint(x: point.x - appFrame.minX, y: point.y - appFrame.minY)
                let before = stateLabel()
                if number == 0 { try capture("input-probe", trial + "-before", collectControls: false) }
                app.coordinate(withNormalizedOffset: .zero)
                    .withOffset(CGVector(dx: local.x, dy: local.y)).tap()
                let after = stateLabel()
                let succeeded = identifier == "watch-hole-menu"
                    ? after.contains("screen=menu;")
                    : (after.contains("pending=true;") || (stateValue("shots", in: after) ?? 0) > 0)
                try writeAuditJSON([
                    "kind": "explicit-input-probe", "face": face, "trial": trial,
                    "control": identifier, "metrics": metrics, "verticalOffsetPt": Double(sample.offset),
                    "appFramePt": [Double(appFrame.minX), Double(appFrame.minY), Double(appFrame.width), Double(appFrame.height)],
                    "expectedWindowPointPt": [Double(point.x), Double(point.y)],
                    "requestedAppOffsetPt": [Double(local.x), Double(local.y)],
                    "pointInsideAXFrame": frame.contains(point), "before": before, "after": after,
                    "observedTransition": succeeded, "rawTraceRequested": sample.traced,
                    "rawTraceFile": sample.traced ? "input-events--\(trial).json" : "none",
                    "inputEvidence": "actual coordinate tap; raw arrival/action must be adjudicated from separate trace",
                    "physicalWatchProven": false, "uiFeedbackMs": NSNull(),
                ], stem: "input-probe--\(trial)")
                try capture("input-probe", trial + "-after", collectControls: false)
            }
        }

        let hazardOffsets: [(x: CGFloat, y: CGFloat)] = [(0, 0), (0, -8), (0, 8), (-8, 0), (8, 0)]
        let hazardCases = hazardOffsets.map { (offset: $0, traced: true) }
            + [(offset: (x: CGFloat(0), y: CGFloat(0)), traced: false)]
        for (number, sample) in hazardCases.enumerated() {
            let trial = "hazard-\(number + 1)-\(sample.traced ? "trace-on" : "trace-off")"
            try launch("audit-phone-18", page: 1, zoom: 2,
                       inputTraceTrial: trial, observeRawInput: sample.traced)
            let control = element("watch-hazard-next")
            XCTAssertTrue(control.waitForExistence(timeout: 8))
            let viewport = element("watch-audit-viewport-hazard")
            let beforePage = element("watch-hole-page-current").label
            let beforeViewport = viewport.label
            XCTAssertEqual(beforePage, "障碍")
            XCTAssertTrue(beforeViewport.contains("zoom=2."))
            let appFrame = app.frame
            let frame = control.frame
            let metrics = controlMetrics(control, role: "hazard-input-probe")
            let point = CGPoint(x: frame.midX + sample.offset.x, y: frame.midY + sample.offset.y)
            let local = CGPoint(x: point.x - appFrame.minX, y: point.y - appFrame.minY)
            let beforeLabel = control.label
            if number == 0 { try capture("input-probe", trial + "-before", collectControls: false) }
            app.coordinate(withNormalizedOffset: .zero)
                .withOffset(CGVector(dx: local.x, dy: local.y)).tap()
            let afterPage = element("watch-hole-page-current").label
            let afterLabel = control.exists ? control.label : "control-absent"
            let afterViewport = viewport.exists ? viewport.label : "viewport-absent"
            try writeAuditJSON([
                "kind": "explicit-input-probe", "face": face, "trial": trial,
                "control": "watch-hazard-next", "metrics": metrics,
                "offsetPt": [Double(sample.offset.x), Double(sample.offset.y)],
                "appFramePt": [Double(appFrame.minX), Double(appFrame.minY), Double(appFrame.width), Double(appFrame.height)],
                "expectedWindowPointPt": [Double(point.x), Double(point.y)],
                "requestedAppOffsetPt": [Double(local.x), Double(local.y)],
                "pointInsideAXFrame": frame.contains(point), "beforePage": beforePage, "afterPage": afterPage,
                "beforeLabel": beforeLabel, "afterLabel": afterLabel,
                "beforeViewport": beforeViewport, "afterViewport": afterViewport,
                "observedTransition": afterPage == "障碍" && afterLabel != beforeLabel
                    && afterLabel != "control-absent" && beforeViewport == afterViewport,
                "rawTraceRequested": sample.traced,
                "rawTraceFile": sample.traced ? "input-events--\(trial).json" : "none",
                "inputEvidence": "actual explicit coordinate tap; fresh hazard2x; no reframing",
                "physicalWatchProven": false, "uiFeedbackMs": NSNull(),
            ], stem: "input-probe--\(trial)")
            try capture("input-probe", trial + "-after", collectControls: false)
        }
    }

    /// Cover the disabled setting through the production view, rather than inferring its visible
    /// explanation from an accessibility hint or treating supported-fixture taps as this coverage.
    func test20UnsupportedAutoShotVisibleFeedback() throws {
        for attempt in 1...5 {
            try launch("audit-phone-18", supportsAutoShot: false, modelScreen: "settings")
            let toggle = element("自动记杆")
            XCTAssertTrue(toggle.waitForExistence(timeout: 8))
            // A disabled row need not be semantically hittable. Scroll by measured visibility,
            // then deliver the actual finger coordinate; do not skip the very state being tested.
            for _ in 0..<8 {
                let row = toggle.frame
                let visible = app.frame.insetBy(dx: 8, dy: 8)
                if visible.contains(CGPoint(x: row.midX, y: row.midY)) { break }
                let scroll = app.scrollViews.firstMatch
                scrollContainer(scroll.exists ? scroll : app, towardTop: row.midY > visible.midY)
            }
            let frame = toggle.frame
            XCTAssertTrue(app.frame.insetBy(dx: 8, dy: 8).contains(CGPoint(x: frame.midX, y: frame.midY)))
            let metrics = controlMetrics(toggle, role: "unsupported-setting")
            let before = stateLabel()
            let valueBefore = String(describing: toggle.value ?? "")
            let enabled = toggle.isEnabled
            let visibleReasonBefore = app.staticTexts["本机不支持"].exists
            if attempt == 1 {
                try capture("unsupported-auto", "01-before", input: "injected-capability-production-setting")
            }
            let appFrame = app.frame
            app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(
                dx: frame.midX + (attempt.isMultiple(of: 2) ? 8 : 0) - appFrame.minX,
                dy: frame.midY - appFrame.minY)).tap()
            let after = stateLabel()
            let valueAfter = String(describing: toggle.value ?? "")
            try writeAuditJSON([
                "kind": "unsupported-setting-input", "face": face, "attempt": attempt,
                "capability": "synthetic unsupported fixture; not simulator hardware inference",
                "metrics": metrics, "enabledBefore": enabled,
                "before": before, "after": after, "valueBefore": valueBefore, "valueAfter": valueAfter,
                "remainedOff": after.contains("auto=false;") && valueBefore == valueAfter,
                "staticReasonBefore": visibleReasonBefore,
                "staticReasonAfter": app.staticTexts["本机不支持"].exists,
                "gesture": attempt.isMultiple(of: 2) ? "tap-8pt-off-centre" : "tap-centre",
                "physicalHapticProven": false, "uiFeedbackMs": NSNull(),
            ], stem: "unsupported-auto--tap-\(attempt)")
            try capture("unsupported-auto", "after-\(attempt)", collectControls: false)
        }
    }

    /// #417 / 6119731901: measure the temporary full-width row's cutoff to one native pixel (0.5pt).
    /// Every point is a fresh launch. Then check both adjacent rows across five horizontal points
    /// and repeat their centres five times without tracing; no product acceptance is implied.
    func test23SafeAreaGeometryAndButtonCutoff() throws {
        try launch("audit-phone-18")
        let appFrame = app.frame
        let height = appFrame.height
        var sequence = 0
        let rootOnly = ProcessInfo.processInfo.environment["UITEST_AUDIT_SAFE_AREA_ROOT_ONLY"] == "1"
        let scopes = rootOnly ? ["root"] : ["root", "hazard"]
        for scope in scopes {
            func probe(_ y: CGFloat, x: CGFloat, stage: String, traced: Bool = true) throws -> Bool {
                sequence += 1
                let trial = "safe-area-\(scope)-\(stage)-\(sequence)"
                try launch("audit-phone-18", page: scope == "hazard" ? 1 : 0,
                           zoom: scope == "hazard" ? 2 : 1,
                           inputTraceTrial: trial, observeRawInput: traced,
                           safeAreaScope: scope, safeAreaY: y)
                let counter = element("watch-safe-area-probe-count")
                XCTAssertTrue(counter.waitForExistence(timeout: 8))
                XCTAssertEqual(counter.label, "count=0;")
                let row = element("watch-safe-area-probe-row")
                let rowFrame = try row.snapshot().frame
                XCTAssertEqual(rowFrame.midY, y, accuracy: 0.01)
                let before = stateLabel()
                app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(
                    dx: x - appFrame.minX, dy: y - appFrame.minY)).tap()
                let countAfter = counter.exists ? counter.label : "control-absent-after-tap"
                let fired = countAfter == "count=1;"
                try writeAuditJSON([
                    "kind": "safe-area-boundary-point", "face": face, "scope": scope, "stage": stage,
                    "trial": trial, "requestedWindowPointPt": [Double(x), Double(y)],
                    "rowFramePt": [Double(rowFrame.minX), Double(rowFrame.minY), Double(rowFrame.width), Double(rowFrame.height)],
                    "appFramePt": [Double(appFrame.minX), Double(appFrame.minY), Double(appFrame.width), Double(appFrame.height)],
                    "rowActionFired": fired, "countAfter": countAfter, "before": before, "after": stateLabel(),
                    "rawTraceRequested": traced, "rawTraceFile": traced ? "input-events--\(trial).json" : "none",
                    "geometryFile": "safe-area-geometry--\(trial).json",
                    "temporaryFullWidthButton": true, "buttonHeightPt": 2, "resolutionPt": 0.5,
                    "productionControlAcceptance": false,
                ], stem: "safe-area-point--\(trial)")
                if stage == "bracket-low" || stage == "bracket-high" || stage == "row-centre" {
                    try capture("safe-area", trial + (fired ? "-fired" : "-ignored"), collectControls: false)
                }
                return fired
            }
            var low = appFrame.minY + height - 72
            var high = appFrame.maxY - 1
            var lowerWorks = try probe(low, x: appFrame.midX, stage: "bracket-low")
            let upperWorks = try probe(high, x: appFrame.midX, stage: "bracket-high")
            // Keep the original cancelled lower trial. A launch-time cancellation must not be
            // relabelled as a hit boundary: require five fresh trace-off successes before searching.
            if !lowerWorks && !upperWorks {
                var retries: [Bool] = []
                for attempt in 1...5 {
                    retries.append(try probe(low, x: appFrame.midX,
                                             stage: "bracket-low-off-\(attempt)", traced: false))
                }
                lowerWorks = retries.allSatisfy { $0 }
                try writeAuditJSON([
                    "kind": "safe-area-bracket-retry", "face": face, "scope": scope,
                    "lowerY": Double(low), "initialLowerWorks": false,
                    "traceOffRetries": retries, "lowerWorks": lowerWorks,
                    "productionControlAcceptance": false,
                ], stem: "safe-area-bracket-retry--\(scope)")
            }
            if !lowerWorks || upperWorks {
                try writeAuditJSON(["kind": "safe-area-boundary-bracket", "face": face, "scope": scope,
                                    "lowerY": Double(low), "upperY": Double(high),
                                    "lowerWorks": lowerWorks, "upperWorks": upperWorks,
                                    "boundaryLocated": false], stem: "safe-area-bracket--\(scope)")
                continue
            }
            while high - low > 0.5 {
                let mid = ((low + high) / 2 * 2).rounded(.down) / 2
                if try probe(mid, x: appFrame.midX, stage: "binary", traced: false) { low = mid } else { high = mid }
            }
            let xs = [appFrame.minX + 20, appFrame.minX + appFrame.width * 0.25,
                      appFrame.midX, appFrame.minX + appFrame.width * 0.75, appFrame.maxX - 20]
            var rows: [[String: Any]] = []
            for y in [low, high] {
                for (index, x) in xs.enumerated() {
                    let fired = try probe(y, x: x, stage: index == 2 ? "row-centre" : "row-span")
                    rows.append(["x": Double(x), "y": Double(y), "fired": fired, "traced": true])
                }
                for attempt in 1...5 {
                    let fired = try probe(y, x: appFrame.midX, stage: "centre-off-\(attempt)", traced: false)
                    rows.append(["x": Double(appFrame.midX), "y": Double(y), "fired": fired, "traced": false])
                }
            }
            try writeAuditJSON([
                "kind": "safe-area-boundary-summary", "face": face, "scope": scope,
                "lastWorkingY": Double(low), "firstFailingY": Double(high), "resolutionPt": 0.5,
                "rows": rows, "freshLaunchPerPoint": true, "temporaryButtonHeightPt": 2,
                "binaryTraceEnabled": false,
                "productionControlAcceptance": false, "physicalWatchProven": false,
            ], stem: "safe-area-cutoff--\(scope)")
        }
    }

    /// Five untraced fresh-launch drags per centre/edge path, then one separate traced diagnostic
    /// of that path. Keep real pointer arrival and drag/tap callbacks separate from value success.
    func test22TotalBandCentreAndEdgeInputDispatch() throws {
        let cases: [(name: String, anchor: String, distance: CGFloat, initial: Int)] = [
            ("centre-left-20", "centre", 20, 10),
            ("centre-left-28", "centre", 28, 10),
            ("right-edge-left-20", "right", 20, 10),
            ("right-edge-left-28", "right", 28, 10),
            ("left-edge-right-28", "left", -28, 10),
            ("right-edge-left-60", "right", 60, 10),
            ("right-edge-full", "right", 0, 4),
        ]
        for sample in cases {
            for attempt in 1...6 {
                let traced = attempt == 6
                let trial = "band-\(sample.name)-\(traced ? "trace" : String(attempt))"
                try launch("audit-phone-18", modelScreen: "scoring", initialScore: sample.initial,
                           initialPutts: 0, initialPenalty: 0,
                           inputTraceTrial: traced ? trial : nil, observeRawInput: traced)
                let before = stateValue("score") ?? -1
                XCTAssertEqual(before, sample.initial)
                let frame = try element("watch-score-band").snapshot().frame
                let appFrame = app.frame
                let distance = sample.distance == 0 ? frame.width - 16 : sample.distance
                let startX = sample.anchor == "right" ? frame.maxX - 8
                    : (sample.anchor == "left" ? frame.minX + 8 : frame.midX)
                let endX = startX - distance
                XCTAssertTrue(frame.contains(CGPoint(x: startX, y: frame.midY)))
                XCTAssertTrue(frame.contains(CGPoint(x: endX, y: frame.midY)))
                if attempt == 1 {
                    try capture("band-probe", sample.name + "-before", collectControls: false)
                }
                let expected = min(15, max(1, before + Int((distance / 28).rounded())))
                let origin = app.coordinate(withNormalizedOffset: .zero)
                origin.withOffset(CGVector(dx: startX - appFrame.minX, dy: frame.midY - appFrame.minY))
                    .press(forDuration: 0.05, thenDragTo: origin.withOffset(CGVector(
                        dx: endX - appFrame.minX, dy: frame.midY - appFrame.minY)))
                _ = waitForValue("score", expected)
                let after = stateValue("score") ?? -1
                try writeAuditJSON([
                    "kind": "total-band-input-probe", "face": face, "case": sample.name,
                    "attempt": attempt, "before": before, "after": after, "expected": expected,
                    "attemptValid": before == sample.initial, "valueCorrect": after == expected,
                    "rawTraceRequested": traced, "rateGroup": traced ? "single-diagnostic" : "five-untraced-first-drags",
                    "startPt": [Double(startX), Double(frame.midY)],
                    "endPt": [Double(endX), Double(frame.midY)], "travelPt": Double(distance),
                    "framePt": [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)],
                    "rawTraceFile": traced ? "input-events--\(trial).json" : "none",
                    "gesture": "actual coordinate press0.05s then horizontal drag",
                    "physicalCrownProven": false, "uiFeedbackMs": NSNull(),
                ], stem: "band-probe--\(trial)")
                try capture("band-probe", trial + "-after", collectControls: false)
            }
        }
    }

    /// Fill the previously declared total-band gap: every valid start 1...15 to every supported
    /// requested total 10...15, with a new production draft for each pair. Values 16...20 have
    /// already exposed the product cap; retain a separate fresh boundary attempt for each value.
    /// No callbacks, pending state or held-open timers are injected to make a gesture succeed.
    func test21TotalBandFreshStartMatrixAndSave() throws {
        var pairs: [(start: Int, target: Int)] = []
        for start in 1...15 {
            for target in 10...15 { pairs.append((start, target)) }
        }
        for target in 16...20 { pairs.append((15, target)) }

        for pair in pairs {
            try launch("audit-phone-18", modelScreen: "scoring", initialScore: pair.start,
                       initialPutts: 0, initialPenalty: 0)
            XCTAssertTrue(waitForFragment("screen=scoring;"))
            let before = stateValue("score") ?? -1
            XCTAssertEqual(before, pair.start, "the seeded start must be observed before dispatch")
            let band = element("watch-score-band")
            let frame = try band.snapshot().frame
            let appFrame = app.frame
            let origin = app.coordinate(withNormalizedOffset: .zero)
            // Rounded watch corners are outside this central band. Keep both pointer endpoints
            // inside its visible width, 8 pt from either edge. Production rounds at 28 pt/step,
            // so a 136 pt sweep on 41 mm is five steps, not four (flooring would bias the test).
            let maxTravel = frame.width - 16
            let maxSteps = Int((maxTravel / 28).rounded())
            XCTAssertGreaterThan(maxSteps, 0)
            var inputs: [[String: Any]] = []
            while stateValue("score") != pair.target && inputs.count < 3 {
                let now = stateValue("score") ?? -1
                let delta = pair.target - now
                let steps = min(maxSteps, max(-maxSteps, delta))
                let travel = min(CGFloat(abs(steps)) * 28, maxTravel)
                let startX = steps > 0 ? frame.maxX - 8 : frame.minX + 8
                let endX = startX + (steps > 0 ? -travel : travel)
                origin.withOffset(CGVector(dx: startX - appFrame.minX, dy: frame.midY - appFrame.minY))
                    .press(forDuration: 0.05, thenDragTo: origin.withOffset(CGVector(
                        dx: endX - appFrame.minX, dy: frame.midY - appFrame.minY)))
                // This is an observation wait, not a direct value assignment. A clamped or
                // swallowed gesture remains visible in the raw before/after sequence.
                let expected = min(15, max(1, now + steps))
                _ = waitForValue("score", expected)
                inputs.append([
                    "before": now, "after": stateValue("score") ?? -1,
                    "requestedSteps": steps, "travelPt": Double(travel),
                    "startPt": [Double(startX), Double(frame.midY)],
                    "endPt": [Double(endX), Double(frame.midY)],
                ])
            }
            let after = stateValue("score") ?? -1
            let reached = after == pair.target
            if pair.target == 10 || pair.target == 15 || !reached {
                try capture("total-matrix", "start-\(pair.start)-target-\(pair.target)",
                            input: "seeded-start-real-band-gestures", collectControls: false)
            }
            var saveAfter = "not-at-requested-value"
            var saveSucceeded = false
            if reached {
                let save = element("watch-score-save")
                let saveFrame = try save.snapshot().frame
                origin.withOffset(CGVector(dx: saveFrame.midX - appFrame.minX,
                                           dy: saveFrame.midY - appFrame.minY)).tap()
                _ = waitForValue("scored", 1)
                saveAfter = stateLabel()
                saveSucceeded = stateValue("scored", in: saveAfter) == 1
                    && stateValue("strokes", in: saveAfter) == pair.target
                if !saveSucceeded {
                    try capture("total-matrix", "start-\(pair.start)-target-\(pair.target)-save-failed",
                                collectControls: false)
                }
            }
            try writeAuditJSON([
                "kind": "fresh-total-reachability", "face": face, "screen": "本洞成绩",
                "start": pair.start, "before": before, "requested": pair.target,
                "attemptValid": before == pair.start, "supportedTarget": pair.target <= 15,
                "after": after, "adjustmentGestures": inputs.count,
                "withinThree": reached && inputs.count <= 3, "inputs": inputs,
                "saveAttempted": reached, "saveAfter": saveAfter, "saveSucceeded": saveSucceeded,
                "saveGestures": reached ? 1 : 0,
                "framePt": [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)],
                "input": "fresh seeded draft per pair; real coordinates; no model callback injection",
                "repetitionsPerPair": 1, "physicalCrownProven": false,
                "uiFeedbackMs": NSNull(),
            ], stem: "total-matrix--\(pair.start)--\(pair.target)")
        }
    }
}
