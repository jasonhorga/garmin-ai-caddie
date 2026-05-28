import XCTest
@testable import AICaddieWatch

final class WatchRoundStateTests: XCTestCase {
    func testWatchRoundStateEncodesAndDecodes() throws {
        let state = WatchRoundState(
            roundId: "round-1",
            hole: 7,
            par: 4,
            distanceM: 142,
            targetLatitude: 22.279,
            targetLongitude: 114.162,
            targetKind: "pin",
            selectedClub: "8I",
            availableClubs: [
                WatchClubOption(clubName: "8I", sampleSize: 24, medianM: 144, source: "club_profile")
            ],
            shotType: "approach",
            strategyMode: "stock",
            lie: "fairway",
            offlineOptionId: "stock",
            decisionId: "decision-1",
            holePlanSummary: "1D-3W-58 / 3 shots / leave -21m",
            expectedStrokes: 3,
            expectedRemainingM: -21,
            score: 4,
            putts: 2,
            penaltyCount: 0,
            caddieConfidence: "high"
        )

        let data = try JSONEncoder().encode(state)
        let decoded = try JSONDecoder().decode(WatchRoundState.self, from: data)

        XCTAssertEqual(decoded, state)
        XCTAssertEqual(decoded.schema, "ai-caddie-watch-round-state-v1")
        XCTAssertEqual(decoded.id, "round-1-7")
        XCTAssertEqual(decoded.targetKind, "pin")
        XCTAssertEqual(decoded.availableClubNames, ["8I"])
        XCTAssertEqual(decoded.shotType, "approach")
        XCTAssertEqual(decoded.offlineOptionId, "stock")
        XCTAssertEqual(decoded.holePlanSummary, "1D-3W-58 / 3 shots / leave -21m")
        XCTAssertEqual(decoded.expectedStrokes, 3)
        XCTAssertEqual(decoded.expectedRemainingM, -21)
    }

    func testWatchRoundStatePreservesEvidenceAndMissingDataAcrossQuickInput() throws {
        let state = WatchRoundState(
            roundId: "round-1",
            hole: 7,
            par: 4,
            distanceM: 142,
            suggestedClub: "8I",
            selectedClub: "8I",
            availableClubs: [
                WatchClubOption(clubName: "8I", sampleSize: 24, medianM: 144, source: "club_profile"),
                WatchClubOption(clubName: "7I", medianM: 156, source: "offline_option:attack"),
            ],
            shotType: "approach",
            strategyMode: "stock",
            lie: "fairway",
            offlineOptionId: "stock",
            decisionId: "decision-1",
            nextShotPrompt: "8I / Stock / 142m",
            holePlanSummary: "1D-3W-58 / 3 shots / leave -21m",
            expectedStrokes: 3,
            expectedRemainingM: -21,
            evidenceSummary: "route: water left",
            missingDataSummary: "wind: not cached",
            score: 4,
            putts: 2,
            penaltyCount: 0,
            caddieConfidence: "medium"
        )
        let event = WatchInputEvent(
            eventId: "event-1",
            roundId: "round-1",
            hole: 7,
            kind: .club,
            value: "7I",
            createdAt: "2026-05-25T00:00:00Z"
        )

        let updated = state.applying(event)

        XCTAssertEqual(updated.selectedClub, "7I")
        XCTAssertEqual(updated.availableClubNames, ["8I", "7I"])
        XCTAssertEqual(updated.shotType, "approach")
        XCTAssertEqual(updated.offlineOptionId, "stock")
        XCTAssertEqual(updated.holePlanSummary, "1D-3W-58 / 3 shots / leave -21m")
        XCTAssertEqual(updated.expectedStrokes, 3)
        XCTAssertEqual(updated.expectedRemainingM, -21)
        XCTAssertEqual(updated.evidenceSummary, "route: water left")
        XCTAssertEqual(updated.missingDataSummary, "wind: not cached")
    }

    func testWatchRoundStateDecodesLegacyStateWithoutAvailableClubs() throws {
        let legacy = """
        {
          "roundId": "round-1",
          "hole": 7,
          "par": 4,
          "distanceM": 142,
          "selectedClub": "8I",
          "score": 4,
          "putts": 2,
          "penaltyCount": 0,
          "caddieConfidence": "medium"
        }
        """.data(using: .utf8)!

        let decoded = try JSONDecoder().decode(WatchRoundState.self, from: legacy)

        XCTAssertEqual(decoded.availableClubs, [])
        XCTAssertEqual(decoded.schema, "ai-caddie-watch-round-state-v1")
        XCTAssertEqual(decoded.selectedClub, "8I")
        XCTAssertNil(decoded.offlineOptionId)
    }

    func testWatchDistanceInputUpdatesLocalDistanceWithoutDroppingTarget() throws {
        let state = WatchRoundState(
            roundId: "round-1",
            hole: 7,
            par: 4,
            distanceM: 142,
            targetLatitude: 22.279,
            targetLongitude: 114.162,
            targetKind: "pin",
            suggestedClub: "8I",
            selectedClub: "8I",
            score: 4,
            putts: 2,
            penaltyCount: 0,
            caddieConfidence: "medium"
        )
        let event = WatchInputEvent(
            eventId: "event-2",
            roundId: "round-1",
            hole: 7,
            kind: .distance,
            value: "155",
            createdAt: "2026-05-25T00:00:00Z",
            contextClub: "8I"
        )

        let updated = state.applying(event)

        XCTAssertEqual(updated.distanceM, 155)
        XCTAssertEqual(updated.targetLatitude, 22.279)
        XCTAssertEqual(updated.targetKind, "pin")
    }
}
