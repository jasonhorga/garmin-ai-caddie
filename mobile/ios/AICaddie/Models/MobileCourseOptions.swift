import Foundation
import AICaddieDomain

/// Provider metadata remains untouched on the wire. This type resolves the
/// shared physical Garmin venue title; a playable loop stays in `segmentLabel`.
/// It never translates an English provider name or maps a global id to a
/// guessed local name.
public enum MobileCourseDisplayLocalization {
    public static let garminSnapshotNameSource = GarminCourseNameAuthority.garminSnapshotNameSource

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
        "shenzhen": "深圳市",
        "guangdong": "广东省",
        "guangdong province": "广东省",
        "monterey": "蒙特雷",
        "monterey county": "蒙特雷县",
        "california": "加利福尼亚州",
    ]

    /// Normalise only Garmin's course separator and incidental surrounding whitespace.
    public static func courseName(_ raw: String, globalId: Int? = nil) -> String {
        _ = globalId
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "" }
        return trimmed
            .split(separator: "~", omittingEmptySubsequences: true)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: " ~ ")
    }

    /// Split a Garmin display name into its venue and optional loop/layout suffix.
    public static func splitCourseName(_ raw: String) -> (venue: String, suffix: String?) {
        let normalized = courseName(raw)
        guard !normalized.isEmpty else { return ("", nil) }
        let parts = normalized.split(separator: "~", maxSplits: 1, omittingEmptySubsequences: true)
        var venue = String(parts[0]).trimmingCharacters(in: .whitespacesAndNewlines)
        var suffix: String? = parts.count > 1
            ? String(parts[1]).trimmingCharacters(in: .whitespacesAndNewlines)
            : nil
        // Older synced rows may omit Garmin's `~` separator (`Black Knight B/C`,
        // `Black Knight AC`). These are played loop combinations, never venue
        // text. Strip only an unambiguous trailing composite token.
        let tokens = venue.split(whereSeparator: { $0.isWhitespace })
        if let last = tokens.last,
           tokens.count > 1,
           isCompositeSegment(String(last)) {
            venue = tokens.dropLast().map(String.init).joined(separator: " ")
            if suffix?.isEmpty != false { suffix = String(last) }
        }
        return (venue, suffix?.isEmpty == false ? suffix : nil)
    }

    /// Garmin sometimes serialises a played route as `A/C`, `A+B`, or a compact `ABC`/`AC` code.
    /// Those are combinations of loops, not the identity of one selectable segment.
    public static func isCompositeSegment(_ raw: String?) -> Bool {
        guard let raw else { return false }
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return false }
        if value.contains("/") || value.contains("+") { return true }
        let compact = value.replacingOccurrences(of: " ", with: "").uppercased()
        return compact.range(of: "^[A-H]{2,4}$", options: .regularExpression) != nil
    }

    /// Name used for a selectable CourseView row. A factual single suffix is retained; a compact
    /// or separated multi-loop route is shown only in round history, never as one segment.
    public static func selectableCourseName(_ raw: String, globalId: Int? = nil) -> String {
        let normalized = courseName(raw, globalId: globalId)
        let split = splitCourseName(normalized)
        guard let suffix = split.suffix, isCompositeSegment(suffix) else { return normalized }
        return split.venue
    }

    /// Consume the backend-owned name contract. This is intentionally a thin
    /// wrapper around the domain implementation so iPhone and Watch apply the
    /// same Garmin-source gate and route handling.
    public static func canonicalCourseName(
        providerName: String?,
        venueName: String? = nil,
        venueNameSource: String? = nil,
        segmentLabel: String? = nil,
        globalId: Int? = nil
    ) -> String {
        let name = GarminCourseNameAuthority.canonicalName(
            providerName: providerName,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel
        )
        return selectableCourseName(name, globalId: globalId)
    }

    public static func canonicalSegment(
        providerName: String?,
        segmentLabel: String? = nil
    ) -> String? {
        GarminCourseNameAuthority.canonicalSegment(
            providerName: providerName,
            segmentLabel: segmentLabel
        )
    }

    public static func canonicalVenueName(
        providerName: String?,
        venueName: String? = nil,
        venueNameSource: String? = nil,
        segmentLabel: String? = nil,
        globalId: Int? = nil
    ) -> String {
        let name = canonicalCourseName(
            providerName: providerName,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel,
            globalId: globalId
        )
        return splitCourseName(name).venue
    }

    public static func administrativeArea(_ raw: String?) -> String? {
        guard let value = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
            return nil
        }
        return areaAliases[normalized(value)] ?? value
    }

    /// Prefer an already-provided Garmin Chinese course name when several sources describe the
    /// same global id. A locale-aware provider row may already be Chinese; a downloaded/history
    /// row remains useful evidence for older caches, but no unknown venue is translated locally.
    public static func preferredCourseName(
        _ rawNames: [String?],
        globalId: Int? = nil,
        fallback: String = "未知球场",
        trustedNameSources: [String?] = []
    ) -> String {
        let normalizedNames = rawNames.compactMap { raw -> String? in
            guard let raw, !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
            return courseName(raw, globalId: globalId)
        }
        let trustedNames = rawNames.enumerated().compactMap { index, raw -> String? in
            guard index < trustedNameSources.count,
                  let source = trustedNameSources[index],
                  source.trimmingCharacters(in: .whitespacesAndNewlines)
                    .caseInsensitiveCompare(Self.garminSnapshotNameSource) == .orderedSame,
                  let raw,
                  !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                return nil
            }
            return courseName(raw, globalId: globalId)
        }
        // Unmarked values are history/provider facts, not localization evidence. Preserve their
        // first spelling, while allowing an explicitly Garmin-backed Chinese value to win.
        let selected = trustedNames.first(where: { containsChinese(splitCourseName($0).venue) })
            ?? trustedNames.first
            ?? normalizedNames.first
            ?? fallback
        return selectableCourseName(selected, globalId: globalId)
    }

    /// Prefer a Chinese venue already present in Garmin-backed rows, without inventing a translation.
    public static func preferredVenueName(
        _ rawNames: [String?],
        globalId: Int? = nil,
        fallback: String = "未知球场",
        trustedNameSources: [String?] = []
    ) -> String {
        let venues = rawNames.compactMap { raw -> String? in
            guard let raw, !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
            let venue = splitCourseName(courseName(raw, globalId: globalId)).venue
            return venue.isEmpty ? nil : venue
        }
        let trustedVenues = rawNames.enumerated().compactMap { index, raw -> String? in
            guard index < trustedNameSources.count,
                  let source = trustedNameSources[index],
                  source.trimmingCharacters(in: .whitespacesAndNewlines)
                    .caseInsensitiveCompare(Self.garminSnapshotNameSource) == .orderedSame,
                  let raw,
                  !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                return nil
            }
            let venue = splitCourseName(courseName(raw, globalId: globalId)).venue
            return venue.isEmpty ? nil : venue
        }
        return trustedVenues.first(where: containsChinese)
            ?? trustedVenues.first
            ?? venues.first
            ?? fallback
    }

    private static func containsChinese(_ value: String) -> Bool {
        value.unicodeScalars.contains { scalar in
            (0x3400...0x4DBF).contains(scalar.value) || (0x4E00...0x9FFF).contains(scalar.value)
        }
    }

    private static func normalized(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .split(whereSeparator: { $0.isWhitespace })
            .joined(separator: " ")
    }
}

/// One presentation boundary for user-visible course names. Callers that only have an optional
/// payload should use this helper instead of sprinkling English fallbacks through view code.
public func localizedCourseDisplayName(
    _ raw: String?,
    globalId: Int? = nil,
    fallback: String = "未知球场"
) -> String {
    guard let raw, !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
        return fallback
    }
    return MobileCourseDisplayLocalization.canonicalVenueName(
        providerName: raw,
        globalId: globalId
    )
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
    /// Optional player-scoped Garmin snapshot authority. Anonymous CourseView
    /// rows remain valid when these fields are absent.
    public let venueName: String?
    public let venueNameSource: String?
    public let segmentLabel: String?

    public init(
        globalId: Int,
        name: String,
        holes: Int?,
        city: String?,
        province: String?,
        ratio: Double,
        latitude: Double? = nil,
        longitude: Double? = nil,
        distanceKm: Double? = nil,
        venueName: String? = nil,
        venueNameSource: String? = nil,
        segmentLabel: String? = nil
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
        self.venueName = venueName
        self.venueNameSource = venueNameSource
        self.segmentLabel = segmentLabel
    }

    /// A result without a factual hole count remains visible but cannot start a round. We do not
    /// guess 9/18, because that would also guess the loop composition and package request.
    public var courseOption: MobileCourseOption? {
        guard let holes, holes > 0 else { return nil }
        let canonical = MobileCourseDisplayLocalization.canonicalCourseName(
            providerName: name,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel,
            globalId: globalId
        )
        let venue = canonical
        let segment = MobileCourseDisplayLocalization.canonicalSegment(
            providerName: name,
            segmentLabel: segmentLabel
        )
        return MobileCourseOption(
            globalId: globalId,
            name: canonical,
            holes: holes,
            geometryCoverage: "missing",
            venueName: venue,
            venueNameSource: venueNameSource,
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
        let segmentText = MobileCourseDisplayLocalization.canonicalSegment(
            providerName: name,
            segmentLabel: segmentLabel
        ).map { "\($0) 场" }
        return ([segmentText].compactMap { $0 } + location + [holeText]).joined(separator: " · ")
    }

    public var displayName: String {
        MobileCourseDisplayLocalization.canonicalCourseName(
            providerName: name,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel,
            globalId: globalId
        )
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
    /// Shared physical venue title; legacy `name` values with a loop suffix are
    /// normalized here without changing the stored route fact.
    var venueDisplayName: String {
        MobileCourseDisplayLocalization.canonicalVenueName(
            providerName: name,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel,
            globalId: globalId
        )
    }

    var localizedName: String {
        MobileCourseDisplayLocalization.canonicalCourseName(
            providerName: name,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel,
            globalId: globalId
        )
    }

    /// Factual single-loop label, recovered from legacy `name` values when the
    /// additive `segmentLabel` field is absent.
    var resolvedSegmentLabel: String? {
        MobileCourseDisplayLocalization.canonicalSegment(
            providerName: name,
            segmentLabel: segmentLabel
        )
    }

    /// Segment row title: a loop ("A 场") or a factual whole 18-hole course. A 9-hole row without
    /// a trustworthy loop label must not be presented as the whole course.
    var segmentDisplayTitle: String {
        if let label = resolvedSegmentLabel {
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

public extension RecentRoundSummary {
    var localizedCourseDisplayName: String {
        MobileCourseDisplayLocalization.canonicalVenueName(
            providerName: courseName,
            globalId: globalId
        )
    }
}

public extension HistoryRoundCard {
    var localizedCourseDisplayName: String {
        MobileCourseDisplayLocalization.canonicalVenueName(
            providerName: courseName,
            globalId: globalId
        )
    }
}

public extension StatsCourse {
    var localizedCourseDisplayName: String {
        guard let courseName else { return courseKey }
        return MobileCourseDisplayLocalization.canonicalVenueName(
            providerName: courseName,
            globalId: globalId
        )
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
            (venue: entry.key, segments: entry.value.sorted { ($0.resolvedSegmentLabel ?? "~~") < ($1.resolvedSegmentLabel ?? "~~") })
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
    /// Source marker for venueName. Only Garmin's explicit scorecard snapshot is trusted for
    /// relabeling an anonymous CourseView row; nil keeps legacy/cache rows conservative.
    public let venueNameSource: String?
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
        venueNameSource: String? = nil,
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
        self.venueNameSource = venueNameSource
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
