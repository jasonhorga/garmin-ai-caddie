import SwiftUI

/// Controls that float on the full-screen live hole map (IMPLEMENTATION_PLAN B1, `live-play.html`).
///
/// The map owns the screen; everything here is a small glass control on its edges:
/// top-left back + hole facts, top-right front / middle / back ladder, a left column of on-demand
/// controls (障碍 / 打法 / 回到), 记分 bottom-left and the single white 记一杆 bottom-right.
enum LivePlayChromeStyle {
    static let captionShadow = Color.black.opacity(0.7)
    static let flagRed = Color(red: 1, green: 0.54, blue: 0.5)
}

/// Frosted circle used by every secondary map control.
struct LivePlayGlassCircle<Label: View>: View {
    let diameter: CGFloat
    var pressed = false
    @ViewBuilder let label: () -> Label

    var body: some View {
        label()
            .foregroundStyle(pressed ? Color.black : Color.white)
            .frame(width: diameter, height: diameter)
            .background {
                if pressed {
                    Circle().fill(Color.white.opacity(0.94))
                } else {
                    Circle().fill(.ultraThinMaterial).environment(\.colorScheme, .dark)
                }
            }
            .overlay(Circle().stroke(Color.white.opacity(pressed ? 0 : 0.18), lineWidth: 0.5))
            .shadow(color: .black.opacity(0.3), radius: 6, y: 2)
    }
}

/// A caption under a map control ("障碍", "记分", …); legible on any fairway colour.
struct LivePlayControlCaption: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(.white)
            .shadow(color: LivePlayChromeStyle.captionShadow, radius: 2, y: 1)
    }
}

/// Top-left: back, then the hole number, par and yards, and the round line underneath.
struct LivePlayTopInfo: View {
    let holeNumber: Int
    let par: Int
    let yards: Int?
    let roundLine: String
    let onBack: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Button(action: onBack) {
                LivePlayGlassCircle(diameter: 40) {
                    Image(systemName: "chevron.backward")
                        .font(.system(size: 16, weight: .semibold))
                }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("计分卡")
            .accessibilityHint("查看每洞成绩，也可以结束本场或回到首页")
            .accessibilityIdentifier("live-back-to-scorecard")

            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text("\(holeNumber)")
                        .font(.system(size: 30, weight: .semibold, design: .rounded))
                        .monospacedDigit()
                        .accessibilityLabel("第 \(holeNumber) 洞")
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier("live-hole-title")
                    Text(subtitle)
                        .font(.system(size: 14, weight: .medium))
                        .monospacedDigit()
                }
                Text(roundLine)
                    .font(.system(size: 12.5, weight: .medium))
                    .monospacedDigit()
                    .foregroundStyle(.white.opacity(0.78))
                    .accessibilityIdentifier("live-round-line")
            }
            .foregroundStyle(.white)
            .shadow(color: LivePlayChromeStyle.captionShadow, radius: 3, y: 1)
        }
    }

    private var subtitle: String {
        var parts = ["Par \(par)"]
        if let yards { parts.append("\(yards) 码") }
        return parts.joined(separator: " · ")
    }
}

/// Top-right: the most-read numbers — back / middle / front of the green, plus the flag when one
/// has been placed. Without a live fix the ladder is the Tee's static reference and says so.
struct LivePlayGreenLadder: View {
    let frontYards: Int?
    let middleYards: Int?
    let backYards: Int?
    let flagYards: Int?
    let isLive: Bool

    var body: some View {
        VStack(spacing: 2) {
            edgeRow("后", backYards, identifier: "live-green-back")
            Text(GeoDistance.greenRangeText(middleYards))
                .font(.system(size: 44, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.6)
                .accessibilityIdentifier("live-green-middle")
            edgeRow("前", frontYards, identifier: "live-green-front")
            if let flagYards, !GeoDistance.isBeyondUsefulGreenRange(flagYards) {
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    Text("旗").font(.system(size: 11, weight: .semibold))
                    Text("\(flagYards)").font(.system(size: 15, weight: .bold, design: .rounded)).monospacedDigit()
                }
                .foregroundStyle(LivePlayChromeStyle.flagRed)
                .padding(.top, 2)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("到旗 \(flagYards) 码")
                .accessibilityIdentifier("live-green-flag")
            }
            Text(isLive ? "到果岭 · 码" : "发球台 · 码")
                .font(.system(size: 10.5, weight: .medium))
                .foregroundStyle(.white.opacity(0.62))
                .padding(.top, 2)
        }
        .foregroundStyle(.white)
        .frame(width: 92)
        .padding(.top, 10)
        .padding(.bottom, 12)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .environment(\.colorScheme, .dark)
        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).stroke(Color.white.opacity(0.18), lineWidth: 0.5))
        .accessibilityElement(children: .contain)
        .accessibilityHint(isLive ? "距离根据当前位置实时计算。" : "这是发球台到果岭的静态参考，不代表当前位置。")
        .accessibilityIdentifier("live-green-ladder")
    }

    private func edgeRow(_ label: String, _ value: Int?, identifier: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Text(label).font(.system(size: 11, weight: .medium))
            Text(GeoDistance.greenRangeText(value))
                .font(.system(size: 14, weight: .medium, design: .rounded))
                .monospacedDigit()
                .accessibilityIdentifier(identifier)
        }
        .foregroundStyle(.white.opacity(0.7))
    }
}

/// Left column of on-demand controls. 回到 appears only after the map was zoomed or panned.
struct LivePlaySideControls: View {
    let hasHazards: Bool
    let hazardShown: Bool
    let planPosition: (index: Int, count: Int)?
    let showsRecenter: Bool
    let onToggleHazards: () -> Void
    let onNextPlan: () -> Void
    let onRecenter: () -> Void

    var body: some View {
        VStack(spacing: 18) {
            if hasHazards {
                control(caption: "障碍") {
                    Button(action: onToggleHazards) {
                        LivePlayGlassCircle(diameter: 46, pressed: hazardShown) {
                            Image(systemName: "square.3.layers.3d")
                                .font(.system(size: 19, weight: .medium))
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(hazardShown ? "隐藏障碍" : "显示障碍")
                    .accessibilityAddTraits(hazardShown ? .isSelected : [])
                    .accessibilityIdentifier("live-hazard-toggle")
                }
            }
            if let planPosition, planPosition.count > 1 {
                control(caption: "打法") {
                    Button(action: onNextPlan) {
                        LivePlayGlassCircle(diameter: 46) {
                            Text("\(planPosition.index + 1)/\(planPosition.count)")
                                .font(.system(size: 14, weight: .bold, design: .rounded))
                                .monospacedDigit()
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("切换打法，当前第 \(planPosition.index + 1) 个，共 \(planPosition.count) 个")
                    .accessibilityIdentifier("live-plan-next")
                }
            }
            if showsRecenter {
                control(caption: "回到") {
                    Button(action: onRecenter) {
                        LivePlayGlassCircle(diameter: 46) {
                            Image(systemName: "location.north.fill")
                                .font(.system(size: 17, weight: .semibold))
                                .rotationEffect(.degrees(45))
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("回到整洞视图")
                    .accessibilityIdentifier("live-hero-map-reset-zoom")
                }
            }
        }
    }

    private func control<Content: View>(caption: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(spacing: 4) {
            content()
            LivePlayControlCaption(text: caption)
        }
    }
}

/// Bottom-centre strip for the one selected obstacle: its name, "2 / 4" and ‹ ›.
struct LivePlayHazardBar: View {
    let row: LiveHazardDisplayItem
    let index: Int
    let count: Int
    let onPrevious: () -> Void
    let onNext: () -> Void

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(row.isWater ? Color(red: 0.36, green: 0.69, blue: 1) : Color(red: 0.92, green: 0.78, blue: 0.4))
                .frame(width: 10, height: 10)
            VStack(alignment: .leading, spacing: 1) {
                Text(row.label)
                    .font(.system(size: 12.5, weight: .bold))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Text("\(index + 1) / \(count)")
                    .font(.system(size: 10.5, weight: .medium))
                    .monospacedDigit()
                    .foregroundStyle(.white.opacity(0.62))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            navigation("chevron.backward", label: "上一个障碍", identifier: "hazard-previous", disabled: index == 0, action: onPrevious)
            navigation("chevron.forward", label: "下一个障碍", identifier: "hazard-next", disabled: index >= count - 1, action: onNext)
        }
        .foregroundStyle(.white)
        .padding(.leading, 12)
        .padding(.trailing, 5)
        .frame(height: 50)
        .background(.ultraThinMaterial, in: Capsule())
        .environment(\.colorScheme, .dark)
        .overlay(Capsule().stroke(Color.white.opacity(0.18), lineWidth: 0.5))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("selected-hazard-\(index + 1)")
    }

    private func navigation(
        _ systemName: String,
        label: String,
        identifier: String,
        disabled: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 14, weight: .semibold))
                .frame(width: 32, height: 32)
                .background(Color.white.opacity(0.1), in: Circle())
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .opacity(disabled ? 0.3 : 1)
        .accessibilityLabel(label)
        .accessibilityIdentifier(identifier)
    }
}

/// Bottom-left: finish this hole (once per hole, away from 记一杆 to avoid mis-taps).
struct LivePlayScoreButton: View {
    let action: () -> Void

    var body: some View {
        VStack(spacing: 4) {
            Button(action: action) {
                LivePlayGlassCircle(diameter: 60) {
                    Image(systemName: "flag")
                        .font(.system(size: 22, weight: .medium))
                }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("完成本洞")
            .accessibilityHint("记分")
            .accessibilityIdentifier("live-score-hole")
            LivePlayControlCaption(text: "记分")
        }
    }
}

/// Bottom-right: the only solid white control — the most frequent action.
struct LivePlayRecordShotButton: View {
    let enabled: Bool
    let recordedShotCount: Int
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 0) {
                Text("＋").font(.system(size: 26, weight: .light))
                Text("记一杆").font(.system(size: 12, weight: .bold))
            }
            .foregroundStyle(Color(red: 0.04, green: 0.06, blue: 0.05))
            .frame(width: 76, height: 76)
            .background(Color(red: 0.96, green: 0.96, blue: 0.95), in: Circle())
            .shadow(color: .black.opacity(0.45), radius: 9, y: 6)
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .opacity(enabled ? 1 : 0.5)
        .accessibilityLabel("记一杆")
        .accessibilityValue(recordedShotCount > 0 ? "已记第 \(recordedShotCount) 杆" : (enabled ? "" : "等待 GPS"))
        .accessibilityHint(enabled ? "在当前位置记录一杆" : "等待 GPS 定位")
        .accessibilityIdentifier("live-record-shot")
    }
}

/// The caddie route on the live map (`live-play.html`): a 3 pt flight arc per leg, a landing dot and
/// a 13 pt "杆名 码数" label bound to every landing, including the final leg onto the green.
///
/// Legs come from `HoleImageMapView.plannedLegs()` in topo pixels and are transformed here with the
/// same pan/zoom as the bitmap, so they follow the map while stroke widths and type stay at screen
/// size. Labels sit beside their landing, never on the route, the flag or another label.
enum LivePlannedRouteRenderer {
    static let labelFontSize: CGFloat = 13
    static let labelPadding = CGSize(width: 7, height: 4)
    static let yardsPerMetre = 1.0936133

    struct PlacedLabel: Equatable {
        let text: String
        let rect: CGRect
    }

    /// "一号木 224": the club and that leg's planned carry (the caddie's number); the drawn leg
    /// length is the fallback for an older plan without a carry.
    static func labelText(for leg: MapPlannedLeg, pixelsPerMetre: Double) -> String {
        let club = zhClubDisplayName(zhClubName(leg.shot.clubName))
        guard let yards = legYards(leg, pixelsPerMetre: pixelsPerMetre) else { return club }
        return "\(club) \(yards)"
    }

    static func legYards(_ leg: MapPlannedLeg, pixelsPerMetre: Double) -> Int? {
        if let carry = leg.shot.carryM, carry.isFinite, carry > 0 {
            return Int((carry * yardsPerMetre).rounded())
        }
        guard pixelsPerMetre.isFinite, pixelsPerMetre > 0 else { return nil }
        let pixels = Double(hypot(leg.destination.x - leg.origin.x, leg.destination.y - leg.origin.y))
        guard pixels > 1 else { return nil }
        return Int((pixels / pixelsPerMetre * yardsPerMetre).rounded())
    }

    /// The route and tee arc transformed into the viewport (pan/zoom applied).
    struct ScreenGeometry {
        let legs: [(leg: MapPlannedLeg, origin: CGPoint, destination: CGPoint)]
        let arcs: [MapFlightArc]
        let teeArc: MapFlightArc?
        let teeArcYards: Int?
    }

    static func screenGeometry(
        size: CGSize,
        legs: [MapPlannedLeg],
        teeArc: MapFlightArc?,
        teeArcYards: Int?,
        overlay: CoursePrepOverlay,
        scale: CGFloat,
        offset: CGSize,
        topInset: CGFloat,
        bottomInset: CGFloat = 0
    ) -> ScreenGeometry {
        func screen(_ point: CGPoint) -> CGPoint? {
            transformedPoint(
                point,
                size: size,
                overlay: overlay,
                scale: scale,
                offset: offset,
                topInset: topInset,
                bottomInset: bottomInset
            )
        }
        let screenLegs = legs.compactMap { leg -> (leg: MapPlannedLeg, origin: CGPoint, destination: CGPoint)? in
            guard let origin = screen(leg.origin), let destination = screen(leg.destination) else { return nil }
            return (leg, origin, destination)
        }
        // Pan/zoom is affine, so transforming the three control points transforms the curve.
        let screenTeeArc: MapFlightArc? = {
            guard let teeArc, let teeArcYards, teeArcYards > 0,
                  let start = screen(teeArc.start),
                  let control = screen(teeArc.control),
                  let end = screen(teeArc.end) else { return nil }
            return MapFlightArc(start: start, control: control, end: end)
        }()
        return ScreenGeometry(
            legs: screenLegs,
            arcs: screenLegs.map { HoleImageMapView.flightArc(from: $0.origin, to: $0.destination) },
            teeArc: screenTeeArc,
            teeArcYards: screenTeeArc == nil ? nil : teeArcYards
        )
    }

    /// A topo pixel in the viewport: the aspect-fit projection, then the hero's pan/zoom.
    static func transformedPoint(
        _ point: CGPoint,
        size: CGSize,
        overlay: CoursePrepOverlay,
        scale: CGFloat,
        offset: CGSize,
        topInset: CGFloat,
        bottomInset: CGFloat = 0
    ) -> CGPoint? {
        guard let base = LivePlayMapOverlayLayout.project(
            overlayPoint: [Double(point.x), Double(point.y)],
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            into: size,
            topInset: topInset,
            bottomInset: bottomInset
        ) else { return nil }
        let x: CGFloat = size.width / 2 + (base.x - size.width / 2) * scale + offset.width
        let y: CGFloat = size.height / 2 + (base.y - size.height / 2) * scale + offset.height
        return CGPoint(x: x, y: y)
    }

    /// Label strings in layout order: one per leg, then the tee-distance "N码".
    static func labelTexts(_ geometry: ScreenGeometry, pixelsPerMetre: Double) -> [String] {
        var texts = geometry.legs.map { labelText(for: $0.leg, pixelsPerMetre: pixelsPerMetre) }
        if let yards = geometry.teeArcYards { texts.append("\(yards)码") }
        return texts
    }

    /// One collision layout for every label on the map: each leg's "杆名 码数" and the
    /// tee-distance "N码" (`labelSizes` in `labelTexts` order). Labels never overlap each other;
    /// they also avoid the route, the tee arc, the landing dots and the flag (drawn in the bitmap,
    /// so it scales with the map).
    static func labelRects(
        _ geometry: ScreenGeometry,
        labelSizes: [CGSize],
        flagScale: CGFloat,
        viewportSize: CGSize
    ) -> [CGRect?] {
        layout(geometry, labelSizes: labelSizes, flagScale: flagScale, viewportSize: viewportSize).route
    }

    /// The shared layout including a selected obstacle: its 前 / 后 labels are placed first (they
    /// must stay outside its outline, next to their edge points), then the route and tee labels
    /// around them. Returned rects are nil for a label that is omitted (anchor off screen).
    static func layout(
        _ geometry: ScreenGeometry,
        labelSizes: [CGSize],
        flagScale: CGFloat,
        viewportSize: CGSize,
        hazard: LiveHazardOverlayRenderer.ScreenGeometry? = nil,
        hazardLabelSizes: [CGSize] = [],
        target: LiveTargetRenderer.ScreenTarget? = nil
    ) -> (route: [CGRect?], hazard: [CGRect?]) {
        var lineSamples: [CGPoint] = geometry.arcs.flatMap { Self.samples(along: $0) }
        if let teeArc = geometry.teeArc { lineSamples += Self.samples(along: teeArc) }
        var reserved: [CGRect] = []
        if let target {
            // The Touch Target readout sits at a fixed spot beside its ring (the prototype's
            // layout); every other label is placed around it and its dashed legs.
            reserved = target.labelRects
            for leg in target.legs {
                lineSamples += Self.samples(along: MapFlightArc(
                    start: leg.start,
                    control: CGPoint(x: (leg.start.x + leg.end.x) / 2, y: (leg.start.y + leg.end.y) / 2),
                    end: leg.end
                ))
            }
        }
        var obstacles: [CGRect] = geometry.legs.map {
            CGRect(x: $0.destination.x - 8, y: $0.destination.y - 8, width: 16, height: 16)
        }
        if let pinLeg = geometry.legs.last(where: { $0.leg.endsAtPin }) {
            obstacles.append(flagRect(foot: pinLeg.destination, scale: flagScale))
        }
        if let target {
            obstacles.append(CGRect(x: target.point.x - 15, y: target.point.y - 15, width: 30, height: 30))
        }
        if let hazard {
            lineSamples += outlineSamples(hazard.outline)
            obstacles += hazard.edges.map {
                CGRect(x: $0.point.x - 4, y: $0.point.y - 4, width: 8, height: 8)
            }
        }
        // A label belongs to its anchor: when the landing, edge point or the whole tee arc is
        // panned off screen its label is omitted rather than clamped to an edge far from it.
        let screenBounds = CGRect(origin: .zero, size: viewportSize)
        var requests: [LabelRequest] = []
        var slots: [(isHazard: Bool, index: Int)] = []
        if let hazard {
            for (index, edge) in hazard.edges.enumerated() where index < hazardLabelSizes.count {
                guard screenBounds.contains(edge.point) else { continue }
                let labelSize = hazardLabelSizes[index]
                requests.append(LabelRequest(
                    size: labelSize,
                    candidates: LiveHazardOverlayRenderer.labelCandidates(
                        for: edge,
                        outline: hazard.outline,
                        labelSize: labelSize,
                        viewportSize: viewportSize
                    )
                ))
                slots.append((true, index))
            }
        }
        for (index, item) in geometry.legs.enumerated() where index < labelSizes.count {
            guard screenBounds.contains(item.destination) else { continue }
            let labelSize = labelSizes[index]
            let candidates = item.leg.endsAtPin
                ? pinCandidates(foot: item.destination, flagScale: flagScale, labelSize: labelSize)
                : landingCandidates(landing: item.destination, from: item.origin, labelSize: labelSize)
            requests.append(LabelRequest(size: labelSize, candidates: candidates))
            slots.append((false, index))
        }
        if let teeArc = geometry.teeArc, labelSizes.count > geometry.legs.count {
            let labelSize = labelSizes[geometry.legs.count]
            let candidates = teeArcCandidates(arc: teeArc, labelSize: labelSize)
                .filter { screenBounds.contains($0) }
            if !candidates.isEmpty {
                requests.append(LabelRequest(size: labelSize, candidates: candidates))
                slots.append((false, geometry.legs.count))
            }
        }
        let viewport = screenBounds.insetBy(dx: 4, dy: 4)
        let placed = layoutLabels(
            requests,
            viewport: viewport,
            obstacles: obstacles,
            samples: lineSamples,
            reserved: reserved
        )
        var route = [CGRect?](repeating: nil, count: labelSizes.count)
        var hazardRects = [CGRect?](repeating: nil, count: hazard?.edges.count ?? 0)
        for (rect, slot) in zip(placed, slots) {
            if slot.isHazard {
                hazardRects[slot.index] = rect
            } else {
                route[slot.index] = rect
            }
        }
        return (route, hazardRects)
    }

    /// Points every ~6 pt along a closed outline, so labels keep off the obstacle's red edge.
    static func outlineSamples(_ outline: [CGPoint]) -> [CGPoint] {
        guard outline.count >= 2 else { return outline }
        var points: [CGPoint] = []
        for index in outline.indices {
            let a = outline[index]
            let b = outline[(index + 1) % outline.count]
            let length: CGFloat = hypot(b.x - a.x, b.y - a.y)
            let steps = max(1, Int(length / 6))
            for step in 0..<steps {
                let t = CGFloat(step) / CGFloat(steps)
                let x: CGFloat = a.x + (b.x - a.x) * t
                let y: CGFloat = a.y + (b.y - a.y) * t
                points.append(CGPoint(x: x, y: y))
            }
        }
        return points
    }

    static func draw(
        _ context: inout GraphicsContext,
        size: CGSize,
        legs: [MapPlannedLeg],
        teeArc: MapFlightArc?,
        teeArcYards: Int?,
        overlay: CoursePrepOverlay,
        scale: CGFloat,
        offset: CGSize,
        topInset: CGFloat,
        bottomInset: CGFloat = 0,
        hazard selectedHazard: (hole: CoursePrepHole, row: LiveHazardDisplayItem)? = nil,
        target: LiveTargetGeometry? = nil
    ) {
        let geometry = screenGeometry(
            size: size,
            legs: legs,
            teeArc: teeArc,
            teeArcYards: teeArcYards,
            overlay: overlay,
            scale: scale,
            offset: offset,
            topInset: topInset,
            bottomInset: bottomInset
        )
        let hazardGeometry = selectedHazard.flatMap {
            LiveHazardOverlayRenderer.screenGeometry(
                size: size,
                hole: $0.hole,
                row: $0.row,
                scale: scale,
                offset: offset,
                topInset: topInset
            )
        }
        if let screenTeeArc = geometry.teeArc {
            let path = HoleImageMapView.path(for: screenTeeArc)
            context.stroke(path, with: .color(.black.opacity(0.62)),
                           style: StrokeStyle(lineWidth: 5, lineCap: .round, dash: [9, 6]))
            context.stroke(path, with: .color(Color(red: 1.0, green: 0.78, blue: 0.18)),
                           style: StrokeStyle(lineWidth: 2.5, lineCap: .round, dash: [9, 6]))
        }
        for (item, arc) in zip(geometry.legs, geometry.arcs) {
            guard hypot(item.destination.x - item.origin.x, item.destination.y - item.origin.y) > 1 else { continue }
            let path = HoleImageMapView.path(for: arc)
            context.stroke(path, with: .color(.black.opacity(0.58)),
                           style: StrokeStyle(lineWidth: 6, lineCap: .round, lineJoin: .round))
            context.stroke(path, with: .color(.white.opacity(item.leg.isSelected ? 0.96 : 0.55)),
                           style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round))
        }
        for item in geometry.legs where !item.leg.endsAtPin {
            let point = item.destination
            context.fill(Path(ellipseIn: CGRect(x: point.x - 7, y: point.y - 7, width: 14, height: 14)),
                         with: .color(item.leg.isSelected ? LiveHoleStyle.green : .white.opacity(0.64)))
            context.fill(Path(ellipseIn: CGRect(x: point.x - 2.5, y: point.y - 2.5, width: 5, height: 5)),
                         with: .color(.white))
        }

        let strings = labelTexts(geometry, pixelsPerMetre: overlay.ppm)
        var resolvedTexts: [GraphicsContext.ResolvedText] = []
        var sizes: [CGSize] = []
        for (index, string) in strings.enumerated() {
            let isTeeLabel = index >= geometry.legs.count
            let text = Text(string)
                .font(.system(size: isTeeLabel ? 11 : labelFontSize, weight: .heavy, design: .rounded))
                .foregroundColor(.white)
            let resolved = context.resolve(text)
            let raw = resolved.measure(in: CGSize(width: 240, height: 60))
            let width: CGFloat = ceil(raw.width) + labelPadding.width * 2
            let height: CGFloat = ceil(raw.height) + labelPadding.height * 2
            resolvedTexts.append(resolved)
            sizes.append(CGSize(width: width, height: height))
        }
        let hazardSizes: [CGSize] = hazardGeometry?.edges.map {
            LiveHazardOverlayRenderer.labelSize(for: $0.text, in: context)
        } ?? []
        var screenTarget: LiveTargetRenderer.ScreenTarget?
        if let target {
            screenTarget = LiveTargetRenderer.screenTarget(
                target,
                in: context,
                viewportSize: size,
                transform: { point in
                    transformedPoint(
                        point,
                        size: size,
                        overlay: overlay,
                        scale: scale,
                        offset: offset,
                        topInset: topInset
                    )
                }
            )
        }
        let placed = layout(
            geometry,
            labelSizes: sizes,
            flagScale: scale,
            viewportSize: size,
            hazard: hazardGeometry,
            hazardLabelSizes: hazardSizes,
            target: screenTarget
        )
        for (index, rect) in placed.route.enumerated() where index < resolvedTexts.count {
            guard let rect else { continue }
            let dimmed = index < geometry.legs.count && !geometry.legs[index].leg.isSelected
            context.fill(Path(roundedRect: rect, cornerRadius: rect.height / 2),
                         with: .color(.black.opacity(dimmed ? 0.5 : 0.74)))
            context.draw(resolvedTexts[index], at: CGPoint(x: rect.midX, y: rect.midY))
        }
        if let screenTarget {
            LiveTargetRenderer.draw(&context, screenTarget)
        }
        // The obstacle is drawn last with the label rectangles from the same layout.
        if let selectedHazard {
            LiveHazardOverlayRenderer.draw(
                &context,
                size: size,
                hole: selectedHazard.hole,
                row: selectedHazard.row,
                scale: scale,
                offset: offset,
                topInset: topInset,
                labelRects: placed.hazard
            )
        }
    }

    /// A label to place: its size and candidate centres in preference order.
    struct LabelRequest {
        let size: CGSize
        let candidates: [CGPoint]
    }

    /// Greedy placement in request order. Overlapping an already placed label is never accepted
    /// while any candidate (as given, or clamped into the viewport) avoids it; after that the
    /// viewport, the obstacles and the sampled lines are avoided in that order.
    static func layoutLabels(
        _ requests: [LabelRequest],
        viewport: CGRect,
        obstacles: [CGRect],
        samples: [CGPoint],
        reserved: [CGRect] = []
    ) -> [CGRect] {
        // `reserved` are labels that are already fixed (the Touch Target readout); they count as
        // placed labels but are not returned.
        var placed: [CGRect] = reserved
        for request in requests {
            let halfW: CGFloat = request.size.width / 2
            let halfH: CGFloat = request.size.height / 2
            let raw: [CGRect] = request.candidates.map {
                CGRect(x: $0.x - halfW, y: $0.y - halfH, width: request.size.width, height: request.size.height)
            }
            let options: [CGRect] = raw + raw.map { clampedRect($0, into: viewport) }
            func score(_ rect: CGRect) -> Int {
                let padded = rect.insetBy(dx: -2, dy: -2)
                let labelHits: Int = placed.filter { $0.intersects(padded) }.count
                let outside: Int = viewport.contains(rect) ? 0 : 1
                let obstacleHits: Int = obstacles.filter { $0.intersects(rect) }.count
                let lineHits: Int = samples.filter { padded.contains($0) }.count
                return labelHits * 100_000 + outside * 10_000 + obstacleHits * 100 + lineHits
            }
            var best = options[0]
            var bestScore = score(best)
            for option in options.dropFirst() where bestScore > 0 {
                let value = score(option)
                if value < bestScore {
                    best = option
                    bestScore = value
                }
            }
            placed.append(best)
        }
        return Array(placed.dropFirst(reserved.count))
    }

    /// Beside the landing across the flight direction (either side), then above/below, then the
    /// diagonals, each at growing distance.
    static func landingCandidates(landing: CGPoint, from origin: CGPoint, labelSize: CGSize) -> [CGPoint] {
        var dx: CGFloat = landing.x - origin.x
        var dy: CGFloat = landing.y - origin.y
        let length: CGFloat = hypot(dx, dy)
        if length > 1 { dx /= length; dy /= length } else { dx = 0; dy = -1 }
        let normal = CGPoint(x: -dy, y: dx)
        let halfW: CGFloat = labelSize.width / 2
        let halfH: CGFloat = labelSize.height / 2
        let acrossX: CGFloat = abs(normal.x) * halfW
        let acrossY: CGFloat = abs(normal.y) * halfH
        var centres: [CGPoint] = []
        for gap in [CGFloat(12), 30, 52] {
            let across: CGFloat = acrossX + acrossY + gap
            let offsetX: CGFloat = normal.x * across
            let offsetY: CGFloat = normal.y * across
            let vertical: CGFloat = halfH + gap + 8
            let horizontal: CGFloat = halfW + gap
            centres.append(CGPoint(x: landing.x + offsetX, y: landing.y + offsetY))
            centres.append(CGPoint(x: landing.x - offsetX, y: landing.y - offsetY))
            centres.append(CGPoint(x: landing.x, y: landing.y - vertical))
            centres.append(CGPoint(x: landing.x, y: landing.y + vertical))
            centres.append(CGPoint(x: landing.x + horizontal, y: landing.y - vertical))
            centres.append(CGPoint(x: landing.x - horizontal, y: landing.y - vertical))
            centres.append(CGPoint(x: landing.x + horizontal, y: landing.y + vertical))
            centres.append(CGPoint(x: landing.x - horizontal, y: landing.y + vertical))
        }
        return centres
    }

    /// Left of the pole first (the pennant flies right), then right of the pennant, above, below.
    static func pinCandidates(foot: CGPoint, flagScale: CGFloat, labelSize: CGSize) -> [CGPoint] {
        let halfW: CGFloat = labelSize.width / 2
        let halfH: CGFloat = labelSize.height / 2
        let flagHeight: CGFloat = LiveMapFlagRenderer.poleHeight * flagScale
        let flagWidth: CGFloat = (LiveMapFlagRenderer.pennantWidth + 2) * flagScale
        let flagMidY: CGFloat = foot.y - flagHeight / 2
        var centres: [CGPoint] = []
        for gap in [CGFloat(10), 28, 48] {
            centres.append(CGPoint(x: foot.x - gap - halfW, y: flagMidY))
            centres.append(CGPoint(x: foot.x + flagWidth + gap + halfW, y: flagMidY))
            centres.append(CGPoint(x: foot.x, y: foot.y - flagHeight - gap - halfH))
            centres.append(CGPoint(x: foot.x, y: foot.y + gap + halfH))
        }
        return centres
    }

    /// Along the tee-distance arc, just above (then below) it: the middle first, then towards
    /// either end, so the label leaves the route where the arc crosses it.
    static func teeArcCandidates(arc: MapFlightArc, labelSize: CGSize) -> [CGPoint] {
        let lift: CGFloat = labelSize.height / 2 + 6
        var centres: [CGPoint] = []
        for side in [CGFloat(-1), 1] {
            for t in [CGFloat(0.5), 0.78, 0.22, 0.92, 0.08] {
                let point = quadPoint(arc, t: t)
                centres.append(CGPoint(x: point.x, y: point.y + side * lift))
            }
        }
        return centres
    }

    static func flagRect(foot: CGPoint, scale: CGFloat) -> CGRect {
        let height = LiveMapFlagRenderer.poleHeight * scale
        let width = (LiveMapFlagRenderer.pennantWidth + 2) * scale
        return CGRect(x: foot.x - 3, y: foot.y - height - 2, width: width + 3, height: height + 4)
    }

    static func samples(along arc: MapFlightArc) -> [CGPoint] {
        let length = hypot(arc.end.x - arc.start.x, arc.end.y - arc.start.y)
        let count = max(2, Int(length / 6))
        var points: [CGPoint] = []
        points.reserveCapacity(count + 1)
        for step in 0...count {
            let t = CGFloat(step) / CGFloat(count)
            points.append(quadPoint(arc, t: t))
        }
        return points
    }

    static func quadPoint(_ arc: MapFlightArc, t: CGFloat) -> CGPoint {
        let u: CGFloat = 1 - t
        let a: CGFloat = u * u
        let b: CGFloat = 2 * u * t
        let c: CGFloat = t * t
        let x: CGFloat = a * arc.start.x + b * arc.control.x + c * arc.end.x
        let y: CGFloat = a * arc.start.y + b * arc.control.y + c * arc.end.y
        return CGPoint(x: x, y: y)
    }

    private static func clampedRect(_ rect: CGRect, into bounds: CGRect) -> CGRect {
        var result = rect
        result.origin.x = min(max(result.minX, bounds.minX), max(bounds.minX, bounds.maxX - result.width))
        result.origin.y = min(max(result.minY, bounds.minY), max(bounds.minY, bounds.maxY - result.height))
        return result
    }
}

/// Touch Target on the main live map (`live-play.html`, B1c): tap the map to place it, hold and drag
/// it to move it with the loupe, tap it again to clear it. Points are topo pixels; distances come
/// from the same pixel frame (`LiveMapPixelDistanceLayout`), so they work without GPS.
struct LiveTargetGeometry: Equatable {
    let reference: CGPoint?
    let target: CGPoint
    let pin: CGPoint?
    let toTargetYards: Int?
    let toPinYards: Int?
}

enum LiveTargetRenderer {
    static let yellow = Color(red: 1, green: 0.847, blue: 0.29)
    static let ringRadius: CGFloat = 13
    /// A press within this distance of the ring grabs the target (drag) or clears it (tap).
    static let grabRadius: CGFloat = 36

    struct ScreenTarget {
        let point: CGPoint
        let legs: [(start: CGPoint, end: CGPoint)]
        let yards: GraphicsContext.ResolvedText?
        let remain: GraphicsContext.ResolvedText?
        let labelRects: [CGRect]
    }

    /// Player (or Tee) → target, then target → flag; the second leg only when the flag is known.
    static func legs(reference: CGPoint?, target: CGPoint, pin: CGPoint?) -> [(start: CGPoint, end: CGPoint)] {
        var result: [(start: CGPoint, end: CGPoint)] = []
        if let reference { result.append((reference, target)) }
        if let pin { result.append((target, pin)) }
        return result
    }

    /// The readout sits beside the ring, on the side with more room: the yardage (22 pt) above
    /// the centre line, "再 N 到旗" (12 pt) below it.
    static func labelRects(target: CGPoint, viewportWidth: CGFloat, yardsSize: CGSize?, remainSize: CGSize?) -> [CGRect] {
        let onLeft = target.x > viewportWidth / 2
        func rect(_ size: CGSize, centreY: CGFloat) -> CGRect {
            let x: CGFloat = onLeft ? target.x - 20 - size.width : target.x + 20
            return CGRect(x: x, y: centreY - size.height / 2, width: size.width, height: size.height)
        }
        var rects: [CGRect] = []
        if let yardsSize { rects.append(rect(yardsSize, centreY: target.y - 4 - yardsSize.height / 2 + 6)) }
        if let remainSize { rects.append(rect(remainSize, centreY: target.y + 10)) }
        return rects
    }

    static func screenTarget(
        _ geometry: LiveTargetGeometry,
        in context: GraphicsContext,
        viewportSize: CGSize,
        transform: (CGPoint) -> CGPoint?
    ) -> ScreenTarget? {
        guard let point = transform(geometry.target) else { return nil }
        let reference: CGPoint? = geometry.reference.flatMap { transform($0) }
        let pin: CGPoint? = geometry.pin.flatMap { transform($0) }
        let yards = geometry.toTargetYards.map {
            context.resolve(
                Text("\($0)")
                    .font(.system(size: 22, weight: .bold, design: .rounded))
                    .foregroundColor(yellow)
            )
        }
        let remain = geometry.toPinYards.map {
            context.resolve(
                Text("再 \($0) 到旗")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.white)
            )
        }
        let limit = CGSize(width: 200, height: 40)
        let rects = labelRects(
            target: point,
            viewportWidth: viewportSize.width,
            yardsSize: yards?.measure(in: limit),
            remainSize: remain?.measure(in: limit)
        )
        return ScreenTarget(
            point: point,
            legs: legs(reference: reference, target: point, pin: pin),
            yards: yards,
            remain: remain,
            labelRects: rects
        )
    }

    static func draw(_ context: inout GraphicsContext, _ target: ScreenTarget) {
        for (index, leg) in target.legs.enumerated() {
            var path = Path()
            path.move(to: leg.start)
            path.addLine(to: leg.end)
            context.stroke(path, with: .color(.black.opacity(0.45)),
                           style: StrokeStyle(lineWidth: 4, lineCap: .round, dash: [5, 5]))
            context.stroke(path, with: .color(yellow.opacity(index == 0 ? 1 : 0.7)),
                           style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [5, 5]))
        }
        let p = target.point
        let ring = Path(ellipseIn: CGRect(x: p.x - ringRadius, y: p.y - ringRadius, width: ringRadius * 2, height: ringRadius * 2))
        context.stroke(ring, with: .color(.black.opacity(0.5)), lineWidth: 4.5)
        context.stroke(ring, with: .color(yellow), lineWidth: 2.5)
        context.fill(Path(ellipseIn: CGRect(x: p.x - 2.5, y: p.y - 2.5, width: 5, height: 5)), with: .color(yellow))

        let texts = [target.yards, target.remain].compactMap { $0 }
        for (text, rect) in zip(texts, target.labelRects) {
            var shadowed = context
            shadowed.addFilter(.shadow(color: .black.opacity(0.75), radius: 2))
            shadowed.draw(text, at: CGPoint(x: rect.midX, y: rect.midY))
        }
    }
}

/// Compact, transform-aware map window used while the Touch Target is dragged (100 pt, 2.35x,
/// white crosshair). The main map applies `C + s(p-C) + O`; the extra magnification keeps the exact
/// source pixel under the finger at the loupe crosshair even after pinch zooming or map panning.
struct LiveMapTargetMagnifierLoupe<Content: View>: View {
    static var diameter: CGFloat { 100 }
    static var magnification: CGFloat { 2.35 }

    let content: Content
    let mapSize: CGSize
    let focus: CGPoint
    let displayedScale: CGFloat
    let displayedOffset: CGSize
    let diameter: CGFloat
    let magnification: CGFloat

    init(
        mapSize: CGSize,
        focus: CGPoint,
        displayedScale: CGFloat,
        displayedOffset: CGSize,
        diameter: CGFloat = 100,
        magnification: CGFloat = 2.35,
        @ViewBuilder content: () -> Content
    ) {
        self.content = content()
        self.mapSize = mapSize
        self.focus = focus
        self.displayedScale = displayedScale
        self.displayedOffset = displayedOffset
        self.diameter = diameter
        self.magnification = magnification
    }

    var body: some View {
        let safeScale = max(displayedScale.isFinite ? displayedScale : 1, 0.001)
        let safeMagnification = max(magnification.isFinite ? magnification : 1, 1)
        let safeFocus = CGPoint(
            x: focus.x.isFinite ? focus.x : mapSize.width / 2,
            y: focus.y.isFinite ? focus.y : mapSize.height / 2
        )
        let center = CGPoint(x: mapSize.width / 2, y: mapSize.height / 2)
        let dx: CGFloat = diameter / 2
            + safeMagnification * ((1 - safeScale) * center.x + displayedOffset.width - safeFocus.x)
        let dy: CGFloat = diameter / 2
            + safeMagnification * ((1 - safeScale) * center.y + displayedOffset.height - safeFocus.y)

        ZStack(alignment: .topLeading) {
            content
                .frame(width: mapSize.width, height: mapSize.height)
                .scaleEffect(safeScale * safeMagnification, anchor: .topLeading)
                .offset(x: dx, y: dy)
        }
        .frame(width: diameter, height: diameter, alignment: .topLeading)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay {
            ZStack {
                Circle()
                    .stroke(LiveTargetRenderer.yellow, lineWidth: 2.5)
                    .frame(width: 26, height: 26)
                Rectangle().fill(.white.opacity(0.95)).frame(width: 1.4, height: 18)
                Rectangle().fill(.white.opacity(0.95)).frame(width: 18, height: 1.4)
            }
            .shadow(color: .black.opacity(0.6), radius: 0.6)
        }
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(.white.opacity(0.86), lineWidth: 1))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(.black.opacity(0.24), lineWidth: 1))
        .compositingGroup()
        .shadow(color: .black.opacity(0.38), radius: 7, y: 3)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("拖动目标点时的放大视图")
        .accessibilityIdentifier("live-map-target-magnifier")
    }

    /// Keep the loupe fully visible above the finger, clear of the top hole facts and the bottom
    /// 记分 / 记一杆 row; below the finger only when there is no room above.
    static func position(for location: CGPoint, in size: CGSize, diameter: CGFloat = 100) -> CGPoint {
        let half = diameter / 2
        let fingerClearance: CGFloat = 72
        let minX = half + 8
        let maxX = max(minX, size.width - half - 8)
        let minY = half + 150
        let maxY = max(minY, size.height - half - 130)
        let x = min(max(location.x, minX), maxX)
        let above = location.y - half - fingerClearance
        let below = location.y + half + fingerClearance
        let preferred = above >= minY ? above : below
        return CGPoint(x: x, y: min(max(preferred, minY), maxY))
    }
}
