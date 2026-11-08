// size: small
// goals: W-08, I-10
import AICaddieCore
import XCTest

/// W-08: a Watch record waits in the offline queue exactly once and leaves it only when the
/// counterpart has resolved it; I-10: replay neither duplicates nor drops a record.
final class QueueStateMachineTests: XCTestCase {
    private func event(_ eventId: String, round: String = "round-a", hole: Int = 1) -> WatchInputEvent {
        WatchInputEvent(
            eventId: eventId,
            roundId: round,
            hole: hole,
            kind: .score,
            value: "4",
            createdAt: "2026-11-08T10:00:00Z"
        )
    }

    // goals: W-08
    func testReEnqueueOfTheSameEventIdKeepsOneEntry() {
        var queue = WatchInputQueue()

        XCTAssertTrue(queue.enqueue(event("e1")))
        XCTAssertFalse(queue.enqueue(event("e1")), "a retried send must not queue the record twice")

        XCTAssertEqual(queue.events.map(\.eventId), ["e1"])
    }

    // goals: W-08, I-10
    func testQueueKeepsCaptureOrder() {
        var queue = WatchInputQueue()
        queue.enqueue(event("e1"))
        queue.enqueue(event("e2"))
        queue.enqueue(event("e1"))
        queue.enqueue(event("e3"))

        XCTAssertEqual(queue.events.map(\.eventId), ["e1", "e2", "e3"])
    }

    // goals: W-08
    func testOnlyResolvedEventsLeaveTheQueue() {
        var queue = WatchInputQueue(events: [event("e1"), event("e2"), event("e3"), event("e4")])
        let ack = WatchSyncAcknowledgement.decode(
            [
                "acceptedEventIds": ["e1"],
                "duplicateEventIds": ["e2"],
                "rejectedEventIds": ["e4"],
            ],
            fallbackEventId: "e1"
        )

        queue.removeResolved(Set(ack.resolvedEventIds))

        XCTAssertEqual(queue.events.map(\.eventId), ["e3"], "an unacknowledged record must stay queued")
    }

    // goals: W-08
    func testAnEmptyAcknowledgementRemovesNothing() {
        var queue = WatchInputQueue(events: [event("e1")])
        let ack = WatchSyncAcknowledgement.decode(["accepted": false], fallbackEventId: "e1")

        queue.removeResolved(Set(ack.resolvedEventIds))

        XCTAssertEqual(queue.events.map(\.eventId), ["e1"])
    }

    // goals: W-08, I-10
    func testDiscardingARoundKeepsOtherRounds() {
        var queue = WatchInputQueue(events: [
            event("a1", round: "round-a"),
            event("b1", round: "round-b"),
            event("a2", round: "round-a", hole: 2),
        ])

        queue.discardRound("round-a")

        XCTAssertEqual(queue.events.map(\.eventId), ["b1"])
    }
}
