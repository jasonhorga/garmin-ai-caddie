import SwiftUI

public struct WatchHoleView: View {
    public let state: WatchRoundState
    public let clubs: [String]
    public let queuedEventCount: Int
    public let phoneReachable: Bool
    public let lastPhoneAcceptedAt: String?
    public let onEvent: (WatchInputEvent) -> Void

    public init(
        state: WatchRoundState,
        clubs: [String],
        queuedEventCount: Int = 0,
        phoneReachable: Bool = false,
        lastPhoneAcceptedAt: String? = nil,
        onEvent: @escaping (WatchInputEvent) -> Void = { _ in }
    ) {
        self.state = state
        self.clubs = clubs
        self.queuedEventCount = queuedEventCount
        self.phoneReachable = phoneReachable
        self.lastPhoneAcceptedAt = lastPhoneAcceptedAt
        self.onEvent = onEvent
    }

    public var body: some View {
        NavigationStack {
            List {
                VStack(alignment: .leading, spacing: 4) {
                    Text("第\(state.hole)洞")
                        .font(.title2.weight(.bold))
                    Text("Par \(state.par)")
                        .foregroundStyle(.secondary)
                    if let distanceM = state.distanceM {
                        Text("\(WatchUnits.yards(distanceM)) 码")
                            .font(.headline.monospacedDigit())
                    }
                    if let targetNote = state.targetNote {
                        Text(targetNote)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Text(state.targetLatitude == nil || state.targetLongitude == nil ? "等待手机更新距离" : "\(WatchCaddieText.targetNoun(state.targetKind))已就绪")
                        .font(.caption2)
                        .foregroundStyle(state.targetLatitude == nil || state.targetLongitude == nil ? AICaddieDesignTokens.confidenceColor("low") : .secondary)
                }
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 4) {
                        Image(systemName: phoneReachable ? "iphone.radiowaves.left.and.right" : "iphone.slash")
                        Text(phoneReachable ? "手机已连" : "手机未连")
                    }
                    if queuedEventCount > 0 {
                        Text("待传 \(queuedEventCount)")
                    } else if lastPhoneAcceptedAt != nil {
                        Text("已同步")
                    }
                }
                .font(.caption2)
                .foregroundStyle(queuedEventCount > 0 ? AICaddieDesignTokens.confidenceColor("low") : .secondary)
                WatchCaddieGlanceView(state: state)
                if !state.caddieOptions.isEmpty {
                    NavigationLink("球童打法") {
                        WatchCaddieOptionsView(
                            hole: state.hole,
                            par: state.par,
                            options: state.caddieOptions,
                            recommendedId: state.offlineOptionId,
                            route: state.holeMap?.route ?? []
                        )
                    }
                }
                if !state.hazards.isEmpty {
                    NavigationLink("障碍") {
                        ScrollView { WatchHazardView(hazards: state.hazards).padding(8) }
                    }
                }
                NavigationLink("输入") {
                    WatchInputView(state: state, clubs: clubs, onEvent: onEvent)
                }
            }
            .navigationTitle("AI Caddie")
        }
    }
}
