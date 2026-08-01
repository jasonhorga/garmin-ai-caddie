import CoreGraphics

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
