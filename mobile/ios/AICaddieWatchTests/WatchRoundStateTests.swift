import XCTest
@testable import AICaddieWatch

final class WatchRoundStateTests: XCTestCase {
    func testWatchRoundStateEncodesAndDecodes() throws {
        let state = WatchRoundState(
            roundId: "round-1",
            hole: 7,
            par: 4,
            distanceM: 142,
            selectedClub: "8I",
            score: 4,
            putts: 2,
            penaltyCount: 0,
            caddieConfidence: "high"
        )

        let data = try JSONEncoder().encode(state)
        let decoded = try JSONDecoder().decode(WatchRoundState.self, from: data)

        XCTAssertEqual(decoded, state)
        XCTAssertEqual(decoded.id, "round-1-7")
    }

    func testWatchRoundStatePreservesEvidenceAndMissingDataAcrossQuickInput() throws {
        let state = WatchRoundState(
            roundId: "round-1",
            hole: 7,
            par: 4,
            distanceM: 142,
            suggestedClub: "8I",
            selectedClub: "8I",
            nextShotPrompt: "8I / Stock / 142m",
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
        XCTAssertEqual(updated.evidenceSummary, "route: water left")
        XCTAssertEqual(updated.missingDataSummary, "wind: not cached")
    }
}
