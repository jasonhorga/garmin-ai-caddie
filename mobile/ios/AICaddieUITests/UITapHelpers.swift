import XCTest

/// Interaction helpers for transitions that can be committed by SwiftUI one run-loop after the
/// accessibility tap.  A disappearing source or an appearing destination acknowledges the first
/// tap; only an unacknowledged source is tapped a second time.
enum UITapHelpers {
    @discardableResult
    static func tapAndWaitForElements(
        _ source: XCUIElement,
        destinations: [XCUIElement],
        timeout: TimeInterval,
        diagnosticName: String
    ) -> Bool {
        let started = Date()
        let deadline = started.addingTimeInterval(timeout)
        guard waitForCondition({ source.exists && source.isHittable }, timeout: timeout) else {
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
            print("重试点击 \(diagnosticName) elapsed=\(Date().timeIntervalSince(started))")
            if source.exists && source.isHittable, deadline.timeIntervalSinceNow > 0 {
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
