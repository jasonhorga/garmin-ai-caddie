import SwiftUI

public struct WatchHoleView: View {
    public let state: WatchRoundState
    public let clubs: [String]
    public let onEvent: (WatchInputEvent) -> Void

    public init(state: WatchRoundState, clubs: [String], onEvent: @escaping (WatchInputEvent) -> Void = { _ in }) {
        self.state = state
        self.clubs = clubs
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
                }
                WatchCaddieGlanceView(state: state)
                NavigationLink("Input") {
                    WatchInputView(state: state, clubs: clubs, onEvent: onEvent)
                }
            }
            .navigationTitle("AI Caddie")
        }
    }
}
