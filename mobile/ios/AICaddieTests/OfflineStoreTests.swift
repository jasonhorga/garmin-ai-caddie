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

    func testAppendSyncMarkerPersistsAcknowledgementMetadata() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let result = SyncResult(
            accepted: 2,
            duplicate: false,
            acceptedEventIds: ["event-1", "event-2"],
            duplicateEventIds: ["event-0"],
            serverSequence: 42
        )

        try store.appendSyncMarker(
            roundId: "round-1",
            timestamp: "2026-05-25T00:01:00Z",
            result: result
        )

        let marker = try XCTUnwrap(try store.loadEvents().first)
        XCTAssertEqual(marker.kind, .syncMarker)
        XCTAssertEqual(marker.payload["status"], .string("synced"))
        XCTAssertEqual(marker.payload["source"], .string("ios_sync"))
        XCTAssertEqual(marker.payload["acceptedEventIds"], .array([.string("event-1"), .string("event-2")]))
        XCTAssertEqual(marker.payload["duplicateEventIds"], .array([.string("event-0")]))
        XCTAssertEqual(marker.payload["serverSequence"], .number(42))
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
                    "targetLatitude": .number(22.2799),
                    "targetLongitude": .number(114.162),
                    "targetKind": .string("pin"),
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
        XCTAssertEqual(holeState.targetLatitude, 22.2799)
        XCTAssertEqual(holeState.targetLongitude, 114.162)
        XCTAssertEqual(holeState.targetKind, "pin")
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

    func testLoadResumablePackageResumesFromEventLogWithoutPointer() throws {
        // round-10 bug: an offline/cached start records events but never writes current_package.json.
        // Resume must still find the in-progress round via the event log (continue card survives quit).
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try fixturePackage()
        try store.saveRoundPackage(package)
        // Simulate the missing pointer: drop current_package.json, keep packages/<id>.json + events.
        try FileManager.default.removeItem(at: directory.appendingPathComponent("current_package.json"))
        try store.appendEvent(
            LiveRoundEvent(eventId: "s1", roundId: package.roundId, timestamp: "2026-06-19T00:00:00Z",
                           hole: 1, kind: .score, payload: ["strokes": .number(4)])
        )

        XCTAssertNil(try store.loadCurrentRoundPackage())  // pointer gone
        XCTAssertEqual(try store.inProgressRoundId(), package.roundId)
        XCTAssertEqual(try store.loadResumablePackage()?.roundId, package.roundId)  // resumes from the log
        XCTAssertTrue(try store.hasRecordedEvents(roundId: package.roundId))
    }

    func testRestoreClampsActiveHoleToPackageHoles() throws {
        // round-10: after「移除加打的 9 洞」the package is narrowed but events span more holes — activeHole
        // must stay within package.holes or the Hub's 继续这场 card (needs activeHole ∈ holes) vanishes.
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try fixturePackage()
        let firstHole = try XCTUnwrap(package.holes.first?.number)
        let outOfRange = (package.holes.map(\.number).max() ?? 9) + 3

        try store.appendEvent(
            LiveRoundEvent(eventId: "s-in", roundId: package.roundId, timestamp: "2026-06-19T00:00:00Z",
                           hole: firstHole, kind: .score, payload: ["strokes": .number(4)])
        )
        try store.appendEvent(
            LiveRoundEvent(eventId: "s-out", roundId: package.roundId, timestamp: "2026-06-19T00:01:00Z",
                           hole: outOfRange, kind: .score, payload: ["strokes": .number(5)])
        )

        let snapshot = try store.restoreLiveRoundState(roundId: package.roundId, package: package)
        XCTAssertTrue(package.holes.contains { $0.number == snapshot.activeHole })  // clamped to package
        XCTAssertNotEqual(snapshot.activeHole, outOfRange)
    }

    func testLoadEventsSkipsTruncatedFinalLineAndStillResumes() throws {
        // round-11 bug: appendEvent writes JSON + "\n" as two non-atomic FileHandle writes. If iOS
        // SIGKILLs the app mid-write, the last log line is a truncated JSON fragment. loadEvents used
        // to THROW on it, which silently aborted resume → the in-progress round looked lost (Hub
        // showed, 继续这场 card gone). loadEvents must skip the bad line and keep every prior event.
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try fixturePackage()
        try store.saveRoundPackage(package)
        try store.appendEvent(
            LiveRoundEvent(eventId: "s1", roundId: package.roundId, timestamp: "2026-06-20T00:00:00Z",
                           hole: 1, kind: .score, payload: ["strokes": .number(4)])
        )
        // Simulate a half-written final line from a forced quit (no closing brace, no newline).
        let logURL = directory.appendingPathComponent("events.jsonl")
        let handle = try FileHandle(forWritingTo: logURL)
        handle.seekToEndOfFile()
        handle.write(Data("{\"eventId\":\"trunc\",\"roundId\":\"\(package.roundId)\",\"ho".utf8))
        try handle.close()

        let events = try store.loadEvents()
        XCTAssertEqual(events.count, 1)                                  // truncated fragment skipped
        XCTAssertEqual(events.first?.eventId, "s1")                      // recorded score survives
        XCTAssertEqual(try store.inProgressRoundId(), package.roundId)   // resume still finds the round
        XCTAssertEqual(try store.loadResumablePackage()?.roundId, package.roundId)
        XCTAssertTrue(try store.hasRecordedEvents(roundId: package.roundId))  // 继续这场 card survives
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
