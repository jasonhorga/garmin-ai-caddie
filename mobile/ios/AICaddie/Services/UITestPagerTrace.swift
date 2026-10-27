#if DEBUG
import Foundation
import SwiftUI

/// An opt-in, in-memory ring for the accessibility tree captured by RealFlowUITests.dump().
/// Release builds contain neither the store nor the accessibility element.
// Called only by the main-actor view/model. Keeping initialization nonisolated also lets
// SwiftUI create its observed trace view before evaluating body on older SDKs.
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

/// Put the same marker inside presented sheets: UIKit can hide the presenting page's AX subtree.
struct UITestPagerTraceElement: View {
    @ObservedObject private var trace = UITestPagerTrace.shared

    var body: some View {
        if trace.enabled {
            Text("pager trace")
                .font(.system(size: 1))
                .foregroundStyle(Color.white.opacity(0.02))
                .frame(width: 1, height: 1)
                .accessibilityElement(children: .ignore)
                .accessibilityIdentifier("debug-pager-trace")
                .accessibilityLabel(trace.label)
                .allowsHitTesting(false)
        }
    }
}
#endif
