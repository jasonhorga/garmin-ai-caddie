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

        let route = hole.resolvedMapOverlay?.route
        // Precise rows need the overlay's topo-pixel route for lateral naming. Interval-only
        // rows have no pixels, so their area label can safely use the raw cumulative route.
        let intervalRoute = route ?? hole.route
        let details = hole.hazards.details
            .filter {
                ($0.kind == "bunker" || $0.kind == "water")
                    && CoursePrepHazardRelevance.isRelevant(
                        kind: $0.kind,
                        frontRouteM: $0.frontRouteM,
                        backRouteM: $0.backRouteM,
                        routeLengthM: routeLengthM,
                        hasPreciseOutline: $0.outlinePx.count >= 3
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

        // Compatibility packages can still supply interval facts without map boundary pixels.
        // Merge them individually, rather than checking only whether a kind exists: a package may
        // have precise data for one bunker while its second greenside bunker survives only in the
        // legacy interval list.
        func hasDetail(kind: String, interval: [Double]) -> Bool {
            guard let start = interval.first, start.isFinite else { return false }
            let end = interval.dropFirst().first(where: { $0.isFinite }) ?? start
            let legacyNear = min(start, end)
            let legacyFar = max(start, end)
            let compatibilityTolerance = 8.0
            return details.contains { detail in
                guard detail.kind == kind else { return false }
                let detailNear = min(detail.frontRouteM, detail.backRouteM)
                let detailFar = max(detail.frontRouteM, detail.backRouteM)
                // Legacy bunker rows only carry one route station; treating that station as a
                // point inside the precise span avoids duplicating the same bunker when the two
                // encoders differ by a few metres. Water rows carry both edges, so the same gap
                // test naturally handles either representation.
                let gap = max(detailNear - legacyFar, legacyNear - detailFar, 0)
                return gap <= compatibilityTolerance
            }
        }
        for (index, interval) in hole.hazards.waterCarry.enumerated() {
            guard let front = interval.first,
                  !hasDetail(kind: "water", interval: interval) else { continue }
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
                    label: CoursePrepHazardNaming.intervalLabel(kind: "water", interval: interval, route: intervalRoute),
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
        for (index, interval) in hole.hazards.bunkers.enumerated() {
            guard let front = interval.first,
                  !hasDetail(kind: "bunker", interval: interval),
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
                    label: CoursePrepHazardNaming.intervalLabel(kind: "bunker", interval: interval, route: intervalRoute),
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
        let staticRows = rows.sorted {
            if $0.frontRouteM == $1.frontRouteM { return $0.id < $1.id }
            return $0.frontRouteM < $1.frontRouteM
        }
        guard let liveReadouts else { return staticRows }

        // Live GPS readouts refine distances for hazards that are ahead, but they are not a
        // completeness filter. Keep every mapped bunker/water from the hole and overlay live
        // values where the geometry matches; this prevents a greenside bunker from disappearing
        // merely because the GPS readout producer returned only the next obstacle.
        let liveRows = liveReadouts
            .filter {
                ($0.kind == "bunker" || $0.kind == "water")
                    && CoursePrepHazardRelevance.isRelevant(
                    kind: $0.kind,
                    frontRouteM: $0.frontRouteM,
                    backRouteM: $0.backRouteM,
                    routeLengthM: routeLengthM,
                    hasPreciseOutline: $0.outlinePx.count >= 3
                    )
                    && CoursePrepLiveHazardReadout.isPlausibleYards($0.toYards)
                    && CoursePrepLiveHazardReadout.isPlausibleYards($0.overYards)
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

        var merged = staticRows
        var matchedLiveIDs = Set<String>()
        for index in merged.indices {
            let row = merged[index]
            let match = liveRows.first(where: { $0.id == row.id && !matchedLiveIDs.contains($0.id) })
                ?? liveRows
                    .filter { !$0.id.isEmpty && !matchedLiveIDs.contains($0.id) && $0.kind == row.kind }
                    .min(by: { abs($0.frontRouteM - row.frontRouteM) < abs($1.frontRouteM - row.frontRouteM) })
            guard let live = match else { continue }
            matchedLiveIDs.insert(live.id)
            merged[index] = Self(
                id: row.id,
                kind: row.kind,
                label: live.label,
                frontYards: live.frontYards,
                backYards: live.backYards,
                frontPx: live.frontPx.isEmpty ? row.frontPx : live.frontPx,
                backPx: live.backPx.isEmpty ? row.backPx : live.backPx,
                outlinePx: live.outlinePx.count >= 3 ? live.outlinePx : row.outlinePx,
                frontRouteM: live.frontRouteM,
                backRouteM: live.backRouteM
            )
        }
        merged.append(contentsOf: liveRows.filter { !matchedLiveIDs.contains($0.id) })
        return merged.sorted {
            if $0.frontRouteM == $1.frontRouteM { return $0.id < $1.id }
            return $0.frontRouteM < $1.frontRouteM
        }
    }
}

/// Draws one selected factual obstacle in the viewport plane. Map pixels are transformed first, so
/// the polygon follows pan/zoom while its red stroke, edge points and labels remain the same screen
/// size at every scale.
enum LiveHazardOverlayRenderer {
    static func draw(
        _ context: inout GraphicsContext,
        size: CGSize,
        hole: CoursePrepHole,
        row: LiveHazardDisplayItem,
        scale: CGFloat,
        offset: CGSize,
        topInset: CGFloat = 0
    ) {
        guard let overlay = hole.resolvedMapOverlay else { return }
        let baseFront = hazardPoint(
            pixels: row.frontPx,
            routeMetres: row.frontRouteM,
            overlay: overlay,
            size: size,
            topInset: topInset
        )
        let baseBack = hazardPoint(
            pixels: row.backPx,
            routeMetres: row.backRouteM,
            overlay: overlay,
            size: size,
            topInset: topInset
        )
        let front = baseFront.flatMap { transformed($0, in: size, scale: scale, offset: offset) }
        let back = baseBack.flatMap { transformed($0, in: size, scale: scale, offset: offset) }
        let outline = row.outlinePx.compactMap { point -> CGPoint? in
            guard let projected = projectedHazardPixelPoint(
                pixels: point,
                overlay: overlay,
                size: size,
                topInset: topInset
            ) else { return nil }
            return transformed(projected, in: size, scale: scale, offset: offset)
        }

        let red = Color(red: 0.95, green: 0.16, blue: 0.14)
        if outline.count >= 3 {
            var path = Path()
            path.move(to: outline[0])
            for point in outline.dropFirst() { path.addLine(to: point) }
            path.closeSubpath()
            context.stroke(path, with: .color(red), style: StrokeStyle(lineWidth: 1.2, lineJoin: .round))
        }

        let annotations: [(point: CGPoint?, label: String, yards: Int?)] = [
            (front, "前", Optional(row.frontYards)),
            (back, "后", row.backYards),
        ]
        for (point, label, yards) in annotations {
            guard let point else { continue }
            context.fill(
                Path(ellipseIn: CGRect(x: point.x - 3.5, y: point.y - 3.5, width: 7, height: 7)),
                with: .color(red)
            )
            let labelCenter = LiveHazardAnnotationLayout.outsideLabelCenter(
                for: point,
                isFront: label == "前",
                outline: outline,
                viewportSize: size
            )
            let labelText = yards.map { "\(label) \($0)" } ?? label
            let labelWidth: CGFloat = yards == nil ? LiveHazardAnnotationLayout.labelWidth : 52
            let labelRect = CGRect(
                x: labelCenter.x - labelWidth / 2,
                y: labelCenter.y - LiveHazardAnnotationLayout.labelHeight / 2,
                width: labelWidth,
                height: LiveHazardAnnotationLayout.labelHeight
            )
            context.fill(
                Path(roundedRect: labelRect, cornerRadius: 5),
                with: .color(.black.opacity(0.64))
            )
            context.draw(
                Text(labelText)
                    .font(.system(size: 10, weight: .heavy, design: .rounded))
                    .foregroundColor(.white),
                at: labelCenter
            )
        }
    }

    private static func transformed(
        _ point: CGPoint,
        in size: CGSize,
        scale: CGFloat,
        offset: CGSize
    ) -> CGPoint? {
        guard point.x.isFinite, point.y.isFinite,
              size.width > 0, size.height > 0,
              scale.isFinite, scale > 0 else { return nil }
        return CGPoint(
            x: (point.x - size.width / 2) * scale + size.width / 2 + offset.width,
            y: (point.y - size.height / 2) * scale + size.height / 2 + offset.height
        )
    }

    private static func hazardPoint(
        pixels: [Double],
        routeMetres: Double,
        overlay: CoursePrepOverlay,
        size: CGSize,
        topInset: CGFloat
    ) -> CGPoint? {
        if let projected = projectedHazardPixelPoint(
            pixels: pixels,
            overlay: overlay,
            size: size,
            topInset: topInset
        ) {
            return projected
        }
        guard let overlayPoint = HoleImageMapView.landingOverlayPoint(
            overlay,
            targetMetres: routeMetres
        ) else { return nil }
        return LivePlayMapOverlayLayout.project(
            overlayPoint: overlayPoint,
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            into: size,
            topInset: topInset
        )
    }

    private static func projectedHazardPixelPoint(
        pixels: [Double],
        overlay: CoursePrepOverlay,
        size: CGSize,
        topInset: CGFloat
    ) -> CGPoint? {
        guard pixels.count >= 2,
              pixels.prefix(2).allSatisfy(\.isFinite) else { return nil }
        return LivePlayMapOverlayLayout.project(
            overlayPoint: pixels,
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            into: size,
            topInset: topInset
        )
    }
}

/// Dedicated one-at-a-time hazard browser. The selected obstacle is outlined only when the backend
/// supplies its real polygon; compatibility packages show the factual edge markers without inventing a
/// shape. Its front and back edges are the only large numbers on screen.
struct LiveHazardDetailView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var selectedHazardID: String?
    @State private var mapScale: CGFloat = 1
    @State private var mapOffset: CGSize = .zero
    @State private var transientMapOffset: CGSize = .zero
    @GestureState private var pinchScale: CGFloat = 1

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
            .scrollDisabled(mapScale > 1.01 || abs(pinchScale - 1) > 0.01)
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
            let displayedScale = min(max(mapScale * pinchScale, 1), 4)
            let proposedOffset = CGSize(
                width: mapOffset.width + transientMapOffset.width,
                height: mapOffset.height + transientMapOffset.height
            )
            let displayedOffset = clamped(
                proposedOffset,
                in: proxy.size,
                scale: displayedScale
            )
            ZStack(alignment: .topTrailing) {
                hazardMapContent(size: proxy.size)
                    .scaleEffect(displayedScale)
                    .offset(displayedOffset)

                // Keep geometry in the transformed map plane, but keep edge readouts in the
                // viewport plane so zooming never makes dots or numbers cover the obstacle.
                hazardMapAnnotationLayer(
                    size: proxy.size,
                    scale: displayedScale,
                    offset: displayedOffset
                )

                hazardMapInteraction(size: proxy.size)

                VStack(spacing: 8) {
                    hazardMapControl(
                        systemName: "plus.magnifyingglass",
                        label: "放大障碍物地图",
                        identifier: "live-hazard-zoom-in"
                    ) {
                        changeMapScale(by: 0.5, in: proxy.size)
                    }
                    hazardMapControl(
                        systemName: "minus.magnifyingglass",
                        label: "缩小障碍物地图",
                        identifier: "live-hazard-zoom-out"
                    ) {
                        changeMapScale(by: -0.5, in: proxy.size)
                    }
                    hazardMapControl(
                        systemName: "scope",
                        label: "还原障碍物地图",
                        identifier: "live-hazard-fit"
                    ) {
                        resetMapViewport()
                    }
                }
                .padding(.top, 12)
                .padding(.trailing, 12)
            }
            .frame(width: proxy.size.width, height: proxy.size.height)
            .clipped()
            .animation(nil, value: transientMapOffset)
        }
        .frame(height: mapHeight)
        .clipped()
        .background(Color.black.opacity(0.18))
        .accessibilityLabel("当前障碍物位置")
    }

    @ViewBuilder
    private func hazardMapContent(size: CGSize) -> some View {
        ZStack {
            HoleImageMapView(
                hole: hole,
                topoURL: topoURL,
                showsCardChrome: false,
                showsRecommendedRoute: false,
                showsHazards: false
            )
            .frame(width: size.width, height: size.height)
            Canvas { context, canvasSize in
                drawSelectedHazardGeometry(&context, size: canvasSize)
            }
            .allowsHitTesting(false)
            .accessibilityIdentifier("selected-hazard-map-outline")
        }
        .frame(width: size.width, height: size.height)
    }

    private func hazardMapAnnotationLayer(
        size: CGSize,
        scale: CGFloat,
        offset: CGSize
    ) -> some View {
        Canvas { context, canvasSize in
            drawSelectedHazardAnnotations(
                &context,
                size: canvasSize,
                scale: scale,
                offset: offset
            )
        }
        .frame(width: size.width, height: size.height)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private func hazardMapInteraction(size: CGSize) -> some View {
        Rectangle()
            .fill(.clear)
            .frame(width: size.width, height: size.height)
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 4)
                    .onChanged { value in
                        guard mapScale * pinchScale > 1.01 else { return }
                        transientMapOffset = value.translation
                    }
                    .onEnded { value in
                        guard mapScale > 1.01 || abs(pinchScale - 1) > 0.01 else {
                            transientMapOffset = .zero
                            return
                        }
                        mapOffset = clamped(
                            CGSize(
                                width: mapOffset.width + value.translation.width,
                                height: mapOffset.height + value.translation.height
                            ),
                            in: size,
                            scale: mapScale
                        )
                        transientMapOffset = .zero
                    }
            )
            .simultaneousGesture(
                MagnificationGesture()
                    .updating($pinchScale) { value, state, _ in state = value }
                    .onEnded { value in
                        mapScale = min(max(mapScale * value, 1), 4)
                        mapOffset = clamped(mapOffset, in: size, scale: mapScale)
                    }
            )
            .accessibilityHidden(true)
    }

    private func hazardMapControl(
        systemName: String,
        label: String,
        identifier: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 15, weight: .bold))
                .foregroundStyle(.black)
                .frame(width: 38, height: 38)
                .background(Color.white.opacity(0.94), in: Circle())
                .shadow(color: .black.opacity(0.28), radius: 3, y: 1)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityIdentifier(identifier)
    }

    private func changeMapScale(by delta: CGFloat, in size: CGSize) {
        withAnimation(.easeInOut(duration: 0.18)) {
            mapScale = min(max(mapScale + delta, 1), 4)
            mapOffset = clamped(mapOffset, in: size, scale: mapScale)
        }
    }

    private func resetMapViewport() {
        withAnimation(.easeInOut(duration: 0.18)) {
            mapScale = 1
            mapOffset = .zero
            transientMapOffset = .zero
        }
    }

    private func clamped(_ value: CGSize, in size: CGSize, scale: CGFloat) -> CGSize {
        guard let overlay = hole.resolvedMapOverlay,
              let frame = LivePlayMapOverlayLayout.mapFrame(
                  overlayWidth: overlay.w,
                  overlayHeight: overlay.h,
                  in: size
              ) else {
            return scale > 1 ? value : .zero
        }
        return LivePlayMapOverlayLayout.clampedOffset(
            value,
            mapFrame: frame,
            viewportSize: size,
            scale: scale
        )
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
        // Keep the current zoom and viewport when moving through the list. The player can inspect
        // the next obstacle in the same enlarged region and pan afterward if its boundary is offscreen.
        #if canImport(UIKit)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
    }

    /// The outline and edge annotations are both rendered in the fixed viewport layer below. Keeping
    /// this map plane free of strokes prevents a 3x zoom from turning a 1 px boundary into a red bar.
    private func drawSelectedHazardGeometry(_ context: inout GraphicsContext, size: CGSize) {
        // Intentionally empty; see `drawSelectedHazardAnnotations` for the fixed-pixel outline.
        _ = context
        _ = size
    }

    private func drawSelectedHazardAnnotations(
        _ context: inout GraphicsContext,
        size: CGSize,
        scale: CGFloat,
        offset: CGSize
    ) {
        guard let row = selectedHazard else { return }
        LiveHazardOverlayRenderer.draw(
            &context,
            size: size,
            hole: hole,
            row: row,
            scale: scale,
            offset: offset
        )
    }
}
