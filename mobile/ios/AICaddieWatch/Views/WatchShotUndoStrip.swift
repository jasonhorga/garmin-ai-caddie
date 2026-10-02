import SwiftUI

/// B6 测到挥杆 (README §3): instead of asking 刚才用哪支杆？, the detected shot flashes as "第 N 杆" at
/// the bottom of the screen; tapping it undoes the shot. The club is inferred later (B7).
struct WatchShotUndoStrip: View {
    let text: String
    var onUndo: () -> Void = {}

    var body: some View {
        Button(action: onUndo) {
            HStack(spacing: 4) {
                Text(text).font(.system(size: 15, weight: .semibold)).monospacedDigit()
                Image(systemName: "arrow.uturn.backward").font(.system(size: 12, weight: .semibold))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Capsule().fill(Color.black.opacity(0.78)))
        }
        .buttonStyle(.plain)
        .padding(.bottom, 4)
        .accessibilityLabel("\(text)，点按撤销")
        .accessibilityIdentifier("watch-shot-undo")
    }
}
