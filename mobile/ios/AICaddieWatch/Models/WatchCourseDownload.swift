import Foundation

/// The small course row the Watch needs before a round. The backend response contains more history
/// metadata; Codable intentionally ignores it instead of copying the iPhone's full model graph.
public struct WatchCourseOption: Codable, Equatable, Identifiable {
    public var id: Int { globalId }

    public let globalId: Int
    public let name: String
    public let holes: Int
    public let teeBox: String?
    public let venueName: String?
    public let segmentLabel: String?
    public let segmentHoles: Int?
    public let tees: [String]
    public let roundCount: Int

    public init(
        globalId: Int,
        name: String,
        holes: Int,
        teeBox: String? = nil,
        venueName: String? = nil,
        segmentLabel: String? = nil,
        segmentHoles: Int? = nil,
        tees: [String] = [],
        roundCount: Int = 0
    ) {
        self.globalId = globalId
        self.name = name
        self.holes = holes
        self.teeBox = teeBox
        self.venueName = venueName
        self.segmentLabel = segmentLabel
        self.segmentHoles = segmentHoles
        self.tees = tees
        self.roundCount = roundCount
    }

    private enum CodingKeys: String, CodingKey {
        case globalId, name, holes, teeBox, venueName, segmentLabel, segmentHoles, tees, roundCount
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        globalId = try container.decode(Int.self, forKey: .globalId)
        name = try container.decode(String.self, forKey: .name)
        holes = try container.decode(Int.self, forKey: .holes)
        teeBox = try container.decodeIfPresent(String.self, forKey: .teeBox)
        venueName = try container.decodeIfPresent(String.self, forKey: .venueName)
        segmentLabel = try container.decodeIfPresent(String.self, forKey: .segmentLabel)
        segmentHoles = try container.decodeIfPresent(Int.self, forKey: .segmentHoles)
        tees = try container.decodeIfPresent([String].self, forKey: .tees) ?? []
        roundCount = try container.decodeIfPresent(Int.self, forKey: .roundCount) ?? 0
    }

    public var displayName: String {
        guard let venueName, let segmentLabel, !segmentLabel.isEmpty else { return name }
        return "\(venueName) · \(segmentLabel)"
    }

    public var playableHoleCount: Int { segmentHoles ?? holes }

    public var preferredTee: String {
        if let teeBox, !teeBox.isEmpty { return teeBox }
        return tees.first ?? "Blue"
    }
}

struct WatchCourseOptionsEnvelope: Decodable {
    let courses: [WatchCourseOption]
}

public struct WatchCoursePackage: Decodable, Equatable {
    public let roundId: String
    public let course: WatchCoursePackageCourse
    public let holes: [WatchCoursePackageHole]
}

public struct WatchCoursePackageCourse: Decodable, Equatable {
    public let globalId: Int
    public let name: String
    public let teeBox: String
}

public struct WatchCoursePackageHole: Decodable, Equatable {
    public let number: Int
    public let par: Int
    public let yards: Int?
    public let geometryCoverage: String?
    public let sourceGlobalId: Int?
    public let sourceLocalHole: Int?
}

public struct WatchCoursePrepResponse: Decodable, Equatable {
    public let globalId: Int
    public let clubs: [WatchCoursePrepClub]
    public let holes: [WatchCoursePrepHole]
}

public struct WatchCoursePrepClub: Decodable, Equatable {
    public let name: String
    public let m: Double
}

public struct WatchCoursePrepHole: Decodable, Equatable {
    public let hole: Int
    public let par: Int?
    public let geometryCoverage: String?
    public let landingM: Double?
    public let teeClub: String?
    public let hazards: WatchCoursePrepHazards
    public let map: WatchCoursePrepMap?
    public let greenDistances: WatchCoursePrepGreenDistances?
    public let playsLike: WatchCoursePrepPlaysLike?
    public let holeImageProjection: WatchCoursePrepProjection?

    private enum CodingKeys: String, CodingKey {
        case hole, par, geometryCoverage, hazards, map, greenDistances, playsLike, holeImageProjection
        case landingM = "landing_m"
        case teeClub = "tee_club"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        hole = try container.decode(Int.self, forKey: .hole)
        par = try container.decodeIfPresent(Int.self, forKey: .par)
        geometryCoverage = try container.decodeIfPresent(String.self, forKey: .geometryCoverage)
        landingM = try container.decodeIfPresent(Double.self, forKey: .landingM)
        teeClub = try container.decodeIfPresent(String.self, forKey: .teeClub)
        hazards = try container.decodeIfPresent(WatchCoursePrepHazards.self, forKey: .hazards)
            ?? WatchCoursePrepHazards()
        map = try container.decodeIfPresent(WatchCoursePrepMap.self, forKey: .map)
        greenDistances = try container.decodeIfPresent(WatchCoursePrepGreenDistances.self, forKey: .greenDistances)
        playsLike = try container.decodeIfPresent(WatchCoursePrepPlaysLike.self, forKey: .playsLike)
        holeImageProjection = try container.decodeIfPresent(WatchCoursePrepProjection.self, forKey: .holeImageProjection)
    }
}

public struct WatchCoursePrepHazards: Decodable, Equatable {
    public let waterCarry: [[Double]]
    public let bunkers: [[Double]]

    public init(waterCarry: [[Double]] = [], bunkers: [[Double]] = []) {
        self.waterCarry = waterCarry
        self.bunkers = bunkers
    }

    private enum CodingKeys: String, CodingKey {
        case waterCarry = "water_carry"
        case bunkers
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        waterCarry = try container.decodeIfPresent([[Double]].self, forKey: .waterCarry) ?? []
        bunkers = try container.decodeIfPresent([[Double]].self, forKey: .bunkers) ?? []
    }
}

public struct WatchCoursePrepMap: Decodable, Equatable {
    public let image: String
    public let overlay: WatchCoursePrepOverlay
}

public struct WatchCoursePrepOverlay: Decodable, Equatable {
    public let w: Int
    public let h: Int
    public let route: [[Double]]
}

public struct WatchCoursePrepGreenDistances: Decodable, Equatable {
    public let available: Bool
    public let frontM: Double?
    public let middleM: Double?
    public let backM: Double?
    public let frontLat: Double?
    public let frontLon: Double?
    public let middleLat: Double?
    public let middleLon: Double?
    public let backLat: Double?
    public let backLon: Double?
}

public struct WatchCoursePrepPlaysLike: Decodable, Equatable {
    public let available: Bool
    public let deltaM: Double?
}

public struct WatchCoursePrepProjection: Decodable, Equatable {
    public let available: Bool
    public let widthPx: Int?
    public let heightPx: Int?
    public let refs: [WatchProjectionRef]?
}

public struct WatchPreparedCourse: Equatable {
    public let roundId: String
    public let courseName: String
    public let holeStates: [WatchRoundState]
}

/// A downloaded course is a reusable, immutable template. Its server download round id is never
/// reused for play: `makeRound` rebases every hole onto a fresh id each time the golfer starts.
public struct WatchCourseTemplate: Codable, Equatable, Identifiable {
    public var id: Int { option.globalId }

    public let option: WatchCourseOption
    public let courseName: String
    public let teeBox: String
    public let holeStates: [WatchRoundState]
    public let cachedAt: String

    public init(
        option: WatchCourseOption,
        courseName: String,
        teeBox: String,
        holeStates: [WatchRoundState],
        cachedAt: String
    ) {
        self.option = option
        self.courseName = courseName
        self.teeBox = teeBox
        self.holeStates = holeStates
        self.cachedAt = cachedAt
    }

    public func makeRound(roundId: String) -> WatchPreparedCourse {
        WatchPreparedCourse(
            roundId: roundId,
            courseName: courseName,
            holeStates: holeStates.map { $0.replacingRoundId(roundId) }
        )
    }
}

public struct WatchCourseImage: Equatable {
    public let globalId: Int
    public let hole: Int
    public let data: Data

    public init(globalId: Int, hole: Int, data: Data) {
        self.globalId = globalId
        self.hole = hole
        self.data = data
    }
}

public struct WatchCourseDownload: Equatable {
    public let template: WatchCourseTemplate
    public let images: [WatchCourseImage]
}
