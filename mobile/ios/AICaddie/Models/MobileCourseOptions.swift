import Foundation

public struct MobileCourseOptionsResponse: Codable, Equatable {
    public let schema: String
    public let dataMode: String
    public let total: Int
    public let courses: [MobileCourseOption]
    public let generatedAt: String
}

/// A lightweight row from Garmin's full CourseView catalogue. Search results are not downloaded
/// course packages: the selected row enters the existing tee/package preparation flow, and only
/// that course's assets are fetched.
public struct MobileCourseSearchMatch: Codable, Equatable, Identifiable {
    public var id: Int { globalId }

    public let globalId: Int
    public let name: String
    public let holes: Int?
    public let city: String?
    public let province: String?
    public let ratio: Double
    public let latitude: Double?
    public let longitude: Double?
    public let distanceKm: Double?

    public init(
        globalId: Int,
        name: String,
        holes: Int?,
        city: String?,
        province: String?,
        ratio: Double,
        latitude: Double? = nil,
        longitude: Double? = nil,
        distanceKm: Double? = nil
    ) {
        self.globalId = globalId
        self.name = name
        self.holes = holes
        self.city = city
        self.province = province
        self.ratio = ratio
        self.latitude = latitude
        self.longitude = longitude
        self.distanceKm = distanceKm
    }

    /// A result without a factual hole count remains visible but cannot start a round. We do not
    /// guess 9/18, because that would also guess the loop composition and package request.
    public var courseOption: MobileCourseOption? {
        guard let holes, holes > 0 else { return nil }
        let parts = name.split(separator: "~", maxSplits: 1, omittingEmptySubsequences: false)
        let venue = String(parts[0]).trimmingCharacters(in: .whitespacesAndNewlines)
        let segment = parts.count > 1
            ? String(parts[1]).trimmingCharacters(in: .whitespacesAndNewlines)
            : nil
        return MobileCourseOption(
            globalId: globalId,
            name: name,
            holes: holes,
            geometryCoverage: "missing",
            venueName: venue.isEmpty ? name : venue,
            segmentLabel: segment?.isEmpty == false ? segment : nil,
            segmentHoles: holes,
            latitude: latitude,
            longitude: longitude
        )
    }

    public var subtitle: String {
        var location: [String] = []
        if let distanceKm, distanceKm.isFinite, distanceKm >= 0 {
            location.append(distanceKm < 10
                ? String(format: "%.1f km", distanceKm)
                : "\(Int(distanceKm.rounded())) km")
        }
        for rawValue in [city, province] {
            guard let value = rawValue?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !value.isEmpty else { continue }
            if !location.contains(where: { $0.caseInsensitiveCompare(value) == .orderedSame }) {
                location.append(value)
            }
        }
        let holeText = holes.flatMap { $0 > 0 ? "\($0) 洞" : nil } ?? "洞数未知"
        return (location + [holeText]).joined(separator: " · ")
    }
}

public struct MobileCourseSearchResponse: Codable, Equatable {
    public let schema: String
    public let query: String
    public let matches: [MobileCourseSearchMatch]
}

public struct MobileNearbyCoursesResponse: Codable, Equatable {
    public let schema: String
    public let radiusKm: Int
    public let matches: [MobileCourseSearchMatch]
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

public enum PrepCourseDownloadPhase: String, Codable, Equatable {
    case queued
    case preparing
    case downloading
    case ready
    case failed
}

/// Durable library row for one explicitly selected prep course. Search results remain metadata-only;
/// only a course the player opens/downloads is retained here and installed into OfflineStore.
public struct PrepCourseDownloadRecord: Codable, Equatable, Identifiable {
    public let id: String
    public let course: MobileCourseOption
    public let teeBox: String
    public let nine: String
    public var phase: PrepCourseDownloadPhase
    public var preparedHoles: Int
    public var downloadedHoles: Int
    public var totalHoles: Int
    public var updatedAt: Date
    public var errorText: String?
    /// Positive server release revisions that a replacement install must satisfy before this row
    /// can become ready again. Nil for ordinary downloads and backward-compatible persisted rows.
    public var requiredGeometryRevisions: [String: String]?

    public init(
        course: MobileCourseOption,
        teeBox: String? = nil,
        nine: String = "all",
        phase: PrepCourseDownloadPhase = .queued,
        preparedHoles: Int = 0,
        downloadedHoles: Int = 0,
        totalHoles: Int? = nil,
        updatedAt: Date = Date(),
        errorText: String? = nil,
        requiredGeometryRevisions: [String: String]? = nil
    ) {
        let rawTee = (teeBox ?? course.teeBox ?? "blue")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedTee = rawTee.isEmpty ? "blue" : rawTee
        let resolvedNine = nine.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        self.id = Self.key(globalId: course.globalId, teeBox: resolvedTee, nine: resolvedNine)
        self.course = course
        self.teeBox = resolvedTee
        self.nine = resolvedNine.isEmpty ? "all" : resolvedNine
        self.phase = phase
        self.preparedHoles = max(0, preparedHoles)
        self.downloadedHoles = max(0, downloadedHoles)
        self.totalHoles = max(1, totalHoles ?? course.resolvedHoles)
        self.updatedAt = updatedAt
        self.errorText = errorText
        self.requiredGeometryRevisions = requiredGeometryRevisions?.isEmpty == false
            ? requiredGeometryRevisions
            : nil
    }

    public static func key(globalId: Int, teeBox: String, nine: String = "all") -> String {
        let tee = teeBox.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let selection = nine.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return "\(globalId):\(tee.isEmpty ? "blue" : tee):\(selection.isEmpty ? "all" : selection)"
    }

    public var isActive: Bool {
        phase == .queued || phase == .preparing || phase == .downloading
    }

    public var progressFraction: Double {
        guard totalHoles > 0 else { return 0 }
        return min(max(Double(downloadedHoles) / Double(totalHoles), 0), 1)
    }
}
