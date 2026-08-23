import Foundation

/// One selectable tee box for the pre-round picker (`GET /api/v2/courses/{id}/tees`):
/// - `teeBox`: the colour key that threads back to the backend as `tee_box` (blue/white/…).
/// - `name`: display label — the course's own CourseView tee name when known, else the colour title.
/// - `yards`: the tee's total yardage, or `nil` when the tee has no geometry (honest — never faked).
/// - `set` / `holeCount`: the geometry set number + how many holes contributed to the yardage.
/// - `courseRating` / `slopeRating`: Garmin's real scorecard values for this gender/layout.
/// - `isDefault`: the course default (blue when present, else the longest tee).
public struct CourseTee: Codable, Equatable, Identifiable {
    public var id: String { teeBox }
    public let teeBox: String
    public let name: String
    public let set: Int?
    public let yards: Int?
    public let holeCount: Int?
    public let courseRating: Double?
    public let slopeRating: Int?
    public let isDefault: Bool

    public enum CodingKeys: String, CodingKey {
        case teeBox, name, set, yards, holeCount, courseRating, slopeRating
        case isDefault = "default"
    }

    public init(
        teeBox: String,
        name: String,
        set: Int? = nil,
        yards: Int? = nil,
        holeCount: Int? = nil,
        courseRating: Double? = nil,
        slopeRating: Int? = nil,
        isDefault: Bool = false
    ) {
        self.teeBox = teeBox
        self.name = name
        self.set = set
        self.yards = yards
        self.holeCount = holeCount
        self.courseRating = courseRating
        self.slopeRating = slopeRating
        self.isDefault = isDefault
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        teeBox = try container.decode(String.self, forKey: .teeBox)
        name = try container.decode(String.self, forKey: .name)
        set = try container.decodeIfPresent(Int.self, forKey: .set)
        yards = try container.decodeIfPresent(Int.self, forKey: .yards)
        holeCount = try container.decodeIfPresent(Int.self, forKey: .holeCount)
        courseRating = try container.decodeIfPresent(Double.self, forKey: .courseRating)
        slopeRating = try container.decodeIfPresent(Int.self, forKey: .slopeRating)
        // Tolerate an older/degraded payload that omits the flag → not default.
        isDefault = try container.decodeIfPresent(Bool.self, forKey: .isDefault) ?? false
    }
}

public struct CourseTeesResponse: Codable, Equatable {
    public let schema: String
    public let globalId: Int
    public let defaultTeeBox: String?
    public let tees: [CourseTee]

    public init(
        schema: String = "ai-caddie-course-tees-v1",
        globalId: Int,
        defaultTeeBox: String? = nil,
        tees: [CourseTee] = []
    ) {
        self.schema = schema
        self.globalId = globalId
        self.defaultTeeBox = defaultTeeBox
        self.tees = tees
    }
}
