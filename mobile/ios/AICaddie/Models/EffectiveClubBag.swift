import Foundation

/// One club in the manual-bag PUT payload (`PUT /api/v2/players/{id}/clubs/bag`). The backend bag
/// stores distances in METRES; the UI shows yards, so callers convert yards→metres when building this
/// (see `ClubBagStore.manualClubInputs`). `token` is the backend vocabulary (e.g. "driver", "wedge54").
public struct ManualClubInput: Codable, Equatable {
    public let token: String
    public let customName: String?
    public let distanceM: Double?
    public init(token: String, customName: String? = nil, distanceM: Double? = nil) {
        self.token = token; self.customName = customName; self.distanceM = distanceM
    }
}

/// One club in the EFFECTIVE bag the backend serves back (manual wins, else the synced Garmin bag).
public struct EffectiveClubBagClub: Codable, Equatable, Identifiable {
    public var id: String { token }
    public let token: String
    public let zhName: String?
    public let customName: String?
    public let clubTypeId: Int?
    public let distanceM: Double?
    public let distanceSource: String?
}

/// `GET`/`PUT /api/v2/players/{id}/clubs/bag` response: the effective bag + where it came from.
public struct EffectiveClubBagResponse: Codable, Equatable {
    public let schema: String?
    public let source: String      // "manual" | "garmin" | "none"
    public let found: Bool
    public let clubs: [EffectiveClubBagClub]
}
