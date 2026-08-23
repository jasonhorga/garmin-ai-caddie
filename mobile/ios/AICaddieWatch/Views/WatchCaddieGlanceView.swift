import SwiftUI

public struct WatchCaddieGlanceView: View {
    /// The root instrument gives compact mode the height left after its header and action rail. This
    /// is the preferred height for callers that render the glance without a measured root budget.
    public static let compactInstrumentPreferredHeight: CGFloat = 112
    /// Kept as a source-compatible alias for snapshot/layout callers. The root no longer treats this
    /// value as a fixed slot; use `compactInstrumentHeight(for:)` when a face budget is available.
    public static let compactInstrumentHeight: CGFloat = compactInstrumentPreferredHeight
    public static let compactInstrumentContentHeight: CGFloat = 102
    public static let compactInstrumentMinimumWidth: CGFloat = 144

    public enum CompactDensity: Equatable {
        case regular
        case tight
        case minimal

        fileprivate var rowSpacing: CGFloat {
            switch self {
            case .regular:
                return 2
            case .tight, .minimal:
                return 1
            }
        }
    }

    /// Select a vertically bounded compact presentation. The thresholds leave a small glyph/stroke
    /// allowance so a 41 mm face can fall back before SwiftUI has to clip a row at its bottom edge.
    public static func compactDensity(for height: CGFloat) -> CompactDensity {
        guard height.isFinite else { return .regular }
        if height < 74 { return .minimal }
        if height < compactInstrumentContentHeight { return .tight }
        return .regular
    }

    /// Resolve the glance slot from the actual space left by the root. A measured budget is allowed
    /// to grow on the 45/49 mm faces; it is never allowed to exceed that budget or become negative.
    public static func compactInstrumentHeight(for availableHeight: CGFloat) -> CGFloat {
        guard availableHeight.isFinite else { return compactInstrumentPreferredHeight }
        return max(0, availableHeight)
    }

    public static func compactContentHeight(for density: CompactDensity) -> CGFloat {
        switch density {
        case .regular:
            return 102
        case .tight:
            return 74
        case .minimal:
            return 68
        }
    }

    public let state: WatchRoundState
    public let frontYd: Int?
    public let centerYd: Int?
    public let backYd: Int?
    public let lastShotDistanceM: Double?
    public let compact: Bool
    public let compactHeight: CGFloat?

    public init(
        state: WatchRoundState,
        frontYd: Int? = nil,
        centerYd: Int? = nil,
        backYd: Int? = nil,
        lastShotDistanceM: Double? = nil,
        compact: Bool = false,
        compactHeight: CGFloat? = nil
    ) {
        self.state = state
        self.frontYd = frontYd
        self.centerYd = centerYd
        self.backYd = backYd
        self.lastShotDistanceM = lastShotDistanceM
        self.compact = compact
        self.compactHeight = compactHeight
    }

    var displayFrontYd: Int? { frontYd ?? state.frontGreenM.map { WatchUnits.yards($0) } }
    var displayCenterYd: Int? { centerYd ?? state.centerGreenM.map { WatchUnits.yards($0) } }
    var displayBackYd: Int? { backYd ?? state.backGreenM.map { WatchUnits.yards($0) } }
    var displayLastShotDistanceM: Double? {
        lastShotDistanceM ?? state.distanceFromLastShotM ?? state.lastShotDistanceM
    }

    /// Prepared offline course data has no explicit target workflow. Only show target status when the
    /// payload actually carries target metadata; otherwise "待选旗位" would invent a required action.
    var showsTargetStatus: Bool {
        state.targetKind != nil || state.targetLatitude != nil || state.targetLongitude != nil
    }

    public var body: some View {
        if compact {
            compactBody
        } else {
            fullBody
        }
    }

    private var fullBody: some View {
        VStack(alignment: .leading, spacing: 4) {
            // round-13 LIVE: 前/中/后果岭(F/M/B)+ 坡度补偿 + 距上一杆 (码). Each guarded so a
            // hole without geometry (fields nil) shows nothing rather than "0" noise.
            if displayCenterYd != nil || displayFrontYd != nil || displayBackYd != nil {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    if let front = displayFrontYd { greenPip("前", front) }
                    if let center = displayCenterYd {
                        VStack(spacing: 0) {
                            Text(WatchGeoMath.greenRangeText(center))
                                .font(.system(size: 44, weight: .black, design: .rounded)).monospacedDigit()
                                .foregroundStyle(AICaddieDesignTokens.hudYellow)
                                .lineLimit(1)
                                .minimumScaleFactor(0.55)
                            Text("中").font(.system(size: 12, weight: .bold)).foregroundStyle(.secondary)
                        }
                    }
                    if let back = displayBackYd { greenPip("后", back) }
                }
                if [displayFrontYd, displayCenterYd, displayBackYd]
                    .contains(where: WatchGeoMath.isBeyondUsefulGreenRange) {
                    Text("离本洞较远")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(.secondary)
                }
            }
            if let delta = state.elevationDeltaM, abs(delta) >= 0.5 {
                let dy = WatchUnits.yards(delta)
                HStack(spacing: 3) {
                    Image(systemName: delta > 0 ? "arrow.up.right" : "arrow.down.right")
                    Text("坡度 \(dy > 0 ? "+" : "")\(dy) 码")
                }
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(delta > 0 ? AICaddieDesignTokens.bogey : AICaddieDesignTokens.par)
            }
            if let fromLast = displayLastShotDistanceM {
                let fromLastYards = WatchUnits.yards(fromLast)
                HStack(spacing: 3) {
                    Image(systemName: "arrow.left.and.right")
                    Text(
                        WatchGeoMath.isBeyondUsefulGreenRange(fromLastYards)
                            ? "离上一杆较远"
                            : "距上一杆 \(WatchGeoMath.greenRangeText(fromLastYards)) 码"
                    )
                }
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(.secondary)
            }
            HStack {
                Image(systemName: "scope")
                Text(WatchClubDisplay.name(state.suggestedClub ?? state.selectedClub ?? "--"))
                    .font(.system(size: 20, weight: .black))
            }
            if let targetNote = state.targetNote {
                Text(targetNote)
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(.secondary)
            }
            if showsTargetStatus {
                HStack(spacing: 4) {
                    Image(systemName: state.targetLatitude == nil || state.targetLongitude == nil ? "mappin.slash" : "mappin.and.ellipse")
                    Text(state.targetLatitude == nil || state.targetLongitude == nil ? "待选旗位" : "\(WatchCaddieText.targetNoun(state.targetKind))就绪")
                        .lineLimit(1)
                }
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(state.targetLatitude == nil || state.targetLongitude == nil ? AICaddieDesignTokens.confidenceColor("low") : .secondary)
            }
            if let nextShotPrompt = state.nextShotPrompt {
                HStack(spacing: 4) {
                    Image(systemName: "figure.golf")
                    Text(nextShotPrompt)
                        .lineLimit(2)
                }
                .font(.system(size: 16, weight: .black))
                .foregroundStyle(AICaddieDesignTokens.strategyColor("stock"))
            }
            if let holePlanSummary = state.holePlanSummary {
                HStack(spacing: 4) {
                    Image(systemName: "point.topleft.down.curvedto.point.bottomright.up")
                    Text(holePlanSummary)
                        .lineLimit(2)
                }
                .font(.system(size: 13, weight: .black))
                .foregroundStyle(AICaddieDesignTokens.strategyColor(state.strategyMode ?? "stock"))
            }
            // De-engineered: the watch glance shows the caddie call + confidence below, not the raw
            // evidence / missing-data provenance strings. (Those fields are still carried in the
            // model for the phone — just no longer surfaced on the watch.)
            Text(WatchCaddieText.confidence(state.caddieConfidence))
                .font(.system(size: 14, weight: .black))
                .foregroundStyle(AICaddieDesignTokens.confidenceColor(state.caddieConfidence))
        }
    }

    /// Compact mode has an explicit row budget. The regular version keeps the complete shot call;
    /// tight/minimal versions remove lower-priority copy before a small face ever has to clip text.
    private var compactBody: some View {
        let height = max(0, compactHeight ?? Self.compactInstrumentPreferredHeight)
        let density = Self.compactDensity(for: height)
        return compactRows(density: density)
            .frame(maxWidth: .infinity, height: height, alignment: .topLeading)
    }

    @ViewBuilder
    private func compactRows(density: CompactDensity) -> some View {
        VStack(alignment: .leading, spacing: density.rowSpacing) {
            compactDistanceRow(density: density)

            switch density {
            case .regular:
                compactDetailRow(density: density, includesElevation: true)
                if let cue = compactCue {
                    compactCueRow(cue, density: density)
                }
            case .tight:
                compactDetailRow(density: density, includesElevation: true)
            case .minimal:
                compactClubRow(density: density)
            }

            compactConfidenceRow(density: density)
        }
        .frame(
            maxWidth: .infinity,
            minHeight: Self.compactContentHeight(for: density),
            alignment: .topLeading
        )
    }

    @ViewBuilder
    private func compactDistanceRow(density: CompactDensity) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: density == .regular ? 3 : 2) {
            if density == .minimal {
                if let center = displayCenterYd {
                    compactDistance(label: "中", yards: center, emphasis: true, density: density)
                } else if let front = displayFrontYd {
                    compactDistance(label: "前", yards: front, emphasis: true, density: density)
                } else if let back = displayBackYd {
                    compactDistance(label: "后", yards: back, emphasis: true, density: density)
                }
            } else {
                if let front = displayFrontYd {
                    compactDistance(label: "前", yards: front, emphasis: false, density: density)
                }
                if let center = displayCenterYd {
                    compactDistance(label: "中", yards: center, emphasis: true, density: density)
                        .layoutPriority(1)
                }
                if let back = displayBackYd {
                    compactDistance(label: "后", yards: back, emphasis: false, density: density)
                }
            }
        }
        .frame(
            maxWidth: .infinity,
            minHeight: density == .regular ? 42 : density == .tight ? 36 : 32,
            alignment: .top
        )
    }

    private func compactDetailRow(density: CompactDensity, includesElevation: Bool) -> some View {
        HStack(spacing: density == .regular ? 5 : 3) {
            if includesElevation, let delta = state.elevationDeltaM, abs(delta) >= 0.5 {
                let dy = WatchUnits.yards(delta)
                Label(
                    "\(dy > 0 ? "+" : "")\(dy)码",
                    systemImage: delta > 0 ? "arrow.up.right" : "arrow.down.right"
                )
                .foregroundStyle(delta > 0 ? AICaddieDesignTokens.bogey : AICaddieDesignTokens.par)
                .lineLimit(1)
                .minimumScaleFactor(0.55)
            }
            Spacer(minLength: 0)
            compactClubLabel(density: density)
        }
        .font(.system(size: density == .regular ? 13 : 12, weight: .black))
        .frame(height: density == .regular ? 20 : 18, alignment: .center)
    }

    private func compactClubRow(density: CompactDensity) -> some View {
        HStack {
            compactClubLabel(density: density)
        }
        .frame(height: 18, alignment: .leading)
    }

    private func compactClubLabel(density: CompactDensity) -> some View {
        Label(
            WatchClubDisplay.name(state.suggestedClub ?? state.selectedClub ?? "--"),
            systemImage: "scope"
        )
        .lineLimit(1)
        .minimumScaleFactor(density == .regular ? 0.65 : 0.55)
        .layoutPriority(1)
    }

    private func compactCueRow(_ cue: String, density: CompactDensity) -> some View {
        HStack(spacing: 4) {
            Image(systemName: "figure.golf")
            Text(cue)
                .lineLimit(1)
                .truncationMode(.tail)
                .minimumScaleFactor(0.55)
        }
        .font(.system(size: 13, weight: .bold))
        .foregroundStyle(AICaddieDesignTokens.strategyColor(state.strategyMode ?? "stock"))
        .frame(height: density == .regular ? 18 : 16, alignment: .leading)
    }

    private func compactConfidenceRow(density: CompactDensity) -> some View {
        HStack(spacing: 4) {
            Text(WatchCaddieText.confidence(state.caddieConfidence))
                .lineLimit(1)
                .minimumScaleFactor(0.6)
            if showsTargetStatus {
                Spacer(minLength: 0)
                Image(systemName: state.targetLatitude == nil || state.targetLongitude == nil ? "mappin.slash" : "mappin.and.ellipse")
                Text(state.targetLatitude == nil || state.targetLongitude == nil ? "待选旗位" : "旗位就绪")
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
            }
        }
        .font(.system(size: density == .minimal ? 11 : 12, weight: .black))
        .foregroundStyle(AICaddieDesignTokens.confidenceColor(state.caddieConfidence))
        .frame(height: density == .minimal ? 15 : 16, alignment: .leading)
    }

    private var compactCue: String? {
        let values = [state.nextShotPrompt, state.holePlanSummary, state.targetNote]
            .compactMap { value in
                guard let value, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
                return value
            }
        guard !values.isEmpty else { return nil }
        return values.prefix(2).joined(separator: " · ")
    }

    private func compactDistance(
        label: String,
        yards: Int,
        emphasis: Bool,
        density: CompactDensity
    ) -> some View {
        let centerSize: CGFloat = density == .regular ? 32 : density == .tight ? 28 : 24
        let sideSize: CGFloat = density == .regular ? 18 : density == .tight ? 16 : 15
        VStack(spacing: 0) {
            Text(WatchGeoMath.greenRangeText(yards))
                .font(.system(size: emphasis ? centerSize : sideSize, weight: .black, design: .rounded))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.55)
            Text(label)
                .font(.system(size: density == .minimal ? 9 : 10, weight: .black))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func greenPip(_ label: String, _ yards: Int) -> some View {
        VStack(spacing: 0) {
            Text(WatchGeoMath.greenRangeText(yards))
                .font(.system(size: 23, weight: .black, design: .rounded)).monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.55)
            Text(label).font(.system(size: 13, weight: .black)).foregroundStyle(.secondary)
        }
    }
}
