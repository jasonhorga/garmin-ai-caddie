import SwiftUI

enum WatchHazardMapLayout {
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

    private static func valid(_ row: [Double]) -> Bool {
        row.count >= 3 && row[0].isFinite && row[1].isFinite && row[2].isFinite
    }
}

/// Map detail for one of the real hazard intervals listed by ``WatchHazardView``. The map position and
/// remaining carry both come from the retained CoursePrep route; no lateral hazard location or flight
/// path is invented. Turning the Crown selects the next upcoming hazard.
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
    }

    private func hazardMap(_ hazard: WatchHazard, index: Int, size: CGSize) -> some View {
        let startMetres = hazard.startM ?? hazard.endM ?? playerProgressMetres
        let endMetres = hazard.endM ?? hazard.startM ?? startMetres
        let startPoint = WatchHazardMapLayout.imagePoint(on: route, atMetres: startMetres)
        let endPoint = WatchHazardMapLayout.imagePoint(on: route, atMetres: endMetres)
        let topImageY = [startPoint?.y, endPoint?.y].compactMap { $0 }.min() ?? geometry.pinPx.y
        let scale = CGFloat(WatchHoleMapViewport.effectiveRestingScale(
            requestedScale: WatchHoleMapView.restingCrownScale,
            viewportHeight: Double(size.height),
            playerAnchorFraction: 0.66,
            playerImageY: Double(geometry.youPx.y),
            pinImageY: Double(topImageY)
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

            controls(hazard: hazard, index: index)
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

        var measuredPoints: [CGPoint] = []
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
        let edges: [(String, Double, CGFloat)] = [
            ("进", startMetres, 13),
            ("过", endMetres, -13),
        ]
        for (label, metres, yOffset) in edges {
            guard let yards = WatchHazardMapLayout.remainingYards(to: metres, after: playerProgressMetres),
                  let imagePoint = WatchHazardMapLayout.imagePoint(on: route, atMetres: metres) else {
                continue
            }
            let point = canvas(imagePoint)
            let markerRect = CGRect(x: point.x - 5, y: point.y - 5, width: 10, height: 10)
            context.fill(Path(ellipseIn: markerRect), with: .color(tint))
            context.stroke(Path(ellipseIn: markerRect), with: .color(.black), style: StrokeStyle(lineWidth: 1.3))

            let text = "\(label) \(yards)"
            let pillWidth: CGFloat = 68
            let preferredX = point.x > size.width * 0.5
                ? point.x - pillWidth * 0.5 - 10
                : point.x + pillWidth * 0.5 + 10
            let pillCenter = CGPoint(
                x: min(max(preferredX, pillWidth * 0.5 + 4), size.width - pillWidth * 0.5 - 4),
                y: min(max(point.y + yOffset, 13), size.height - 13)
            )
            let rect = CGRect(
                x: pillCenter.x - pillWidth * 0.5,
                y: pillCenter.y - 11,
                width: pillWidth,
                height: 22
            )
            context.fill(Path(roundedRect: rect, cornerRadius: 11), with: .color(.black.opacity(0.82)))
            context.stroke(Path(roundedRect: rect, cornerRadius: 11), with: .color(tint), style: StrokeStyle(lineWidth: 1.2))
            context.draw(
                context.resolve(Text(text).font(.system(size: 10, weight: .semibold)).foregroundColor(.white)),
                at: pillCenter
            )
        }
    }

    private func controls(hazard: WatchHazard, index: Int) -> some View {
        ZStack {
            VStack {
                HStack {
                    Button(action: onBack) {
                        Image(systemName: "chevron.backward")
                            .font(.system(size: 12, weight: .bold))
                            .padding(6)
                            .background(Circle().fill(.black.opacity(0.72)))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("返回障碍列表")
                    Spacer()
                }
                Spacer()
            }
            .padding(6)

            VStack {
                if centerGreenYards > 0 {
                    Text("中 \(centerGreenYards) 码 · 到果岭")
                        .font(.system(size: 11, weight: .semibold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(Capsule().fill(.black.opacity(0.72)))
                }
                Spacer()
                VStack(spacing: 1) {
                    Text("\(hazard.label) · \(index + 1)/\(upcoming.count)")
                        .font(.system(size: 10, weight: .semibold))
                    Text(upcoming.count > 1 ? "转表冠换障碍" : "障碍前后沿")
                        .font(.system(size: 8.5, weight: .medium))
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 9)
                .padding(.vertical, 4)
                .background(Capsule().fill(.black.opacity(0.78)))
            }
            .padding(.top, 5)
            .padding(.bottom, 5)
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
            .filter { ($0.endM ?? $0.startM ?? -Double.greatestFiniteMagnitude) > progressMetres }
            .sorted { ($0.startM ?? $0.endM ?? Double.greatestFiniteMagnitude)
                < ($1.startM ?? $1.endM ?? Double.greatestFiniteMagnitude) }
    }
}
