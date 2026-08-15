import SwiftUI

/// Garmin-style Virtual Caddie instrument: one route at a time, with the factual hole map and target
/// as the visual subject. Turning the Crown browses the stable 推荐 → 保守 → 进攻 order; selecting a
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
                topClearance: 52
            ))
        } ?? CGFloat(WatchHoleMapView.restingCrownScale)

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
                    hazards: [],
                    hazardRoute: route,
                    ringPips: [],
                    showTextOverlay: false,
                    showHoleIdentity: false,
                    fullMap: true,
                    mapScale: scale,
                    geometry: mappedGeometry
                )
                .allowsHitTesting(false)
            } else {
                Color(red: 0.08, green: 0.18, blue: 0.10)
                Image(systemName: "map")
                    .font(.system(size: 28, weight: .light))
                    .foregroundStyle(.white.opacity(0.25))
            }

            LinearGradient(
                colors: [.black.opacity(0.76), .clear, .clear, .black.opacity(0.88)],
                startPoint: .top,
                endPoint: .bottom
            )
            .allowsHitTesting(false)

            VStack(spacing: 0) {
                header(option)
                Spacer()
                footer(option)
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

    private func header(_ option: WatchCaddieOption) -> some View {
        HStack(spacing: 5) {
            Button(action: { onBack?() }) {
                Image(systemName: "chevron.backward")
                    .font(.system(size: 11, weight: .bold))
                    .frame(width: 28, height: 28)
                    .background(Color.black.opacity(0.58), in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("返回球洞")
            Text(strategyLabel(option))
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(AICaddieDesignTokens.strategyColor(Self.strategyKey(option.optionId)))
                .lineLimit(1)
            Spacer(minLength: 48)
        }
    }

    private func footer(_ option: WatchCaddieOption) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(clubChain(option))
                .font(.system(size: 14, weight: .bold, design: .rounded))
                .lineLimit(1)
                .minimumScaleFactor(0.85)
            HStack(spacing: 5) {
                Text(carrySummary(option))
                    .font(.system(size: 10, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.white.opacity(0.82))
                    .lineLimit(1)
                    .minimumScaleFactor(0.85)
                Spacer(minLength: 2)
                Text("\(selectedIndex + 1)/\(orderedOptions.count)")
                    .font(.system(size: 9, weight: .medium, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.white.opacity(0.62))
            }
        }
        .padding(.horizontal, 7)
        .padding(.vertical, 5)
        .background(Color.black.opacity(0.72), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
    }

    private func emptyState(size: CGSize) -> some View {
        let safeRect = WatchDisplayGeometry.contentRect(in: size)
        return VStack(spacing: 8) {
            HStack {
                Button(action: { onBack?() }) {
                    Image(systemName: "chevron.backward")
                }
                .buttonStyle(.plain)
                Text("球童建议").font(.system(size: 14, weight: .bold))
                Spacer(minLength: 48)
            }
            Spacer()
            Text("暂无可用方案")
                .font(.system(size: 12, weight: .medium))
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

    /// Convert the remaining club sequence into grounded route points. The first shot already owns
    /// `WatchCurrentShotLayout.target`; every middle shot gets its cumulative route landing and the
    /// final shot terminates at the actual pin instead of an invented extension beyond the green.
    static func continuationTargets(
        for option: WatchCaddieOption,
        route: [[Double]],
        geometry: WatchHoleMapGeometry
    ) -> [CGPoint] {
        guard let plan = option.plan,
              plan.count > 1,
              let firstCarry = plan.first?.carryM ?? option.carryM,
              firstCarry.isFinite,
              firstCarry > 0,
              let progress = WatchHazardMapLayout.playerProgressMetres(
                on: route,
                playerImagePoint: geometry.youPx
              ),
              var previous = WatchHazardMapLayout.imagePoint(
                on: route,
                atMetres: progress + firstCarry
              ) else { return [] }

        var cumulative = progress + firstCarry
        var targets: [CGPoint] = []
        if plan.count > 2 {
            for step in plan.dropFirst().dropLast() {
                guard let carry = step.carryM, carry.isFinite, carry > 0 else { continue }
                cumulative += carry
                guard let target = WatchHazardMapLayout.imagePoint(on: route, atMetres: cumulative),
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
              let target = WatchHazardMapLayout.imagePoint(on: route, atMetres: progress + carry)
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
        option.plan?.first?.carryM ?? option.carryM
    }

    private func clubChain(_ option: WatchCaddieOption) -> String {
        let plan = option.plan ?? []
        if !plan.isEmpty {
            return plan.map { WatchClubDisplay.shortCode($0.clubName) }.joined(separator: " → ")
        }
        return option.clubName.map(WatchClubDisplay.shortCode) ?? "—"
    }

    private func carrySummary(_ option: WatchCaddieOption) -> String {
        if let p10 = option.carryP10M,
           let p90 = option.carryP90M,
           p10.isFinite, p90.isFinite, p10 > 0, p90 >= p10 {
            return "实测 \(Self.yards(p10))–\(Self.yards(p90))码"
        }
        if let fallback = option.optionId == recommendedId ? rootRecommendation : nil {
            return "实测 \(Self.yards(fallback.carryP10M))–\(Self.yards(fallback.carryP90M))码"
        }
        if let carry = firstCarry(option), carry.isFinite, carry > 0 {
            return "目标 \(Self.yards(carry))码"
        }
        return "暂无落点范围"
    }

    private func strategyLabel(_ option: WatchCaddieOption) -> String {
        switch Self.strategyKey(option.optionId) {
        case "stock": return "推荐"
        case "protect_score": return "保守"
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
        case "stock": return 0
        case "protect_score": return 1
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

    static func yards(_ metres: Double) -> Int { Int((metres * 1.09361).rounded()) }
}

/// Opening the recommendation from Hole Root goes to the focused route instrument. Older payloads
/// with only one current-shot fact retain the honest text fallback.
public struct WatchCaddieScreen: View {
    public let state: WatchRoundState
    public let geometry: WatchHoleMapGeometry?
    public let frontYd: Int?
    public let centerYd: Int?
    public let backYd: Int?
    public let lastShotDistanceM: Double?
    public let onBack: () -> Void

    public init(
        state: WatchRoundState,
        geometry: WatchHoleMapGeometry? = nil,
        frontYd: Int? = nil,
        centerYd: Int? = nil,
        backYd: Int? = nil,
        lastShotDistanceM: Double? = nil,
        onBack: @escaping () -> Void = {}
    ) {
        self.state = state
        self.geometry = geometry
        self.frontYd = frontYd
        self.centerYd = centerYd
        self.backYd = backYd
        self.lastShotDistanceM = lastShotDistanceM
        self.onBack = onBack
    }

    var showsPlanOptionsFirst: Bool { !state.caddieOptions.isEmpty }

    public var body: some View {
        if showsPlanOptionsFirst {
            WatchCaddieOptionsView(
                hole: state.hole,
                par: state.par,
                options: state.caddieOptions,
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
                        Button(action: onBack) {
                            Image(systemName: "chevron.backward")
                                .font(.caption.weight(.semibold))
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("返回球洞")
                        Text("球童建议")
                            .font(.headline)
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
