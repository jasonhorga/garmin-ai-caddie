import XCTest

/// Interaction helpers for transitions that can be committed by SwiftUI one run-loop after the
/// accessibility tap.  A disappearing source or an appearing destination acknowledges the first
/// tap; only an unacknowledged source is tapped a second time.
enum UITapHelpers {
    /// Tap only after the element has stayed hittable at the same non-empty frame for two
    /// accessibility polls.  SwiftUI can publish the new button before its transition has
    /// committed an activation point.
    @discardableResult
    static func tapWhenHittable(
        _ source: XCUIElement,
        timeout: TimeInterval,
        diagnosticName: String
    ) -> Bool {
        guard waitForStableHittability(source, timeout: timeout) else {
            print("UI_TAP source-not-ready \(diagnosticName)")
            return false
        }
        source.tap()
        return true
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
        guard waitForStableHittability(field, timeout: timeout) else {
            print("UI_TYPE field-not-ready \(diagnosticName)")
            return false
        }

        field.tap()
        if waitForCondition({ hasKeyboardFocus(field, app: app) }, timeout: max(0, deadline.timeIntervalSinceNow)) {
            field.typeText(text)
            return true
        }

        print("UI_TYPE focus-retry \(diagnosticName)")
        guard deadline.timeIntervalSinceNow > 0,
              waitForStableHittability(field, timeout: max(0, deadline.timeIntervalSinceNow)) else {
            return false
        }
        field.tap()
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
        destinations: [XCUIElement],
        timeout: TimeInterval,
        diagnosticName: String
    ) -> Bool {
        let started = Date()
        let deadline = started.addingTimeInterval(timeout)
        guard waitForStableHittability(source, timeout: timeout) else {
            print("UI_TAP source-not-ready \(diagnosticName)")
            return false
        }

        source.tap()
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
               waitForStableHittability(source, timeout: max(0, deadline.timeIntervalSinceNow)) {
                source.tap()
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
        field.hasKeyboardFocus || app.keyboards.firstMatch.exists
    }

    private static func waitForStableHittability(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        var previousFrame: CGRect?
        return waitForCondition({
            guard element.exists, element.isHittable else {
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
            return stable
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
