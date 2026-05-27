import Foundation

public struct WatchRoundState: Codable, Equatable, Identifiable {
    public var id: String { "\(roundId)-\(hole)" }

    public let roundId: String
    public let hole: Int
    public let par: Int
    public let distanceM: Double?
    public let targetNote: String?
    public let suggestedClub: String?
    public let selectedClub: String?
    public let nextShotPrompt: String?
    public let score: Int
    public let putts: Int
    public let penaltyCount: Int
    public let caddieConfidence: String

    public init(
        roundId: String,
        hole: Int,
        par: Int,
        distanceM: Double?,
        targetNote: String? = nil,
        suggestedClub: String? = nil,
        selectedClub: String?,
        nextShotPrompt: String? = nil,
        score: Int,
        putts: Int,
        penaltyCount: Int,
        caddieConfidence: String
    ) {
        self.roundId = roundId
        self.hole = hole
        self.par = par
        self.distanceM = distanceM
        self.targetNote = targetNote
        self.suggestedClub = suggestedClub
        self.selectedClub = selectedClub
        self.nextShotPrompt = nextShotPrompt
        self.score = score
        self.putts = putts
        self.penaltyCount = penaltyCount
        self.caddieConfidence = caddieConfidence
    }

    public func applying(_ event: WatchInputEvent) -> WatchRoundState {
        guard event.roundId == roundId, event.hole == hole else {
            return self
        }
        var nextSelectedClub = selectedClub
        var nextScore = score
        var nextPutts = putts
        var nextPenaltyCount = penaltyCount
        switch event.kind {
        case .score:
            nextScore = Int(event.value) ?? score
        case .putt:
            nextPutts = Int(event.value) ?? putts
        case .penalty:
            nextPenaltyCount = Int(event.value) ?? penaltyCount
        case .club:
            nextSelectedClub = event.value
        }
        return WatchRoundState(
            roundId: roundId,
            hole: hole,
            par: par,
            distanceM: distanceM,
            targetNote: targetNote,
            suggestedClub: suggestedClub,
            selectedClub: nextSelectedClub,
            nextShotPrompt: nextShotPrompt,
            score: nextScore,
            putts: nextPutts,
            penaltyCount: nextPenaltyCount,
            caddieConfidence: caddieConfidence
        )
    }
}
