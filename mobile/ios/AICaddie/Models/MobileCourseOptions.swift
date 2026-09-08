import Foundation

/// Provider metadata remains untouched on the wire. These aliases are presentation-only and cover
/// stable catalogue names seen in the Chinese app; unknown names fall through instead of inventing
/// a translation that could identify the wrong physical course.
public enum MobileCourseDisplayLocalization {
    private static let courseAliases: [String: String] = [
        "beijing riverside resort golf club": "北京河畔度假高尔夫俱乐部",
        "beijing huanggang international golf club": "北京黄港国际高尔夫俱乐部",
        "beijing black knight golf club": "北京黑骑士国际高尔夫俱乐部",
        "beijing black knight international golf club": "北京黑骑士国际高尔夫俱乐部",
        "nicklaus club beijing": "北京尼克劳斯俱乐部",
        "beijing orient tianxing country club": "北京东方天星乡村俱乐部",
    ]

    private static let areaAliases: [String: String] = [
        "beijing": "北京市",
        "beijing city": "北京市",
        "chaoyang": "朝阳区",
        "chaoyang district": "朝阳区",
        "shunyi": "顺义区",
        "shunyi district": "顺义区",
        "daxing": "大兴区",
        "daxing district": "大兴区",
        "changping": "昌平区",
        "changping district": "昌平区",
        "tianzhu": "天竺镇",
    ]

    public static func courseName(_ raw: String, globalId: Int? = nil) -> String {
        let parts = raw.components(separatedBy: " ~ ")
        let venue = parts.first?.trimmingCharacters(in: .whitespacesAndNewlines) ?? raw
        let localizedVenue: String
        if globalId == 31_793 {
            // This CourseView ID is provider-mislabeled as Shadow Creek; the repository's verified
            // player history and geometry identify the Beijing venue without changing provider data.
            localizedVenue = "北京丽宫体育公园高尔夫俱乐部"
        } else {
            localizedVenue = courseAliases[normalized(venue)] ?? venue
        }
        guard parts.count > 1 else { return localizedVenue }
        return ([localizedVenue] + parts.dropFirst()).joined(separator: " ~ ")
    }

    public static func administrativeArea(_ raw: String?) -> String? {
        guard let value = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
            return nil
        }
        return areaAliases[normalized(value)] ?? value
    }

    private static func normalized(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "  ", with: " ")
    }
}

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
        let localizedVenue = MobileCourseDisplayLocalization.courseName(venue, globalId: globalId)
        let localizedName: String
        if let segment, !segment.isEmpty {
            localizedName = "\(localizedVenue) ~ \(segment)"
        } else {
            localizedName = localizedVenue
        }
        return MobileCourseOption(
            globalId: globalId,
            name: localizedName,
            holes: holes,
            geometryCoverage: "missing",
            venueName: localizedVenue,
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
                ? String(format: "%.1f 公里", distanceKm)
                : "\(Int(distanceKm.rounded())) 公里")
        }
        for rawValue in [city, province] {
            guard let value = MobileCourseDisplayLocalization.administrativeArea(rawValue) else { continue }
            if !location.contains(where: { $0.caseInsensitiveCompare(value) == .orderedSame }) {
                location.append(value)
            }
        }
        let holeText = holes.flatMap { $0 > 0 ? "\($0) 洞" : nil } ?? "洞数未知"
        return (location + [holeText]).joined(separator: " · ")
    }

    public var displayName: String {
        MobileCourseDisplayLocalization.courseName(name, globalId: globalId)
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
        let raw = venueName ?? (name.components(separatedBy: " ~ ").first?.trimmingCharacters(in: .whitespaces) ?? name)
        return MobileCourseDisplayLocalization.courseName(raw, globalId: globalId)
    }

    var localizedName: String {
        MobileCourseDisplayLocalization.courseName(name, globalId: globalId)
    }

    /// Segment row title: a loop ("A 场") or a factual whole 18-hole course. A 9-hole row without
    /// a trustworthy loop label must not be presented as the whole course.
    var segmentDisplayTitle: String {
        if let label = segmentLabel?.trimmingCharacters(in: .whitespacesAndNewlines), !label.isEmpty {
            return "\(label) 场"
        }
        if resolvedHoles == 9 {
            return "未标注场区"
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

    /// Composite 9+9 packages use the live-round path until prep can install both physical loops.
    /// Keep this terminal state distinct from a transient network failure so the UI does not offer
    /// a misleading endless retry action.
    public var isTerminalFailure: Bool {
        phase == .failed && errorText?.hasPrefix("两段 9 洞组合暂不支持备战下载") == true
    }

    public var progressFraction: Double {
        guard totalHoles > 0 else { return 0 }
        return min(max(Double(downloadedHoles) / Double(totalHoles), 0), 1)
    }
}
