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
        CatalogClub(zhName: "一号小鸡腿", category: .hybrid),
        CatalogClub(zhName: "二号小鸡腿", category: .hybrid),
        CatalogClub(zhName: "三号小鸡腿", category: .hybrid),
        CatalogClub(zhName: "四号小鸡腿", category: .hybrid),
        CatalogClub(zhName: "五号小鸡腿", category: .hybrid),
        CatalogClub(zhName: "六号小鸡腿", category: .hybrid),
        CatalogClub(zhName: "一号铁", category: .iron),
        CatalogClub(zhName: "二号铁", category: .iron),
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

/// Garmin clubType enum (the `value` from `/club/types`) → the app's Chinese catalog name.
/// AUTHORITATIVE scheme: Driver=1 … Putter=23. (Do NOT confuse with the backend's older guessed
/// `CLUB_TYPE_NAME` table, which had Putter=18.) The player's custom degree names (50/54/58) are
/// handled separately via `zhClubName(customName)`, so this only covers the standard fallbacks.
public let garminClubTypeZh: [Int: String] = [
    1: "一号木", 2: "三号木", 3: "五号木",
    4: "一号小鸡腿", 5: "二号小鸡腿", 6: "三号小鸡腿", 7: "四号小鸡腿", 8: "五号小鸡腿", 9: "六号小鸡腿",
    10: "一号铁", 11: "二号铁", 12: "三号铁", 13: "四号铁", 14: "五号铁", 15: "六号铁", 16: "七号铁", 17: "八号铁", 18: "九号铁",
    19: "P 杆", 20: "A 杆", 21: "S 杆", 22: "L 杆",
    23: "推杆",
]

/// The player's bag, persisted locally (UserDefaults). The live picker / caddie use `effectiveBag()`:
/// a manual override (`bag()`) wins, else the auto-fetched real Garmin bag (`realBag()`); `nil` from
/// both means not-yet-known → callers fall back to clubs that appear in the player's shot history.
public enum ClubBagStore {
    private static let key = "ai-caddie.club-bag-v1"
    private static let realKey = "ai-caddie.club-bag-real-v1"

    public static func bag() -> Set<String>? {
        decodeBag(key)
    }

    public static func save(_ bag: Set<String>) {
        encodeBag(bag, into: key)
    }

    /// Drop the manual override so the player snaps back to the auto `realBag` default. Used by the
    /// 「用 Garmin 球包重置」 action when a stale manual selection no longer matches the real bag.
    public static func clearManual() {
        UserDefaults.standard.removeObject(forKey: key)
    }

    /// The real Garmin bag, auto-fetched from the backend and cached. Used as the default everywhere
    /// the player hasn't manually overridden their bag. Refreshed whenever `refreshRealClubBag` runs.
    public static func realBag() -> Set<String>? {
        decodeBag(realKey)
    }

    public static func saveRealBag(_ bag: Set<String>) {
        encodeBag(bag, into: realKey)
    }

    /// Manual override wins; otherwise the real Garmin bag. `nil` if neither is known yet.
    public static func effectiveBag() -> Set<String>? {
        bag() ?? realBag()
    }

    private static func decodeBag(_ storageKey: String) -> Set<String>? {
        guard let data = UserDefaults.standard.data(forKey: storageKey),
              let list = try? JSONDecoder().decode([String].self, from: data) else {
            return nil
        }
        return list.isEmpty ? nil : Set(list)
    }

    private static func encodeBag(_ bag: Set<String>, into storageKey: String) {
        guard let data = try? JSONEncoder().encode(Array(bag).sorted()) else { return }
        UserDefaults.standard.set(data, forKey: storageKey)
    }
}

/// Resolve a fetched bag response to the app's Chinese catalog names (in-use clubs only).
/// Custom names win (`zhClubName` handles "Pw"/"Aw"/"50"/"54"/"58"); else the authoritative
/// `garminClubTypeZh[clubTypeId]`; else a last-ditch `zhClubName(typeName)`. Only names that exist in
/// `ClubCatalog` are kept, so a bag club always lines up with a checkable catalog row.
public func resolvedBagNames(_ response: ClubBagResponse) -> Set<String> {
    var names = Set<String>()
    for club in response.clubs where !club.deleted && !club.retired {
        if let custom = club.customName?.trimmingCharacters(in: .whitespaces), !custom.isEmpty {
            let zh = zhClubName(custom)
            if ClubCatalog.names.contains(zh) { names.insert(zh); continue }
        }
        if let zh = garminClubTypeZh[club.clubTypeId], ClubCatalog.names.contains(zh) {
            names.insert(zh); continue
        }
        if let typeName = club.typeName {
            let zh = zhClubName(typeName)
            if ClubCatalog.names.contains(zh) { names.insert(zh) }
        }
    }
    return names
}

/// Fetch the player's real Garmin bag from the backend and cache it as `realBag` (the auto-default).
/// Returns the resolved catalog names, or `nil` on failure / empty / unconfigured backend. Safe to
/// call from multiple screens; failures are swallowed (the app falls back to shot-history clubs).
@discardableResult
public func refreshRealClubBag(apiBaseURL: URL?, adminToken: String?) async -> Set<String>? {
    guard let apiBaseURL else { return nil }
    guard let response = try? await SyncClient(baseURL: apiBaseURL, adminToken: adminToken).fetchClubBag(),
          response.found else { return nil }
    let names = resolvedBagNames(response)
    guard !names.isEmpty else { return nil }
    ClubBagStore.saveRealBag(names)
    return names
}
