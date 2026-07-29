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

    func testStrategyModeSelectsCachedOptionWithoutNetwork() throws {
        let seed = try XCTUnwrap(try fixturePackage().caddieContextSeeds.first)
        let evaluator = OfflineCaddieDecisionEvaluator()

        XCTAssertEqual(evaluator.selectedOption(in: seed, strategyMode: "protect_score")?.optionId, "safe")
        XCTAssertEqual(evaluator.selectedOption(in: seed, strategyMode: "stock")?.optionId, "stock")
        XCTAssertEqual(evaluator.selectedOption(in: seed, strategyMode: "attack")?.optionId, "attack")
        XCTAssertEqual(evaluator.selectedOption(in: seed, strategyMode: nil)?.optionId, "stock")
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
