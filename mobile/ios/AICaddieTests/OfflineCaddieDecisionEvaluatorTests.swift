import XCTest
@testable import AICaddie

final class OfflineCaddieDecisionEvaluatorTests: XCTestCase {
    func testLiveCaddieDistancePrefersManualThenLiveThenStaticMiddle() {
        XCTAssertEqual(
            LiveCaddieDistance.resolve(manualM: 141, liveMiddleM: 152, staticMiddleM: 163),
            141
        )
        XCTAssertEqual(
            LiveCaddieDistance.resolve(manualM: nil, liveMiddleM: 152, staticMiddleM: 163),
            152
        )
        XCTAssertEqual(
            LiveCaddieDistance.resolve(manualM: nil, liveMiddleM: nil, staticMiddleM: 163),
            163
        )
        XCTAssertNil(LiveCaddieDistance.resolve(manualM: nil, liveMiddleM: nil, staticMiddleM: nil))
    }

    func testOffCourseGPSFallsBackToDownloadedHoleDistance() {
        XCTAssertEqual(
            LiveCaddieDistance.resolve(
                manualM: nil,
                liveMiddleM: 20_000,
                staticMiddleM: 374,
                holeYards: 410
            ),
            374
        )
    }

    func testMakesAuditableOfflineDecisionFromSeedAndStrategy() throws {
        let package = try fixturePackage()
        let seed = try XCTUnwrap(package.caddieContextSeeds.first)
        let request = CaddieDecisionRequestBuilder().makeDecisionRequest(
            seed: seed,
            input: LiveCaddieInput(
                shotType: "approach",
                distanceToPinM: 151,
                lie: "rough",
                strategyMode: "attack"
            )
        )
        let evaluator = OfflineCaddieDecisionEvaluator()

        let decision = try XCTUnwrap(evaluator.makeDecision(seed: seed, request: request, strategyMode: "attack"))

        XCTAssertEqual(decision.schema, "ai-caddie-decision-v2")
        XCTAssertEqual(decision.decisionId, "offline-live-round-1-1-approach-attack")
        XCTAssertEqual(decision.sourceRef, seed.sourceRef)
        XCTAssertEqual(decision.shotType, "approach")
        XCTAssertEqual(decision.phase, "Approach")
        XCTAssertEqual(decision.selectedOptionId, "attack")
        XCTAssertEqual(decision.selectedOption?["clubName"], .string("7I"))
        XCTAssertEqual(decision.selected?["carryM"], .number(156))
        XCTAssertEqual(decision.confidence["level"], .string("medium"))
        XCTAssertEqual(decision.context["strategyMode"], .string("attack"))
        XCTAssertTrue(decision.evidenceRefs?.contains(seed.sourceRef) == true)
        XCTAssertTrue(decision.evidence.contains { row in row["label"] == .string("offline_caddie") })
        XCTAssertTrue(decision.auditCriteria.contains { row in row["label"] == .string("offline_selected_option") })
        XCTAssertTrue(decision.missingData.contains { row in row["label"] == .string("club_profile_sample") })
    }

    func testLiveStructuredDecisionDoesNotWaitForUnusedLLMExplanation() throws {
        let seed = try XCTUnwrap(try fixturePackage().caddieContextSeeds.first)
        let request = CaddieDecisionRequestBuilder().makeDecisionRequest(
            seed: seed,
            input: LiveCaddieInput(shotType: "tee", distanceToPinM: 369)
        )

        XCTAssertFalse(request.includeExplanation)
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any]
        )
        XCTAssertEqual(object["includeExplanation"] as? Bool, false)
    }

    func testCancelledLiveCaddieRequestIsNotReportedAsConnectivityFailure() {
        XCTAssertTrue(LiveCaddieLoadFailure.isCancellation(CancellationError()))
        XCTAssertTrue(LiveCaddieLoadFailure.isCancellation(URLError(.cancelled)))
        XCTAssertFalse(LiveCaddieLoadFailure.isCancellation(URLError(.timedOut)))
    }

    func testStrategyModeSelectsCachedOptionWithoutNetwork() throws {
        let seed = try XCTUnwrap(try fixturePackage().caddieContextSeeds.first)
        let evaluator = OfflineCaddieDecisionEvaluator()

        XCTAssertEqual(evaluator.selectedOption(in: seed, strategyMode: "protect_score")?.optionId, "safe")
        XCTAssertEqual(evaluator.selectedOption(in: seed, strategyMode: "stock")?.optionId, "stock")
        XCTAssertEqual(evaluator.selectedOption(in: seed, strategyMode: "attack")?.optionId, "attack")
        XCTAssertEqual(evaluator.selectedOption(in: seed, strategyMode: nil)?.optionId, "stock")
    }

    func testBlackKnightA3SynthesizesCompletePrepPlanWhenPackageSeedIsMissing() throws {
        let source = try fixturePackage()
        let hole = Hole(
            number: 3,
            par: 5,
            yards: 510,
            geometryCoverage: .ready,
            geometryRevision: "black-knight-a3-r1",
            sourceGlobalId: 31794,
            sourceLocalHole: 3
        )
        let package = LiveRoundPackage(
            schema: source.schema,
            roundId: "black-knight-a-live",
            dataMode: "local",
            sourceCoverage: SourceCoverage(
                state: "ready",
                dataMode: "local",
                requestedRoundId: "black-knight-a-live",
                selectedRoundId: nil,
                roundFound: false,
                availableRoundCount: 0,
                holeCount: 1,
                clubProfileCount: source.clubProfiles.count,
                playerStatsWindow: nil
            ),
            missingData: [],
            playerProfile: source.playerProfile,
            course: Course(
                globalId: 31794,
                name: "北京天竺黑骑士球员俱乐部 ~ A",
                teeBox: "blue",
                venueName: "北京天竺黑骑士球员俱乐部",
                venueNameSource: "garmin_courseview_zh_chs",
                segmentLabel: "A"
            ),
            holes: [hole],
            nine: "all",
            coursePrep: nil,
            geometryCoverage: GeometryCoverage(state: .ready, readyHoles: 1, totalHoles: 1),
            readinessChecks: source.readinessChecks,
            caddieContextSeeds: [],
            weatherSnapshot: source.weatherSnapshot,
            clubProfiles: source.clubProfiles,
            caddieDecisionEndpoint: source.caddieDecisionEndpoint,
            offlinePackageStatus: source.offlinePackageStatus,
            eventCursor: source.eventCursor,
            recentHistory: source.recentHistory,
            cachedCaddieRules: source.cachedCaddieRules,
            generatedAt: source.generatedAt
        )
        let prep = CoursePrepHole(
            hole: hole.number,
            par: 5,
            parSource: "courseview",
            blueYards: 510,
            routeLenM: 466,
            geometryCoverage: "ready",
            steps: [
                CoursePrepStep(
                    club: "1W", note: "", clubName: "1W", targetCarryM: 205,
                    routeOffsetM: 205, landingM: 205, expectedRemainingM: 261,
                    role: "tee", planIndex: 0
                ),
                CoursePrepStep(
                    club: "3H", note: "", clubName: "3H", targetCarryM: 178,
                    routeOffsetM: 383, landingM: 383, expectedRemainingM: 83,
                    role: "advance", planIndex: 1
                ),
                CoursePrepStep(
                    club: "7I", note: "", clubName: "7I", targetCarryM: 83,
                    routeOffsetM: 466, landingM: 466, expectedRemainingM: 0,
                    role: "approach", planIndex: 2
                ),
            ]
        )

        XCTAssertTrue(package.caddieContextSeeds.isEmpty)
        let seed = try XCTUnwrap(
            LiveCaddieSeedFactory.resolve(package: package, hole: hole, prep: prep)
        )
        XCTAssertEqual(seed.hole, 3)
        XCTAssertEqual(seed.sourceRef, "black-knight-a-live:3")
        XCTAssertEqual(seed.context["globalId"], .number(31794))
        XCTAssertEqual(seed.context["localHole"], .number(3))
        let request = CaddieDecisionRequestBuilder().makeDecisionRequest(
            seed: seed,
            input: LiveCaddieInput(shotType: "tee", distanceToPinM: 466)
        )
        let decision = try XCTUnwrap(
            OfflineCaddieDecisionEvaluator().makeDecision(
                seed: seed,
                request: request,
                strategyMode: nil
            )
        )
        let sequence = try XCTUnwrap(CaddiePlanSequence.selectedSequence(from: decision))

        XCTAssertEqual(sequence.steps.map(\.clubName), ["1W", "3H", "7I"])
        XCTAssertEqual(sequence.steps.map(\.targetCarryM), [205, 178, 83])
        XCTAssertEqual(sequence.steps.map(\.routeOffsetM), [205, 383, 466])
        XCTAssertEqual(sequence.steps.map(\.landingM), [205, 383, 466])
        XCTAssertEqual(sequence.steps.map(\.expectedRemainingM), [261, 83, 0])
        XCTAssertEqual(sequence.steps.map(\.role), ["tee", "advance", "approach"])
        XCTAssertEqual(sequence.steps.map(\.planIndex), [0, 1, 2])
        XCTAssertTrue(LiveCaddieDecisionUsability.hasRecommendation(decision))
    }

    func testEmptyOnlineDecisionIsNotUsableAndMustFallBack() {
        let empty = CaddieDecisionResponse(
            schema: "ai-caddie-decision-v2",
            decisionId: "empty-a3",
            sourceRef: "black-knight-a:3",
            evidenceRefs: [],
            shotType: "tee",
            phase: "tee_shot",
            context: [:],
            options: [],
            selected: nil,
            selectedOptionId: nil,
            selectedOption: nil,
            sequences: [],
            selectedSequence: nil,
            avoidZones: [],
            forbiddenZones: [],
            acceptableMiss: [:],
            evidence: [],
            confidence: [:],
            missingData: [],
            auditCriteria: []
        )

        XCTAssertFalse(LiveCaddieDecisionUsability.hasRecommendation(empty))
    }

    private func fixturePackage() throws -> LiveRoundPackage {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(LiveRoundPackage.self, from: data)
    }
}
