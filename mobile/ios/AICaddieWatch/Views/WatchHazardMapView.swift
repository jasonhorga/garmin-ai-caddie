import SwiftUI

enum WatchHazardMapLayout {
    /// The real watchOS runtime keeps drawing its clock even when this full-screen map requests
    /// hidden overlays. Reserve that top-right lane instead of centering map copy underneath it.
    static let systemTimeTrailingClearance: CGFloat = 56
    /// S70's Hazard instrument centres one obstacle rather than shrinking the whole hole until both
    /// the player and obstacle fit. Target roughly a 38-point measured front/back span, while keeping
    /// enough surrounding fairway to make the obstacle's location obvious.
    static let minimumFocusedScale: CGFloat = 0.82
    static let maximumFocusedScale: CGFloat = 1.80
    static let targetBoundarySpan: CGFloat = 38

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
    public let centerGreenYards: Int?
    public let onBack: () -> Void

    @State private var crownSelection: Double

    public init(
        geometry: WatchHoleMapGeometry,
        route: [[Double]],
        hazards: [WatchHazard],
        centerGreenYards: Int?,
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
            if centerGreenYards.map { WatchGeoMath.isBeyondUsefulGreenRange($0) } == true {
                offCourseState
            } else if upcoming.isEmpty {
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
        .accessibilityAction(named: Text("返回菜单"), onBack)
        .ignoresSafeArea()
    }

    private func hazardMap(_ hazard: WatchHazard, index: Int, size: CGSize) -> some View {
        let startMetres = hazard.startM ?? WatchHazardMapLayout.alongRouteEndMetres(for: hazard)
            ?? playerProgressMetres
        let endMetres = WatchHazardMapLayout.alongRouteEndMetres(for: hazard) ?? startMetres
        let startPoint = WatchHazardMapLayout.frontImagePoint(for: hazard, on: route)
        let endPoint = WatchHazardMapLayout.backImagePoint(for: hazard, on: route)
        let focusPoint = WatchHazardMapLayout.focusPoint(
            front: startPoint,
            back: endPoint,
            fallback: geometry.pinPx
        )
        let scale = WatchHazardMapLayout.focusedScale(front: startPoint, back: endPoint)

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
                    scale: scale,
                    focusPoint: focusPoint
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
        scale: CGFloat,
        focusPoint: CGPoint
    ) {
        let focusCanvas = CGPoint(x: size.width * 0.52, y: size.height * 0.52)
        func canvas(_ point: CGPoint) -> CGPoint {
            CGPoint(
                x: (point.x - focusPoint.x) * scale + focusCanvas.x,
                y: (point.y - focusPoint.y) * scale + focusCanvas.y
            )
        }

        let tint = hazard.kind == "water"
            ? Color(red: 0.20, green: 0.68, blue: 1.0)
            : Color(red: 1.0, green: 0.31, blue: 0.24)
        let hasFrontBack = hazard.kind == "water" || WatchHazardMapLayout.hasMeasuredFrontBack(hazard)
        let frontPoint = WatchHazardMapLayout.frontImagePoint(for: hazard, on: route)
        let backPoint = WatchHazardMapLayout.backImagePoint(for: hazard, on: route)
        let safeRect = WatchDisplayGeometry.contentRect(in: size)

        // Precise packages bind both points to the real obstacle boundary. A restrained tint stroke
        // makes the bunker/water already present in the topo easy to find without inventing a shape.
        if WatchHazardMapLayout.point(hazard.frontPx) != nil,
           WatchHazardMapLayout.point(hazard.backPx) != nil,
           let frontPoint,
           let backPoint {
            var boundary = Path()
            boundary.move(to: canvas(frontPoint))
            boundary.addLine(to: canvas(backPoint))
            context.stroke(
                boundary,
                with: .color(tint.opacity(0.92)),
                style: StrokeStyle(
                    lineWidth: hazard.kind == "water" ? 4 : 3,
                    lineCap: .round
                )
            )
        }

        let edges: [(Double, CGPoint?, CGFloat)] = hasFrontBack
            ? [(startMetres, frontPoint, 9), (endMetres, backPoint, -9)]
            : [(startMetres, frontPoint, 0)]
        for (metres, imagePoint, verticalOffset) in edges {
            guard let imagePoint else {
                continue
            }
            let yards = WatchHazardMapLayout.distanceYards(
                from: geometry.youPx, to: imagePoint, on: route
            ) ?? WatchHazardMapLayout.remainingYards(to: metres, after: playerProgressMetres)
            guard let yards = WatchGeoMath.usefulGolfYards(yards) else { continue }
            let point = canvas(imagePoint)
            let labelPoint = CGPoint(
                x: min(max(point.x, safeRect.minX + 17), safeRect.maxX - 17),
                y: min(max(point.y + verticalOffset, safeRect.minY + 30), safeRect.maxY - 12)
            )
            context.draw(
                context.resolve(
                    Text("\(yards)")
                        .font(.system(size: 12, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                ),
                at: labelPoint
            )
        }
    }

    private func controls(hazard: WatchHazard, index: Int, size: CGSize) -> some View {
        let safeInset = WatchDisplayGeometry.contentInset(for: size)
        let trackHeight = min(size.height * 0.55, 104)
        let thumbHeight = min(40, max(18, trackHeight * 0.28))
        let thumbOffset = CGFloat(index) * (trackHeight - thumbHeight)
            / CGFloat(max(upcoming.count - 1, 1))

        return ZStack {
            VStack {
                HStack(spacing: 4) {
                    WatchInstrumentBackButton(accessibilityLabel: "返回菜单", onBack: onBack)
                    Text(shortHazardTitle(hazard))
                        .font(.system(size: 12, weight: .bold))
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                    Spacer(minLength: WatchHazardMapLayout.systemTimeTrailingClearance)
                }
                .padding(.leading, max(0, safeInset - 6))
                Spacer()
                if upcoming.count > 1 {
                    Text("\(index + 1)/\(upcoming.count)")
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(.white.opacity(0.72))
                }
            }
            .padding(.top, safeInset)
            .padding(.bottom, safeInset)

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
                    .padding(.trailing, safeInset)
                }
            }
        }
    }

    private func shortHazardTitle(_ hazard: WatchHazard) -> String {
        if hazard.kind == "water" { return "水障碍" }
        return "沙坑"
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            WatchInstrumentBackButton(accessibilityLabel: "返回菜单", onBack: onBack)
            Text("前方没有可用障碍")
                .font(.caption)
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
                .font(.headline.weight(.bold))
            Text("回到本洞后再显示障碍距离")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(10)
    }

    private static func upcomingHazards(_ hazards: [WatchHazard], after progressMetres: Double) -> [WatchHazard] {
        hazards
            .filter { (WatchHazardMapLayout.alongRouteEndMetres(for: $0)
                ?? -Double.greatestFiniteMagnitude) > progressMetres }
            .sorted { ($0.startM ?? $0.endM ?? Double.greatestFiniteMagnitude)
                < ($1.startM ?? $1.endM ?? Double.greatestFiniteMagnitude) }
    }
}
