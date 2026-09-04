import Foundation

/// 手表端距离统一按「码 (yards)」显示与输入;数据 / 事件内部仍是米(Garmin 原生 `distanceM`),
/// 只在显示 / 输入边界换算,与 iPhone 端 (`yardsText(fromMetres:)`) 及球童速览一致。
/// 用户明确要求:全站用码、不用米。1 码 = 0.9144 米。
enum WatchUnits {
    static func yards(_ metres: Double) -> Int { Int((metres * 1.09361).rounded()) }
    static func metres(fromYards yards: Int) -> Double { Double(yards) * 0.9144 }

    /// Plays-like state stays in metres; only the Watch presentation converts the slope delta.
    /// Keeping this arithmetic here prevents a yard display value from ever receiving metres.
    static func playsLikeMetres(distanceMetres: Double?, elevationDeltaMetres: Double?) -> Double? {
        guard let distanceMetres, distanceMetres.isFinite,
              let elevationDeltaMetres, elevationDeltaMetres.isFinite else { return nil }
        return distanceMetres + elevationDeltaMetres
    }
}
