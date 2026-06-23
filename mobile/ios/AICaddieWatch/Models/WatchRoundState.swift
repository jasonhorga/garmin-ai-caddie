import Foundation

public struct WatchClubOption: Codable, Equatable, Identifiable {
    public var id: String { clubName }

    public let clubName: String
    public let sampleSize: Int?
    public let medianM: Double?
    public let source: String?

    public init(
        clubName: String,
        sampleSize: Int? = nil,
        medianM: Double? = nil,
        source: String? = nil
    ) {
        self.clubName = clubName
        self.sampleSize = sampleSize
        self.medianM = medianM
        self.source = source
    }
}

public struct WatchRoundState: Codable, Equatable, Identifiable {
    public var id: String { "\(roundId)-\(hole)" }
    public var availableClubNames: [String] {
        availableClubs.map(\.clubName)
    }

    public let schema: String = "ai-caddie-watch-round-state-v1"
    public let roundId: String
    public let hole: Int
    public let par: Int
    public let distanceM: Double?
    public let targetNote: String?
    public let targetLatitude: Double?
    public let targetLongitude: Double?
    public let targetKind: String?
    public let suggestedClub: String?
    public let selectedClub: String?
    public let availableClubs: [WatchClubOption]
    public let shotType: String?
    public let strategyMode: String?
    public let lie: String?
    public let offlineOptionId: String?
    public let decisionId: String?
    public let nextShotPrompt: String?
    public let holePlanSummary: String?
    public let expectedStrokes: Double?
    public let expectedRemainingM: Double?
    public let evidenceSummary: String?
    public let missingDataSummary: String?
    // round-13 E4: Apple Watch live-screen fields (F/M/B green, plays-like/slope, last shot,
    // GIR/fairway, geometry-coverage gating). All optional/additive; populated by a later UI PR.
    public let frontGreenM: Double?
    public let centerGreenM: Double?
    public let backGreenM: Double?
    public let playsLikeDistanceM: Double?
    public let elevationDeltaM: Double?
    public let lastShotDistanceM: Double?
    public let distanceFromLastShotM: Double?
    public let greenInRegulation: Bool?
    public let fairwayResult: String?
    public let geometryCoverage: String?
    public let score: Int
    public let putts: Int
    public let penaltyCount: Int
    public let caddieConfidence: String

    enum CodingKeys: String, CodingKey {
        case schema
        case roundId
        case hole
        case par
        case distanceM
        case targetNote
        case targetLatitude
        case targetLongitude
        case targetKind
        case suggestedClub
        case selectedClub
        case availableClubs
        case shotType
        case strategyMode
        case lie
        case offlineOptionId
        case decisionId
        case nextShotPrompt
        case holePlanSummary
        case expectedStrokes
        case expectedRemainingM
        case evidenceSummary
        case missingDataSummary
        case frontGreenM
        case centerGreenM
        case backGreenM
        case playsLikeDistanceM
        case elevationDeltaM
        case lastShotDistanceM
        case distanceFromLastShotM
        case greenInRegulation
        case fairwayResult
        case geometryCoverage
        case score
        case putts
        case penaltyCount
        case caddieConfidence
    }

    public init(
        roundId: String,
        hole: Int,
        par: Int,
        distanceM: Double?,
        targetNote: String? = nil,
        targetLatitude: Double? = nil,
        targetLongitude: Double? = nil,
        targetKind: String? = nil,
        suggestedClub: String? = nil,
        selectedClub: String?,
        availableClubs: [WatchClubOption] = [],
        shotType: String? = nil,
        strategyMode: String? = nil,
        lie: String? = nil,
        offlineOptionId: String? = nil,
        decisionId: String? = nil,
        nextShotPrompt: String? = nil,
        holePlanSummary: String? = nil,
        expectedStrokes: Double? = nil,
        expectedRemainingM: Double? = nil,
        evidenceSummary: String? = nil,
        missingDataSummary: String? = nil,
        frontGreenM: Double? = nil,
        centerGreenM: Double? = nil,
        backGreenM: Double? = nil,
        playsLikeDistanceM: Double? = nil,
        elevationDeltaM: Double? = nil,
        lastShotDistanceM: Double? = nil,
        distanceFromLastShotM: Double? = nil,
        greenInRegulation: Bool? = nil,
        fairwayResult: String? = nil,
        geometryCoverage: String? = nil,
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
        self.targetLatitude = targetLatitude
        self.targetLongitude = targetLongitude
        self.targetKind = targetKind
        self.suggestedClub = suggestedClub
        self.selectedClub = selectedClub
        self.availableClubs = availableClubs
        self.shotType = shotType
        self.strategyMode = strategyMode
        self.lie = lie
        self.offlineOptionId = offlineOptionId
        self.decisionId = decisionId
        self.nextShotPrompt = nextShotPrompt
        self.holePlanSummary = holePlanSummary
        self.expectedStrokes = expectedStrokes
        self.expectedRemainingM = expectedRemainingM
        self.evidenceSummary = evidenceSummary
        self.missingDataSummary = missingDataSummary
        self.frontGreenM = frontGreenM
        self.centerGreenM = centerGreenM
        self.backGreenM = backGreenM
        self.playsLikeDistanceM = playsLikeDistanceM
        self.elevationDeltaM = elevationDeltaM
        self.lastShotDistanceM = lastShotDistanceM
        self.distanceFromLastShotM = distanceFromLastShotM
        self.greenInRegulation = greenInRegulation
        self.fairwayResult = fairwayResult
        self.geometryCoverage = geometryCoverage
        self.score = score
        self.putts = putts
        self.penaltyCount = penaltyCount
        self.caddieConfidence = caddieConfidence
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.roundId = try container.decode(String.self, forKey: .roundId)
        self.hole = try container.decode(Int.self, forKey: .hole)
        self.par = try container.decode(Int.self, forKey: .par)
        self.distanceM = try container.decodeIfPresent(Double.self, forKey: .distanceM)
        self.targetNote = try container.decodeIfPresent(String.self, forKey: .targetNote)
        self.targetLatitude = try container.decodeIfPresent(Double.self, forKey: .targetLatitude)
        self.targetLongitude = try container.decodeIfPresent(Double.self, forKey: .targetLongitude)
        self.targetKind = try container.decodeIfPresent(String.self, forKey: .targetKind)
        self.suggestedClub = try container.decodeIfPresent(String.self, forKey: .suggestedClub)
        self.selectedClub = try container.decodeIfPresent(String.self, forKey: .selectedClub)
        self.availableClubs = try container.decodeIfPresent([WatchClubOption].self, forKey: .availableClubs) ?? []
        self.shotType = try container.decodeIfPresent(String.self, forKey: .shotType)
        self.strategyMode = try container.decodeIfPresent(String.self, forKey: .strategyMode)
        self.lie = try container.decodeIfPresent(String.self, forKey: .lie)
        self.offlineOptionId = try container.decodeIfPresent(String.self, forKey: .offlineOptionId)
        self.decisionId = try container.decodeIfPresent(String.self, forKey: .decisionId)
        self.nextShotPrompt = try container.decodeIfPresent(String.self, forKey: .nextShotPrompt)
        self.holePlanSummary = try container.decodeIfPresent(String.self, forKey: .holePlanSummary)
        self.expectedStrokes = try container.decodeIfPresent(Double.self, forKey: .expectedStrokes)
        self.expectedRemainingM = try container.decodeIfPresent(Double.self, forKey: .expectedRemainingM)
        self.evidenceSummary = try container.decodeIfPresent(String.self, forKey: .evidenceSummary)
        self.missingDataSummary = try container.decodeIfPresent(String.self, forKey: .missingDataSummary)
        self.frontGreenM = try container.decodeIfPresent(Double.self, forKey: .frontGreenM)
        self.centerGreenM = try container.decodeIfPresent(Double.self, forKey: .centerGreenM)
        self.backGreenM = try container.decodeIfPresent(Double.self, forKey: .backGreenM)
        self.playsLikeDistanceM = try container.decodeIfPresent(Double.self, forKey: .playsLikeDistanceM)
        self.elevationDeltaM = try container.decodeIfPresent(Double.self, forKey: .elevationDeltaM)
        self.lastShotDistanceM = try container.decodeIfPresent(Double.self, forKey: .lastShotDistanceM)
        self.distanceFromLastShotM = try container.decodeIfPresent(Double.self, forKey: .distanceFromLastShotM)
        self.greenInRegulation = try container.decodeIfPresent(Bool.self, forKey: .greenInRegulation)
        self.fairwayResult = try container.decodeIfPresent(String.self, forKey: .fairwayResult)
        self.geometryCoverage = try container.decodeIfPresent(String.self, forKey: .geometryCoverage)
        self.score = try container.decode(Int.self, forKey: .score)
        self.putts = try container.decode(Int.self, forKey: .putts)
        self.penaltyCount = try container.decode(Int.self, forKey: .penaltyCount)
        self.caddieConfidence = try container.decode(String.self, forKey: .caddieConfidence)
    }

    public func applying(_ event: WatchInputEvent) -> WatchRoundState {
        guard event.roundId == roundId, event.hole == hole else {
            return self
        }
        var nextSelectedClub = selectedClub
        var nextDistanceM = distanceM
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
        case .distance:
            nextDistanceM = Double(event.value)
        }
        return WatchRoundState(
            roundId: roundId,
            hole: hole,
            par: par,
            distanceM: nextDistanceM,
            targetNote: targetNote,
            targetLatitude: targetLatitude,
            targetLongitude: targetLongitude,
            targetKind: targetKind,
            suggestedClub: suggestedClub,
            selectedClub: nextSelectedClub,
            availableClubs: availableClubs,
            shotType: shotType,
            strategyMode: strategyMode,
            lie: lie,
            offlineOptionId: offlineOptionId,
            decisionId: decisionId,
            nextShotPrompt: nextShotPrompt,
            holePlanSummary: holePlanSummary,
            expectedStrokes: expectedStrokes,
            expectedRemainingM: expectedRemainingM,
            evidenceSummary: evidenceSummary,
            missingDataSummary: missingDataSummary,
            frontGreenM: frontGreenM,
            centerGreenM: centerGreenM,
            backGreenM: backGreenM,
            playsLikeDistanceM: playsLikeDistanceM,
            elevationDeltaM: elevationDeltaM,
            lastShotDistanceM: lastShotDistanceM,
            distanceFromLastShotM: distanceFromLastShotM,
            greenInRegulation: greenInRegulation,
            fairwayResult: fairwayResult,
            geometryCoverage: geometryCoverage,
            score: nextScore,
            putts: nextPutts,
            penaltyCount: nextPenaltyCount,
            caddieConfidence: caddieConfidence
        )
    }
}
