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
}
