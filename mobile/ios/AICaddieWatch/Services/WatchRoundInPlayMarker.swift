import Foundation

/// Remembers that a round was in play a moment ago (owner request 2026-10-12): an app quit by
/// accident, or stopped by the system or an update, comes straight back to the round instead of
/// asking to resume. A round set aside as idle, or one left for longer, still asks.
public struct WatchRoundInPlayMarker {
    public static let resumeWindow: TimeInterval = 30 * 60

    private static let roundKey = "watch.inPlay.roundId"
    private static let atKey = "watch.inPlay.at"
    /// nil keeps nothing (tests and previews): every relaunch asks to resume.
    private let defaults: UserDefaults?

    public init(defaults: UserDefaults?) {
        self.defaults = defaults
    }

    public func mark(roundId: String, at now: Date = Date()) {
        defaults?.set(roundId, forKey: Self.roundKey)
        defaults?.set(now.timeIntervalSince1970, forKey: Self.atKey)
    }

    public func clear() {
        defaults?.removeObject(forKey: Self.roundKey)
        defaults?.removeObject(forKey: Self.atKey)
    }

    public func wasInPlay(roundId: String, now: Date = Date()) -> Bool {
        guard let defaults,
              defaults.string(forKey: Self.roundKey) == roundId,
              let at = defaults.object(forKey: Self.atKey) as? Double else { return false }
        let age = now.timeIntervalSince1970 - at
        return age >= 0 && age <= Self.resumeWindow
    }
}
