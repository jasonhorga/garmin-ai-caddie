#if DEBUG
import Foundation
import SwiftUI

/// #422 review instrumentation. No layout/hit repair and never compiled into Release.
enum WatchPrototypeAuditProbe {
    private static let environment = ProcessInfo.processInfo.environment
    private static var layers: [String: [String: Any]] = [:]
    static var enabled: Bool { environment["UITEST_PROTO_AUDIT"] == "1" }
    static var boundaryScope: String { environment["UITEST_PROTO_BOUNDARY_SCOPE"] ?? "" }
    static var boundaryY: CGFloat { CGFloat(Double(environment["UITEST_PROTO_BOUNDARY_Y"] ?? "0") ?? 0) }
    static var trial: String {
        (environment["UITEST_AUDIT_INPUT_TRIAL"] ?? "unnamed")
            .filter { $0.isLetter || $0.isNumber || $0 == "-" }
    }

    static func install() {
        guard enabled else { return }
        #if targetEnvironment(simulator)
        WatchSimulatorInputTrace.installIfRequested()
        #endif
    }

    static func action(_ name: String, fields: [String: Any] = [:]) {
        guard enabled else { return }
        #if targetEnvironment(simulator)
        WatchSimulatorInputTrace.action(name, fields: fields)
        #endif
    }

    static func geometry(_ layer: String, proxy: GeometryProxy) -> some View {
        let size = proxy.size
        let frame = proxy.frame(in: .global)
        let insets = proxy.safeAreaInsets
        return Color.clear.allowsHitTesting(false).accessibilityHidden(true)
            .onAppear {
                guard enabled else { return }
                layers[layer] = [
                    "sizePt": [Double(size.width), Double(size.height)],
                    "globalFramePt": [Double(frame.minX), Double(frame.minY), Double(frame.width), Double(frame.height)],
                    "safeAreaInsetsPt": ["top": Double(insets.top), "bottom": Double(insets.bottom),
                                          "leading": Double(insets.leading), "trailing": Double(insets.trailing)],
                ]
                write(["kind": "prototype-safe-area", "trial": trial, "layers": layers,
                       "boundaryScope": boundaryScope, "temporaryProbe": !boundaryScope.isEmpty],
                      name: "proto-geometry--\(trial).json")
            }
    }

    static func write(_ value: [String: Any], name: String) {
        guard enabled else { return }
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("watch-audit", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        if let data = try? JSONSerialization.data(withJSONObject: value, options: .sortedKeys) {
            try? data.write(to: directory.appendingPathComponent(name), options: .atomic)
        }
    }
}

/// Passive one-point AX state anchor; outside the controls and unable to receive touches.
struct WatchPrototypeAuditState: View {
    let value: String
    var body: some View {
        if WatchPrototypeAuditProbe.enabled {
            Text(value).font(.system(size: 1)).foregroundStyle(.clear)
                .frame(width: 1, height: 1).allowsHitTesting(false)
                .accessibilityIdentifier("proto-audit-state")
                .onAppear { WatchPrototypeAuditProbe.install() }
        }
    }
}

/// A passive receipt used to scroll real menu rows into the measured interactive canvas.
struct WatchPrototypeAuditCanvasGeometry: View {
    let size: CGSize
    let interactiveBottom: CGFloat
    var body: some View {
        if WatchPrototypeAuditProbe.enabled {
            Text("width=\(Double(size.width));height=\(Double(size.height));bottom=\(Double(interactiveBottom));")
                .font(.system(size: 1)).foregroundStyle(.clear)
                .frame(width: 1, height: 1).allowsHitTesting(false)
                .accessibilityIdentifier("proto-audit-canvas-geometry")
        }
    }
}

/// A temporary 2pt row locates the native cutoff; it does not validate original controls.
struct WatchPrototypeBoundaryLayer: View {
    @State private var count = 0
    var body: some View {
        GeometryReader { proxy in
            let frame = proxy.frame(in: .global)
            ZStack(alignment: .topLeading) {
                Button {
                    count += 1
                    WatchPrototypeAuditProbe.action("proto-boundary-row", fields: ["count": count])
                } label: {
                    Rectangle().fill(Color.pink.opacity(0.7))
                        .frame(width: proxy.size.width, height: 2).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .frame(width: proxy.size.width, height: 2)
                .position(x: proxy.size.width / 2, y: WatchPrototypeAuditProbe.boundaryY - frame.minY)
                .accessibilityIdentifier("proto-boundary-row")
                Text("count=\(count);").font(.system(size: 1)).foregroundStyle(.clear)
                    .frame(width: 1, height: 1).allowsHitTesting(false)
                    .accessibilityIdentifier("proto-boundary-count")
            }
            .background { WatchPrototypeAuditProbe.geometry("boundary-layer", proxy: proxy) }
        }
    }
}
#endif
