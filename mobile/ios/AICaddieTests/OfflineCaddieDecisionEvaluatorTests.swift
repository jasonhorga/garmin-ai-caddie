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
            sourceLocalHole: 3,
            courseHoleNumber: 3
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
            roundLoops: [RoundLoop(globalId: 31794, half: "all", roundStartHole: 3, sourceStartHole: 3, holeCount: 1)],
            loopKey: "31794:all",
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
        XCTAssertEqual(sequence.steps.map(\.role), ["tee", "advance", "scoring"])
        XCTAssertEqual(sequence.steps.map(\.planIndex), [0, 1, 2])
        XCTAssertTrue(LiveCaddieDecisionUsability.hasRecommendation(decision))
    }

    func testOldMinimalSeedIsAugmentedFromCurrentPackageFacts() throws {
        let source = try fixturePackage()
        let hole = try XCTUnwrap(source.holes.first)
        let profiles = [
            ClubProfile(clubName: "1W", sampleSize: 120, medianM: 199.2, p10M: 150, p90M: 232),
            ClubProfile(clubName: "3H", sampleSize: 25, medianM: 164.6, p10M: 145, p90M: 183),
            ClubProfile(clubName: "7I", sampleSize: 40, medianM: 83, p10M: 74, p90M: 92),
        ]
        let package = LiveRoundPackage(
            schema: source.schema,
            roundId: "black-knight-a-live",
            dataMode: source.dataMode,
            sourceCoverage: source.sourceCoverage,
            missingData: source.missingData,
            playerProfile: source.playerProfile,
            course: Course(globalId: 31794, name: "北京天竺黑骑士球员俱乐部 ~ A", teeBox: "blue"),
            holes: [Hole(
                number: 1,
                par: 4,
                yards: 377,
                geometryCoverage: .ready,
                sourceGlobalId: 31794,
                sourceLocalHole: 1,
                courseHoleNumber: 1
            )],
            roundLoops: [RoundLoop(globalId: 31794, half: "all", roundStartHole: 1, sourceStartHole: 1, holeCount: 1)],
            loopKey: "31794:all",
            coursePrep: nil,
            geometryCoverage: GeometryCoverage(state: .ready, readyHoles: 1, totalHoles: 1),
            readinessChecks: source.readinessChecks,
            caddieContextSeeds: [CaddieContextSeed(
                hole: 1,
                sourceRef: "black-knight-a-live:1",
                shotTypes: ["tee"],
                requiredLiveInputs: ["currentLocation"],
                enrichmentState: "deferred",
                context: [
                    "courseName": .string("北京天竺黑骑士球员俱乐部"),
                    "globalId": .number(31794),
                    "localHole": .number(1),
                    "hole": .number(1),
                    "lie": .string("tee"),
                ],
                selectedOfflineOptionId: "stock",
                offlineOptions: [],
                evidence: [],
                missingData: []
            )],
            weatherSnapshot: source.weatherSnapshot,
            clubProfiles: profiles,
            caddieDecisionEndpoint: source.caddieDecisionEndpoint,
            offlinePackageStatus: source.offlinePackageStatus,
            eventCursor: source.eventCursor,
            recentHistory: source.recentHistory,
            cachedCaddieRules: source.cachedCaddieRules,
            generatedAt: source.generatedAt
        )
        let prep = CoursePrepHole(
            hole: 1,
            par: 4,
            parSource: "courseview",
            blueYards: 377,
            routeLenM: 344.7,
            geometryCoverage: "ready",
            steps: [
                CoursePrepStep(
                    club: "1W", note: "", clubName: "1W", targetCarryM: 199.2,
                    routeOffsetM: 199.2, landingM: 199.2, expectedRemainingM: 145.5,
                    role: "tee", planIndex: 0
                ),
                CoursePrepStep(
                    club: "3H", note: "", clubName: "3H", targetCarryM: 164.6,
                    routeOffsetM: 363.8, landingM: 363.8, expectedRemainingM: 0,
                    role: "advance", planIndex: 1
                ),
            ]
        )

        let packagedPrep = CoursePrepPackage(
            schema: "ai-caddie-course-prep-package-v1",
            globalId: 31794,
            holes: [prep],
            missingData: nil
        )
        let packageWithPrep = package.replacingCoursePrep(packagedPrep)
        // Resolve against the current package hole, not the fixture source hole. The source
        // fixture intentionally carries a different yardage so this test proves that the
        // installed package facts replace an older sparse seed.
        let currentHole = try XCTUnwrap(packageWithPrep.holes.first)
        let seed = try XCTUnwrap(LiveCaddieSeedFactory.resolve(package: packageWithPrep, hole: currentHole, prep: nil))
        if case .object(let rows)? = seed.context["clubProfiles"] {
            XCTAssertEqual(rows.count, 3)
        } else {
            XCTFail("augmented seed must carry the current package club profiles")
        }
        if case .array(let rows)? = seed.context["canonicalShotPlan"] {
            XCTAssertEqual(rows.count, 2)
        } else {
            XCTFail("augmented seed must carry the current CoursePrep chain")
        }
        XCTAssertEqual(seed.context["yards"], .number(377))
        XCTAssertEqual(seed.context["canonicalPlanRouteLength_m"], .number(344.7))

        let request = CaddieDecisionRequestBuilder().makeDecisionRequest(
            seed: seed,
            input: LiveCaddieInput(shotType: "tee", distanceToPinM: 344.7)
        )
        XCTAssertEqual(request.context["source"], .string("ios_live"))
        if case .object(let profiles)? = request.context["clubProfiles"] {
            XCTAssertEqual(profiles.count, 3)
        } else {
            XCTFail("request must normalize club profiles to an object")
        }
        XCTAssertEqual(request.context["canonicalShotPlan"], seed.context["canonicalShotPlan"])
    }

    func testPar3TeeBuildsOneDirectScoringRouteFromArrayBag() throws {
        let profiles: JSONValue = .array([
            .object([
                "clubName": .string("7I"),
                "sampleSize": .number(40),
                "median_m": .number(125),
                "p10_m": .number(116),
                "p90_m": .number(132),
            ]),
            .object([
                "clubName": .string("6I"),
                "sampleSize": .number(35),
                "median_m": .number(138),
                "p10_m": .number(128),
                "p90_m": .number(146),
            ]),
        ])
        let seed = CaddieContextSeed(
            hole: 2,
            sourceRef: "round:2",
            shotTypes: ["tee"],
            requiredLiveInputs: [],
            context: [
                "par": .number(3),
                "yards": .number(151),
                "clubProfiles": profiles,
            ],
            selectedOfflineOptionId: "stock",
            offlineOptions: [
                OfflineCaddieOption(
                    optionId: "stock", label: "推荐", clubName: "7I", carryM: 125,
                    sampleSize: 40, confidence: "medium", riskScore: 0,
                    source: "test", sourceRefs: ["round:2"]
                )
            ],
            evidence: [],
            missingData: []
        )
        let request = CaddieDecisionRequestBuilder().makeDecisionRequest(
            seed: seed,
            input: LiveCaddieInput(shotType: "tee", distanceToPinM: 151)
        )
        let decision = try XCTUnwrap(
            OfflineCaddieDecisionEvaluator().makeDecision(seed: seed, request: request, strategyMode: nil)
        )
        let sequence = try XCTUnwrap(CaddiePlanSequence.selectedSequence(from: decision))

        XCTAssertEqual(sequence.steps.count, 1)
        XCTAssertEqual(sequence.steps.first?.clubName, "7I")
        XCTAssertEqual(sequence.steps.first?.role, "scoring")
        let routeOffsetM = try XCTUnwrap(sequence.steps.first?.routeOffsetM)
        XCTAssertEqual(routeOffsetM, 151, accuracy: 0.001)
        XCTAssertTrue(LiveCaddieDecisionUsability.hasCompleteRoute(decision, par: 3, shotType: "tee"))
    }

    // MARK: Whole-hole strategies (Codex 5922608092)

    /// A tee decision from a bag of `(club, median m, half p10-p90 spread m)` and seed options of
    /// `(id, club)`, with optional factual water carries in route metres.
    private func wholeHoleDecision(
        par: Int,
        distanceM: Double,
        bag: [(String, Double, Double)],
        options: [(String, String)],
        water: [[Double]] = []
    ) throws -> CaddieDecisionResponse {
        let profiles: JSONValue = .array(bag.map { name, carry, half in
            .object([
                "clubName": .string(name), "sampleSize": .number(24),
                "median_m": .number(carry), "p10_m": .number(carry - half), "p90_m": .number(carry + half),
            ])
        })
        let seed = CaddieContextSeed(
            hole: 1,
            sourceRef: "round:1",
            shotTypes: ["tee"],
            requiredLiveInputs: [],
            context: ["par": .number(Double(par)), "clubProfiles": profiles],
            selectedOfflineOptionId: "stock",
            offlineOptions: options.map { id, club in
                OfflineCaddieOption(
                    optionId: id, label: id, clubName: club,
                    carryM: bag.first { $0.0 == club }?.1 ?? 0,
                    sampleSize: 24, confidence: "high", riskScore: 0,
                    source: "test", sourceRefs: ["round:1"]
                )
            },
            evidence: [],
            missingData: []
        )
        var request = CaddieDecisionRequestBuilder().makeDecisionRequest(
            seed: seed,
            input: LiveCaddieInput(shotType: "tee", distanceToPinM: distanceM)
        )
        if !water.isEmpty {
            var context = request.context
            context["hazardWaterCarry_m"] = .array(water.map { .array($0.map(JSONValue.number)) })
            request = CaddieDecisionRequest(shotType: request.shotType, context: context, includeExplanation: false)
        }
        return try XCTUnwrap(OfflineCaddieDecisionEvaluator().makeDecision(seed: seed, request: request, strategyMode: nil))
    }

    func testNoHazardPar4NeverOffersTheShortFirstThreeShotRoute() throws {
        // Codex's case: a clear 410-yard Par 4 whose seed offers 9I as the safe tee club. The old
        // greedy remainder produced 9I 132 -> 7I 156 -> 8I 144: three strokes on a hole the driver
        // reaches in two.
        let bag = [("1D", 210.0, 10.0), ("7I", 156.0, 10.0), ("8I", 144.0, 10.0), ("9I", 132.0, 10.0)]
        let decision = try wholeHoleDecision(
            par: 4, distanceM: 375, bag: bag,
            options: [("stock", "1D"), ("safe", "9I"), ("attack", "7I")]
        )
        let routes = CaddiePlanSequence.sequences(from: decision)
        XCTAssertFalse(routes.contains { $0.steps.map(\.clubName) == ["9I", "7I", "8I"] })
        XCTAssertEqual(routes.first { $0.id == "stock" }?.steps.map(\.clubName), ["1D", "7I"])
        for route in routes {
            XCTAssertLessThanOrEqual(route.steps.count, 2, "\(route.id) goes for the green in regulation")
        }
    }

    func testSafePar5NeverMovesItsLongestClubToTheGreenBoundStroke() throws {
        // Codex's case: 7I -> 5I -> 5W as "safe" — the shortest opening and the hardest shot last.
        let bag = [
            ("1D", 220.0, 22.0), ("3W", 210.0, 16.0), ("5W", 196.0, 14.0), ("5I", 161.0, 10.0),
            ("7I", 139.0, 8.0), ("9I", 115.0, 7.0), ("PW", 102.0, 6.0),
        ]
        let decision = try wholeHoleDecision(
            par: 5, distanceM: 496, bag: bag,
            options: [("stock", "1D"), ("safe", "7I"), ("attack", "3W")]
        )
        let carries = Dictionary(uniqueKeysWithValues: bag.map { ($0.0, $0.1) })
        let routes = CaddiePlanSequence.sequences(from: decision)
        XCTAssertFalse(routes.contains { $0.steps.map(\.clubName) == ["7I", "5I", "5W"] })
        XCTAssertNotNil(routes.first { $0.id == "stock" })
        for route in routes {
            XCTAssertLessThanOrEqual(route.steps.count, 3, "\(route.id) goes for the green in regulation")
            let tee = try XCTUnwrap(carries[try XCTUnwrap(route.steps.first).clubName])
            let after = route.steps.dropFirst().compactMap { carries[$0.clubName] }
            XCTAssertTrue(after.allSatisfy { $0 <= tee + 15 }, "\(route.id): no longer club after a short tee club")
            XCTAssertEqual(after, after.sorted(by: >), "\(route.id): longer clubs first")
        }
    }

    func testFactualWaterCarryJustifiesALayUpWithItsReason() throws {
        // Water across 190-225 m: the driver's 210 m tee shot lands in it, and nothing else reaches
        // a 400 m Par 4 in two without landing in it, so the lay-up is the plan and says why.
        let bag = [
            ("1D", 210.0, 20.0), ("3H", 180.0, 12.0), ("7I", 156.0, 10.0), ("8I", 144.0, 10.0),
            ("9I", 132.0, 8.0), ("PW", 110.0, 6.0),
        ]
        let decision = try wholeHoleDecision(
            par: 4, distanceM: 400, bag: bag,
            options: [("stock", "1D"), ("safe", "3H")],
            water: [[190, 225]]
        )
        let rows = decision.sequences ?? []
        XCTAssertFalse(rows.contains { $0["id"] == .string("stock") }, "no driver into the water")
        let layup = try XCTUnwrap(rows.first { $0["id"] == .string("safe") })
        XCTAssertEqual(layup["layupReason"], .string("water_carry"))
        let route = try XCTUnwrap(CaddiePlanSequence.sequences(from: decision).first { $0.id == "safe" })
        XCTAssertEqual(route.steps.first?.clubName, "3H")
        XCTAssertGreaterThan(route.steps.count, 2)
        // No landing of the lay-up is in the water (with the 8 m buffer).
        for offset in route.steps.compactMap(\.routeOffsetM) {
            XCTAssertFalse(offset > 182 && offset < 233, "landing at \(offset) m is clear of the water")
        }
    }

    func testPar4LegThatFliesTheBackEdgeIsNotGIR() throws {
        // The fallback planner clamps the second landing to the 396 m route end, but the 3W
        // median lands at 412.2 m: past back (400 m) + the 8 m tolerance, so it is not a GIR.
        let profiles: JSONValue = .array([
            .object([
                "clubName": .string("1W"), "sampleSize": .number(120),
                "median_m": .number(199.2), "p10_m": .number(180), "p90_m": .number(215),
            ]),
            .object([
                "clubName": .string("3W"), "sampleSize": .number(80),
                "median_m": .number(213), "p10_m": .number(200), "p90_m": .number(224),
            ]),
        ])
        let seed = CaddieContextSeed(
            hole: 4,
            sourceRef: "round:4",
            shotTypes: ["tee"],
            requiredLiveInputs: [],
            context: [
                "par": .number(4),
                "clubProfiles": profiles,
                "greenDistances": .object([
                    "available": .bool(true),
                    "frontM": .number(376),
                    "middleM": .number(388),
                    "backM": .number(400),
                ]),
            ],
            selectedOfflineOptionId: "stock",
            offlineOptions: [
                OfflineCaddieOption(
                    optionId: "stock", label: "推荐", clubName: "1W", carryM: 199.2,
                    sampleSize: 120, confidence: "medium", riskScore: 0,
                    source: "test", sourceRefs: ["round:4"]
                )
            ],
            evidence: [],
            missingData: []
        )
        let request = CaddieDecisionRequestBuilder().makeDecisionRequest(
            seed: seed,
            input: LiveCaddieInput(shotType: "tee", distanceToPinM: 396)
        )
        let decision = try XCTUnwrap(
            OfflineCaddieDecisionEvaluator().makeDecision(seed: seed, request: request, strategyMode: nil)
        )
        let sequence = try XCTUnwrap(CaddiePlanSequence.selectedSequence(from: decision))

        XCTAssertEqual(sequence.steps.map(\.clubName), ["1W", "3W"])
        XCTAssertNotEqual(sequence.steps.last?.greenInRegulation, true)
    }

    func testRefreshKeepsCompleteLocalRouteWhenRemoteResponseIsOnlyAClubCard() {
        let local = sequenceDecision(
            clubs: [
                ["clubName": .string("1W"), "role": .string("tee"), "expectedRemaining_m": .number(160)],
                ["clubName": .string("3H"), "role": .string("scoring"), "expectedRemaining_m": .number(0)],
            ]
        )
        let remote = CaddieDecisionResponse(
            schema: "ai-caddie-decision-v2", decisionId: "remote", sourceRef: nil,
            evidenceRefs: nil, shotType: "tee", phase: "Tee", context: [:],
            options: [["clubName": .string("3H")]], selected: ["clubName": .string("3H")],
            selectedOptionId: "stock", selectedOption: ["clubName": .string("3H")],
            sequences: [], selectedSequence: nil, avoidZones: [], forbiddenZones: [],
            acceptableMiss: [:], evidence: [], confidence: [:], missingData: [], auditCriteria: []
        )

        XCTAssertTrue(
            LiveCaddieDecisionUsability.shouldPreferLocalRoute(
                local: local, remote: remote, par: 4, shotType: "tee"
            )
        )
    }

    func testRefreshRejectsRepeatedRemoteChainWhenLocalRouteIsDistinct() {
        let local = sequenceDecision(
            clubs: [
                ["clubName": .string("1W"), "role": .string("tee")],
                ["clubName": .string("3H"), "role": .string("scoring"), "expectedRemaining_m": .number(0)],
            ]
        )
        let remote = sequenceDecision(
            clubs: [
                ["clubName": .string("3H"), "role": .string("tee")],
                ["clubName": .string("3H"), "role": .string("position")],
                ["clubName": .string("3H"), "role": .string("scoring"), "expectedRemaining_m": .number(0)],
            ]
        )

        XCTAssertTrue(
            LiveCaddieDecisionUsability.shouldPreferLocalRoute(
                local: local, remote: remote, par: 4, shotType: "tee"
            )
        )
    }

    func testPositionPrefixWithZeroLeaveIsNotACompleteRoute() {
        let local = sequenceDecision(
            clubs: [
                ["clubName": .string("1W"), "role": .string("tee")],
                ["clubName": .string("3H"), "role": .string("scoring"), "expectedRemaining_m": .number(0)],
            ]
        )
        let remote = sequenceDecision(
            clubs: [
                ["clubName": .string("3H"), "role": .string("position"), "expectedRemaining_m": .number(0)],
            ]
        )

        XCTAssertTrue(
            LiveCaddieDecisionUsability.shouldPreferLocalRoute(
                local: local, remote: remote, par: 4, shotType: "tee"
            )
        )
    }

    func testBarePar4ScoringCardIsNotACompleteRouteWithoutGIRFact() {
        let response = sequenceDecision(clubs: [[
            "clubName": .string("1W"),
            "role": .string("scoring"),
            "expectedRemaining_m": .number(0),
        ]])

        XCTAssertFalse(
            LiveCaddieDecisionUsability.hasCompleteRoute(response, par: 4, shotType: "tee")
        )
    }

    func testCompleteRemoteGeometryRouteWinsOverInstalledPrepPrefix() {
        let local = sequenceDecision(
            clubs: [
                ["clubName": .string("1W"), "role": .string("tee")],
                ["clubName": .string("3H"), "role": .string("position"), "expectedRemaining_m": .number(0)],
            ]
        )
        let remoteSequence: [String: JSONValue] = [
            "id": .string("stock"),
            "clubs": .array([
                .object(["clubName": .string("1W"), "role": .string("tee")]),
                .object(["clubName": .string("7I"), "role": .string("scoring"), "expectedRemaining_m": .number(0)]),
            ]),
            "completion": .string("scoring_window"),
        ]
        let remote = CaddieDecisionResponse(
            schema: "ai-caddie-decision-v2", decisionId: "remote-geometry", sourceRef: nil,
            evidenceRefs: nil, shotType: "tee", phase: "Tee", context: [:],
            options: [["clubName": .string("1W")]], selected: nil,
            selectedOptionId: "stock", selectedOption: nil,
            sequences: [remoteSequence], selectedSequence: remoteSequence,
            avoidZones: [], forbiddenZones: [], acceptableMiss: [:],
            evidence: [["kind": .string("geometry"), "text": .string("prodgeometry ready")]],
            confidence: [:], missingData: [], auditCriteria: []
        )

        XCTAssertFalse(
            LiveCaddieDecisionUsability.shouldPreferLocalRoute(
                local: local, remote: remote, par: 4, shotType: "tee"
            )
        )
    }

    func testPositionPrefixDoesNotClaimTheFlagButScoringLegDoes() {
        let prefix = MapPlannedShot(
            id: "prefix", clubName: "3H", routeOffsetM: 345,
            role: "position", expectedRemainingM: 0
        )
        let scoring = MapPlannedShot(
            id: "scoring", clubName: "Pw", routeOffsetM: 448,
            role: "scoring", expectedRemainingM: 5
        )

        XCTAssertFalse(prefix.shouldEndAtPin)
        XCTAssertTrue(scoring.shouldEndAtPin)
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

    private func sequenceDecision(clubs: [[String: JSONValue]]) -> CaddieDecisionResponse {
        let sequence: [String: JSONValue] = [
            "id": .string("stock"),
            "clubs": .array(clubs.map { .object($0) }),
        ]
        return CaddieDecisionResponse(
            schema: "ai-caddie-decision-v2", decisionId: "local", sourceRef: nil,
            evidenceRefs: nil, shotType: "tee", phase: "Tee", context: [:],
            options: [["clubName": clubs[0]["clubName"] ?? .string("-")]],
            selected: nil, selectedOptionId: "stock", selectedOption: nil,
            sequences: [sequence], selectedSequence: sequence, avoidZones: [],
            forbiddenZones: [], acceptableMiss: [:], evidence: [], confidence: [:],
            missingData: [], auditCriteria: []
        )
    }
}
