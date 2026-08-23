import Foundation

/// The player's REAL Garmin club bag, fetched from the backend (which merges Garmin's
/// `/club/player` roster with the `/club/types` dictionary). This is the authoritative
/// "which clubs do I actually carry, by real name" — distinct from `ClubProfile` (distance
/// stats derived from shot history). Resolution to a Chinese catalog name happens on-device
/// (see `resolvedBagNames` / `garminClubTypeZh` in ClubBag.swift) so all name logic lives in
/// one place alongside `zhClubName`.
public struct ClubBagResponse: Codable, Equatable {
    public let schema: String?
    public let found: Bool
    public let playerProfileId: Int?
    public let clubs: [ClubBagClub]

    public init(schema: String? = nil, found: Bool, playerProfileId: Int? = nil, clubs: [ClubBagClub]) {
        self.schema = schema
        self.found = found
        self.playerProfileId = playerProfileId
        self.clubs = clubs
    }
}

public struct ClubBagClub: Codable, Equatable, Identifiable {
    /// Garmin club instance id (stable per club in the bag).
    public let id: Int
    /// Garmin clubType enum value (1=Driver … 23=Putter). Authoritative for the standard name.
    public let clubTypeId: Int
    /// The user's custom name when they renamed the club (e.g. "Pw", "Aw", "50", "54", "58"); else nil.
    public let customName: String?
    /// The clubType's standard English name from Garmin's dictionary (e.g. "Driver", "5 Iron").
    public let typeName: String?
    public let loftAngle: Double?
    /// Garmin's own normal-distance fields. Older accounts commonly return 0 for both.
    public let averageDistance: Double?
    public let adviceDistance: Double?
    public let retired: Bool
    public let deleted: Bool

    public init(id: Int, clubTypeId: Int, customName: String? = nil, typeName: String? = nil,
                loftAngle: Double? = nil, averageDistance: Double? = nil,
                adviceDistance: Double? = nil, retired: Bool = false, deleted: Bool = false) {
        self.id = id
        self.clubTypeId = clubTypeId
        self.customName = customName
        self.typeName = typeName
        self.loftAngle = loftAngle
        self.averageDistance = averageDistance
        self.adviceDistance = adviceDistance
        self.retired = retired
        self.deleted = deleted
    }
}
