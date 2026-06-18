import Foundation

public struct MobileCourseOptionsResponse: Codable, Equatable {
    public let schema: String
    public let dataMode: String
    public let total: Int
    public let courses: [MobileCourseOption]
    public let generatedAt: String
}

public extension MobileCourseOption {
    /// Venue name without the loop suffix (falls back to stripping " ~ …" from `name`).
    var venueDisplayName: String {
        venueName ?? (name.components(separatedBy: " ~ ").first?.trimmingCharacters(in: .whitespaces) ?? name)
    }

    /// Segment row title: a loop ("A 场") or a whole course ("全场").
    var segmentDisplayTitle: String {
        if let label = segmentLabel, !label.isEmpty {
            return "\(label) 场"
        }
        return "全场"
    }

    /// True 9/18 hole count for this segment (CourseView), falling back to the played count.
    var resolvedHoles: Int {
        segmentHoles ?? holes
    }
}

/// Group course options by venue → each venue's playable segments (loops A/B/C, or a whole 18),
/// loops first (A<B<C), single course last; venues ordered by most-played first.
public func courseVenueGroups(_ options: [MobileCourseOption]) -> [(venue: String, segments: [MobileCourseOption])] {
    var byVenue: [String: [MobileCourseOption]] = [:]
    for option in options {
        byVenue[option.venueDisplayName, default: []].append(option)
    }
    return byVenue
        .map { entry in
            (venue: entry.key, segments: entry.value.sorted { ($0.segmentLabel ?? "~~") < ($1.segmentLabel ?? "~~") })
        }
        .sorted { ($0.segments.map(\.roundCount).max() ?? 0) > ($1.segments.map(\.roundCount).max() ?? 0) }
}

public struct MobileCourseOption: Codable, Equatable, Identifiable {
    public var id: Int { globalId }

    public let globalId: Int
    public let courseKey: String?
    public let name: String
    public let roundCount: Int
    public let latestRoundId: String?
    public let latestRoundDate: String?
    public let templateRoundId: String?
    public let suggestedLiveRoundId: String?
    public let holes: Int
    public let teeBox: String?
    public let geometryCoverage: String
    public let sourceRefs: [String]
    /// CourseView loop structure (so the picker lists each playable nine under its venue):
    /// venueName = Chinese venue without the '~ X' suffix; segmentLabel = loop letter/name
    /// (nil for a single whole course); segmentHoles = true 9/18. Optional → tolerate older payloads.
    public let venueName: String?
    public let segmentLabel: String?
    public let segmentHoles: Int?
    /// Course coordinates for GPS "nearby courses" sorting (nil when unknown).
    public let latitude: Double?
    public let longitude: Double?
    /// Real tee colours for this course (Gold/Black/Blue/White/Red…) from Garmin CourseView —
    /// the same list Garmin's own new-round tee picker shows. Empty when unknown.
    public let tees: [String]?

    public init(
        globalId: Int,
        courseKey: String? = nil,
        name: String,
        roundCount: Int = 0,
        latestRoundId: String? = nil,
        latestRoundDate: String? = nil,
        templateRoundId: String? = nil,
        suggestedLiveRoundId: String? = nil,
        holes: Int = 18,
        teeBox: String? = nil,
        geometryCoverage: String = "missing",
        sourceRefs: [String] = [],
        venueName: String? = nil,
        segmentLabel: String? = nil,
        segmentHoles: Int? = nil,
        latitude: Double? = nil,
        longitude: Double? = nil,
        tees: [String]? = nil
    ) {
        self.globalId = globalId
        self.courseKey = courseKey
        self.name = name
        self.roundCount = roundCount
        self.latestRoundId = latestRoundId
        self.latestRoundDate = latestRoundDate
        self.templateRoundId = templateRoundId
        self.suggestedLiveRoundId = suggestedLiveRoundId
        self.holes = holes
        self.teeBox = teeBox
        self.geometryCoverage = geometryCoverage
        self.sourceRefs = sourceRefs
        self.venueName = venueName
        self.segmentLabel = segmentLabel
        self.segmentHoles = segmentHoles
        self.latitude = latitude
        self.longitude = longitude
        self.tees = tees
    }
}
