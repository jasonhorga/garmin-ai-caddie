#if DEBUG
import Foundation
import SwiftUI
import UIKit

/// DEBUG-only trace storage. It deliberately is not ObservableObject: a trace event must not
/// invalidate every CurrentHoleView mounted by the pager.
final class UITestPagerTrace {
    enum Metric: String {
        case roundHomeBody = "roundHome.body"
        case currentHoleBody = "currentHole.body"
        case currentHoleAppear = "currentHole.appear"
        case currentHoleDisappear = "currentHole.disappear"
        case displayProbeUpdate = "displayProbe.update"
        case preferenceCallback = "preference.callback"
        case correctionTask = "task.correction"
        case presentationEndTask = "task.presentationEnd"
        case preciseMapPoll = "task.preciseMapPoll"
    }

    static let shared = UITestPagerTrace()
    let enabled = ProcessInfo.processInfo.environment["UITEST_PAGER_TRACE"] == "1"

    private var events: [String] = []
    private var counts: [String: Int] = [:]
    private var totals: [String: Double] = [:]
    private var taskCounts: [String: Int] = [:]
    private var views: [WeakTraceView] = []

    func record(_ message: String) {
        guard enabled else { return }
        counts["trace.record"] = (counts["trace.record"] ?? 0) + 1
        events.append(String(format: "%.3f", ProcessInfo.processInfo.systemUptime) + " " + message)
        if events.count > 40 { events.removeFirst(events.count - 40) }
        refreshAccessibilityLabels()
    }

    func metric(_ metric: Metric) {
        guard enabled else { return }
        let key = metric.rawValue
        counts[key] = (counts[key] ?? 0) + 1
        refreshAccessibilityLabels()
    }

    func taskStarted(_ metric: Metric) {
        guard enabled else { return }
        let key = metric.rawValue
        taskCounts[key] = (taskCounts[key] ?? 0) + 1
        refreshAccessibilityLabels()
    }

    func taskFinished(_ metric: Metric) {
        guard enabled else { return }
        let key = metric.rawValue
        taskCounts[key] = max(0, (taskCounts[key] ?? 0) - 1)
        refreshAccessibilityLabels()
    }

    func loadEventsCompleted(duration: TimeInterval, cacheHit: Bool) {
        guard enabled else { return }
        counts["offline.loadEvents.calls"] = (counts["offline.loadEvents.calls"] ?? 0) + 1
        if cacheHit {
            counts["offline.loadEvents.cacheHits"] =
                (counts["offline.loadEvents.cacheHits"] ?? 0) + 1
        }
        totals["offline.loadEvents.ms"] =
            (totals["offline.loadEvents.ms"] ?? 0) + duration * 1_000
        refreshAccessibilityLabels()
    }

    func attach(_ view: UIView) {
        guard enabled else { return }
        views.removeAll { $0.view == nil || $0.view === view }
        views.append(WeakTraceView(view))
        update(view)
    }

    func update(_ view: UIView) {
        guard enabled else { return }
        view.accessibilityIdentifier = "debug-pager-trace"
        view.accessibilityLabel = renderedLabel()
    }

    private func refreshAccessibilityLabels() {
        guard enabled else { return }
        views.removeAll { $0.view == nil }
        let value = renderedLabel()
        for box in views { box.view?.accessibilityLabel = value }
    }

    private func renderedLabel() -> String {
        let metricText = counts.keys.sorted().map { "\($0)=\(counts[$0] ?? 0)" }.joined(separator: " ")
        let totalText = totals.keys.sorted().map {
            let value = String(format: "%.1f", totals[$0] ?? 0)
            return "\($0)=\(value)"
        }.joined(separator: " ")
        let taskText = taskCounts.keys.sorted().map { "\($0)=\(taskCounts[$0] ?? 0)" }.joined(separator: " ")
        let mounted = (counts[Metric.currentHoleAppear.rawValue] ?? 0)
            - (counts[Metric.currentHoleDisappear.rawValue] ?? 0)
        return events.joined(separator: "\n")
            + "\nCOUNTS \(metricText) currentHole.mounted=\(mounted) totals=\(totalText) tasks=\(taskText)"
    }
}

private final class WeakTraceView {
    weak var view: UIView?

    init(_ view: UIView) { self.view = view }
}

/// A direct UIKit accessibility node. Updating its label does not invalidate SwiftUI's view tree.
struct UITestPagerTraceElement: UIViewRepresentable {
    func makeUIView(context: Context) -> UIView {
        let view = UIView(frame: .zero)
        view.isUserInteractionEnabled = false
        view.frame = CGRect(x: 0, y: 0, width: 1, height: 1)
        view.isAccessibilityElement = UITestPagerTrace.shared.enabled
        if UITestPagerTrace.shared.enabled {
            view.accessibilityIdentifier = "debug-pager-trace"
        }
        UITestPagerTrace.shared.attach(view)
        return view
    }

    func updateUIView(_ uiView: UIView, context: Context) {
        UITestPagerTrace.shared.attach(uiView)
    }
}

#endif
