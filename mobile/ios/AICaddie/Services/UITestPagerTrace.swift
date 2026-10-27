#if DEBUG
import Foundation
import SwiftUI

/// An opt-in, in-memory ring for the accessibility tree captured by RealFlowUITests.dump().
/// Release builds contain neither the store nor the accessibility element.
// Called only by the main-actor view/model. Keeping initialization nonisolated also lets
// SwiftUI create its StateObject before evaluating body on older SDKs.
final class UITestPagerTrace: ObservableObject {
    static let shared = UITestPagerTrace()
    let enabled = ProcessInfo.processInfo.environment["UITEST_PAGER_TRACE"] == "1"
    @Published private(set) var label = ""
    private var events: [String] = []

    func record(_ message: String) {
        guard enabled else { return }
        events.append(String(format: "%.3f", ProcessInfo.processInfo.systemUptime) + " " + message)
        if events.count > 40 { events.removeFirst(events.count - 40) }
        label = events.joined(separator: "\n")
    }
}
#endif
