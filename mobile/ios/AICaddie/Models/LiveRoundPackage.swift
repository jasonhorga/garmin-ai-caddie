import Foundation

public enum GeometryCoverageState: String, Codable, Equatable {
    case ready
    case partial
    case missing
}

public enum OfflinePackageCacheState: String, Equatable {
    case ready
    case stale
    case expired
    case degraded
}

/// Optional caddie work that is intentionally hydrated when a later hole opens. The factual
/// course package remains one protocol; this metadata only tells clients which seed details are
/// provisional and must not be presented as complete offline hazard evidence.
public struct PackageEnrichmentState: Codable, Equatable {
    public let schema: String
    public let state: String
    public let strategy: String
    public let priorityHoles: [Int]
    public let readyHoles: [Int]
    public let pendingHoles: [Int]
    public let pendingEnrichment: [[String: JSONValue]]
    public let onDemandEndpoint: String
}

public struct LiveRoundPackage: Codable, Equatable {
    public let schema: String
    public let roundId: String
    public let dataMode: String
    public let sourceCoverage: SourceCoverage
    public let missingData: [[String: JSONValue]]
    public let playerProfile: PlayerProfile
    public let course: Course
    public let holes: [Hole]
    /// 当前视图的起始九洞:"front" / "back" / "all"(缺省视为 all)。后端按此过滤 holes/seeds。
    public let nine: String?
    public let coursePrep: CoursePrepPackage?
    public let geometryCoverage: GeometryCoverage
    public let readinessChecks: [PackageReadinessCheck]
    public let caddieContextSeeds: [CaddieContextSeed]
    public let enrichmentState: PackageEnrichmentState?
    public let weatherSnapshot: WeatherSnapshot
    public let clubProfiles: [ClubProfile]
    public let caddieDecisionEndpoint: String
    public let offlinePackageStatus: OfflinePackageStatus
    /// Cross-surface package gate. `blocked` means download/progress only; it is not a prep map.
    public let readinessState: String?
    public let eventCursor: EventCursor
    public let recentHistory: RecentHistory
    public let cachedCaddieRules: CachedCaddieRules
    public let generatedAt: String

    public init(
        schema: String = "ai-caddie-live-round-package-v1",
        roundId: String,
        dataMode: String,
        sourceCoverage: SourceCoverage,
        missingData: [[String: JSONValue]],
        playerProfile: PlayerProfile,
        course: Course,
        holes: [Hole],
        nine: String? = nil,
        coursePrep: CoursePrepPackage? = nil,
        geometryCoverage: GeometryCoverage,
        readinessChecks: [PackageReadinessCheck],
        caddieContextSeeds: [CaddieContextSeed],
        weatherSnapshot: WeatherSnapshot,
        clubProfiles: [ClubProfile],
        caddieDecisionEndpoint: String,
        offlinePackageStatus: OfflinePackageStatus,
        eventCursor: EventCursor,
        recentHistory: RecentHistory,
        cachedCaddieRules: CachedCaddieRules,
        generatedAt: String,
        readinessState: String? = nil,
        enrichmentState: PackageEnrichmentState? = nil
    ) {
        self.schema = schema
        self.roundId = roundId
        self.dataMode = dataMode
        self.sourceCoverage = sourceCoverage
        self.missingData = missingData
        self.playerProfile = playerProfile
        self.course = course
        self.holes = holes
        self.nine = nine
        self.coursePrep = coursePrep
        self.geometryCoverage = geometryCoverage
        self.readinessChecks = readinessChecks
        self.caddieContextSeeds = caddieContextSeeds
        self.enrichmentState = enrichmentState
        self.weatherSnapshot = weatherSnapshot
        self.clubProfiles = clubProfiles
        self.caddieDecisionEndpoint = caddieDecisionEndpoint
        self.offlinePackageStatus = offlinePackageStatus
        self.readinessState = readinessState
        self.eventCursor = eventCursor
        self.recentHistory = recentHistory
        self.cachedCaddieRules = cachedCaddieRules
        self.generatedAt = generatedAt
    }

    public func cacheState(now: Date = Date()) -> OfflinePackageCacheState {
        offlinePackageStatus.cacheState(now: now)
    }

    /// A live package may start with factual route data while precise assets are prepared separately.
    /// Once the background download fills it, every round hole must have both a retained
    /// route/projection and precise geometry. A CourseView-only outline remains useful for online
    /// play, but is not a complete offline map.
    public var hasCompleteOfflineCoursePrep: Bool {
        guard !holes.isEmpty, let preparedHoles = coursePrep?.holes else { return false }
        let preciseDrawable: Set<Int> = Set(preparedHoles.compactMap { prep -> Int? in
            guard prep.resolvedMapOverlay != nil,
                  prep.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame else {
                return nil
            }
            return prep.hole
        })
        return Set(holes.map(\.number)).isSubset(of: preciseDrawable)
    }

    /// A local template is safe for immediate live play only when the caddie contract is also
    /// complete. Older templates may have every topo bitmap but no per-hole seed; entering those
    /// templates would bypass the online decision request and leave the first hole on fallback data.
    public var hasCaddieContextForEveryHole: Bool {
        guard !holes.isEmpty,
              !caddieDecisionEndpoint.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return false
        }
        let seededHoles = Set(caddieContextSeeds.map(\.hole))
        return holes.allSatisfy { seededHoles.contains($0.number) }
    }

    public func replacingCoursePrep(_ nextCoursePrep: CoursePrepPackage?) -> LiveRoundPackage {
        LiveRoundPackage(
            schema: schema,
            roundId: roundId,
            dataMode: dataMode,
            sourceCoverage: sourceCoverage,
            missingData: missingData,
            playerProfile: playerProfile,
            course: course,
            holes: holes,
            nine: nine,
            coursePrep: nextCoursePrep,
            geometryCoverage: geometryCoverage,
            readinessChecks: readinessChecks,
            caddieContextSeeds: caddieContextSeeds,
            weatherSnapshot: weatherSnapshot,
            clubProfiles: clubProfiles,
            caddieDecisionEndpoint: caddieDecisionEndpoint,
            offlinePackageStatus: offlinePackageStatus,
            eventCursor: eventCursor,
            recentHistory: recentHistory,
            cachedCaddieRules: cachedCaddieRules,
            generatedAt: generatedAt,
            readinessState: readinessState,
            enrichmentState: enrichmentState
        )
    }

    /// Keep the catalogue identity the player actually selected while retaining every package fact
    /// (global id, Tee, release revisions, geometry and event authority) from the server. Garmin's
    /// catalogue and package builders can expose different localized aliases for the same globalId;
    /// letting a background refresh swap those aliases makes the course appear to change mid-round.
    public func replacingCourseDisplayName(_ rawName: String?) -> LiveRoundPackage {
        guard let name = rawName?.trimmingCharacters(in: .whitespacesAndNewlines),
              !name.isEmpty,
              name != course.name else { return self }
        return LiveRoundPackage(
            schema: schema,
            roundId: roundId,
            dataMode: dataMode,
            sourceCoverage: sourceCoverage,
            missingData: missingData,
            playerProfile: playerProfile,
            course: Course(
                globalId: course.globalId,
                name: name,
                teeBox: course.teeBox,
                venueName: course.venueName,
                venueNameSource: course.venueNameSource,
                segmentLabel: course.segmentLabel
            ),
            holes: holes,
            nine: nine,
            coursePrep: coursePrep,
            geometryCoverage: geometryCoverage,
            readinessChecks: readinessChecks,
            caddieContextSeeds: caddieContextSeeds,
            weatherSnapshot: weatherSnapshot,
            clubProfiles: clubProfiles,
            caddieDecisionEndpoint: caddieDecisionEndpoint,
            offlinePackageStatus: offlinePackageStatus,
            eventCursor: eventCursor,
            recentHistory: recentHistory,
            cachedCaddieRules: cachedCaddieRules,
            generatedAt: generatedAt,
            readinessState: readinessState,
            enrichmentState: enrichmentState
        )
    }

    /// Reuse immutable course/geometry/caddie facts for a brand-new offline round without reusing
    /// the old round's identity or server cursor. Hole events live in OfflineStore separately and
    /// are therefore intentionally absent from this new identity.
    public func rebasedForOfflineStart(roundId: String, generatedAt: Date = Date()) -> LiveRoundPackage {
        let rebasedSeeds = caddieContextSeeds.map {
            $0.rebasedForOfflineStart(roundId: roundId, discardDynamicWeather: true)
        }
        var rebasedSeedRefs: [String: String] = [:]
        for (oldSeed, newSeed) in zip(caddieContextSeeds, rebasedSeeds) {
            rebasedSeedRefs[oldSeed.sourceRef] = newSeed.sourceRef
        }
        return LiveRoundPackage(
            schema: schema,
            roundId: roundId,
            dataMode: dataMode,
            sourceCoverage: SourceCoverage(
                state: sourceCoverage.state,
                dataMode: sourceCoverage.dataMode,
                requestedRoundId: roundId,
                selectedRoundId: nil,
                roundFound: false,
                availableRoundCount: sourceCoverage.availableRoundCount,
                holeCount: holes.count,
                clubProfileCount: sourceCoverage.clubProfileCount,
                playerStatsWindow: sourceCoverage.playerStatsWindow
            ),
            missingData: missingData,
            playerProfile: playerProfile,
            course: course,
            holes: holes,
            nine: nine,
            coursePrep: coursePrep,
            geometryCoverage: geometryCoverage,
            readinessChecks: readinessChecks.map { check in
                PackageReadinessCheck(
                    label: check.label,
                    state: check.state,
                    ready: check.ready,
                    total: check.total,
                    reason: check.reason,
                    sourceRefs: check.sourceRefs.map { rebasedSeedRefs[$0] ?? $0 }
                )
            },
            caddieContextSeeds: rebasedSeeds,
            // A course template can live for weeks. Its map, clubs and historical evidence remain
            // reusable, but its weather does not. Online revalidation supplies a fresh snapshot;
            // an offline start stays honest and makes no wind adjustment from prep-day conditions.
            weatherSnapshot: .offlineRefreshPending,
            clubProfiles: clubProfiles,
            caddieDecisionEndpoint: caddieDecisionEndpoint,
            offlinePackageStatus: offlinePackageStatus,
            eventCursor: EventCursor(
                serverSequence: 0,
                pendingEventCount: 0,
                clientId: eventCursor.clientId,
                lastAckedServerSequence: 0,
                replayEndpoint: nil
            ),
            recentHistory: recentHistory,
            cachedCaddieRules: cachedCaddieRules,
            generatedAt: ISO8601DateFormatter().string(from: generatedAt),
            readinessState: readinessState,
            enrichmentState: enrichmentState
        )
    }

    /// Stable identity of the playable hole set. Precise-map enrichment deliberately does not
    /// change this value, while adding/removing a physical nine does, so SwiftUI can refresh the
    /// live destination exactly when navigation truth changes.
    public var holeSetIdentity: String {
        holes
            .sorted { $0.number < $1.number }
            .map {
                "\($0.number):\($0.sourceGlobalId ?? course.globalId):\($0.sourceLocalHole ?? $0.number)"
            }
            .joined(separator: "|")
    }

    /// A composite 9+9 resets the source-local number at round hole 10. A same-loop A+A round has
    /// one global id, so source-id inequality alone is not a valid composite test.
    public var isCompositeNineRound: Bool {
        guard holes.count > 9,
              let firstBack = holes.sorted(by: { $0.number < $1.number }).first(where: {
                  $0.number > 9
              }) else { return false }
        return (firstBack.sourceLocalHole ?? firstBack.number) <= 9
    }

    /// Compose two already-installed physical loops without asking the server to rebuild or resend
    /// their geometry. The second loop keeps its factual source gid/local-hole identity while only
    /// its round/display number moves to 10...18.
    public func composingBackNine(
        from back: LiveRoundPackage,
        roundId: String
    ) -> LiveRoundPackage? {
        let frontHoles = holes.sorted { $0.number < $1.number }.filter { $0.number <= 9 }
        let backHoles = back.holes.sorted { $0.number < $1.number }.prefix(9)
        guard !frontHoles.isEmpty,
              frontHoles.count <= 9,
              !backHoles.isEmpty else { return nil }

        let offset = frontHoles.count
        let shiftedBackHoles = backHoles.enumerated().map { index, source in
            source.renumbered(
                to: offset + index + 1,
                sourceGlobalId: source.sourceGlobalId ?? back.course.globalId,
                sourceLocalHole: source.sourceLocalHole ?? source.number
            )
        }
        let mergedHoles = frontHoles + shiftedBackHoles
        let courseName = course.venueDisplayName

        let frontPrep = frontHoles.compactMap { roundHole in
            coursePrep?.holes.first(where: { $0.hole == roundHole.number })
        }
        let shiftedBackPrep = zip(Array(backHoles), shiftedBackHoles).compactMap { source, shifted in
            back.coursePrep?.holes.first(where: { $0.hole == source.number })?
                .renumbered(to: shifted.number)
        }
        let mergedPrepRows = frontPrep + shiftedBackPrep
        let mergedPrep: CoursePrepPackage? = mergedPrepRows.isEmpty ? nil : CoursePrepPackage(
            schema: coursePrep?.schema ?? back.coursePrep?.schema ?? "ai-caddie-course-prep-v1",
            globalId: course.globalId,
            holes: mergedPrepRows.sorted { $0.hole < $1.hole },
            missingData: mergedPrepRows.count == mergedHoles.count ? nil : [
                CoursePrepMissingData(
                    label: "offline_course_prep",
                    reason: "\(mergedPrepRows.count)/\(mergedHoles.count) locally composed hole maps"
                )
            ]
        )

        let frontSeeds = frontHoles.compactMap { roundHole in
            caddieContextSeeds.first(where: { $0.hole == roundHole.number })?.rebased(
                roundId: roundId,
                displayHole: roundHole.number,
                courseName: courseName,
                sourceGlobalId: roundHole.sourceGlobalId ?? course.globalId,
                sourceLocalHole: roundHole.sourceLocalHole ?? roundHole.number
            )
        }
        let shiftedBackSeeds = zip(Array(backHoles), shiftedBackHoles).compactMap { source, shifted in
            back.caddieContextSeeds.first(where: { $0.hole == source.number })?.rebased(
                roundId: roundId,
                displayHole: shifted.number,
                courseName: courseName,
                sourceGlobalId: shifted.sourceGlobalId ?? back.course.globalId,
                sourceLocalHole: shifted.sourceLocalHole ?? source.number
            )
        }
        let mergedSeeds = frontSeeds + shiftedBackSeeds
        let readyCount = mergedHoles.filter { $0.geometryCoverage == .ready }.count
        let coverageState: GeometryCoverageState = readyCount == mergedHoles.count
            ? .ready
            : (readyCount > 0 ? .partial : .missing)

        return LiveRoundPackage(
            schema: schema,
            roundId: roundId,
            dataMode: dataMode,
            sourceCoverage: sourceCoverage.replacing(
                requestedRoundId: roundId,
                holeCount: mergedHoles.count
            ),
            missingData: missingData + back.missingData,
            playerProfile: playerProfile,
            course: Course(
                globalId: course.globalId,
                name: courseName,
                teeBox: course.teeBox,
                venueName: course.venueName ?? courseName,
                venueNameSource: course.venueNameSource,
                segmentLabel: course.segmentLabel
            ),
            holes: mergedHoles,
            nine: "all",
            coursePrep: mergedPrep,
            geometryCoverage: GeometryCoverage(
                state: coverageState,
                readyHoles: readyCount,
                totalHoles: mergedHoles.count
            ),
            readinessChecks: readinessChecks,
            caddieContextSeeds: mergedSeeds,
            weatherSnapshot: weatherSnapshot,
            clubProfiles: clubProfiles.isEmpty ? back.clubProfiles : clubProfiles,
            caddieDecisionEndpoint: caddieDecisionEndpoint,
            offlinePackageStatus: offlinePackageStatus,
            eventCursor: eventCursor,
            recentHistory: recentHistory,
            cachedCaddieRules: cachedCaddieRules,
            generatedAt: ISO8601DateFormatter().string(from: Date()),
            readinessState: readinessState,
            enrichmentState: nil
        )
    }

    /// Remove a locally-added physical back loop immediately. Geometry/topo bytes stay in the
    /// course cache and can be reattached later; only this round's playable hole set changes.
    public func removingCompositeBackNine() -> LiveRoundPackage? {
        guard isCompositeNineRound else { return nil }
        return selectingExistingHoles(
            holes.filter { $0.number <= 9 },
            nine: "all"
        )
    }

    /// Local subset for an ordinary 18-hole course's front/back toggle. Expansion still requires
    /// an installed all-hole template (or the remote package) because absent holes are never made up.
    public func selectingExistingNine(_ nine: String) -> LiveRoundPackage? {
        let key = nine.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        switch key {
        case "front":
            return selectingExistingHoles(holes.filter { (1...9).contains($0.number) }, nine: key)
        case "back":
            return selectingExistingHoles(holes.filter { (10...18).contains($0.number) }, nine: key)
        case "all":
            return self
        default:
            return nil
        }
    }

    private func selectingExistingHoles(_ selected: [Hole], nine: String) -> LiveRoundPackage? {
        let selected = selected.sorted { $0.number < $1.number }
        guard !selected.isEmpty else { return nil }
        let numbers = Set(selected.map(\.number))
        let prepRows = coursePrep?.holes.filter { numbers.contains($0.hole) } ?? []
        let readyCount = selected.filter { $0.geometryCoverage == .ready }.count
        let coverageState: GeometryCoverageState = readyCount == selected.count
            ? .ready
            : (readyCount > 0 ? .partial : .missing)
        return LiveRoundPackage(
            schema: schema,
            roundId: roundId,
            dataMode: dataMode,
            sourceCoverage: sourceCoverage.replacing(
                requestedRoundId: roundId,
                holeCount: selected.count
            ),
            missingData: missingData,
            playerProfile: playerProfile,
            course: course,
            holes: selected,
            nine: nine,
            coursePrep: prepRows.isEmpty ? nil : CoursePrepPackage(
                schema: coursePrep?.schema ?? "ai-caddie-course-prep-v1",
                globalId: coursePrep?.globalId ?? course.globalId,
                holes: prepRows,
                missingData: prepRows.count == selected.count ? nil : coursePrep?.missingData
            ),
            geometryCoverage: GeometryCoverage(
                state: coverageState,
                readyHoles: readyCount,
                totalHoles: selected.count
            ),
            readinessChecks: readinessChecks,
            caddieContextSeeds: caddieContextSeeds.filter { numbers.contains($0.hole) },
            weatherSnapshot: weatherSnapshot,
            clubProfiles: clubProfiles,
            caddieDecisionEndpoint: caddieDecisionEndpoint,
            offlinePackageStatus: offlinePackageStatus,
            eventCursor: eventCursor,
            recentHistory: RecentHistory(
                course: recentHistory.course,
                rounds: recentHistory.rounds,
                holes: recentHistory.holes.filter { numbers.contains($0.number) }
            ),
            cachedCaddieRules: cachedCaddieRules,
            generatedAt: ISO8601DateFormatter().string(from: Date()),
            readinessState: readinessState,
            enrichmentState: nil
        )
    }

}

private extension SourceCoverage {
    func replacing(requestedRoundId: String, holeCount: Int) -> SourceCoverage {
        SourceCoverage(
            state: state,
            dataMode: dataMode,
            requestedRoundId: requestedRoundId,
            selectedRoundId: selectedRoundId,
            roundFound: roundFound,
            availableRoundCount: availableRoundCount,
            holeCount: holeCount,
            clubProfileCount: clubProfileCount,
            playerStatsWindow: playerStatsWindow
        )
    }
}

private extension Hole {
    func renumbered(
        to number: Int,
        sourceGlobalId: Int,
        sourceLocalHole: Int
    ) -> Hole {
        Hole(
            number: number,
            par: par,
            yards: yards,
            geometryCoverage: geometryCoverage,
            geometryRevision: geometryRevision,
            sourceGlobalId: sourceGlobalId,
            sourceLocalHole: sourceLocalHole,
            teeLatitude: teeLatitude,
            teeLongitude: teeLongitude
        )
    }
}

public struct SourceCoverage: Codable, Equatable {
    public let state: String
    public let dataMode: String
    public let requestedRoundId: String
    public let selectedRoundId: String?
    public let roundFound: Bool
    public let availableRoundCount: Int
    public let holeCount: Int
    public let clubProfileCount: Int
    /// The bounded history projection used to make this startup package.
    /// Older cached packages may omit it, so decoding remains backward-compatible.
    public let playerStatsWindow: String?
}

public struct PlayerProfile: Codable, Equatable {
    public let playerId: String
    public let displayName: String
    public let handedness: String
    public let schema: String?
    public let roundCount: Int?
    public let confidence: String?
    public let strengths: [PlayerProfileSignal]?
    public let weaknesses: [PlayerProfileSignal]?
    public let caddieBiases: [PlayerProfileSignal]?
    public let topStrength: PlayerProfileSignal?
    public let topWeakness: PlayerProfileSignal?
    public let sourceRefs: [String]?
    public let coverage: PlayerProfileCoverage?
}

public struct PlayerProfileSignal: Codable, Equatable, Identifiable {
    public var id: String { key ?? label ?? "player-profile-signal" }

    public let key: String?
    public let label: String?
    public let kind: String?
    public let phase: String?
    public let reason: String?
    public let severityScore: Double?
    public let value: Double?
    public let unit: String?
    public let direction: String?
    public let appliesTo: [String]?
    public let riskOptionIds: [String]?
    public let sourceRefs: [String]?
    public let coverage: PlayerProfileCoverage?
    public let confidence: String?
}

public struct PlayerProfileCoverage: Codable, Equatable {
    public let ready: Int?
    public let total: Int?
    public let pct: Double?
}

public struct Course: Codable, Equatable {
    public let globalId: Int
    public let name: String
    /// Backend-owned physical venue identity. Optional for packages cached
    /// before the canonical course-name contract was introduced.
    public let venueName: String?
    public let venueNameSource: String?
    public let segmentLabel: String?
    public let teeBox: String

    /// One physical venue title for user-facing round surfaces. A trusted
    /// Garmin snapshot may replace the provider spelling; a cached unmarked
    /// venue field never outranks the package's canonical `name`.
    public var venueDisplayName: String {
        MobileCourseDisplayLocalization.canonicalVenueName(
            providerName: name,
            venueName: venueName,
            venueNameSource: venueNameSource,
            segmentLabel: segmentLabel,
            globalId: globalId
        )
    }

    public init(
        globalId: Int,
        name: String,
        teeBox: String,
        venueName: String? = nil,
        venueNameSource: String? = nil,
        segmentLabel: String? = nil
    ) {
        self.globalId = globalId
        self.name = name
        self.venueName = venueName
        self.venueNameSource = venueNameSource
        self.segmentLabel = segmentLabel
        self.teeBox = teeBox
    }
}

public struct Hole: Codable, Equatable, Identifiable {
    public var id: Int { number }

    public let number: Int
    public let par: Int
    public let yards: Int?
    public let geometryCoverage: GeometryCoverageState
    /// Stable identity of the Garmin release-bound geometry used by prep/topo. Optional keeps
    /// packages saved by older app versions playable offline until the next online revalidation.
    public let geometryRevision: String?
    /// Source course id + local hole for this hole's geometry (composite rounds: holes 10–18 live
    /// in a second loop's gid). Optional → older payloads decode to nil and fall back to the course.
    public let sourceGlobalId: Int?
    public let sourceLocalHole: Int?
    /// Selected Tee anchor from the same per-hole geometry. Optional keeps cached v1 packages valid.
    public let teeLatitude: Double?
    public let teeLongitude: Double?

    public init(
        number: Int,
        par: Int,
        yards: Int?,
        geometryCoverage: GeometryCoverageState,
        geometryRevision: String? = nil,
        sourceGlobalId: Int? = nil,
        sourceLocalHole: Int? = nil,
        teeLatitude: Double? = nil,
        teeLongitude: Double? = nil
    ) {
        self.number = number
        self.par = par
        self.yards = yards
        self.geometryCoverage = geometryCoverage
        self.geometryRevision = geometryRevision
        self.sourceGlobalId = sourceGlobalId
        self.sourceLocalHole = sourceLocalHole
        self.teeLatitude = teeLatitude
        self.teeLongitude = teeLongitude
    }
}

public struct GeometryCoverage: Codable, Equatable {
    public let state: GeometryCoverageState
    public let readyHoles: Int
    public let totalHoles: Int
}

public struct PackageReadinessCheck: Codable, Equatable, Identifiable {
    public var id: String { label }

    public let label: String
    public let state: String
    public let ready: Int
    public let total: Int
    public let reason: String
    public let sourceRefs: [String]
    public let backGlobalId: Int? = nil
    public let nine: String? = nil
    public let teeBox: String? = nil
}

public struct CaddieContextSeed: Codable, Equatable, Identifiable {
    public var id: String { sourceRef }

    public let hole: Int
    public let sourceRef: String
    public let shotTypes: [String]
    public let requiredLiveInputs: [String]
    public let enrichmentState: String?
    public let context: [String: JSONValue]
    public let selectedOfflineOptionId: String?
    public let offlineOptions: [OfflineCaddieOption]
    public let evidence: [[String: JSONValue]]
    public let missingData: [[String: JSONValue]]

    enum CodingKeys: String, CodingKey {
        case hole
        case sourceRef
        case shotTypes
        case requiredLiveInputs
        case enrichmentState
        case context
        case selectedOfflineOptionId
        case offlineOptions
        case evidence
        case missingData
    }

    public init(
        hole: Int,
        sourceRef: String,
        shotTypes: [String],
        requiredLiveInputs: [String],
        enrichmentState: String? = nil,
        context: [String: JSONValue],
        selectedOfflineOptionId: String?,
        offlineOptions: [OfflineCaddieOption],
        evidence: [[String: JSONValue]],
        missingData: [[String: JSONValue]]
    ) {
        self.hole = hole
        self.sourceRef = sourceRef
        self.shotTypes = shotTypes
        self.requiredLiveInputs = requiredLiveInputs
        self.enrichmentState = enrichmentState
        self.context = context
        self.selectedOfflineOptionId = selectedOfflineOptionId
        self.offlineOptions = offlineOptions
        self.evidence = evidence
        self.missingData = missingData
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.hole = try container.decode(Int.self, forKey: .hole)
        self.sourceRef = try container.decode(String.self, forKey: .sourceRef)
        self.shotTypes = try container.decode([String].self, forKey: .shotTypes)
        self.requiredLiveInputs = try container.decode([String].self, forKey: .requiredLiveInputs)
        self.enrichmentState = try container.decodeIfPresent(String.self, forKey: .enrichmentState)
        self.context = try container.decode([String: JSONValue].self, forKey: .context)
        self.selectedOfflineOptionId = try container.decodeIfPresent(String.self, forKey: .selectedOfflineOptionId)
        let offlineOptions = try container.decodeIfPresent([OfflineCaddieOption].self, forKey: .offlineOptions)
        self.offlineOptions = offlineOptions ?? []
        self.evidence = try container.decode([[String: JSONValue]].self, forKey: .evidence)
        self.missingData = try container.decode([[String: JSONValue]].self, forKey: .missingData)
    }

    /// A cached seed contains both reusable golf evidence and identity that belongs to the round
    /// which originally downloaded it. Rebind only that runtime identity. Historical shot samples
    /// remain untouched so the recommendation keeps its real provenance.
    public func rebasedForOfflineStart(
        roundId: String,
        discardDynamicWeather: Bool = false
    ) -> CaddieContextSeed {
        let nextSourceRef = "\(roundId):\(hole)"
        var nextContext = context.mapValues {
            $0.replacingExactString(sourceRef, with: nextSourceRef)
        }
        nextContext["roundId"] = .string(roundId)
        nextContext["sourceRef"] = .string(nextSourceRef)
        if discardDynamicWeather {
            nextContext["weatherSnapshot"] = .object([
                "schema": .string("ai-caddie-weather-snapshot-v1"),
                "state": .string("missing"),
                "source": .string("missing"),
                "confidence": .string("low"),
                "missingData": .array([
                    .object([
                        "label": .string("weather_values"),
                        "reason": .string("course template weather is stale; refresh required"),
                    ])
                ]),
            ])
        }

        return CaddieContextSeed(
            hole: hole,
            sourceRef: nextSourceRef,
            shotTypes: shotTypes,
            requiredLiveInputs: requiredLiveInputs,
            enrichmentState: enrichmentState,
            context: nextContext,
            selectedOfflineOptionId: selectedOfflineOptionId,
            offlineOptions: offlineOptions.map {
                $0.replacingRuntimeSourceRef(sourceRef, with: nextSourceRef)
            },
            evidence: evidence.map { row in
                row.mapValues { $0.replacingExactString(sourceRef, with: nextSourceRef) }
            },
            missingData: missingData.map { row in
                row.mapValues { $0.replacingExactString(sourceRef, with: nextSourceRef) }
            }
        )
    }

    fileprivate func rebased(
        roundId: String,
        displayHole: Int,
        courseName: String,
        sourceGlobalId: Int,
        sourceLocalHole: Int
    ) -> CaddieContextSeed {
        let nextSourceRef = "\(roundId):\(displayHole)"
        var nextContext = context.mapValues {
            $0.replacingExactString(sourceRef, with: nextSourceRef)
        }
        nextContext["roundId"] = .string(roundId)
        nextContext["sourceRef"] = .string(nextSourceRef)
        nextContext["courseName"] = .string(courseName)
        nextContext["hole"] = .number(Double(displayHole))
        nextContext["displayHole"] = .number(Double(displayHole))
        nextContext["globalId"] = .number(Double(sourceGlobalId))
        nextContext["localHole"] = .number(Double(sourceLocalHole))
        if case .object(var historical)? = nextContext["historicalHole"] {
            historical["hole"] = .number(Double(displayHole))
            nextContext["historicalHole"] = .object(historical)
        }
        return CaddieContextSeed(
            hole: displayHole,
            sourceRef: nextSourceRef,
            shotTypes: shotTypes,
            requiredLiveInputs: requiredLiveInputs,
            enrichmentState: enrichmentState,
            context: nextContext,
            selectedOfflineOptionId: selectedOfflineOptionId,
            offlineOptions: offlineOptions.map {
                $0.replacingRuntimeSourceRef(sourceRef, with: nextSourceRef)
            },
            evidence: evidence.map { row in
                row.mapValues { $0.replacingExactString(sourceRef, with: nextSourceRef) }
            },
            missingData: missingData.map { row in
                row.mapValues { $0.replacingExactString(sourceRef, with: nextSourceRef) }
            }
        )
    }
}

public struct OfflineCaddieOption: Codable, Equatable, Identifiable {
    public var id: String { optionId }

    public let optionId: String
    public let label: String
    public let clubName: String
    public let carryM: Double
    public let p10M: Double?
    public let p90M: Double?
    public let sampleSize: Int?
    public let confidence: String?
    public let coverage: OfflineOptionCoverage?
    public let riskScore: Double
    public let source: String
    public let sourceRefs: [String]
    public let sampleRefs: [String]?
    public let missingData: [[String: JSONValue]]?

    public init(
        optionId: String,
        label: String,
        clubName: String,
        carryM: Double,
        p10M: Double? = nil,
        p90M: Double? = nil,
        sampleSize: Int? = nil,
        confidence: String? = nil,
        coverage: OfflineOptionCoverage? = nil,
        riskScore: Double,
        source: String,
        sourceRefs: [String],
        sampleRefs: [String]? = nil,
        missingData: [[String: JSONValue]]? = nil
    ) {
        self.optionId = optionId
        self.label = label
        self.clubName = clubName
        self.carryM = carryM
        self.p10M = p10M
        self.p90M = p90M
        self.sampleSize = sampleSize
        self.confidence = confidence
        self.coverage = coverage
        self.riskScore = riskScore
        self.source = source
        self.sourceRefs = sourceRefs
        self.sampleRefs = sampleRefs
        self.missingData = missingData
    }

    enum CodingKeys: String, CodingKey {
        case optionId = "id"
        case label
        case clubName
        case carryM
        case p10M
        case p90M
        case sampleSize
        case confidence
        case coverage
        case riskScore
        case source
        case sourceRefs
        case sampleRefs
        case missingData
    }

    fileprivate func replacingRuntimeSourceRef(
        _ oldSourceRef: String,
        with newSourceRef: String
    ) -> OfflineCaddieOption {
        OfflineCaddieOption(
            optionId: optionId,
            label: label,
            clubName: clubName,
            carryM: carryM,
            p10M: p10M,
            p90M: p90M,
            sampleSize: sampleSize,
            confidence: confidence,
            coverage: coverage,
            riskScore: riskScore,
            source: source,
            sourceRefs: sourceRefs.map { $0 == oldSourceRef ? newSourceRef : $0 },
            sampleRefs: sampleRefs,
            missingData: missingData?.map { row in
                row.mapValues { $0.replacingExactString(oldSourceRef, with: newSourceRef) }
            }
        )
    }
}

public struct OfflineOptionCoverage: Codable, Equatable {
    public let ready: Int
    public let total: Int
    public let pct: Double
}

public struct WeatherSnapshot: Codable, Equatable {
    public let schema: String
    public let state: String
    public let source: String
    public let confidence: String
    public let missingData: [WeatherMissingData]

    public static let offlineRefreshPending = WeatherSnapshot(
        schema: "ai-caddie-weather-snapshot-v1",
        state: "missing",
        source: "missing",
        confidence: "low",
        missingData: [WeatherMissingData(
            label: "weather_values",
            reason: "course template weather is stale; refresh required"
        )]
    )
}

public struct WeatherMissingData: Codable, Equatable {
    public let label: String
    public let reason: String

    public init(label: String, reason: String) {
        self.label = label
        self.reason = reason
    }
}

public struct ClubProfile: Codable, Equatable, Identifiable {
    public var id: String { clubName }

    public let clubName: String
    public let sampleSize: Int
    public let medianM: Double
    public let p10M: Double
    public let p90M: Double

    enum CodingKeys: String, CodingKey {
        case clubName
        case sampleSize
        case medianM = "median_m"
        case p10M = "p10_m"
        case p90M = "p90_m"
    }
}

public struct OfflinePackageStatus: Codable, Equatable {
    public let state: String
    public let preparedAt: String
    public let expiresAt: String
    public let cachePolicy: CachePolicy

    public var preparedAtDate: Date? {
        ISO8601DateFormatter().date(from: preparedAt)
    }

    public var expiresAtDate: Date? {
        ISO8601DateFormatter().date(from: expiresAt)
    }

    public func cacheState(now: Date) -> OfflinePackageCacheState {
        if state == "expired" {
            return .expired
        }
        if state == "degraded" {
            return .degraded
        }
        guard let expiresAtDate else {
            return .expired
        }
        if now >= expiresAtDate {
            return .expired
        }
        if let preparedAtDate,
           let staleAt = Calendar(identifier: .gregorian).date(
            byAdding: .hour,
            value: cachePolicy.staleAfterHours,
            to: preparedAtDate
           ),
           now >= staleAt
        {
            return .stale
        }
        return .ready
    }
}

public struct CachePolicy: Codable, Equatable {
    public let staleAfterHours: Int
    public let expiresAfterHours: Int
}

public struct EventCursor: Codable, Equatable {
    public let serverSequence: Int
    public let pendingEventCount: Int
    public let clientId: String?
    public let lastAckedServerSequence: Int?
    public let replayEndpoint: String?
}

public struct RecentHistory: Codable, Equatable {
    public let course: CourseRecentHistory
    public let rounds: [RecentRoundSummary]
    public let holes: [HoleRecentHistory]

    enum CodingKeys: String, CodingKey {
        case course
        case rounds
        case holes
    }

    public init(course: CourseRecentHistory, rounds: [RecentRoundSummary] = [], holes: [HoleRecentHistory]) {
        self.course = course
        self.rounds = rounds
        self.holes = holes
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.course = try container.decode(CourseRecentHistory.self, forKey: .course)
        let rounds = try container.decodeIfPresent([RecentRoundSummary].self, forKey: .rounds)
        self.rounds = rounds ?? []
        self.holes = try container.decode([HoleRecentHistory].self, forKey: .holes)
    }
}

public struct RecentRoundSummary: Codable, Equatable, Identifiable {
    public var id: String { roundId }

    public let roundId: String
    public let date: String
    public let courseName: String
    public let score: Int
    public let par: Int?
    public let toPar: Int?
    public let holesCompleted: Int
    /// 该盘球场第 1 洞的物理球场 globalId(后端 `_recent_history` 随 summary 下发,前九感知)。
    /// 首页「上一场」卡用它 + `SyncClient.topoImageURL(…, localHole: 1)` 取真实地形缩略图。
    /// 旧 payload 无此字段 → 合成 Codable 解码为 nil → 卡片回退纯文字,绝不造图。
    public let globalId: Int?
    public let sourceRefs: [String]
    public let backGlobalId: Int?
    public let nine: String?
    public let teeBox: String?
}

public struct CourseRecentHistory: Codable, Equatable {
    public let courseKey: String
    /// The BASE course name (e.g. "黑骑士"), collapsing the nine combo — counts span the whole course.
    public let courseName: String?
    public let roundCount: Int
    public let averageScore: Double?
    public let bestScore: Int?
    public let worstScore: Int?
    public let recentScores: [Int]
    public let roundIds: [String]
}

public struct HoleRecentHistory: Codable, Equatable, Identifiable {
    public var id: Int { number }

    public let number: Int
    public let sampleCount: Int
    public let averageToPar: Double?
    public let repeatedIssues: [RepeatedIssue]
}

public struct RepeatedIssue: Codable, Equatable {
    public let label: String
    public let count: Int
}

public struct CachedCaddieRules: Codable, Equatable {
    public let decisionContract: String
    public let offlineCapable: Bool
    public let requiredInputs: [String]
    public let degradeWhenMissing: [String]
}

private extension JSONValue {
    func replacingExactString(_ oldValue: String, with newValue: String) -> JSONValue {
        switch self {
        case .string(let value):
            return .string(value == oldValue ? newValue : value)
        case .object(let object):
            return .object(object.mapValues {
                $0.replacingExactString(oldValue, with: newValue)
            })
        case .array(let array):
            return .array(array.map {
                $0.replacingExactString(oldValue, with: newValue)
            })
        case .number(_), .bool(_), .null:
            return self
        }
    }
}
