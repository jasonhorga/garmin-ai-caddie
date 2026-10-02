import SwiftUI

/// Garmin-style Virtual Caddie instrument: one route at a time, with the factual hole map and target
/// as the visual subject. Turning the Crown browses the stable 稳妥 → 标准 → 进攻 order; selecting a
/// route never moves it to a different slot.
public struct WatchCaddieOptionsView: View {
    public let hole: Int
    public let par: Int
    public let options: [WatchCaddieOption]
    public let recommendedId: String?
    public let geometry: WatchHoleMapGeometry?
    public let route: [[Double]]
    public let rootRecommendation: WatchRootCaddieRecommendation?
    public let onBack: (() -> Void)?

    @State private var crownSelection: Double

    public init(
        hole: Int = 0,
        par: Int = 0,
        options: [WatchCaddieOption],
        recommendedId: String? = nil,
        geometry: WatchHoleMapGeometry? = nil,
        route: [[Double]] = [],
        rootRecommendation: WatchRootCaddieRecommendation? = nil,
        onBack: (() -> Void)? = nil
    ) {
        self.hole = hole
        self.par = par
        self.options = options
        self.recommendedId = recommendedId
        self.geometry = geometry
        self.route = route
        self.rootRecommendation = rootRecommendation
        self.onBack = onBack

        let ordered = Self.ordered(options)
        let initialIndex = recommendedId.flatMap { id in
            ordered.firstIndex { $0.optionId == id }
        } ?? ordered.firstIndex { Self.strategyKey($0.optionId) == "stock" } ?? 0
        _crownSelection = State(initialValue: Double(initialIndex))
    }

    public var body: some View {
        GeometryReader { proxy in
            if let option = selectedOption {
                optionInstrument(option, size: proxy.size)
            } else {
                emptyState(size: proxy.size)
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
        .simultaneousGesture(
            DragGesture(minimumDistance: 24)
                .onEnded { value in
                    guard let onBack,
                          WatchEdgeBackGesture.shouldTrigger(
                            startX: value.startLocation.x,
                            translation: value.translation
                          ) else { return }
                    onBack()
                }
        )
        .accessibilityAction(named: Text("返回球洞")) { onBack?() }
        .accessibilityIdentifier("watch-caddie-instrument")
        .ignoresSafeArea()
    }

    private var orderedOptions: [WatchCaddieOption] { Self.ordered(options) }

    private var selectedIndex: Int {
        min(max(Int(crownSelection.rounded()), 0), max(orderedOptions.count - 1, 0))
    }

    private var selectedOption: WatchCaddieOption? {
        guard orderedOptions.indices.contains(selectedIndex) else { return nil }
        return orderedOptions[selectedIndex]
    }

    private var crownUpperBound: Double { Double(max(orderedOptions.count - 1, 1)) }

    private func optionInstrument(_ option: WatchCaddieOption, size: CGSize) -> some View {
        let safeInset = WatchDisplayGeometry.contentInset(for: size)
        let mappedGeometry = geometry.map { optionGeometry(option, base: $0) }
        let shotLayout = mappedGeometry.flatMap { currentShotLayout(option, geometry: $0) }
        // The focused Caddie screen is a whole-hole plan, not a duplicate next-shot overlay. Fit the
        // viewport through the final pin whenever the payload contains a multi-club sequence.
        let focusY = shotLayout?.continuation.last?.y
            ?? shotLayout?.carryP90.y
            ?? mappedGeometry?.layupPx.y
            ?? geometry?.pinPx.y
            ?? 0
        let scale = mappedGeometry.map {
            CGFloat(WatchHoleMapViewport.effectiveRestingScale(
                requestedScale: WatchHoleMapView.maximumCrownScale,
                viewportHeight: Double(size.height),
                playerAnchorFraction: 0.66,
                playerImageY: Double($0.youPx.y),
                pinImageY: Double(focusY),
                topClearance: 42
            ))
        } ?? CGFloat(WatchHoleMapView.restingCrownScale)
        let legs = mappedGeometry.map { Self.planLegs(for: option, route: route, geometry: $0) } ?? []
        // The whole remaining plan (player, every landing and its label, the pin and its flag)
        // fits between the header and the strategy row, with or without measured dispersion.
        let viewport = mappedGeometry.flatMap { geometry in
            Self.planViewport(
                points: [geometry.youPx] + legs.map(\.landing) + [geometry.pinPx],
                size: size,
                maxScale: CGFloat(WatchHoleMapView.maximumCrownScale)
            )
        }

        return ZStack {
            if let mappedGeometry {
                WatchHoleMapView(
                    holeNumber: hole,
                    par: par,
                    frontGreen: nil,
                    centerGreen: nil,
                    backGreen: nil,
                    lastShot: 0,
                    caddieClub: primaryClub(option),
                    caddieNote: "",
                    showCaddieRecommendation: true,
                    currentShotLayout: shotLayout,
                    showPreparedPlan: shotLayout == nil && firstCarry(option) != nil,
                    hazardRoute: route,
                    ringPips: [],
                    showTextOverlay: false,
                    showHoleIdentity: false,
                    fullMap: true,
                    mapScale: viewport?.scale ?? scale,
                    fullMapFocusImagePx: viewport?.focusImage,
                    fullMapFocusCanvasFraction: viewport?.focusFraction ?? CGPoint(x: 0.5, y: 0.52),
                    geometry: mappedGeometry,
                    // The whole remaining plan, the same legs as the 方案 page; dispersion (live
                    // only) is drawn on top and is not needed to show the later shots.
                    planLegs: legs,
                    planLabelBounds: Self.planRestFrame(in: size)
                )
                .allowsHitTesting(false)
            } else {
                Color(red: 0.08, green: 0.18, blue: 0.10)
                Image(systemName: "map")
                    .font(.system(size: 28, weight: .light))
                    .foregroundStyle(.white.opacity(0.25))
            }

            LinearGradient(
                colors: [.black.opacity(0.62), .clear, .clear, .black.opacity(0.58)],
                startPoint: .top,
                endPoint: .bottom
            )
            .allowsHitTesting(false)

            VStack(spacing: 0) {
                header(option, compact: size.width < 190)
                Spacer()
                HStack(spacing: 4) {
                    Text(strategyLabel(option))
                        .font(.system(size: 14, weight: .black))
                        .foregroundStyle(AICaddieDesignTokens.strategyColor(Self.strategyKey(option.optionId)))
                    Spacer()
                    if orderedOptions.count > 1 {
                        Text("\(selectedIndex + 1)/\(orderedOptions.count)")
                            .font(.system(size: 13, weight: .black, design: .rounded))
                            .monospacedDigit()
                            .foregroundStyle(.white.opacity(0.7))
                    }
                }
            }
            .padding(.horizontal, safeInset)
            .padding(.top, safeInset)
            .padding(.bottom, safeInset)

            if orderedOptions.count > 1 {
                HStack {
                    Spacer()
                    VStack(spacing: 5) {
                        ForEach(orderedOptions.indices, id: \.self) { index in
                            Circle()
                                .fill(index == selectedIndex ? Color.white : Color.white.opacity(0.28))
                                .frame(width: index == selectedIndex ? 5 : 4, height: index == selectedIndex ? 5 : 4)
                        }
                    }
                    .padding(.trailing, safeInset)
                }
            }
        }
    }

    private func header(_ option: WatchCaddieOption, compact: Bool) -> some View {
        HStack(spacing: 5) {
            WatchInstrumentBackButton(accessibilityLabel: "返回球洞") { onBack?() }
            Text(Self.clubChain(option, compact: compact))
                .font(.system(size: 18, weight: .black, design: .rounded))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.78)
            Spacer(minLength: 48)
        }
    }

    private func emptyState(size: CGSize) -> some View {
        let safeRect = WatchDisplayGeometry.contentRect(in: size)
        return VStack(spacing: 8) {
            HStack {
                WatchInstrumentBackButton(accessibilityLabel: "返回球洞") { onBack?() }
                Text("球童建议").font(.system(size: 20, weight: .black))
                Spacer(minLength: 48)
            }
            Spacer()
            Text("暂无可用方案")
                .font(.system(size: 16, weight: .bold))
                .foregroundStyle(.secondary)
            Spacer()
        }
        .frame(width: safeRect.width, height: safeRect.height)
        .position(x: safeRect.midX, y: safeRect.midY)
    }

    private func currentShotLayout(
        _ option: WatchCaddieOption,
        geometry: WatchHoleMapGeometry
    ) -> WatchCurrentShotLayout? {
        let fallback = option.optionId == recommendedId ? rootRecommendation : nil
        guard let aim = firstCarry(option) ?? fallback?.aimCarryM,
              let p10 = option.carryP10M ?? fallback?.carryP10M,
              let p90 = option.carryP90M ?? fallback?.carryP90M else { return nil }
        let continuation = Self.continuationTargets(
            for: option,
            route: route,
            geometry: geometry
        )
        return WatchCurrentShotLayout.resolve(
            route: route,
            playerImagePoint: geometry.youPx,
            aimCarryM: aim,
            carryP10M: p10,
            carryP90M: p90,
            continuation: continuation
        )
    }

    /// How the focused plan is framed: the image scale, the image point at the frame's centre and
    /// where that centre sits on the face (as fractions of its size).
    struct PlanViewport: Equatable {
        let scale: CGFloat
        let focusImage: CGPoint
        let focusFraction: CGPoint
    }

    /// Room each landing's label (drawn to its right, stacked by `WatchPlanLegs.labelFrames`) and the pin's flag need.
    static let planLabelReserve = CGSize(width: 58, height: 16)
    static let planFlagReserve: CGFloat = 16

    /// The face between the header (back button + club chain) and the strategy row, left of the
    /// plan dots.
    static func planRestFrame(in size: CGSize) -> CGRect {
        let inset = WatchDisplayGeometry.contentInset(for: size)
        let top = inset + WatchDisplayGeometry.instrumentControlSize + 4
        let bottom = size.height - inset - 22
        return CGRect(x: inset, y: top, width: max(0, size.width - inset * 2 - 12), height: max(0, bottom - top))
    }

    /// The scale and centre that fit every `points` (player, landings, pin) into the rest frame
    /// with room for the landing labels and the flag; never zoomed past `maxScale`.
    static func planViewport(points: [CGPoint], size: CGSize, maxScale: CGFloat) -> PlanViewport? {
        guard let first = points.first, size.width > 0, size.height > 0 else { return nil }
        var minX = first.x, maxX = first.x, minY = first.y, maxY = first.y
        for point in points.dropFirst() {
            minX = min(minX, point.x); maxX = max(maxX, point.x)
            minY = min(minY, point.y); maxY = max(maxY, point.y)
        }
        let rest = planRestFrame(in: size)
        let half = planLabelReserve.height / 2
        let fit = CGRect(
            x: rest.minX + 4,
            y: rest.minY + max(planFlagReserve, half),
            width: rest.width - 4 - planLabelReserve.width,
            height: rest.height - max(planFlagReserve, half) - half
        )
        guard fit.width > 0, fit.height > 0 else { return nil }
        let scale = min(maxScale, fit.width / max(maxX - minX, 1), fit.height / max(maxY - minY, 1))
        return PlanViewport(
            scale: scale,
            focusImage: CGPoint(x: (minX + maxX) / 2, y: (minY + maxY) / 2),
            focusFraction: CGPoint(x: fit.midX / size.width, y: fit.midY / size.height)
        )
    }

    /// Every leg still to play of `option` from the player, whatever its offset basis.
    static func planLegs(
        for option: WatchCaddieOption,
        route: [[Double]],
        geometry: WatchHoleMapGeometry
    ) -> [WatchPlanLeg] {
        guard let progress = WatchHazardMapLayout.playerProgressMetres(on: route, playerImagePoint: geometry.youPx) else {
            return []
        }
        return WatchPlanLegs.resolve(
            plan: option.remainingPlan(fromProgressM: progress, shotsSinceOrigin: 0),
            route: route,
            origin: geometry.youPx
        )
    }

    /// Convert the remaining club sequence into grounded route points. The first shot already owns
    /// `WatchCurrentShotLayout.target`; every middle shot gets its cumulative route landing and the
    /// final shot terminates at the actual pin instead of an invented extension beyond the green.
    static func continuationTargets(
        for option: WatchCaddieOption,
        route: [[Double]],
        geometry: WatchHoleMapGeometry
    ) -> [CGPoint] {
        guard let progress = WatchHazardMapLayout.playerProgressMetres(
                on: route,
                playerImagePoint: geometry.youPx
              ) else { return [] }
        // Offsets re-based on the player whatever the option's basis (`WatchRouteOffsetBasis`).
        let plan = option.remainingPlan(fromProgressM: progress, shotsSinceOrigin: 0)
        guard plan.count > 1,
              let firstCarry = plan.first?.routeOffsetM ?? plan.first?.carryM ?? option.carryM,
              firstCarry.isFinite,
              firstCarry > 0,
              var previous = WatchHazardMapLayout.imagePoint(
                on: route,
                atMetres: progress + firstCarry
              ) else { return [] }

        var cumulative = progress + firstCarry
        var targets: [CGPoint] = []
        if plan.count > 2 {
            for step in plan.dropFirst().dropLast() {
                let targetMetres: Double
                if let routeOffset = step.routeOffsetM, routeOffset.isFinite, routeOffset > 0 {
                    targetMetres = progress + routeOffset
                    cumulative = targetMetres
                } else if let carry = step.carryM, carry.isFinite, carry > 0 {
                    cumulative += carry
                    targetMetres = cumulative
                } else {
                    continue
                }
                guard let target = WatchHazardMapLayout.imagePoint(on: route, atMetres: targetMetres),
                      hypot(target.x - previous.x, target.y - previous.y) > 1 else { continue }
                targets.append(target)
                previous = target
            }
        }

        if hypot(geometry.pinPx.x - previous.x, geometry.pinPx.y - previous.y) > 1 {
            targets.append(geometry.pinPx)
        }
        return targets
    }

    private func optionGeometry(
        _ option: WatchCaddieOption,
        base: WatchHoleMapGeometry
    ) -> WatchHoleMapGeometry {
        guard let carry = firstCarry(option), carry.isFinite, carry > 0,
              let progress = WatchHazardMapLayout.playerProgressMetres(
                on: route,
                playerImagePoint: base.youPx
              ),
              let target = WatchHazardMapLayout.imagePoint(
                  on: route,
                  atMetres: progress + (
                      option.remainingPlan(fromProgressM: progress, shotsSinceOrigin: 0).first?.routeOffsetM ?? carry
                  )
              )
        else { return base }

        let apex = WatchHazardMapLayout.imagePoint(on: route, atMetres: progress + carry * 0.5)
            ?? midpoint(base.youPx, target)
        let total = route.last.flatMap { $0.count >= 3 ? $0[2] : nil } ?? progress + carry
        let greenControl = WatchHazardMapLayout.imagePoint(
            on: route,
            atMetres: min(total, progress + carry + max(0, total - progress - carry) * 0.5)
        ) ?? midpoint(target, base.pinPx)

        return WatchHoleMapGeometry(
            image: base.image,
            imageSize: base.imageSize,
            youPx: base.youPx,
            pinPx: base.pinPx,
            layupPx: target,
            apexPx: apex,
            greenCtrlPx: greenControl,
            routePx: base.routePx,
            greenOutlinePx: base.greenOutlinePx,
            hazardSpans: base.hazardSpans
        )
    }

    private func midpoint(_ lhs: CGPoint, _ rhs: CGPoint) -> CGPoint {
        CGPoint(x: (lhs.x + rhs.x) * 0.5, y: (lhs.y + rhs.y) * 0.5)
    }

    private func primaryClub(_ option: WatchCaddieOption) -> String {
        option.plan?.first?.clubName ?? option.clubName ?? "—"
    }

    private func firstCarry(_ option: WatchCaddieOption) -> Double? {
        // Only a live (shot-based) offset is a distance from the player.
        (option.resolvedRouteOffsetBasis == .shot ? option.plan?.first?.routeOffsetM : nil)
            ?? option.plan?.first?.carryM ?? option.carryM
    }

    static func clubChain(_ option: WatchCaddieOption, compact: Bool) -> String {
        let plan = option.plan ?? []
        if !plan.isEmpty {
            return plan
                .map { WatchClubDisplay.shortCode($0.clubName) }
                .joined(separator: compact ? "›" : " → ")
        }
        return option.clubName.map(WatchClubDisplay.shortCode) ?? "—"
    }

    private func strategyLabel(_ option: WatchCaddieOption) -> String {
        switch Self.strategyKey(option.optionId) {
        case "stock": return "标准"
        case "protect_score": return "稳妥"
        case "attack": return "进攻"
        default: return option.label
        }
    }

    /// Internal so the Watch tests can lock the player-facing order without reaching into SwiftUI
    /// rendering state. The selected recommendation changes the initial Crown position, never order.
    static func ordered(_ options: [WatchCaddieOption]) -> [WatchCaddieOption] {
        options.enumerated().sorted { lhs, rhs in
            let lhsRank = strategyRank(lhs.element.optionId)
            let rhsRank = strategyRank(rhs.element.optionId)
            return lhsRank == rhsRank ? lhs.offset < rhs.offset : lhsRank < rhsRank
        }.map(\.element)
    }

    private static func strategyRank(_ optionId: String) -> Int {
        switch strategyKey(optionId) {
        case "protect_score": return 0
        case "stock": return 1
        case "attack": return 2
        default: return 3
        }
    }

    private static func strategyKey(_ optionId: String) -> String {
        switch optionId.lowercased() {
        case "safe", "conservative", "protect", "protect_score": return "protect_score"
        case "attack", "aggressive": return "attack"
        default: return "stock"
        }
    }
}

/// Opening the recommendation from Hole Root goes to the focused route instrument. Older payloads
/// with only one current-shot fact retain the honest text fallback.
public struct WatchCaddieScreen: View {
    public let state: WatchRoundState
    /// The options as they stand now (`WatchRoundModel.currentCaddieOptions`); defaults to the
    /// state's own.
    public let options: [WatchCaddieOption]
    public let geometry: WatchHoleMapGeometry?
    public let frontYd: Int?
    public let centerYd: Int?
    public let backYd: Int?
    public let lastShotDistanceM: Double?
    public let onBack: () -> Void

    public init(
        state: WatchRoundState,
        options: [WatchCaddieOption]? = nil,
        geometry: WatchHoleMapGeometry? = nil,
        frontYd: Int? = nil,
        centerYd: Int? = nil,
        backYd: Int? = nil,
        lastShotDistanceM: Double? = nil,
        onBack: @escaping () -> Void = {}
    ) {
        self.state = state
        self.options = options ?? state.caddieOptions
        self.geometry = geometry
        self.frontYd = frontYd
        self.centerYd = centerYd
        self.backYd = backYd
        self.lastShotDistanceM = lastShotDistanceM
        self.onBack = onBack
    }

    var showsPlanOptionsFirst: Bool { !options.isEmpty }

    public var body: some View {
        if !showsPlanOptionsFirst && !state.caddieOptions.isEmpty {
            // The hole's plans are all played or stale: never fall back to the raw decision text.
            Color.black.onAppear(perform: onBack)
        } else if showsPlanOptionsFirst {
            WatchCaddieOptionsView(
                hole: state.displayHoleNumber,
                par: state.par,
                options: options,
                recommendedId: state.offlineOptionId ?? state.strategyMode,
                geometry: geometry,
                route: state.holeMap?.route ?? [],
                rootRecommendation: state.rootCaddieRecommendation,
                onBack: onBack
            )
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 5) {
                        WatchInstrumentBackButton(accessibilityLabel: "返回球洞", onBack: onBack)
                        Text("球童建议")
                            .font(.system(size: 20, weight: .black))
                    }
                    WatchCaddieGlanceView(
                        state: state,
                        frontYd: frontYd,
                        centerYd: centerYd,
                        backYd: backYd,
                        lastShotDistanceM: lastShotDistanceM
                    )
                }
                .padding(8)
            }
            .scrollIndicators(.hidden)
        }
    }
}
