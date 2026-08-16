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
        size: CGSize
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
        let scale = max(
            0.01,
            min(contentRect.width / max(padded.width, 1), contentRect.height / max(padded.height, 1))
        )
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
            let viewport = WatchGreenPreviewLayout.viewport(geometry: geometry, size: proxy.size)
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

                if !canMoveFlag {
                    Text("无果岭轮廓")
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(.white.opacity(0.7))
                        .position(x: safeRect.midX, y: safeRect.midY)
                }
            }
            .contentShape(Rectangle())
            .gesture(flagGesture(viewport: viewport))
        }
        .background(Color.black)
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

    private func drawGreen(
        _ context: inout GraphicsContext,
        size: CGSize,
        viewport: WatchGreenViewport
    ) {
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))

        if geometry.greenOutlinePx.count >= 3 {
            var outline = Path()
            outline.move(to: viewport.canvasPoint(geometry.greenOutlinePx[0]))
            for point in geometry.greenOutlinePx.dropFirst() {
                outline.addLine(to: viewport.canvasPoint(point))
            }
            outline.closeSubpath()
            context.fill(
                outline,
                with: .color(Color(red: 0.35, green: 0.82, blue: 0.29).opacity(0.98))
            )
            context.stroke(
                outline,
                with: .color(Color(red: 0.16, green: 0.49, blue: 0.18)),
                style: StrokeStyle(lineWidth: 1.1, lineJoin: .round)
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
