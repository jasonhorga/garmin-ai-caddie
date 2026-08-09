import Foundation

/// Per-hole 复盘 shot map from `GET /api/v2/history/rounds/{ref}/holes/{hole}/shotmap`
/// (server `build_round_hole_shot_map`): this round's actual shots projected onto the hole's 2D
/// render. `map` reuses CoursePrepMap (image + overlay); shots carry start/end overlay pixels + lie.
public struct RoundHoleShotMap: Codable, Equatable {
    public let found: Bool
    public let hole: Int
    public let par: Int?
    /// The physical (course, hole) the render came from — front/back-nine aware (a composite round's
    /// back nine maps to a different course's gid). Present when geometry rendered (`map` set); used
    /// to fetch the realistic topo base bitmap for the 复盘 canvas.
    public let globalId: Int?
    public let localHole: Int?
    public let geometryRevision: String?
    public let map: CoursePrepMap?
    /// `var` so RoundEditModel can apply edits optimistically in place before the server round-trips.
    public var shots: [RoundShot]
    /// Per-hole manually-entered penalty strokes (backend `manualPenalty`; `var` for the +/− stepper).
    public var manualPenalty: Int
    /// Honest degradation notes, including a stale whole-hole pixel edit after Garmin updates the
    /// course geometry. The raw shots remain visible and the player is prompted to redo that edit.
    public let missingData: [RoundShotMapMissing]

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        found = (try? c.decode(Bool.self, forKey: .found)) ?? false
        hole = (try? c.decode(Int.self, forKey: .hole)) ?? 0
        par = try? c.decodeIfPresent(Int.self, forKey: .par)
        globalId = try? c.decodeIfPresent(Int.self, forKey: .globalId)
        localHole = try? c.decodeIfPresent(Int.self, forKey: .localHole)
        geometryRevision = try? c.decodeIfPresent(String.self, forKey: .geometryRevision)
        map = try? c.decodeIfPresent(CoursePrepMap.self, forKey: .map)
        shots = (try? c.decodeIfPresent([RoundShot].self, forKey: .shots)) ?? []
        manualPenalty = (try? c.decodeIfPresent(Int.self, forKey: .manualPenalty)) ?? 0
        missingData = (try? c.decodeIfPresent([RoundShotMapMissing].self, forKey: .missingData)) ?? []
    }

    public init(found: Bool, hole: Int, par: Int? = nil, globalId: Int? = nil, localHole: Int? = nil,
                geometryRevision: String? = nil,
                map: CoursePrepMap? = nil, shots: [RoundShot] = [], manualPenalty: Int = 0,
                missingData: [RoundShotMapMissing] = []) {
        self.found = found
        self.hole = hole
        self.par = par
        self.globalId = globalId
        self.localHole = localHole
        self.geometryRevision = geometryRevision
        self.map = map
        self.shots = shots
        self.manualPenalty = manualPenalty
        self.missingData = missingData
    }

    private enum CodingKeys: String, CodingKey {
        case found, hole, par, globalId, localHole, geometryRevision, map, shots, manualPenalty, missingData
    }
}

public struct RoundShotMapMissing: Codable, Equatable, Identifiable {
    public var id: String { label + ":" + (reason ?? "") }
    public let label: String
    public let reason: String?

    public init(label: String, reason: String? = nil) {
        self.label = label
        self.reason = reason
    }
}

public struct RoundShot: Codable, Equatable, Identifiable {
    /// Stable per-shot identity from the backend (`s:{ref}:{n}`), used to reference this shot in
    /// correction ops. Falls back to an order-derived key when absent (unprojectable/legacy).
    public let shotId: String?
    public var id: String { shotId ?? "o\(order ?? 0)" }
    /// [x, y] in overlay pixels (same frame as map.overlay). nil if unprojectable.
    public let start: [Int]?
    public let end: [Int]?
    public let club: String?
    public let lie: String?
    public let endLie: String?
    public let shotType: String?
    public let order: Int?
    /// "manual" once the user has edited this field (surfaces a 已修正 marker; read-only web already uses it).
    public let clubSource: String?
    public let lieSource: String?
    /// true = synthesized (e.g. an unrecorded drive defaulted from the tee) → drawn faded/dashed.
    public let synthetic: Bool

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        shotId = try? c.decodeIfPresent(String.self, forKey: .shotId)
        start = try? c.decodeIfPresent([Int].self, forKey: .start)
        end = try? c.decodeIfPresent([Int].self, forKey: .end)
        club = try? c.decodeIfPresent(String.self, forKey: .club)
        lie = try? c.decodeIfPresent(String.self, forKey: .lie)
        endLie = try? c.decodeIfPresent(String.self, forKey: .endLie)
        shotType = try? c.decodeIfPresent(String.self, forKey: .shotType)
        order = try? c.decodeIfPresent(Int.self, forKey: .order)
        clubSource = try? c.decodeIfPresent(String.self, forKey: .clubSource)
        lieSource = try? c.decodeIfPresent(String.self, forKey: .lieSource)
        synthetic = (try? c.decodeIfPresent(Bool.self, forKey: .synthetic)) ?? false
    }

    public init(shotId: String? = nil, start: [Int]?, end: [Int]?, club: String? = nil, lie: String? = nil,
                endLie: String? = nil, shotType: String? = nil, order: Int? = nil,
                clubSource: String? = nil, lieSource: String? = nil, synthetic: Bool = false) {
        self.shotId = shotId
        self.start = start
        self.end = end
        self.club = club
        self.lie = lie
        self.endLie = endLie
        self.shotType = shotType
        self.order = order
        self.clubSource = clubSource
        self.lieSource = lieSource
        self.synthetic = synthetic
    }

    private enum CodingKeys: String, CodingKey {
        case shotId = "id"
        case start, end, club, lie, endLie, shotType, order, clubSource, lieSource, synthetic
    }
}
