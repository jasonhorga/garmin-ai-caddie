import SwiftUI

@main
public struct AICaddieWatchApp: App {
    @StateObject private var syncClient = WatchSyncClient()
    @StateObject private var roundModel = WatchRoundModel()

    public init() {}

    public var body: some Scene {
        WindowGroup {
            content
                // Keep the standalone round able to sync: adopt the backend config the phone delivers.
                .onChange(of: syncClient.config, initial: true) { _, newConfig in
                    roundModel.config = newConfig
                }
        }
    }

    @ViewBuilder
    private var content: some View {
        if roundModel.round != nil {
            // round-12 P3.3: a standalone round in progress takes over the whole watch.
            WatchRoundContainerView(model: roundModel)
        } else if let state = syncClient.currentState {
            // phone-coordinated companion glance (legacy single-hole push).
            WatchHoleView(
                state: state,
                clubs: state.availableClubNames,
                queuedEventCount: syncClient.queuedEventCount,
                phoneReachable: syncClient.phoneReachable,
                lastPhoneAcceptedAt: syncClient.lastPhoneAcceptedAt,
                onEvent: sendQuickInputEvent
            )
        } else {
            WatchStartView(
                phoneReachable: syncClient.phoneReachable,
                onStartPractice: { roundModel.startPracticeRound() }
            )
        }
    }

    private func sendQuickInputEvent(_ event: WatchInputEvent) {
        try? syncClient.sendQuickInputEvent(event)
    }
}
