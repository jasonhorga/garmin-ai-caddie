import SwiftUI

enum WatchCurrentHoleShotsLayout {
    /// This scroll surface cannot hide watchOS's clock. Start its own header below that lane rather
    /// than placing “H7 · P4” beside a seemingly unrelated system time.
    static let systemTimeTopClearance: CGFloat = 18
}

/// The shallow current-hole correction surface locked by D10/L11. It shows only facts already recorded
/// on the Watch and reuses the existing manual-shot path for a missed stroke. Full position, ordering,
/// lie and historical cross-hole editing remain on iPhone.
public struct WatchCurrentHoleShotsView: View {
    public let hole: Int
    public let par: Int
    public let shots: [WatchRecordedShot]
    public let latestShotDistanceM: Double?
    public let canAddShot: Bool
    public let onAddShot: () -> Void
    public let onBack: () -> Void

    public init(
        hole: Int,
        par: Int,
        shots: [WatchRecordedShot],
        latestShotDistanceM: Double? = nil,
        canAddShot: Bool,
        onAddShot: @escaping () -> Void = {},
        onBack: @escaping () -> Void = {}
    ) {
        self.hole = hole
        self.par = par
        self.shots = shots
        self.latestShotDistanceM = latestShotDistanceM
        self.canAddShot = canAddShot
        self.onAddShot = onAddShot
        self.onBack = onBack
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            WatchInstrumentHeader(
                "H\(hole) · 本洞击球",
                backLabel: "返回菜单",
                onBack: onBack
            )

            if shots.isEmpty {
                Text("本洞还没有记录击球")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 12)
            } else {
                ForEach(shots) { shot in
                    HStack(spacing: 7) {
                        Text("\(shot.number)")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.secondary)
                            .frame(width: 16, alignment: .leading)
                        Text(shotLabel(shot))
                            .font(.system(size: 13, weight: .semibold))
                            .lineLimit(1)
                        Spacer(minLength: 4)
                        Text(distanceLabel(shot))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .monospacedDigit()
                    }
                    .padding(.vertical, 5)
                    .overlay(alignment: .bottom) { Divider() }
                }
            }

            Text("推杆在洞末确认")
                .font(.caption2)
                .foregroundStyle(.tertiary)

            Spacer(minLength: 8)

            Button(action: onAddShot) {
                Text(canAddShot ? "+ 补记一杆" : "等待 GPS 后补杆")
                    .font(.system(size: 11, weight: .bold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 7)
                    .foregroundStyle(canAddShot ? Color.white : Color.secondary)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(canAddShot ? AICaddieDesignTokens.par : Color.white.opacity(0.08))
                    )
            }
            .buttonStyle(.plain)
            .disabled(!canAddShot)
            .accessibilityHint(canAddShot ? "保存当前位置并选择实际球杆" : "等待手表取得 GPS 位置")
        }
        .frame(minHeight: 180, alignment: .top)
        .padding(.horizontal, 8)
        .padding(.top, WatchCurrentHoleShotsLayout.systemTimeTopClearance)
        .padding(.bottom, 8)
        .simultaneousGesture(
            DragGesture(minimumDistance: 24)
                .onEnded { value in
                    guard WatchEdgeBackGesture.shouldTrigger(
                        startX: value.startLocation.x,
                        translation: value.translation
                    ) else { return }
                    onBack()
                }
        )
        .accessibilityAction(named: Text("返回菜单"), onBack)
        .persistentSystemOverlays(.hidden)
    }

    private func shotLabel(_ shot: WatchRecordedShot) -> String {
        let club = shot.clubName.map(WatchClubDisplay.shortCode) ?? "未选球杆"
        return shot.number == 1 && shot.shotType == "tee" ? "开球 \(club)" : club
    }

    private func distanceLabel(_ shot: WatchRecordedShot) -> String {
        let metres = shot.distanceToNextM ?? (shot.id == shots.last?.id ? latestShotDistanceM : nil)
        guard let metres else { return "位置已记" }
        let yards = WatchUnits.yards(metres)
        guard let usefulYards = WatchGeoMath.usefulGolfYards(yards) else { return "—" }
        return "\(usefulYards) 码"
    }
}
