#if DEBUG && targetEnvironment(simulator)
import Foundation
import SwiftUI

/// #417 / 6119731901: opt-in geometry receipts and a deliberately temporary full-width button.
/// This changes the DEBUG probe's hit surface only; it does not repair or validate product controls.
enum WatchSafeAreaProbe {
    private static let environment = ProcessInfo.processInfo.environment
    private static var geometries: [String: [String: Any]] = [:]
    static var scope: String { environment["UITEST_AUDIT_SAFE_AREA_SCOPE"] ?? "" }
    static var enabled: Bool { scope == "root" || scope == "hazard" }
    static var windowY: CGFloat { CGFloat(Double(environment["UITEST_AUDIT_SAFE_AREA_Y"] ?? "0") ?? 0) }

    static func receipt(_ layer: String, proxy: GeometryProxy) -> some View {
        let size = proxy.size
        let frame = proxy.frame(in: .global)
        let insets = proxy.safeAreaInsets
        return Color.clear.allowsHitTesting(false).accessibilityHidden(true)
            .onAppear { record(layer, size: size, frame: frame, insets: insets) }
    }

    static func record(_ layer: String, size: CGSize, frame: CGRect, insets: EdgeInsets) {
        guard enabled else { return }
        geometries[layer] = [
            "sizePt": [Double(size.width), Double(size.height)],
            "globalFramePt": [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)],
            "safeAreaInsetsPt": ["top": Double(insets.top), "bottom": Double(insets.bottom),
                                  "leading": Double(insets.leading), "trailing": Double(insets.trailing)],
            "localHeightMinusBottomPt": Double(size.height - insets.bottom),
            "globalBottomMinusInsetPt": Double(frame.maxY - insets.bottom),
        ]
        let trial = (environment["UITEST_AUDIT_INPUT_TRIAL"] ?? "unnamed")
            .filter { $0.isLetter || $0.isNumber || $0 == "-" }
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("watch-audit", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let payload: [String: Any] = ["kind": "safe-area-geometry", "scope": scope,
                                      "trial": trial, "requestedWindowY": Double(windowY),
                                      "layers": geometries, "productionControlAcceptance": false]
        if let data = try? JSONSerialization.data(withJSONObject: payload, options: .sortedKeys) {
            try? data.write(to: directory.appendingPathComponent("safe-area-geometry--\(trial).json"), options: .atomic)
        }
    }
}

/// Passive background measurement at the container root, outside the instrument's ignoresSafeArea.
struct WatchSafeAreaGeometryObserver: View {
    let layer: String
    var body: some View {
        if WatchSafeAreaProbe.enabled {
            GeometryReader { proxy in WatchSafeAreaProbe.receipt(layer, proxy: proxy) }
                .allowsHitTesting(false).accessibilityHidden(true)
        }
    }
}

struct WatchSafeAreaProbeLayer: View {
    let scope: String
    @State private var count = 0

    var body: some View {
        GeometryReader { proxy in
            let frame = proxy.frame(in: .global)
            ZStack(alignment: .topLeading) {
                Button {
                    count += 1
                    WatchSimulatorInputTrace.action("safe-area-row.enter", fields: [
                        "scope": scope, "requestedWindowY": Double(WatchSafeAreaProbe.windowY), "count": count,
                    ])
                } label: {
                    Rectangle().fill(Color.pink.opacity(0.7))
                        .frame(width: proxy.size.width, height: 2)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .frame(width: proxy.size.width, height: 2)
                .position(x: proxy.size.width / 2, y: WatchSafeAreaProbe.windowY - frame.minY)
                .accessibilityLabel("DEBUG boundary row")
                .accessibilityIdentifier("watch-safe-area-probe-row")
                Text("count=\(count);").font(.system(size: 1)).foregroundStyle(.clear)
                    .frame(width: 2, height: 2).allowsHitTesting(false)
                    .accessibilityIdentifier("watch-safe-area-probe-count")
            }
            .background { WatchSafeAreaProbe.receipt(scope + "-probe-layer", proxy: proxy) }
        }
    }
}
#endif
