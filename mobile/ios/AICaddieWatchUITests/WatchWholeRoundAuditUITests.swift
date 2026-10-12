import XCTest

/// Opt-in #417 element harness applied only to exact #422 DEBUG prototypes.
/// Five fresh launches at centre and five at centre+8pt, not ten taps in one launch.
/// Collection succeeds even when a measured interaction fails; receipts carry the result.
final class WatchWholeRoundAuditUITests: XCTestCase {
    private let app = XCUIApplication()
    private var sequence = 0
    private var face: String { ProcessInfo.processInfo.environment["UITEST_AUDIT_FACE"] ?? "unknown" }
    private var prototypeRecheck: Bool { ProcessInfo.processInfo.environment["UITEST_PROTO_RECHECK"] == "1" }
    private var prototypeClockRecheck: Bool { ProcessInfo.processInfo.environment["UITEST_PROTO_CLOCK_RECHECK"] == "1" }
    private var output: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("watch-audit", isDirectory: true)
    }

    struct Spec {
        let route: String
        let key: String
        let target: String
        let prepare: [String]
        let precondition: [String: String]
        let expected: [String: String]
        let placeholder: Bool
        let callback: String?
        init(_ route: String, _ key: String, _ target: String, prepare: [String] = [],
             precondition: [String: String] = [:], expected: [String: String] = [:],
             placeholder: Bool = false, callback: String? = nil) {
            self.route = route; self.key = key; self.target = target; self.prepare = prepare
            self.precondition = precondition; self.expected = expected
            self.placeholder = placeholder; self.callback = callback
        }
    }

    override func setUpWithError() throws {
        guard ProcessInfo.processInfo.environment["UITEST_WATCH_FULL_AUDIT"] == "1" else {
            throw XCTSkip("Five-face prototype audit requires its dedicated dispatch")
        }
        continueAfterFailure = false
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        if let run = testRun, run.failureCount > 0 {
            try screenshot("proto-failure", name.replacingOccurrences(of: "/", with: "_"))
            print(app.debugDescription)
        }
        app.terminate()
    }

    private func launch(_ route: String, trial: String, traced: Bool = false,
                        scope: String = "", y: CGFloat? = nil) throws {
        app.terminate()
        app.launchArguments = ["-uitest-screen", route]
        app.launchEnvironment = ["UITEST_PROTO_AUDIT": "1", "UITEST_AUDIT_INPUT_TRIAL": trial,
                                 "UITEST_AUDIT_INPUT_TRACE": traced ? "1" : "0",
                                 "UITEST_PROTO_BOUNDARY_SCOPE": scope]
        app.launchEnvironment["UITEST_PROTO_BOUNDARY_Y"] = y.map { String(Double($0)) }
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 20))
        XCTAssertTrue(element("proto-audit-state").waitForExistence(timeout: 10))
    }

    /// Label queries disambiguate the stack's six distinct +/- buttons without adding IDs to it.
    private func element(_ identity: String) -> XCUIElement {
        if identity.hasPrefix("label:") {
            return app.buttons.matching(NSPredicate(format: "label == %@", String(identity.dropFirst(6)))).firstMatch
        }
        return app.descendants(matching: .any).matching(identifier: identity).firstMatch
    }

    private func state() -> String { element("proto-audit-state").label }
    private func matches(_ value: String, _ fields: [String: String]) -> Bool {
        fields.allSatisfy { value.contains("\($0.key)=\($0.value);") }
    }
    private func frame(_ rect: CGRect) -> [Double] {
        [Double(rect.minX), Double(rect.minY), Double(rect.width), Double(rect.height)]
    }
    private func metric(_ control: XCUIElement) -> [String: Any] {
        guard let snap = try? control.snapshot() else { return ["exists": false] }
        return metric(snap)
    }
    private func metric(_ snap: any XCUIElementSnapshot) -> [String: Any] {
        let box = snap.frame
        guard [box.minX, box.minY, box.width, box.height].allSatisfy({ $0.isFinite }) else {
            return ["exists": true, "identifier": snap.identifier, "label": snap.label, "finiteFrame": false]
        }
        return ["exists": true, "identifier": snap.identifier, "label": snap.label,
                "value": (snap.value as? String) ?? "", "elementType": snap.elementType.rawValue,
                "framePt": frame(box), "minDimensionPt": Double(min(box.width, box.height)),
                "under44Pt": box.width < 44 || box.height < 44,
                "frameEvidence": "AX frame; does not prove padded hit bounds"]
    }
    private func write(_ value: [String: Any], _ stem: String) throws {
        sequence += 1
        let path = output.appendingPathComponent(String(format: "%04d-%@.json", sequence, stem))
        try JSONSerialization.data(withJSONObject: value, options: .sortedKeys).write(to: path, options: .atomic)
    }
    private func screenshot(_ flow: String, _ step: String, inventory: Bool = false) throws {
        let stem = "\(flow)--\(step)"
        let shot = XCUIScreen.main.screenshot()
        try shot.pngRepresentation.write(to: output.appendingPathComponent(stem + ".png"), options: .atomic)
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = stem; attachment.lifetime = .keepAlways; add(attachment)
        var controls: [[String: Any]] = []
        if inventory {
            // Scrolling changes live query indices (38251740277 failed at index21 on every face).
            // Capture the native tree once; every inventory entry belongs to that same snapshot.
            func descendants(_ root: any XCUIElementSnapshot) -> [any XCUIElementSnapshot] {
                root.children.flatMap { [$0] + descendants($0) }
            }
            let tree = descendants(try app.snapshot())
            controls = tree.filter {
                $0.identifier.hasPrefix("proto-") && $0.identifier != "proto-audit-state"
            }.map(metric)
            controls += tree.filter {
                $0.elementType == .button && $0.identifier.isEmpty
                    && ($0.label.hasSuffix("加一") || $0.label.hasSuffix("减一"))
            }.map(metric)
        }
        try write(["kind": "prototype-screen", "face": face, "flow": flow, "step": step,
                   "state": state(), "screenFramePt": frame(app.frame),
                   "screenshotPixels": [shot.image.cgImage?.width ?? 0, shot.image.cgImage?.height ?? 0],
                   "inventory": controls, "sourceFontsRequireCodeCrossCheck": true,
                   "physicalWatchProven": false], "proto-screen--\(stem)")
    }

    private func tapCoordinate(_ control: XCUIElement, offset: CGFloat = 0) throws -> CGPoint {
        let box = try control.snapshot().frame
        let point = CGPoint(x: box.midX + offset, y: box.midY)
        let origin = app.frame.origin
        app.coordinate(withNormalizedOffset: .zero)
            .withOffset(CGVector(dx: point.x - origin.x, dy: point.y - origin.y)).tap()
        return point
    }

    private func canvasMetric(_ key: String) -> CGFloat? {
        element("proto-audit-canvas-geometry").label.split(separator: ";")
            .first { $0.hasPrefix("\(key)=") }
            .flatMap { Double($0.dropFirst(key.count + 1)) }
            .map { CGFloat($0) }
    }

    private func prepare(_ actions: [String]) throws -> Bool {
        for action in actions {
            if action.hasPrefix("menu-reveal:") {
                let target = element(String(action.dropFirst("menu-reveal:".count)))
                guard let bottom = canvasMetric("bottom"), let top = canvasMetric("top") else { return false }
                var visible = false
                for step in 0...3 {
                    if target.exists {
                        let rect = try target.snapshot().frame
                        // Keep the whole row below the initial clock gap and above the measured
                        // interactive bottom; an existing off-screen AX node isn't a valid tap.
                        visible = rect.minY >= top - 0.01 && rect.maxY <= bottom + 0.01
                        if visible { break }
                    }
                    if step < 3 { app.swipeUp() }
                }
                guard visible else { return false }
            } else {
                let control = element(action)
                guard control.exists else { return false }
                _ = try tapCoordinate(control)
            }
        }
        return true
    }

    private func run(_ specs: [Spec]) throws {
        for spec in specs {
            for offset in [CGFloat(0), CGFloat(8)] {
                for attempt in 1...5 {
                    let trial = "\(spec.key)-x\(Int(offset))-\(attempt)"
                    try launch(spec.route, trial: trial, traced: spec.placeholder && spec.callback != nil)
                    var preparationValid = try prepare(spec.prepare)
                    let before = state()
                    preparationValid = preparationValid && matches(before, spec.precondition)
                    let control = element(spec.target)
                    let exists = control.exists
                    let details = exists ? metric(control) : ["exists": false]
                    if offset == 0, attempt == 1 {
                        try screenshot("proto-baseline", spec.key, inventory: true)
                    }
                    if !preparationValid || !exists {
                        try write(["kind": "prototype-tap", "face": face, "trial": trial, "route": spec.route,
                                   "key": spec.key, "control": details, "offsetPt": Double(offset),
                                   "attempt": attempt, "before": before, "after": before,
                                   "attemptValid": false, "success": NSNull(),
                                   "reason": !exists ? "not rendered" : "real-input preparation did not establish required state or visible row",
                                   "placeholder": spec.placeholder], "proto-tap--\(trial)")
                        continue
                    }
                    let started = Date()
                    let point = try tapCoordinate(control, offset: offset)
                    let duration = Int(Date().timeIntervalSince(started) * 1_000)
                    let after = state()
                    let passed: Any = spec.placeholder ? NSNull() : matches(after, spec.expected)
                    try write(["kind": "prototype-tap", "face": face, "trial": trial, "route": spec.route,
                               "key": spec.key, "control": details, "offsetPt": Double(offset),
                               "requestedWindowPointPt": [Double(point.x), Double(point.y)], "attempt": attempt,
                               "before": before, "after": after, "expected": spec.expected,
                               "attemptValid": true, "success": passed, "freshLaunch": true,
                               "placeholder": spec.placeholder, "callbackExpected": spec.callback ?? "none",
                               "rawTraceEnabled": spec.placeholder && spec.callback != nil,
                               "traceFile": spec.placeholder && spec.callback != nil ? "input-events--\(trial).json" : "none",
                               "xctestActionMs": duration, "uiFeedbackMs": NSNull(),
                               "latencyEvidence": "XCTest synchronization included; not visible feedback latency"],
                              "proto-tap--\(trial)")
                    try screenshot("proto-taps", trial)
                }
            }
            // One independent raw-input diagnostic; do not mix it into the ten trace-off trials.
            if !spec.placeholder || spec.route == "proto-menu" {
                let trial = "\(spec.key)-diagnostic"
                try launch(spec.route, trial: trial, traced: true)
                let prepared = try prepare(spec.prepare)
                if prepared && element(spec.target).exists {
                    let before = state()
                    let point = try tapCoordinate(element(spec.target))
                    try write(["kind": "prototype-input-diagnostic", "face": face, "trial": trial,
                               "key": spec.key, "requestedWindowPointPt": [Double(point.x), Double(point.y)],
                               "before": before, "after": state(), "expected": spec.expected,
                               "traceFile": "input-events--\(trial).json", "includedInAcceptance": false],
                              "proto-diagnostic--\(trial)")
                }
            }
        }
    }

    func test01FaceAndAutoShotControls() throws {
        try run([
            Spec("proto-face", "face-plan", "proto-face-plan", expected: ["plan": "1", "club": "5i"]),
            Spec("proto-face", "face-record", "proto-face-record", expected: ["shots": "1"]),
            Spec("proto-face-autoshot", "auto-plan", "proto-face-plan", expected: ["plan": "1", "autoShot": "true"]),
        ])
        try launch("proto-face-autoshot", trial: "auto-hidden-control")
        try write(["kind": "prototype-visibility", "face": face, "route": "proto-face-autoshot",
                   "recordExists": element("proto-face-record").exists, "expectedRecordExists": false], "proto-auto-hidden")
        try screenshot("proto-route", "face-autoshot", inventory: true)
    }

    func test02RowScoreAndFairwayControls() throws {
        var specs: [Spec] = []
        for route in ["proto-score", "proto-score-par3"] {
            let key = route == "proto-score" ? "row" : "par3"
            let total = route == "proto-score" ? 5 : 3
            for field in ["total", "putts", "penalty"] {
                let prep = field == "putts" ? ["proto-score-total"] : []
                specs.append(Spec(route, "\(key)-select-\(field)", "proto-score-\(field)", prepare: prep,
                                  precondition: field == "putts" ? ["selected": "total"] : [:],
                                  expected: ["selected": field]))
            }
            specs.append(Spec(route, "\(key)-minus", "label:推杆减一",
                              expected: ["putts": "1", "total": "\(total - 1)"]))
            specs.append(Spec(route, "\(key)-plus", "label:推杆加一",
                              expected: ["putts": "3", "total": "\(total + 1)"]))
            specs.append(Spec(route, "\(key)-save", "proto-score-save", placeholder: true,
                              callback: "proto-score-save-placeholder"))
            if route == "proto-score" {
                specs.append(Spec(route, "row-fairway-open", "proto-score-fairway", expected: ["sheet": "true"]))
                for (index, side) in ["左", "中", "右"].enumerated() {
                    specs.append(Spec(route, "row-fairway-\(index)", "proto-score-fairway-\(side)",
                                      prepare: ["proto-score-fairway"], precondition: ["sheet": "true"],
                                      expected: ["sheet": "false", "fairway": side]))
                }
            }
        }
        try run(specs)
        try launch("proto-score-par3", trial: "par3-hidden-fairway")
        try write(["kind": "prototype-visibility", "face": face, "route": "proto-score-par3",
                   "fairwayExists": element("proto-score-fairway").exists, "expectedFairwayExists": false], "proto-par3-hidden")
        try screenshot("proto-route", "score-par3", inventory: true)
    }

    func test03StackScoreControls() throws {
        var specs: [Spec] = []
        let names = ["total": "总杆", "putts": "推杆", "penalty": "罚杆"]
        for field in ["total", "putts", "penalty"] {
            specs.append(Spec("proto-score-stack", "stack-select-\(field)", "proto-score-\(field)",
                              prepare: field == "putts" ? ["proto-score-total"] : [],
                              precondition: field == "putts" ? ["selected": "total"] : [:],
                              expected: ["selected": field]))
            for direction in ["减一", "加一"] {
                let increase = direction == "加一"
                let prep = field == "penalty" && !increase ? ["label:罚杆加一"] : []
                var values: [String: String] = ["selected": field]
                values["total"] = field == "penalty" && !increase ? "5" : (increase ? "6" : "4")
                if field == "putts" { values["putts"] = increase ? "3" : "1" }
                if field == "penalty" { values["penalty"] = increase ? "1" : "0" }
                specs.append(Spec("proto-score-stack", "stack-\(field)-\(increase ? "plus" : "minus")",
                                  "label:\(names[field]!)\(direction)", prepare: prep,
                                  precondition: prep.isEmpty ? [:] : ["penalty": "1", "total": "6"], expected: values))
            }
        }
        specs.append(Spec("proto-score-stack", "stack-fairway-open", "proto-score-fairway", expected: ["sheet": "true"]))
        specs.append(Spec("proto-score-stack", "stack-save", "proto-score-save", placeholder: true,
                          callback: "proto-score-save-placeholder"))
        try run(specs)
    }

    func test04TurnAndMenuControls() throws {
        var specs: [Spec] = prototypeRecheck ? [] : [
            Spec("proto-turn", "turn-continue", "proto-turn-continue", placeholder: true, callback: "proto-turn-continue"),
            Spec("proto-turn", "turn-change", "proto-turn-change", expected: ["all": "true"]),
            Spec("proto-turn", "turn-finish", "proto-turn-finish", placeholder: true, callback: "proto-turn-finish"),
        ]
        if !prototypeRecheck {
            for (index, option) in ["C 场", "A 场（再打一次）"].enumerated() {
                specs.append(Spec("proto-turn", "turn-option-\(index)", "proto-turn-\(option)",
                                  prepare: ["proto-turn-change"], precondition: ["all": "true"],
                                  expected: ["all": "false", "next": option]))
            }
        }
        for (index, title) in ["计分卡", "换洞", "本洞记录", "设置", "结束本场"].enumerated() {
            specs.append(Spec("proto-menu", "menu-row-\(index)", "proto-menu-\(title)",
                              prepare: ["menu-reveal:proto-menu-\(title)"], placeholder: true))
        }
        try run(specs)
        // Actual swipes can reveal omitted rows only if the prototype supports them.
        try launch("proto-menu", trial: "menu-scroll-reachability")
        for step in 1...3 {
            app.swipeUp()
            try screenshot("proto-menu-scroll", "\(step)", inventory: true)
        }
    }

    func test05SafeAreaCutoffAndCrownEvidenceBoundary() throws {
        // Genuine Crown rotation is not a public watch XCTest input. Preserve runner capability
        // listings; never call a binding injection, touch swipe or accessibility adjust a Crown.
        try launch("proto-score", trial: "crown-capability-boundary")
        try write(["kind": "prototype-crown-boundary", "face": face,
                   "requested": "real simulator Crown rotation changes selected field",
                   "executed": false, "reason": "No verified genuine Crown rotation mechanism available to this XCTest harness",
                   "bindingInjected": false, "touchSwipeSubstituted": false, "physicalCrownProven": false], "proto-crown-boundary")
        try screenshot("proto-route", "score-crown-boundary", inventory: true)
        guard face == "42mm" || face == "45mm" || prototypeRecheck || prototypeClockRecheck else {
            try write(["kind": "prototype-safe-area-reuse", "face": face,
                       "priorNativeRuns": ["38219857642", "38225977002"],
                       "note": "Original control trials retain current geometry/native diagnostics; no repeat cutoff search"], "proto-cutoff-prior")
            return
        }
        // Test the newly changed score hierarchy rather than infer its dispatch from the map.
        let boundaryRoute = prototypeClockRecheck ? "proto-score-stack" : "proto-face"
        try launch(boundaryRoute, trial: "boundary-window")
        let window = app.frame
        let interactiveBottom = try XCTUnwrap(canvasMetric("bottom"))
        let bottomInset = window.maxY - interactiveBottom
        var serial = 0
        for scope in ["root", "canvas"] {
            func probe(_ y: CGFloat, stage: String, traced: Bool = false) throws -> Bool {
                serial += 1
                let trial = "boundary-\(scope)-\(stage)-\(serial)"
                try launch(boundaryRoute, trial: trial, traced: traced, scope: scope, y: y)
                let row = element("proto-boundary-row")
                XCTAssertTrue(row.waitForExistence(timeout: 5))
                XCTAssertEqual(try row.snapshot().frame.midY, y, accuracy: 0.01)
                let count = element("proto-boundary-count")
                XCTAssertEqual(count.label, "count=0;")
                let point = CGPoint(x: window.midX, y: y)
                app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(
                    dx: point.x - window.minX, dy: point.y - window.minY)).tap()
                let fired = count.label == "count=1;"
                try write(["kind": "prototype-cutoff-point", "face": face, "scope": scope, "stage": stage,
                           "route": boundaryRoute, "trial": trial,
                           "windowPointPt": [Double(point.x), Double(point.y)], "fired": fired,
                           "measuredInteractiveBottomPt": Double(interactiveBottom),
                           "insideBottomInset": y > interactiveBottom,
                           "temporaryButtonHeightPt": 2, "originalControlAcceptance": false,
                           "geometryFile": "proto-geometry--\(trial).json", "traced": traced,
                           "traceFile": traced ? "input-events--\(trial).json" : "none"], "proto-cutoff-point--\(trial)")
                if stage.hasPrefix("confirm") { try screenshot("proto-boundary", trial) }
                return fired
            }
            var low = window.maxY - 72
            var high = window.maxY - 1
            var lowerWorks = try probe(low, stage: "low")
            let upperWorks = try probe(high, stage: "high")
            var insetConfirmations: [[String: Any]] = []
            if prototypeClockRecheck {
                // Collect these positions even if the very bottom rejects the first probe.
                // Their receipts remain independent of any monotonic-cutoff assumption.
                let ys = [interactiveBottom - 1, interactiveBottom + 1,
                          ((interactiveBottom + bottomInset / 2) * 2).rounded(.down) / 2]
                for y in ys {
                    for attempt in 1...5 {
                        insetConfirmations.append(["y": Double(y), "traced": false,
                                                   "fired": try probe(y, stage: "confirm-inset-\(attempt)")])
                    }
                    insetConfirmations.append(["y": Double(y), "traced": true,
                                               "fired": try probe(y, stage: "confirm-inset-diagnostic", traced: true)])
                }
            }
            if !lowerWorks && !upperWorks {
                var retries: [Bool] = []
                for attempt in 1...5 { retries.append(try probe(low, stage: "retry-\(attempt)")) }
                lowerWorks = retries.allSatisfy { $0 }
            }
            if upperWorks {
                var confirmations = insetConfirmations
                for y in [low, high] {
                    for attempt in 1...5 {
                        confirmations.append(["y": Double(y), "traced": false,
                                              "fired": try probe(y, stage: "confirm-endpoint-\(attempt)")])
                    }
                    confirmations.append(["y": Double(y), "traced": true,
                                          "fired": try probe(y, stage: "confirm-endpoint-diagnostic", traced: true)])
                }
                try write(["kind": "prototype-cutoff-summary", "face": face, "scope": scope,
                           "route": boundaryRoute,
                           "boundaryLocated": false, "lowerWorks": lowerWorks, "upperWorks": upperWorks,
                           "measuredInteractiveBottomPt": Double(interactiveBottom),
                           "windowMaxY": Double(window.maxY), "sampledLowY": Double(low),
                           "sampledHighY": Double(high), "confirmations": confirmations,
                           "note": "Upper endpoint accepted; confirmations retain each sampled y, without proving every intervening pixel or another hierarchy.",
                           "originalControlAcceptance": false], "proto-cutoff-summary--\(scope)")
                continue
            }
            if !lowerWorks {
                try write(["kind": "prototype-cutoff-summary", "face": face, "scope": scope,
                           "route": boundaryRoute, "boundaryLocated": false,
                           "lowerWorks": lowerWorks, "upperWorks": upperWorks,
                           "confirmations": insetConfirmations,
                           "originalControlAcceptance": false], "proto-cutoff-summary--\(scope)")
                continue
            }
            while high - low > 0.5 {
                let middle = ((low + high) * 1).rounded(.down) / 2
                if try probe(middle, stage: "binary") { low = middle } else { high = middle }
            }
            var confirmations = insetConfirmations
            for y in [low, high] {
                for attempt in 1...5 {
                    confirmations.append(["y": Double(y), "traced": false,
                                          "fired": try probe(y, stage: "confirm-\(attempt)")])
                }
                confirmations.append(["y": Double(y), "traced": true,
                                      "fired": try probe(y, stage: "confirm-diagnostic", traced: true)])
            }
            try write(["kind": "prototype-cutoff-summary", "face": face, "scope": scope,
                       "route": boundaryRoute,
                       "lastWorkingY": Double(low), "firstFailingY": Double(high), "resolutionPt": 0.5,
                       "boundaryLocated": true, "confirmations": confirmations,
                       "originalControlAcceptance": false], "proto-cutoff-summary--\(scope)")
        }
    }
}
