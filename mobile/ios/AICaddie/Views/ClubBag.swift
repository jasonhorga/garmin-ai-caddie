import Foundation

/// Garmin-standard club taxonomy + the player's configured bag.
/// The catalog is the full set a player COULD carry, grouped like Garmin's club setup. The player's
/// bag is the subset they actually own — the live picker and the caddie only use the bag, so clubs
/// the player doesn't have (a stray "二号小鸡腿" from one mis-tagged shot) never show up.
/// Catalog `zhName`s match `zhClubName(...)` output exactly so bag membership filters cleanly.

public enum ClubCategory: String, CaseIterable {
    case wood = "木杆"
    case hybrid = "混合杆"
    case iron = "铁杆"
    case wedge = "挖起杆"
    case putter = "推杆"
}

public struct CatalogClub: Identifiable, Hashable {
    public var id: String { zhName }
    public let zhName: String
    public let category: ClubCategory

    public init(zhName: String, category: ClubCategory) {
        self.zhName = zhName
        self.category = category
    }
}

public enum ClubCatalog {
    public static let all: [CatalogClub] = [
        CatalogClub(zhName: "一号木", category: .wood),
        CatalogClub(zhName: "三号木", category: .wood),
        CatalogClub(zhName: "五号木", category: .wood),
        CatalogClub(zhName: "七号木", category: .wood),
        CatalogClub(zhName: "二号小鸡腿", category: .hybrid),
        CatalogClub(zhName: "三号小鸡腿", category: .hybrid),
        CatalogClub(zhName: "四号小鸡腿", category: .hybrid),
        CatalogClub(zhName: "五号小鸡腿", category: .hybrid),
        CatalogClub(zhName: "三号铁", category: .iron),
        CatalogClub(zhName: "四号铁", category: .iron),
        CatalogClub(zhName: "五号铁", category: .iron),
        CatalogClub(zhName: "六号铁", category: .iron),
        CatalogClub(zhName: "七号铁", category: .iron),
        CatalogClub(zhName: "八号铁", category: .iron),
        CatalogClub(zhName: "九号铁", category: .iron),
        CatalogClub(zhName: "P 杆", category: .wedge),
        CatalogClub(zhName: "A 杆", category: .wedge),
        CatalogClub(zhName: "S 杆", category: .wedge),
        CatalogClub(zhName: "L 杆", category: .wedge),
        CatalogClub(zhName: "50° 挖起杆", category: .wedge),
        CatalogClub(zhName: "52° 挖起杆", category: .wedge),
        CatalogClub(zhName: "54° 挖起杆", category: .wedge),
        CatalogClub(zhName: "56° 挖起杆", category: .wedge),
        CatalogClub(zhName: "58° 挖起杆", category: .wedge),
        CatalogClub(zhName: "60° 挖起杆", category: .wedge),
        CatalogClub(zhName: "推杆", category: .putter),
    ]

    public static func byCategory(_ category: ClubCategory) -> [CatalogClub] {
        all.filter { $0.category == category }
    }

    /// Every catalog name — used to keep only recognised clubs when deriving a default bag.
    public static let names: Set<String> = Set(all.map(\.zhName))
}

/// The player's bag, persisted locally (UserDefaults). `nil` = not configured yet → the live picker
/// falls back to clubs that appear in the player's shot history.
public enum ClubBagStore {
    private static let key = "ai-caddie.club-bag-v1"

    public static func bag() -> Set<String>? {
        guard let data = UserDefaults.standard.data(forKey: key),
              let list = try? JSONDecoder().decode([String].self, from: data) else {
            return nil
        }
        return list.isEmpty ? nil : Set(list)
    }

    public static func save(_ bag: Set<String>) {
        guard let data = try? JSONEncoder().encode(Array(bag).sorted()) else { return }
        UserDefaults.standard.set(data, forKey: key)
    }
}
