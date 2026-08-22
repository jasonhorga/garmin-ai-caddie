import CoreGraphics
import SwiftUI

/// Garmin has a hardware Back key; on Apple Watch the equivalent shallow-instrument exit is a
/// deliberate right swipe that begins at the left bezel. Keeping the predicate in one place lets
/// compact screens omit a space-consuming inline Back row without making them dead ends.
enum WatchEdgeBackGesture {
    static func shouldTrigger(startX: CGFloat, translation: CGSize) -> Bool {
        startX <= 28
            && translation.width >= 60
            && abs(translation.height) < 50
    }
}

/// S70 has a physical Back key. Apple Watch does not, so every shallow golf instrument keeps a
/// visible equivalent while retaining the bezel swipe as a shortcut. The glyph stays visually small;
/// the transparent 44-point frame is the actual target.
struct WatchInstrumentBackButton: View {
    let accessibilityLabel: String
    let onBack: () -> Void

    init(
        accessibilityLabel: String = "返回",
        onBack: @escaping () -> Void
    ) {
        self.accessibilityLabel = accessibilityLabel
        self.onBack = onBack
    }

    var body: some View {
        Button(action: onBack) {
            Image(systemName: "chevron.backward")
                .font(.system(size: 14, weight: .heavy))
                .foregroundStyle(.white)
                .frame(width: 32, height: 32)
                .background(Color.black.opacity(0.68), in: Circle())
                .overlay(Circle().stroke(.white.opacity(0.28), lineWidth: 0.8))
                .frame(
                    width: WatchDisplayGeometry.instrumentControlSize,
                    height: WatchDisplayGeometry.instrumentControlSize
                )
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(accessibilityLabel)
    }
}

/// Compact, clock-safe header used by list-like Watch instruments. It gives Back a discoverable
/// target without turning it into another full-width row.
struct WatchInstrumentHeader: View {
    let title: String
    let backLabel: String
    let reserveSystemTime: Bool
    let onBack: () -> Void

    init(
        _ title: String,
        backLabel: String = "返回",
        reserveSystemTime: Bool = true,
        onBack: @escaping () -> Void
    ) {
        self.title = title
        self.backLabel = backLabel
        self.reserveSystemTime = reserveSystemTime
        self.onBack = onBack
    }

    var body: some View {
        HStack(spacing: 0) {
            WatchInstrumentBackButton(accessibilityLabel: backLabel, onBack: onBack)
            Text(title)
                .font(.system(size: 17, weight: .heavy))
                .lineLimit(1)
                .minimumScaleFactor(0.85)
            Spacer(minLength: reserveSystemTime ? 46 : 4)
        }
        .frame(height: 44)
    }
}
