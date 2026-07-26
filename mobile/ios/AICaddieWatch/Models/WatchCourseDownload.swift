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
