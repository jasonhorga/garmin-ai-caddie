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

    static func draw(
        _ context: inout GraphicsContext,
        size: CGSize,
        legs: [MapPlannedLeg],
        overlay: CoursePrepOverlay,
        scale: CGFloat,
        offset: CGSize,
        topInset: CGFloat
    ) {
        let centre = CGPoint(x: size.width / 2, y: size.height / 2)
        func screen(_ point: CGPoint) -> CGPoint? {
            guard let base = LivePlayMapOverlayLayout.project(
                overlayPoint: [Double(point.x), Double(point.y)],
                overlayWidth: overlay.w,
                overlayHeight: overlay.h,
                into: size,
                topInset: topInset
            ) else { return nil }
            let x: CGFloat = centre.x + (base.x - centre.x) * scale + offset.width
            let y: CGFloat = centre.y + (base.y - centre.y) * scale + offset.height
            return CGPoint(x: x, y: y)
        }
        let screenLegs = legs.compactMap { leg -> (leg: MapPlannedLeg, origin: CGPoint, destination: CGPoint)? in
            guard let origin = screen(leg.origin), let destination = screen(leg.destination) else { return nil }
            return (leg, origin, destination)
        }
        guard !screenLegs.isEmpty else { return }

        let arcs = screenLegs.map { HoleImageMapView.flightArc(from: $0.origin, to: $0.destination) }
        for (item, arc) in zip(screenLegs, arcs) {
            guard hypot(item.destination.x - item.origin.x, item.destination.y - item.origin.y) > 1 else { continue }
            let path = HoleImageMapView.path(for: arc)
            context.stroke(path, with: .color(.black.opacity(0.58)),
                           style: StrokeStyle(lineWidth: 6, lineCap: .round, lineJoin: .round))
            context.stroke(path, with: .color(.white.opacity(item.leg.isSelected ? 0.96 : 0.55)),
                           style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round))
        }
        for item in screenLegs where !item.leg.endsAtPin {
            let point = item.destination
            context.fill(Path(ellipseIn: CGRect(x: point.x - 7, y: point.y - 7, width: 14, height: 14)),
                         with: .color(item.leg.isSelected ? LiveHoleStyle.green : .white.opacity(0.64)))
            context.fill(Path(ellipseIn: CGRect(x: point.x - 2.5, y: point.y - 2.5, width: 5, height: 5)),
                         with: .color(.white))
        }

        // Everything a label must not cover: the route itself (sampled), every landing dot and the
        // flag, which is drawn in the bitmap and therefore scales with the map.
        let routeSamples = arcs.flatMap(samples(along:))
        var occupied: [CGRect] = screenLegs.map {
            CGRect(x: $0.destination.x - 8, y: $0.destination.y - 8, width: 16, height: 16)
        }
        if let pinLeg = screenLegs.last(where: { $0.leg.endsAtPin }) {
            occupied.append(flagRect(foot: pinLeg.destination, scale: scale))
        }
        let viewport = CGRect(origin: .zero, size: size).insetBy(dx: 4, dy: 4)
        for item in screenLegs {
            let text = Text(labelText(for: item.leg, pixelsPerMetre: overlay.ppm))
                .font(.system(size: labelFontSize, weight: .heavy, design: .rounded))
                .foregroundColor(.white)
            let resolved = context.resolve(text)
            let measured = resolved.measure(in: CGSize(width: 240, height: 60))
            let labelSize = CGSize(
                width: ceil(measured.width) + labelPadding.width * 2,
                height: ceil(measured.height) + labelPadding.height * 2
            )
            let rect = labelRect(
                landing: item.destination,
                from: item.origin,
                endsAtPin: item.leg.endsAtPin,
                flagScale: scale,
                labelSize: labelSize,
                viewport: viewport,
                occupied: occupied,
                routeSamples: routeSamples
            )
            occupied.append(rect)
            context.fill(Path(roundedRect: rect, cornerRadius: rect.height / 2),
                         with: .color(.black.opacity(item.leg.isSelected ? 0.74 : 0.5)))
            context.draw(resolved, at: CGPoint(x: rect.midX, y: rect.midY))
        }
    }

    /// Candidate positions in preference order: beside the landing across the flight direction
    /// (either side), then above/below; for the flag, to its left, clear of the pennant. The first
    /// candidate inside the viewport that touches nothing wins; otherwise the least-bad clamped one.
    static func labelRect(
        landing: CGPoint,
        from origin: CGPoint,
        endsAtPin: Bool,
        flagScale: CGFloat,
        labelSize: CGSize,
        viewport: CGRect,
        occupied: [CGRect],
        routeSamples: [CGPoint]
    ) -> CGRect {
        let w = labelSize.width
        let h = labelSize.height
        var dx = landing.x - origin.x
        var dy = landing.y - origin.y
        let length = hypot(dx, dy)
        if length > 1 { dx /= length; dy /= length } else { dx = 0; dy = -1 }
        let normal = CGPoint(x: -dy, y: dx)
        let gap: CGFloat = 12
        let acrossX: CGFloat = abs(normal.x) * w / 2
        let acrossY: CGFloat = abs(normal.y) * h / 2
        let across: CGFloat = acrossX + acrossY + gap
        let halfW: CGFloat = w / 2
        let halfH: CGFloat = h / 2
        let centres: [CGPoint]
        if endsAtPin {
            let flagHeight: CGFloat = LiveMapFlagRenderer.poleHeight * flagScale
            let flagWidth: CGFloat = (LiveMapFlagRenderer.pennantWidth + 2) * flagScale
            let flagMidY: CGFloat = landing.y - flagHeight / 2
            let leftX: CGFloat = landing.x - gap - halfW
            let rightX: CGFloat = landing.x + flagWidth + gap + halfW
            let aboveY: CGFloat = landing.y - flagHeight - gap - halfH
            let belowY: CGFloat = landing.y + gap + halfH
            centres = [
                CGPoint(x: leftX, y: flagMidY),
                CGPoint(x: rightX, y: flagMidY),
                CGPoint(x: landing.x, y: aboveY),
                CGPoint(x: landing.x, y: belowY),
            ]
        } else {
            let offsetX: CGFloat = normal.x * across
            let offsetY: CGFloat = normal.y * across
            let clearance: CGFloat = gap + 8 + halfH
            centres = [
                CGPoint(x: landing.x + offsetX, y: landing.y + offsetY),
                CGPoint(x: landing.x - offsetX, y: landing.y - offsetY),
                CGPoint(x: landing.x, y: landing.y - clearance),
                CGPoint(x: landing.x, y: landing.y + clearance),
            ]
        }
        let rects = centres.map { CGRect(x: $0.x - halfW, y: $0.y - halfH, width: w, height: h) }
        func conflicts(_ rect: CGRect) -> Int {
            let padded = rect.insetBy(dx: -2, dy: -2)
            let overlaps: Int = occupied.filter { $0.intersects(rect) }.count
            let crossings: Int = routeSamples.filter { padded.contains($0) }.count
            return overlaps + crossings
        }
        if let clear = rects.first(where: { viewport.contains($0) && conflicts($0) == 0 }) {
            return clear
        }
        let clamped = rects.map { clampedRect($0, into: viewport) }
        return clamped.min { conflicts($0) < conflicts($1) } ?? clamped[0]
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

    private static func quadPoint(_ arc: MapFlightArc, t: CGFloat) -> CGPoint {
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
