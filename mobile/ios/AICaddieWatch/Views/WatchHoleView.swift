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
                    Text("H\(state.hole)")
                        .font(.title2.weight(.bold))
                    Text("Par \(state.par)")
                        .foregroundStyle(.secondary)
                    if let distanceM = state.distanceM {
                        Text("\(Int(distanceM))m")
                            .font(.headline.monospacedDigit())
                    }
                    if let targetNote = state.targetNote {
                        Text(targetNote)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Text(state.targetLatitude == nil || state.targetLongitude == nil ? "Pin from iPhone needed" : "\(state.targetKind ?? "target") set")
                        .font(.caption2)
                        .foregroundStyle(state.targetLatitude == nil || state.targetLongitude == nil ? AICaddieDesignTokens.confidenceColor("low") : .secondary)
                }
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 4) {
                        Image(systemName: phoneReachable ? "iphone.radiowaves.left.and.right" : "iphone.slash")
                        Text(phoneReachable ? "iPhone online" : "iPhone offline")
                    }
                    if queuedEventCount > 0 {
                        Text("Queue \(queuedEventCount)")
                    } else if lastPhoneAcceptedAt != nil {
                        Text("Synced")
                    }
                }
                .font(.caption2)
                .foregroundStyle(queuedEventCount > 0 ? AICaddieDesignTokens.confidenceColor("low") : .secondary)
                WatchCaddieGlanceView(state: state)
                if !state.caddieOptions.isEmpty {
                    NavigationLink("球童打法") {
                        ScrollView { WatchCaddieOptionsView(options: state.caddieOptions, recommendedId: state.offlineOptionId).padding(8) }
                    }
                }
                if !state.hazards.isEmpty {
                    NavigationLink("障碍") {
                        ScrollView { WatchHazardView(hazards: state.hazards).padding(8) }
                    }
                }
                NavigationLink("Input") {
                    WatchInputView(state: state, clubs: clubs, onEvent: onEvent)
                }
            }
            .navigationTitle("AI Caddie")
        }
    }
}
