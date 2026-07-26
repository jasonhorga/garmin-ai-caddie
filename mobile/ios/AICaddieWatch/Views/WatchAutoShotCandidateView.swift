import SwiftUI

/// Explicit confirmation for an opt-in AutoShot observation. Neither button asks the player to judge
/// detector confidence: accept continues into the normal club/location flow; reject records nothing.
public struct WatchAutoShotCandidateView: View {
    public let onAccept: () -> Void
    public let onReject: () -> Void

    public init(
        onAccept: @escaping () -> Void = {},
        onReject: @escaping () -> Void = {}
    ) {
        self.onAccept = onAccept
        self.onReject = onReject
    }

    public var body: some View {
        VStack(spacing: 8) {
            Text("检测到一杆")
                .font(.headline.weight(.bold))
            Text("位置已暂存\n确认后才会记入")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button("记这一杆", action: onAccept)
                .buttonStyle(.borderedProminent)
                .tint(.green)
                .accessibilityIdentifier("autoshot.accept")

            Button("不是击球", role: .cancel, action: onReject)
                .buttonStyle(.bordered)
                .accessibilityIdentifier("autoshot.reject")
        }
        .padding(8)
    }
}
