import XCTest
@testable import AICaddie

final class OfflineStoreTests: XCTestCase {
    private enum TestDurabilityFailure: Error {
        case directorySync
    }

    private struct PrivacySanitizerGolden: Decodable {
        struct Case: Decodable {
            let name: String
            let input: LiveRoundEvent
            let expected: LiveRoundEvent
        }

        let schema: String
        let cases: [Case]
    }

    private func privacySanitizerGoldenURL() throws -> URL {
        #if SWIFT_PACKAGE
        let bundle = Bundle.module
        #else
        let bundle = Bundle(for: OfflineStoreTests.self)
        #endif
        if let nested = bundle.url(
            forResource: "mobile_event_sanitizer_golden",
            withExtension: "json",
            subdirectory: "Fixtures"
        ) {
            return nested
        }
        return try XCTUnwrap(
            bundle.url(
                forResource: "mobile_event_sanitizer_golden",
                withExtension: "json"
            )
        )
    }

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

    func testApplyReplayEventsUsesFullIdentityAndRequiresEqualEnvelope() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let phone = LiveRoundEvent(
            eventId: "shared-event-id",
            roundId: "round-1",
            clientId: "ios-phone",
            timestamp: "2026-07-21T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )
        let watch = LiveRoundEvent(
            eventId: "shared-event-id",
            roundId: "round-1",
            clientId: "apple-watch",
            timestamp: "2026-07-21T00:00:01Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(5)]
        )

        XCTAssertTrue(try store.applyReplayEvents([phone, watch, phone]))
        XCTAssertEqual(try store.loadEvents(), [phone, watch])
        XCTAssertFalse(try store.applyReplayEvents([phone, watch]))

        let conflictingPhone = LiveRoundEvent(
            eventId: phone.eventId,
            roundId: phone.roundId,
            clientId: phone.clientId,
            timestamp: phone.timestamp,
            hole: phone.hole,
            kind: phone.kind,
            payload: ["strokes": .number(6)]
        )
        XCTAssertThrowsError(try store.applyReplayEvents([conflictingPhone])) { error in
            XCTAssertEqual(error as? OfflineStoreError, .replayIdentityEnvelopeMismatch)
        }
        XCTAssertEqual(try store.loadEvents(), [phone, watch])
    }

    func testMediaTransportEnvelopeSanitizesNewAndLegacyRowsBeforeReplayComparison() throws {
        let rawEvent = LiveRoundEvent(
            eventId: "private-photo",
            roundId: "round-1",
            clientId: "ios-phone",
            timestamp: "2026-07-21T00:00:00Z",
            hole: 1,
            kind: .photo,
            payload: [
                "assetLocalId": .string("photo.jpg"),
                "fileURL": .string("file:///private/mobile/photo.jpg"),
                "mediaType": .string("photo"),
                "note": .string("token=legacy-secret from /home/mobile/private-note.txt"),
            ]
        )
        let transportEvent = LiveRoundEvent(
            eventId: rawEvent.eventId,
            roundId: rawEvent.roundId,
            clientId: rawEvent.clientId,
            timestamp: rawEvent.timestamp,
            hole: rawEvent.hole,
            kind: rawEvent.kind,
            payload: [
                "assetLocalId": .string("photo.jpg"),
                "fileURL": .string("[REDACTED_LOCAL_MEDIA_URL]"),
                "mediaType": .string("photo"),
                "note": .string("token=[REDACTED] from [REDACTED_PATH]"),
            ]
        )

        let newDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let newStore = OfflineStore(directoryURL: newDirectory)
        try newStore.appendEvent(rawEvent)

        XCTAssertEqual(try newStore.loadEvents(), [transportEvent])
        let durableText = try XCTUnwrap(
            String(
                data: Data(contentsOf: newDirectory.appendingPathComponent("events.jsonl")),
                encoding: .utf8
            )
        )
        XCTAssertFalse(durableText.contains("file:///private"))
        XCTAssertFalse(durableText.contains("legacy-secret"))
        XCTAssertFalse(try newStore.applyReplayEvents([transportEvent]))

        let conflicting = LiveRoundEvent(
            eventId: transportEvent.eventId,
            roundId: transportEvent.roundId,
            clientId: transportEvent.clientId,
            timestamp: transportEvent.timestamp,
            hole: transportEvent.hole,
            kind: transportEvent.kind,
            payload: [
                "assetLocalId": .string("photo.jpg"),
                "fileURL": .string("[REDACTED_LOCAL_MEDIA_URL]"),
                "mediaType": .string("photo"),
                "note": .string("genuinely different public note"),
            ]
        )
        XCTAssertThrowsError(try newStore.applyReplayEvents([conflicting])) { error in
            XCTAssertEqual(error as? OfflineStoreError, .replayIdentityEnvelopeMismatch)
        }

        let legacyDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: legacyDirectory, withIntermediateDirectories: true)
        var rawLegacyLine = try JSONEncoder().encode(rawEvent)
        rawLegacyLine.append(Data([0x0A]))
        try rawLegacyLine.write(
            to: legacyDirectory.appendingPathComponent("events.jsonl"),
            options: [.atomic]
        )
        let legacyStore = OfflineStore(directoryURL: legacyDirectory)
        XCTAssertFalse(try legacyStore.applyReplayEvents([transportEvent]))
        XCTAssertEqual(try legacyStore.loadEvents(), [transportEvent])
    }

    func testPrivacySanitizerMatchesSharedCrossLanguageGoldenCorpus() throws {
        let corpus = try JSONDecoder().decode(
            PrivacySanitizerGolden.self,
            from: Data(contentsOf: try privacySanitizerGoldenURL())
        )
        XCTAssertEqual(corpus.schema, "ai-caddie-mobile-event-sanitizer-golden-v1")

        for testCase in corpus.cases {
            let directory = FileManager.default.temporaryDirectory
                .appendingPathComponent(UUID().uuidString, isDirectory: true)
            let store = OfflineStore(directoryURL: directory)
            try store.appendEvent(testCase.input)
            XCTAssertEqual(
                try store.loadEvents(),
                [testCase.expected],
                "privacy golden drift: \(testCase.name)"
            )
        }
    }

    func testAppendAndDiscardFailClosedOnMalformedMiddleEventRow() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let store = OfflineStore(directoryURL: directory)
        let first = LiveRoundEvent(
            eventId: "first",
            roundId: "round-1",
            timestamp: "2026-07-21T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )
        let last = LiveRoundEvent(
            eventId: "last",
            roundId: "round-1",
            timestamp: "2026-07-21T00:00:01Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(5)]
        )
        var corruptLog = try JSONEncoder().encode(first)
        corruptLog.append(Data([0x0A]))
        corruptLog.append(Data("{broken}\n".utf8))
        corruptLog.append(try JSONEncoder().encode(last))
        corruptLog.append(Data([0x0A]))
        let logURL = directory.appendingPathComponent("events.jsonl")
        try corruptLog.write(to: logURL, options: [.atomic])
        let original = try Data(contentsOf: logURL)

        XCTAssertThrowsError(
            try store.appendEvent(
                LiveRoundEvent(
                    eventId: "must-not-append",
                    roundId: "round-1",
                    timestamp: "2026-07-21T00:00:02Z",
                    hole: 1,
                    kind: .score,
                    payload: ["strokes": .number(6)]
                )
            )
        ) { error in
            XCTAssertEqual(error as? OfflineStoreError, .eventLogCorrupt)
        }
        XCTAssertEqual(try Data(contentsOf: logURL), original)

        XCTAssertThrowsError(try store.discardRound(roundId: "round-1")) { error in
            XCTAssertEqual(error as? OfflineStoreError, .eventLogCorrupt)
        }
        XCTAssertEqual(try Data(contentsOf: logURL), original)
    }

    func testLaterMediaUploadSuccessKeepsResponseLostRetryBodyAndKeyExact() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let attachment = try store.savePendingMedia(
            data: Data("image".utf8),
            eventId: "photo-event",
            roundId: "round-1",
            hole: 1,
            targetId: "round-1:1",
            assetLocalId: "photo.jpg",
            mediaKind: "photo",
            fileName: "photo.jpg",
            capturedAt: "2026-07-21T00:00:00Z"
        )
        let event = LiveRoundEventBuilder(
            roundId: "round-1",
            idFactory: { "photo-event" },
            now: { Date(timeIntervalSince1970: 1_774_051_200) }
        ).makePhotoEvent(
            hole: 1,
            assetLocalId: attachment.assetLocalId,
            fileURL: attachment.fileURL,
            note: nil,
            mediaId: nil
        )
        try store.appendEvent(event)

        let beforeEvents = try store.loadPendingEvents(roundId: "round-1")
        let beforeBody = try JSONEncoder().encode(EventBatch(roundId: "round-1", events: beforeEvents))
        let beforeKey = "round-1-" + beforeEvents.map(\.eventId).joined(separator: "-")

        // The event POST response was lost, then the independently queued media upload succeeded.
        try store.removePendingMedia(ids: Set([attachment.id]))

        let afterEvents = try store.loadPendingEvents(roundId: "round-1")
        let afterBody = try JSONEncoder().encode(EventBatch(roundId: "round-1", events: afterEvents))
        let afterKey = "round-1-" + afterEvents.map(\.eventId).joined(separator: "-")
        XCTAssertEqual(afterBody, beforeBody)
        XCTAssertEqual(afterKey, beforeKey)
    }

    func testApplyReplayEventsThrowsWhenAnyPageEventFailsToPersist() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let durable = LiveRoundEvent(
            eventId: "durable-first",
            roundId: "round-1",
            clientId: nil,
            timestamp: "2026-07-21T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )
        let unencodable = LiveRoundEvent(
            eventId: "fails-second",
            roundId: "round-1",
            clientId: "apple-watch",
            timestamp: "2026-07-21T00:00:01Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(Double.nan)]
        )

        XCTAssertThrowsError(try store.applyReplayEvents([durable, unencodable]))
        XCTAssertEqual(try store.loadEvents(), [durable])
        XCTAssertFalse(try store.applyReplayEvents([durable]))
    }

    func testApplyReplayEventsRepairsTornEOFTailAndReloadsBeforeAckGate() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let logURL = directory.appendingPathComponent("events.jsonl")
        let store = OfflineStore(directoryURL: directory)
        let existing = LiveRoundEvent(
            eventId: "existing",
            roundId: "round-1",
            clientId: "ios-phone",
            timestamp: "2026-07-21T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )
        let replayed = LiveRoundEvent(
            eventId: "replayed-after-torn-tail",
            roundId: "round-1",
            clientId: "apple-watch",
            timestamp: "2026-07-21T00:00:01Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(5)]
        )
        var tornLog = try JSONEncoder().encode(existing)
        tornLog.append(Data([0x0A]))
        tornLog.append(Data(#"{"eventId":"torn"#.utf8))
        try tornLog.write(to: logURL, options: [.atomic])

        XCTAssertTrue(try store.applyReplayEvents([replayed]))
        XCTAssertEqual(try store.loadEvents(), [existing, replayed])
        XCTAssertEqual(try Data(contentsOf: logURL).last, 0x0A)
    }

    func testReplayFirstLogCreationRequiresFileAndDirectoryDurabilityBeforeSuccess() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        var barriers: [String] = []
        let store = OfflineStore(
            directoryURL: directory,
            syncEventLogFile: { url in
                barriers.append("file:\(url.lastPathComponent)")
            },
            syncEventLogDirectory: { url in
                barriers.append("directory:\(url.lastPathComponent)")
                if url == directory {
                    throw TestDurabilityFailure.directorySync
                }
            }
        )
        let replayed = LiveRoundEvent(
            eventId: "first-durable-replay",
            roundId: "round-1",
            clientId: "apple-watch",
            timestamp: "2026-07-21T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )

        XCTAssertThrowsError(try store.applyReplayEvents([replayed])) { error in
            XCTAssertEqual(error as? TestDurabilityFailure, .directorySync)
        }
        XCTAssertEqual(
            Array(barriers.suffix(2)),
            ["file:events.jsonl", "directory:\(directory.lastPathComponent)"]
        )

        // The replace may already be visible despite an uncertain directory barrier. A normal
        // retry must reuse the exact durable envelope rather than duplicate or conflict it.
        let restarted = OfflineStore(directoryURL: directory)
        XCTAssertFalse(try restarted.applyReplayEvents([replayed]))
        XCTAssertEqual(try restarted.loadEvents(), [replayed])
    }

    func testTornTailReplacementRequiresFileAndDirectoryDurabilityBeforeReplaySuccess() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let logURL = directory.appendingPathComponent("events.jsonl")
        let existing = LiveRoundEvent(
            eventId: "existing-before-torn-tail",
            roundId: "round-1",
            clientId: "ios-phone",
            timestamp: "2026-07-21T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )
        let replayed = LiveRoundEvent(
            eventId: "after-torn-tail",
            roundId: "round-1",
            clientId: "apple-watch",
            timestamp: "2026-07-21T00:00:01Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(5)]
        )
        var tornLog = try JSONEncoder().encode(existing)
        tornLog.append(Data([0x0A]))
        tornLog.append(Data(#"{"eventId":"torn"#.utf8))
        try tornLog.write(to: logURL, options: [.atomic])
        var barriers: [String] = []
        let store = OfflineStore(
            directoryURL: directory,
            syncEventLogFile: { url in
                barriers.append("file:\(url.lastPathComponent)")
            },
            syncEventLogDirectory: { url in
                barriers.append("directory:\(url.lastPathComponent)")
                if url == directory {
                    throw TestDurabilityFailure.directorySync
                }
            }
        )

        XCTAssertThrowsError(try store.applyReplayEvents([replayed])) { error in
            XCTAssertEqual(error as? TestDurabilityFailure, .directorySync)
        }
        XCTAssertEqual(
            barriers,
            ["file:events.jsonl", "directory:\(directory.lastPathComponent)"]
        )

        let restarted = OfflineStore(directoryURL: directory)
        XCTAssertTrue(try restarted.applyReplayEvents([replayed]))
        XCTAssertEqual(try restarted.loadEvents(), [existing, replayed])
    }

    func testApplyReplayEventsRejectsMalformedMiddleLineBeforePageCanAck() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let logURL = directory.appendingPathComponent("events.jsonl")
        let store = OfflineStore(directoryURL: directory)
        let existing = LiveRoundEvent(
            eventId: "existing",
            roundId: "round-1",
            clientId: "ios-phone",
            timestamp: "2026-07-21T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )
        let replayed = LiveRoundEvent(
            eventId: "must-not-ack",
            roundId: "round-1",
            clientId: "apple-watch",
            timestamp: "2026-07-21T00:00:01Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(5)]
        )
        var corruptLog = try JSONEncoder().encode(existing)
        corruptLog.append(Data([0x0A]))
        corruptLog.append(Data("{broken}\n".utf8))
        try corruptLog.write(to: logURL, options: [.atomic])

        XCTAssertThrowsError(try store.applyReplayEvents([replayed])) { error in
            XCTAssertEqual(error as? OfflineStoreError, .eventLogCorrupt)
        }
        XCTAssertEqual(try store.loadEvents(), [existing])
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

    func testLoadPendingMediaSkipsTruncatedFinalLine() throws {
        // P2: pending_media.jsonl is appended non-atomically; a kill mid-write torns the last line.
        // loadPendingMedia must skip it and still return every prior attachment, not throw and drop all.
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let saved = try store.savePendingMedia(
            data: Data("img".utf8),
            eventId: "e1",
            roundId: "round-1",
            hole: 1,
            targetId: "shot-1",
            assetLocalId: "asset-1",
            mediaKind: "photo",
            fileName: "p.jpg",
            capturedAt: "2026-05-25T00:00:00Z"
        )
        // Simulate a half-written final line from a forced quit (no closing brace, no newline).
        let indexURL = directory.appendingPathComponent("pending_media.jsonl")
        let handle = try FileHandle(forWritingTo: indexURL)
        handle.seekToEndOfFile()
        handle.write(Data("{\"id\":\"trunc\",\"roundId\":\"round-1\",\"ho".utf8))
        try handle.close()

        let media = try store.loadPendingMedia()
        XCTAssertEqual(media.map(\.id), [saved.id])  // valid attachment survives, torn fragment skipped
    }

    func testReconcileSaveOnlyFieldsPreservesUnsavedLocalEdits() throws {
        // P0-5: score/putts/penalty persist only on an explicit Save, so when ANY incoming
        // event or remote sync rebuilds the snapshot it still carries the OLD persisted
        // values. A blanket restore reverted the user's unsaved edits — reconcile must keep
        // every on-screen field the user has diverged from the baseline on.
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try fixturePackage()
        let baseline = try XCTUnwrap(
            try store.restoreLiveRoundState(roundId: package.roundId, package: package).holeState(for: 1)
        )
        // Nothing was saved, so the rebuilt snapshot equals the baseline we last synced to.
        let incoming = baseline
        let merged = incoming.reconciledSaveOnlyFields(
            currentScore: baseline.score + 2,
            currentPutts: baseline.putts + 1,
            currentPenaltyCount: baseline.penaltyCount + 1,
            lastApplied: baseline
        )
        XCTAssertEqual(merged.score, baseline.score + 2)
        XCTAssertEqual(merged.putts, baseline.putts + 1)
        XCTAssertEqual(merged.penaltyCount, baseline.penaltyCount + 1)
    }

    func testReconcileSaveOnlyFieldsAdoptsSnapshotForUntouchedFields() throws {
        // A field the user has NOT touched (on-screen value still equals the baseline) adopts
        // the incoming snapshot — a remote/watch sync that legitimately advanced a value wins
        // when there is no competing local edit.
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try fixturePackage()
        let baseline = try XCTUnwrap(
            try store.restoreLiveRoundState(roundId: package.roundId, package: package).holeState(for: 1)
        )
        var incoming = baseline
        incoming.score = baseline.score + 3
        incoming.putts = baseline.putts + 2
        incoming.penaltyCount = baseline.penaltyCount + 1
        let merged = incoming.reconciledSaveOnlyFields(
            currentScore: baseline.score,
            currentPutts: baseline.putts,
            currentPenaltyCount: baseline.penaltyCount,
            lastApplied: baseline
        )
        XCTAssertEqual(merged.score, baseline.score + 3)
        XCTAssertEqual(merged.putts, baseline.putts + 2)
        XCTAssertEqual(merged.penaltyCount, baseline.penaltyCount + 1)
    }

    func testReconcileSaveOnlyFieldsKeepsLocalEditWhenNoBaseline() throws {
        // Fresh hole: no prior live state, so there is no baseline to prove a field is clean.
        // Save-only fields default to preserving the on-screen edit rather than clobbering it
        // with a partial snapshot.
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try fixturePackage()
        let incoming = try XCTUnwrap(
            try store.restoreLiveRoundState(roundId: package.roundId, package: package).holeState(for: 1)
        )
        let merged = incoming.reconciledSaveOnlyFields(
            currentScore: incoming.score + 5,
            currentPutts: incoming.putts + 1,
            currentPenaltyCount: incoming.penaltyCount + 2,
            lastApplied: nil
        )
        XCTAssertEqual(merged.score, incoming.score + 5)
        XCTAssertEqual(merged.putts, incoming.putts + 1)
        XCTAssertEqual(merged.penaltyCount, incoming.penaltyCount + 2)
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
