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

    /// Catalog default carries (metres) — the server's ``club_catalog`` ``defaultDistanceM``, keyed
    /// by catalog name. A selected club with neither shot history nor a typed carry uses this; a club
    /// without a default stays out rather than getting an invented distance.
    public static let defaultDistanceM: [String: Double] = [
        "一号木": 200, "三号木": 171, "三号小鸡腿": 159,
        "五号铁": 146, "六号铁": 132, "七号铁": 128, "八号铁": 122, "九号铁": 114,
        "P 杆": 102, "A 杆": 84, "50° 挖起杆": 53, "54° 挖起杆": 52, "58° 挖起杆": 42,
    ]
}

/// Garmin clubType enum (the `value` from `/club/types`) → the app's Chinese catalog name.
/// AUTHORITATIVE scheme: Driver=1 … Putter=23. The backend's `CLUB_TYPE_NAME` and club catalog use
/// this same table. The player's custom degree names (50/54/58) are handled separately via
/// `zhClubName(customName)`, so this only covers the standard fallbacks.
public let garminClubTypeZh: [Int: String] = [
    1: "一号木", 2: "三号木", 3: "五号木",
    4: "一号小鸡腿", 5: "二号小鸡腿", 6: "三号小鸡腿", 7: "四号小鸡腿", 8: "五号小鸡腿", 9: "六号小鸡腿",
    10: "一号铁", 11: "二号铁", 12: "三号铁", 13: "四号铁", 14: "五号铁", 15: "六号铁", 16: "七号铁", 17: "八号铁", 18: "九号铁",
    19: "P 杆", 20: "A 杆", 21: "S 杆", 22: "L 杆",
    23: "推杆",
]

/// The app's Chinese catalog name → the backend's club token vocabulary, the reverse of the on-device
/// resolution. Bridges the iOS catalog (`CatalogClub.zhName`) to the manual-bag PUT payload tokens so
/// the bag the player checks here persists server-side. Keys MUST equal `CatalogClub.zhName` byte for
/// byte (mind the spaces in "P 杆" / "50° 挖起杆"); values are the backend tokens (see club_catalog).
public let zhNameToBackendToken: [String: String] = [
    "一号木": "driver", "三号木": "wood3", "五号木": "wood5", "七号木": "wood7",
    "一号小鸡腿": "hybrid1", "二号小鸡腿": "hybrid2", "三号小鸡腿": "hybrid3",
    "四号小鸡腿": "hybrid4", "五号小鸡腿": "hybrid5", "六号小鸡腿": "hybrid6",
    "一号铁": "iron1", "二号铁": "iron2", "三号铁": "iron3", "四号铁": "iron4",
    "五号铁": "iron5", "六号铁": "iron6", "七号铁": "iron7", "八号铁": "iron8", "九号铁": "iron9",
    "P 杆": "pw", "A 杆": "gw", "S 杆": "sw", "L 杆": "lw",
    "50° 挖起杆": "wedge50", "52° 挖起杆": "wedge52", "54° 挖起杆": "wedge54",
    "56° 挖起杆": "wedge56", "58° 挖起杆": "wedge58", "60° 挖起杆": "wedge60",
    "推杆": "putter",
]

public func backendToken(forZhName zhName: String) -> String? { zhNameToBackendToken[zhName] }

/// The player's bag, persisted locally (UserDefaults) PER SIGNED-IN PLAYER. The live picker / caddie
/// use `effectiveBag()`: a manual override (`bag()`) wins, else the auto-fetched real Garmin bag
/// (`realBag()`); `nil` from both means not-yet-known → callers fall back to shot-history clubs.
public enum ClubBagStore {
    /// Where the bag lives. Tests and design snapshots swap in an isolated suite.
    public static var defaults: UserDefaults = .standard
    /// Posted on the main thread whenever the manual roster or a typed carry changes, so a live
    /// decision built from the previous bag is re-requested.
    public static let didChange = Notification.Name("ai-caddie.club-bag.did-change")

    static let bagBase = "ai-caddie.club-bag-v1"
    static let realBase = "ai-caddie.club-bag-real-v1"
    static let distancesBase = "ai-caddie.club-bag-distances-v1"
    static let revisionBase = "ai-caddie.club-bag-revision-v1"
    static let outboxBase = "ai-caddie.club-bag-outbox-v1"
    static let generationBase = "ai-caddie.club-bag-outbox-generation-v1"
    static let syncedBase = "ai-caddie.club-bag-cloud-synced-v1"
    private static let scopedBases = [bagBase, realBase, distancesBase, revisionBase, outboxBase, generationBase, syncedBase]

    /// Whether this phone has ever matched the bound player's cloud bag (a restore or an accepted
    /// PUT). Until then an edit could be based on a partial local bag and overwrite the cloud one.
    public static var hasSyncedWithCloud: Bool {
        get { defaults.bool(forKey: key(syncedBase)) }
        set { defaults.set(newValue, forKey: key(syncedBase)) }
    }

    /// The signed-in player every key is scoped to (`nil` before sign-in / the owner admin build).
    public private(set) static var playerId: String?

    /// The storage key of `base` for `player` — one player's bag, distances and outbox never leak to
    /// another account on the same phone.
    static func key(_ base: String, playerId player: String?) -> String {
        guard let player, !player.isEmpty else { return base }
        return "\(base).\(player)"
    }

    private static func key(_ base: String) -> String { key(base, playerId: playerId) }

    /// Rebind to the signed-in player. With `migrateLegacy` the unscoped values written before
    /// per-account storage move to this player once (mirrors `OfflineStore.bindAccount`).
    public static func bind(playerId newValue: String?, migrateLegacy: Bool) {
        let trimmed = newValue?.trimmingCharacters(in: .whitespacesAndNewlines)
        let player = (trimmed?.isEmpty ?? true) ? nil : trimmed
        guard player != playerId else { return }
        playerId = player
        if migrateLegacy, let player {
            for base in scopedBases {
                let scoped = key(base, playerId: player)
                if let legacy = defaults.object(forKey: base) {
                    if defaults.object(forKey: scoped) == nil { defaults.set(legacy, forKey: scoped) }
                    defaults.removeObject(forKey: base)
                }
            }
        }
        notifyChanged(bumpRevision: false)
    }

    /// Bumped on every roster / typed-carry change of the bound player.
    public static var revision: Int { defaults.integer(forKey: key(revisionBase)) }

    public static func bag() -> Set<String>? {
        decodeBag(key(bagBase))
    }

    /// An empty set is not a roster: like the server's `PUT {"clubs": []}`, it clears the manual bag.
    public static func save(_ bag: Set<String>) {
        guard !bag.isEmpty else {
            clearManual()
            return
        }
        guard bag != self.bag() else { return }
        encodeBag(bag, into: key(bagBase))
        notifyChanged()
    }

    /// Drop the manual override so the player snaps back to the auto `realBag` default. Used by the
    /// 「用 Garmin 球包重置」 action when a stale manual selection no longer matches the real bag.
    public static func clearManual() {
        guard defaults.object(forKey: key(bagBase)) != nil else { return }
        defaults.removeObject(forKey: key(bagBase))
        notifyChanged()
    }

    /// The real Garmin bag, auto-fetched from the backend and cached. Used as the default everywhere
    /// the player hasn't manually overridden their bag. Refreshed whenever `refreshRealClubBag` runs.
    public static func realBag() -> Set<String>? {
        decodeBag(key(realBase))
    }

    public static func saveRealBag(_ bag: Set<String>) {
        encodeBag(bag, into: key(realBase))
    }

    /// Manual override wins; otherwise the real Garmin bag. `nil` if neither is known yet.
    public static func effectiveBag() -> Set<String>? {
        bag() ?? realBag()
    }

    /// Per-club typed distances (yards) the player edits in 球包, persisted locally and pushed to
    /// the backend manual bag. Keyed by catalog `zhName`; the UI is yards, the payload is metres.
    public static func manualDistancesYd() -> [String: Int] {
        (defaults.dictionary(forKey: key(distancesBase)) as? [String: Int]) ?? [:]
    }

    public static func saveManualDistancesYd(_ d: [String: Int]) {
        guard d != manualDistancesYd() else { return }
        if d.isEmpty {
            defaults.removeObject(forKey: key(distancesBase))
        } else {
            defaults.set(d, forKey: key(distancesBase))
        }
        notifyChanged()
    }

    /// Replace the bound player's local manual roster and typed distances with the server's
    /// EFFECTIVE bag (a reinstall or a second phone). A manual bag restores roster + typed carries
    /// (keeping the local yard value when it rounds to the same metres); a Garmin/none bag means
    /// there is no manual override, so the local one is dropped.
    public static func hydrate(from response: EffectiveClubBagResponse) {
        guard response.source == "manual" else {
            clearManual()
            saveManualDistancesYd([:])
            return
        }
        let local = manualDistancesYd()
        var roster = Set<String>()
        var distances: [String: Int] = [:]
        for club in response.clubs {
            guard let name = zhName(forBackendToken: club.token) else { continue }
            roster.insert(name)
            guard club.distanceSource == "manual", let metres = club.distanceM, metres > 0 else { continue }
            if let yards = local[name], carryMetres(yards: yards) == metres.rounded() {
                distances[name] = yards
            } else {
                distances[name] = Int((metres / 0.9144).rounded())
            }
        }
        if roster.isEmpty { clearManual() } else { save(roster) }
        saveManualDistancesYd(distances)
    }

    static func zhName(forBackendToken token: String) -> String? {
        zhNameToBackendToken.first { $0.value == token }?.key
    }

    private static func notifyChanged(bumpRevision: Bool = true) {
        if bumpRevision {
            defaults.set(revision &+ 1, forKey: key(revisionBase))
        }
        NotificationCenter.default.post(name: didChange, object: nil)
    }

    /// The typed carry in metres, rounded exactly like the PUT payload so the phone and the server
    /// project the same number.
    static func carryMetres(yards: Int) -> Double {
        (Double(yards) * 0.9144).rounded()
    }

    /// Build the PUT payload: backend token + yards->metres (the bag stores metres). Clubs whose name
    /// has no backend token are dropped; a club without a typed distance sends a nil `distanceM`.
    /// In catalog order, so one bag always produces the same payload.
    public static func manualClubInputs(selected: Set<String>, distancesYd: [String: Int]) -> [ManualClubInput] {
        ClubCatalog.all.map(\.zhName).filter { selected.contains($0) }.compactMap { zh in
            guard let token = backendToken(forZhName: zh) else { return nil }
            let m = distancesYd[zh].flatMap { $0 > 0 ? carryMetres(yards: $0) : nil }
            return ManualClubInput(token: token, customName: nil, distanceM: m)
        }
    }

    /// Typed carries (metres) for the clubs in the bag, keyed by catalog name. The putter has none.
    static func manualCarriesM(
        bag: Set<String>? = ClubBagStore.effectiveBag(),
        distancesYd: [String: Int] = ClubBagStore.manualDistancesYd()
    ) -> [String: Double] {
        var carries: [String: Double] = [:]
        for (name, yards) in distancesYd where yards > 0 && name != "推杆" && ClubCatalog.names.contains(name) {
            if let bag, !bag.contains(name) { continue }
            carries[name] = carryMetres(yards: yards)
        }
        return carries
    }

    /// THE effective-profile projection every caddie consumer reads (local decisions, online
    /// requests, map distance, Watch). A manual roster is authoritative: a club taken out of 球包 is
    /// dropped. A distance typed in 球包 replaces the history median and the history p10–p90 band
    /// moves with it, so the measured spread stays; aliases of one physical club ("Aw"/"GW") all
    /// move to the same carry. A typed club without any history gets a zero-sample row. Mirrors the
    /// server's ``restrict_to_bag`` + ``apply_manual_carries``; re-applying is a no-op.
    public static func effectiveProfiles(
        _ profiles: [ClubProfile],
        authority: ClubBagAuthority = .current
    ) -> [ClubProfile] {
        guard !authority.isEmpty else { return profiles }
        var covered = Set<String>()
        var result = profiles.compactMap { profile -> ClubProfile? in
            let name = zhClubName(profile.clubName.trimmingCharacters(in: .whitespaces))
            guard authority.allows(name) else { return nil }
            covered.insert(name)
            guard let carry = authority.carriesM[name] else { return profile }
            let band = shiftedBand(median: profile.medianM, p10: profile.p10M, p90: profile.p90M, to: carry)
            return ClubProfile(clubName: profile.clubName, sampleSize: profile.sampleSize, medianM: carry, p10M: band.p10, p90M: band.p90)
        }
        for name in ClubCatalog.all.map(\.zhName) where !covered.contains(name) {
            guard let carry = authority.missingRowCarry(name) else { continue }
            result.append(ClubProfile(clubName: name, sampleSize: 0, medianM: carry, p10M: carry, p90M: carry))
        }
        return result
    }

    /// The same projection over a seed/request `clubProfiles` value (name-keyed object or array).
    static func effectiveProfileValue(_ value: JSONValue?, authority: ClubBagAuthority = .current) -> JSONValue? {
        guard !authority.isEmpty else { return value }
        var covered = Set<String>()
        func project(_ row: JSONValue) -> JSONValue? {
            guard case .object(var fields) = row,
                  case .string(let raw)? = fields["clubName"] ?? fields["name"] else { return row }
            let name = zhClubName(raw.trimmingCharacters(in: .whitespaces))
            guard authority.allows(name) else { return nil }
            covered.insert(name)
            guard let carry = authority.carriesM[name] else { return row }
            func number(_ keys: [String]) -> Double? {
                for key in keys { if case .number(let v)? = fields[key] { return v } }
                return nil
            }
            let median = number(["median_m", "median", "carryM"]) ?? 0
            let band = shiftedBand(median: median, p10: number(["p10_m", "p10M", "p10"]) ?? 0, p90: number(["p90_m", "p90M", "p90"]) ?? 0, to: carry)
            for key in ["median", "carryM"] where fields[key] != nil { fields[key] = .number(carry) }
            for key in ["p10M", "p10"] where fields[key] != nil { fields[key] = .number(band.p10) }
            for key in ["p90M", "p90"] where fields[key] != nil { fields[key] = .number(band.p90) }
            fields["median_m"] = .number(carry)
            fields["p10_m"] = .number(band.p10)
            fields["p90_m"] = .number(band.p90)
            return .object(fields)
        }
        func missingRows() -> [(String, JSONValue)] {
            ClubCatalog.all.map(\.zhName).compactMap { name in
                guard !covered.contains(name), let carry = authority.missingRowCarry(name) else { return nil }
                return (name, .object([
                    "clubName": .string(name), "sampleSize": .number(0),
                    "median_m": .number(carry), "p10_m": .number(carry), "p90_m": .number(carry),
                ]))
            }
        }
        switch value {
        case .object(let rows)?:
            var projected = rows.compactMapValues(project)
            for (name, row) in missingRows() where projected[name] == nil { projected[name] = row }
            return .object(projected)
        case .array(let rows)?:
            let projected = rows.compactMap(project)
            return .array(projected + missingRows().map { $0.1 })
        case nil:
            let rows = missingRows()
            return rows.isEmpty ? nil : .object(Dictionary(rows, uniquingKeysWith: { first, _ in first }))
        default:
            return value
        }
    }

    /// Move a history p10–p90 band with its median to a typed carry; no history → a point band.
    private static func shiftedBand(median: Double, p10: Double, p90: Double, to carry: Double) -> (p10: Double, p90: Double) {
        guard median.isFinite, median > 0, p10.isFinite, p90.isFinite, p10 > 0, p90 > 0 else { return (carry, carry) }
        let delta = carry - median
        func shifted(_ v: Double) -> Double { (max(1, v + delta) * 10).rounded() / 10 }
        return (shifted(p10), shifted(p90))
    }

    private static func decodeBag(_ storageKey: String) -> Set<String>? {
        guard let data = defaults.data(forKey: storageKey),
              let list = try? JSONDecoder().decode([String].self, from: data) else {
            return nil
        }
        // One contract with the server: a manual roster always has clubs; empty means none.
        return list.isEmpty ? nil : Set(list)
    }

    private static func encodeBag(_ bag: Set<String>, into storageKey: String) {
        guard let data = try? JSONEncoder().encode(Array(bag).sorted()) else { return }
        defaults.set(data, forKey: storageKey)
    }
}

/// What the player set in 球包 that every recommendation must respect: the manual roster (a club
/// taken out is never recommended) and the typed carries. Cached plans built before a change —
/// CoursePrep chains, candidate routes, offline options — are kept only while every leg still
/// matches; otherwise they are dropped and the caddie re-plans from the effective profiles.
public struct ClubBagAuthority: Equatable {
    /// The manual roster (catalog names); `nil` when the player has no manual bag.
    public var roster: Set<String>?
    /// Typed carries in metres by catalog name.
    public var carriesM: [String: Double]

    /// A cached leg whose carry is within this of the typed carry still matches (metre rounding).
    static let carryToleranceM = 1.5

    public init(roster: Set<String>?, carriesM: [String: Double]) {
        self.roster = roster
        self.carriesM = carriesM
    }

    public static var current: ClubBagAuthority {
        ClubBagAuthority(roster: ClubBagStore.bag(), carriesM: ClubBagStore.manualCarriesM())
    }

    var isEmpty: Bool { roster == nil && carriesM.isEmpty }

    /// The carry of a zero-sample row for a selected club that no history row covers: the typed
    /// carry, else (for a club in a manual roster) the catalog default. The putter has none.
    func missingRowCarry(_ name: String) -> Double? {
        guard name != "推杆" else { return nil }
        if let carry = carriesM[name] { return carry }
        guard roster?.contains(name) == true else { return nil }
        return ClubCatalog.defaultDistanceM[name]
    }

    /// A club (any alias) is usable unless a manual roster leaves it out.
    func allows(_ rawName: String) -> Bool {
        guard let roster else { return true }
        return roster.contains(zhClubName(rawName.trimmingCharacters(in: .whitespacesAndNewlines)))
    }

    /// One cached leg: its club is still in the bag, and a typed carry (if any) is the one it uses.
    func matches(club rawName: String, carryM: Double?) -> Bool {
        let name = zhClubName(rawName.trimmingCharacters(in: .whitespacesAndNewlines))
        guard !name.isEmpty, name != "-" else { return true }
        guard allows(name) else { return false }
        if let typed = carriesM[name], let carryM, carryM.isFinite, carryM > 0 {
            return abs(carryM - typed) <= Self.carryToleranceM
        }
        return true
    }

    func planMatches(_ legs: [(club: String, carryM: Double?)]) -> Bool {
        legs.allSatisfy { matches(club: $0.club, carryM: $0.carryM) }
    }

    /// Roster only — for live decisions, whose carries are strategy values rather than medians
    /// (they are re-requested on every bag change instead).
    func rosterAllows(_ clubs: [String]) -> Bool {
        clubs.allSatisfy { club in
            let trimmed = club.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty || trimmed == "-" || allows(trimmed)
        }
    }
}

extension LiveRoundPackage {
    /// The package's club profiles with the carries typed in 球包 applied — what every caddie, map and
    /// Watch consumer reads instead of the raw history `clubProfiles`.
    public var effectiveClubProfiles: [ClubProfile] {
        ClubBagStore.effectiveProfiles(clubProfiles)
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
