import XCTest

/// #417 acceptance of #424 production controls. Every target gets five fresh centre taps and
/// five fresh centre+8pt taps. The model/persistence/navigation callbacks are never replaced.
/// Tests collect failed interactions as evidence; an executed method is not an interaction pass.
final class WatchProductionElementAuditUITests: XCTestCase {
    private let app = XCUIApplication()
    private var sequence = 0
    private var face: String { ProcessInfo.processInfo.environment["UITEST_AUDIT_FACE"] ?? "unknown" }
    private var output: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("watch-audit", isDirectory: true)
    }

    private struct Spec {
        let key: String
        let route: String
        let screen: String
        let page: Int
        let prepare: [String]
        let target: String
        let expected: [String: String]
        let selected: Bool
        let visibleAfter: String?
        let absentAfter: String?
        let changedLabel: Bool
        init(_ key: String, target: String, route: String = "audit-phone-18", screen: String = "scoring",
             page: Int = 0, prepare: [String] = [], expected: [String: String] = [:],
             selected: Bool = false, visibleAfter: String? = nil, absentAfter: String? = nil,
             changedLabel: Bool = false) {
            self.key = key; self.target = target; self.route = route; self.screen = screen
            self.page = page; self.prepare = prepare; self.expected = expected; self.selected = selected
            self.visibleAfter = visibleAfter; self.absentAfter = absentAfter; self.changedLabel = changedLabel
        }
    }

    override func setUpWithError() throws {
        guard ProcessInfo.processInfo.environment["UITEST_WATCH_FULL_AUDIT"] == "1" else {
            throw XCTSkip("Production element audit requires its dedicated dispatch")
        }
        continueAfterFailure = false
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        if let run = testRun, run.failureCount > 0 { try capture("production-failure", name) }
        app.terminate()
    }

    private func element(_ id: String) -> XCUIElement {
        if id.hasPrefix("label:") {
            return app.buttons.matching(NSPredicate(format: "label == %@", String(id.dropFirst(6)))).firstMatch
        }
        return app.descendants(matching: .any).matching(identifier: id).firstMatch
    }

    private func state() -> String { element("watch-audit-state").label }
    private func matches(_ value: String, _ expected: [String: String]) -> Bool {
        expected.allSatisfy { value.contains("\($0.key)=\($0.value);") }
    }

    private func launch(_ spec: Spec, trial: String) throws {
        app.terminate()
        app.launchArguments = ["-uitest-screen", spec.route]
        app.launchEnvironment = ["UITEST_AUDIT_FACE": face, "UITEST_AUDIT_MODEL_SCREEN": spec.screen,
                                 "UITEST_AUDIT_PAGE": String(spec.page), "UITEST_AUDIT_RANGE": "fresh",
                                 "UITEST_AUDIT_SCORE": spec.route == "audit-score-par3" ? "3" : "5",
                                 "UITEST_AUDIT_PUTTS": "2", "UITEST_AUDIT_PENALTY": "0"]
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 20))
        XCTAssertTrue(element("watch-audit-state").waitForExistence(timeout: 15))
        let predicate = NSPredicate { _, _ in self.state().contains("ready=true;") }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: predicate, object: app)],
                                     timeout: 15), .completed)
    }

    private func box(_ frame: CGRect) -> [Double] {
        [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)]
    }

    private func metrics(_ control: XCUIElement) -> [String: Any] {
        guard control.exists, let snap = try? control.snapshot() else { return ["exists": false] }
        let rect = snap.frame
        guard [rect.minX, rect.minY, rect.width, rect.height].allSatisfy({ $0.isFinite }) else {
            return ["exists": true, "finiteFrame": false]
        }
        return ["exists": true, "identifier": snap.identifier, "label": snap.label,
                "value": (snap.value as? String) ?? "", "framePt": box(rect),
                "minDimensionPt": Double(min(rect.width, rect.height)),
                "under44Pt": rect.width < 44 || rect.height < 44,
                "frameEvidence": "AX frame; does not prove padded hit bounds"]
    }

    private func write(_ value: [String: Any], _ name: String) throws {
        sequence += 1
        let file = output.appendingPathComponent(String(format: "%04d-%@.json", sequence, name))
        try JSONSerialization.data(withJSONObject: value, options: .sortedKeys).write(to: file, options: .atomic)
    }

    private func capture(_ flow: String, _ step: String, inventory: Bool = false) throws {
        let stem = flow + "--" + step.replacingOccurrences(of: "/", with: "_")
        let shot = XCUIScreen.main.screenshot()
        try shot.pngRepresentation.write(to: output.appendingPathComponent(stem + ".png"), options: .atomic)
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = stem; attachment.lifetime = .keepAlways; add(attachment)
        var controls: [[String: Any]] = []
        if inventory {
            func descendants(_ root: any XCUIElementSnapshot) -> [any XCUIElementSnapshot] {
                root.children.flatMap { [$0] + descendants($0) }
            }
            controls = descendants(try app.snapshot()).filter {
                $0.identifier.hasPrefix("watch-") && $0.identifier != "watch-audit-state"
            }.map { snap in
                ["identifier": snap.identifier, "label": snap.label,
                 "value": (snap.value as? String) ?? "", "framePt": box(snap.frame)]
            }
        }
        try write(["kind": "production-screen", "face": face, "flow": flow, "step": step,
                   "state": state(), "screenFramePt": box(app.frame), "inventory": controls,
                   "screenshotPixels": [shot.image.cgImage?.width ?? 0, shot.image.cgImage?.height ?? 0],
                   "physicalWatchProven": false], "production-screen--" + stem)
    }

    private func pointerTap(_ control: XCUIElement, offset: CGFloat = 0) -> CGPoint {
        let frame = control.frame
        let point = CGPoint(x: frame.midX + offset, y: frame.midY)
        let origin = app.frame.origin
        app.coordinate(withNormalizedOffset: .zero)
            .withOffset(CGVector(dx: point.x - origin.x, dy: point.y - origin.y)).tap()
        return point
    }

    private func safeBottom() -> CGFloat {
        let height = app.frame.height
        let inset: CGFloat = height < 219 ? 26 : (height < 232 ? 31 : (height < 245 ? 27 : (height < 249.5 ? 36 : 39)))
        return app.frame.maxY - inset
    }

    /// Six deliberate user-like swipes, never AX tap's implicit off-screen scrolling.
    private func reveal(_ control: XCUIElement) -> Bool {
        for attempt in 0...6 {
            if control.exists {
                let rect = control.frame
                // Fixed controls may intentionally pad outside their visible frame. Acceptance
                // concerns the exact centre/+8pt pointer, not a claim of full-row visibility.
                if rect.midY >= app.frame.minY + 2, rect.midY <= safeBottom() + 0.5 { return true }
            }
            if attempt < 6 {
                let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.52, dy: 0.72))
                let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.52, dy: 0.35))
                start.press(forDuration: 0.05, thenDragTo: end)
            }
        }
        return false
    }

    private func prepare(_ actions: [String]) -> Bool {
        for action in actions {
            let control = element(action)
            guard reveal(control) else { return false }
            _ = pointerTap(control)
        }
        return true
    }

    private func satisfied(_ spec: Spec, priorLabel: String) -> Bool {
        guard matches(state(), spec.expected) else { return false }
        if spec.selected && !element(spec.target).isSelected { return false }
        if let id = spec.visibleAfter, !element(id).exists { return false }
        if let id = spec.absentAfter, element(id).exists { return false }
        if spec.changedLabel && element(spec.target).label == priorLabel { return false }
        return true
    }

    private func run(_ specs: [Spec]) throws {
        for spec in specs {
            for offset in [CGFloat(0), CGFloat(8)] {
                for attempt in 1...5 {
                    let trial = "\(spec.key)-x\(Int(offset))-\(attempt)"
                    try launch(spec, trial: trial)
                    let prepared = prepare(spec.prepare)
                    let target = element(spec.target)
                    let reached = prepared && reveal(target)
                    let before = state()
                    let details = metrics(target)
                    if !reached {
                        try write(["kind": "production-tap", "face": face, "trial": trial, "key": spec.key,
                                   "control": details, "before": before, "after": before,
                                   "offsetPt": Double(offset), "attempt": attempt, "attemptValid": false,
                                   "success": NSNull(), "reason": "preparation/visible target not reached",
                                   "freshLaunch": true, "productCallbacks": true], "production-tap--" + trial)
                        if attempt == 1 { try capture("production-unreachable", trial, inventory: true) }
                        continue
                    }
                    let oldLabel = target.label
                    let start = Date()
                    let point = pointerTap(target, offset: offset)
                    let predicate = NSPredicate { _, _ in self.satisfied(spec, priorLabel: oldLabel) }
                    let passed = XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: predicate, object: app)],
                                               timeout: 3) == .completed
                    try write(["kind": "production-tap", "face": face, "trial": trial, "key": spec.key,
                               "route": spec.route, "screen": spec.screen, "control": details,
                               "offsetPt": Double(offset), "attempt": attempt, "attemptValid": true,
                               "requestedWindowPointPt": [Double(point.x), Double(point.y)],
                               "before": before, "after": state(), "expected": spec.expected,
                               "success": passed, "freshLaunch": true, "productCallbacks": true,
                               "xctestActionMs": Int(Date().timeIntervalSince(start) * 1_000),
                               "uiFeedbackMs": NSNull(), "physicalWatchProven": false], "production-tap--" + trial)
                    if attempt == 1 { try capture("production-elements", trial, inventory: true) }
                }
            }
        }
    }

    func test01ScoreRows() throws {
        for route in ["audit-phone-18", "audit-score-par3"] {
            let total = route == "audit-score-par3" ? 3 : 5
            var specs: [Spec] = []
            for field in ["total", "putts", "penalty"] {
                specs.append(Spec("\(route)-select-\(field)", target: "watch-score-\(field)", route: route,
                                  prepare: ["watch-score-\(field == "total" ? "putts" : "total")"], selected: true))
                for plus in [false, true] {
                    let initial = field == "total" ? total : (field == "putts" ? 2 : 0)
                    let delta = plus ? 1 : -1
                    let prep = field == "penalty" && !plus ? ["watch-score-penalty-plus"] : []
                    let next = max(0, initial + (prep.isEmpty ? delta : 0))
                    specs.append(Spec("\(route)-\(field)-\(plus ? "plus" : "minus")",
                                      target: "watch-score-\(field)-\(plus ? "plus" : "minus")", route: route,
                                      prepare: prep, expected: [field == "total" ? "score" : field: String(next)]))
                }
            }
            try run(specs)
        }
    }

    func test02FairwayAndScoreSave() throws {
        var specs = [
            Spec("fairway-open", target: "watch-score-fairway", visibleAfter: "watch-score-fairway-back"),
            Spec("fairway-back", target: "watch-score-fairway-back", prepare: ["watch-score-fairway"],
                 absentAfter: "watch-score-fairway-back"),
        ]
        for side in ["LEFT", "HIT", "RIGHT"] {
            specs.append(Spec("fairway-\(side)", target: "watch-score-fairway-\(side)",
                              prepare: ["watch-score-fairway"], expected: ["fairway": side],
                              absentAfter: "watch-score-fairway-back"))
            specs.append(Spec("fairway-clear-\(side)", target: "watch-score-fairway-\(side)",
                              prepare: ["watch-score-fairway", "watch-score-fairway-\(side)", "watch-score-fairway"],
                              expected: ["fairway": "none"], absentAfter: "watch-score-fairway-back"))
        }
        for route in ["audit-phone-18", "audit-score-par3"] {
            specs.append(Spec("\(route)-save", target: "watch-score-save", route: route,
                              expected: ["scored": "1", "screen": "home", "strokes": route == "audit-score-par3" ? "3" : "5"]))
            specs.append(Spec("\(route)-cancel", target: "watch-score-cancel", route: route,
                              expected: ["scored": "0", "screen": "home"]))
        }
        try run(specs)
        let par3 = Spec("par3-hidden", target: "watch-score-save", route: "audit-score-par3")
        try launch(par3, trial: "par3-hidden-fairway")
        try write(["kind": "production-visibility", "face": face, "route": par3.route,
                   "fairwayExists": element("watch-score-fairway").exists, "expectedFairwayExists": false],
                  "production-par3-hidden")
        try capture("production-score", "par3", inventory: true)
    }

    func test03RootFirstShotAndHazard() throws {
        try run([Spec("root-menu", target: "watch-hole-menu", screen: "", expected: ["screen": "menu"]),
                 Spec("hazard-next", target: "watch-hazard-next", screen: "", page: 1, changedLabel: true)])
        for offset in [CGFloat(0), CGFloat(8)] {
            for attempt in 1...5 {
                let trial = "root-shot-x\(Int(offset))-\(attempt)"
                try launch(Spec(trial, target: "watch-hole-record-shot", screen: ""), trial: trial)
                let record = element("watch-hole-record-shot")
                let details = metrics(record)
                let before = state()
                let point = pointerTap(record, offset: offset)
                let afterRecord = state()
                var undone = false
                let undo = element("watch-shot-undo")
                if afterRecord.contains("pending=true;"), undo.exists {
                    _ = pointerTap(undo)
                    undone = state().contains("pending=false;") && state().contains("shots=0;")
                }
                try write(["kind": "first-try-shot", "face": face, "trial": trial, "attempt": attempt,
                           "offsetPt": Double(offset), "control": details, "before": before,
                           "requestedWindowPointPt": [Double(point.x), Double(point.y)],
                           "afterRecord": afterRecord, "afterUndo": state(),
                           "recordSucceeded": afterRecord.contains("pending=true;"), "undoSucceeded": undone,
                           "freshLaunch": true, "productCallbacks": true, "physicalWatchProven": false],
                          "first-try--" + trial)
                if attempt == 1 { try capture("production-root", trial, inventory: true) }
            }
        }
    }

    func test04TurnChoicesAndContinue() throws {
        try run([
            Spec("turn-continue", target: "watch-turn-continue", route: "audit-turn", screen: "",
                 expected: ["screen": "home", "hole": "10", "holes": "18", "loop": "31669:front+31669:back"]),
            Spec("turn-same", target: "watch-turn-continue", route: "audit-turn", screen: "",
                 prepare: ["watch-turn-half-front"], expected: ["screen": "home", "loop": "31669:front+31669:front"]),
            Spec("turn-stop", target: "watch-turn-continue", route: "audit-turn", screen: "",
                 prepare: ["watch-turn-stop-after-nine"], expected: ["screen": "finishing", "holes": "9"]),
            Spec("abc-turn", target: "watch-turn-continue", route: "audit-turn-nine", screen: "",
                 expected: ["screen": "home", "hole": "10", "loop": "32001:all+32002:all"]),
            Spec("abc-same-turn", target: "watch-turn-continue", route: "audit-turn-nine", screen: "",
                 prepare: ["watch-turn-loop-32001"], expected: ["screen": "home", "loop": "32001:all+32001:all"]),
        ])
    }

    func test05SecondNineReplacementAndPersistence() throws {
        let menu = "watch-hole-menu"
        let change = "label:换一个 9 洞"
        try run([
            Spec("replace-second", target: "watch-turn-continue", route: "audit-turn", screen: "",
                 prepare: ["watch-turn-continue", menu, change, "watch-turn-half-front"],
                 expected: ["screen": "home", "hole": "10", "loop": "31669:front+31669:front", "changeSecond": "true"]),
            Spec("drop-second", target: "watch-turn-continue", route: "audit-turn", screen: "",
                 prepare: ["watch-turn-continue", menu, change, "watch-turn-stop-after-nine"],
                 expected: ["screen": "finishing", "hole": "9", "holes": "9", "loop": "31669:front"]),
            Spec("abc-replace-second", target: "watch-turn-continue", route: "audit-turn-nine", screen: "",
                 prepare: ["watch-turn-continue", menu, change, "watch-turn-loop-32001"],
                 expected: ["screen": "home", "loop": "32001:all+32001:all", "changeSecond": "true"]),
        ])
        // Saving and relaunching goes through the real WatchRoundStore, not an injected screen.
        let score = Spec("score-persistence", target: "watch-score-save", prepare: ["watch-score-total-plus"])
        try launch(score, trial: "score-persistence")
        _ = pointerTap(element("watch-score-total-plus"))
        _ = pointerTap(element("watch-score-save"))
        let before = state()
        try launch(Spec("restore", target: "watch-score-save", route: "audit-restore", screen: ""), trial: "restore")
        try write(["kind": "production-persistence", "face": face, "beforeRelaunch": before,
                   "afterRelaunch": state(), "savedScoreRetained": matches(state(), ["scored": "1", "strokes": "6"]),
                   "physicalCrownProven": false, "realWCSessionProven": false], "production-score-persistence")
        try capture("production-persistence", "score-restore", inventory: true)
    }
}
