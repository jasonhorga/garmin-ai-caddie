import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// 球洞 2D 俯视图:服务端渲染的真实球场图(球道/果岭/沙坑/水)+ 推荐打法叠加(route 平滑弧线 +
/// 落点 + 球杆 + 旗杆)。备战和实战共用 —— 给它一个 `CoursePrepHole` 即可。
/// 实战时可传 `selectedClub` + 该杆距离:切球杆/换策略时落点标记与球杆标签**实时联动**。
/// 不传则回退到 prep 的推荐落点 / 推荐球杆(备战屏即如此)。
public struct HoleImageMapView: View {
    public let hole: CoursePrepHole
    /// 实战:当前选中的球杆(已是中文名)。传入则地图标签随之变。
    public let selectedClub: String?
    /// 实战:当前选中球杆的典型距离(米)。传入则落点标记移到该距离处。
    public let selectedClubMetres: Double?
    /// 服务端真实地形底图 URL(`…/holes/{hole}/topo.png`)。有则底图用它,否则/加载失败回退到
    /// payload 里的 flat 渲染图(`hole.map.image`);加载中会明确标示,不会把 fallback 冒充完成态。
    /// 两者共用同一投影,叠加层像素级对齐。
    public let topoURL: URL?
    /// Prep/review use a bounded map card. Live play places the same map directly into its hero, so
    /// the shared map must not add a second rounded card boundary around the instrument backdrop.
    public let showsCardChrome: Bool
    /// Live map-layer controls. Prep/review callers retain the full factual rendering by default.
    public let showsRecommendedRoute: Bool
    public let showsHazards: Bool
    /// Pre-round only: place static tee-based F/M/B and measured obstacle-edge ranges on the map.
    /// Live play supplies current-GPS ranges in `CurrentHoleView`, so its caller leaves this false
    /// and never gets a duplicate or a tee distance disguised as a live distance.
    public let showsPrepFactOverlays: Bool

    public init(hole: CoursePrepHole, selectedClub: String? = nil, selectedClubMetres: Double? = nil,
                topoURL: URL? = nil, showsCardChrome: Bool = true,
                showsRecommendedRoute: Bool = true, showsHazards: Bool = true,
                showsPrepFactOverlays: Bool = false) {
        self.hole = hole
        self.selectedClub = selectedClub
        self.selectedClubMetres = selectedClubMetres
        self.topoURL = topoURL
        self.showsCardChrome = showsCardChrome
        self.showsRecommendedRoute = showsRecommendedRoute
        self.showsHazards = showsHazards
        self.showsPrepFactOverlays = showsPrepFactOverlays
    }

    public var body: some View {
        #if canImport(UIKit)
        if let overlay = hole.resolvedMapOverlay, overlay.w > 0, overlay.h > 0 {
            let map = ZStack {
                // A partial CourseView package already has factual vectors but no prodgeometry
                // bitmap. Do not issue a guaranteed 404 and pin AsyncImage in its failure state;
                // the URL appears only when the same hole later upgrades to precise geometry.
                TopoHoleBaseImage(topoURL: preciseTopoURL, fallback: decodedImage)
                Canvas { context, size in
                    draw(&context, size: size, overlay: overlay)
                }
                if showsPrepFactOverlays {
                    prepFactOverlays(overlay: overlay)
                }
            }
            .aspectRatio(CGFloat(overlay.w) / CGFloat(overlay.h), contentMode: .fit)
            if showsCardChrome {
                map.mapSurface()
            } else {
                map
            }
        }
        #endif
    }

    public var hasMap: Bool {
        hole.resolvedMapOverlay != nil
    }

    #if canImport(UIKit)
    private var decodedImage: UIImage? {
        guard let uri = hole.map?.image,
              let comma = uri.firstIndex(of: ","),
              let data = Data(base64Encoded: String(uri[uri.index(after: comma)...]))
        else {
            return nil
        }
        return UIImage(data: data)
    }

    private var preciseTopoURL: URL? {
        hole.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame ? topoURL : nil
    }
    #endif

    private func draw(_ context: inout GraphicsContext, size: CGSize, overlay: CoursePrepOverlay) {
        let sx = size.width / CGFloat(overlay.w)
        let sy = size.height / CGFloat(overlay.h)
        let routePoints: [CGPoint] = overlay.route.compactMap { row in
            row.count >= 2 ? CGPoint(x: row[0] * sx, y: row[1] * sy) : nil
        }
        let pin = routePoints.last
        if hole.geometryCoverage.caseInsensitiveCompare("partial") == .orderedSame {
            drawLightweightFacts(
                &context,
                routePoints: routePoints,
                sx: sx,
                sy: sy,
                showsRoute: showsRecommendedRoute,
                showsHazards: showsHazards
            )
        }
        // Recommended play line (tee → green) as a smooth SOLID curve, not a hard polyline.
        if showsRecommendedRoute, routePoints.count >= 2 {
            context.stroke(
                Self.smoothPath(through: routePoints),
                with: .color(.white.opacity(0.95)),
                style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round)
            )
            let tee = routePoints[0]
            context.fill(Path(ellipseIn: CGRect(x: tee.x - 5, y: tee.y - 5, width: 10, height: 10)), with: .color(.white))
        }
        // Landing point + club label: live (selected club's distance) when playing, else the prep's
        // recommended landing. Switching clubs mid-shot moves the marker here.
        if showsRecommendedRoute, let landing = Self.landingOverlayPoint(
            overlay,
            targetMetres: selectedClubMetres ?? hole.landingM
        ) {
            let center = CGPoint(x: landing[0] * sx, y: landing[1] * sy)
            context.fill(Path(ellipseIn: CGRect(x: center.x - 8, y: center.y - 8, width: 16, height: 16)), with: .color(LiveHoleStyle.green))
            context.fill(Path(ellipseIn: CGRect(x: center.x - 3, y: center.y - 3, width: 6, height: 6)), with: .color(.white))
            if let club = clubLabel {
                context.draw(
                    Text(club).font(.caption2.weight(.bold)).foregroundColor(.white),
                    at: Self.clubLabelPoint(landing: center, pin: pin)
                )
            }
        }
        // Pin (green end of the route).
        if showsRecommendedRoute, let pin {
            context.fill(Path(ellipseIn: CGRect(x: pin.x - 5, y: pin.y - 5, width: 10, height: 10)), with: .color(.red))
        }
    }

    /// Preparation is a spatial planning surface, not a second report below the map. These overlays
    /// consume only facts with a shared topo coordinate: the measured green target and at most the
    /// nearest two measured obstacle spans. A partial CourseView package deliberately withholds the
    /// obstacle readouts because that subset is not a completeness guarantee.
    private func prepFactOverlays(overlay: CoursePrepOverlay) -> some View {
        GeometryReader { proxy in
            ZStack {
                PrepMapHoleInfoOverlay(
                    hole: hole.hole,
                    par: hole.par,
                    yards: hole.blueYards,
                    playsLikeDeltaYards: hole.playsLike?.available == true ? hole.playsLike?.deltaYd : nil
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .padding(10)
                .accessibilityIdentifier("prep-hole-header-\(hole.hole)")

                if let anchor = prepGreenAnchor(in: proxy.size, overlay: overlay),
                   let distances = prepGreenYards {
                    PrepMapGreenRangeOverlay(
                        frontYards: distances.front,
                        middleYards: distances.middle,
                        backYards: distances.back,
                        anchor: anchor,
                        viewportSize: proxy.size
                    )
                }

                ForEach(Array(prepHazardAnnotations.prefix(2).enumerated()), id: \.element.id) { index, item in
                    if let front = mapPoint(item.frontPx, in: proxy.size, overlay: overlay),
                       let back = mapPoint(item.backPx, in: proxy.size, overlay: overlay) {
                        PrepMapHazardRangeOverlay(
                            kind: item.kind,
                            label: item.label,
                            toYards: item.toYards,
                            overYards: item.overYards,
                            front: front,
                            back: back,
                            index: index,
                            viewportSize: proxy.size
                        )
                        .accessibilityIdentifier("prep-map-hazard-\(index + 1)")
                    }
                }

            }
            .allowsHitTesting(false)
        }
    }

    private struct PrepHazardAnnotation: Identifiable {
        let id: String
        let kind: String
        let label: String
        let toYards: Int
        let overYards: Int
        let frontPx: [Double]
        let backPx: [Double]
    }

    private var prepHazardAnnotations: [PrepHazardAnnotation] {
        guard hole.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame else { return [] }
        let route = hole.resolvedMapOverlay?.route
        return hole.hazards.details
            .filter {
                ($0.kind == "bunker" || $0.kind == "water")
                    && $0.frontPx.count >= 2
                    && $0.backPx.count >= 2
                    && $0.frontPx.prefix(2).allSatisfy(\.isFinite)
                    && $0.backPx.prefix(2).allSatisfy(\.isFinite)
            }
            .sorted {
                if $0.frontRouteM == $1.frontRouteM { return $0.kind < $1.kind }
                return $0.frontRouteM < $1.frontRouteM
            }
            .enumerated()
            .map { index, detail in
                PrepHazardAnnotation(
                    id: "\(detail.kind)-\(index)",
                    kind: detail.kind,
                    label: CoursePrepHazardNaming.label(kind: detail.kind, detail: detail, route: route),
                    toYards: CoursePrepRoute.yards(fromMetres: detail.frontM),
                    overYards: CoursePrepRoute.yards(fromMetres: detail.backM),
                    frontPx: detail.frontPx,
                    backPx: detail.backPx
                )
            }
    }

    private var prepGreenYards: (front: Int?, middle: Int?, back: Int?)? {
        guard let green = hole.greenDistances, green.available else { return nil }
        let values = (
            front: green.frontM.map { CoursePrepRoute.yards(fromMetres: $0) },
            middle: green.middleM.map { CoursePrepRoute.yards(fromMetres: $0) },
            back: green.backM.map { CoursePrepRoute.yards(fromMetres: $0) }
        )
        return values.front != nil || values.middle != nil || values.back != nil ? values : nil
    }

    private func prepGreenAnchor(in size: CGSize, overlay: CoursePrepOverlay) -> CGPoint? {
        if let green = hole.greenDistances,
           let latitude = green.middleLat,
           let longitude = green.middleLon,
           let projection = hole.holeImageProjection,
           projection.available,
           let refs = projection.refs,
           let px = WatchEventBridge.projectToTopoPx(
                lat: latitude,
                lon: longitude,
                refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
           ), let projected = mapPoint(px, in: size, overlay: overlay) {
            return projected
        }
        guard let routeEnd = overlay.route.last else { return nil }
        return mapPoint(routeEnd, in: size, overlay: overlay)
    }

    private func mapPoint(_ row: [Double], in size: CGSize, overlay: CoursePrepOverlay) -> CGPoint? {
        guard row.count >= 2,
              row[0].isFinite,
              row[1].isFinite,
              overlay.w > 0,
              overlay.h > 0 else { return nil }
        return CGPoint(
            x: CGFloat(row[0]) / CGFloat(overlay.w) * size.width,
            y: CGFloat(row[1]) / CGFloat(overlay.h) * size.height
        )
    }

    /// Coarse but factual CourseView-only map shown during the precise prodgeometry download. The
    /// hazard spans are explicitly approximate near→far extents; they are never presented as exact
    /// polygons, and disappear as soon as the precise topo bitmap becomes authoritative.
    private func drawLightweightFacts(
        _ context: inout GraphicsContext,
        routePoints: [CGPoint],
        sx: CGFloat,
        sy: CGFloat,
        showsRoute: Bool,
        showsHazards: Bool
    ) {
        if showsRoute, routePoints.count >= 2 {
            context.stroke(
                Self.smoothPath(through: routePoints),
                with: .color(Color(red: 0.20, green: 0.49, blue: 0.25).opacity(0.9)),
                style: StrokeStyle(lineWidth: 24, lineCap: .round, lineJoin: .round)
            )
        }

        for detail in hole.hazards.details where showsHazards
            && detail.frontPx.count >= 2
            && detail.backPx.count >= 2 {
            let front = CGPoint(x: detail.frontPx[0] * sx, y: detail.frontPx[1] * sy)
            let back = CGPoint(x: detail.backPx[0] * sx, y: detail.backPx[1] * sy)
            var span = Path()
            span.move(to: front)
            span.addLine(to: back)
            let color = detail.kind == "water"
                ? Color(red: 0.18, green: 0.58, blue: 0.88)
                : Color(red: 0.88, green: 0.76, blue: 0.48)
            context.stroke(
                span,
                with: .color(color.opacity(0.95)),
                style: StrokeStyle(lineWidth: detail.kind == "water" ? 14 : 12, lineCap: .round)
            )
        }

        let greenRows = hole.greenOutline?.available == true
            ? (hole.greenOutline?.pointsPx ?? [])
            : []
        let greenPoints: [CGPoint] = greenRows.compactMap { row in
                guard row.count >= 2, row[0].isFinite, row[1].isFinite else { return nil }
                return CGPoint(x: row[0] * sx, y: row[1] * sy)
            }
        if greenPoints.count >= 3 {
            var green = Path()
            green.move(to: greenPoints[0])
            for point in greenPoints.dropFirst() { green.addLine(to: point) }
            green.closeSubpath()
            context.fill(green, with: .color(Color(red: 0.36, green: 0.72, blue: 0.35).opacity(0.95)))
            context.stroke(green, with: .color(.white.opacity(0.35)), style: StrokeStyle(lineWidth: 1))
        }
    }

    /// 标签:实战传入的当前球杆(已中文)优先,否则 prep 推荐球杆(转中文)。
    private var clubLabel: String? {
        if let selectedClub, !selectedClub.isEmpty {
            return selectedClub
        }
        guard let raw = hole.teeClub ?? hole.steps.first?.club else {
            return nil
        }
        return zhClubName(raw)
    }

    /// Landing point in overlay px: walk the route polyline to where cumulative metres reach the
    /// target (selected club's distance when playing, else the prep's recommended landingM).
    static func landingOverlayPoint(
        _ overlay: CoursePrepOverlay,
        targetMetres targetM: Double?
    ) -> [Double]? {
        guard let targetM, !overlay.route.isEmpty else {
            return nil
        }
        for row in overlay.route where row.count >= 3 {
            if row[2] >= targetM {
                return row
            }
        }
        return overlay.route.last
    }

    /// A Par-3 recommendation can end on the pin. Keep its club name outside the 60-point live
    /// target reticle; ordinary fairway landings retain the compact label above their marker.
    static func clubLabelPoint(landing: CGPoint, pin: CGPoint?) -> CGPoint {
        guard let pin, hypot(landing.x - pin.x, landing.y - pin.y) <= 54 else {
            return CGPoint(x: landing.x, y: landing.y - 18)
        }
        return CGPoint(x: pin.x, y: pin.y + 44)
    }

    /// Smooth play line through the route centreline points. Quadratic-through-midpoints: each
    /// interior route point is a control point and the curve passes through the midpoints between
    /// consecutive points. Unlike a Catmull-Rom spline this stays INSIDE the control polygon, so it
    /// never overshoots/bulges outside the fairway at a dogleg (the earlier curve's problem) while
    /// still rounding the corners (a hard polyline looked wrong).
    static func smoothPath(through points: [CGPoint]) -> Path {
        var path = Path()
        guard points.count >= 2 else { return path }
        path.move(to: points[0])
        if points.count == 2 {
            path.addLine(to: points[1])
            return path
        }
        for index in 1 ..< points.count - 1 {
            let midpoint = CGPoint(
                x: (points[index].x + points[index + 1].x) / 2,
                y: (points[index].y + points[index + 1].y) / 2
            )
            path.addQuadCurve(to: midpoint, control: points[index])
        }
        path.addLine(to: points[points.count - 1])
        return path
    }
}

private struct PrepMapHoleInfoOverlay: View {
    let hole: Int
    let par: Int
    let yards: Int
    let playsLikeDeltaYards: Int?

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text("第 \(hole) 洞 · Par \(par)")
                .font(.caption.weight(.heavy))
            Text("蓝T \(yards) 码")
                .font(.caption2.weight(.semibold).monospacedDigit())
                .foregroundStyle(.white.opacity(0.76))
            if let delta = playsLikeDeltaYards, delta != 0 {
                Text("坡度 \(delta > 0 ? "+" : "")\(delta) 码")
                    .font(.caption2.weight(.semibold).monospacedDigit())
                    .foregroundStyle(.white.opacity(0.76))
            }
        }
        .foregroundStyle(.white)
        .padding(.horizontal, 9)
        .padding(.vertical, 7)
        .background(Color.black.opacity(0.7), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(Color.white.opacity(0.18)))
        .shadow(color: .black.opacity(0.28), radius: 4, y: 2)
    }
}

/// Static tee-based green range in preparation. The connector makes clear that the compact F/M/B
/// instrument describes this green, while its dark backing stays legible on every topo palette.
private struct PrepMapGreenRangeOverlay: View {
    let frontYards: Int?
    let middleYards: Int?
    let backYards: Int?
    let anchor: CGPoint
    let viewportSize: CGSize

    private var center: CGPoint {
        let width: CGFloat = 78
        let preferRight = anchor.x < viewportSize.width * 0.58
        let desiredX = anchor.x + (preferRight ? 58 : -58)
        return CGPoint(
            x: min(max(desiredX, width / 2 + 5), viewportSize.width - width / 2 - 5),
            y: min(max(anchor.y, 58), viewportSize.height - 58)
        )
    }

    var body: some View {
        ZStack {
            Path { path in
                path.move(to: anchor)
                path.addLine(to: center)
            }
            .stroke(Color.white.opacity(0.72), style: StrokeStyle(lineWidth: 1.2, lineCap: .round))

            VStack(alignment: .leading, spacing: 0) {
                Text("到果岭")
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(.white.opacity(0.68))
                row("后", backYards, color: Color(red: 0.74, green: 0.77, blue: 0.82), large: false)
                row("中", middleYards, color: .white, large: true)
                row("前", frontYards, color: Color(red: 0.35, green: 0.72, blue: 1.0), large: false)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .frame(width: 78, alignment: .leading)
            .background(Color.black.opacity(0.72), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 9).stroke(Color.white.opacity(0.18)))
            .position(center)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("prep-map-green-range")
    }

    private func row(_ label: String, _ value: Int?, color: Color, large: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Text(label)
                .font(.system(size: large ? 9 : 8, weight: .semibold))
                .foregroundStyle(.white.opacity(0.56))
            Text(value.map(String.init) ?? "—")
                .font(.system(size: large ? 17 : 11, weight: .heavy, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(color)
        }
    }
}

/// Preparation obstacle facts use the exact same visual language as live play: yellow is sand,
/// blue is water, and `到 / 过` are attached to the measured near/far boundary pixels.
private struct PrepMapHazardRangeOverlay: View {
    let kind: String
    let label: String
    let toYards: Int
    let overYards: Int
    let front: CGPoint
    let back: CGPoint
    let index: Int
    let viewportSize: CGSize

    private var tint: Color {
        kind == "water"
            ? Color(red: 0.18, green: 0.58, blue: 0.94)
            : Color(red: 0.95, green: 0.77, blue: 0.28)
    }

    private var anchor: CGPoint {
        CGPoint(x: (front.x + back.x) / 2, y: (front.y + back.y) / 2)
    }

    private var center: CGPoint {
        let width: CGFloat = 104
        let preferRight = anchor.x < viewportSize.width * 0.52
        let desiredX = anchor.x + (preferRight ? 65 : -65)
        let stagger: CGFloat = index == 0 ? -14 : 18
        return CGPoint(
            x: min(max(desiredX, width / 2 + 5), viewportSize.width - width / 2 - 5),
            y: min(max(anchor.y + stagger, 38), viewportSize.height - 34)
        )
    }

    var body: some View {
        ZStack {
            Path { path in
                path.move(to: anchor)
                path.addLine(to: center)
            }
            .stroke(tint.opacity(0.9), style: StrokeStyle(lineWidth: 1.2, lineCap: .round))
            marker(front)
            marker(back)
            VStack(alignment: .leading, spacing: 0) {
                Text(label)
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(.white.opacity(0.74))
                    .lineLimit(1)
                Text("到 \(toYards) · 过 \(overYards)")
                    .font(.system(size: 10, weight: .heavy))
                    .monospacedDigit()
                    .foregroundStyle(.white)
                    .lineLimit(1)
            }
            .padding(.horizontal, 7)
            .padding(.vertical, 4)
            .frame(width: 104, alignment: .leading)
            .background(Color.black.opacity(0.74), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(tint.opacity(0.9)))
            .position(center)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(label)，到 \(toYards) 码，过 \(overYards) 码")
    }

    private func marker(_ point: CGPoint) -> some View {
        Circle()
            .fill(tint)
            .frame(width: 8, height: 8)
            .overlay(Circle().stroke(Color.black.opacity(0.75), lineWidth: 1))
            .position(point)
    }
}
