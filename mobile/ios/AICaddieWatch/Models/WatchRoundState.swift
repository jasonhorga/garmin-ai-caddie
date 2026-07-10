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

/// round-13 spec ⑤: a single 障碍 (bunker/water) carry interval to surface on the watch Hazard View.
/// Distances are along-route metres (start = near edge / 越线前沿, end = far edge / 越线后沿); the watch
/// converts to 码. Pushed from the phone — mirrors the iPhone CaddiePlanHazard list.
public struct WatchHazard: Codable, Equatable, Identifiable {
    public var id: String { "\(kind)-\(label)" }

    public let kind: String     // "bunker" | "water"
    public let label: String    // 中文,如「沙坑 1」「水域」
    public let startM: Double?
    public let endM: Double?

    public init(kind: String, label: String, startM: Double? = nil, endM: Double? = nil) {
        self.kind = kind
        self.label = label
        self.startM = startM
        self.endM = endM
    }
}

/// round-13 spec ②: one AI-caddie play option (激进/推荐/保守) to surface on the watch 球童打法 screen.
/// Pushed from the phone — mirrors the iPhone CaddiePlanOption set. No success-% (intentionally absent).
public struct WatchCaddieOption: Codable, Equatable, Identifiable {
    public var id: String { optionId }

    public let optionId: String          // safe/stock/attack(或 option-N)
    public let label: String             // 稳妥/标准/进攻
    public let clubName: String?
    public let carryM: Double?
    public let expectedStrokes: Double?
    public let confidence: String?

    public init(
        optionId: String,
        label: String,
        clubName: String? = nil,
        carryM: Double? = nil,
        expectedStrokes: Double? = nil,
        confidence: String? = nil
    ) {
        self.optionId = optionId
        self.label = label
        self.clubName = clubName
        self.carryM = carryM
        self.expectedStrokes = expectedStrokes
        self.confidence = confidence
    }
}

// watch P0.2: the topo image's geo→pixel mapping — 3 non-collinear reference points (each WGS84 +
// its pixel on /topo.png); the watch fits an affine from them to project any lat/lon → pixel.
public struct WatchProjectionRef: Codable, Equatable {
    public let lat: Double
    public let lon: Double
    public let px: Double
    public let py: Double

    public init(lat: Double, lon: Double, px: Double, py: Double) {
        self.lat = lat
        self.lon = lon
        self.px = px
        self.py = py
    }
}

public struct WatchHoleImageProjection: Codable, Equatable {
    public let widthPx: Int?
    public let heightPx: Int?
    public let refs: [WatchProjectionRef]?

    public init(widthPx: Int?, heightPx: Int?, refs: [WatchProjectionRef]?) {
        self.widthPx = widthPx
        self.heightPx = heightPx
        self.refs = refs
    }
}

// watch P1b: the five overlay anchor points (in /topo.png IMAGE-pixel space, w×h) the phone pre-computes
// from the hole's centreline route so the watch renders the hole map WITHOUT any projection math — just
// draws the cached image + these anchors. `you` = tee (pre-GPS start), `pin` = green centre, `layup` =
// recommended lay-up, `apex`/`greenCtrl` = the you→lay-up / lay-up→green curve controls (on the route,
// so the play line bends with the dogleg). Each point is `[px, py]`.
public struct WatchHoleMap: Codable, Equatable {
    public let w: Int
    public let h: Int
    public let you: [Double]
    public let pin: [Double]
    public let layup: [Double]
    public let apex: [Double]
    public let greenCtrl: [Double]

    public init(w: Int, h: Int, you: [Double], pin: [Double], layup: [Double], apex: [Double], greenCtrl: [Double]) {
        self.w = w
        self.h = h
        self.you = you
        self.pin = pin
        self.layup = layup
        self.apex = apex
        self.greenCtrl = greenCtrl
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
    // watch P2 green slope (putt-read break): magnitude % + the bearing (topo frame) the ball breaks toward.
    public let greenSlopePct: Double?
    public let greenSlopeDirDeg: Double?
    public let lastShotDistanceM: Double?
    public let distanceFromLastShotM: Double?
    public let greenInRegulation: Bool?
    public let fairwayResult: String?
    public let geometryCoverage: String?
    // watch P0.2: green Front/Middle/Back WGS84 coords (so the watch recomputes F/M/B from its OWN GPS)
    // + the topo image's geo→px projection (so the watch places its GPS/pin/landings on /topo.png).
    public let frontGreenLat: Double?
    public let frontGreenLon: Double?
    public let centerGreenLat: Double?
    public let centerGreenLon: Double?
    public let backGreenLat: Double?
    public let backGreenLon: Double?
    public let holeImageProjection: WatchHoleImageProjection?
    // watch P1b: course global id (keys the cached /topo.png in WatchHoleImageStore) + the pre-computed
    // hole-map overlay anchors. Both optional — older payloads (no map) fall back to the text home view.
    public let globalId: Int?
    public let holeMap: WatchHoleMap?
    // round-13 spec ②⑤: AI-caddie play options (激进/推荐/保守) + 障碍 carry intervals, pushed from
    // the phone. Additive/optional — default [] so older payloads decode unchanged.
    public let caddieOptions: [WatchCaddieOption]
    public let hazards: [WatchHazard]
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
        case frontGreenLat
        case frontGreenLon
        case centerGreenLat
        case centerGreenLon
        case backGreenLat
        case backGreenLon
        case holeImageProjection
        case globalId
        case holeMap
        case playsLikeDistanceM
        case elevationDeltaM
        case greenSlopePct
        case greenSlopeDirDeg
        case lastShotDistanceM
        case distanceFromLastShotM
        case greenInRegulation
        case fairwayResult
        case geometryCoverage
        case caddieOptions
        case hazards
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
        frontGreenLat: Double? = nil,
        frontGreenLon: Double? = nil,
        centerGreenLat: Double? = nil,
        centerGreenLon: Double? = nil,
        backGreenLat: Double? = nil,
        backGreenLon: Double? = nil,
        holeImageProjection: WatchHoleImageProjection? = nil,
        globalId: Int? = nil,
        holeMap: WatchHoleMap? = nil,
        playsLikeDistanceM: Double? = nil,
        elevationDeltaM: Double? = nil,
        greenSlopePct: Double? = nil,
        greenSlopeDirDeg: Double? = nil,
        lastShotDistanceM: Double? = nil,
        distanceFromLastShotM: Double? = nil,
        greenInRegulation: Bool? = nil,
        fairwayResult: String? = nil,
        geometryCoverage: String? = nil,
        caddieOptions: [WatchCaddieOption] = [],
        hazards: [WatchHazard] = [],
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
        self.frontGreenLat = frontGreenLat
        self.frontGreenLon = frontGreenLon
        self.centerGreenLat = centerGreenLat
        self.centerGreenLon = centerGreenLon
        self.backGreenLat = backGreenLat
        self.backGreenLon = backGreenLon
        self.holeImageProjection = holeImageProjection
        self.globalId = globalId
        self.holeMap = holeMap
        self.playsLikeDistanceM = playsLikeDistanceM
        self.elevationDeltaM = elevationDeltaM
        self.greenSlopePct = greenSlopePct
        self.greenSlopeDirDeg = greenSlopeDirDeg
        self.lastShotDistanceM = lastShotDistanceM
        self.distanceFromLastShotM = distanceFromLastShotM
        self.greenInRegulation = greenInRegulation
        self.fairwayResult = fairwayResult
        self.geometryCoverage = geometryCoverage
        self.caddieOptions = caddieOptions
        self.hazards = hazards
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
        self.frontGreenLat = try container.decodeIfPresent(Double.self, forKey: .frontGreenLat)
        self.frontGreenLon = try container.decodeIfPresent(Double.self, forKey: .frontGreenLon)
        self.centerGreenLat = try container.decodeIfPresent(Double.self, forKey: .centerGreenLat)
        self.centerGreenLon = try container.decodeIfPresent(Double.self, forKey: .centerGreenLon)
        self.backGreenLat = try container.decodeIfPresent(Double.self, forKey: .backGreenLat)
        self.backGreenLon = try container.decodeIfPresent(Double.self, forKey: .backGreenLon)
        self.holeImageProjection = try container.decodeIfPresent(WatchHoleImageProjection.self, forKey: .holeImageProjection)
        self.globalId = try container.decodeIfPresent(Int.self, forKey: .globalId)
        self.holeMap = try container.decodeIfPresent(WatchHoleMap.self, forKey: .holeMap)
        self.centerGreenM = try container.decodeIfPresent(Double.self, forKey: .centerGreenM)
        self.backGreenM = try container.decodeIfPresent(Double.self, forKey: .backGreenM)
        self.playsLikeDistanceM = try container.decodeIfPresent(Double.self, forKey: .playsLikeDistanceM)
        self.elevationDeltaM = try container.decodeIfPresent(Double.self, forKey: .elevationDeltaM)
        self.greenSlopePct = try container.decodeIfPresent(Double.self, forKey: .greenSlopePct)
        self.greenSlopeDirDeg = try container.decodeIfPresent(Double.self, forKey: .greenSlopeDirDeg)
        self.lastShotDistanceM = try container.decodeIfPresent(Double.self, forKey: .lastShotDistanceM)
        self.distanceFromLastShotM = try container.decodeIfPresent(Double.self, forKey: .distanceFromLastShotM)
        self.greenInRegulation = try container.decodeIfPresent(Bool.self, forKey: .greenInRegulation)
        self.fairwayResult = try container.decodeIfPresent(String.self, forKey: .fairwayResult)
        self.geometryCoverage = try container.decodeIfPresent(String.self, forKey: .geometryCoverage)
        self.caddieOptions = try container.decodeIfPresent([WatchCaddieOption].self, forKey: .caddieOptions) ?? []
        self.hazards = try container.decodeIfPresent([WatchHazard].self, forKey: .hazards) ?? []
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
        case .fairway:
            break  // 上球道结果发去后端喂统计,不改本地即时的分数/推杆/距离
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
            frontGreenLat: frontGreenLat,
            frontGreenLon: frontGreenLon,
            centerGreenLat: centerGreenLat,
            centerGreenLon: centerGreenLon,
            backGreenLat: backGreenLat,
            backGreenLon: backGreenLon,
            holeImageProjection: holeImageProjection,
            globalId: globalId,
            holeMap: holeMap,
            playsLikeDistanceM: playsLikeDistanceM,
            elevationDeltaM: elevationDeltaM,
            greenSlopePct: greenSlopePct,
            greenSlopeDirDeg: greenSlopeDirDeg,
            lastShotDistanceM: lastShotDistanceM,
            distanceFromLastShotM: distanceFromLastShotM,
            greenInRegulation: greenInRegulation,
            fairwayResult: fairwayResult,
            geometryCoverage: geometryCoverage,
            caddieOptions: caddieOptions,
            hazards: hazards,
            score: nextScore,
            putts: nextPutts,
            penaltyCount: nextPenaltyCount,
            caddieConfidence: caddieConfidence
        )
    }
}
