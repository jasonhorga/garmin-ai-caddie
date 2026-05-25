import Foundation

public struct WatchRoundState: Codable, Equatable, Identifiable {
    public var id: String { "\(roundId)-\(hole)" }

    public let roundId: String
    public let hole: Int
    public let par: Int
    public let distanceM: Double?
    public let selectedClub: String?
    public let score: Int
    public let putts: Int
    public let penaltyCount: Int
    public let caddieConfidence: String

    public init(
        roundId: String,
        hole: Int,
        par: Int,
        distanceM: Double?,
        selectedClub: String?,
        score: Int,
        putts: Int,
        penaltyCount: Int,
        caddieConfidence: String
    ) {
        self.roundId = roundId
        self.hole = hole
        self.par = par
        self.distanceM = distanceM
        self.selectedClub = selectedClub
        self.score = score
        self.putts = putts
        self.penaltyCount = penaltyCount
        self.caddieConfidence = caddieConfidence
    }
}
