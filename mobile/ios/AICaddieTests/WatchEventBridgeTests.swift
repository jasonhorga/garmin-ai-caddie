import XCTest
@testable import AICaddie

final class WatchEventBridgeTests: XCTestCase {
    func testWatchRoundStatePayloadCompactsDecisionEvidenceWithoutDroppingContext() throws {
        let bridge = WatchEventBridge()
        let package = try fixturePackage()
        let decision = CaddieDecisionResponse(
            schema: "ai-caddie-decision-v1",
            decisionId: "decision-1",
            sourceRef: nil,
            evidenceRefs: nil,
            shotType: "approach",
            phase: "approach",
            context: [:],
            options: [
                [
                    "id": .string("stock"),
                    "label": .string("Center green"),
                    "carryM": .number(142),
                    "clubName": .string("8I"),
                ]
            ],
            selected: nil,
            selectedOptionId: "stock",
            selectedOption: nil,
            avoidZones: [],
            forbiddenZones: [],
            acceptableMiss: [:],
            evidence: [
                [
                    "label": .string("route"),
                    "source": .string("prodgeometry"),
                    "kind": .string("geometry"),
                    "value": .number(2),
                    "text": .string("water left"),
                    "state": .string("ready"),
                ]
            ],
            confidence: ["level": .string("medium")],
            missingData: [
                [
                    "label": .string("wind"),
                    "reason": .string("not cached"),
                    "state": .string("missing"),
                ]
            ],
            auditCriteria: []
        )

        let payload = bridge.makeWatchRoundStatePayload(
            package: package,
            hole: try XCTUnwrap(package.holes.first),
            score: 4,
            putts: 2,
            penaltyCount: 0,
            selectedClub: "8I",
            decision: decision
        )

        XCTAssertEqual(payload.evidenceSummary, "route / prodgeometry / geometry: 2 / water left / ready")
        XCTAssertEqual(payload.missingDataSummary, "wind: not cached / missing")
    }

    func testOfflineEvidenceSummaryRedactsPrivateSourceRefs() throws {
        let bridge = WatchEventBridge()
        let package = try fixturePackage()
        let option = OfflineCaddieOption(
            optionId: "stock",
            label: "Center green",
            clubName: "8I",
            carryM: 142,
            riskScore: 1,
            source: "offline_seed",
            sourceRefs: ["/Users/player/private/raw.json"]
        )

        let payload = bridge.makeWatchRoundStatePayload(
            package: package,
            hole: try XCTUnwrap(package.holes.first),
            score: 4,
            putts: 2,
            penaltyCount: 0,
            selectedClub: "8I",
            decision: nil,
            offlineOption: option
        )

        XCTAssertEqual(payload.evidenceSummary, "offline_seed / [redacted]")
        XCTAssertFalse(try XCTUnwrap(payload.evidenceSummary).contains("/Users/"))
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
