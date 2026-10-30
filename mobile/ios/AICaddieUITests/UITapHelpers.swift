import XCTest

/// Interaction helpers for transitions that can be committed by SwiftUI one run-loop after the
/// accessibility tap.  A disappearing source or an appearing destination acknowledges the first
/// tap; only an unacknowledged source is tapped a second time.
enum UITapHelpers {
    /// Wait within a budget for stable geometry, dismissal of covering sheets, and a real hit
    /// point, then tap the visible centre. On timeout return false; callers must reveal/scroll an
    /// off-screen source first. There is no coordinate fallback through a still-present sheet.
    @discardableResult
    static func tapWhenHittable(
        _ source: XCUIElement,
        app: XCUIApplication,
        timeout: TimeInterval,
        diagnosticName: String
    ) -> Bool {
        guard tapPreferringStableFrame(source, app: app, timeout: timeout, diagnosticName: diagnosticName) else {
            return false
        }
        return true
    }

    private static func tapPreferringStableFrame(
        _ source: XCUIElement,
        app: XCUIApplication,
        timeout: TimeInterval,
        diagnosticName: String
    ) -> Bool {
        guard waitForStableHittability(source, app: app, timeout: timeout) else {
            print("UI_TAP source-not-ready \(diagnosticName)")
            return false
        }
        return tapUsingStableCoordinate(source, app: app, diagnosticName: diagnosticName)
    }

    /// Focus a text field before typing.  A sheet can be visible while the first tap is still
    /// being committed; retry the focus tap once before allowing text input to proceed.
    @discardableResult
    static func focusAndTypeText(
        _ field: XCUIElement,
        text: String,
        app: XCUIApplication,
        timeout: TimeInterval,
        diagnosticName: String
    ) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        guard tapPreferringStableFrame(field, app: app, timeout: timeout, diagnosticName: diagnosticName) else {
            print("UI_TYPE field-not-ready \(diagnosticName)")
            return false
        }
        // A readiness wait may have used the whole stability budget; still give focus a short window.
        if waitForCondition({ hasKeyboardFocus(field, app: app) }, timeout: max(2, deadline.timeIntervalSinceNow)) {
            field.typeText(text)
            return true
        }

        print("UI_TYPE focus-retry \(diagnosticName)")
        guard deadline.timeIntervalSinceNow > 0,
              waitForStableHittability(field, app: app, timeout: max(0, deadline.timeIntervalSinceNow)) else {
            print("UI_TYPE field-not-ready-after-retry \(diagnosticName)")
            return false
        }
        _ = tapUsingStableCoordinate(field, app: app, diagnosticName: "\(diagnosticName)-focus-retry")
        guard waitForCondition({ hasKeyboardFocus(field, app: app) }, timeout: max(0, deadline.timeIntervalSinceNow)) else {
            print("UI_TYPE focus-not-ready \(diagnosticName)")
            return false
        }
        field.typeText(text)
        return true
    }

    @discardableResult
    static func tapAndWaitForElements(
        _ source: XCUIElement,
        app: XCUIApplication,
        destinations: [XCUIElement],
        timeout: TimeInterval,
        diagnosticName: String
    ) -> Bool {
        let started = Date()
        let deadline = started.addingTimeInterval(timeout)
        guard tapPreferringStableFrame(source, app: app, timeout: timeout / 2, diagnosticName: diagnosticName) else {
            return false
        }
        var acknowledged = false
        let transitionAcknowledged = {
            if !acknowledged {
                acknowledged = destinations.contains { $0.exists } || !source.exists
            }
            return acknowledged
        }
        let firstBudget = max(0, deadline.timeIntervalSinceNow) / 2
        if !waitForCondition(transitionAcknowledged, timeout: firstBudget), !transitionAcknowledged() {
            let elapsed = Date().timeIntervalSince(started)
            print("重试点击 \(diagnosticName) elapsed=\(elapsed)")
            XCTContext.runActivity(named: "retry tap \(diagnosticName)") { activity in
                let attachment = XCTAttachment(string: "retry tap \(diagnosticName), elapsed=\(elapsed)s")
                // Keep retry evidence on passing runs too: a swallowed tap is the C113 symptom.
                attachment.lifetime = .keepAlways
                activity.add(attachment)
            }
            if deadline.timeIntervalSinceNow > 0,
               waitForStableHittability(source, app: app, timeout: max(0, deadline.timeIntervalSinceNow)) {
                _ = tapUsingStableCoordinate(source, app: app, diagnosticName: "\(diagnosticName)-transition-retry")
            }
        }
        let ready = waitForCondition(
            { destinations.contains { $0.exists } },
            timeout: max(0, deadline.timeIntervalSinceNow)
        )
        if !ready {
            print("UI_TAP destination-not-ready \(diagnosticName) elapsed=\(Date().timeIntervalSince(started))")
        }
        return ready
    }

    private static func hasKeyboardFocus(_ field: XCUIElement, app: XCUIApplication) -> Bool {
        let keyboardVisible = app.keyboards.firstMatch.exists
        let fieldHasFocus = (field.value(forKey: "hasKeyboardFocus") as? Bool) ?? false
        return keyboardVisible && (fieldHasFocus || app.textFields.allElementsBoundByIndex.filter { $0.exists }.count == 1)
    }

    /// Preserve hit-testing semantics for assertions and UITestViewport's sheet occlusion rule.
    static func isSafelyHittable(_ element: XCUIElement, in app: XCUIApplication) -> Bool {
        guard element.exists else { return false }
        let frame = element.frame
        let windowFrame = app.windows.firstMatch.frame
        guard frame.width > 0, frame.height > 0,
              windowFrame.width > 0, windowFrame.height > 0,
              frame.intersects(windowFrame) else { return false }
        return element.isHittable
    }

    /// Geometry is only a prerequisite for a tap, never proof that an element is uncovered.
    private static func isTapGeometryReady(_ element: XCUIElement, in app: XCUIApplication) -> Bool {
        guard element.exists else { return false }
        let frame = element.frame
        let window = app.windows.firstMatch.frame
        return !frame.isEmpty && !window.isEmpty && window.contains(
            element.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).screenPoint
        )
    }

    private static func isCoveredBySheet(_ element: XCUIElement, in app: XCUIApplication) -> Bool {
        // The live chrome does not move while the score sheet dismisses. SwiftUI may expose that
        // sheet as an Other rather than a Sheet, so wait for its controls before probing the
        // underlying scorecard's activation point (the original live-open-scorecard failure).
        if element.identifier == "live-open-scorecard",
           app.buttons.matching(NSPredicate(format: "identifier IN %@", ["score-save", "score-cancel"]))
               .firstMatch.exists {
            return true
        }
        let centre = element.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).screenPoint
        return app.sheets.allElementsBoundByIndex.contains { sheet in
            sheet.exists && sheet.frame.contains(centre) && !UITestViewport.isDescendant(element, of: sheet)
        }
    }

    @discardableResult
    private static func tapUsingStableCoordinate(
        _ element: XCUIElement,
        app: XCUIApplication,
        diagnosticName: String
    ) -> Bool {
        guard isTapGeometryReady(element, in: app), !isCoveredBySheet(element, in: app),
              isSafelyHittable(element, in: app) else {
            print("UI_TAP activation-point-not-ready \(diagnosticName)")
            return false
        }
        element.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        return true
    }

    private static func waitForStableHittability(
        _ element: XCUIElement,
        app: XCUIApplication,
        timeout: TimeInterval
    ) -> Bool {
        var previousFrame: CGRect?
        return waitForCondition({
            guard isTapGeometryReady(element, in: app), element.isEnabled,
                  !isCoveredBySheet(element, in: app) else {
                previousFrame = nil
                return false
            }
            let frame = element.frame
            guard !frame.isEmpty else {
                previousFrame = nil
                return false
            }
            guard let oldFrame = previousFrame else {
                previousFrame = frame
                return false
            }
            let stable = abs(frame.minX - oldFrame.minX) < 0.5
                && abs(frame.minY - oldFrame.minY) < 0.5
                && abs(frame.width - oldFrame.width) < 0.5
                && abs(frame.height - oldFrame.height) < 0.5
            previousFrame = frame
            // Only ask XCTest for a hit point after the geometry and presentation have settled.
            // A stable underlying button alone is insufficient while a sheet is still moving.
            return stable && isSafelyHittable(element, in: app)
        }, timeout: timeout)
    }

    private static func waitForCondition(_ condition: @escaping () -> Bool, timeout: TimeInterval) -> Bool {
        if condition() { return true }
        let remaining = max(0, timeout)
        guard remaining > 0 else { return false }
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate { _, _ in condition() },
            object: nil
        )
        return XCTWaiter.wait(for: [expectation], timeout: remaining) == .completed
    }
}
