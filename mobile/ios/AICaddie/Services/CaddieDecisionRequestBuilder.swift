import CoreLocation
import Foundation

public enum LiveCaddieDistance {
    /// A live GPS range is useful only while the player is plausibly on this hole. A stale fix from
    /// home or another hole must not outrank the downloaded Tee-to-green distance and create a
    /// 20,000-yard caddie sequence. Manual input remains authoritative but is still finite/positive.
    public static func resolve(
        manualM: Double?,
        liveMiddleM: Double?,
        staticMiddleM: Double?,
        holeYards: Int? = nil
    ) -> Double? {
        if let manualM, manualM.isFinite, manualM > 0 { return manualM }
        let nominalM = holeYards.flatMap { $0 > 0 ? CoursePrepRoute.metres(fromYards: Double($0)) : nil }
            ?? staticMiddleM
        let maximumPlausibleM = max(GeoDistance.maximumUsefulGreenMetres, (nominalM ?? 0) + 250)
        if let liveMiddleM,
           liveMiddleM.isFinite,
           liveMiddleM > 0,
           liveMiddleM <= maximumPlausibleM {
            return liveMiddleM
        }
        if let staticMiddleM, staticMiddleM.isFinite, staticMiddleM > 0 { return staticMiddleM }
        return nil
    }
}

public struct LiveCaddieInput {
    public let shotType: String
    public let distanceToPinM: Double?
    public let lie: String?
    public let coordinate: CLLocationCoordinate2D?
    public let targetCoordinate: CLLocationCoordinate2D?
    public let targetKind: String?
    public let horizontalAccuracyM: Double?
    public let capturedAt: String?
    public let strategyMode: String?
    public let requestedOptionId: String?
    public let visionFindings: [[String: JSONValue]]

    public init(
        shotType: String,
        distanceToPinM: Double? = nil,
        lie: String? = nil,
        coordinate: CLLocationCoordinate2D? = nil,
        targetCoordinate: CLLocationCoordinate2D? = nil,
        targetKind: String? = nil,
        horizontalAccuracyM: Double? = nil,
        capturedAt: String? = nil,
        strategyMode: String? = nil,
        requestedOptionId: String? = nil,
        visionFindings: [[String: JSONValue]] = []
    ) {
        self.shotType = shotType
        self.distanceToPinM = distanceToPinM
        self.lie = lie
        self.coordinate = coordinate
        self.targetCoordinate = targetCoordinate
        self.targetKind = targetKind
        self.horizontalAccuracyM = horizontalAccuracyM
        self.capturedAt = capturedAt
        self.strategyMode = strategyMode
        self.requestedOptionId = requestedOptionId
        self.visionFindings = visionFindings
    }
}

public final class CaddieDecisionRequestBuilder {
    public init() {}

    public func makeDecisionRequest(seed: CaddieContextSeed, input: LiveCaddieInput) -> CaddieDecisionRequest {
        var context = seed.context
        context["source"] = .string("ios_live")
        context["sourceRef"] = .string(seed.sourceRef)
        context["hole"] = .number(Double(seed.hole))
        context["requiredLiveInputs"] = .array(seed.requiredLiveInputs.map { JSONValue.string($0) })

        if let distanceToPinM = input.distanceToPinM,
           distanceToPinM.isFinite,
           distanceToPinM > 0,
           distanceToPinM <= GeoDistance.maximumUsefulGreenMetres {
            context["distanceToPin_m"] = .number(distanceToPinM)
        }
        if let lie = input.lie, !lie.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            context["lie"] = .string(lie)
        }
        if let coordinate = input.coordinate {
            var location: [String: JSONValue] = [
                "latitude": .number(coordinate.latitude),
                "longitude": .number(coordinate.longitude),
                "source": .string("ios_gps")
            ]
            if let horizontalAccuracyM = input.horizontalAccuracyM {
                location["horizontalAccuracyM"] = .number(horizontalAccuracyM)
            }
            if let capturedAt = input.capturedAt,
               !capturedAt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                location["capturedAt"] = .string(capturedAt)
            }
            context["currentLocation"] = .object(location)
            // The server has the authoritative surface polygons. Mark the initial UI value as an
            // automatic fallback so precise GPS classification may replace it with tee/fairway/
            // rough/bunker without treating the default picker value as a manual instruction.
            context["lieSource"] = .string("gps_auto")
        }
        if let targetCoordinate = input.targetCoordinate {
            var targetLocation: [String: JSONValue] = [
                "latitude": .number(targetCoordinate.latitude),
                "longitude": .number(targetCoordinate.longitude),
                "source": .string("ios_target")
            ]
            if let targetKind = input.targetKind, !targetKind.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                targetLocation["kind"] = .string(targetKind)
            }
            context["targetLocation"] = .object(targetLocation)
        }
        if let strategyMode = input.strategyMode, !strategyMode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            context["strategyMode"] = .string(strategyMode)
        }
        if let requestedOptionId = input.requestedOptionId,
           !requestedOptionId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            context["requestedOptionId"] = .string(requestedOptionId)
        }
        if !input.visionFindings.isEmpty {
            context["visionFindings"] = .array(input.visionFindings.map { .object($0) })
        }

        return CaddieDecisionRequest(shotType: input.shotType, context: context)
    }
}

/// A live hole must remain playable even when an older/lightweight package omitted its deferred
/// caddie seed. The current package already carries the factual hole, bag and (once available)
/// CoursePrep shot chain, so synthesize only the bounded decision input that the normal seed would
/// have transported. This does not run a second planner on the phone.
public enum LiveCaddieSeedFactory {
    public static func resolve(
        package: LiveRoundPackage,
        hole: Hole,
        prep: CoursePrepHole?
    ) -> CaddieContextSeed? {
        // ``holePrep`` can still be nil for the first frame while the package already contains
        // its one-hole/full CoursePrep payload. Use that package fact before falling back to a
        // bag-only seed; otherwise the first live request loses the route chain unnecessarily.
        let effectivePrep = prep ?? package.coursePrep?.holes.first(where: { $0.hole == hole.number })
        if let installed = package.caddieContextSeeds.first(where: { $0.hole == hole.number }) {
            // Packages are cached longer than a single app release. An older package can still
            // contain a valid identity/history seed while omitting the current bag, hole distance,
            // or CoursePrep chain. Returning it verbatim is what allowed the live request to fall
            // back to one short club and repeat it (the IMG-8160 ``3H -> 3H`` case). Treat the
            // package's current factual fields as authoritative, but retain dynamic/history facts
            // that are not regenerated by this local repair.
            guard needsFactualAugmentation(installed, package: package, hole: hole, prep: effectivePrep),
                  let factual = synthesize(package: package, hole: hole, prep: effectivePrep) else {
                return installed
            }
            return mergeInstalledSeed(installed, with: factual)
        }
        return synthesize(package: package, hole: hole, prep: effectivePrep)
    }

    private static func needsFactualAugmentation(
        _ seed: CaddieContextSeed,
        package: LiveRoundPackage,
        hole: Hole,
        prep: CoursePrepHole?
    ) -> Bool {
        let installedProfiles = profileCount(seed.context["clubProfiles"])
        let packageProfiles = package.clubProfiles.filter {
            $0.medianM.isFinite && $0.medianM > 0
        }.count
        let profileGap = installedProfiles == 0 || (packageProfiles > installedProfiles && packageProfiles >= 2)
        let hasDistance = ["yards", "distanceToPin_m", "holeRemaining_m", "canonicalPlanRouteLength_m"]
            .contains { positiveNumber(seed.context[$0]) }
        let missingDistance = !hasDistance && (hole.yards ?? 0) > 0
        let hasPlan: Bool = {
            guard case .array(let rows)? = seed.context["canonicalShotPlan"] else { return false }
            return !rows.isEmpty
        }()
        let missingPlan = !hasPlan && !(prep?.steps.isEmpty ?? true)
        let deferred = seed.enrichmentState?.lowercased() == "deferred"
        return profileGap || missingDistance || missingPlan || deferred
    }

    private static func mergeInstalledSeed(
        _ installed: CaddieContextSeed,
        with factual: CaddieContextSeed
    ) -> CaddieContextSeed {
        let authoritativeKeys: Set<String> = [
            "roundId", "sourceRef", "courseName", "globalId", "localHole", "hole", "displayHole",
            "par", "yards", "teeBox", "clubProfiles", "candidateRoutes", "candidateRoutesState",
            "candidateRoutesReason", "canonicalShotPlan", "canonicalPlanSource", "canonicalPlanVersion",
            "canonicalPlanRouteLength_m", "holeRemaining_m"
        ]
        var context = factual.context
        for (key, value) in installed.context where !authoritativeKeys.contains(key) {
            context[key] = value
        }
        // The synthesized context only carries coverage/revision. Preserve richer cached hazard
        // evidence while refreshing those two authority markers from the current hole package.
        if case .object(let installedGeometry)? = installed.context["geometry"],
           case .object(let factualGeometry)? = factual.context["geometry"] {
            var geometry = installedGeometry
            for (key, value) in factualGeometry {
                geometry[key] = value
            }
            context["geometry"] = .object(geometry)
        }
        if case .array(let installedRoutes)? = installed.context["candidateRoutes"],
           case .array(let factualRoutes)? = factual.context["candidateRoutes"],
           factualRoutes.isEmpty, !installedRoutes.isEmpty {
            context["candidateRoutes"] = .array(installedRoutes)
            context["candidateRoutesState"] = installed.context["candidateRoutesState"] ?? .string("ready")
        }

        var options = factual.offlineOptions
        var signatures = Set(options.map { "\(normalizedClub($0.clubName)):\(Int($0.carryM.rounded()))" })
        for option in installed.offlineOptions {
            let signature = "\(normalizedClub(option.clubName)):\(Int(option.carryM.rounded()))"
            if signatures.insert(signature).inserted {
                options.append(option)
            }
        }
        let selectedId = installed.selectedOfflineOptionId.flatMap { selected in
            options.contains(where: { $0.optionId == selected }) ? selected : nil
        } ?? factual.selectedOfflineOptionId
        let shotTypes = uniqueStrings(installed.shotTypes + factual.shotTypes)
        let requiredInputs = uniqueStrings(installed.requiredLiveInputs + factual.requiredLiveInputs)

        return CaddieContextSeed(
            hole: factual.hole,
            sourceRef: factual.sourceRef,
            shotTypes: shotTypes,
            requiredLiveInputs: requiredInputs,
            enrichmentState: factual.enrichmentState ?? installed.enrichmentState,
            context: context,
            selectedOfflineOptionId: selectedId,
            offlineOptions: options,
            evidence: factual.evidence + installed.evidence,
            missingData: installed.missingData + factual.missingData
        )
    }

    private static func profileCount(_ value: JSONValue?) -> Int {
        switch value {
        case .array(let rows):
            return rows.filter { profileHasCarry($0) }.count
        case .object(let rows):
            return rows.values.filter { profileHasCarry($0) }.count
        default:
            return 0
        }
    }

    private static func profileHasCarry(_ value: JSONValue) -> Bool {
        guard case .object(let row) = value else { return false }
        for key in ["median_m", "median", "carryM"] {
            if positiveNumber(row[key]) { return true }
        }
        return false
    }

    private static func positiveNumber(_ value: JSONValue?) -> Bool {
        guard case .number(let number) = value else { return false }
        return number.isFinite && number > 0
    }

    private static func uniqueStrings(_ values: [String]) -> [String] {
        var seen = Set<String>()
        return values.filter { seen.insert($0).inserted }
    }

    public static func synthesize(
        package: LiveRoundPackage,
        hole: Hole,
        prep: CoursePrepHole?
    ) -> CaddieContextSeed? {
        let sourceRef = "\(package.roundId):\(hole.number)"
        let profiles = package.clubProfiles.filter {
            $0.medianM.isFinite && $0.medianM > 0
        }
        let steps = canonicalSteps(prep?.steps ?? [], profiles: profiles)
        let firstStep = steps.first
        let fallbackProfile = fallbackProfile(for: hole, prep: prep, profiles: profiles)
        let primaryName = string(firstStep?["clubName"]) ?? fallbackProfile?.clubName
        let primaryCarry = number(firstStep?["targetCarryM"]) ?? fallbackProfile?.medianM
        guard let primaryName,
              !primaryName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let primaryCarry,
              primaryCarry.isFinite,
              primaryCarry > 0 else {
            return nil
        }

        var context: [String: JSONValue] = [
            "roundId": .string(package.roundId),
            "sourceRef": .string(sourceRef),
            "courseName": .string(package.course.venueDisplayName),
            "globalId": .number(Double(hole.sourceGlobalId ?? package.course.globalId)),
            "localHole": .number(Double(hole.sourceLocalHole ?? hole.number)),
            "hole": .number(Double(hole.number)),
            "displayHole": .number(Double(hole.number)),
            "par": .number(Double(hole.par)),
            "teeBox": .string(package.course.teeBox),
            "clubProfiles": .array(profiles.map { profile in
                .object([
                    "clubName": .string(profile.clubName),
                    "sampleSize": .number(Double(profile.sampleSize)),
                    "median_m": .number(profile.medianM),
                    "p10_m": .number(profile.p10M),
                    "p90_m": .number(profile.p90M),
                ])
            }),
            "geometry": .object([
                "coverage": .string(prep?.geometryCoverage ?? hole.geometryCoverage.rawValue),
                "geometryRevision": (prep?.geometryRevision ?? hole.geometryRevision).map(JSONValue.string) ?? .null,
            ]),
            "candidateRoutesState": .string("ready"),
        ]
        if let yards = hole.yards, yards > 0 {
            context["yards"] = .number(Double(yards))
        }
        if !steps.isEmpty {
            context["canonicalShotPlan"] = .array(steps.map(JSONValue.object))
            context["canonicalPlanSource"] = .string("course_prep")
            context["canonicalPlanVersion"] = .string("ai-caddie-shot-plan-v1")
        }
        if let routeLength = prep?.routeLenM, routeLength.isFinite, routeLength > 0 {
            context["canonicalPlanRouteLength_m"] = .number(routeLength)
            context["holeRemaining_m"] = .number(routeLength)
        }

        let options = offlineOptions(
            sourceRef: sourceRef,
            primaryName: primaryName,
            primaryCarry: primaryCarry,
            prep: prep,
            profiles: profiles
        )
        context["candidateRoutes"] = .array(options.map { option in
            .object([
                "id": .string(option.optionId),
                "label": .string(option.label),
                "club": .string(option.clubName),
                "carry_m": .number(option.carryM),
                "riskScore": .number(option.riskScore),
            ])
        })

        return CaddieContextSeed(
            hole: hole.number,
            sourceRef: sourceRef,
            shotTypes: ["tee", "approach", "recovery"],
            requiredLiveInputs: ["currentLocation", "lie"],
            enrichmentState: "local_factual_fallback",
            context: context,
            selectedOfflineOptionId: options.first?.optionId,
            offlineOptions: options,
            evidence: [[
                "label": .string("local_caddie_seed"),
                "value": .string(prep == nil ? "hole_and_bag" : "course_prep"),
                "sourceRef": .string(sourceRef),
            ]],
            missingData: [[
                "label": .string("server_caddie_seed"),
                "reason": .string("package omitted this hole's deferred seed; using factual local course and bag data"),
            ]]
        )
    }

    private static func canonicalSteps(
        _ source: [CoursePrepStep],
        profiles: [ClubProfile]
    ) -> [[String: JSONValue]] {
        source.enumerated().compactMap { index, step in
            let rawName = (step.clubName ?? step.club ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard !rawName.isEmpty, rawName != "-" else { return nil }
            let profile = matchingProfile(rawName, in: profiles)
            var row: [String: JSONValue] = [
                "clubName": .string(rawName),
                "planIndex": .number(Double(step.planIndex ?? index)),
            ]
            if let carry = step.targetCarryM ?? profile?.medianM,
               carry.isFinite, carry > 0 {
                row["targetCarryM"] = .number(carry)
            }
            if let value = step.routeOffsetM, value.isFinite, value >= 0 {
                row["routeOffsetM"] = .number(value)
            }
            if let value = step.landingM, value.isFinite, value >= 0 {
                row["landingM"] = .number(value)
            }
            if let value = step.expectedRemainingM, value.isFinite {
                row["expectedRemainingM"] = .number(value)
            }
            if let role = step.role, !role.isEmpty { row["role"] = .string(role) }
            row["planVersion"] = .string(step.planVersion ?? "ai-caddie-shot-plan-v1")
            return row
        }
    }

    private static func offlineOptions(
        sourceRef: String,
        primaryName: String,
        primaryCarry: Double,
        prep: CoursePrepHole?,
        profiles: [ClubProfile]
    ) -> [OfflineCaddieOption] {
        var rows: [(id: String, label: String, club: String, carry: Double, risk: Double)] = [
            ("stock", "推荐", primaryName, primaryCarry, 0),
        ]
        for route in prep?.candidateRoutes ?? [] {
            guard let club = route.club?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !club.isEmpty,
                  let carry = route.carryM ?? matchingProfile(club, in: profiles)?.medianM,
                  carry.isFinite,
                  carry > 0 else { continue }
            let rawID = route.id.trimmingCharacters(in: .whitespacesAndNewlines)
            rows.append((rawID.isEmpty ? "route-\(rows.count)" : rawID, "备选", club, carry, route.riskScore ?? 0))
        }

        var seen = Set<String>()
        return rows.compactMap { row in
            let signature = "\(normalizedClub(row.club)):\(Int(row.carry.rounded()))"
            guard seen.insert(signature).inserted else { return nil }
            let profile = matchingProfile(row.club, in: profiles)
            return OfflineCaddieOption(
                optionId: row.id,
                label: row.label,
                clubName: row.club,
                carryM: row.carry,
                p10M: profile?.p10M,
                p90M: profile?.p90M,
                sampleSize: profile?.sampleSize,
                confidence: (profile?.sampleSize ?? 0) >= 10 ? "medium" : "low",
                riskScore: row.risk,
                source: "ios_local_factual_seed",
                sourceRefs: [sourceRef]
            )
        }
    }

    private static func fallbackProfile(
        for hole: Hole,
        prep: CoursePrepHole?,
        profiles: [ClubProfile]
    ) -> ClubProfile? {
        if let teeClub = prep?.teeClub,
           let match = matchingProfile(teeClub, in: profiles) {
            return match
        }
        guard !profiles.isEmpty else { return nil }
        if hole.par >= 4 {
            return profiles.max(by: { $0.medianM < $1.medianM })
        }
        let target = prep?.routeLenM
            ?? hole.yards.map { CoursePrepRoute.metres(fromYards: Double($0)) }
            ?? profiles.map(\.medianM).max()
            ?? 0
        return profiles.min(by: { abs($0.medianM - target) < abs($1.medianM - target) })
    }

    private static func matchingProfile(_ name: String, in profiles: [ClubProfile]) -> ClubProfile? {
        let key = normalizedClub(name)
        return profiles.first { normalizedClub($0.clubName) == key }
    }

    private static func normalizedClub(_ value: String) -> String {
        zhClubDisplayName(zhClubName(value))
            .lowercased()
            .filter { $0.isLetter || $0.isNumber }
    }

    private static func string(_ value: JSONValue?) -> String? {
        guard case .string(let raw) = value else { return nil }
        return raw
    }

    private static func number(_ value: JSONValue?) -> Double? {
        guard case .number(let raw) = value else { return nil }
        return raw
    }
}

public enum LiveCaddieDecisionUsability {
    public static func hasRecommendation(_ response: CaddieDecisionResponse) -> Bool {
        if sequenceHasClub(response.selectedSequence) { return true }
        if optionHasClub(response.selectedOption ?? response.selected) { return true }
        if (response.sequences ?? []).contains(where: sequenceHasClub) { return true }
        return response.options.contains(where: optionHasClub)
    }

    private static func sequenceHasClub(_ row: [String: JSONValue]?) -> Bool {
        guard let row, case .array(let clubs) = row["clubs"] else { return false }
        return clubs.contains { value in
            guard case .object(let club) = value else { return false }
            return usableString(club["clubName"] ?? club["club"])
        }
    }

    private static func optionHasClub(_ row: [String: JSONValue]?) -> Bool {
        guard let row else { return false }
        if usableString(row["clubName"] ?? row["club"]) { return true }
        guard case .object(let recommendation) = row["clubRecommendation"],
              case .array(let clubs) = recommendation["clubs"] else { return false }
        return clubs.contains { value in
            guard case .object(let club) = value else { return false }
            return usableString(club["clubName"] ?? club["club"])
        }
    }

    private static func usableString(_ value: JSONValue?) -> Bool {
        guard case .string(let raw) = value else { return false }
        let normalized = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return !normalized.isEmpty && normalized != "-"
    }
}
