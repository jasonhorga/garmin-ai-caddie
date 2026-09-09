import SwiftUI
import AICaddieDomain
#if canImport(UIKit)
import UIKit
#endif

/// One player-facing obstacle row. The geometry fields stay in the same full-hole topo frame as the
/// bitmap, while the yardage fields can be replaced by a current-GPS readout without moving the row.
struct LiveHazardDisplayItem: Identifiable, Equatable {
    let id: String
    let kind: String
    let label: String
    let frontYards: Int
    let backYards: Int?
    let frontPx: [Double]
    let backPx: [Double]
    let frontRouteM: Double

    var isWater: Bool { kind == "water" }

    /// Build the complete, meaningful obstacle list for the dedicated surface. A live readout is
    /// matched by stable geometry id first, then by the nearest same-kind route station so a partial
    /// GPS response cannot attach a later obstacle's distance to the first one in the list.
    static func rows(
        for hole: CoursePrepHole,
        liveReadouts: [CoursePrepLiveHazardReadout]?
    ) -> [Self] {
        let route = hole.resolvedMapOverlay?.route
        let details = hole.hazards.details
            .filter { detail in
                guard detail.kind == "bunker" || detail.kind == "water" else { return false }
                guard detail.frontRouteM.isFinite, detail.backRouteM.isFinite else { return false }
                return max(detail.frontRouteM, detail.backRouteM) > 30.0
            }
            .sorted {
                if $0.frontRouteM == $1.frontRouteM { return $0.kind < $1.kind }
                return $0.frontRouteM < $1.frontRouteM
            }

        var rows: [Self] = []
        var detailOrdinals: [String: Int] = [:]
        var usedLiveIDs = Set<String>()
        for detail in details {
            let ordinal = detailOrdinals[detail.kind, default: 0]
            detailOrdinals[detail.kind] = ordinal + 1
            let id = "\(detail.kind)-\(ordinal)"
            let label = CoursePrepHazardNaming.label(kind: detail.kind, detail: detail, route: route)
            let live = liveReadouts?.first(where: { $0.id == id })
                ?? liveReadouts?
                    .filter { $0.kind == detail.kind && !usedLiveIDs.contains($0.id) }
                    .filter { $0.frontRouteM.isFinite && $0.frontRouteM > 0 }
                    .min {
                        abs($0.frontRouteM - detail.frontRouteM)
                            < abs($1.frontRouteM - detail.frontRouteM)
                    }
            if let live { usedLiveIDs.insert(live.id) }
            rows.append(
                Self(
                    id: id,
                    kind: detail.kind,
                    label: label,
                    frontYards: live?.toYards ?? CoursePrepRoute.yards(fromMetres: detail.frontM),
                    backYards: live?.overYards ?? CoursePrepRoute.yards(fromMetres: detail.backM),
                    frontPx: detail.frontPx,
                    backPx: detail.backPx,
                    frontRouteM: detail.frontRouteM
                )
            )
        }

        // Older downloaded packages expose interval arrays but no mapped detail rows. Keep those
        // facts in the list, without pretending a lateral bunker distance is a back edge.
        let detailKinds = Set(details.map(\.kind))
        if !detailKinds.contains("water") {
            for (index, interval) in hole.hazards.waterCarry.enumerated() {
                guard let front = interval.first else { continue }
                let back = interval.dropFirst().first
                guard max(front, back ?? front) > 30 else { continue }
                rows.append(
                    Self(
                        id: "water-legacy-\(index)",
                        kind: "water",
                        label: CoursePrepHazardNaming.legacyLabel(kind: "water", interval: interval, route: route),
                        frontYards: CoursePrepRoute.yards(fromMetres: front),
                        backYards: back.map { CoursePrepRoute.yards(fromMetres: $0) },
                        frontPx: [],
                        backPx: [],
                        frontRouteM: front
                    )
                )
            }
        }
        if !detailKinds.contains("bunker") {
            for (index, interval) in hole.hazards.bunkers.enumerated() {
                guard let front = interval.first, front > 30 else { continue }
                rows.append(
                    Self(
                        id: "bunker-legacy-\(index)",
                        kind: "bunker",
                        label: CoursePrepHazardNaming.legacyLabel(kind: "bunker", interval: interval, route: route),
                        frontYards: CoursePrepRoute.yards(fromMetres: front),
                        backYards: nil,
                        frontPx: [],
                        backPx: [],
                        frontRouteM: front
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

/// Full-hole obstacle instrument for live play. The main map remains uncluttered; this surface gives
/// every water/bunker a numbered visual span plus a vertically scrollable front/back distance row.
struct LiveHazardDetailView: View {
    @Environment(\.dismiss) private var dismiss

    let hole: CoursePrepHole
    let topoURL: URL?
    let liveReadouts: [CoursePrepLiveHazardReadout]?

    private let mapHeight: CGFloat = 320

    private var rows: [LiveHazardDisplayItem] {
        LiveHazardDisplayItem.rows(for: hole, liveReadouts: liveReadouts)
    }

    var body: some View {
        ZStack(alignment: .top) {
            LivePlayStyle.base.ignoresSafeArea()
            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 0) {
                    hazardMap
                    legend
                    Text(rows.isEmpty ? "本洞暂无可用障碍数据" : "全部障碍")
                        .font(.headline.weight(.heavy))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 16)
                        .padding(.top, 18)
                        .padding(.bottom, 8)
                    if rows.isEmpty {
                        Text("地图数据准备好后可重新打开")
                            .font(.subheadline)
                            .foregroundStyle(.white.opacity(0.62))
                            .padding(.horizontal, 16)
                            .padding(.bottom, 24)
                    } else {
                        VStack(spacing: 0) {
                            ForEach(Array(rows.enumerated()), id: \.element.id) { index, row in
                                hazardRow(row, index: index)
                                if index < rows.count - 1 {
                                    Divider().overlay(Color.white.opacity(0.10))
                                }
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.bottom, 28)
                    }
                }
                .padding(.top, 66)
            }
            header
        }
        .preferredColorScheme(.dark)
        .accessibilityIdentifier("live-hazard-detail")
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
            Text("\(rows.count) 个")
                .font(.caption.weight(.bold))
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
            ZStack(alignment: .topLeading) {
                HoleImageMapView(
                    hole: hole,
                    topoURL: topoURL,
                    showsCardChrome: false,
                    showsRecommendedRoute: false,
                    // The dedicated surface owns the numbered front/back spans below. The shared
                    // map must stay free of its coarse hazard layer or every obstacle is painted
                    // twice (once as an unnumbered span, once as the detailed instrument).
                    showsHazards: false
                )
                .frame(width: proxy.size.width, height: proxy.size.height)
                Canvas { context, size in
                    drawHazardSpans(&context, size: size)
                }
                .allowsHitTesting(false)
                Text("编号对应下方列表")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.white)
                    .padding(.vertical, 5)
                    .padding(.horizontal, 8)
                    .background(Color.black.opacity(0.62), in: Capsule())
                    .padding(.leading, 14)
                    .padding(.top, 12)
            }
        }
        .frame(height: mapHeight)
        .clipped()
        .background(Color.black.opacity(0.18))
        .accessibilityLabel("本洞障碍物分布图")
    }

    private var legend: some View {
        HStack(spacing: 18) {
            legendItem(color: Color(red: 0.20, green: 0.63, blue: 0.95), text: "水障碍")
            legendItem(color: Color(red: 0.96, green: 0.76, blue: 0.25), text: "沙坑")
            Spacer(minLength: 0)
            Text(liveReadouts == nil ? "发球台参考" : "当前位置")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.white.opacity(0.58))
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 11)
        .background(Color.black.opacity(0.20))
    }

    private func legendItem(color: Color, text: String) -> some View {
        HStack(spacing: 6) {
            Capsule().fill(color).frame(width: 20, height: 7)
            Text(text)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white.opacity(0.78))
        }
    }

    private func hazardRow(_ row: LiveHazardDisplayItem, index: Int) -> some View {
        HStack(alignment: .center, spacing: 10) {
            ZStack {
                Circle().fill(row.isWater ? Color.blue.opacity(0.22) : Color.yellow.opacity(0.20))
                Text("\(index + 1)")
                    .font(.caption.weight(.heavy))
                    .foregroundStyle(row.isWater ? Color.blue.opacity(0.95) : Color.yellow.opacity(0.95))
            }
            .frame(width: 30, height: 30)
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Image(systemName: row.isWater ? "drop.fill" : "square.grid.2x2.fill")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(row.isWater ? Color.blue : Color.yellow)
                    Text(row.label)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                        .lineLimit(2)
                }
                Text(row.isWater ? "水障碍" : "沙坑")
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(.white.opacity(0.52))
            }
            Spacer(minLength: 6)
            distanceColumn(title: "到前沿", value: row.frontYards)
            distanceColumn(title: "过后沿", value: row.backYards)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 12)
        .background(Color.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(index + 1)号\(row.isWater ? "水障碍" : "沙坑")，\(row.label)，到前沿 \(row.frontYards) 码，过后沿 \(row.backYards.map(String.init) ?? "未知")")
    }

    private func distanceColumn(title: String, value: Int?) -> some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.white.opacity(0.52))
            Text(value.map { "\($0) 码" } ?? "—")
                .font(.system(size: 15, weight: .heavy, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .frame(width: 54, alignment: .trailing)
    }

    private func drawHazardSpans(_ context: inout GraphicsContext, size: CGSize) {
        guard let overlay = hole.resolvedMapOverlay else { return }
        for (index, row) in rows.enumerated() {
            guard row.frontPx.count >= 2,
                  row.backPx.count >= 2,
                  let front = LivePlayMapOverlayLayout.project(
                      overlayPoint: row.frontPx,
                      overlayWidth: overlay.w,
                      overlayHeight: overlay.h,
                      into: size
                  ),
                  let back = LivePlayMapOverlayLayout.project(
                      overlayPoint: row.backPx,
                      overlayWidth: overlay.w,
                      overlayHeight: overlay.h,
                      into: size
                  ) else { continue }

            var span = Path()
            span.move(to: front)
            span.addLine(to: back)
            let tint = row.isWater
                ? Color(red: 0.20, green: 0.63, blue: 0.95)
                : Color(red: 0.96, green: 0.76, blue: 0.25)
            context.stroke(
                span,
                with: .color(.black.opacity(0.72)),
                style: StrokeStyle(lineWidth: 17, lineCap: .round)
            )
            context.stroke(
                span,
                with: .color(tint.opacity(0.92)),
                style: StrokeStyle(lineWidth: 11, lineCap: .round)
            )
            for point in [front, back] {
                context.fill(
                    Path(ellipseIn: CGRect(x: point.x - 5, y: point.y - 5, width: 10, height: 10)),
                    with: .color(tint)
                )
                context.stroke(
                    Path(ellipseIn: CGRect(x: point.x - 5, y: point.y - 5, width: 10, height: 10)),
                    with: .color(.black.opacity(0.70)),
                    style: StrokeStyle(lineWidth: 1)
                )
            }
            let midpoint = CGPoint(x: (front.x + back.x) / 2, y: (front.y + back.y) / 2)
            context.draw(
                Text("\(index + 1)")
                    .font(.system(size: 10, weight: .heavy, design: .rounded))
                    .foregroundColor(.black),
                at: midpoint
            )
        }
    }
}
