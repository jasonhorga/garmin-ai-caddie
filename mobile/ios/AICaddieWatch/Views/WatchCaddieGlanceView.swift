import SwiftUI

public struct WatchCaddieGlanceView: View {
    public let state: WatchRoundState

    public init(state: WatchRoundState) {
        self.state = state
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: "scope")
                Text(state.selectedClub ?? "--")
                    .font(.headline)
            }
            Text(state.caddieConfidence)
                .font(.caption)
                .foregroundStyle(confidenceColor)
        }
    }

    private var confidenceColor: Color {
        switch state.caddieConfidence {
        case "high":
            return .green
        case "medium":
            return .yellow
        default:
            return .red
        }
    }
}
