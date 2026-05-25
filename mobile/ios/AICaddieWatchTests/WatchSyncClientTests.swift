import XCTest
@testable import AICaddieWatch

final class WatchSyncClientTests: XCTestCase {
    func testQueueInputEventSerializesPendingEvents() throws {
        let queueURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("queued_events.json")
        let client = WatchSyncClient(queueURL: queueURL)
        let event = WatchInputEvent(
            eventId: "event-1",
            roundId: "round-1",
            hole: 3,
            kind: .club,
            value: "8I",
            createdAt: "2026-05-25T00:00:00Z"
        )

        try client.queueInputEvent(event)

        XCTAssertEqual(try client.loadQueuedEvents(), [event])
    }
}
