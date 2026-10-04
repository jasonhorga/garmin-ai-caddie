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

/// One loop of a round in play order (B4b-2 package v2). `roundStartHole` is on the round-hole
/// axis (1 or 10); `sourceStartHole` is on the physical axis of `globalId` (1 for a 9-hole loop or
/// a front half, 10 for a back half).
public struct RoundLoop: Codable, Equatable, Hashable {
    public let globalId: Int
    /// "all" (a 9-hole loop) · "front" / "back" (a half of an 18-hole course).
    public let half: String
    public let roundStartHole: Int
    public let sourceStartHole: Int
    public let holeCount: Int

    public init(globalId: Int, half: String, roundStartHole: Int, sourceStartHole: Int, holeCount: Int) {
        self.globalId = globalId
        self.half = half
        self.roundStartHole = roundStartHole
        self.sourceStartHole = sourceStartHole
        self.holeCount = holeCount
    }

    public var entry: RoundLoopEntry { RoundLoopEntry(globalId: globalId, half: half) }

    /// True for a half of an 18-hole course, whose holes show their physical number.
    public var isCourseHalf: Bool { half == "front" || half == "back" }

    public func contains(roundHole: Int) -> Bool {
        roundHole >= roundStartHole && roundHole < roundStartHole + holeCount
    }
}

/// One requested loop: a course and which of its nines (the `loops=` request unit).
public struct RoundLoopEntry: Codable, Equatable, Hashable {
    public let globalId: Int
    public let half: String

    public init(globalId: Int, half: String) {
        self.globalId = globalId
        self.half = half
    }

    public static let holesPerLoop = 9

    /// 1 for a 9-hole loop or a front half, 10 for a back half.
    public var sourceStartHole: Int { half == "back" ? 10 : 1 }

    /// The canonical ordered identity: order and duplicates preserved ("41825:back+41825:front").
    public static func loopKey(_ entries: [RoundLoopEntry]) -> String {
        entries.map { "\($0.globalId):\($0.half)" }.joined(separator: "+")
    }

    /// Parse a canonical loop key back into ordered entries; nil for anything malformed.
    public static func entries(loopKey: String) -> [RoundLoopEntry]? {
        let parts = loopKey.split(separator: "+", omittingEmptySubsequences: false)
        guard (1...2).contains(parts.count) else { return nil }
        var entries: [RoundLoopEntry] = []
        for part in parts {
            let fields = part.split(separator: ":", omittingEmptySubsequences: false)
            guard fields.count == 2,
                  let globalId = Int(fields[0]), globalId > 0,
                  ["all", "front", "back"].contains(String(fields[1])) else { return nil }
            entries.append(RoundLoopEntry(globalId: globalId, half: String(fields[1])))
        }
        return entries
    }

    /// The `loops=` query value ("41825:back,41825:front").
    public static func query(_ entries: [RoundLoopEntry]) -> String {
        entries.map { "\($0.globalId):\($0.half)" }.joined(separator: ",")
    }

    /// A whole physical course in its usual order: an 18-hole course is its two halves, a 9-hole
    /// loop is itself. This is the canonical template identity for offline composition.
    public static func wholeCourse(globalId: Int, holes: Int) -> [RoundLoopEntry] {
        holes == holesPerLoop
            ? [RoundLoopEntry(globalId: globalId, half: "all")]
            : [RoundLoopEntry(globalId: globalId, half: "front"), RoundLoopEntry(globalId: globalId, half: "back")]
    }

    /// The loop table the server returns for these entries.
    public static func table(_ entries: [RoundLoopEntry]) -> [RoundLoop] {
        entries.enumerated().map { index, entry in
            RoundLoop(
                globalId: entry.globalId,
                half: entry.half,
                roundStartHole: 1 + index * holesPerLoop,
                sourceStartHole: entry.sourceStartHole,
                holeCount: holesPerLoop
            )
        }
    }
}

/// A package whose v2 round identity (B4b-2 contract §6) is contradictory or incomplete.
public enum RoundIdentityError: Error, Equatable {
    case unsupportedSchema(String)
    case invalidRoundLoops
    case nonCanonicalLoopKey
    case holeDoesNotMatchItsLoop(Int)
}

public struct LiveRoundPackage: Codable, Equatable {
    /// The only package contract this client accepts. Every package is checked with
    /// ``validatedRoundIdentity()`` when it arrives from the server (SyncClient) and whenever it is
    /// written to or read from durable storage (OfflineStore: round, current pointer, home,
    /// templates — invalid bytes are removed and re-downloaded). v1 packages fail to decode or are
    /// rejected, and source identity is never fabricated from `number`.
    public static let supportedSchema = "ai-caddie-live-round-package-v2"

    public let schema: String
    public let roundId: String
    public let dataMode: String
    public let sourceCoverage: SourceCoverage
    public let missingData: [[String: JSONValue]]
    public let playerProfile: PlayerProfile
    public let course: Course
    public let holes: [Hole]
    /// The round's loops in play order and their canonical key (B4b-2). Hole `number` is the
    /// round hole; `sourceGlobalId` / `sourceLocalHole` the physical hole; `courseHoleNumber` the
    /// presentation number.
    public let roundLoops: [RoundLoop]
    public let loopKey: String
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
        schema: String = LiveRoundPackage.supportedSchema,
        roundId: String,
        dataMode: String,
        sourceCoverage: SourceCoverage,
        missingData: [[String: JSONValue]],
        playerProfile: PlayerProfile,
        course: Course,
        holes: [Hole],
        roundLoops: [RoundLoop],
        loopKey: String,
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
        self.roundLoops = roundLoops
        self.loopKey = loopKey
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

    /// Carry precise prep rows from `retained` (the same course and Tee) into this package wherever
    /// this package's row for the same physical hole is not precise and the hole's geometry
    /// revision is unchanged. A network package's lightweight rows therefore never displace an
    /// already-downloaded precise map: the precise row is the same fact, just complete (device
    /// review, build 77: a second start of the same course re-waited on every hole).
    public func carryingPrecisePrep(from retained: LiveRoundPackage?) -> LiveRoundPackage {
        guard let retained,
              retained.course.teeBox.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                == course.teeBox.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() else {
            return self
        }
        var retainedByPhysicalHole: [String: CoursePrepHole] = [:]
        for hole in retained.holes {
            guard let row = retained.coursePrep?.holes.first(where: { $0.hole == hole.number }),
                  row.isPreciseOfflineMap else { continue }
            retainedByPhysicalHole["\(hole.sourceGlobalId):\(hole.sourceLocalHole)"] = row
        }
        guard !retainedByPhysicalHole.isEmpty else { return self }
        var rows = Dictionary(uniqueKeysWithValues: (coursePrep?.holes ?? []).map { ($0.hole, $0) })
        var changed = false
        for hole in holes {
            let current = rows[hole.number]
            guard current?.isPreciseOfflineMap != true,
                  let precise = retainedByPhysicalHole["\(hole.sourceGlobalId):\(hole.sourceLocalHole)"] else {
                continue
            }
            let expected = hole.geometryRevision ?? current?.geometryRevision
            guard Self.sameRevision(expected, precise.geometryRevision) else { continue }
            rows[hole.number] = precise.renumbered(to: hole.number)
            changed = true
        }
        guard changed else { return self }
        return replacingCoursePrep(CoursePrepPackage(
            schema: coursePrep?.schema ?? "ai-caddie-course-prep-v1",
            globalId: coursePrep?.globalId ?? course.globalId,
            holes: rows.values.sorted { $0.hole < $1.hole },
            missingData: coursePrep?.missingData
        ))
    }

    private static func sameRevision(_ lhs: String?, _ rhs: String?) -> Bool {
        guard let lhs = lhs?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              let rhs = rhs?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              !lhs.isEmpty, !rhs.isEmpty else { return false }
        return lhs == rhs
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
            roundLoops: roundLoops,
            loopKey: loopKey,
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
            roundLoops: roundLoops,
            loopKey: loopKey,
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
            roundLoops: roundLoops,
            loopKey: loopKey,
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
    /// change this value, while adding / removing / reordering a loop does, so SwiftUI can refresh
    /// the live destination exactly when navigation truth changes.
    public var holeSetIdentity: String {
        loopKey + "|" + holes
            .sorted { $0.number < $1.number }
            .map { "\($0.number):\($0.sourceGlobalId):\($0.sourceLocalHole)" }
            .joined(separator: "|")
    }

    /// The complete v2 identity invariant, checked on every package that arrives from the server:
    /// the v2 schema; with playable holes, one or two loops starting on round holes 1 then 10,
    /// nine holes each, `sourceStartHole` matching `half`, the canonical `loopKey`, unique hole
    /// numbers and every hole on its row (physical course, local hole and course number). A
    /// package without holes names no loop. Throws ``RoundIdentityError``; returns `self`.
    @discardableResult
    public func validatedRoundIdentity() throws -> LiveRoundPackage {
        try Self.validateRoundIdentity(
            schema: schema,
            roundLoops: roundLoops,
            loopKey: loopKey,
            holes: holes.map {
                RoundIdentityHole(
                    number: $0.number,
                    sourceGlobalId: $0.sourceGlobalId,
                    sourceLocalHole: $0.sourceLocalHole,
                    courseHoleNumber: $0.courseHoleNumber
                )
            }
        )
        return self
    }

    /// The identity fields of one hole, as the shared validation rule set sees them.
    public struct RoundIdentityHole: Decodable, Equatable {
        public let number: Int
        public let sourceGlobalId: Int
        public let sourceLocalHole: Int
        public let courseHoleNumber: Int

        public init(number: Int, sourceGlobalId: Int, sourceLocalHole: Int, courseHoleNumber: Int) {
            self.number = number
            self.sourceGlobalId = sourceGlobalId
            self.sourceLocalHole = sourceLocalHole
            self.courseHoleNumber = courseHoleNumber
        }
    }

    /// The shared v2 round-identity rule set (server `validate_round_identity`, Watch decoding and
    /// this are all tested against `round_identity_cases.json`).
    public static func validateRoundIdentity(
        schema: String,
        roundLoops: [RoundLoop],
        loopKey: String,
        holes: [RoundIdentityHole]
    ) throws {
        guard schema == supportedSchema else { throw RoundIdentityError.unsupportedSchema(schema) }
        if holes.isEmpty {
            guard roundLoops.isEmpty, loopKey.isEmpty else { throw RoundIdentityError.invalidRoundLoops }
            return
        }
        guard (1...2).contains(roundLoops.count) else { throw RoundIdentityError.invalidRoundLoops }
        var expected: [Int: (globalId: Int, localHole: Int, courseHole: Int)] = [:]
        for (index, loop) in roundLoops.enumerated() {
            guard ["all", "front", "back"].contains(loop.half),
                  loop.globalId > 0,
                  loop.roundStartHole == 1 + index * RoundLoopEntry.holesPerLoop,
                  loop.sourceStartHole == loop.entry.sourceStartHole,
                  loop.holeCount == RoundLoopEntry.holesPerLoop else {
                throw RoundIdentityError.invalidRoundLoops
            }
            for offset in 0..<RoundLoopEntry.holesPerLoop {
                let number = loop.roundStartHole + offset
                let local = loop.sourceStartHole + offset
                expected[number] = (loop.globalId, local, loop.isCourseHalf ? local : number)
            }
        }
        guard loopKey == RoundLoopEntry.loopKey(roundLoops.map(\.entry)) else {
            throw RoundIdentityError.nonCanonicalLoopKey
        }
        var seen = Set<Int>()
        for hole in holes {
            guard seen.insert(hole.number).inserted,
                  let row = expected[hole.number],
                  row.globalId == hole.sourceGlobalId,
                  row.localHole == hole.sourceLocalHole,
                  row.courseHole == hole.courseHoleNumber else {
                throw RoundIdentityError.holeDoesNotMatchItsLoop(hole.number)
            }
        }
        guard seen == Set(expected.keys) else { throw RoundIdentityError.invalidRoundLoops }
    }

    /// The round's loops as request entries, in play order (the `loops=` of this package).
    public var loopEntries: [RoundLoopEntry] { roundLoops.map(\.entry) }

    /// The second loop once the round has one (added at the turn, or started as a pair).
    public var secondLoop: RoundLoop? { roundLoops.count > 1 ? roundLoops[1] : nil }

    /// README §8 lock: the second loop can change until its first hole has anything recorded —
    /// any event of this round on a round hole at or after `roundLoops[1].roundStartHole`. Round
    /// holes, not physical ones, so 后→前 locks on round hole 10 exactly like 前→后.
    public func isSecondLoopLocked(by events: [LiveRoundEvent]) -> Bool {
        guard let start = secondLoop?.roundStartHole else { return false }
        return events.contains { $0.roundId == roundId && $0.hole >= start }
    }

    /// The loop that owns a round hole.
    public func loop(containingRoundHole number: Int) -> RoundLoop? {
        roundLoops.first { $0.contains(roundHole: number) }
    }

    /// The course's own number for a round hole: the physical hole on a half of an 18-hole course,
    /// the round number on a 9-hole loop. Presentation only — never a key.
    public func courseHoleNumber(forRoundHole number: Int) -> Int {
        holes.first { $0.number == number }?.courseHoleNumber ?? number
    }

    /// The canonical whole-course entries of `globalId` as this round knows them: a 9-hole loop
    /// is itself (`G:all`), an 18-hole course is its two halves in the usual order.
    public func wholeCourseEntries(globalId: Int) -> [RoundLoopEntry]? {
        let halves = Set(roundLoops.filter { $0.globalId == globalId }.map(\.half))
        if halves.contains("all") { return [RoundLoopEntry(globalId: globalId, half: "all")] }
        guard !halves.isEmpty else { return nil }
        return RoundLoopEntry.wholeCourse(globalId: globalId, holes: RoundLoopEntry.holesPerLoop * 2)
    }

    /// True when this package is already the canonical whole-course template of its course.
    public var isWholeCourseTemplate: Bool {
        guard let entries = wholeCourseEntries(globalId: course.globalId) else { return false }
        return loopKey == RoundLoopEntry.loopKey(entries)
    }

    /// The canonical physical template (`G:front+G:back` or `G:all`) of this package's course,
    /// re-projected from whatever order the round was played in. Nil when the round does not
    /// carry every physical hole of the course (e.g. one half only) — nothing is made up.
    public func wholeCourseTemplate() -> LiveRoundPackage? {
        if isWholeCourseTemplate { return self }
        guard let entries = wholeCourseEntries(globalId: course.globalId) else { return nil }
        return LiveRoundPackage.projecting(entries, templates: [course.globalId: self], roundId: roundId)
    }

    /// Project an ordered round from whole-course templates keyed by physical course id — the
    /// offline path, which yields the server's `number → (sourceGlobalId, sourceLocalHole,
    /// courseHoleNumber)` table for the same `loops=`.
    public static func projecting(
        _ entries: [RoundLoopEntry],
        templates: [Int: LiveRoundPackage],
        roundId: String
    ) -> LiveRoundPackage? {
        guard (1...2).contains(entries.count),
              let first = entries.first,
              let base = templates[first.globalId] else { return nil }
        let courseName = base.course.venueDisplayName
        var projected = ProjectedLoop.empty
        var clubProfiles = base.clubProfiles
        var missingData = base.missingData
        for (index, entry) in entries.enumerated() {
            guard let template = templates[entry.globalId],
                  let loop = template.projectedLoop(
                    entry,
                    roundStartHole: 1 + index * RoundLoopEntry.holesPerLoop,
                    roundId: roundId,
                    courseName: courseName
                  ) else { return nil }
            projected = projected.appending(loop)
            if clubProfiles.isEmpty { clubProfiles = template.clubProfiles }
            if template.course.globalId != base.course.globalId {
                missingData += template.missingData
            }
        }
        return base.assembling(
            projected,
            entries: entries,
            roundId: roundId,
            clubProfiles: clubProfiles,
            missingData: missingData
        )
    }

    /// Add the second loop at the turn from an installed whole-course template, keeping this
    /// round's first loop exactly as it is. The second loop keeps its physical identity and is
    /// numbered after the first loop in play order.
    public func composingSecondLoop(
        _ entry: RoundLoopEntry,
        from template: LiveRoundPackage,
        roundId: String
    ) -> LiveRoundPackage? {
        guard let first = roundLoops.first else { return nil }
        let courseName = course.venueDisplayName
        let firstHoles = holes
            .filter { first.contains(roundHole: $0.number) }
            .sorted { $0.number < $1.number }
        guard firstHoles.count == first.holeCount,
              let second = template.projectedLoop(
                entry,
                roundStartHole: first.roundStartHole + first.holeCount,
                roundId: roundId,
                courseName: courseName
              ) else { return nil }
        let firstNumbers = Set(firstHoles.map(\.number))
        let firstLoop = ProjectedLoop(
            holes: firstHoles,
            prep: coursePrep?.holes.filter { firstNumbers.contains($0.hole) } ?? [],
            seeds: firstHoles.compactMap { hole in
                caddieContextSeeds.first(where: { $0.hole == hole.number })?.rebased(
                    roundId: roundId,
                    displayHole: hole.number,
                    courseName: courseName,
                    sourceGlobalId: hole.sourceGlobalId,
                    sourceLocalHole: hole.sourceLocalHole
                )
            },
            recent: recentHistory.holes.filter { firstNumbers.contains($0.number) }
        )
        return assembling(
            firstLoop.appending(second),
            entries: [first.entry, entry],
            roundId: roundId,
            clubProfiles: clubProfiles.isEmpty ? template.clubProfiles : clubProfiles,
            missingData: template.course.globalId == course.globalId
                ? missingData
                : missingData + template.missingData
        )
    }

    /// Remove the second loop (only before it is played — the caller owns the lock). Geometry /
    /// topo bytes stay in the course cache; only this round's playable hole set changes.
    public func removingSecondLoop() -> LiveRoundPackage? {
        guard roundLoops.count > 1, let first = roundLoops.first else { return nil }
        let kept = holes
            .filter { first.contains(roundHole: $0.number) }
            .sorted { $0.number < $1.number }
        guard !kept.isEmpty else { return nil }
        let numbers = Set(kept.map(\.number))
        return assembling(
            ProjectedLoop(
                holes: kept,
                prep: coursePrep?.holes.filter { numbers.contains($0.hole) } ?? [],
                seeds: caddieContextSeeds.filter { numbers.contains($0.hole) },
                recent: recentHistory.holes.filter { numbers.contains($0.number) }
            ),
            entries: [first.entry],
            roundId: roundId,
            clubProfiles: clubProfiles,
            missingData: missingData
        )
    }

    /// One loop's holes, prep rows, seeds and hole history taken from this whole-course template
    /// by physical identity and numbered from `roundStartHole`. Nil unless all nine physical holes
    /// of the loop are present — a missing hole is never made up.
    fileprivate func projectedLoop(
        _ entry: RoundLoopEntry,
        roundStartHole: Int,
        roundId: String,
        courseName: String
    ) -> ProjectedLoop? {
        let range = entry.sourceStartHole..<(entry.sourceStartHole + RoundLoopEntry.holesPerLoop)
        let sources = holes
            .filter { $0.sourceGlobalId == entry.globalId && range.contains($0.sourceLocalHole) }
            .sorted { $0.sourceLocalHole < $1.sourceLocalHole }
        guard sources.count == RoundLoopEntry.holesPerLoop,
              Set(sources.map(\.sourceLocalHole)).count == sources.count else { return nil }
        var loop = ProjectedLoop.empty
        for (index, source) in sources.enumerated() {
            let number = roundStartHole + index
            loop.holes.append(source.renumbered(
                to: number,
                courseHoleNumber: entry.half == "all" ? number : source.sourceLocalHole
            ))
            if let prep = coursePrep?.holes.first(where: { $0.hole == source.number }) {
                loop.prep.append(prep.renumbered(to: number))
            }
            if let seed = caddieContextSeeds.first(where: { $0.hole == source.number }) {
                loop.seeds.append(seed.rebased(
                    roundId: roundId,
                    displayHole: number,
                    courseName: courseName,
                    sourceGlobalId: source.sourceGlobalId,
                    sourceLocalHole: source.sourceLocalHole
                ))
            }
            if let recent = recentHistory.holes.first(where: { $0.number == source.number }) {
                loop.recent.append(HoleRecentHistory(
                    number: number,
                    sampleCount: recent.sampleCount,
                    averageToPar: recent.averageToPar,
                    repeatedIssues: recent.repeatedIssues
                ))
            }
        }
        return loop
    }

    fileprivate func assembling(
        _ loop: ProjectedLoop,
        entries: [RoundLoopEntry],
        roundId: String,
        clubProfiles: [ClubProfile],
        missingData: [[String: JSONValue]]
    ) -> LiveRoundPackage {
        let sortedHoles = loop.holes.sorted { $0.number < $1.number }
        let courseName = course.venueDisplayName
        let readyCount = sortedHoles.filter { $0.geometryCoverage == .ready }.count
        let coverageState: GeometryCoverageState = readyCount == sortedHoles.count
            ? .ready
            : (readyCount > 0 ? .partial : .missing)
        let prepRows = loop.prep.sorted { $0.hole < $1.hole }
        return LiveRoundPackage(
            schema: LiveRoundPackage.supportedSchema,
            roundId: roundId,
            dataMode: dataMode,
            sourceCoverage: sourceCoverage.replacing(
                requestedRoundId: roundId,
                holeCount: sortedHoles.count
            ),
            missingData: missingData,
            playerProfile: playerProfile,
            course: Course(
                globalId: course.globalId,
                name: courseName,
                teeBox: course.teeBox,
                venueName: course.venueName ?? courseName,
                venueNameSource: course.venueNameSource,
                segmentLabel: course.segmentLabel
            ),
            holes: sortedHoles,
            roundLoops: RoundLoopEntry.table(entries),
            loopKey: RoundLoopEntry.loopKey(entries),
            coursePrep: prepRows.isEmpty ? nil : CoursePrepPackage(
                schema: coursePrep?.schema ?? "ai-caddie-course-prep-v1",
                globalId: course.globalId,
                holes: prepRows,
                missingData: prepRows.count == sortedHoles.count ? nil : [
                    CoursePrepMissingData(
                        label: "offline_course_prep",
                        reason: "\(prepRows.count)/\(sortedHoles.count) locally composed hole maps"
                    )
                ]
            ),
            geometryCoverage: GeometryCoverage(
                state: coverageState,
                readyHoles: readyCount,
                totalHoles: sortedHoles.count
            ),
            readinessChecks: readinessChecks,
            caddieContextSeeds: loop.seeds.sorted { $0.hole < $1.hole },
            weatherSnapshot: weatherSnapshot,
            clubProfiles: clubProfiles,
            caddieDecisionEndpoint: caddieDecisionEndpoint,
            offlinePackageStatus: offlinePackageStatus,
            eventCursor: eventCursor,
            recentHistory: RecentHistory(
                course: recentHistory.course,
                rounds: recentHistory.rounds,
                holes: loop.recent.sorted { $0.number < $1.number }
            ),
            cachedCaddieRules: cachedCaddieRules,
            generatedAt: ISO8601DateFormatter().string(from: Date()),
            readinessState: readinessState,
            enrichmentState: nil
        )
    }
}

/// The per-loop pieces a round is assembled from.
fileprivate struct ProjectedLoop {
    var holes: [Hole]
    var prep: [CoursePrepHole]
    var seeds: [CaddieContextSeed]
    var recent: [HoleRecentHistory]

    static let empty = ProjectedLoop(holes: [], prep: [], seeds: [], recent: [])

    func appending(_ other: ProjectedLoop) -> ProjectedLoop {
        ProjectedLoop(
            holes: holes + other.holes,
            prep: prep + other.prep,
            seeds: seeds + other.seeds,
            recent: recent + other.recent
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
    /// Move the round number (and its presentation number); the physical identity never moves.
    func renumbered(to number: Int, courseHoleNumber: Int) -> Hole {
        Hole(
            number: number,
            par: par,
            yards: yards,
            geometryCoverage: geometryCoverage,
            geometryRevision: geometryRevision,
            sourceGlobalId: sourceGlobalId,
            sourceLocalHole: sourceLocalHole,
            courseHoleNumber: courseHoleNumber,
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
    /// Stable identity of the Garmin release-bound geometry used by prep/topo; nil when the server
    /// has no current release for the hole. (v1 packages are never played — contract §6.)
    public let geometryRevision: String?
    /// The physical hole: its Garmin course id and local hole (1–9 on a 9-hole loop, 1–18 on an
    /// 18-hole course). Required in package v2; geometry, topo, install and stats use only this.
    public let sourceGlobalId: Int
    public let sourceLocalHole: Int
    /// Presentation-only course number: the physical hole on a half of an 18-hole course, the
    /// round number on a 9-hole loop. Text only (header, scorecard, summary, review, Watch).
    public let courseHoleNumber: Int
    /// Selected Tee anchor from the same per-hole geometry; nil when the Tee has no position.
    public let teeLatitude: Double?
    public let teeLongitude: Double?

    public init(
        number: Int,
        par: Int,
        yards: Int?,
        geometryCoverage: GeometryCoverageState,
        geometryRevision: String? = nil,
        sourceGlobalId: Int,
        sourceLocalHole: Int,
        courseHoleNumber: Int,
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
        self.courseHoleNumber = courseHoleNumber
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
