import SwiftUI

enum WatchHazardMapLayout {
    static let markerDiameter: CGFloat = 8
    static let markerToPillCenterOffset: CGFloat = 14
    static let topPillLaneCenterY: CGFloat = 42
    static let topBoundaryClearance: CGFloat = 56
    /// The real watchOS runtime keeps drawing its clock even when this full-screen map requests
    /// hidden overlays. Reserve that top-right lane instead of centering map copy underneath it.
    static let systemTimeTrailingClearance: CGFloat = 56
    static let topSummaryLeadingInset: CGFloat = 4

    static func topSummaryWidth(viewportWidth: CGFloat) -> CGFloat {
        max(0, viewportWidth - topSummaryLeadingInset - systemTimeTrailingClearance)
    }

    static func distancePillSize(for text: String) -> CGSize {
        CGSize(width: CGFloat(text.count) * 8 + 20, height: 18)
    }

    static func distancePillCenterX(
        markerX: CGFloat,
        pillWidth: CGFloat,
        viewportWidth: CGFloat
    ) -> CGFloat {
        let halfWidth = max(pillWidth, 0) / 2
        let minimumX = halfWidth + 4
        let maximumX = max(minimumX, viewportWidth - halfWidth - 4)
        return min(max(markerX, minimumX), maximumX)
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

    /// Keep the farther-edge (过) label above the nearer-edge (到) label when viewport clamping
    /// would otherwise collapse both compact pills onto one row.
    static func separatedPillCenterYs(
        frontPreferredY: CGFloat,
        backPreferredY: CGFloat,
        minimumY: CGFloat,
        maximumY: CGFloat,
        minimumSpacing: CGFloat
    ) -> (front: CGFloat, back: CGFloat) {
        guard frontPreferredY.isFinite, backPreferredY.isFinite,
              minimumY.isFinite, maximumY.isFinite, minimumSpacing.isFinite,
              maximumY >= minimumY else {
            return (frontPreferredY, backPreferredY)
        }
        let available = maximumY - minimumY
        let spacing = min(max(minimumSpacing, 0), available)
        let clamp: (CGFloat) -> CGFloat = { min(max($0, minimumY), maximumY) }
        let front = clamp(frontPreferredY)
        let back = clamp(backPreferredY)
        if front >= back + spacing {
            return (front, back)
        }

        let resolvedBack = min(max(min(front, back), minimumY), maximumY - spacing)
        return (resolvedBack + spacing, resolvedBack)
    }

    private static func valid(_ row: [Double]) -> Bool {
        row.count >= 3 && row[0].isFinite && row[1].isFinite && row[2].isFinite
    }
}

/// Map detail for one measured hazard. New payloads place both dots on the real geometry boundary and
/// range straight to them; old caches fall back to their retained route facts. Turning the Crown selects
/// the next upcoming hazard.
public struct WatchHazardMapView: View {
    public let geometry: WatchHoleMapGeometry
    public let route: [[Double]]
    public let hazards: [WatchHazard]
    public let centerGreenYards: Int
    public let onBack: () -> Void

    @State private var crownSelection: Double

    public init(
        geometry: WatchHoleMapGeometry,
        route: [[Double]],
        hazards: [WatchHazard],
        centerGreenYards: Int,
        initialHazardID: String? = nil,
        onBack: @escaping () -> Void = {}
    ) {
        self.geometry = geometry
        self.route = route
        self.hazards = hazards
        self.centerGreenYards = centerGreenYards
        self.onBack = onBack

        let progress = WatchHazardMapLayout.playerProgressMetres(
            on: route,
            playerImagePoint: geometry.youPx
        ) ?? 0
        let upcoming = Self.upcomingHazards(hazards, after: progress)
        let initialIndex = initialHazardID.flatMap { id in upcoming.firstIndex { $0.id == id } } ?? 0
        _crownSelection = State(initialValue: Double(initialIndex))
    }

    private var playerProgressMetres: Double {
        WatchHazardMapLayout.playerProgressMetres(on: route, playerImagePoint: geometry.youPx) ?? 0
    }

    private var upcoming: [WatchHazard] {
        Self.upcomingHazards(hazards, after: playerProgressMetres)
    }

    private var selectedIndex: Int {
        min(max(Int(crownSelection.rounded()), 0), max(upcoming.count - 1, 0))
    }

    private var crownUpperBound: Double { Double(max(upcoming.count - 1, 1)) }

    public var body: some View {
        GeometryReader { geo in
            if upcoming.isEmpty {
                emptyState
            } else {
                hazardMap(upcoming[selectedIndex], index: selectedIndex, size: geo.size)
            }
        }
        .background(Color.black)
        .focusable(true)
        .digitalCrownRotation(
            $crownSelection,
            from: 0,
            through: crownUpperBound,
            by: 1,
            sensitivity: .medium,
            isContinuous: false,
            isHapticFeedbackEnabled: true
        )
        .onChange(of: upcoming.count) { count in
            crownSelection = min(crownSelection, Double(max(count - 1, 0)))
        }
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
        .accessibilityAction(named: Text("返回障碍列表"), onBack)
        .persistentSystemOverlays(.hidden)
        .ignoresSafeArea()
    }

    private func hazardMap(_ hazard: WatchHazard, index: Int, size: CGSize) -> some View {
        let startMetres = hazard.startM ?? WatchHazardMapLayout.alongRouteEndMetres(for: hazard)
            ?? playerProgressMetres
        let endMetres = WatchHazardMapLayout.alongRouteEndMetres(for: hazard) ?? startMetres
        let startPoint = WatchHazardMapLayout.frontImagePoint(for: hazard, on: route)
        let endPoint = WatchHazardMapLayout.backImagePoint(for: hazard, on: route)
        let topImageY = [startPoint?.y, endPoint?.y].compactMap { $0 }.min() ?? geometry.pinPx.y
        let scale = CGFloat(WatchHoleMapViewport.effectiveRestingScale(
            requestedScale: WatchHoleMapView.maximumCrownScale,
            viewportHeight: Double(size.height),
            playerAnchorFraction: 0.66,
            playerImageY: Double(geometry.youPx.y),
            pinImageY: Double(topImageY),
            topClearance: centerGreenYards > 0
                ? Double(WatchHazardMapLayout.topBoundaryClearance)
                : WatchHoleMapViewport.flagTopClearance
        ))

        return ZStack {
            WatchHoleMapView(
                frontGreen: 0,
                centerGreen: centerGreenYards,
                backGreen: 0,
                lastShot: 0,
                ringPips: [],
                showTextOverlay: false,
                fullMap: true,
                mapScale: scale,
                geometry: geometry
            )
            .allowsHitTesting(false)

            Canvas { context, canvasSize in
                drawHazard(
                    &context,
                    size: canvasSize,
                    hazard: hazard,
                    startMetres: startMetres,
                    endMetres: endMetres,
                    scale: scale
                )
            }

            controls(hazard: hazard, index: index, size: size)
        }
    }

    private func drawHazard(
        _ context: inout GraphicsContext,
        size: CGSize,
        hazard: WatchHazard,
        startMetres: Double,
        endMetres: Double,
        scale: CGFloat
    ) {
        let playerCanvas = CGPoint(x: size.width * 0.5, y: size.height * 0.66)
        func canvas(_ point: CGPoint) -> CGPoint {
            CGPoint(
                x: (point.x - geometry.youPx.x) * scale + playerCanvas.x,
                y: (point.y - geometry.youPx.y) * scale + playerCanvas.y
            )
        }

        var measuredPoints: [CGPoint] = [playerCanvas]
        if let start = WatchHazardMapLayout.imagePoint(on: route, atMetres: playerProgressMetres) {
            measuredPoints.append(canvas(start))
        }
        for row in route where row.count >= 3 && row[2] > playerProgressMetres && row[2] < endMetres {
            measuredPoints.append(canvas(CGPoint(x: row[0], y: row[1])))
        }
        if let end = WatchHazardMapLayout.imagePoint(on: route, atMetres: endMetres) {
            measuredPoints.append(canvas(end))
        }
        if measuredPoints.count >= 2 {
            var path = Path()
            path.move(to: measuredPoints[0])
            for point in measuredPoints.dropFirst() { path.addLine(to: point) }
            context.stroke(
                path,
                with: .color(.white.opacity(0.9)),
                style: StrokeStyle(lineWidth: 1.8, lineCap: .round, lineJoin: .round, dash: [6, 5])
            )
        }

        let tint = hazard.kind == "water"
            ? Color(red: 0.20, green: 0.68, blue: 1.0)
            : Color(red: 1.0, green: 0.76, blue: 0.18)
        let hasFrontBack = hazard.kind == "water" || WatchHazardMapLayout.hasMeasuredFrontBack(hazard)
        let frontPoint = WatchHazardMapLayout.frontImagePoint(for: hazard, on: route)
        let backPoint = WatchHazardMapLayout.backImagePoint(for: hazard, on: route)
        let pillHeight = WatchHazardMapLayout.distancePillSize(for: "到 000").height
        let minimumPillCenterY: CGFloat = centerGreenYards > 0
            ? WatchHazardMapLayout.topPillLaneCenterY
            : pillHeight * 0.5 + 4
        let maximumPillCenterY = max(minimumPillCenterY, size.height - pillHeight * 0.5 - 4)
        let frontCanvasPoint = frontPoint.map(canvas)
        let backCanvasPoint = backPoint.map(canvas)
        let lanes = WatchHazardMapLayout.separatedPillCenterYs(
            frontPreferredY: (frontCanvasPoint?.y ?? minimumPillCenterY)
                + WatchHazardMapLayout.markerToPillCenterOffset,
            backPreferredY: (backCanvasPoint?.y ?? minimumPillCenterY)
                - WatchHazardMapLayout.markerToPillCenterOffset,
            minimumY: minimumPillCenterY,
            maximumY: maximumPillCenterY,
            minimumSpacing: pillHeight + 4
        )
        let edges: [(String, Double, CGPoint?, CGFloat?)] = hasFrontBack
            ? [("到", startMetres, frontPoint, lanes.front), ("过", endMetres, backPoint, lanes.back)]
            : [("距", startMetres, frontPoint, nil)]
        for (label, metres, imagePoint, fixedCenterY) in edges {
            guard let imagePoint else {
                continue
            }
            let yards = WatchHazardMapLayout.distanceYards(
                from: geometry.youPx, to: imagePoint, on: route
            ) ?? WatchHazardMapLayout.remainingYards(to: metres, after: playerProgressMetres)
            guard let yards else { continue }
            let point = canvas(imagePoint)
            let markerDiameter = WatchHazardMapLayout.markerDiameter
            let markerRect = CGRect(
                x: point.x - markerDiameter * 0.5,
                y: point.y - markerDiameter * 0.5,
                width: markerDiameter,
                height: markerDiameter
            )
            context.fill(Path(ellipseIn: markerRect), with: .color(tint))
            context.stroke(
                Path(ellipseIn: markerRect),
                with: .color(.black),
                style: StrokeStyle(lineWidth: 1.2)
            )

            let text = "\(label) \(yards)"
            let pillSize = WatchHazardMapLayout.distancePillSize(for: text)
            let pillCenter = CGPoint(
                x: WatchHazardMapLayout.distancePillCenterX(
                    markerX: point.x,
                    pillWidth: pillSize.width,
                    viewportWidth: size.width
                ),
                y: fixedCenterY
                    ?? min(max(point.y, minimumPillCenterY), maximumPillCenterY)
            )
            let rect = CGRect(
                x: pillCenter.x - pillSize.width * 0.5,
                y: pillCenter.y - pillSize.height * 0.5,
                width: pillSize.width,
                height: pillSize.height
            )
            context.fill(
                Path(roundedRect: rect, cornerRadius: pillSize.height * 0.5),
                with: .color(.black.opacity(0.72))
            )
            context.stroke(
                Path(roundedRect: rect, cornerRadius: pillSize.height * 0.5),
                with: .color(tint),
                style: StrokeStyle(lineWidth: 1)
            )
            context.draw(
                context.resolve(Text(text).font(.system(size: 10, weight: .semibold)).foregroundColor(.white)),
                at: pillCenter
            )
        }
    }

    private func controls(hazard: WatchHazard, index: Int, size: CGSize) -> some View {
        let summary = "\(hazard.label) \(index + 1)/\(upcoming.count)"
        let trackHeight = min(size.height * 0.55, 104)
        let thumbHeight = min(40, max(18, trackHeight * 0.28))
        let thumbOffset = CGFloat(index) * (trackHeight - thumbHeight)
            / CGFloat(max(upcoming.count - 1, 1))

        return ZStack {
            VStack {
                if centerGreenYards > 0 {
                    HStack(spacing: 0) {
                        Text("中 \(centerGreenYards) 码 · 到果岭")
                            .font(.system(size: 11, weight: .semibold))
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Capsule().fill(.black.opacity(0.72)))
                            .frame(
                                width: WatchHazardMapLayout.topSummaryWidth(viewportWidth: size.width),
                                alignment: .leading
                            )
                        Spacer(minLength: WatchHazardMapLayout.systemTimeTrailingClearance)
                    }
                    .padding(.leading, WatchHazardMapLayout.topSummaryLeadingInset)
                }
                Spacer()
                VStack(spacing: 1) {
                    Text(summary)
                        .font(.system(size: 10, weight: .semibold))
                    Text(upcoming.count > 1
                        ? "转表冠换障碍"
                        : ((hazard.kind == "water" || WatchHazardMapLayout.hasMeasuredFrontBack(hazard))
                            ? "障碍前后沿" : "到障碍距离"))
                        .font(.system(size: 8.5, weight: .medium))
                        .foregroundStyle(.white.opacity(0.62))
                }
                .lineLimit(1)
                .shadow(color: .black, radius: 2)
            }
            .padding(.top, 5)
            .padding(.bottom, 16)

            if upcoming.count > 1 {
                HStack {
                    Spacer()
                    ZStack(alignment: .top) {
                        Capsule()
                            .fill(Color.white.opacity(0.22))
                            .frame(width: 4, height: trackHeight)
                        Capsule()
                            .fill(Color(red: 0.30, green: 0.86, blue: 0.46))
                            .frame(width: 4, height: thumbHeight)
                            .offset(y: thumbOffset)
                    }
                    .padding(.trailing, 6)
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Button(action: onBack) {
                Label("障碍列表", systemImage: "chevron.backward")
            }
            .buttonStyle(.plain)
            Text("前方没有可用障碍")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private static func upcomingHazards(_ hazards: [WatchHazard], after progressMetres: Double) -> [WatchHazard] {
        hazards
            .filter { (WatchHazardMapLayout.alongRouteEndMetres(for: $0)
                ?? -Double.greatestFiniteMagnitude) > progressMetres }
            .sorted { ($0.startM ?? $0.endM ?? Double.greatestFiniteMagnitude)
                < ($1.startM ?? $1.endM ?? Double.greatestFiniteMagnitude) }
    }
}
