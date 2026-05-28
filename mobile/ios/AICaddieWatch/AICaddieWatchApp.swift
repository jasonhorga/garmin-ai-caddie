import SwiftUI

@main
public struct AICaddieWatchApp: App {
    @StateObject private var syncClient = WatchSyncClient()

    public init() {}

    public var body: some Scene {
        WindowGroup {
            if let state = syncClient.currentState {
                WatchHoleView(
                    state: state,
                    clubs: state.availableClubNames,
                    queuedEventCount: syncClient.queuedEventCount,
                    phoneReachable: syncClient.phoneReachable,
                    lastPhoneAcceptedAt: syncClient.lastPhoneAcceptedAt,
                    onEvent: sendQuickInputEvent
                )
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    Text("AI Caddie")
                        .font(.headline)
                    Text("Waiting for iPhone")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func sendQuickInputEvent(_ event: WatchInputEvent) {
        try? syncClient.sendQuickInputEvent(event)
    }
}
