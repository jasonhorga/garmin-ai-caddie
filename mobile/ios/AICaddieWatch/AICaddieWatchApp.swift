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
                    clubs: defaultClubs,
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

    private var defaultClubs: [String] {
        ["1D", "3W", "5I", "7I", "9I", "PW", "54", "58", "Putter"]
    }

    private func sendQuickInputEvent(_ event: WatchInputEvent) {
        try? syncClient.sendQuickInputEvent(event)
    }
}
