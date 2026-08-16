import SwiftUI

struct WatchGreenViewport: Equatable {
    let scale: CGFloat
    let imageOrigin: CGPoint

    func canvasPoint(_ imagePoint: CGPoint) -> CGPoint {
        CGPoint(
            x: imageOrigin.x + imagePoint.x * scale,
            y: imageOrigin.y + imagePoint.y * scale
        )
    }

    func imagePoint(_ canvasPoint: CGPoint) -> CGPoint {
        CGPoint(
            x: (canvasPoint.x - imageOrigin.x) / scale,
            y: (canvasPoint.y - imageOrigin.y) / scale
        )
    }
}

enum WatchGreenPreviewLayout {
    static func viewport(
        geometry: WatchHoleMapGeometry,
        size: CGSize,
        zoom: CGFloat = 1
    ) -> WatchGreenViewport {
        let safeRect = WatchDisplayGeometry.contentRect(in: size)
        let contentRect = CGRect(
            x: safeRect.minX,
            y: safeRect.minY + 26,
            width: safeRect.width,
            height: max(44, safeRect.height - 70)
        )
        let focus = focusBounds(geometry: geometry)
        let longestSide = max(focus.width, focus.height, 1)
        let padding = max(5, longestSide * 0.16)
        let padded = focus.insetBy(dx: -padding, dy: -padding)
        let fittedScale = max(
            0.01,
            min(contentRect.width / max(padded.width, 1), contentRect.height / max(padded.height, 1))
        )
        let scale = fittedScale * min(max(zoom, 1), 2)
        let origin = CGPoint(
            x: contentRect.midX - padded.midX * scale,
            y: contentRect.midY - padded.midY * scale
        )
        return WatchGreenViewport(scale: scale, imageOrigin: origin)
    }

    static func contains(_ point: CGPoint, polygon: [CGPoint]) -> Bool {
        guard polygon.count >= 3, point.x.isFinite, point.y.isFinite else { return false }
        var inside = false
        var previous = polygon.count - 1
        for current in polygon.indices {
            let a = polygon[current]
            let b = polygon[previous]
            let crossesY = (a.y > point.y) != (b.y > point.y)
            if crossesY {
                let denominator = b.y - a.y
                if abs(denominator) > 0.000_001 {
                    let edgeX = (b.x - a.x) * (point.y - a.y) / denominator + a.x
                    if point.x < edgeX { inside.toggle() }
                }
            }
            previous = current
        }
        return inside
    }

    /// The downloaded green boundary is intentionally lightweight and commonly contains only six to
    /// ten points. A midpoint-quadratic path preserves those measured points while removing the
    /// angular "hexagon" appearance that the raw line segments produced.
    static func smoothPath(
        polygon: [CGPoint],
        transform: (CGPoint) -> CGPoint = { $0 }
    ) -> Path {
        let points = polygon
            .filter { $0.x.isFinite && $0.y.isFinite }
            .map(transform)
        guard points.count >= 3 else { return Path() }

        func midpoint(_ lhs: CGPoint, _ rhs: CGPoint) -> CGPoint {
            CGPoint(x: (lhs.x + rhs.x) * 0.5, y: (lhs.y + rhs.y) * 0.5)
        }

        var path = Path()
        path.move(to: midpoint(points[points.count - 1], points[0]))
        for index in points.indices {
            let current = points[index]
            let next = points[(index + 1) % points.count]
            path.addQuadCurve(to: midpoint(current, next), control: current)
        }
        path.closeSubpath()
        return path
    }

    private static func focusBounds(geometry: WatchHoleMapGeometry) -> CGRect {
        let points = geometry.greenOutlinePx.filter { $0.x.isFinite && $0.y.isFinite }
        guard let first = points.first else {
            let side = max(36, min(geometry.imageSize.width, geometry.imageSize.height) * 0.08)
            return CGRect(
                x: geometry.pinPx.x - side * 0.5,
                y: geometry.pinPx.y - side * 0.5,
                width: side,
                height: side
            )
        }
        var minX = first.x
        var maxX = first.x
        var minY = first.y
        var maxY = first.y
        for point in points.dropFirst() {
            minX = min(minX, point.x)
            maxX = max(maxX, point.x)
            minY = min(minY, point.y)
            maxY = max(maxY, point.y)
        }
        return CGRect(
            x: minX,
            y: minY,
            width: max(maxX - minX, 1),
            height: max(maxY - minY, 1)
        )
    }
}

/// S70-style View Green: the real green outline is the entire instrument, with one distance and a
/// draggable temporary flag. Hole topo, cards, titles and explanatory copy deliberately disappear.
/// The current live-round contract has no independent `flag_position_set` event yet, so leaving this
/// instrument restores the canonical pin.
public struct WatchGreenPreviewView: View {
    public let geometry: WatchHoleMapGeometry
    public let centerGreenYards: Int?
    public let onBack: () -> Void

    @State private var temporaryPin: CGPoint?
    @State private var zoomScale = 1.0

    public init(
        geometry: WatchHoleMapGeometry,
        centerGreenYards: Int? = nil,
        onBack: @escaping () -> Void = {}
    ) {
        self.geometry = geometry
        self.centerGreenYards = centerGreenYards
        self.onBack = onBack
    }

    public var body: some View {
        GeometryReader { proxy in
            let viewport = WatchGreenPreviewLayout.viewport(
                geometry: geometry,
                size: proxy.size,
                zoom: CGFloat(zoomScale)
            )
            let safeRect = WatchDisplayGeometry.contentRect(in: proxy.size)
            ZStack {
                Canvas { context, size in
                    drawGreen(&context, size: size, viewport: viewport)
                }

                if let distanceText {
                    Text(distanceText)
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.white)
                        .position(x: safeRect.midX, y: safeRect.minY + 13)
                        .accessibilityLabel("到旗 \(distanceText) 码")
                }

                WatchInstrumentBackButton(accessibilityLabel: "返回菜单", onBack: onBack)
                    .position(x: safeRect.minX + 22, y: safeRect.maxY - 22)

                if zoomScale > 1.02 {
                    ZStack(alignment: .bottom) {
                        Capsule()
                            .fill(.white.opacity(0.22))
                            .frame(width: 3, height: min(86, safeRect.height * 0.42))
                        Capsule()
                            .fill(.white.opacity(0.9))
                            .frame(width: 3, height: 24)
                            .offset(y: -CGFloat((zoomScale - 1) * 36))
                    }
                    .position(x: safeRect.maxX - 4, y: safeRect.midY)
                }

                if !canMoveFlag {
                    Text("无果岭轮廓")
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(.white.opacity(0.7))
                        .position(x: safeRect.midX, y: safeRect.midY)
                }
            }
            .contentShape(Rectangle())
            .gesture(flagGesture(viewport: viewport))
            .simultaneousGesture(
                SpatialTapGesture().onEnded { value in
                    moveFlag(to: value.location, viewport: viewport)
                }
            )
        }
        .background(Color.black)
        .focusable(true)
        .digitalCrownRotation(
            $zoomScale,
            from: 1,
            through: 2,
            by: 0.1,
            sensitivity: .medium,
            isContinuous: false,
            isHapticFeedbackEnabled: true
        )
        .ignoresSafeArea()
        .simultaneousGesture(
            DragGesture(minimumDistance: 24)
                .onEnded { value in
                    guard WatchEdgeBackGesture.shouldTrigger(
                        startX: value.startLocation.x,
                        translation: value.translation
                    ) else { return }
                    onBack()
                }
        )
        .accessibilityAction(named: Text("返回菜单"), onBack)
    }

    private var pin: CGPoint { temporaryPin ?? geometry.pinPx }
    private var canMoveFlag: Bool { geometry.greenOutlinePx.count >= 3 }

    private var distanceText: String? {
        guard let centerGreenYards,
              centerGreenYards > 0,
              centerGreenYards <= WatchGeoMath.maximumUsefulGreenYards else { return nil }
        let referenceSpan = hypot(
            geometry.pinPx.x - geometry.youPx.x,
            geometry.pinPx.y - geometry.youPx.y
        )
        guard referenceSpan > 1 else { return nil }
        let yardsPerPixel = CGFloat(centerGreenYards) / referenceSpan
        let yards = Int((hypot(pin.x - geometry.youPx.x, pin.y - geometry.youPx.y) * yardsPerPixel).rounded())
        return "\(yards)"
    }

    private func flagGesture(viewport: WatchGreenViewport) -> some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                guard canMoveFlag else { return }
                let flagCanvas = viewport.canvasPoint(pin)
                guard hypot(
                    value.startLocation.x - flagCanvas.x,
                    value.startLocation.y - flagCanvas.y
                ) <= 36 else { return }
                let candidate = viewport.imagePoint(value.location)
                guard WatchGreenPreviewLayout.contains(
                    candidate,
                    polygon: geometry.greenOutlinePx
                ) else { return }
                temporaryPin = candidate
            }
    }

    private func moveFlag(to canvasPoint: CGPoint, viewport: WatchGreenViewport) {
        guard canMoveFlag else { return }
        let candidate = viewport.imagePoint(canvasPoint)
        guard WatchGreenPreviewLayout.contains(
            candidate,
            polygon: geometry.greenOutlinePx
        ) else { return }
        temporaryPin = candidate
    }

    private func drawGreen(
        _ context: inout GraphicsContext,
        size: CGSize,
        viewport: WatchGreenViewport
    ) {
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))

        if geometry.greenOutlinePx.count >= 3 {
            let outline = WatchGreenPreviewLayout.smoothPath(
                polygon: geometry.greenOutlinePx,
                transform: viewport.canvasPoint
            )
            let bounds = outline.boundingRect
            context.fill(
                outline,
                with: .linearGradient(
                    Gradient(colors: [
                        Color(red: 0.43, green: 0.93, blue: 0.22),
                        Color(red: 0.24, green: 0.78, blue: 0.18),
                    ]),
                    startPoint: CGPoint(x: bounds.midX, y: bounds.minY),
                    endPoint: CGPoint(x: bounds.midX, y: bounds.maxY)
                )
            )
            // This is a neutral instrument grid, not invented slope/contour data. It provides the
            // same move-the-pin spatial cue as S70 while the actual measured outline remains the
            // only course geometry shown.
            context.drawLayer { layer in
                layer.clip(to: outline)
                var grid = Path()
                grid.move(to: CGPoint(x: bounds.midX, y: bounds.minY))
                grid.addLine(to: CGPoint(x: bounds.midX, y: bounds.maxY))
                grid.move(to: CGPoint(x: bounds.minX, y: bounds.midY))
                grid.addLine(to: CGPoint(x: bounds.maxX, y: bounds.midY))
                layer.stroke(
                    grid,
                    with: .color(.white.opacity(0.18)),
                    style: StrokeStyle(lineWidth: 0.8)
                )
            }
            context.stroke(
                outline,
                with: .color(.white.opacity(0.28)),
                style: StrokeStyle(lineWidth: 1.0, lineJoin: .round)
            )
        }

        let flagPoint = viewport.canvasPoint(pin)
        let radius: CGFloat = 5
        let marker = CGRect(
            x: flagPoint.x - radius,
            y: flagPoint.y - radius,
            width: radius * 2,
            height: radius * 2
        )
        context.fill(Path(ellipseIn: marker), with: .color(.white))
        var pole = Path()
        pole.move(to: CGPoint(x: flagPoint.x - 1, y: flagPoint.y + 3))
        pole.addLine(to: CGPoint(x: flagPoint.x - 1, y: flagPoint.y - 4))
        context.stroke(pole, with: .color(Color(red: 0.94, green: 0.20, blue: 0.18)), style: StrokeStyle(lineWidth: 1))
        var flag = Path()
        flag.move(to: CGPoint(x: flagPoint.x - 1, y: flagPoint.y - 4))
        flag.addLine(to: CGPoint(x: flagPoint.x + 4, y: flagPoint.y - 2.5))
        flag.addLine(to: CGPoint(x: flagPoint.x - 1, y: flagPoint.y - 1))
        flag.closeSubpath()
        context.fill(flag, with: .color(Color(red: 0.94, green: 0.28, blue: 0.24)))
    }
}
