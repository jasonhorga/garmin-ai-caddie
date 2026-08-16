import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

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

enum WatchGreenEdgeDirection: CaseIterable, Equatable {
    case top
    case right
    case bottom
    case left
}

struct WatchGreenEdgeMeasurement: Equatable {
    let direction: WatchGreenEdgeDirection
    let yards: Int
    let edgeImagePoint: CGPoint
}

struct WatchGreenPinMetrics: Equatable {
    let playerToPinYards: Int
    let edges: [WatchGreenEdgeMeasurement]

    func edge(_ direction: WatchGreenEdgeDirection) -> WatchGreenEdgeMeasurement? {
        edges.first { $0.direction == direction }
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
        // View Green is a tighter level than Hole Root, but Garmin still keeps the approach apron and
        // adjacent hazards around the enlarged green. This crop includes the real nearby bunker at
        // the default Crown detent; zooming never turns the surrounding map into a black cut-out.
        let padding = max(12, longestSide * 0.40)
        let padded = focus.insetBy(dx: -padding, dy: -padding)
        let fittedScale = max(
            0.01,
            min(contentRect.width / max(padded.width, 1), contentRect.height / max(padded.height, 1))
        )
        let scale = fittedScale * min(max(zoom, 1), 2)
        let desiredOrigin = CGPoint(
            x: contentRect.midX - padded.midX * scale,
            y: contentRect.midY - padded.midY * scale
        )
        // Keep the real topo under the whole rounded display even when the green sits close to an
        // image edge. A centered crop alone can expose the Canvas' black fallback at high Crown
        // detents; clamp each axis whenever the downloaded image is large enough to cover it.
        func coveredOrigin(_ desired: CGFloat, imageLength: CGFloat, canvasLength: CGFloat) -> CGFloat {
            let renderedLength = imageLength * scale
            guard renderedLength.isFinite, renderedLength > 0 else { return desired }
            if renderedLength >= canvasLength {
                return min(max(desired, canvasLength - renderedLength), 0)
            }
            return (canvasLength - renderedLength) * 0.5
        }
        let origin = CGPoint(
            x: coveredOrigin(
                desiredOrigin.x,
                imageLength: geometry.imageSize.width,
                canvasLength: size.width
            ),
            y: coveredOrigin(
                desiredOrigin.y,
                imageLength: geometry.imageSize.height,
                canvasLength: size.height
            )
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

    /// Resolve the selected flag's live distance plus its four directional clearances to the real
    /// downloaded green boundary. The current wrist→canonical-centre GPS range calibrates topo px to
    /// yards; all five values then update from the same selected flag point.
    static func pinMetrics(
        playerImagePoint: CGPoint,
        canonicalPinImagePoint: CGPoint,
        selectedPinImagePoint: CGPoint,
        greenOutline: [CGPoint],
        centerGreenYards: Int?
    ) -> WatchGreenPinMetrics? {
        let scalarValues = [
            playerImagePoint.x, playerImagePoint.y,
            canonicalPinImagePoint.x, canonicalPinImagePoint.y,
            selectedPinImagePoint.x, selectedPinImagePoint.y,
        ]
        guard scalarValues.allSatisfy(\.isFinite),
              let centerGreenYards,
              centerGreenYards > 0,
              centerGreenYards <= WatchGeoMath.maximumUsefulGreenYards else { return nil }
        let referenceSpan = hypot(
            canonicalPinImagePoint.x - playerImagePoint.x,
            canonicalPinImagePoint.y - playerImagePoint.y
        )
        guard referenceSpan > 1 else { return nil }
        let yardsPerPixel = CGFloat(centerGreenYards) / referenceSpan
        let playerToSelected = hypot(
            selectedPinImagePoint.x - playerImagePoint.x,
            selectedPinImagePoint.y - playerImagePoint.y
        ) * yardsPerPixel
        guard playerToSelected.isFinite else { return nil }

        let edges = contains(selectedPinImagePoint, polygon: greenOutline)
            ? edgeMeasurements(
                pin: selectedPinImagePoint,
                polygon: greenOutline,
                yardsPerPixel: yardsPerPixel
            )
            : []
        return WatchGreenPinMetrics(
            playerToPinYards: Int(playerToSelected.rounded()),
            edges: edges
        )
    }

    static func edgeMeasurements(
        pin: CGPoint,
        polygon: [CGPoint],
        yardsPerPixel: CGFloat
    ) -> [WatchGreenEdgeMeasurement] {
        guard polygon.count >= 3,
              pin.x.isFinite, pin.y.isFinite,
              yardsPerPixel.isFinite, yardsPerPixel > 0 else { return [] }

        var horizontal: [CGPoint] = []
        var vertical: [CGPoint] = []
        for index in polygon.indices {
            let a = polygon[index]
            let b = polygon[(index + 1) % polygon.count]
            guard [a.x, a.y, b.x, b.y].allSatisfy(\.isFinite) else { continue }

            let dy = b.y - a.y
            if abs(dy) > 0.000_001 {
                let t = (pin.y - a.y) / dy
                if (0...1).contains(t) {
                    horizontal.append(CGPoint(x: a.x + (b.x - a.x) * t, y: pin.y))
                }
            }

            let dx = b.x - a.x
            if abs(dx) > 0.000_001 {
                let t = (pin.x - a.x) / dx
                if (0...1).contains(t) {
                    vertical.append(CGPoint(x: pin.x, y: a.y + (b.y - a.y) * t))
                }
            }
        }

        let epsilon: CGFloat = 0.000_1
        let candidates: [(WatchGreenEdgeDirection, CGPoint?)] = [
            (.top, vertical.filter { $0.y < pin.y - epsilon }.max { $0.y < $1.y }),
            (.right, horizontal.filter { $0.x > pin.x + epsilon }.min { $0.x < $1.x }),
            (.bottom, vertical.filter { $0.y > pin.y + epsilon }.min { $0.y < $1.y }),
            (.left, horizontal.filter { $0.x < pin.x - epsilon }.max { $0.x < $1.x }),
        ]
        return candidates.compactMap { direction, point in
            guard let point else { return nil }
            let yards = hypot(point.x - pin.x, point.y - pin.y) * yardsPerPixel
            guard yards.isFinite else { return nil }
            return WatchGreenEdgeMeasurement(
                direction: direction,
                yards: Int(yards.rounded()),
                edgeImagePoint: point
            )
        }
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

/// S70-style View Green: enlarge the real green within its nearby topo context, with a live distance,
/// four flag-to-edge clearances and a draggable temporary flag. Cards, titles and explanatory copy
/// disappear, but the approach apron and adjacent hazards remain visible around the green.
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
        initialPin: CGPoint? = nil,
        initialZoomScale: Double = 1,
        onBack: @escaping () -> Void = {}
    ) {
        self.geometry = geometry
        self.centerGreenYards = centerGreenYards
        self.onBack = onBack
        _temporaryPin = State(initialValue: initialPin.flatMap {
            WatchGreenPreviewLayout.contains($0, polygon: geometry.greenOutlinePx) ? $0 : nil
        })
        _zoomScale = State(initialValue: min(max(initialZoomScale, 1), 2))
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
                        .accessibilityLabel(metricsAccessibilityLabel ?? "到旗 \(distanceText) 码")
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

    private var pinMetrics: WatchGreenPinMetrics? {
        WatchGreenPreviewLayout.pinMetrics(
            playerImagePoint: geometry.youPx,
            canonicalPinImagePoint: geometry.pinPx,
            selectedPinImagePoint: pin,
            greenOutline: geometry.greenOutlinePx,
            centerGreenYards: centerGreenYards
        )
    }

    private var distanceText: String? {
        pinMetrics.map { "\($0.playerToPinYards)" }
    }

    private var metricsAccessibilityLabel: String? {
        guard let metrics = pinMetrics else { return nil }
        let labels: [(WatchGreenEdgeDirection, String)] = [
            (.top, "上"), (.right, "右"), (.bottom, "下"), (.left, "左"),
        ]
        let edges = labels.compactMap { direction, label in
            metrics.edge(direction).map { "\(label) \($0.yards) 码" }
        }.joined(separator: "，")
        return edges.isEmpty
            ? "到旗 \(metrics.playerToPinYards) 码"
            : "到旗 \(metrics.playerToPinYards) 码，\(edges)"
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

        var drewTopo = false
        #if canImport(UIKit)
        if let image = geometry.image {
            let rect = CGRect(
                x: viewport.imageOrigin.x,
                y: viewport.imageOrigin.y,
                width: geometry.imageSize.width * viewport.scale,
                height: geometry.imageSize.height * viewport.scale
            )
            if rect.width.isFinite, rect.height.isFinite, rect.width > 0, rect.height > 0 {
                context.draw(context.resolve(Image(uiImage: image)), in: rect)
                drewTopo = true
            }
        }
        #endif

        if geometry.greenOutlinePx.count >= 3 {
            let outline = WatchGreenPreviewLayout.smoothPath(
                polygon: geometry.greenOutlinePx,
                transform: viewport.canvasPoint
            )
            let bounds = outline.boundingRect
            if drewTopo {
                context.fill(
                    outline,
                    with: .color(Color(red: 0.45, green: 0.95, blue: 0.24).opacity(0.18))
                )
            } else {
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
            }
            // This is a neutral instrument grid, not invented slope/contour data. It provides the
            // same move-the-pin spatial cue as S70. It follows the selected flag so each line ends at
            // the same measured boundary used by the four directional yardages.
            context.drawLayer { layer in
                layer.clip(to: outline)
                var grid = Path()
                if let metrics = pinMetrics,
                   let top = metrics.edge(.top),
                   let right = metrics.edge(.right),
                   let bottom = metrics.edge(.bottom),
                   let left = metrics.edge(.left) {
                    grid.move(to: viewport.canvasPoint(top.edgeImagePoint))
                    grid.addLine(to: viewport.canvasPoint(bottom.edgeImagePoint))
                    grid.move(to: viewport.canvasPoint(left.edgeImagePoint))
                    grid.addLine(to: viewport.canvasPoint(right.edgeImagePoint))
                } else {
                    grid.move(to: CGPoint(x: bounds.midX, y: bounds.minY))
                    grid.addLine(to: CGPoint(x: bounds.midX, y: bounds.maxY))
                    grid.move(to: CGPoint(x: bounds.minX, y: bounds.midY))
                    grid.addLine(to: CGPoint(x: bounds.maxX, y: bounds.midY))
                }
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

            if let metrics = pinMetrics {
                drawEdgeMeasurements(
                    &context,
                    metrics: metrics,
                    viewport: viewport,
                    size: size
                )
            }
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

    private func drawEdgeMeasurements(
        _ context: inout GraphicsContext,
        metrics: WatchGreenPinMetrics,
        viewport: WatchGreenViewport,
        size: CGSize
    ) {
        let flagCanvas = viewport.canvasPoint(pin)
        let safeRect = WatchDisplayGeometry.contentRect(in: size)
        for measurement in metrics.edges {
            let edge = viewport.canvasPoint(measurement.edgeImagePoint)
            let dx = flagCanvas.x - edge.x
            let dy = flagCanvas.y - edge.y
            let length = max(hypot(dx, dy), 1)
            let inset = min(10, length * 0.36)
            let rawPoint = CGPoint(
                x: edge.x + dx / length * inset,
                y: edge.y + dy / length * inset
            )
            let point = CGPoint(
                x: min(max(rawPoint.x, safeRect.minX + 12), safeRect.maxX - 14),
                y: min(max(rawPoint.y, safeRect.minY + 31), safeRect.maxY - 32)
            )
            let black = context.resolve(
                Text("\(measurement.yards)")
                    .font(.system(size: 9, weight: .heavy, design: .rounded))
                    .foregroundColor(.black.opacity(0.9))
            )
            for offset in [
                CGPoint(x: -1, y: 0), CGPoint(x: 1, y: 0),
                CGPoint(x: 0, y: -1), CGPoint(x: 0, y: 1),
            ] {
                context.draw(black, at: CGPoint(x: point.x + offset.x, y: point.y + offset.y))
            }
            context.draw(
                context.resolve(
                    Text("\(measurement.yards)")
                        .font(.system(size: 9, weight: .heavy, design: .rounded))
                        .foregroundColor(.white)
                ),
                at: point
            )
        }
    }
}
