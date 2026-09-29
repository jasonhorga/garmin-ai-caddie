import Foundation
import AICaddieDomain

/// The small physical-venue row the Watch needs before a round. The backend
/// response contains more history metadata; Codable intentionally ignores it
/// instead of copying the iPhone's full model graph. Loop facts stay separate.
public struct WatchCourseOption: Codable, Equatable, Identifiable {
    public var id: Int { globalId }

    public let globalId: Int
    public let name: String
    public let holes: Int
    public let teeBox: String?
    public let venueName: String?
    public let venueNameSource: String?
    public let segmentLabel: String?
    public let segmentHoles: Int?
    /// Course coordinates already supplied by `/mobile/courses/options`; retained so the Watch can
    /// rank known courses from its own GPS without another backend or phone dependency.
    public let latitude: Double?
    public let longitude: Double?
    public let tees: [String]
    public let roundCount: Int

    public init(
        globalId: Int,
        name: String,
        holes: Int,
        teeBox: String? = nil,
        venueName: String? = nil,
        venueNameSource: String? = nil,
        segmentLabel: String? = nil,
        segmentHoles: Int? = nil,
        latitude: Double? = nil,
        longitude: Double? = nil,
        tees: [String] = [],
        roundCount: Int = 0
    ) {
        self.globalId = globalId
        self.name = name
        self.holes = holes
        self.teeBox = teeBox
        self.venueName = venueName
        self.venueNameSource = venueNameSource
        self.segmentLabel = segmentLabel
        self.segmentHoles = segmentHoles
        self.latitude = latitude
        self.longitude = longitude
        self.tees = tees
        self.roundCount = roundCount
    }

    private enum CodingKeys: String, CodingKey {
        case globalId, name, holes, teeBox, venueName, venueNameSource, segmentLabel, segmentHoles
        case latitude, longitude, tees, roundCount
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        globalId = try container.decode(Int.self, forKey: .globalId)
        name = try container.decode(String.self, forKey: .name)
        holes = try container.decode(Int.self, forKey: .holes)
        teeBox = try container.decodeIfPresent(String.self, forKey: .teeBox)
        venueName = try container.decodeIfPresent(String.self, forKey: .venueName)
        venueNameSource = try container.decodeIfPresent(String.self, forKey: .venueNameSource)
        segmentLabel = try container.decodeIfPresent(String.self, forKey: .segmentLabel)
        segmentHoles = try container.decodeIfPresent(Int.self, forKey: .segmentHoles)
        latitude = try container.decodeIfPresent(Double.self, forKey: .latitude)
        longitude = try container.decodeIfPresent(Double.self, forKey: .longitude)
        tees = try container.decodeIfPresent([String].self, forKey: .tees) ?? []
        roundCount = try container.decodeIfPresent(Int.self, forKey: .roundCount) ?? 0
    }

    public var displayName: String {
        GarminCourseNameAuthority.canonicalName(
            providerName: name,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel
        )
    }

    public var resolvedSegmentLabel: String? {
        GarminCourseNameAuthority.canonicalSegment(
            providerName: name,
            segmentLabel: segmentLabel
        )
    }

    public var segmentDisplayTitle: String {
        GarminCourseNameAuthority.userFacingSegmentTitle(
            label: resolvedSegmentLabel,
            holes: playableHoleCount
        )
    }

    public var venueDisplayName: String {
        GarminCourseNameAuthority.canonicalVenueName(
            providerName: name,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel
        )
    }

    public var playableHoleCount: Int { segmentHoles ?? holes }

    public var preferredTee: String {
        if let teeBox {
            let normalized = teeBox.trimmingCharacters(in: .whitespacesAndNewlines)
            if !normalized.isEmpty, normalized.caseInsensitiveCompare("unknown") != .orderedSame {
                return teeBox
            }
        }
        return tees.first(where: { ["blue", "white"].contains($0.lowercased()) })
            ?? tees.first
            ?? "unknown"
    }

    public func withTees(
        _ teeOptions: [WatchCourseTee],
        selectedTee: String? = nil
    ) -> WatchCourseOption {
        WatchCourseOption(
            globalId: globalId,
            name: name,
            holes: holes,
            teeBox: selectedTee ?? teeOptions.first(where: \.isDefault)?.teeBox ?? teeBox,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel,
            segmentHoles: segmentHoles,
            latitude: latitude,
            longitude: longitude,
            tees: teeOptions.map(\.teeBox),
            roundCount: roundCount
        )
    }

    /// A full-catalogue search row has no coordinates. Once its real package has supplied a
    /// validated Tee coordinate, retain that as the downloaded course location for offline nearby
    /// sorting. Existing mobile-option coordinates remain authoritative.
    public func withFallbackLocation(latitude: Double?, longitude: Double?) -> WatchCourseOption {
        guard self.latitude == nil || self.longitude == nil,
              let latitude, latitude.isFinite, (-90...90).contains(latitude),
              let longitude, longitude.isFinite, (-180...180).contains(longitude) else {
            return self
        }
        return WatchCourseOption(
            globalId: globalId,
            name: name,
            holes: holes,
            teeBox: teeBox,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel,
            segmentHoles: segmentHoles,
            latitude: latitude,
            longitude: longitude,
            tees: tees,
            roundCount: roundCount
        )
    }
}

/// A ranked row from Garmin's full course catalogue. It remains ephemeral until the selected
/// package + prep data has been downloaded into the existing Watch course store.
public struct WatchCourseSearchMatch: Decodable, Equatable, Identifiable {
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
    /// Optional localized venue/loop facts from the player's Garmin-backed
    /// history. Provider rows remain valid when omitted.
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

    public var courseOption: WatchCourseOption? {
        guard let holes, holes > 0 else { return nil }
        let canonical = GarminCourseNameAuthority.canonicalName(
            providerName: name,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel
        )
        let venue = canonical
        let segment = GarminCourseNameAuthority.canonicalSegment(
            providerName: name,
            segmentLabel: segmentLabel
        )
        return WatchCourseOption(
            globalId: globalId,
            name: canonical,
            holes: holes,
            venueName: venue,
            venueNameSource: venueNameSource,
            segmentLabel: segment?.isEmpty == false ? segment : nil,
            segmentHoles: holes,
            latitude: latitude,
            longitude: longitude
        )
    }

    public var displayName: String {
        GarminCourseNameAuthority.canonicalName(
            providerName: name,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel
        )
    }

    public var resolvedSegmentLabel: String? {
        GarminCourseNameAuthority.canonicalSegment(
            providerName: name,
            segmentLabel: segmentLabel
        )
    }

    public var segmentDisplayTitle: String {
        GarminCourseNameAuthority.userFacingSegmentTitle(
            label: resolvedSegmentLabel,
            holes: holes
        )
    }
}

/// One real tee row returned by GET /courses/{globalId}/tees. Missing yardage stays nil rather than
/// being replaced by a guessed distance.
public struct WatchCourseTee: Decodable, Equatable, Identifiable {
    public var id: String { teeBox.lowercased() }

    public let teeBox: String
    public let name: String
    public let geometrySet: Int?
    public let yards: Int?
    public let holeCount: Int?
    public let courseRating: Double?
    public let slopeRating: Int?
    public let isDefault: Bool

    public init(
        teeBox: String,
        name: String,
        geometrySet: Int? = nil,
        yards: Int? = nil,
        holeCount: Int? = nil,
        courseRating: Double? = nil,
        slopeRating: Int? = nil,
        isDefault: Bool
    ) {
        self.teeBox = teeBox
        self.name = name
        self.geometrySet = geometrySet
        self.yards = yards
        self.holeCount = holeCount
        self.courseRating = courseRating
        self.slopeRating = slopeRating
        self.isDefault = isDefault
    }

    private enum CodingKeys: String, CodingKey {
        case teeBox, name, yards, holeCount, courseRating, slopeRating
        case geometrySet = "set"
        case isDefault = "default"
    }
}

/// The exact real-world setup the player chose before downloading or starting a Watch round.
/// A 9-hole front loop can optionally be paired with a second loop; the selected tee always travels
/// with that choice so an offline launch can never silently substitute a different setup.
///
/// An 18-hole course is played as its two halves (B4b-2 §7): the player starts on one ordered half
/// (`firstHalf`, 前九 = "front" / 后九 = "back") and chooses the second half at the turn
/// (`secondHalf`, the same half allowed). Without `firstHalf` an 18-hole selection is the canonical
/// whole-course template (`G:front+G:back`), which is also what an offline turn projects from.
public struct WatchCourseSelection: Equatable {
    public static let halves = ["front", "back"]

    public let front: WatchCourseOption
    public let back: WatchCourseOption?
    public let teeBox: String
    public let ensureGeometry: Bool
    /// 18-hole course only: the half the round starts on. Nil for a nine-hole loop / 9+9 pairing and
    /// for the whole-course template.
    public let firstHalf: String?
    /// 18-hole course only: the half played after the turn. Nil until the turn is taken.
    public let secondHalf: String?

    public init(
        front: WatchCourseOption,
        back: WatchCourseOption? = nil,
        teeBox: String,
        ensureGeometry: Bool = false,
        firstHalf: String? = nil,
        secondHalf: String? = nil
    ) {
        self.front = front
        self.back = back
        self.teeBox = teeBox
        self.ensureGeometry = ensureGeometry
        let playsHalves = back == nil && front.playableHoleCount == 18
        let first = playsHalves ? Self.normalizedHalf(firstHalf) : nil
        self.firstHalf = first
        self.secondHalf = first == nil ? nil : Self.normalizedHalf(secondHalf)
    }

    /// Rebuild the exact selection a cached template was downloaded for (its halves come from the
    /// template's own ordered loop key, so `G:back` stays a one-half selection).
    public init(template: WatchCourseTemplate, ensureGeometry: Bool = false) {
        var halves: [String]?
        if template.backOption == nil, template.option.playableHoleCount == 18,
           let loop = Self.halfLoop(loopKey: template.loopKey),
           loop.globalId == template.option.globalId {
            halves = loop.halves
        }
        self.init(
            front: template.option,
            back: template.backOption,
            teeBox: template.teeBox,
            ensureGeometry: ensureGeometry,
            firstHalf: halves?.first,
            secondHalf: (halves?.count ?? 0) > 1 ? halves?.last : nil
        )
    }

    public var holeCount: Int {
        if firstHalf != nil {
            return secondHalf == nil ? 9 : 18
        }
        return front.playableHoleCount + (back?.playableHoleCount ?? 0)
    }

    /// The round's canonical ordered loop key (B4b-2): an 18-hole course is one or two ordered
    /// halves (`G:back`, `G:back+G:front`, `G:front+G:front`, ...; the whole course is
    /// `G:front+G:back`), a nine-hole loop is `G:all`, a 9+9 pairing appends the second loop.
    public var loopKey: String {
        Self.loopKey(front: front, back: back, firstHalf: firstHalf, secondHalf: secondHalf)
    }

    /// The `loops=` request value for this selection.
    public var loopsQuery: String {
        loopKey.replacingOccurrences(of: "+", with: ",")
    }

    public static func loopKey(front: WatchCourseOption, back: WatchCourseOption?) -> String {
        loopKey(front: front, back: back, firstHalf: nil, secondHalf: nil)
    }

    public static func loopKey(
        front: WatchCourseOption,
        back: WatchCourseOption?,
        firstHalf: String?,
        secondHalf: String? = nil
    ) -> String {
        if front.playableHoleCount == 18 {
            if back == nil, let first = normalizedHalf(firstHalf) {
                let halves = [first] + [normalizedHalf(secondHalf)].compactMap { $0 }
                return halves.map { "\(front.globalId):\($0)" }.joined(separator: "+")
            }
            return "\(front.globalId):front+\(front.globalId):back"
        }
        let first = "\(front.globalId):all"
        guard let back else { return first }
        return first + "+\(back.globalId):all"
    }

    /// The course ids of a loop key in play order (a repeated loop appears twice).
    public static func globalIds(loopKey: String) -> [Int] {
        loopKey.split(separator: "+").compactMap { part in
            part.split(separator: ":").first.flatMap { Int($0) }
        }
    }

    /// `"front"` / `"back"` (case-insensitive) or nil.
    public static func normalizedHalf(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              halves.contains(value) else { return nil }
        return value
    }

    /// One or two halves of one 18-hole course (`G:back`, `G:back+G:front`, ...), else nil.
    public static func halfLoop(loopKey: String) -> (globalId: Int, halves: [String])? {
        let entries = loopKey.split(separator: "+").map { $0.split(separator: ":").map(String.init) }
        guard (1...2).contains(entries.count) else { return nil }
        var globalId: Int?
        var halves: [String] = []
        for entry in entries {
            guard entry.count == 2,
                  let id = Int(entry[0]), id > 0,
                  let half = normalizedHalf(entry[1]),
                  globalId == nil || globalId == id else { return nil }
            globalId = id
            halves.append(half)
        }
        guard let globalId else { return nil }
        return (globalId, halves)
    }

    /// The physical hole a half starts on: 前九 1, 后九 10 (`sourceLocalHole` = `courseHoleNumber`).
    public static func physicalStartHole(_ half: String) -> Int {
        normalizedHalf(half) == "back" ? 10 : 1
    }

    /// 前九 / 后九 — a physical half is never relabelled.
    public static func halfName(_ half: String) -> String {
        normalizedHalf(half) == "back" ? "后九" : "前九"
    }

    /// Stable, case/whitespace-insensitive Tee identity used by the on-watch course cache.
    /// Empty and provider placeholder values intentionally share the `unknown` bucket: they mean
    /// that the player did not choose a concrete Tee, rather than a real Tee named "unknown".
    public var normalizedTeeKey: String {
        Self.normalizedTeeKey(teeBox)
    }

    public var hasExplicitTee: Bool {
        Self.hasExplicitTee(teeBox)
    }

    public static func normalizedTeeKey(_ value: String?) -> String {
        let normalized = (value ?? "")
            .split(whereSeparator: { $0.isWhitespace })
            .joined(separator: " ")
            .lowercased()
        return hasExplicitTee(normalized) ? normalized : "unknown"
    }

    public static func hasExplicitTee(_ value: String?) -> Bool {
        guard let value else { return false }
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return !normalized.isEmpty && normalized.caseInsensitiveCompare("unknown") != .orderedSame
    }
}

struct WatchCourseOptionsEnvelope: Decodable {
    let courses: [WatchCourseOption]
}

struct WatchCourseSearchEnvelope: Decodable {
    let matches: [WatchCourseSearchMatch]
}

struct WatchCourseTeesEnvelope: Decodable {
    let tees: [WatchCourseTee]
}

/// The only package contract the Watch accepts (B4b-2). A v1 package, or a v2 package missing
/// its loops or any hole's source identity, fails to decode — identity is never made up.
public struct WatchCoursePackage: Decodable, Equatable {
    public static let supportedSchema = "ai-caddie-live-round-package-v2"

    public let schema: String
    public let roundId: String
    public let course: WatchCoursePackageCourse
    public let holes: [WatchCoursePackageHole]
    public let roundLoops: [WatchRoundLoop]
    public let loopKey: String
    /// A fast package may carry a CourseView-only first-hole seed. Older servers omit this field.
    public let coursePrep: WatchCoursePrepResponse?
    /// Shared server gate; Watch still validates every local raster before advertising offline use.
    public let readinessState: String?
}

public struct WatchCoursePackageCourse: Decodable, Equatable {
    public let globalId: Int
    public let name: String
    public let venueName: String?
    public let venueNameSource: String?
    public let segmentLabel: String?
    public let teeBox: String

    /// Physical venue title shared with iPhone/Web. A trusted Garmin snapshot
    /// is the only local field allowed to replace the package name.
    public var venueDisplayName: String {
        GarminCourseNameAuthority.canonicalVenueName(
            providerName: name,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel
        )
    }
}

public struct WatchCoursePackageHole: Decodable, Equatable {
    public let number: Int
    public let par: Int
    public let yards: Int?
    public let geometryCoverage: String?
    public let geometryRevision: String?
    /// `number` is the round hole; these two are the physical hole; `courseHoleNumber` is text.
    public let sourceGlobalId: Int
    public let sourceLocalHole: Int
    public let courseHoleNumber: Int
    public let teeLatitude: Double?
    public let teeLongitude: Double?
}

public struct WatchRoundLoop: Decodable, Equatable {
    public let globalId: Int
    public let half: String
    public let roundStartHole: Int
    public let sourceStartHole: Int
    public let holeCount: Int
}

/// The v2 round-identity invariant (B4b-2 contract §6), enforced while decoding: a package that
/// names contradictory loops or holes is rejected, never played.
public enum WatchRoundIdentityError: Error, Equatable {
    case unsupportedSchema(String)
    case invalidRoundLoops
    case nonCanonicalLoopKey
    case holeDoesNotMatchItsLoop(Int)
}

extension WatchCoursePackage {
    private enum CodingKeys: String, CodingKey {
        case schema, roundId, course, holes, roundLoops, loopKey, coursePrep, readinessState
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let schema = try container.decode(String.self, forKey: .schema)
        guard schema == Self.supportedSchema else {
            throw WatchRoundIdentityError.unsupportedSchema(schema)
        }
        let holes = try container.decode([WatchCoursePackageHole].self, forKey: .holes)
        let roundLoops = try container.decode([WatchRoundLoop].self, forKey: .roundLoops)
        let loopKey = try container.decode(String.self, forKey: .loopKey)
        try Self.validateRoundIdentity(roundLoops: roundLoops, loopKey: loopKey, holes: holes)
        self.init(
            schema: schema,
            roundId: try container.decode(String.self, forKey: .roundId),
            course: try container.decode(WatchCoursePackageCourse.self, forKey: .course),
            holes: holes,
            roundLoops: roundLoops,
            loopKey: loopKey,
            coursePrep: try container.decodeIfPresent(WatchCoursePrepResponse.self, forKey: .coursePrep),
            readinessState: try container.decodeIfPresent(String.self, forKey: .readinessState)
        )
    }

    /// One or two loops starting on round holes 1 then 10, nine holes each, `sourceStartHole`
    /// matching `half`, the canonical `loopKey`, unique hole numbers, and every hole on its row.
    /// A package without playable holes names no loop.
    public static func validateRoundIdentity(
        roundLoops: [WatchRoundLoop],
        loopKey: String,
        holes: [WatchCoursePackageHole]
    ) throws {
        if holes.isEmpty {
            guard roundLoops.isEmpty, loopKey.isEmpty else { throw WatchRoundIdentityError.invalidRoundLoops }
            return
        }
        guard (1...2).contains(roundLoops.count) else { throw WatchRoundIdentityError.invalidRoundLoops }
        var expected: [Int: (globalId: Int, localHole: Int, courseHole: Int)] = [:]
        for (index, loop) in roundLoops.enumerated() {
            let sourceStart = loop.half == "back" ? 10 : 1
            guard ["all", "front", "back"].contains(loop.half),
                  loop.globalId > 0,
                  loop.roundStartHole == 1 + index * 9,
                  loop.sourceStartHole == sourceStart,
                  loop.holeCount == 9 else {
                throw WatchRoundIdentityError.invalidRoundLoops
            }
            for offset in 0..<9 {
                let number = loop.roundStartHole + offset
                let local = sourceStart + offset
                expected[number] = (loop.globalId, local, loop.half == "all" ? number : local)
            }
        }
        let canonical = roundLoops.map { "\($0.globalId):\($0.half)" }.joined(separator: "+")
        guard loopKey == canonical else { throw WatchRoundIdentityError.nonCanonicalLoopKey }
        var seen = Set<Int>()
        for hole in holes {
            guard seen.insert(hole.number).inserted,
                  let row = expected[hole.number],
                  row.globalId == hole.sourceGlobalId,
                  row.localHole == hole.sourceLocalHole,
                  row.courseHole == hole.courseHoleNumber else {
                throw WatchRoundIdentityError.holeDoesNotMatchItsLoop(hole.number)
            }
        }
        guard seen == Set(expected.keys) else { throw WatchRoundIdentityError.invalidRoundLoops }
    }
}

public struct WatchCoursePrepResponse: Decodable, Equatable {
    public let globalId: Int
    public let clubs: [WatchCoursePrepClub]
    public let holes: [WatchCoursePrepHole]

    public init(
        globalId: Int,
        clubs: [WatchCoursePrepClub] = [],
        holes: [WatchCoursePrepHole] = []
    ) {
        self.globalId = globalId
        self.clubs = clubs
        self.holes = holes
    }

    private enum CodingKeys: String, CodingKey {
        case globalId, clubs, holes
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        globalId = try container.decode(Int.self, forKey: .globalId)
        // Lightweight package seeds intentionally omit the bag. Treat that as "no measured club
        // facts yet" rather than failing the entire package and losing the drawable course map.
        clubs = try container.decodeIfPresent([WatchCoursePrepClub].self, forKey: .clubs) ?? []
        holes = try container.decodeIfPresent([WatchCoursePrepHole].self, forKey: .holes) ?? []
    }
}

public struct WatchCoursePrepClub: Decodable, Equatable {
    public let name: String
    public let token: String?
    public let m: Double
    public let distanceSource: String?
    public let sampleSize: Int?
    public let confidence: String?
}

public struct WatchCoursePrepHole: Decodable, Equatable {
    public let hole: Int
    public let par: Int?
    public let geometryCoverage: String?
    public let geometryRevision: String?
    public let landingM: Double?
    public let teeClub: String?
    public let steps: [WatchCoursePrepStep]
    public let route: [[Double]]
    public let hazards: WatchCoursePrepHazards
    public let map: WatchCoursePrepMap?
    public let greenDistances: WatchCoursePrepGreenDistances?
    public let playsLike: WatchCoursePrepPlaysLike?
    public let holeImageProjection: WatchCoursePrepProjection?
    public let greenOutline: WatchCoursePrepGreenOutline?
    /// B0 fairway rings; `nil` for old packages, no fairway geometry or a malformed value.
    public let fairwayOutline: FairwayOutline?

    private enum CodingKeys: String, CodingKey {
        case hole, par, geometryCoverage, geometryRevision, route, hazards, map, greenDistances, playsLike, holeImageProjection, greenOutline, fairwayOutline, steps
        case landingM = "landing_m"
        case teeClub = "tee_club"
    }

    public init(
        hole: Int,
        par: Int? = nil,
        geometryCoverage: String? = nil,
        geometryRevision: String? = nil,
        landingM: Double? = nil,
        teeClub: String? = nil,
        steps: [WatchCoursePrepStep] = [],
        route: [[Double]] = [],
        hazards: WatchCoursePrepHazards = WatchCoursePrepHazards(),
        map: WatchCoursePrepMap? = nil,
        greenDistances: WatchCoursePrepGreenDistances? = nil,
        playsLike: WatchCoursePrepPlaysLike? = nil,
        holeImageProjection: WatchCoursePrepProjection? = nil,
        greenOutline: WatchCoursePrepGreenOutline? = nil,
        fairwayOutline: FairwayOutline? = nil
    ) {
        self.hole = hole
        self.par = par
        self.geometryCoverage = geometryCoverage
        self.geometryRevision = geometryRevision
        self.landingM = landingM
        self.teeClub = teeClub
        self.steps = steps
        self.route = route
        self.hazards = hazards
        self.map = map
        self.greenDistances = greenDistances
        self.playsLike = playsLike
        self.holeImageProjection = holeImageProjection
        self.greenOutline = greenOutline
        self.fairwayOutline = fairwayOutline
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        hole = try container.decode(Int.self, forKey: .hole)
        par = try container.decodeIfPresent(Int.self, forKey: .par)
        geometryCoverage = try container.decodeIfPresent(String.self, forKey: .geometryCoverage)
        geometryRevision = try container.decodeIfPresent(String.self, forKey: .geometryRevision)
        landingM = try container.decodeIfPresent(Double.self, forKey: .landingM)
        teeClub = try container.decodeIfPresent(String.self, forKey: .teeClub)
        steps = try container.decodeIfPresent([WatchCoursePrepStep].self, forKey: .steps) ?? []
        route = try container.decodeIfPresent([[Double]].self, forKey: .route) ?? []
        hazards = try container.decodeIfPresent(WatchCoursePrepHazards.self, forKey: .hazards)
            ?? WatchCoursePrepHazards()
        map = try container.decodeIfPresent(WatchCoursePrepMap.self, forKey: .map)
        greenDistances = try container.decodeIfPresent(WatchCoursePrepGreenDistances.self, forKey: .greenDistances)
        playsLike = try container.decodeIfPresent(WatchCoursePrepPlaysLike.self, forKey: .playsLike)
        holeImageProjection = try container.decodeIfPresent(WatchCoursePrepProjection.self, forKey: .holeImageProjection)
        greenOutline = try container.decodeIfPresent(WatchCoursePrepGreenOutline.self, forKey: .greenOutline)
        fairwayOutline = container.decodeSupportedFairwayOutline(forKey: .fairwayOutline)
    }

    /// Composite package holes use display numbers (10...18), while prep requests use the source
    /// loop's local numbers (1...9). Keep all geometry facts intact while changing only that key.
    public func renumbered(to sourceLocalHole: Int) -> WatchCoursePrepHole {
        WatchCoursePrepHole(
            hole: sourceLocalHole,
            par: par,
            geometryCoverage: geometryCoverage,
            geometryRevision: geometryRevision,
            landingM: landingM,
            teeClub: teeClub,
            steps: steps,
            route: route,
            hazards: hazards,
            map: map,
            greenDistances: greenDistances,
            playsLike: playsLike,
            holeImageProjection: holeImageProjection,
            greenOutline: greenOutline,
            fairwayOutline: fairwayOutline
        )
    }
}

public struct WatchCoursePrepStep: Decodable, Equatable {
    public let club: String?
    public let clubName: String?
    public let targetCarryM: Double?
    public let routeOffsetM: Double?
    public let landingM: Double?
    public let expectedRemainingM: Double?
    public let role: String?
    public let planIndex: Int?

    private enum CodingKeys: String, CodingKey {
        case club, clubName, targetCarryM, routeOffsetM, landingM, expectedRemainingM, role, planIndex
        case targetCarrySnake = "targetCarry_m"
        case routeOffsetSnake = "routeOffset_m"
        case landingSnake = "landing_m"
        case expectedRemainingSnake = "expectedRemaining_m"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        club = try container.decodeIfPresent(String.self, forKey: .club)
        clubName = try container.decodeIfPresent(String.self, forKey: .clubName) ?? club
        func optionalDouble(_ primary: CodingKeys, _ fallback: CodingKeys) throws -> Double? {
            if let value = try container.decodeIfPresent(Double.self, forKey: primary) {
                return value
            }
            return try container.decodeIfPresent(Double.self, forKey: fallback)
        }
        targetCarryM = try optionalDouble(.targetCarryM, .targetCarrySnake)
        routeOffsetM = try optionalDouble(.routeOffsetM, .routeOffsetSnake)
        landingM = try optionalDouble(.landingM, .landingSnake)
        expectedRemainingM = try optionalDouble(.expectedRemainingM, .expectedRemainingSnake)
        role = try container.decodeIfPresent(String.self, forKey: .role)
        planIndex = try container.decodeIfPresent(Int.self, forKey: .planIndex)
    }
}

public struct WatchCoursePrepGreenOutline: Decodable, Equatable {
    public let available: Bool
    public let pointsPx: [[Double]]

    public init(available: Bool, pointsPx: [[Double]] = []) {
        self.available = available
        self.pointsPx = pointsPx
    }

    private enum CodingKeys: String, CodingKey {
        case available, pointsPx
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        available = try container.decodeIfPresent(Bool.self, forKey: .available) ?? false
        pointsPx = try container.decodeIfPresent([[Double]].self, forKey: .pointsPx) ?? []
    }
}

public struct WatchCoursePrepHazards: Decodable, Equatable {
    public let waterCarry: [[Double]]
    public let bunkers: [[Double]]
    public let details: [WatchCoursePrepHazardDetail]

    public init(
        waterCarry: [[Double]] = [],
        bunkers: [[Double]] = [],
        details: [WatchCoursePrepHazardDetail] = []
    ) {
        self.waterCarry = waterCarry
        self.bunkers = bunkers
        self.details = details
    }

    private enum CodingKeys: String, CodingKey {
        case waterCarry = "water_carry"
        case bunkers, details
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        waterCarry = try container.decodeIfPresent([[Double]].self, forKey: .waterCarry) ?? []
        bunkers = try container.decodeIfPresent([[Double]].self, forKey: .bunkers) ?? []
        details = try container.decodeIfPresent([WatchCoursePrepHazardDetail].self, forKey: .details) ?? []
    }
}

public struct WatchCoursePrepHazardDetail: Decodable, Equatable {
    public let kind: String
    public let frontM: Double
    public let backM: Double
    public let frontRouteM: Double
    public let backRouteM: Double
    public let frontPx: [Double]
    public let backPx: [Double]
    public let sideM: Double?
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

    /// Composite cache identity: the canonical ordered loop key plus Tee (B4b-2). `id` remains the
    /// front Garmin id for source compatibility, while this key keeps every loop order and Tee apart.
    public var cacheKey: String {
        Self.cacheKey(loopKey: loopKey, teeBox: teeBox)
    }

    public let option: WatchCourseOption
    public let backOption: WatchCourseOption?
    /// Required: a template cached before loop keys (v1) fails to decode and is re-downloaded.
    public let loopKey: String
    public let courseName: String
    public let teeBox: String
    public let holeStates: [WatchRoundState]
    public let cachedAt: String

    public init(
        option: WatchCourseOption,
        backOption: WatchCourseOption? = nil,
        loopKey: String? = nil,
        courseName: String,
        teeBox: String,
        holeStates: [WatchRoundState],
        cachedAt: String
    ) {
        self.option = option
        self.backOption = backOption
        // An ordered half (`G:back`, `G:back+G:front`) is passed explicitly; otherwise the key is the
        // options' canonical one (whole 18-hole course, nine-hole loop or 9+9 pairing).
        self.loopKey = loopKey ?? WatchCourseSelection.loopKey(front: option, back: backOption)
        self.courseName = courseName
        self.teeBox = teeBox
        self.holeStates = holeStates
        self.cachedAt = cachedAt
    }

    public func matches(_ selection: WatchCourseSelection) -> Bool {
        matches(loopKey: selection.loopKey, teeBox: selection.teeBox)
    }

    /// Holes this template must hold: nine per ordered half, else the options' playable holes.
    public var expectedHoleCount: Int {
        if backOption == nil, option.playableHoleCount == 18,
           let loop = WatchCourseSelection.halfLoop(loopKey: loopKey),
           loop.globalId == option.globalId {
            return loop.halves.count * 9
        }
        return option.playableHoleCount + (backOption?.playableHoleCount ?? 0)
    }

    public func matches(loopKey: String, teeBox: String?) -> Bool {
        self.loopKey == loopKey
            && WatchCourseSelection.normalizedTeeKey(self.teeBox) == WatchCourseSelection.normalizedTeeKey(teeBox)
    }

    public static func cacheKey(loopKey: String, teeBox: String?) -> String {
        "\(loopKey)|\(WatchCourseSelection.normalizedTeeKey(teeBox))"
    }

    public func makeRound(roundId: String, courseName overrideName: String? = nil) -> WatchPreparedCourse {
        let rawName = overrideName ?? courseName
        let roundName = GarminCourseNameAuthority.canonicalVenueName(
            providerName: rawName,
            venueName: option.venueName,
            venueNameSource: option.venueNameSource,
            segmentLabel: option.segmentLabel
        )
        return WatchPreparedCourse(
            roundId: roundId,
            courseName: roundName.isEmpty ? GarminCourseNameAuthority.selectableName(rawName) : roundName,
            holeStates: holeStates.map { $0.replacingRoundId(roundId) }
        )
    }
}

/// One round position of a cached template: the physical hole it must hold.
public struct WatchTemplateHoleRow: Equatable {
    public let number: Int
    public let globalId: Int
    public let sourceLocalHole: Int
}

/// The durable-template side of the round-identity invariant (B4b-2 §6). A template read from disk is
/// only trusted when its loop key is canonical for its own options and every hole sits on its loop
/// row; anything else is dropped at the load boundary and re-downloaded, never played.
extension WatchCourseTemplate {
    /// The round positions `loopKey` names for these options, in play order. An 18-hole course is
    /// one or two ordered halves (`G:back` → round 1–9 = physical 10–18); a nine-hole loop is `G:all`
    /// (local = position in the loop); a 9+9 pairing appends the second loop's rows.
    public static func expectedRows(
        option: WatchCourseOption,
        backOption: WatchCourseOption?,
        loopKey: String
    ) throws -> [WatchTemplateHoleRow] {
        var loops: [(globalId: Int, half: String, size: Int)] = []
        if option.playableHoleCount == 18 {
            guard backOption == nil,
                  let loop = WatchCourseSelection.halfLoop(loopKey: loopKey),
                  loop.globalId == option.globalId else {
                throw WatchRoundIdentityError.nonCanonicalLoopKey
            }
            loops = loop.halves.map { (globalId: loop.globalId, half: $0, size: 9) }
        } else {
            guard loopKey == WatchCourseSelection.loopKey(front: option, back: backOption) else {
                throw WatchRoundIdentityError.nonCanonicalLoopKey
            }
            loops.append((globalId: option.globalId, half: "all", size: option.playableHoleCount))
            if let backOption {
                loops.append((globalId: backOption.globalId, half: "all", size: backOption.playableHoleCount))
            }
        }
        var rows: [WatchTemplateHoleRow] = []
        var number = 1
        for loop in loops {
            guard loop.size > 0 else { throw WatchRoundIdentityError.invalidRoundLoops }
            let sourceStart = WatchCourseSelection.physicalStartHole(loop.half)
            for offset in 0..<loop.size {
                rows.append(WatchTemplateHoleRow(
                    number: number,
                    globalId: loop.globalId,
                    sourceLocalHole: sourceStart + offset
                ))
                number += 1
            }
        }
        return rows
    }

    /// Throws unless the loop key is canonical for `option` / `backOption` (order and repeats
    /// preserved), the hole states are exactly the expected round positions, and each hole's
    /// `globalId` / `sourceLocalHole` match its loop row. A provisional (`pending`) row that predates
    /// source identity may omit `sourceLocalHole`; it never carries course facts.
    public func validateIdentity() throws {
        let rows = try Self.expectedRows(option: option, backOption: backOption, loopKey: loopKey)
        let byNumber = Dictionary(uniqueKeysWithValues: rows.map { ($0.number, $0) })
        var seen = Set<Int>()
        for state in holeStates {
            guard seen.insert(state.hole).inserted,
                  let row = byNumber[state.hole],
                  state.globalId == row.globalId else {
                throw WatchRoundIdentityError.holeDoesNotMatchItsLoop(state.hole)
            }
            if let local = state.sourceLocalHole {
                guard local == row.sourceLocalHole else {
                    throw WatchRoundIdentityError.holeDoesNotMatchItsLoop(state.hole)
                }
            } else if state.geometryCoverage?.caseInsensitiveCompare("pending") != .orderedSame {
                throw WatchRoundIdentityError.holeDoesNotMatchItsLoop(state.hole)
            }
        }
        guard seen == Set(byNumber.keys) else { throw WatchRoundIdentityError.invalidRoundLoops }
    }

    public var hasValidIdentity: Bool {
        (try? validateIdentity()) != nil
    }
}

public struct WatchCourseImage: Equatable {
    public let globalId: Int
    public let hole: Int
    public let data: Data
    public let geometryRevision: String?

    public init(
        globalId: Int,
        hole: Int,
        data: Data,
        geometryRevision: String? = nil
    ) {
        self.globalId = globalId
        self.hole = hole
        self.data = data
        self.geometryRevision = geometryRevision
    }
}

public struct WatchCourseDownload: Equatable {
    public let template: WatchCourseTemplate
    public let images: [WatchCourseImage]
}

/// The turn's request for the second nine of a round started on one half of an 18-hole course.
public struct WatchSecondLoopRequest: Equatable {
    public let roundId: String
    /// The round's current one-half loop key, e.g. `41825:back`.
    public let firstLoopKey: String
    /// `"front"` / `"back"`; the same half as the first loop is allowed.
    public let secondHalf: String
    public let teeBox: String?

    public init(roundId: String, firstLoopKey: String, secondHalf: String, teeBox: String?) {
        self.roundId = roundId
        self.firstLoopKey = firstLoopKey
        self.secondHalf = secondHalf
        self.teeBox = teeBox
    }

    /// `G:first+G:second`, or nil when `firstLoopKey` is not one half of an 18-hole course.
    public var loopKey: String? {
        guard let loop = WatchCourseSelection.halfLoop(loopKey: firstLoopKey),
              loop.halves.count == 1,
              let second = WatchCourseSelection.normalizedHalf(secondHalf) else { return nil }
        return "\(firstLoopKey)+\(loop.globalId):\(second)"
    }
}

/// Round holes 10–18 for the second nine (physical holes of the chosen half, in play order), or an
/// honest reason they are not available. Holes are never invented.
public enum WatchSecondLoopResult: Equatable {
    case ready(loopKey: String, holeStates: [WatchRoundState])
    case unavailable(String)
}
