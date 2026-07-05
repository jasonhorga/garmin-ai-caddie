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
    public let map: CoursePrepMap?
    public let shots: [RoundShot]

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        found = (try? c.decode(Bool.self, forKey: .found)) ?? false
        hole = (try? c.decode(Int.self, forKey: .hole)) ?? 0
        par = try? c.decodeIfPresent(Int.self, forKey: .par)
        globalId = try? c.decodeIfPresent(Int.self, forKey: .globalId)
        localHole = try? c.decodeIfPresent(Int.self, forKey: .localHole)
        map = try? c.decodeIfPresent(CoursePrepMap.self, forKey: .map)
        shots = (try? c.decodeIfPresent([RoundShot].self, forKey: .shots)) ?? []
    }

    public init(found: Bool, hole: Int, par: Int? = nil, globalId: Int? = nil, localHole: Int? = nil,
                map: CoursePrepMap? = nil, shots: [RoundShot] = []) {
        self.found = found
        self.hole = hole
        self.par = par
        self.globalId = globalId
        self.localHole = localHole
        self.map = map
        self.shots = shots
    }

    private enum CodingKeys: String, CodingKey { case found, hole, par, globalId, localHole, map, shots }
}

public struct RoundShot: Codable, Equatable, Identifiable {
    public var id: Int { order ?? 0 }
    /// [x, y] in overlay pixels (same frame as map.overlay). nil if unprojectable.
    public let start: [Int]?
    public let end: [Int]?
    public let club: String?
    public let lie: String?
    public let endLie: String?
    public let shotType: String?
    public let order: Int?
    /// true = synthesized (e.g. an unrecorded drive defaulted from the tee) → drawn faded/dashed.
    public let synthetic: Bool

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        start = try? c.decodeIfPresent([Int].self, forKey: .start)
        end = try? c.decodeIfPresent([Int].self, forKey: .end)
        club = try? c.decodeIfPresent(String.self, forKey: .club)
        lie = try? c.decodeIfPresent(String.self, forKey: .lie)
        endLie = try? c.decodeIfPresent(String.self, forKey: .endLie)
        shotType = try? c.decodeIfPresent(String.self, forKey: .shotType)
        order = try? c.decodeIfPresent(Int.self, forKey: .order)
        synthetic = (try? c.decodeIfPresent(Bool.self, forKey: .synthetic)) ?? false
    }

    public init(start: [Int]?, end: [Int]?, club: String? = nil, lie: String? = nil, endLie: String? = nil,
                shotType: String? = nil, order: Int? = nil, synthetic: Bool = false) {
        self.start = start
        self.end = end
        self.club = club
        self.lie = lie
        self.endLie = endLie
        self.shotType = shotType
        self.order = order
        self.synthetic = synthetic
    }

    private enum CodingKeys: String, CodingKey { case start, end, club, lie, endLie, shotType, order, synthetic }
}
