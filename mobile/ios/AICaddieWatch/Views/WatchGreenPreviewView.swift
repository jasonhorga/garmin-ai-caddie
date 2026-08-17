import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

struct WatchGreenViewport: Equatable {
    let scale: CGFloat
    let imageOrigin: CGPoint
    let rotationCenterCanvas: CGPoint
    let rotationRadians: CGFloat

    private func rotated(_ point: CGPoint, radians: CGFloat) -> CGPoint {
        let dx = point.x - rotationCenterCanvas.x
        let dy = point.y - rotationCenterCanvas.y
        let cosine = cos(radians)
        let sine = sin(radians)
        return CGPoint(
            x: rotationCenterCanvas.x + dx * cosine - dy * sine,
            y: rotationCenterCanvas.y + dx * sine + dy * cosine
        )
    }

    func canvasPoint(_ imagePoint: CGPoint) -> CGPoint {
        rotated(CGPoint(
            x: imageOrigin.x + imagePoint.x * scale,
            y: imageOrigin.y + imagePoint.y * scale
        ), radians: rotationRadians)
    }

    func imagePoint(_ canvasPoint: CGPoint) -> CGPoint {
        let unrotated = rotated(canvasPoint, radians: -rotationRadians)
        return CGPoint(
            x: (unrotated.x - imageOrigin.x) / scale,
            y: (unrotated.y - imageOrigin.y) / scale
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
        zoom: CGFloat = 1,
        rotationDegrees: Double = 0
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
        let rotationRadians = CGFloat(rotationDegrees * .pi / 180)
        let rotationCenterCanvas = CGPoint(x: contentRect.midX, y: contentRect.midY)
        let rotationCenterImage = CGPoint(x: padded.midX, y: padded.midY)

        // Rotation must never reveal synthetic black wedges. Keep the real green centred, inverse-
        // rotate all four display corners, and increase only the minimum fill scale needed for those
        // corners to remain inside the downloaded image. Crown zoom then remains a pure magnification.
        let corners = [
            CGPoint(x: 0, y: 0), CGPoint(x: size.width, y: 0),
            CGPoint(x: size.width, y: size.height), CGPoint(x: 0, y: size.height),
        ]
        func inverseRotatedOffset(_ point: CGPoint) -> CGPoint {
            let dx = point.x - rotationCenterCanvas.x
            let dy = point.y - rotationCenterCanvas.y
            let cosine = cos(rotationRadians)
            let sine = sin(rotationRadians)
            return CGPoint(x: dx * cosine + dy * sine, y: -dx * sine + dy * cosine)
        }
        var coverageScale: CGFloat = 0.01
        for corner in corners.map(inverseRotatedOffset) {
            if corner.x < 0, rotationCenterImage.x > 0 {
                coverageScale = max(coverageScale, -corner.x / rotationCenterImage.x)
            } else if corner.x > 0, geometry.imageSize.width > rotationCenterImage.x {
                coverageScale = max(
                    coverageScale,
                    corner.x / (geometry.imageSize.width - rotationCenterImage.x)
                )
            }
            if corner.y < 0, rotationCenterImage.y > 0 {
                coverageScale = max(coverageScale, -corner.y / rotationCenterImage.y)
            } else if corner.y > 0, geometry.imageSize.height > rotationCenterImage.y {
                coverageScale = max(
                    coverageScale,
                    corner.y / (geometry.imageSize.height - rotationCenterImage.y)
                )
            }
        }
        let scale = max(
            fittedScale * min(max(zoom, 1), 2),
            coverageScale * 1.002
        )
        let origin = CGPoint(
            x: rotationCenterCanvas.x - rotationCenterImage.x * scale,
            y: rotationCenterCanvas.y - rotationCenterImage.y * scale
        )
        return WatchGreenViewport(
            scale: scale,
            imageOrigin: origin,
            rotationCenterCanvas: rotationCenterCanvas,
            rotationRadians: rotationRadians
        )
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

    /// Sample the same midpoint-quadratic boundary that is displayed. Hit testing, four-axis rays and
    /// drawing all consume this polygon, eliminating the old raw-polygon/smoothed-outline mismatch.
    static func boundaryPolygon(
        _ polygon: [CGPoint],
        samplesPerCurve: Int = 12
    ) -> [CGPoint] {
        let points = polygon.filter { $0.x.isFinite && $0.y.isFinite }
        guard points.count >= 3 else { return points }
        let samples = max(samplesPerCurve, 2)
        func midpoint(_ lhs: CGPoint, _ rhs: CGPoint) -> CGPoint {
            CGPoint(x: (lhs.x + rhs.x) * 0.5, y: (lhs.y + rhs.y) * 0.5)
        }
        func quadratic(_ start: CGPoint, _ control: CGPoint, _ end: CGPoint, _ t: CGFloat) -> CGPoint {
            let inverse = 1 - t
            return CGPoint(
                x: inverse * inverse * start.x + 2 * inverse * t * control.x + t * t * end.x,
                y: inverse * inverse * start.y + 2 * inverse * t * control.y + t * t * end.y
            )
        }

        var sampled: [CGPoint] = []
        sampled.reserveCapacity(points.count * samples)
        for index in points.indices {
            let previous = points[(index + points.count - 1) % points.count]
            let current = points[index]
            let next = points[(index + 1) % points.count]
            let start = midpoint(previous, current)
            let end = midpoint(current, next)
            if sampled.isEmpty { sampled.append(start) }
            for sample in 1...samples {
                sampled.append(quadratic(start, current, end, CGFloat(sample) / CGFloat(samples)))
            }
        }
        // The last sample closes onto the first. Path and intersection code close explicitly.
        if let first = sampled.first, let last = sampled.last,
           hypot(first.x - last.x, first.y - last.y) < 0.000_1 {
            sampled.removeLast()
        }
        return sampled
    }

    static func rotationCenter(polygon: [CGPoint]) -> CGPoint {
        let points = polygon.filter { $0.x.isFinite && $0.y.isFinite }
        guard let first = points.first else { return .zero }
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
        return CGPoint(x: (minX + maxX) * 0.5, y: (minY + maxY) * 0.5)
    }

    static func rotated(_ point: CGPoint, around center: CGPoint, degrees: Double) -> CGPoint {
        let radians = CGFloat(degrees * .pi / 180)
        let cosine = cos(radians)
        let sine = sin(radians)
        let dx = point.x - center.x
        let dy = point.y - center.y
        return CGPoint(
            x: center.x + dx * cosine - dy * sine,
            y: center.y + dx * sine + dy * cosine
        )
    }

    /// Resolve the selected flag's live distance plus its four directional clearances to the real
    /// downloaded green boundary. The current wrist→canonical-centre GPS range calibrates topo px to
    /// yards; all five values then update from the same selected flag point.
    static func pinMetrics(
        playerImagePoint: CGPoint,
        canonicalPinImagePoint: CGPoint,
        selectedPinImagePoint: CGPoint,
        greenOutline: [CGPoint],
        centerGreenYards: Int?,
        rotationDegrees: Double = 0
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

        let boundary = boundaryPolygon(greenOutline)
        let center = rotationCenter(polygon: boundary)
        let rotatedPin = rotated(selectedPinImagePoint, around: center, degrees: rotationDegrees)
        let rotatedBoundary = boundary.map {
            rotated($0, around: center, degrees: rotationDegrees)
        }
        let edges = contains(selectedPinImagePoint, polygon: boundary)
            ? edgeMeasurements(
                pin: rotatedPin,
                polygon: rotatedBoundary,
                yardsPerPixel: yardsPerPixel
            ).map { measurement in
                WatchGreenEdgeMeasurement(
                    direction: measurement.direction,
                    yards: measurement.yards,
                    edgeImagePoint: rotated(
                        measurement.edgeImagePoint,
                        around: center,
                        degrees: -rotationDegrees
                    )
                )
            }
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
    /// ten points. Render the sampled measurement boundary rather than a second geometric authority.
    static func smoothPath(
        polygon: [CGPoint],
        transform: (CGPoint) -> CGPoint = { $0 }
    ) -> Path {
        let points = boundaryPolygon(polygon).map(transform)
        guard points.count >= 3 else { return Path() }
        var path = Path()
        path.move(to: points[0])
        for point in points.dropFirst() { path.addLine(to: point) }
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

private struct WatchGreenCrownModifier: ViewModifier {
    @Binding var zoomScale: Double
    @Binding var rotationDegrees: Double
    let rotatesGreen: Bool

    @ViewBuilder
    func body(content: Content) -> some View {
        if rotatesGreen {
            content.digitalCrownRotation(
                $rotationDegrees,
                from: -180,
                through: 180,
                by: 1,
                sensitivity: .medium,
                isContinuous: true,
                isHapticFeedbackEnabled: true
            )
        } else {
            content.digitalCrownRotation(
                $zoomScale,
                from: 1,
                through: 2,
                by: 0.1,
                sensitivity: .medium,
                isContinuous: false,
                isHapticFeedbackEnabled: true
            )
        }
    }
}

/// S70-style View Green: enlarge the real green within its nearby topo context, with a live distance,
/// four flag-to-edge clearances and a draggable round-scoped flag. Cards, titles and explanatory copy
/// disappear, but the approach apron and adjacent hazards remain visible around the green. Crown zoom
/// is the default; the compact rotate control temporarily maps Crown input to paper-pin-sheet alignment.
public struct WatchGreenPreviewView: View {
    public let geometry: WatchHoleMapGeometry
    public let centerGreenYards: Int?
    public let onBack: () -> Void
    public let onPlacementChange: (CGPoint, Double) -> Void

    @State private var selectedPin: CGPoint?
    @State private var zoomScale = 1.0
    @State private var rotationDegrees = 0.0
    @State private var rotatesGreen = false
    @State private var persistenceTask: Task<Void, Never>?
    @State private var placementChanged = false
    @State private var isDraggingFlag = false

    public init(
        geometry: WatchHoleMapGeometry,
        centerGreenYards: Int? = nil,
        initialPin: CGPoint? = nil,
        initialZoomScale: Double = 1,
        initialRotationDegrees: Double = 0,
        onPlacementChange: @escaping (CGPoint, Double) -> Void = { _, _ in },
        onBack: @escaping () -> Void = {}
    ) {
        self.geometry = geometry
        self.centerGreenYards = centerGreenYards
        self.onPlacementChange = onPlacementChange
        self.onBack = onBack
        let boundary = WatchGreenPreviewLayout.boundaryPolygon(geometry.greenOutlinePx)
        _selectedPin = State(initialValue: initialPin.flatMap {
            WatchGreenPreviewLayout.contains($0, polygon: boundary) ? $0 : nil
        })
        _zoomScale = State(initialValue: min(max(initialZoomScale, 1), 2))
        _rotationDegrees = State(initialValue: WatchRoundModel.wrappedGreenRotation(initialRotationDegrees))
    }

    public var body: some View {
        GeometryReader { proxy in
            let viewport = WatchGreenPreviewLayout.viewport(
                geometry: geometry,
                size: proxy.size,
                zoom: CGFloat(zoomScale),
                rotationDegrees: rotationDegrees
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

                if !rotatesGreen, zoomScale > 1.02 {
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

                Button {
                    rotatesGreen.toggle()
                } label: {
                    Group {
                        if rotatesGreen {
                            Text("\(Int(rotationDegrees.rounded()))°")
                                .font(.system(size: 8.5, weight: .bold, design: .rounded))
                                .monospacedDigit()
                        } else {
                            Image(systemName: "rotate.right")
                                .font(.system(size: 11, weight: .bold))
                        }
                    }
                    .foregroundStyle(rotatesGreen ? Color.black : Color.white)
                    .frame(width: 26, height: 26)
                    .background(
                        rotatesGreen ? Color.yellow : Color.black.opacity(0.72),
                        in: Circle()
                    )
                    .overlay(Circle().stroke(.white.opacity(0.28), lineWidth: 0.8))
                    .frame(width: 40, height: 40)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .position(x: safeRect.maxX - 22, y: safeRect.maxY - 22)
                .accessibilityLabel(rotatesGreen ? "旋转果岭，当前 \(Int(rotationDegrees.rounded())) 度" : "旋转果岭")
                .accessibilityHint(rotatesGreen ? "转动数码表冠调整方向，再点按返回缩放" : "点按后转动数码表冠")

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
        .modifier(
            WatchGreenCrownModifier(
                zoomScale: $zoomScale,
                rotationDegrees: $rotationDegrees,
                rotatesGreen: rotatesGreen
            )
        )
        .onChange(of: rotationDegrees) { _ in schedulePlacementPersistence() }
        .onDisappear {
            persistenceTask?.cancel()
            if placementChanged { persistPlacement() }
        }
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

    private var pin: CGPoint { selectedPin ?? geometry.pinPx }
    private var canMoveFlag: Bool { geometry.greenOutlinePx.count >= 3 }

    private var pinMetrics: WatchGreenPinMetrics? {
        WatchGreenPreviewLayout.pinMetrics(
            playerImagePoint: geometry.youPx,
            canonicalPinImagePoint: geometry.pinPx,
            selectedPinImagePoint: pin,
            greenOutline: geometry.greenOutlinePx,
            centerGreenYards: centerGreenYards,
            rotationDegrees: rotationDegrees
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
                if !isDraggingFlag {
                    let flagCanvas = viewport.canvasPoint(pin)
                    guard hypot(
                        value.startLocation.x - flagCanvas.x,
                        value.startLocation.y - flagCanvas.y
                    ) <= 36 else { return }
                    isDraggingFlag = true
                }
                let candidate = viewport.imagePoint(value.location)
                guard WatchGreenPreviewLayout.contains(
                    candidate,
                    polygon: WatchGreenPreviewLayout.boundaryPolygon(geometry.greenOutlinePx)
                ) else { return }
                selectedPin = candidate
                placementChanged = true
            }
            .onEnded { value in
                guard canMoveFlag, isDraggingFlag else { return }
                isDraggingFlag = false
                let candidate = viewport.imagePoint(value.location)
                if WatchGreenPreviewLayout.contains(
                    candidate,
                    polygon: WatchGreenPreviewLayout.boundaryPolygon(geometry.greenOutlinePx)
                ) {
                    selectedPin = candidate
                    persistPlacement(pin: candidate)
                } else {
                    persistPlacement()
                }
            }
    }

    private func moveFlag(to canvasPoint: CGPoint, viewport: WatchGreenViewport) {
        guard canMoveFlag else { return }
        let candidate = viewport.imagePoint(canvasPoint)
        guard WatchGreenPreviewLayout.contains(
            candidate,
            polygon: WatchGreenPreviewLayout.boundaryPolygon(geometry.greenOutlinePx)
        ) else { return }
        selectedPin = candidate
        placementChanged = true
        persistPlacement(pin: candidate)
    }

    private func schedulePlacementPersistence() {
        placementChanged = true
        persistenceTask?.cancel()
        persistenceTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 350_000_000)
            guard !Task.isCancelled else { return }
            persistPlacement()
        }
    }

    private func persistPlacement(pin selectedPin: CGPoint? = nil) {
        let selectedPin = selectedPin ?? pin
        guard placementChanged, selectedPin.x.isFinite, selectedPin.y.isFinite else { return }
        placementChanged = false
        onPlacementChange(selectedPin, rotationDegrees)
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
                context.drawLayer { layer in
                    layer.translateBy(
                        x: viewport.rotationCenterCanvas.x,
                        y: viewport.rotationCenterCanvas.y
                    )
                    layer.rotate(by: .radians(Double(viewport.rotationRadians)))
                    layer.translateBy(
                        x: -viewport.rotationCenterCanvas.x,
                        y: -viewport.rotationCenterCanvas.y
                    )
                    layer.draw(layer.resolve(Image(uiImage: image)), in: rect)
                }
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
