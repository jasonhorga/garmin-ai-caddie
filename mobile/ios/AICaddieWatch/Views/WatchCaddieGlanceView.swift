import SwiftUI

public struct WatchCaddieGlanceView: View {
    public let state: WatchRoundState
    public let frontYd: Int?
    public let centerYd: Int?
    public let backYd: Int?
    public let lastShotDistanceM: Double?

    public init(
        state: WatchRoundState,
        frontYd: Int? = nil,
        centerYd: Int? = nil,
        backYd: Int? = nil,
        lastShotDistanceM: Double? = nil
    ) {
        self.state = state
        self.frontYd = frontYd
        self.centerYd = centerYd
        self.backYd = backYd
        self.lastShotDistanceM = lastShotDistanceM
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
        VStack(alignment: .leading, spacing: 4) {
            // round-13 LIVE: 前/中/后果岭(F/M/B)+ 坡度补偿 + 距上一杆 (码). Each guarded so a
            // hole without geometry (fields nil) shows nothing rather than "0" noise.
            if displayCenterYd != nil || displayFrontYd != nil || displayBackYd != nil {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    if let front = displayFrontYd { greenPip("前", front) }
                    if let center = displayCenterYd {
                        VStack(spacing: 0) {
                            Text(WatchGeoMath.greenRangeText(center))
                                .font(.system(size: 34, weight: .bold, design: .rounded)).monospacedDigit()
                                .foregroundStyle(AICaddieDesignTokens.bogey)
                                .lineLimit(1)
                                .minimumScaleFactor(0.55)
                            Text("中").font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    if let back = displayBackYd { greenPip("后", back) }
                }
                if [displayFrontYd, displayCenterYd, displayBackYd]
                    .contains(where: WatchGeoMath.isBeyondUsefulGreenRange) {
                    Text("离本洞较远")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
            }
            if let delta = state.elevationDeltaM, abs(delta) >= 0.5 {
                let dy = WatchUnits.yards(delta)
                HStack(spacing: 3) {
                    Image(systemName: delta > 0 ? "arrow.up.right" : "arrow.down.right")
                    Text("坡度 \(dy > 0 ? "+" : "")\(dy) 码")
                }
                .font(.caption2)
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
                .font(.caption2)
                .foregroundStyle(.secondary)
            }
            HStack {
                Image(systemName: "scope")
                Text(WatchClubDisplay.name(state.suggestedClub ?? state.selectedClub ?? "--"))
                    .font(.headline)
            }
            if let targetNote = state.targetNote {
                Text(targetNote)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if showsTargetStatus {
                HStack(spacing: 4) {
                    Image(systemName: state.targetLatitude == nil || state.targetLongitude == nil ? "mappin.slash" : "mappin.and.ellipse")
                    Text(state.targetLatitude == nil || state.targetLongitude == nil ? "待选旗位" : "\(WatchCaddieText.targetNoun(state.targetKind))就绪")
                        .lineLimit(1)
                }
                .font(.caption2)
                .foregroundStyle(state.targetLatitude == nil || state.targetLongitude == nil ? AICaddieDesignTokens.confidenceColor("low") : .secondary)
            }
            if let nextShotPrompt = state.nextShotPrompt {
                HStack(spacing: 4) {
                    Image(systemName: "figure.golf")
                    Text(nextShotPrompt)
                        .lineLimit(2)
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(AICaddieDesignTokens.strategyColor("stock"))
            }
            if let holePlanSummary = state.holePlanSummary {
                HStack(spacing: 4) {
                    Image(systemName: "point.topleft.down.curvedto.point.bottomright.up")
                    Text(holePlanSummary)
                        .lineLimit(2)
                }
                .font(.caption2.weight(.semibold))
                .foregroundStyle(AICaddieDesignTokens.strategyColor(state.strategyMode ?? "stock"))
            }
            // De-engineered: the watch glance shows the caddie call + confidence below, not the raw
            // evidence / missing-data provenance strings. (Those fields are still carried in the
            // model for the phone — just no longer surfaced on the watch.)
            Text(WatchCaddieText.confidence(state.caddieConfidence))
                .font(.caption)
                .foregroundStyle(AICaddieDesignTokens.confidenceColor(state.caddieConfidence))
        }
    }

    private func greenPip(_ label: String, _ yards: Int) -> some View {
        VStack(spacing: 0) {
            Text(WatchGeoMath.greenRangeText(yards))
                .font(.headline.weight(.semibold)).monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.55)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
    }
}
