import SwiftUI

/// B6 本洞 pages: the Digital Crown zooms the page (1–4×) and, once zoomed, a drag pans it. Unzoomed
/// the page installs no drag, so the vertical page swipe and taps keep working.
struct WatchZoomPanModifier: ViewModifier {
    @Binding var viewport: WatchHoleViewport
    let size: CGSize
    let auditTag: String
    @State private var crown: Double = 1
    @State private var dragStart: CGSize?

    func body(content: Content) -> some View {
        content
            .focusable(true)
            .digitalCrownRotation(
                $crown,
                from: Double(WatchHoleZoom.range.lowerBound),
                through: Double(WatchHoleZoom.range.upperBound),
                by: 0.05,
                sensitivity: .medium,
                isContinuous: false,
                isHapticFeedbackEnabled: true
            )
            .onChange(of: crown) { _, value in
                viewport.setZoom(CGFloat(value), viewport: size)
            }
            .onChange(of: viewport.zoom) { _, zoom in
                // A reset from outside (new hole) brings the Crown back with it.
                if abs(Double(zoom) - crown) > 0.001 { crown = Double(zoom) }
            }
            .highPriorityGesture(
                DragGesture(minimumDistance: 4)
                    .onChanged { value in
                        let start = dragStart ?? viewport.pan
                        dragStart = start
                        viewport.setPan(
                            CGSize(width: start.width + value.translation.width,
                                   height: start.height + value.translation.height),
                            viewport: size
                        )
                    }
                    .onEnded { _ in dragStart = nil },
                including: viewport.isZoomed ? .all : .subviews
            )
            #if DEBUG
            .overlay(alignment: .topLeading) {
                if ProcessInfo.processInfo.environment["UITEST_AUDIT_ANCHORS"] == "1" {
                    Text("zoom=\(viewport.zoom);panX=\(viewport.pan.width);panY=\(viewport.pan.height);")
                        .font(.system(size: 1)).foregroundStyle(.clear)
                        .frame(width: 2, height: 2).allowsHitTesting(false)
                        .accessibilityIdentifier("watch-audit-viewport-\(auditTag)")
                }
            }
            #endif
    }
}

extension View {
    func watchZoomPan(_ viewport: Binding<WatchHoleViewport>, size: CGSize, auditTag: String = "default") -> some View {
        modifier(WatchZoomPanModifier(viewport: viewport, size: size, auditTag: auditTag))
    }
}
