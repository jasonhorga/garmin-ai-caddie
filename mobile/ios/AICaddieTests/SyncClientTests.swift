import Foundation
import XCTest
@testable import AICaddie

final class SyncClientTests: XCTestCase {
    func testEventBatchEncodesRoundIdAndEvents() throws {
        let event = LiveRoundEvent(
            eventId: "event-1",
            roundId: "round-1",
            timestamp: "2026-05-25T00:00:00Z",
            hole: 1,
            kind: .club,
            payload: ["clubName": .string("8I")]
        )

        let data = try JSONEncoder().encode(EventBatch(roundId: "round-1", events: [event]))
        let decoded = try JSONDecoder().decode(EventBatch.self, from: data)

        XCTAssertEqual(decoded.roundId, "round-1")
        XCTAssertEqual(decoded.events.first?.kind, .club)
    }
}
