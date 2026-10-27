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
        var reads = 0
        let events = [
            locationEvent(id: "tee", timestamp: "2026-10-27T08:00:00Z"),
            locationEvent(id: "landing", timestamp: "2026-10-27T08:05:00Z"),
            locationEvent(id: "other-hole", hole: 4, timestamp: "2026-10-27T08:06:00Z"),
            locationEvent(id: "other-round", roundId: "round-2", timestamp: "2026-10-27T08:07:00Z")
        ]
        let snapshot = LiveEventLogSnapshot(loader: {
            reads += 1
            return events
        })

        // The phone redraw consumes the same event log for the F/M/B-driven shot facts, the
        // second-shot landing, and the newest-shot marker. Each consumer intentionally asks the
        // snapshot independently, matching the view's separate derived properties.
        let frontShots = LiveMarkedShots.locations(
            in: snapshot.events(), roundId: "round-1", hole: 3
        )
        let middleShots = LiveMarkedShots.locations(
            in: snapshot.events(), roundId: "round-1", hole: 3
        )
        let backShots = LiveMarkedShots.locations(
            in: snapshot.events(), roundId: "round-1", hole: 3
        )
        let secondShot = CurrentHoleView.secondShotCoordinate(in: middleShots)
        let newestShot = CurrentHoleView.newestShotCoordinate(in: backShots)

        XCTAssertEqual(frontShots.map(\.eventId), ["tee", "landing"])
        XCTAssertEqual(secondShot?.latitude ?? -1, 40.0)
        XCTAssertEqual(newestShot?.capturedAt ?? "", "2026-10-27T08:05:00Z")
        XCTAssertEqual(reads, 1)

        // sendWatchState's marked-shot payload runs after the redraw and still uses the cached
        // snapshot. A new event invalidates it, so the next send gets exactly one fresh read.
        let watchShots = LiveMarkedShots.locations(
            in: snapshot.events(), roundId: "round-1", hole: 3
        )
        XCTAssertEqual(watchShots.map(\.eventId), frontShots.map(\.eventId))
        XCTAssertEqual(reads, 1)
        snapshot.invalidate()
        let refreshed = LiveMarkedShots.locations(
            in: snapshot.events(), roundId: "round-1", hole: 3
        )
        XCTAssertEqual(refreshed.count, 2)
        XCTAssertEqual(reads, 2)
    }
}
