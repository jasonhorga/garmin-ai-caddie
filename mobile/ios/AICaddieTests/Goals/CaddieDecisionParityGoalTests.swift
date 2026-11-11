// size: medium
// goals: I-07

import Foundation
import XCTest
@testable import AICaddie

/// I-07: the live request and offline fallback use the same physical facts as the server.
/// The independent oracle is contracts/fixtures/shared/caddie_golden.json, also checked by
/// Python DecisionGoldenTests against build_decision_plan (the online decision engine).
@MainActor
final class CaddieDecisionParityGoalTests: XCTestCase {
    private var bagIsolation: GoalClubBagIsolation?

    override func setUp() async throws {
        try await super.setUp()
        bagIsolation = try GoalClubBagIsolation()
    }

    override func tearDown() async throws {
        await bagIsolation?.restore()
        bagIsolation = nil
        try await super.tearDown()
    }
    // goals: I-07
    func testLiveRequestAndOfflineFallbackMatchServerSharedGolden() throws {
        let document: ProductCaddieDocument = try ProductSharedVectors.read("caddie_golden")
        XCTAssertFalse(document.cases.isEmpty)
        for vector in document.cases {
            let seed = try vector.seed()
            let input = LiveCaddieInput(
                shotType: vector.shotType,
                distanceToPinM: vector.distanceToPin_m,
                distanceToPinSource: "gps_auto",
                lie: "fairway",
                strategyMode: "stock"
            )
            let request = CaddieDecisionRequestBuilder().makeDecisionRequest(seed: seed, input: input)
            let response = try XCTUnwrap(OfflineCaddieDecisionEvaluator().makeDecision(
                seed: seed, request: request, strategyMode: input.strategyMode
            ), vector.id)
            let expected = try XCTUnwrap(vector.expected.first { $0.id == "stock" }, vector.id)
            let route = try XCTUnwrap(CaddiePlanSequence.selectedSequence(from: response), vector.id)

            XCTAssertEqual(request.context["source"], .string("ios_live"), vector.id)
            XCTAssertEqual(request.context["sourceRef"], .string(seed.sourceRef), vector.id)
            XCTAssertEqual(request.context["hole"], .number(Double(vector.hole)), vector.id)
            XCTAssertEqual(request.context["distanceToPin_m"], .number(vector.distanceToPin_m), vector.id)
            XCTAssertEqual(request.context["distanceToPinSource"], .string("gps_auto"), vector.id)
            XCTAssertEqual(response.sourceRef, seed.sourceRef, vector.id)
            XCTAssertEqual(response.shotType, request.shotType, vector.id)
            XCTAssertEqual(response.selectedOptionId, expected.id, vector.id)
            XCTAssertEqual(route.steps.map(\.clubName), expected.clubNames, vector.id)
            XCTAssertEqual(route.steps.count, expected.plannedStrokes, vector.id)
            XCTAssertEqual(route.steps.map(\.routeOffsetM), expected.routeOffsets_m, vector.id)
        }
    }
}
