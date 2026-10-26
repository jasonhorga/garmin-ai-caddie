/// Selects the reference for front/middle/back green distances on both phone and Watch.
/// GPS qualification stays with each device; fallback preserves its existing unavailable/static UI.
public enum GreenRangeOrigin: Equatable {
    case tee
    case liveGPS
    case fallback

    public static func resolve(
        recordedShotCount: Int,
        isPreparing: Bool,
        hasQualifiedFix: Bool
    ) -> GreenRangeOrigin {
        if isPreparing || recordedShotCount == 0 { return .tee }
        return hasQualifiedFix ? .liveGPS : .fallback
    }
}
