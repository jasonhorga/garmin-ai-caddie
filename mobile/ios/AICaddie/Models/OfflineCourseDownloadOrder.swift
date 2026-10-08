import Foundation

/// The order a live round's all-hole download visits its physical holes: the hole being played
/// first, then the holes still ahead in round order, then the ones already played. Sorting local
/// hole numbers instead sent a back-nine start (or a relaunch on hole 7) to fetch hole 1 first.
public enum OfflineCourseDownloadOrder {
    public struct Hole: Equatable {
        public let number: Int
        public let key: String

        public init(number: Int, key: String) {
            self.number = number
            self.key = key
        }
    }

    /// Rank by physical-hole key (0 = fetch first). `roundHoles` is in round order; an active hole
    /// that is not in the round (nil, finished, stale) keeps plain round order. A key repeated by a
    /// duplicate loop keeps its earliest rank.
    public static func ranks(roundHoles: [Hole], activeHole: Int?) -> [String: Int] {
        let start = activeHole.flatMap { active in
            roundHoles.firstIndex(where: { $0.number == active })
        } ?? 0
        var ranks: [String: Int] = [:]
        for offset in 0..<roundHoles.count {
            let hole = roundHoles[(start + offset) % roundHoles.count]
            if ranks[hole.key] == nil {
                ranks[hole.key] = offset
            }
        }
        return ranks
    }
}
