import SwiftUI
import AICaddieDomain
#if canImport(UIKit)
import UIKit
#endif

/// One player-facing obstacle. Geometry stays in the full-hole topo frame; distances become
/// current-position readings as soon as a qualified GPS fix is available.
struct LiveHazardDisplayItem: Identifiable, Equatable {
    let id: String
    let kind: String
    let label: String
    let frontYards: Int
    let backYards: Int?
    let frontPx: [Double]
    let backPx: [Double]
    let outlinePx: [[Double]]
    let frontRouteM: Double
    let backRouteM: Double

    var isWater: Bool { kind == "water" }

    static func rows(
        for hole: CoursePrepHole,
        liveReadouts: [CoursePrepLiveHazardReadout]?
    ) -> [Self] {
        let routeLengthM = hole.resolvedMapOverlay?.ln ?? hole.routeLenM

        // A non-nil live result is authoritative for what remains ahead. Falling back to tee
        // distances for unmatched geometry resurrected already-passed hazards during live play.
        if let liveReadouts {
            return liveReadouts
                .filter {
                    ($0.kind == "bunker" || $0.kind == "water")
                        && CoursePrepHazardRelevance.isRelevant(
                            kind: $0.kind,
                            frontRouteM: $0.frontRouteM,
                            backRouteM: $0.backRouteM,
                            routeLengthM: routeLengthM
                        )
                        && CoursePrepLiveHazardReadout.isPlausibleYards($0.toYards)
                        && CoursePrepLiveHazardReadout.isPlausibleYards($0.overYards)
                }
                .sorted {
                    if $0.toYards == $1.toYards { return $0.id < $1.id }
                    return $0.toYards < $1.toYards
                }
                .map {
                    Self(
                        id: $0.id,
                        kind: $0.kind,
                        label: $0.label,
                        frontYards: $0.toYards,
                        backYards: $0.overYards,
                        frontPx: $0.frontPx,
                        backPx: $0.backPx,
                        outlinePx: $0.outlinePx,
                        frontRouteM: $0.frontRouteM,
                        backRouteM: $0.backRouteM
                    )
                }
        }

        let route = hole.resolvedMapOverlay?.route
        // Precise rows need the overlay's topo-pixel route for lateral naming. Legacy interval
        // rows have no pixels, so their area label can safely use the raw cumulative route.
        let legacyRoute = route ?? hole.route
        let details = hole.hazards.details
            .filter {
                ($0.kind == "bunker" || $0.kind == "water")
                    && CoursePrepHazardRelevance.isRelevant(
                        kind: $0.kind,
                        frontRouteM: $0.frontRouteM,
                        backRouteM: $0.backRouteM,
                        routeLengthM: routeLengthM
                    )
                    && CoursePrepLiveHazardReadout.isPlausibleYards(
                        CoursePrepRoute.yards(fromMetres: $0.frontM)
                    )
                    && CoursePrepLiveHazardReadout.isPlausibleYards(
                        CoursePrepRoute.yards(fromMetres: $0.backM)
                    )
            }
            .sorted {
                if $0.frontRouteM == $1.frontRouteM { return $0.kind < $1.kind }
                return $0.frontRouteM < $1.frontRouteM
            }

        var rows: [Self] = []
        var ordinals: [String: Int] = [:]
        for detail in details {
            let ordinal = ordinals[detail.kind, default: 0]
            ordinals[detail.kind] = ordinal + 1
            rows.append(
                Self(
                    id: "\(detail.kind)-\(ordinal)",
                    kind: detail.kind,
                    label: CoursePrepHazardNaming.label(kind: detail.kind, detail: detail, route: route),
                    frontYards: CoursePrepRoute.yards(fromMetres: detail.frontM),
                    backYards: CoursePrepRoute.yards(fromMetres: detail.backM),
                    frontPx: detail.frontPx,
                    backPx: detail.backPx,
                    outlinePx: detail.outlinePx,
                    frontRouteM: detail.frontRouteM,
                    backRouteM: detail.backRouteM
                )
            )
        }

        // Legacy packages can still supply interval facts without map boundary pixels.
        let detailKinds = Set(details.map(\.kind))
        if !detailKinds.contains("water") {
            for (index, interval) in hole.hazards.waterCarry.enumerated() {
                guard let front = interval.first else { continue }
                let back = interval.dropFirst().first
                guard CoursePrepHazardRelevance.isRelevant(
                    kind: "water",
                    frontRouteM: front,
                    backRouteM: back ?? front,
                    routeLengthM: routeLengthM
                ) else { continue }
                rows.append(
                    Self(
                        id: "water-legacy-\(index)",
                        kind: "water",
                        label: CoursePrepHazardNaming.legacyLabel(kind: "water", interval: interval, route: legacyRoute),
                        frontYards: CoursePrepRoute.yards(fromMetres: front),
                        backYards: back.map { CoursePrepRoute.yards(fromMetres: $0) },
                        frontPx: [],
                        backPx: [],
                        outlinePx: [],
                        frontRouteM: front,
                        backRouteM: back ?? front
                    )
                )
            }
        }
        if !detailKinds.contains("bunker") {
            for (index, interval) in hole.hazards.bunkers.enumerated() {
                guard let front = interval.first,
                      CoursePrepHazardRelevance.isRelevant(
                        kind: "bunker",
                        frontRouteM: front,
                        backRouteM: front,
                        routeLengthM: routeLengthM
                      ) else { continue }
                rows.append(
                    Self(
                        id: "bunker-legacy-\(index)",
                        kind: "bunker",
                        label: CoursePrepHazardNaming.legacyLabel(kind: "bunker", interval: interval, route: legacyRoute),
                        frontYards: CoursePrepRoute.yards(fromMetres: front),
                        backYards: nil,
                        frontPx: [],
                        backPx: [],
                        outlinePx: [],
                        frontRouteM: front,
                        backRouteM: front
                    )
                )
            }
        }
        return rows.sorted {
            if $0.frontRouteM == $1.frontRouteM { return $0.id < $1.id }
            return $0.frontRouteM < $1.frontRouteM
        }
    }
}

/// Dedicated one-at-a-time hazard browser. The selected obstacle is circled on the course image;
/// its front and back edges are the only large numbers on screen.
struct LiveHazardDetailView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var selectedHazardID: String?

    let hole: CoursePrepHole
    let topoURL: URL?
    let liveReadouts: [CoursePrepLiveHazardReadout]?

    private let mapHeight: CGFloat = 390

    init(
        hole: CoursePrepHole,
        topoURL: URL?,
        liveReadouts: [CoursePrepLiveHazardReadout]?
    ) {
        self.hole = hole
        self.topoURL = topoURL
        self.liveReadouts = liveReadouts
        _selectedHazardID = State(
            initialValue: LiveHazardDisplayItem.rows(for: hole, liveReadouts: liveReadouts).first?.id
        )
    }

    private var rows: [LiveHazardDisplayItem] {
        LiveHazardDisplayItem.rows(for: hole, liveReadouts: liveReadouts)
    }

    private var selectedIndex: Int? {
        guard !rows.isEmpty else { return nil }
        return rows.firstIndex(where: { $0.id == selectedHazardID }) ?? 0
    }

    private var selectedHazard: LiveHazardDisplayItem? {
        guard let selectedIndex else { return nil }
        return rows[selectedIndex]
    }

    var body: some View {
        ZStack(alignment: .top) {
            LivePlayStyle.base.ignoresSafeArea()
            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 0) {
                    hazardMap
                    if rows.isEmpty {
                        Text("本洞暂无可用障碍数据")
                            .font(.headline.weight(.heavy))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 16)
                            .padding(.top, 18)
                        Text("地图数据准备好后可重新打开")
                            .font(.subheadline)
                            .foregroundStyle(.white.opacity(0.62))
                            .padding(.horizontal, 16)
                            .padding(.bottom, 24)
                    } else if let selectedHazard, let selectedIndex {
                        selectedHazardPanel(selectedHazard, index: selectedIndex)
                            .padding(.horizontal, 16)
                            .padding(.top, 14)
                            .padding(.bottom, 28)
                    }
                }
                .padding(.top, 66)
            }
            header
        }
        .preferredColorScheme(.dark)
        .accessibilityIdentifier("live-hazard-detail")
        .onChange(of: rows.map(\.id)) { _, ids in
            if selectedHazardID == nil || !ids.contains(selectedHazardID ?? "") {
                selectedHazardID = ids.first
            }
        }
    }

    private var header: some View {
        HStack(spacing: 10) {
            Button { dismiss() } label: {
                Image(systemName: "chevron.backward")
                    .font(.system(size: 15, weight: .bold))
                    .frame(width: 40, height: 40)
                    .background(Color.black.opacity(0.68), in: Circle())
                    .overlay(Circle().stroke(Color.white.opacity(0.2)))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("关闭障碍物")
            Text("第 \(hole.hole) 洞 · 障碍物")
                .font(.headline.weight(.heavy))
                .foregroundStyle(.white)
                .lineLimit(1)
            Spacer(minLength: 0)
            Text(selectedIndex.map { "\($0 + 1) / \(rows.count)" } ?? "0 / 0")
                .font(.caption.monospacedDigit().weight(.bold))
                .foregroundStyle(.white.opacity(0.72))
        }
        .padding(.horizontal, 16)
        .padding(.top, 8)
        .padding(.bottom, 8)
        .background(
            LinearGradient(
                colors: [LivePlayStyle.base.opacity(0.98), LivePlayStyle.base.opacity(0.82)],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea(edges: .top)
        )
    }

    private var hazardMap: some View {
        GeometryReader { proxy in
            ZStack {
                HoleImageMapView(
                    hole: hole,
                    topoURL: topoURL,
                    showsCardChrome: false,
                    showsRecommendedRoute: false,
                    showsHazards: false
                )
                .frame(width: proxy.size.width, height: proxy.size.height)
                Canvas { context, size in
                    drawSelectedHazard(&context, size: size)
                }
                .allowsHitTesting(false)
                .accessibilityIdentifier("selected-hazard-map-outline")
            }
        }
        .frame(height: mapHeight)
        .clipped()
        .background(Color.black.opacity(0.18))
        .accessibilityLabel("当前障碍物位置")
    }

    private func selectedHazardPanel(_ row: LiveHazardDisplayItem, index: Int) -> some View {
        VStack(spacing: 16) {
            HStack(spacing: 10) {
                Image(systemName: row.isWater ? "drop.fill" : "square.grid.2x2.fill")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(row.isWater ? Color.blue : Color.yellow)
                VStack(alignment: .leading, spacing: 2) {
                    Text(row.label)
                        .font(.headline.weight(.bold))
                        .foregroundStyle(.white)
                    Text(row.isWater ? "水障碍" : "沙坑")
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.58))
                }
                Spacer()
                Text(liveReadouts == nil ? "发球台参考" : "当前位置")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white.opacity(0.62))
            }

            HStack(spacing: 0) {
                distanceColumn(title: "到前沿", value: row.frontYards)
                Divider()
                    .frame(height: 58)
                    .overlay(Color.white.opacity(0.16))
                distanceColumn(title: "过后沿", value: row.backYards)
            }

            HStack(spacing: 18) {
                navigationButton(
                    systemName: "chevron.up",
                    label: "上一个障碍",
                    identifier: "hazard-previous"
                ) {
                    select(index: index - 1)
                }
                .disabled(index == 0)
                .opacity(index == 0 ? 0.35 : 1)
                Text("\(index + 1) / \(rows.count)")
                    .font(.subheadline.monospacedDigit().weight(.bold))
                    .foregroundStyle(.white.opacity(0.78))
                    .frame(minWidth: 58)
                navigationButton(
                    systemName: "chevron.down",
                    label: "下一个障碍",
                    identifier: "hazard-next"
                ) {
                    select(index: index + 1)
                }
                .disabled(index == rows.count - 1)
                .opacity(index == rows.count - 1 ? 0.35 : 1)
            }
        }
        .padding(16)
        .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .strokeBorder(Color.white.opacity(0.10), lineWidth: 1)
        )
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("selected-hazard-\(index + 1)")
    }

    private func distanceColumn(title: String, value: Int?) -> some View {
        VStack(spacing: 3) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white.opacity(0.58))
            Text(value.map(String.init) ?? "—")
                .font(.system(size: 34, weight: .heavy, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text("码")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white.opacity(0.58))
        }
        .frame(maxWidth: .infinity)
    }

    private func navigationButton(
        systemName: String,
        label: String,
        identifier: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 17, weight: .bold))
                .frame(width: 44, height: 44)
                .background(Color.white.opacity(0.10), in: Circle())
                .foregroundStyle(.white)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityIdentifier(identifier)
    }

    private func select(index: Int) {
        guard rows.indices.contains(index) else { return }
        selectedHazardID = rows[index].id
        #if canImport(UIKit)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
    }

    private func drawSelectedHazard(_ context: inout GraphicsContext, size: CGSize) {
        guard let row = selectedHazard,
              let overlay = hole.resolvedMapOverlay else { return }

        let front = hazardPoint(
            pixels: row.frontPx,
            routeMetres: row.frontRouteM,
            overlay: overlay,
            size: size
        )
        let back = hazardPoint(
            pixels: row.backPx,
            routeMetres: row.backRouteM,
            overlay: overlay,
            size: size
        )
        // An outline is already in the topo-pixel frame. Never interpolate malformed outline
        // points along the route: doing so can draw a false segment at the tee. Only the legacy
        // front/back markers are allowed to use route interpolation below.
        let outlinePoints = row.outlinePx.compactMap {
            projectedHazardPixelPoint(pixels: $0, overlay: overlay, size: size)
        }

        // Precise prep carries the ordered mesh boundary. Draw it as a translucent filled shape
        // with a high-contrast red halo so the selected obstacle remains readable over the topo
        // raster. Older packages have no polygon and use only the narrow front/back span below.
        if outlinePoints.count >= 3 {
            var outline = Path()
            outline.move(to: outlinePoints[0])
            for point in outlinePoints.dropFirst() {
                outline.addLine(to: point)
            }
            outline.closeSubpath()
            context.fill(outline, with: .color(Color(red: 0.95, green: 0.16, blue: 0.14).opacity(0.12)))
            context.stroke(outline, with: .color(.black.opacity(0.78)), style: StrokeStyle(lineWidth: 8))
            context.stroke(
                outline,
                with: .color(Color(red: 0.95, green: 0.16, blue: 0.14)),
                style: StrokeStyle(lineWidth: 3)
            )
        } else if let front, let back {
            // Do not invent an oversized oval from two points. A restrained span is honest about
            // the legacy data while still making the selected obstacle obvious.
            var span = Path()
            span.move(to: front)
            span.addLine(to: back)
            context.stroke(span, with: .color(.black.opacity(0.78)), style: StrokeStyle(lineWidth: 14, lineCap: .round))
            context.stroke(
                span,
                with: .color(Color(red: 0.95, green: 0.16, blue: 0.14)),
                style: StrokeStyle(lineWidth: 7, lineCap: .round)
            )
        }

        for (point, label) in [(front, "前"), (back, "后")] {
            guard let point else { continue }
            let marker = Path(ellipseIn: CGRect(x: point.x - 6, y: point.y - 6, width: 12, height: 12))
            context.fill(marker, with: .color(Color(red: 0.95, green: 0.16, blue: 0.14)))
            context.stroke(marker, with: .color(.white), style: StrokeStyle(lineWidth: 1.5))
            context.draw(
                Text(label).font(.system(size: 10, weight: .heavy)).foregroundColor(.white),
                at: CGPoint(x: point.x + 13, y: point.y)
            )
        }
    }

    /// Precise prep supplies real boundary pixels. Legacy packages only know the interval along the
    /// measured route, so interpolate that route rather than leaving the selected obstacle unmarked.
    private func hazardPoint(
        pixels: [Double],
        routeMetres: Double,
        overlay: CoursePrepOverlay,
        size: CGSize
    ) -> CGPoint? {
        if let projected = projectedHazardPixelPoint(pixels: pixels, overlay: overlay, size: size) {
            return projected
        }
        guard let overlayPoint = HoleImageMapView.landingOverlayPoint(overlay, targetMetres: routeMetres) else {
            return nil
        }
        return LivePlayMapOverlayLayout.project(
            overlayPoint: overlayPoint,
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            into: size
        )
    }

    private func projectedHazardPixelPoint(
        pixels: [Double],
        overlay: CoursePrepOverlay,
        size: CGSize
    ) -> CGPoint? {
        guard pixels.count >= 2,
              pixels.prefix(2).allSatisfy(\.isFinite) else {
            return nil
        }
        return LivePlayMapOverlayLayout.project(
            overlayPoint: pixels,
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            into: size
        )
    }
}
