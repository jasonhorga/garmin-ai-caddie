#if DEBUG && targetEnvironment(simulator)
import CoreGraphics
import Foundation
import ObjectiveC

/// Opt-in input evidence, never shipped in a device build. Observe the existing native event
/// dispatcher instead of adding a SwiftUI recognizer/view that could change gesture competition.
/// Runtime lookup is needed because watchOS does not expose UIKit in its public SDK. If that
/// dispatcher is unavailable, the receipt says so; an empty trace is not proof of a lost touch.
enum WatchSimulatorInputTrace {
    private typealias SendEvent = @convention(c) (AnyObject, Selector, AnyObject) -> Void
    private typealias ObjectGetter = @convention(c) (AnyObject, Selector) -> AnyObject?
    private typealias IntegerGetter = @convention(c) (AnyObject, Selector) -> Int
    private typealias PointGetter = @convention(c) (AnyObject, Selector, AnyObject?) -> CGPoint
    private typealias RectGetter = @convention(c) (AnyObject, Selector) -> CGRect
    private static let environment = ProcessInfo.processInfo.environment
    private static var installed = false
    private static var records: [[String: Any]] = []

    private static var enabled: Bool { environment["UITEST_AUDIT_INPUT_TRACE"] == "1" }
    private static var trial: String { environment["UITEST_AUDIT_INPUT_TRIAL"] ?? "unnamed" }

    static func installIfRequested() {
        guard enabled, !installed else { return }
        installed = true
        let eventSelector = NSSelectorFromString("sendEvent:")
        let sharedSelector = NSSelectorFromString("sharedApplication")
        var candidates: [[String: Any]] = []
        for name in ["UIApplication", "PUICApplication", "SPApplication"] {
            guard let type = NSClassFromString(name) else {
                candidates.append(["class": name, "loaded": false]); continue
            }
            guard let shared = class_getClassMethod(type, sharedSelector) else {
                candidates.append(["class": name, "loaded": true, "sharedApplication": false]); continue
            }
            let getShared = unsafeBitCast(method_getImplementation(shared), to: ObjectGetter.self)
            guard let application = getShared(type as AnyObject, sharedSelector),
                  let actualClass = object_getClass(application),
                  let method = class_getInstanceMethod(actualClass, eventSelector) else {
                candidates.append(["class": name, "loaded": true, "sendEvent": false]); continue
            }
            let forward = unsafeBitCast(method_getImplementation(method), to: SendEvent.self)
            let block: @convention(block) (AnyObject, AnyObject) -> Void = { application, event in
                // Read-only observation before forwarding exactly once to the original dispatcher.
                observe(event)
                forward(application, eventSelector, event)
            }
            let replacement = imp_implementationWithBlock(block)
            // Do not accidentally replace a superclass's inherited method for unrelated receivers.
            if !class_addMethod(actualClass, eventSelector, replacement, method_getTypeEncoding(method)) {
                method_setImplementation(method, replacement)
            }
            append(["kind": "hook", "available": true, "applicationClass": NSStringFromClass(actualClass),
                    "selector": "sendEvent:", "addsGestureRecognizer": false,
                    "changesHitTesting": false, "forwardsOriginalOnce": true])
            return
        }
        append(["kind": "hook", "available": false, "candidates": candidates,
                "reason": "Native dispatcher not available; raw-touch arrival is unproved"])
    }

    static func action(_ name: String, fields: [String: Any] = [:]) {
        guard enabled else { return }
        append(["kind": "action", "action": name, "fields": fields])
    }

    private static func observe(_ event: AnyObject) {
        guard let touches = object(event, "allTouches") as? NSSet, touches.count > 0 else { return }
        var rows: [[String: Any]] = []
        for touch in touches {
            let touch = touch as AnyObject
            let window = object(touch, "window")
            let view = object(touch, "view")
            var row: [String: Any] = ["touchClass": className(touch),
                                     "phase": integer(touch, "phase") ?? -1,
                                     "windowClass": window.map(className) ?? "none",
                                     "hitViewClass": view.map(className) ?? "none"]
            let selector = NSSelectorFromString("locationInView:")
            if let method = instanceMethod(touch, selector) {
                let getPoint = unsafeBitCast(method_getImplementation(method), to: PointGetter.self)
                let point = getPoint(touch, selector, window)
                row["windowPointPt"] = [Double(point.x), Double(point.y)]
            }
            if let window, let bounds = rectangle(window, "bounds") {
                row["windowBoundsPt"] = rect(bounds)
                if let guide = object(window, "safeAreaLayoutGuide"), let layout = rectangle(guide, "layoutFrame") {
                    row["windowSafeAreaLayoutFramePt"] = rect(layout)
                    row["windowSafeAreaInsetsDerivedPt"] = [
                        "top": Double(layout.minY - bounds.minY), "bottom": Double(bounds.maxY - layout.maxY),
                        "leading": Double(layout.minX - bounds.minX), "trailing": Double(bounds.maxX - layout.maxX),
                    ]
                }
            }
            var ancestors: [[String: Any]] = []
            var next = view
            while let node = next, ancestors.count < 12 {
                var ancestor: [String: Any] = ["class": className(node)]
                if let frame = rectangle(node, "frame") { ancestor["framePt"] = rect(frame) }
                if let identifier = object(node, "accessibilityIdentifier") as? String {
                    ancestor["identifier"] = identifier
                }
                ancestors.append(ancestor)
                next = object(node, "superview")
            }
            row["hitViewAncestors"] = ancestors
            rows.append(row)
        }
        append(["kind": "touches", "eventClass": className(event), "touches": rows])
    }

    private static func instanceMethod(_ receiver: AnyObject, _ selector: Selector) -> Method? {
        guard let type = object_getClass(receiver) else { return nil }
        return class_getInstanceMethod(type, selector)
    }

    private static func object(_ receiver: AnyObject, _ name: String) -> AnyObject? {
        let selector = NSSelectorFromString(name)
        guard let method = instanceMethod(receiver, selector) else { return nil }
        let get = unsafeBitCast(method_getImplementation(method), to: ObjectGetter.self)
        return get(receiver, selector)
    }

    private static func integer(_ receiver: AnyObject, _ name: String) -> Int? {
        let selector = NSSelectorFromString(name)
        guard let method = instanceMethod(receiver, selector) else { return nil }
        let get = unsafeBitCast(method_getImplementation(method), to: IntegerGetter.self)
        return get(receiver, selector)
    }

    private static func rectangle(_ receiver: AnyObject, _ name: String) -> CGRect? {
        let selector = NSSelectorFromString(name)
        guard let method = instanceMethod(receiver, selector) else { return nil }
        let get = unsafeBitCast(method_getImplementation(method), to: RectGetter.self)
        return get(receiver, selector)
    }

    private static func className(_ receiver: AnyObject) -> String {
        object_getClass(receiver).map(NSStringFromClass) ?? "unknown"
    }

    private static func rect(_ value: CGRect) -> [Double] {
        [Double(value.minX), Double(value.minY), Double(value.width), Double(value.height)]
    }

    private static func append(_ fields: [String: Any]) {
        var row = fields
        row["sequence"] = records.count + 1
        row["uptimeSeconds"] = ProcessInfo.processInfo.systemUptime
        records.append(row)
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("watch-audit", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let safeTrial = trial.filter { $0.isLetter || $0.isNumber || $0 == "-" }
        let payload: [String: Any] = ["kind": "native-input-trace", "trial": trial,
                                      "releaseBehaviorChanged": false, "events": records]
        if let data = try? JSONSerialization.data(withJSONObject: payload, options: .sortedKeys) {
            try? data.write(to: directory.appendingPathComponent("input-events--\(safeTrial).json"), options: .atomic)
        }
    }
}
#endif
