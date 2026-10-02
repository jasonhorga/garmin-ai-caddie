import SwiftUI

/// B6 本洞 pages: the Digital Crown zooms the page (1–4×) and, once zoomed, a drag pans it. Unzoomed
/// the page installs no drag, so the vertical page swipe and taps keep working.
struct WatchZoomPanModifier: ViewModifier {
    @Binding var viewport: WatchHoleViewport
    let size: CGSize
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
    }
}

extension View {
    func watchZoomPan(_ viewport: Binding<WatchHoleViewport>, size: CGSize) -> some View {
        modifier(WatchZoomPanModifier(viewport: viewport, size: size))
    }
}
