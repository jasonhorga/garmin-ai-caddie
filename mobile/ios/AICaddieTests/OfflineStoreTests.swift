import XCTest
@testable import AICaddie

final class OfflineStoreTests: XCTestCase {
    func testSaveAndLoadRoundPackage() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try fixturePackage()

        try store.saveRoundPackage(package)

        XCTAssertEqual(try store.loadRoundPackage(roundId: package.roundId)?.roundId, package.roundId)
        XCTAssertEqual(try store.loadCurrentRoundPackage()?.roundId, package.roundId)
    }

    func testAppendAndLoadEvents() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let event = LiveRoundEvent(
            eventId: "event-1",
            roundId: "round-1",
            timestamp: "2026-05-25T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )

        try store.appendEvent(event)
        try store.appendSyncMarker(roundId: "round-1", timestamp: "2026-05-25T00:01:00Z")

        let events = try store.loadEvents()
        XCTAssertEqual(events.count, 2)
        XCTAssertEqual(events.first?.eventId, "event-1")
        XCTAssertEqual(events.last?.kind, .syncMarker)
    }

    func testRestoreLiveRoundStateReplaysScoringClubAndLocationEvents() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try fixturePackage()

        try store.appendEvent(
            LiveRoundEvent(
                eventId: "score-1",
                roundId: package.roundId,
                timestamp: "2026-05-25T00:00:00Z",
                hole: 1,
                kind: .score,
                payload: ["strokes": .number(5)]
            )
        )
        try store.appendEvent(
            LiveRoundEvent(
                eventId: "putt-1",
                roundId: package.roundId,
                timestamp: "2026-05-25T00:01:00Z",
                hole: 1,
                kind: .putt,
                payload: ["putts": .number(3)]
            )
        )
        try store.appendEvent(
            LiveRoundEvent(
                eventId: "penalty-1",
                roundId: package.roundId,
                timestamp: "2026-05-25T00:02:00Z",
                hole: 1,
                kind: .penalty,
                payload: ["penalties": .number(1)]
            )
        )
        try store.appendEvent(
            LiveRoundEvent(
                eventId: "club-1",
                roundId: package.roundId,
                timestamp: "2026-05-25T00:03:00Z",
                hole: 1,
                kind: .club,
                payload: [
                    "clubName": .string("7I"),
                    "shotType": .string("approach"),
                    "strategyMode": .string("attack"),
                    "lie": .string("rough"),
                    "distanceToPinM": .number(142),
                ]
            )
        )
        try store.appendEvent(
            LiveRoundEvent(
                eventId: "location-1",
                roundId: package.roundId,
                timestamp: "2026-05-25T00:04:00Z",
                hole: 1,
                kind: .location,
                payload: [
                    "latitude": .number(22.279),
                    "longitude": .number(114.162),
                    "horizontalAccuracyM": .number(4.5),
                ]
            )
        )

        let snapshot = try store.restoreLiveRoundState(roundId: package.roundId, package: package)
        let holeState = try XCTUnwrap(snapshot.holeState(for: 1))

        XCTAssertEqual(snapshot.activeHole, 1)
        XCTAssertEqual(holeState.score, 5)
        XCTAssertEqual(holeState.putts, 3)
        XCTAssertEqual(holeState.penaltyCount, 1)
        XCTAssertEqual(holeState.selectedClub, "7I")
        XCTAssertEqual(holeState.selectedStrategyMode, "attack")
        XCTAssertEqual(holeState.lie, "rough")
        XCTAssertEqual(holeState.distanceToPinM, 142)
        XCTAssertEqual(holeState.latitude, 22.279)
        XCTAssertEqual(holeState.longitude, 114.162)
        XCTAssertEqual(holeState.horizontalAccuracyM, 4.5)
    }

    func testRestoreLiveRoundStateClearsNullableLiveFieldsInLogOrder() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try fixturePackage()

        try store.appendEvent(
            LiveRoundEvent(
                eventId: "club-distance",
                roundId: package.roundId,
                timestamp: "2026-05-25T00:00:00Z",
                hole: 1,
                kind: .club,
                payload: [
                    "clubName": .string("7I"),
                    "distanceToPinM": .number(142),
                ]
            )
        )
        try store.appendEvent(
            LiveRoundEvent(
                eventId: "location-accurate",
                roundId: package.roundId,
                timestamp: "2026-05-25T00:01:00Z",
                hole: 1,
                kind: .location,
                payload: [
                    "latitude": .number(22.279),
                    "longitude": .number(114.162),
                    "horizontalAccuracyM": .number(4.5),
                ]
            )
        )
        try store.appendEvent(
            LiveRoundEvent(
                eventId: "club-distance-cleared",
                roundId: package.roundId,
                timestamp: "2026-05-25T00:02:00Z",
                hole: 1,
                kind: .club,
                payload: [
                    "clubName": .string("7I"),
                    "distanceToPinM": .null,
                ]
            )
        )
        try store.appendEvent(
            LiveRoundEvent(
                eventId: "location-accuracy-cleared",
                roundId: package.roundId,
                timestamp: "2026-05-25T00:03:00Z",
                hole: 1,
                kind: .location,
                payload: [
                    "latitude": .number(22.28),
                    "longitude": .number(114.163),
                    "horizontalAccuracyM": .null,
                ]
            )
        )

        let snapshot = try store.restoreLiveRoundState(roundId: package.roundId, package: package)
        let holeState = try XCTUnwrap(snapshot.holeState(for: 1))

        XCTAssertNil(holeState.distanceToPinM)
        XCTAssertEqual(holeState.latitude, 22.28)
        XCTAssertEqual(holeState.longitude, 114.163)
        XCTAssertNil(holeState.horizontalAccuracyM)
    }

    func testLiveHoleStateRestorableComparisonIgnoresUpdatedAt() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try fixturePackage()

        let base = try store.restoreLiveRoundState(roundId: package.roundId, package: package)
            .holeState(for: 1)
        var sameEditableFields = try XCTUnwrap(base)
        sameEditableFields.updatedAt = "2026-05-25T00:05:00Z"
        var changedScore = try XCTUnwrap(base)
        changedScore.score += 1

        XCTAssertTrue(try XCTUnwrap(base).hasSameRestorableFields(as: sameEditableFields))
        XCTAssertFalse(try XCTUnwrap(base).hasSameRestorableFields(as: changedScore))
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
