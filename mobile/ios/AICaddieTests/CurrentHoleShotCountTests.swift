import XCTest
@testable import AICaddie

final class CurrentHoleShotCountTests: XCTestCase {
    private func locationEvent(
        id: String,
        roundId: String = "round-1",
        hole: Int = 3,
        timestamp: String
    ) -> LiveRoundEvent {
        LiveRoundEvent(
            eventId: id,
            roundId: roundId,
            timestamp: timestamp,
            hole: hole,
            kind: .location,
            payload: [
                "latitude": .number(40.0),
                "longitude": .number(116.0)
            ]
        )
    }

    func testOneSnapshotReadIsSharedByFMBAndWatchDerivedValues() throws {
        var redrawReads = 0
        let events = [
            locationEvent(id: "tee", timestamp: "2026-10-27T08:00:00Z"),
            locationEvent(id: "landing", timestamp: "2026-10-27T08:05:00Z"),
            locationEvent(id: "other-hole", hole: 4, timestamp: "2026-10-27T08:06:00Z"),
            locationEvent(id: "other-round", roundId: "round-2", timestamp: "2026-10-27T08:07:00Z")
        ]
        let redrawSnapshot = LiveEventLogSnapshot(loader: {
            redrawReads += 1
            return events
        })

        // One redraw derives the F/M/B shot count, second-shot landing, and newest-shot marker
        // from one snapshot read.
        let redraw = CurrentHoleView.liveHoleEventDerivedValues(
            from: redrawSnapshot, roundId: "round-1", hole: 3
        )

        XCTAssertEqual(redraw.markedShots.map(\.eventId), ["tee", "landing"])
        XCTAssertEqual(redraw.secondShotCoordinate?.latitude ?? -1, 40.0)
        XCTAssertEqual(redraw.newestShotCoordinate?.capturedAt ?? "", "2026-10-27T08:05:00Z")
        XCTAssertEqual(redrawReads, 1)

        // sendWatchState builds its event portion through the same one-read boundary.
        var sendReads = 0
        let sendSnapshot = LiveEventLogSnapshot(loader: {
            sendReads += 1
            return events
        })
        let payload = CurrentHoleView.liveWatchShotPayload(
            from: sendSnapshot, roundId: "round-1", hole: 3
        )
        XCTAssertEqual(payload.phoneShotEventIds, redraw.markedShots.map(\.eventId))
        XCTAssertEqual(payload.teeShotLanding?.latitude ?? -1, 40.0)
        XCTAssertEqual(payload.lastShotCapturedAt ?? "", "2026-10-27T08:05:00Z")
        XCTAssertEqual(sendReads, 1)

        sendSnapshot.invalidate()
        _ = CurrentHoleView.liveWatchShotPayload(
            from: sendSnapshot, roundId: "round-1", hole: 3
        )
        XCTAssertEqual(sendReads, 2)
    }
}
