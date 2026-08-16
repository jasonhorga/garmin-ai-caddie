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
            y: safeRect.minY + 34,
            width: safeRect.width,
            height: max(44, safeRect.height - 66)
        )
        let focus = focusBounds(geometry: geometry)
        let longestSide = max(focus.width, focus.height, 1)
        let padding = max(8, longestSide * 0.38)
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

/// Honest first step toward S70 View Green. It magnifies the real topo/green outline and lets the
/// player inspect a temporary flag position. The current live-round contract has no independent
/// `flag_position_set` event yet, so leaving this instrument deliberately restores the canonical pin.
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
                    drawMap(&context, size: size, viewport: viewport)
                }

                HStack(spacing: 0) {
                    WatchInstrumentBackButton(accessibilityLabel: "返回菜单", onBack: onBack)
                    Text("查看果岭")
                        .font(.system(size: 13, weight: .bold))
                        .lineLimit(1)
                    Spacer(minLength: 46)
                }
                .frame(width: safeRect.width, height: 44)
                .position(x: safeRect.midX, y: safeRect.minY + 22)

                VStack(spacing: 2) {
                    Spacer()
                    if let distanceText {
                        Text(distanceText)
                            .font(.system(size: 12, weight: .bold, design: .rounded))
                            .monospacedDigit()
                            .padding(.horizontal, 9)
                            .padding(.vertical, 4)
                            .background(Color.black.opacity(0.74), in: Capsule())
                    }
                    Text(canMoveFlag ? "拖动临时旗位 · 离开复原" : "当前球包没有果岭轮廓")
                        .font(.system(size: 8.5, weight: .medium))
                        .foregroundStyle(.white.opacity(0.72))
                        .lineLimit(1)
                }
                .frame(width: safeRect.width, height: safeRect.height)
                .position(x: safeRect.midX, y: safeRect.midY)
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
        return "到旗 \(yards) 码"
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

    private func drawMap(
        _ context: inout GraphicsContext,
        size: CGSize,
        viewport: WatchGreenViewport
    ) {
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))

        #if canImport(UIKit)
        if let image = geometry.image {
            let rect = CGRect(
                x: viewport.imageOrigin.x,
                y: viewport.imageOrigin.y,
                width: geometry.imageSize.width * viewport.scale,
                height: geometry.imageSize.height * viewport.scale
            )
            context.draw(context.resolve(Image(uiImage: image)), in: rect)
        }
        #endif

        if geometry.image == nil {
            context.fill(
                Path(CGRect(origin: .zero, size: size)),
                with: .color(Color(red: 0.08, green: 0.22, blue: 0.11))
            )
        }

        if geometry.greenOutlinePx.count >= 3 {
            var outline = Path()
            outline.move(to: viewport.canvasPoint(geometry.greenOutlinePx[0]))
            for point in geometry.greenOutlinePx.dropFirst() {
                outline.addLine(to: viewport.canvasPoint(point))
            }
            outline.closeSubpath()
            if geometry.image == nil {
                context.fill(
                    outline,
                    with: .color(Color(red: 0.28, green: 0.68, blue: 0.34).opacity(0.96))
                )
            }
            context.stroke(
                outline,
                with: .color(.white.opacity(0.72)),
                style: StrokeStyle(lineWidth: 1.4, lineJoin: .round)
            )
        }

        let flagPoint = viewport.canvasPoint(pin)
        let radius: CGFloat = 6
        let marker = CGRect(
            x: flagPoint.x - radius,
            y: flagPoint.y - radius,
            width: radius * 2,
            height: radius * 2
        )
        context.fill(Path(ellipseIn: marker), with: .color(.white))
        context.stroke(
            Path(ellipseIn: marker),
            with: .color(Color(red: 0.94, green: 0.28, blue: 0.24)),
            style: StrokeStyle(lineWidth: 2)
        )
        var pole = Path()
        pole.move(to: CGPoint(x: flagPoint.x, y: flagPoint.y - radius))
        pole.addLine(to: CGPoint(x: flagPoint.x, y: flagPoint.y - radius - 16))
        context.stroke(pole, with: .color(.white), style: StrokeStyle(lineWidth: 1.4))
        var flag = Path()
        flag.move(to: CGPoint(x: flagPoint.x, y: flagPoint.y - radius - 16))
        flag.addLine(to: CGPoint(x: flagPoint.x + 9, y: flagPoint.y - radius - 13))
        flag.addLine(to: CGPoint(x: flagPoint.x, y: flagPoint.y - radius - 10))
        flag.closeSubpath()
        context.fill(flag, with: .color(Color(red: 0.94, green: 0.28, blue: 0.24)))
    }
}
