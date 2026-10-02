import SwiftUI

enum WatchHazardMapLayout {
    /// The real watchOS runtime keeps drawing its clock even when this full-screen map requests
    /// hidden overlays. Reserve that top-right lane instead of centering map copy underneath it.
    static let systemTimeTrailingClearance: CGFloat = 56
    /// S70's Hazard instrument centres one obstacle rather than shrinking the whole hole until both
    /// the player and obstacle fit. Target roughly a 26-point measured front/back span (about 52
    /// physical pixels on current Watches), while retaining enough green/fairway context to show
    /// where the obstacle actually sits.
    static let minimumFocusedScale: CGFloat = 0.70
    static let maximumFocusedScale: CGFloat = 1.30
    static let targetBoundarySpan: CGFloat = 26

    static func focusPoint(front: CGPoint?, back: CGPoint?, fallback: CGPoint) -> CGPoint {
        switch (front, back) {
        case let (.some(front), .some(back)):
            return CGPoint(x: (front.x + back.x) * 0.5, y: (front.y + back.y) * 0.5)
        case let (.some(front), .none):
            return front
        case let (.none, .some(back)):
            return back
        case (.none, .none):
            return fallback
        }
    }

    static func focusedScale(front: CGPoint?, back: CGPoint?) -> CGFloat {
        guard let front, let back else { return 1.15 }
        let span = hypot(back.x - front.x, back.y - front.y)
        guard span.isFinite, span > 1 else { return 1.15 }
        return min(max(targetBoundarySpan / span, minimumFocusedScale), maximumFocusedScale)
    }

    static func imagePoint(on route: [[Double]], atMetres metres: Double) -> CGPoint? {
        guard metres.isFinite,
              let first = route.first(where: { valid($0) }),
              let last = route.last(where: { valid($0) }) else {
            return nil
        }
        if metres <= first[2] { return CGPoint(x: first[0], y: first[1]) }

        for index in 0..<(route.count - 1) {
            let start = route[index]
            let end = route[index + 1]
            guard valid(start), valid(end), end[2] >= start[2] else { continue }
            if metres <= end[2] {
                let span = end[2] - start[2]
                let fraction = span > 0 ? (metres - start[2]) / span : 0
                return CGPoint(
                    x: start[0] + (end[0] - start[0]) * fraction,
                    y: start[1] + (end[1] - start[1]) * fraction
                )
            }
        }
        return CGPoint(x: last[0], y: last[1])
    }

    static func playerProgressMetres(on route: [[Double]], playerImagePoint: CGPoint) -> Double? {
        guard playerImagePoint.x.isFinite, playerImagePoint.y.isFinite, route.count >= 2 else {
            return nil
        }
        var bestDistanceSquared = Double.greatestFiniteMagnitude
        var bestProgress: Double?

        for index in 0..<(route.count - 1) {
            let start = route[index]
            let end = route[index + 1]
            guard valid(start), valid(end), end[2] >= start[2] else { continue }
            let dx = end[0] - start[0]
            let dy = end[1] - start[1]
            let lengthSquared = dx * dx + dy * dy
            guard lengthSquared > 0 else { continue }
            let rawFraction = ((Double(playerImagePoint.x) - start[0]) * dx
                + (Double(playerImagePoint.y) - start[1]) * dy) / lengthSquared
            let fraction = min(max(rawFraction, 0), 1)
            let projectedX = start[0] + dx * fraction
            let projectedY = start[1] + dy * fraction
            let playerDX = Double(playerImagePoint.x) - projectedX
            let playerDY = Double(playerImagePoint.y) - projectedY
            let distanceSquared = playerDX * playerDX + playerDY * playerDY
            if distanceSquared < bestDistanceSquared {
                bestDistanceSquared = distanceSquared
                bestProgress = start[2] + (end[2] - start[2]) * fraction
            }
        }
        return bestProgress
    }

    static func remainingYards(to absoluteMetres: Double, after progressMetres: Double) -> Int? {
        guard absoluteMetres.isFinite, progressMetres.isFinite else { return nil }
        let remaining = absoluteMetres - progressMetres
        guard remaining > 0 else { return nil }
        return Int((remaining * 1.09361).rounded())
    }

    static func point(_ coordinates: [Double]?) -> CGPoint? {
        guard let coordinates, coordinates.count >= 2,
              coordinates[0].isFinite, coordinates[1].isFinite else { return nil }
        return CGPoint(x: coordinates[0], y: coordinates[1])
    }

    /// Straight-line range from the current player pixel to a true hazard-boundary pixel. The topo
    /// projector is uniform, so the retained route's cumulative metres calibrate image pixels exactly.
    static func distanceYards(from player: CGPoint, to edge: CGPoint, on route: [[Double]]) -> Int? {
        guard player.x.isFinite, player.y.isFinite, edge.x.isFinite, edge.y.isFinite else { return nil }
        var metres = 0.0
        var pixels = 0.0
        for index in 0..<(route.count - 1) {
            let start = route[index]
            let end = route[index + 1]
            guard valid(start), valid(end), end[2] > start[2] else { continue }
            let pixelLength = hypot(end[0] - start[0], end[1] - start[1])
            guard pixelLength > 0 else { continue }
            metres += end[2] - start[2]
            pixels += pixelLength
        }
        guard metres > 0, pixels > 0 else { return nil }
        let distancePixels = hypot(Double(edge.x - player.x), Double(edge.y - player.y))
        return Int((distancePixels * metres / pixels * 1.09361).rounded())
    }

    static func hasMeasuredFrontBack(_ hazard: WatchHazard) -> Bool {
        hazard.frontDistanceM != nil || hazard.backDistanceM != nil
            || point(hazard.frontPx) != nil || point(hazard.backPx) != nil
    }

    static func alongRouteEndMetres(for hazard: WatchHazard) -> Double? {
        if hazard.kind == "water" || hasMeasuredFrontBack(hazard) {
            return hazard.endM ?? hazard.startM
        }
        return hazard.startM
    }

    static func bunkerSideMetres(for hazard: WatchHazard) -> Double? {
        guard hazard.kind == "bunker", !hasMeasuredFrontBack(hazard) else { return nil }
        // Before `sideM` existed, the same source value was incorrectly encoded as `endM`.
        return hazard.sideM ?? hazard.endM
    }

    static func frontImagePoint(for hazard: WatchHazard, on route: [[Double]]) -> CGPoint? {
        point(hazard.frontPx) ?? hazard.startM.flatMap { imagePoint(on: route, atMetres: $0) }
    }

    static func backImagePoint(for hazard: WatchHazard, on route: [[Double]]) -> CGPoint? {
        point(hazard.backPx) ?? alongRouteEndMetres(for: hazard).flatMap { imagePoint(on: route, atMetres: $0) }
    }

    /// The hazard's real boundary in image pixels (empty for legacy payloads without one).
    static func outline(_ hazard: WatchHazard) -> [CGPoint] {
        (hazard.outlinePx ?? []).compactMap { point($0) }
    }

    /// Yards from the player to one hazard edge: straight to the boundary pixel when known, else
    /// along the route from the player's progress. Nil outside the useful golf range.
    static func edgeYards(
        hazard: WatchHazard, edge: CGPoint, metres: Double,
        player: CGPoint, progress: Double, route: [[Double]]
    ) -> Int? {
        let yards = distanceYards(from: player, to: edge, on: route)
            ?? remainingYards(to: metres, after: progress)
        return yards.flatMap { WatchGeoMath.usefulGolfYards($0) }
    }

    private static func valid(_ row: [Double]) -> Bool {
        row.count >= 3 && row[0].isFinite && row[1].isFinite && row[2].isFinite
    }
}

/// Map detail for one measured hazard. New payloads place both dots on the real geometry boundary and
/// range straight to them; old caches fall back to their retained route facts. B6 (README §3): the
/// Crown zooms (1–4×) and a drag pans once zoomed; tapping "1 / N" selects the next upcoming hazard,
/// and while zoomed that keeps the current zoom and pan instead of re-framing (IMG-8050).
public struct WatchHazardMapView: View {
    public let geometry: WatchHoleMapGeometry
    public let route: [[Double]]
    public let hazards: [WatchHazard]
    public let centerGreenYards: Int?
    /// Hazard distances are player-relative too. Keep the instrument explicit while the wrist fix
    /// is unavailable instead of measuring from the cached Tee/phone anchor.
    public let rangeUnavailable: Bool
    public let onBack: () -> Void
    /// Off on the 本洞 pages: there the vertical page swipe and the Back button navigate, and an
    /// edge-back drag recognizer would compete with the page swipe.
    public let edgeBackEnabled: Bool

    @State private var selection: Int
    @State private var viewport: WatchHoleViewport
    /// The framing in use when zooming began; held while zoomed so switching hazards never re-fits.
    @State private var frozenFrame: WatchHazardFrame?

    public init(
        geometry: WatchHoleMapGeometry,
        route: [[Double]],
        hazards: [WatchHazard],
        centerGreenYards: Int?,
        rangeUnavailable: Bool = false,
        initialHazardID: String? = nil,
        initialViewport: WatchHoleViewport = WatchHoleViewport(),
        edgeBackEnabled: Bool = true,
        onBack: @escaping () -> Void = {}
    ) {
        self.geometry = geometry
        self.route = route
        self.hazards = hazards
        self.centerGreenYards = centerGreenYards
        self.rangeUnavailable = rangeUnavailable
        self.onBack = onBack
        self.edgeBackEnabled = edgeBackEnabled

        let progress = WatchHazardMapLayout.playerProgressMetres(
            on: route,
            playerImagePoint: geometry.youPx
        ) ?? 0
        let upcoming = Self.upcomingHazards(hazards, after: progress)
        let initialIndex = initialHazardID.flatMap { id in upcoming.firstIndex { $0.id == id } } ?? 0
        _selection = State(initialValue: initialIndex)
        _viewport = State(initialValue: initialViewport)
    }

    private var playerProgressMetres: Double {
        WatchHazardMapLayout.playerProgressMetres(on: route, playerImagePoint: geometry.youPx) ?? 0
    }

    private var upcoming: [WatchHazard] {
        Self.upcomingHazards(hazards, after: playerProgressMetres)
    }

    private var selectedIndex: Int {
        min(max(selection, 0), max(upcoming.count - 1, 0))
    }

    /// The selected hazard's own framing (both edges in view).
    private func frame(for hazard: WatchHazard) -> WatchHazardFrame {
        let front = WatchHazardMapLayout.frontImagePoint(for: hazard, on: route)
        let back = WatchHazardMapLayout.backImagePoint(for: hazard, on: route)
        return WatchHazardFrame(
            focus: WatchHazardMapLayout.focusPoint(front: front, back: back, fallback: geometry.pinPx),
            scale: WatchHazardMapLayout.focusedScale(front: front, back: back)
        )
    }

    /// Unzoomed the selected hazard frames itself; zoomed, the framing from when zooming began stays,
    /// so "1 / N" never changes the zoom or pan the player set up (IMG-8050).
    static func activeFrame(isZoomed: Bool, frozen: WatchHazardFrame?, current: WatchHazardFrame) -> WatchHazardFrame {
        isZoomed ? (frozen ?? current) : current
    }

    /// "1 / N": the next upcoming hazard (wrapping).
    private func selectNextHazard() {
        guard upcoming.count > 1 else { return }
        selection = (selectedIndex + 1) % upcoming.count
    }

    public var body: some View {
        GeometryReader { geo in
            if rangeUnavailable {
                rangeUnavailableState
            } else if centerGreenYards.map { WatchGeoMath.isBeyondUsefulGreenRange($0) } == true {
                offCourseState
            } else if upcoming.isEmpty {
                emptyState
            } else {
                hazardMap(upcoming[selectedIndex], index: selectedIndex, size: geo.size)
                    .watchZoomPan($viewport, size: geo.size)
            }
        }
        .background(Color.black)
        .onChange(of: viewport.isZoomed) { _, zoomed in
            frozenFrame = zoomed && !upcoming.isEmpty ? frame(for: upcoming[selectedIndex]) : nil
        }
        .onChange(of: upcoming.count) { _, count in
            selection = min(selection, max(count - 1, 0))
        }
        .simultaneousGesture(
            DragGesture(minimumDistance: 24)
                .onEnded { value in
                    guard WatchEdgeBackGesture.shouldTrigger(
                        startX: value.startLocation.x,
                        translation: value.translation
                    ) else { return }
                    onBack()
                },
            including: edgeBackEnabled ? .all : .subviews
        )
        .accessibilityAction(named: Text("返回菜单"), onBack)
        .ignoresSafeArea()
    }

    private func hazardMap(_ hazard: WatchHazard, index: Int, size: CGSize) -> some View {
        let startMetres = hazard.startM ?? WatchHazardMapLayout.alongRouteEndMetres(for: hazard)
            ?? playerProgressMetres
        let endMetres = WatchHazardMapLayout.alongRouteEndMetres(for: hazard) ?? startMetres
        let startPoint = WatchHazardMapLayout.frontImagePoint(for: hazard, on: route)
        let endPoint = WatchHazardMapLayout.backImagePoint(for: hazard, on: route)
        _ = (startPoint, endPoint)
        // Unzoomed each hazard frames itself; zoomed, the framing from when zooming began is kept.
        let base = Self.activeFrame(isZoomed: viewport.isZoomed, frozen: frozenFrame, current: frame(for: hazard))
        let focusPoint = base.focus
        let scale = base.scale

        return ZStack {
            WatchHoleMapView(
                frontGreen: nil,
                centerGreen: centerGreenYards,
                backGreen: nil,
                lastShot: 0,
                ringPips: [],
                showTextOverlay: false,
                showHoleIdentity: false,
                fullMap: true,
                mapScale: scale,
                fullMapFocusImagePx: focusPoint,
                fullMapFocusCanvasFraction: CGPoint(x: 0.52, y: 0.52),
                geometry: geometry,
                userZoom: viewport.zoom,
                userPan: viewport.pan
            )
            .allowsHitTesting(false)

            Canvas { context, canvasSize in
                drawHazard(
                    &context,
                    size: canvasSize,
                    hazard: hazard,
                    startMetres: startMetres,
                    endMetres: endMetres,
                    scale: scale * viewport.zoom,
                    focusPoint: focusPoint
                )
            }
            .allowsHitTesting(false)

            controls(hazard: hazard, index: index, size: size)
        }
    }

    private func drawHazard(
        _ context: inout GraphicsContext,
        size: CGSize,
        hazard: WatchHazard,
        startMetres: Double,
        endMetres: Double,
        scale: CGFloat,
        focusPoint: CGPoint
    ) {
        let focusCanvas = CGPoint(x: size.width * 0.52 + viewport.pan.width,
                                  y: size.height * 0.52 + viewport.pan.height)
        func canvas(_ point: CGPoint) -> CGPoint {
            CGPoint(
                x: (point.x - focusPoint.x) * scale + focusCanvas.x,
                y: (point.y - focusPoint.y) * scale + focusCanvas.y
            )
        }

        // README §1 唯一规范 (IMG-8050 / IMG-7959): one hazard, its REAL boundary as a thin red line,
        // the front / back as small red dots (no white ring, no thick frame) and compact black
        // "前 N / 后 N" labels.
        let red = Color(red: 1.0, green: 0.23, blue: 0.19)
        let frontPoint = WatchHazardMapLayout.frontImagePoint(for: hazard, on: route)
        let backPoint = WatchHazardMapLayout.backImagePoint(for: hazard, on: route)
        let safeRect = WatchDisplayGeometry.contentRect(in: size)

        let outline = WatchHazardMapLayout.outline(hazard)
        if outline.count >= 3 {
            var path = Path()
            path.addLines(outline.map(canvas))
            path.closeSubpath()
            context.stroke(path, with: .color(red), style: StrokeStyle(lineWidth: 1.2, lineJoin: .round))
        }

        let hasFrontBack = hazard.kind == "water" || WatchHazardMapLayout.hasMeasuredFrontBack(hazard)
        let edges: [(String, Double, CGPoint?)] = hasFrontBack
            ? [("前", startMetres, frontPoint), ("后", endMetres, backPoint)]
            : [("前", startMetres, frontPoint)]
        for (prefix, metres, imagePoint) in edges {
            guard let imagePoint else { continue }
            let point = canvas(imagePoint)
            let radius: CGFloat = 2.6
            context.fill(
                Path(ellipseIn: CGRect(x: point.x - radius, y: point.y - radius, width: radius * 2, height: radius * 2)),
                with: .color(red)
            )
            guard let yards = WatchHazardMapLayout.edgeYards(
                hazard: hazard, edge: imagePoint, metres: metres,
                player: geometry.youPx, progress: playerProgressMetres, route: route
            ) else { continue }
            let label = context.resolve(
                Text("\(prefix) \(yards)")
                    .font(.system(size: 11, weight: .heavy, design: .rounded))
                    .foregroundColor(.white)
            )
            let textSize = label.measure(in: CGSize(width: 80, height: 20))
            let box = CGSize(width: textSize.width + 8, height: textSize.height + 3)
            // Beside the dot (front below-left, back above-right), kept inside the round display.
            let raw = CGPoint(
                x: point.x + (prefix == "前" ? -(box.width / 2 + 6) : box.width / 2 + 6),
                y: point.y + (prefix == "前" ? 8 : -8)
            )
            let center = CGPoint(
                x: min(max(raw.x, safeRect.minX + box.width / 2), safeRect.maxX - box.width / 2),
                y: min(max(raw.y, safeRect.minY + 40), safeRect.maxY - box.height / 2)
            )
            let rect = CGRect(x: center.x - box.width / 2, y: center.y - box.height / 2, width: box.width, height: box.height)
            context.fill(Path(roundedRect: rect, cornerRadius: 4), with: .color(.black.opacity(0.82)))
            context.draw(label, at: center)
        }
    }

    private func controls(hazard: WatchHazard, index: Int, size: CGSize) -> some View {
        let safeInset = WatchDisplayGeometry.contentInset(for: size)
        return ZStack {
            VStack {
                HStack(spacing: 4) {
                    WatchInstrumentBackButton(accessibilityLabel: "返回菜单", onBack: onBack)
                    // A compact black backing keeps the title readable when the player dot or the
                    // outline sits under it.
                    Text(shortHazardTitle(hazard))
                        .font(.system(size: 17, weight: .black))
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.black.opacity(0.82), in: RoundedRectangle(cornerRadius: 6))
                    Spacer(minLength: WatchHazardMapLayout.systemTimeTrailingClearance)
                }
                .padding(.leading, safeInset)
                // 左侧大数字 = 到前沿 (README §3).
                if let front = frontYards(hazard) {
                    HStack {
                        Text("\(front)")
                            .font(.system(size: 34, weight: .black, design: .rounded))
                            .monospacedDigit()
                            .foregroundStyle(.white)
                            .padding(.horizontal, 5)
                            .background(Color.black.opacity(0.72), in: RoundedRectangle(cornerRadius: 8))
                            .accessibilityLabel("到前沿 \(front) 码")
                            .accessibilityIdentifier("watch-hazard-front-yards")
                        Spacer()
                    }
                    .padding(.leading, safeInset)
                }
                Spacer()
                if upcoming.count > 1 {
                    Button(action: selectNextHazard) {
                        Text("\(index + 1) / \(upcoming.count)")
                            .font(.system(size: 15, weight: .black, design: .rounded))
                            .monospacedDigit()
                            .foregroundStyle(.white)
                            .padding(.horizontal, 12)
                            .frame(minHeight: 32)
                            .background(Color.black.opacity(0.6), in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("下一个障碍，第 \(index + 1) 个，共 \(upcoming.count) 个")
                    .accessibilityIdentifier("watch-hazard-next")
                }
            }
            .padding(.top, safeInset)
            .padding(.bottom, safeInset)

        }
    }

    private func frontYards(_ hazard: WatchHazard) -> Int? {
        guard let front = WatchHazardMapLayout.frontImagePoint(for: hazard, on: route) else { return nil }
        return WatchHazardMapLayout.edgeYards(
            hazard: hazard, edge: front,
            metres: hazard.startM ?? WatchHazardMapLayout.alongRouteEndMetres(for: hazard) ?? playerProgressMetres,
            player: geometry.youPx, progress: playerProgressMetres, route: route
        )
    }

    private func shortHazardTitle(_ hazard: WatchHazard) -> String {
        if hazard.kind == "water" { return "水障碍" }
        return "沙坑"
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            WatchInstrumentBackButton(accessibilityLabel: "返回菜单", onBack: onBack)
            Text("前方无障碍")
                .font(.system(size: 16, weight: .bold))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var offCourseState: some View {
        VStack(spacing: 12) {
            WatchInstrumentBackButton(accessibilityLabel: "返回菜单", onBack: onBack)
            Image(systemName: "location.slash")
                .font(.system(size: 42))
                .foregroundStyle(.secondary)
            Text("离本洞较远")
                .font(.system(size: 20, weight: .black))
            Text("回到本洞后再显示障碍距离")
                .font(.system(size: 15, weight: .bold))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(10)
    }

    private var rangeUnavailableState: some View {
        VStack(spacing: 10) {
            WatchInstrumentBackButton(accessibilityLabel: "返回菜单", onBack: onBack)
            Text("999")
                .font(.system(size: 42, weight: .black, design: .rounded))
                .monospacedDigit()
            Text("等待定位")
                .font(.system(size: 19, weight: .black))
                .foregroundStyle(AICaddieDesignTokens.hudYellow)
            Text("定位完成后显示障碍距离")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(10)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("999 码，等待定位，定位完成后显示障碍距离")
    }

    private static func upcomingHazards(_ hazards: [WatchHazard], after progressMetres: Double) -> [WatchHazard] {
        hazards
            .filter { (WatchHazardMapLayout.alongRouteEndMetres(for: $0)
                ?? -Double.greatestFiniteMagnitude) > progressMetres }
            .sorted { ($0.startM ?? $0.endM ?? Double.greatestFiniteMagnitude)
                < ($1.startM ?? $1.endM ?? Double.greatestFiniteMagnitude) }
    }
}

/// One hazard's map framing: the image point centred and its scale.
struct WatchHazardFrame: Equatable {
    let focus: CGPoint
    let scale: CGFloat
}
