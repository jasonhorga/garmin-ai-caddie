import XCTest
@testable import AICaddie

private func makeCustomAnchoredOfflineStore(
    directoryURL: URL,
    trustedDirectoryAnchor: URL,
    syncEventLogFile: @escaping (URL) throws -> Void,
    syncEventLogDirectory: @escaping (URL) throws -> Void
) -> OfflineStore {
    return OfflineStore(
        directoryURL: directoryURL,
        trustedDirectoryAnchor: trustedDirectoryAnchor,
        syncEventLogFile: syncEventLogFile,
        syncEventLogDirectory: syncEventLogDirectory
    )
}

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

    func testAccountScopesNeverReuseAnotherPlayersPackageEventsOrTemplate() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try localFixturePackage()
        let accountAEvent = LiveRoundEvent(
            eventId: "account-a-score",
            roundId: package.roundId,
            timestamp: "2026-08-07T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )
        let png = validOnePixelPNGData()

        // Upgrade path: an already-authenticated player owns the legacy unscoped cache.
        try store.saveRoundPackage(package)
        try store.saveHomePackage(package)
        try store.appendEvent(accountAEvent)
        XCTAssertTrue(try store.saveCourseTopoImage(
            png,
            globalId: package.course.globalId,
            localHole: 1
        ))
        store.bindAccount(playerId: "player-a", migrateLegacyData: true)
        XCTAssertEqual(try store.loadCurrentRoundPackage()?.roundId, package.roundId)
        XCTAssertEqual(try store.loadEvents(), [accountAEvent])
        XCTAssertFalse(try store.loadCourseTemplates().isEmpty)

        // A new family member gets a clean personal scope, but can reuse factual map pixels.
        store.bindAccount(playerId: "player-b", migrateLegacyData: false)
        XCTAssertNil(try store.loadCurrentRoundPackage())
        XCTAssertNil(try store.loadHomePackage())
        XCTAssertTrue(try store.loadEvents().isEmpty)
        XCTAssertTrue(try store.loadCourseTemplates().isEmpty)
        XCTAssertEqual(
            store.loadCourseTopoImage(globalId: package.course.globalId, localHole: 1),
            png
        )

        let accountBEvent = LiveRoundEvent(
            eventId: "account-b-score",
            roundId: package.roundId,
            timestamp: "2026-08-07T00:01:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(6)]
        )
        try store.saveRoundPackage(package)
        try store.appendEvent(accountBEvent)
        XCTAssertEqual(try store.loadEvents(), [accountBEvent])

        store.bindAccount(playerId: "player-a", migrateLegacyData: false)
        XCTAssertEqual(try store.loadEvents(), [accountAEvent])
        XCTAssertEqual(try store.loadCurrentRoundPackage()?.roundId, package.roundId)
    }

    func testCourseTemplateSurvivesRoundDiscardAndRebasesWithoutOldIdentityOrCursor() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try localFixturePackage()
        try store.saveRoundPackage(package)
        try store.appendEvent(LiveRoundEvent(
            eventId: "old-score",
            roundId: package.roundId,
            timestamp: "2026-08-07T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        ))

        try store.discardRound(roundId: package.roundId)
        XCTAssertNil(try store.loadRoundPackage(roundId: package.roundId))
        XCTAssertFalse(try store.loadEvents().contains { $0.roundId == package.roundId })

        let template = try XCTUnwrap(store.loadCourseTemplate(
            globalId: package.course.globalId,
            teeBox: package.course.teeBox,
            nine: package.nine ?? "all"
        ))
        let rebased = template.rebasedForOfflineStart(
            roundId: "offline-new-round",
            generatedAt: Date(timeIntervalSince1970: 1_800_000_000)
        )
        XCTAssertEqual(rebased.roundId, "offline-new-round")
        XCTAssertEqual(rebased.course, package.course)
        XCTAssertEqual(rebased.holes, package.holes)
        XCTAssertEqual(rebased.eventCursor.serverSequence, 0)
        XCTAssertEqual(rebased.eventCursor.pendingEventCount, 0)
        XCTAssertEqual(rebased.eventCursor.lastAckedServerSequence, 0)
        XCTAssertNil(rebased.eventCursor.replayEndpoint)
        XCTAssertEqual(rebased.sourceCoverage.requestedRoundId, "offline-new-round")
        XCTAssertNil(rebased.sourceCoverage.selectedRoundId)
        XCTAssertFalse(rebased.sourceCoverage.roundFound)
        let oldSeed = try XCTUnwrap(package.caddieContextSeeds.first)
        let seed = try XCTUnwrap(rebased.caddieContextSeeds.first)
        let expectedSeedRef = "offline-new-round:\(seed.hole)"
        XCTAssertEqual(seed.sourceRef, expectedSeedRef)
        XCTAssertEqual(seed.context["roundId"], .string("offline-new-round"))
        XCTAssertEqual(seed.context["sourceRef"], .string(expectedSeedRef))
        XCTAssertFalse(seed.offlineOptions.isEmpty)
        XCTAssertTrue(seed.offlineOptions.allSatisfy { option in
            option.sourceRefs.contains(expectedSeedRef)
                && !option.sourceRefs.contains(oldSeed.sourceRef)
        })
        XCTAssertEqual(
            seed.offlineOptions.map(\.sampleRefs),
            oldSeed.offlineOptions.map(\.sampleRefs),
            "historical shot evidence must survive a new offline round"
        )
        XCTAssertFalse(seed.evidence.contains { row in
            row.values.contains(.string(oldSeed.sourceRef))
        })
        XCTAssertTrue(rebased.readinessChecks.allSatisfy { check in
            !check.sourceRefs.contains(oldSeed.sourceRef)
        })
        XCTAssertFalse(try store.loadEvents().contains { $0.roundId == rebased.roundId })
        XCTAssertNil(try store.loadCourseTemplate(
            globalId: package.course.globalId,
            teeBox: "white",
            nine: package.nine ?? "all"
        ))
    }

    func testCourseTemplateDoesNotDowngradeWhenLaterPackageHasLessGeometry() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let partial = try localFixturePackage()
        let ready = replacingGeometryCoverage(
            in: partial,
            with: GeometryCoverage(
                state: .ready,
                readyHoles: partial.holes.count,
                totalHoles: partial.holes.count
            ),
            generatedAt: "2026-08-06T00:00:00Z"
        )
        let laterPartial = replacingGeometryCoverage(
            in: partial,
            with: GeometryCoverage(
                state: .partial,
                readyHoles: 0,
                totalHoles: partial.holes.count
            ),
            generatedAt: "2026-08-07T00:00:00Z"
        )

        try store.saveCourseTemplate(ready)
        try store.saveCourseTemplate(laterPartial)

        let retained = try XCTUnwrap(store.loadCourseTemplate(
            globalId: ready.course.globalId,
            teeBox: ready.course.teeBox,
            nine: ready.nine ?? "all"
        ))
        XCTAssertEqual(retained.geometryCoverage.state, .ready)
        XCTAssertEqual(retained.geometryCoverage.readyHoles, ready.holes.count)
        XCTAssertEqual(retained.generatedAt, "2026-08-06T00:00:00Z")
    }

    func testCourseTemplateDoesNotReplaceEighteenPlayableHolesWithANewerSingleHolePackage() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let partial = try localFixturePackage()
        let sourceHole = try XCTUnwrap(partial.holes.first)
        let fullHoles = (1...18).map { number in
            Hole(
                number: number,
                par: number % 3 == 0 ? 3 : (number % 5 == 0 ? 5 : 4),
                yards: sourceHole.yards,
                geometryCoverage: sourceHole.geometryCoverage,
                sourceGlobalId: partial.course.globalId,
                sourceLocalHole: number,
                teeLatitude: sourceHole.teeLatitude,
                teeLongitude: sourceHole.teeLongitude
            )
        }
        let full = replacingHoles(
            in: partial,
            with: fullHoles,
            generatedAt: "2026-08-06T00:00:00Z"
        )
        let laterSingleHole = replacingHoles(
            in: partial,
            with: [sourceHole],
            generatedAt: "2026-08-07T00:00:00Z"
        )

        try store.saveCourseTemplate(full)
        try store.saveCourseTemplate(laterSingleHole)

        let retained = try XCTUnwrap(store.loadCourseTemplate(
            globalId: full.course.globalId,
            teeBox: full.course.teeBox,
            nine: full.nine ?? "all"
        ))
        XCTAssertEqual(retained.holes.count, 18)
        XCTAssertEqual(retained.generatedAt, "2026-08-06T00:00:00Z")
    }

    func testCourseTopoCacheAcceptsOnlyPngAndUsesStaticCourseHoleIdentity() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let png = validOnePixelPNGData()

        XCTAssertFalse(try store.saveCourseTopoImage(
            Data("not-an-image".utf8),
            globalId: 31795,
            localHole: 1
        ))
        XCTAssertFalse(try store.saveCourseTopoImage(
            Data([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]),
            globalId: 31795,
            localHole: 1
        ))
        XCTAssertNil(store.loadCourseTopoImageURL(globalId: 31795, localHole: 1))
        XCTAssertTrue(try store.saveCourseTopoImage(
            png,
            globalId: 31795,
            localHole: 1
        ))
        XCTAssertTrue(
            FileManager.default.fileExists(
                atPath: directory
                    .appendingPathComponent("course_topo", isDirectory: true)
                    .appendingPathComponent(SyncClient.topoStyleVersion, isDirectory: true)
                    .appendingPathComponent("31795-1.png")
                    .path
            ),
            "renderer version must participate in the installed-device cache identity"
        )
        XCTAssertEqual(store.loadCourseTopoImage(globalId: 31795, localHole: 1), png)
        XCTAssertNil(store.loadCourseTopoImage(globalId: 31795, localHole: 2))
        XCTAssertNil(store.loadCourseTopoImage(globalId: -1, localHole: 1))
    }

    func testCourseTopoCacheDoesNotReuseLegacyUnversionedPixels() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let legacyDirectory = directory.appendingPathComponent("course_topo", isDirectory: true)
        try FileManager.default.createDirectory(at: legacyDirectory, withIntermediateDirectories: true)
        try validOnePixelPNGData().write(
            to: legacyDirectory.appendingPathComponent("31795-1.png"),
            options: .atomic
        )

        let store = OfflineStore(directoryURL: directory)

        XCTAssertNil(store.loadCourseTopoImage(globalId: 31795, localHole: 1))
        XCTAssertNil(store.loadCourseTopoImageURL(globalId: 31795, localHole: 1))
    }

    func testOfflineMapCompletenessRequiresEveryPrecisePrepAndTopoImage() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let source = try localFixturePackage()

        let noPrep = source.replacingCoursePrep(nil)
        XCTAssertFalse(noPrep.hasCompleteOfflineCoursePrep)
        XCTAssertFalse(store.hasCourseTopoImages(for: noPrep))

        let partial = replacingCoursePrep(in: source, geometryCoverage: "partial")
        XCTAssertFalse(partial.hasCompleteOfflineCoursePrep)
        XCTAssertTrue(try store.saveCourseTopoImage(
            validOnePixelPNGData(),
            globalId: source.course.globalId,
            localHole: source.holes[0].sourceLocalHole ?? source.holes[0].number
        ))
        XCTAssertFalse(
            store.hasCourseTopoImages(for: partial),
            "a lightweight outline plus PNG must not masquerade as a precise offline course"
        )

        let ready = replacingCoursePrep(in: source, geometryCoverage: "ready")
        XCTAssertTrue(ready.hasCompleteOfflineCoursePrep)
        XCTAssertTrue(store.hasCourseTopoImages(for: ready))

        let missingImageStore = OfflineStore(
            directoryURL: FileManager.default.temporaryDirectory
                .appendingPathComponent(UUID().uuidString, isDirectory: true)
        )
        XCTAssertFalse(
            missingImageStore.hasCourseTopoImages(for: ready),
            "ready facts without the production PNG are not a complete offline map"
        )
    }

    func testSaveAndLoadHomePackageCreatesFreshStoreDirectory() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try fixturePackage()

        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.path))
        do {
            try store.saveHomePackage(package)
        } catch {
            XCTFail("fresh-install home package must persist without prior store writes: \(error)")
            return
        }

        XCTAssertEqual(try store.loadHomePackage()?.roundId, package.roundId)
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
            let logURL = directory.appendingPathComponent("events.jsonl")
            let rawBeforeReplay = try Data(contentsOf: logURL)
            XCTAssertEqual(rawBeforeReplay.last, 0x0A, "raw newline: \(testCase.name)")
            let rawLines = rawBeforeReplay.split(separator: 0x0A)
            XCTAssertEqual(rawLines.count, 1, "raw row count: \(testCase.name)")
            XCTAssertEqual(
                try JSONDecoder().decode(
                    LiveRoundEvent.self,
                    from: Data(try XCTUnwrap(rawLines.first))
                ),
                testCase.expected,
                "raw transport drift: \(testCase.name)"
            )

            let reopened = OfflineStore(directoryURL: directory)
            XCTAssertEqual(
                try reopened.loadEvents(),
                [testCase.expected],
                "append/reload privacy drift: \(testCase.name)"
            )
            XCTAssertFalse(
                try reopened.applyReplayEvents([testCase.input]),
                "sanitized exact replay appended: \(testCase.name)"
            )
            XCTAssertEqual(
                try Data(contentsOf: logURL),
                rawBeforeReplay,
                "exact replay rewrote raw bytes: \(testCase.name)"
            )
            XCTAssertEqual(
                try reopened.loadEvents(),
                [testCase.expected],
                "replay privacy drift: \(testCase.name)"
            )
        }
    }

    func testPrivacySanitizerCoversGeneratedPathAndUnicodeFamilies() throws {
        var pathInputs: [String] = []
        var pathExpected: [String] = []
        for rootName in ["alpha", "opt", "srv-custom", "数据"] {
            for boundary in ["", "path:", "source:", "value=", "("] {
                pathInputs.append("\(boundary)/\(rootName)/private/file.txt")
                pathExpected.append("\(boundary)[REDACTED_PATH]")
            }
        }
        for driveLetter in ["C", "c", "Z", "z"] {
            for separator in ["\\", "/"] {
                pathInputs.append(
                    "drive=\(driveLetter):\(separator)users\(separator)alice\(separator)private.txt"
                )
                pathExpected.append("drive=[REDACTED_PATH]")
            }
        }
        pathInputs.append(contentsOf: [
            #"\\fileserver\rounds\private.json"#,
            "//fileserver/rounds/private.json",
            "file:///var/mobile/private.json",
            "FILE://server/share/private.json",
        ])
        pathExpected.append(contentsOf: Array(repeating: "[REDACTED_PATH]", count: 4))
        let preservedURLs = [
            "https://example.test/opt/public",
            "https://example.test/C:/users/alice/private.txt",
            "https://example.test//fileserver/share/x",
            "http://example.test/srv/public",
            "custom://host/root/public",
            "https://example.test/search?course=private",
        ]
        let bearerInputs = ["Bearer İ", "Bearer ı", "Bearer 密钥Δ"]
        let event = LiveRoundEvent(
            schema: "source:/schema-root/private.json token=structural-secret",
            eventId: "//identity-server/share/event",
            roundId: "/identity-root/round",
            clientId: "Bearer ı",
            timestamp: "Bearer İ path:/clock-root/private.txt",
            hole: 1,
            kind: .note,
            payload: [
                "paths": .array(pathInputs.map(JSONValue.string)),
                "urls": .array(preservedURLs.map(JSONValue.string)),
                "bearers": .array(bearerInputs.map(JSONValue.string)),
            ]
        )
        let localMedia = LiveRoundEvent(
            eventId: "local-media-placeholder",
            roundId: event.roundId,
            clientId: "ios-phone",
            timestamp: "2026-07-23T00:00:00Z",
            hole: 1,
            kind: .photo,
            payload: [
                "fileURL": .string("[REDACTED_LOCAL_MEDIA_URL]"),
                "note": .string("public"),
            ]
        )
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)

        try store.appendEvent(event)
        try store.appendEvent(localMedia)
        let expected = LiveRoundEvent(
            schema: "source:[REDACTED_PATH] token=[REDACTED]",
            eventId: event.eventId,
            roundId: event.roundId,
            clientId: event.clientId,
            timestamp: "Bearer [REDACTED] path:[REDACTED_PATH]",
            hole: 1,
            kind: .note,
            payload: [
                "paths": .array(pathExpected.map(JSONValue.string)),
                "urls": .array(preservedURLs.map(JSONValue.string)),
                "bearers": .array(
                    Array(repeating: .string("Bearer [REDACTED]"), count: bearerInputs.count)
                ),
            ]
        )
        let logURL = directory.appendingPathComponent("events.jsonl")
        let rawBeforeReplay = try Data(contentsOf: logURL)
        XCTAssertEqual(rawBeforeReplay.last, 0x0A)
        let rawLines = rawBeforeReplay.split(separator: 0x0A)
        XCTAssertEqual(rawLines.count, 2)
        XCTAssertEqual(
            try rawLines.map {
                try JSONDecoder().decode(LiveRoundEvent.self, from: Data($0))
            },
            [expected, localMedia]
        )

        let reopened = OfflineStore(directoryURL: directory)
        let events = try reopened.loadEvents()
        let sanitized = try XCTUnwrap(events.first)
        let sanitizedMedia = try XCTUnwrap(events.last)

        XCTAssertEqual(sanitized.eventId, event.eventId)
        XCTAssertEqual(sanitized.roundId, event.roundId)
        XCTAssertEqual(sanitized.clientId, event.clientId)
        XCTAssertEqual(
            sanitized.schema,
            "source:[REDACTED_PATH] token=[REDACTED]"
        )
        XCTAssertEqual(
            sanitized.timestamp,
            "Bearer [REDACTED] path:[REDACTED_PATH]"
        )
        XCTAssertEqual(
            sanitized.payload["paths"],
            .array(pathExpected.map(JSONValue.string))
        )
        XCTAssertEqual(
            sanitized.payload["urls"],
            .array(preservedURLs.map(JSONValue.string))
        )
        XCTAssertEqual(
            sanitized.payload["bearers"],
            .array(Array(repeating: .string("Bearer [REDACTED]"), count: bearerInputs.count))
        )
        XCTAssertEqual(
            sanitizedMedia.payload["fileURL"],
            .string("[REDACTED_LOCAL_MEDIA_URL]")
        )
        XCTAssertFalse(try reopened.applyReplayEvents([event, localMedia]))
        XCTAssertEqual(try Data(contentsOf: logURL), rawBeforeReplay)
        XCTAssertEqual(
            try OfflineStore(directoryURL: directory).loadEvents(),
            [expected, localMedia]
        )
    }

    func testLargeDecisionAuditAppendAndReloadDoesNotBlockClubSelection() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let auditRows: [JSONValue] = (0..<24).map { index in
            .object([
                "club": .string("Club \(index)"),
                "label": .string("Stock option \(index)"),
                "shotType": .string("approach"),
                "targetKind": .string("planned landing"),
                "surface": .string("fairway"),
                "rationale": .string("Public caddie rationale \(index)"),
            ])
        }
        let event = LiveRoundEvent(
            eventId: "large-decision-club-event",
            roundId: "round-1",
            clientId: "ios-phone",
            timestamp: "2026-07-29T00:00:00Z",
            hole: 2,
            kind: .club,
            payload: [
                "clubName": .string("3W"),
                "decision": .object([
                    "schema": .string("ai-caddie-decision-v1"),
                    "shotType": .string("tee"),
                    "phase": .string("planning"),
                    "context": .object([
                        "courseName": .string("Real course"),
                        "holeLabel": .string("Hole 2"),
                        "strategyMode": .string("stock"),
                    ]),
                    "options": .array(auditRows),
                    "evidence": .array(auditRows),
                    "auditCriteria": .array(auditRows),
                ]),
            ]
        )

        let startedAt = ProcessInfo.processInfo.systemUptime
        try store.appendEvent(event)
        let reloaded = try store.loadEvents()
        let elapsed = ProcessInfo.processInfo.systemUptime - startedAt

        XCTAssertEqual(reloaded, [event])
        XCTAssertLessThan(
            elapsed,
            2.0,
            "club selection persisted and reloaded in \(elapsed)s; this runs synchronously on tap"
        )
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

        let logURL = directory.appendingPathComponent("events.jsonl")
        let encoder = JSONEncoder()
        let decoder = JSONDecoder()
        let beforeEvents = try store.loadPendingEvents(roundId: "round-1")
        let beforeBatch = try decoder.decode(
            EventBatch.self,
            from: encoder.encode(EventBatch(roundId: "round-1", events: beforeEvents))
        )
        let beforeKey = "round-1-" + beforeEvents.map(\.eventId).joined(separator: "-")
        let beforeLog = try Data(contentsOf: logURL)

        // The event POST response was lost, then the independently queued media upload succeeded.
        try store.removePendingMedia(ids: Set([attachment.id]))

        let afterEvents = try store.loadPendingEvents(roundId: "round-1")
        let afterBatch = try decoder.decode(
            EventBatch.self,
            from: encoder.encode(EventBatch(roundId: "round-1", events: afterEvents))
        )
        let afterKey = "round-1-" + afterEvents.map(\.eventId).joined(separator: "-")
        XCTAssertEqual(afterBatch, beforeBatch)
        XCTAssertEqual(afterKey, beforeKey)
        XCTAssertEqual(try Data(contentsOf: logURL), beforeLog)
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

    func testGenuinelyIncompleteJSONPrefixesRemainRepairable() throws {
        let tornKey = Data(#"{"eventId"#.utf8)
        var partialEscape = Data(#"{"eventId":"torn"#.utf8)
        partialEscape.append(0x5C)
        var truncatedUTF8 = Data(#"{"eventId":"torn "#.utf8)
        truncatedUTF8.append(contentsOf: Array("雪".utf8).prefix(2))
        let tornPrefixes: [(name: String, bytes: Data)] = [
            ("torn-key", tornKey),
            ("partial-escape", partialEscape),
            ("truncated-utf8", truncatedUTF8),
        ]

        for testCase in tornPrefixes {
            let directory = FileManager.default.temporaryDirectory
                .appendingPathComponent(UUID().uuidString, isDirectory: true)
            try FileManager.default.createDirectory(
                at: directory,
                withIntermediateDirectories: true
            )
            let logURL = directory.appendingPathComponent("events.jsonl")
            let existing = LiveRoundEvent(
                eventId: "existing-\(testCase.name)",
                roundId: "round-1",
                clientId: "ios-phone",
                timestamp: "2026-07-21T00:00:00Z",
                hole: 1,
                kind: .score,
                payload: ["strokes": .number(4)]
            )
            let replayed = LiveRoundEvent(
                eventId: "replayed-\(testCase.name)",
                roundId: "round-1",
                clientId: "apple-watch",
                timestamp: "2026-07-21T00:00:01Z",
                hole: 1,
                kind: .score,
                payload: ["strokes": .number(5)]
            )
            var tornLog = try JSONEncoder().encode(existing)
            tornLog.append(0x0A)
            tornLog.append(testCase.bytes)
            try tornLog.write(to: logURL, options: [.atomic])
            let store = OfflineStore(directoryURL: directory)

            XCTAssertTrue(try store.applyReplayEvents([replayed]), testCase.name)
            XCTAssertEqual(
                try store.loadEvents(),
                [existing, replayed],
                testCase.name
            )
            let repaired = try Data(contentsOf: logURL)
            XCTAssertEqual(repaired.last, 0x0A, testCase.name)
            XCTAssertEqual(repaired.split(separator: 0x0A).count, 2, testCase.name)
        }
    }

    func testReplayRepairsOnlyValidIncompleteJSONGrammarPrefixes() throws {
        struct PrefixCase {
            let name: String
            let bytes: Data
            let isRepairable: Bool
        }

        var unescapedControl = Data(#"{"value":"bad"#.utf8)
        unescapedControl.append(0x01)
        let maximumJSONNestingDepth = 128
        let cases = [
            PrefixCase(name: "incomplete-number", bytes: Data("1e".utf8), isRepairable: true),
            PrefixCase(name: "invalid-number", bytes: Data("1eX".utf8), isRepairable: false),
            PrefixCase(name: "incomplete-literal", bytes: Data("tru".utf8), isRepairable: true),
            PrefixCase(name: "invalid-literal", bytes: Data("truX".utf8), isRepairable: false),
            PrefixCase(
                name: "incomplete-unicode-escape",
                bytes: Data(#"{"value":"\u12"#.utf8),
                isRepairable: true
            ),
            PrefixCase(
                name: "invalid-string-escape",
                bytes: Data(#"{"value":"\x"#.utf8),
                isRepairable: false
            ),
            PrefixCase(
                name: "incomplete-container",
                bytes: Data(#"{"value":[1,2"#.utf8),
                isRepairable: true
            ),
            PrefixCase(
                name: "unescaped-control",
                bytes: unescapedControl,
                isRepairable: false
            ),
            PrefixCase(
                name: "trailing-comma",
                bytes: Data(#"{"value":1,}"#.utf8),
                isRepairable: false
            ),
            PrefixCase(
                name: "missing-colon",
                bytes: Data(#"{"value" 1}"#.utf8),
                isRepairable: false
            ),
            PrefixCase(
                name: "complete-whitespace-torn-suffix",
                bytes: Data("true \r\t {\"eventId\":\"torn\"".utf8),
                isRepairable: false
            ),
            PrefixCase(
                name: "nesting-at-limit",
                bytes: Data(String(repeating: "[", count: maximumJSONNestingDepth).utf8),
                isRepairable: true
            ),
            PrefixCase(
                name: "nesting-over-limit",
                bytes: Data(String(repeating: "[", count: maximumJSONNestingDepth + 1).utf8),
                isRepairable: false
            ),
        ]

        for testCase in cases {
            let directory = FileManager.default.temporaryDirectory
                .appendingPathComponent(UUID().uuidString, isDirectory: true)
            try FileManager.default.createDirectory(
                at: directory,
                withIntermediateDirectories: true
            )
            let existing = LiveRoundEvent(
                eventId: "existing-grammar-\(testCase.name)",
                roundId: "round-1",
                clientId: "ios-phone",
                timestamp: "2026-07-21T00:00:00Z",
                hole: 1,
                kind: .score,
                payload: ["strokes": .number(4)]
            )
            let replayed = LiveRoundEvent(
                eventId: "replayed-grammar-\(testCase.name)",
                roundId: "round-1",
                clientId: "apple-watch",
                timestamp: "2026-07-21T00:00:01Z",
                hole: 1,
                kind: .score,
                payload: ["strokes": .number(5)]
            )
            let logURL = directory.appendingPathComponent("events.jsonl")
            var corruptLog = try JSONEncoder().encode(existing)
            corruptLog.append(0x0A)
            corruptLog.append(testCase.bytes)
            try corruptLog.write(to: logURL, options: [.atomic])
            let original = try Data(contentsOf: logURL)
            var fileCallbacks: [URL] = []
            var directoryCallbacks: [URL] = []
            let store = OfflineStore(
                directoryURL: directory,
                syncEventLogFile: { fileCallbacks.append($0) },
                syncEventLogDirectory: { directoryCallbacks.append($0) }
            )

            if testCase.isRepairable {
                XCTAssertTrue(try store.applyReplayEvents([replayed]), testCase.name)
                XCTAssertEqual(
                    try store.loadEvents(),
                    [existing, replayed],
                    testCase.name
                )
            } else {
                XCTAssertThrowsError(
                    try store.applyReplayEvents([replayed]),
                    testCase.name
                ) { error in
                    XCTAssertEqual(error as? OfflineStoreError, .eventLogCorrupt, testCase.name)
                }
                XCTAssertEqual(try Data(contentsOf: logURL), original, testCase.name)
                XCTAssertTrue(fileCallbacks.isEmpty, "\(testCase.name) attempted file repair")
                XCTAssertTrue(
                    directoryCallbacks.isEmpty,
                    "\(testCase.name) attempted directory repair"
                )
            }
        }
    }

    func testCompleteInvalidJSONValuesAtEOFFailClosedAndPreserveBytes() throws {
        let invalidValues = [
            #"{"schema":"ai-caddie-live-round-event-v1"}"#,
            #"["not-a-live-round-event"]"#,
            "null",
        ]
        for invalidValue in invalidValues {
            let directory = FileManager.default.temporaryDirectory
                .appendingPathComponent(UUID().uuidString, isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let logURL = directory.appendingPathComponent("events.jsonl")
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
                eventId: "must-not-bless-invalid-tail",
                roundId: "round-1",
                clientId: "apple-watch",
                timestamp: "2026-07-21T00:00:01Z",
                hole: 1,
                kind: .score,
                payload: ["strokes": .number(5)]
            )
            var corruptLog = try JSONEncoder().encode(existing)
            corruptLog.append(Data([0x0A]))
            corruptLog.append(Data(invalidValue.utf8))
            try corruptLog.write(to: logURL, options: [.atomic])
            let original = try Data(contentsOf: logURL)
            let store = OfflineStore(directoryURL: directory)

            XCTAssertThrowsError(try store.loadEvents(), invalidValue) { error in
                XCTAssertEqual(error as? OfflineStoreError, .eventLogCorrupt)
            }
            XCTAssertEqual(try Data(contentsOf: logURL), original, invalidValue)
            XCTAssertThrowsError(try store.applyReplayEvents([replayed]), invalidValue) { error in
                XCTAssertEqual(error as? OfflineStoreError, .eventLogCorrupt)
            }
            XCTAssertEqual(try Data(contentsOf: logURL), original, invalidValue)
            XCTAssertThrowsError(try store.appendEvent(replayed), invalidValue) { error in
                XCTAssertEqual(error as? OfflineStoreError, .eventLogCorrupt)
            }
            XCTAssertEqual(try Data(contentsOf: logURL), original, invalidValue)
        }
    }

    func testCompleteJSONPrefixFollowedByTornSuffixFailsClosedAndPreservesBytes() throws {
        let completeOrInvalidPrefixes = [
            "object": #"{"schema":"complete-but-invalid"}"#,
            "array": #"["complete-but-invalid"]"#,
            "null": "null",
            "string-escaped-unicode": #""escaped \"quote\" \\ snowman \u2603 雪""#,
            "number": "-12.5e+3",
            "true": "true",
            "false": "false",
            "invalid-string-escape": #"{"value":"bad\x"#,
        ]
        let tornSuffix = #"{"eventId":"torn""#
        var nonRepairableTails = completeOrInvalidPrefixes.map { name, prefix in
            (name: name, bytes: Data((prefix + tornSuffix).utf8))
        }
        var invalidUTF8 = Data(#"{"value":"bad "#.utf8)
        invalidUTF8.append(contentsOf: [0xE9, 0x28])
        invalidUTF8.append(Data(tornSuffix.utf8))
        nonRepairableTails.append((name: "invalid-utf8", bytes: invalidUTF8))
        var invalidShortThreeByteUTF8 = Data(#"{"value":"bad "#.utf8)
        invalidShortThreeByteUTF8.append(contentsOf: [0xE9, 0x28])
        nonRepairableTails.append(
            (name: "invalid-short-three-byte-utf8", bytes: invalidShortThreeByteUTF8)
        )
        var invalidShortFourByteUTF8 = Data(#"{"value":"bad "#.utf8)
        invalidShortFourByteUTF8.append(contentsOf: [0xF0, 0x90, 0x28])
        nonRepairableTails.append(
            (name: "invalid-short-four-byte-utf8", bytes: invalidShortFourByteUTF8)
        )

        for (prefixFamily, nonRepairableTail) in nonRepairableTails {
            for operation in ["load", "replay", "append"] {
                let directory = FileManager.default.temporaryDirectory
                    .appendingPathComponent(UUID().uuidString, isDirectory: true)
                try FileManager.default.createDirectory(
                    at: directory,
                    withIntermediateDirectories: true
                )
                let logURL = directory.appendingPathComponent("events.jsonl")
                let existing = LiveRoundEvent(
                    eventId: "existing",
                    roundId: "round-1",
                    clientId: "ios-phone",
                    timestamp: "2026-07-21T00:00:00Z",
                    hole: 1,
                    kind: .score,
                    payload: ["strokes": .number(4)]
                )
                let incoming = LiveRoundEvent(
                    eventId: "must-not-bless-composite-tail",
                    roundId: "round-1",
                    clientId: "apple-watch",
                    timestamp: "2026-07-21T00:00:01Z",
                    hole: 1,
                    kind: .note,
                    payload: ["note": .string("must remain absent")]
                )
                var corruptLog = try JSONEncoder().encode(existing)
                corruptLog.append(Data([0x0A]))
                corruptLog.append(nonRepairableTail)
                try corruptLog.write(to: logURL, options: [.atomic])
                let original = try Data(contentsOf: logURL)
                var repairFileBarriers: [URL] = []
                var repairDirectoryBarriers: [URL] = []
                let store = OfflineStore(
                    directoryURL: directory,
                    syncEventLogFile: { url in
                        repairFileBarriers.append(url)
                    },
                    syncEventLogDirectory: { url in
                        repairDirectoryBarriers.append(url)
                    }
                )
                let context = "\(prefixFamily)-\(operation)"

                do {
                    switch operation {
                    case "load":
                        _ = try store.loadEvents()
                    case "replay":
                        _ = try store.applyReplayEvents([incoming])
                    default:
                        try store.appendEvent(incoming)
                    }
                    XCTFail("\(context) accepted a complete corrupt JSON prefix")
                } catch {
                    XCTAssertEqual(error as? OfflineStoreError, .eventLogCorrupt, context)
                }
                let after = try Data(contentsOf: logURL)
                XCTAssertEqual(after, original, context)
                XCTAssertTrue(repairFileBarriers.isEmpty, "\(context) attempted file repair")
                XCTAssertTrue(
                    repairDirectoryBarriers.isEmpty,
                    "\(context) attempted directory repair"
                )
                XCTAssertFalse(String(decoding: after, as: UTF8.self).contains(incoming.eventId))
            }
        }
    }

    func testReplayFirstLogCreationRequiresFileAndDirectoryDurabilityBeforeSuccess() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let canonicalDirectoryPath = directory.standardizedFileURL
            .resolvingSymlinksInPath().path
        var barriers: [String] = []
        let store = OfflineStore(
            directoryURL: directory,
            syncEventLogFile: { url in
                barriers.append("file:\(url.lastPathComponent)")
            },
            syncEventLogDirectory: { url in
                barriers.append("directory:\(url.lastPathComponent)")
                let callbackDirectoryPath = url.standardizedFileURL
                    .resolvingSymlinksInPath().path
                if callbackDirectoryPath == canonicalDirectoryPath {
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

        // The replace may already be visible despite an uncertain directory barrier. Exact reuse
        // must establish a fresh file + directory barrier before a successful page result.
        var uncertainRetryBarriers: [String] = []
        let uncertainRetry = OfflineStore(
            directoryURL: directory,
            syncEventLogFile: { url in
                uncertainRetryBarriers.append("file:\(url.lastPathComponent)")
            },
            syncEventLogDirectory: { url in
                uncertainRetryBarriers.append("directory:\(url.lastPathComponent)")
                let callbackDirectoryPath = url.standardizedFileURL
                    .resolvingSymlinksInPath().path
                if callbackDirectoryPath == canonicalDirectoryPath {
                    throw TestDurabilityFailure.directorySync
                }
            }
        )
        XCTAssertThrowsError(try uncertainRetry.applyReplayEvents([replayed])) { error in
            XCTAssertEqual(error as? TestDurabilityFailure, .directorySync)
        }
        XCTAssertEqual(
            Array(uncertainRetryBarriers.suffix(2)),
            ["file:events.jsonl", "directory:\(directory.lastPathComponent)"]
        )

        var successfulRetryBarriers: [String] = []
        let successfulRetry = OfflineStore(
            directoryURL: directory,
            syncEventLogFile: { url in
                successfulRetryBarriers.append("file:\(url.lastPathComponent)")
            },
            syncEventLogDirectory: { url in
                successfulRetryBarriers.append("directory:\(url.lastPathComponent)")
            }
        )
        XCTAssertFalse(try successfulRetry.applyReplayEvents([replayed]))
        XCTAssertEqual(
            Array(successfulRetryBarriers.suffix(2)),
            ["file:events.jsonl", "directory:\(directory.lastPathComponent)"]
        )
        XCTAssertEqual(try successfulRetry.loadEvents(), [replayed])
    }

    func testNestedDirectoryBarrierFailuresRetryAllAncestorsBeforeEventMutation() throws {
        let trustedAnchor = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true)
            .standardizedFileURL.resolvingSymlinksInPath()
        let testRoot = trustedAnchor.appendingPathComponent(
            ".aicaddie-directory-barrier-\(UUID().uuidString)",
            isDirectory: true
        )
        defer { try? FileManager.default.removeItem(at: testRoot) }
        let prototypeStore = testRoot
            .appendingPathComponent("prototype", isDirectory: true)
            .appendingPathComponent("level-two", isDirectory: true)
            .appendingPathComponent("mobile-events", isDirectory: true)
        let barrierCount = try directoryCreationParents(
            from: trustedAnchor,
            to: prototypeStore
        ).count

        for failedIndex in 0..<barrierCount {
            let levelOne = testRoot.appendingPathComponent(
                "case-\(failedIndex)",
                isDirectory: true
            )
            let levelTwo = levelOne.appendingPathComponent("level-two", isDirectory: true)
            let storeDirectory = levelTwo.appendingPathComponent("mobile-events", isDirectory: true)
            let creationParents = try directoryCreationParents(
                from: trustedAnchor,
                to: storeDirectory
            )
            XCTAssertEqual(creationParents.count, barrierCount)
            let failedParent = creationParents[failedIndex]
            var failedOnce = false
            var firstAttemptBarriers: [URL] = []
            let event = LiveRoundEvent(
                eventId: "nested-\(failedIndex)",
                roundId: "round-1",
                clientId: "ios-phone",
                timestamp: "2026-07-23T00:00:00Z",
                hole: 1,
                kind: .score,
                payload: ["strokes": .number(4)]
            )
            let failingStore = OfflineStore(
                directoryURL: storeDirectory,
                trustedDirectoryAnchor: trustedAnchor,
                syncEventLogFile: { _ in
                    XCTFail("event file mutated before all directory barriers")
                },
                syncEventLogDirectory: { url in
                    let resolved = url.standardizedFileURL.resolvingSymlinksInPath()
                    firstAttemptBarriers.append(resolved)
                    if resolved == failedParent, !failedOnce {
                        failedOnce = true
                        throw TestDurabilityFailure.directorySync
                    }
                }
            )

            XCTAssertThrowsError(try failingStore.appendEvent(event)) { error in
                XCTAssertEqual(error as? TestDurabilityFailure, .directorySync)
            }
            XCTAssertTrue(failedOnce, "creation barrier \(failedIndex) was never exercised")
            XCTAssertEqual(
                firstAttemptBarriers,
                Array(creationParents.prefix(failedIndex + 1))
            )
            let logURL = storeDirectory.appendingPathComponent("events.jsonl")
                .standardizedFileURL.resolvingSymlinksInPath()
            XCTAssertFalse(FileManager.default.fileExists(atPath: logURL.path))

            var retryOperations: [String] = []
            let retryStore = OfflineStore(
                directoryURL: storeDirectory,
                trustedDirectoryAnchor: trustedAnchor,
                syncEventLogFile: { url in
                    XCTAssertEqual(
                        Array(retryOperations.prefix(creationParents.count)),
                        creationParents.map { "directory:\($0.path)" }
                    )
                    retryOperations.append(
                        "file:\(url.standardizedFileURL.resolvingSymlinksInPath().path)"
                    )
                },
                syncEventLogDirectory: { url in
                    retryOperations.append(
                        "directory:\(url.standardizedFileURL.resolvingSymlinksInPath().path)"
                    )
                    if retryOperations.count <= creationParents.count {
                        XCTAssertFalse(FileManager.default.fileExists(atPath: logURL.path))
                    }
                }
            )

            try retryStore.appendEvent(event)

            XCTAssertEqual(
                Array(retryOperations.prefix(creationParents.count)),
                creationParents.map { "directory:\($0.path)" }
            )
            let eventFileIndex = try XCTUnwrap(
                retryOperations.firstIndex(of: "file:\(logURL.path)")
            )
            let storeDirectoryPath = storeDirectory.standardizedFileURL
                .resolvingSymlinksInPath().path
            let storeDirectoryIndex = try XCTUnwrap(
                retryOperations[(eventFileIndex + 1)...].firstIndex(
                    of: "directory:\(storeDirectoryPath)"
                )
            )
            XCTAssertLessThan(eventFileIndex, storeDirectoryIndex)
            XCTAssertEqual(try retryStore.loadEvents(), [event])
        }
    }

    func testCustomDirectoryConvenienceAnchorsAtNearestExistingAncestor() throws {
        let existingRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(
            at: existingRoot,
            withIntermediateDirectories: true
        )
        defer { try? FileManager.default.removeItem(at: existingRoot) }
        let missingParent = existingRoot.appendingPathComponent(
            "missing-parent",
            isDirectory: true
        )
        let storeDirectory = missingParent.appendingPathComponent("store", isDirectory: true)
        let logURL = storeDirectory.appendingPathComponent("events.jsonl")
        let expectedCreationBarriers = [existingRoot, missingParent].map {
            $0.standardizedFileURL.resolvingSymlinksInPath()
        }
        var operations: [String] = []
        let store = OfflineStore(
            directoryURL: storeDirectory,
            syncEventLogFile: { url in
                operations.append(
                    "file:\(url.standardizedFileURL.resolvingSymlinksInPath().path)"
                )
            },
            syncEventLogDirectory: { url in
                operations.append(
                    "directory:\(url.standardizedFileURL.resolvingSymlinksInPath().path)"
                )
                if operations.count <= expectedCreationBarriers.count {
                    XCTAssertFalse(FileManager.default.fileExists(atPath: logURL.path))
                }
            }
        )
        let event = LiveRoundEvent(
            eventId: "nearest-existing-anchor",
            roundId: "round-1",
            clientId: "ios-phone",
            timestamp: "2026-07-23T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )

        try store.appendEvent(event)

        XCTAssertEqual(
            Array(operations.prefix(expectedCreationBarriers.count)),
            expectedCreationBarriers.map { "directory:\($0.path)" }
        )
        let eventFileIndex = try XCTUnwrap(
            operations.firstIndex(
                of: "file:\(logURL.standardizedFileURL.resolvingSymlinksInPath().path)"
            )
        )
        XCTAssertGreaterThanOrEqual(eventFileIndex, expectedCreationBarriers.count)
        XCTAssertEqual(try store.loadEvents(), [event])
    }

    func testDefaultStoreFixesTrustedAnchorToResolvedAppContainerHome() throws {
        let anchor = Mirror(reflecting: OfflineStore()).children.first {
            $0.label == "trustedDirectoryAnchor"
        }?.value as? URL
        XCTAssertEqual(
            try XCTUnwrap(anchor),
            URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true)
                .standardizedFileURL.resolvingSymlinksInPath()
        )
    }

    func testCustomAnchorRejectsWritableSiblingDotDotAndSymlinkEscapesBeforeMutation() throws {
        let suiteRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let trustedAnchor = suiteRoot.appendingPathComponent("trusted", isDirectory: true)
        let outsideRoot = suiteRoot.appendingPathComponent("trusted-escape", isDirectory: true)
        try FileManager.default.createDirectory(at: trustedAnchor, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: outsideRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: suiteRoot) }
        let outsideLink = trustedAnchor.appendingPathComponent("outside-link", isDirectory: true)
        try FileManager.default.createSymbolicLink(
            at: outsideLink,
            withDestinationURL: outsideRoot
        )
        let replayed = LiveRoundEvent(
            eventId: "must-not-escape-custom-anchor",
            roundId: "round-1",
            clientId: "apple-watch",
            timestamp: "2026-07-23T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )
        let operations: [(String, (OfflineStore) throws -> Void)] = [
            ("append", { try $0.appendEvent(replayed) }),
            ("replay", { _ = try $0.applyReplayEvents([replayed]) }),
        ]

        for escapeFamily in ["sibling", "dot-dot", "symlink"] {
            for (operationName, operation) in operations {
                let target: URL
                let resolvedTarget: URL
                switch escapeFamily {
                case "sibling":
                    target = outsideRoot.appendingPathComponent(
                        "sibling-\(operationName)",
                        isDirectory: true
                    )
                    resolvedTarget = target.standardizedFileURL.resolvingSymlinksInPath()
                case "dot-dot":
                    target = URL(
                        fileURLWithPath:
                            "\(trustedAnchor.path)/nested/../../trusted-escape/dot-dot-\(operationName)",
                        isDirectory: true
                    )
                    resolvedTarget = target.standardizedFileURL.resolvingSymlinksInPath()
                default:
                    target = outsideLink.appendingPathComponent(
                        "symlink-\(operationName)",
                        isDirectory: true
                    )
                    resolvedTarget = outsideLink.standardizedFileURL
                        .resolvingSymlinksInPath()
                        .appendingPathComponent(
                            "symlink-\(operationName)",
                            isDirectory: true
                        )
                }
                let anchorComponents = trustedAnchor.standardizedFileURL
                    .resolvingSymlinksInPath().pathComponents
                XCTAssertNotEqual(
                    Array(resolvedTarget.pathComponents.prefix(anchorComponents.count)),
                    anchorComponents,
                    "invalid test setup: \(escapeFamily)-\(operationName)"
                )
                var fileCallbacks: [URL] = []
                var directoryCallbacks: [URL] = []
                let store = makeCustomAnchoredOfflineStore(
                    directoryURL: target,
                    trustedDirectoryAnchor: trustedAnchor,
                    syncEventLogFile: { fileCallbacks.append($0) },
                    syncEventLogDirectory: { directoryCallbacks.append($0) }
                )
                let context = "\(escapeFamily)-\(operationName)"

                XCTAssertThrowsError(try operation(store), context) { error in
                    XCTAssertEqual(error as? OfflineStoreError, .eventLogCorrupt, context)
                }
                XCTAssertTrue(fileCallbacks.isEmpty, "\(context) reached a file callback")
                XCTAssertTrue(
                    directoryCallbacks.isEmpty,
                    "\(context) reached a directory callback"
                )
                XCTAssertFalse(
                    FileManager.default.fileExists(atPath: resolvedTarget.path),
                    "\(context) created the escaped store"
                )
                XCTAssertFalse(
                    FileManager.default.fileExists(
                        atPath: resolvedTarget.appendingPathComponent("events.jsonl").path
                    ),
                    "\(context) created an escaped event log"
                )
                try? FileManager.default.removeItem(at: resolvedTarget)
            }
        }
    }

    func testEventLogSymlinkEscapesFailClosedAtAllPublicBoundaries() throws {
        let suiteRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let trustedAnchor = suiteRoot.appendingPathComponent("trusted", isDirectory: true)
        let outsideRoot = suiteRoot.appendingPathComponent("outside", isDirectory: true)
        try FileManager.default.createDirectory(at: trustedAnchor, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: outsideRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: suiteRoot) }

        let existing = LiveRoundEvent(
            eventId: "outside-event",
            roundId: "round-1",
            clientId: "ios-phone",
            timestamp: "2026-07-23T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )
        let incoming = LiveRoundEvent(
            eventId: "must-not-follow-event-log-symlink",
            roundId: "round-1",
            clientId: "apple-watch",
            timestamp: "2026-07-23T00:00:01Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(5)]
        )
        let operations: [(
            name: String,
            hasTornTail: Bool,
            run: (OfflineStore, LiveRoundEvent) throws -> Void
        )] = [
            ("load", false, { store, _ in _ = try store.loadEvents() }),
            ("append", false, { store, event in try store.appendEvent(event) }),
            ("replay", false, { store, event in _ = try store.applyReplayEvents([event]) }),
            ("repair-append", true, { store, event in try store.appendEvent(event) }),
            ("repair-replay", true, {
                store, event in _ = try store.applyReplayEvents([event])
            }),
        ]

        for operation in operations {
            let storeDirectory = trustedAnchor.appendingPathComponent(
                operation.name,
                isDirectory: true
            )
            try FileManager.default.createDirectory(
                at: storeDirectory,
                withIntermediateDirectories: true
            )
            let outsideURL = outsideRoot.appendingPathComponent("\(operation.name).jsonl")
            var outsideBytes = try JSONEncoder().encode(existing)
            outsideBytes.append(0x0A)
            if operation.hasTornTail {
                outsideBytes.append(Data(#"{"eventId":"torn""#.utf8))
            }
            try outsideBytes.write(to: outsideURL, options: [.atomic])
            let originalOutsideBytes = try Data(contentsOf: outsideURL)
            let logURL = storeDirectory.appendingPathComponent("events.jsonl")
            try FileManager.default.createSymbolicLink(
                at: logURL,
                withDestinationURL: outsideURL
            )
            let originalLinkDestination = try FileManager.default
                .destinationOfSymbolicLink(atPath: logURL.path)
            var fileCallbacks: [URL] = []
            var directoryCallbacks: [URL] = []
            let store = makeCustomAnchoredOfflineStore(
                directoryURL: storeDirectory,
                trustedDirectoryAnchor: trustedAnchor,
                syncEventLogFile: { fileCallbacks.append($0) },
                syncEventLogDirectory: { directoryCallbacks.append($0) }
            )

            XCTAssertThrowsError(try operation.run(store, incoming), operation.name) { error in
                XCTAssertEqual(error as? OfflineStoreError, .eventLogCorrupt, operation.name)
            }
            XCTAssertEqual(
                try Data(contentsOf: outsideURL),
                originalOutsideBytes,
                operation.name
            )
            XCTAssertEqual(
                try FileManager.default.destinationOfSymbolicLink(atPath: logURL.path),
                originalLinkDestination,
                operation.name
            )
            XCTAssertTrue(fileCallbacks.isEmpty, "\(operation.name) reached file barrier")
            XCTAssertTrue(
                directoryCallbacks.isEmpty,
                "\(operation.name) reached directory barrier"
            )
        }
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
            Array(barriers.suffix(2)),
            ["file:events.jsonl", "directory:\(directory.lastPathComponent)"]
        )
        let physicallyRepaired = try Data(contentsOf: logURL)
        XCTAssertEqual(physicallyRepaired.last, 0x0A)
        let physicallyRepairedLines = physicallyRepaired.split(separator: 0x0A)
        XCTAssertEqual(physicallyRepairedLines.count, 1)
        XCTAssertEqual(
            try JSONDecoder().decode(
                LiveRoundEvent.self,
                from: Data(try XCTUnwrap(physicallyRepairedLines.first))
            ),
            existing
        )

        var uncertainRetryBarriers: [String] = []
        let uncertainRetry = OfflineStore(
            directoryURL: directory,
            syncEventLogFile: { url in
                XCTAssertFalse(
                    String(decoding: try Data(contentsOf: logURL), as: UTF8.self)
                        .contains(replayed.eventId)
                )
                uncertainRetryBarriers.append("file:\(url.lastPathComponent)")
            },
            syncEventLogDirectory: { url in
                XCTAssertFalse(
                    String(decoding: try Data(contentsOf: logURL), as: UTF8.self)
                        .contains(replayed.eventId)
                )
                uncertainRetryBarriers.append("directory:\(url.lastPathComponent)")
                if url == directory {
                    throw TestDurabilityFailure.directorySync
                }
            }
        )
        XCTAssertThrowsError(try uncertainRetry.applyReplayEvents([replayed])) { error in
            XCTAssertEqual(error as? TestDurabilityFailure, .directorySync)
        }
        XCTAssertEqual(
            Array(uncertainRetryBarriers.suffix(2)),
            ["file:events.jsonl", "directory:\(directory.lastPathComponent)"]
        )
        XCTAssertFalse(
            String(decoding: try Data(contentsOf: logURL), as: UTF8.self)
                .contains(replayed.eventId)
        )

        var successfulRetryBarriers: [String] = []
        var repairFileObserved = false
        var repairDirectoryObserved = false
        let successfulRetry = OfflineStore(
            directoryURL: directory,
            syncEventLogFile: { url in
                if url.lastPathComponent == "events.jsonl", !repairFileObserved {
                    XCTAssertFalse(
                        String(decoding: try Data(contentsOf: logURL), as: UTF8.self)
                            .contains(replayed.eventId)
                    )
                    repairFileObserved = true
                }
                successfulRetryBarriers.append("file:\(url.lastPathComponent)")
            },
            syncEventLogDirectory: { url in
                if repairFileObserved, !repairDirectoryObserved, url == directory {
                    XCTAssertFalse(
                        String(decoding: try Data(contentsOf: logURL), as: UTF8.self)
                            .contains(replayed.eventId)
                    )
                    repairDirectoryObserved = true
                }
                successfulRetryBarriers.append("directory:\(url.lastPathComponent)")
            }
        )
        XCTAssertTrue(try successfulRetry.applyReplayEvents([replayed]))
        XCTAssertTrue(repairFileObserved)
        XCTAssertTrue(repairDirectoryObserved)
        let repairFileIndex = try XCTUnwrap(
            successfulRetryBarriers.firstIndex(of: "file:events.jsonl")
        )
        let repairDirectoryIndex = try XCTUnwrap(
            successfulRetryBarriers[(repairFileIndex + 1)...].firstIndex(
                of: "directory:\(directory.lastPathComponent)"
            )
        )
        XCTAssertLessThan(repairFileIndex, repairDirectoryIndex)
        XCTAssertEqual(try successfulRetry.loadEvents(), [existing, replayed])
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
        let original = try Data(contentsOf: logURL)

        XCTAssertThrowsError(try store.applyReplayEvents([replayed])) { error in
            XCTAssertEqual(error as? OfflineStoreError, .eventLogCorrupt)
        }
        XCTAssertEqual(try Data(contentsOf: logURL), original)
        XCTAssertThrowsError(try store.loadEvents()) { error in
            XCTAssertEqual(error as? OfflineStoreError, .eventLogCorrupt)
        }
        XCTAssertEqual(try Data(contentsOf: logURL), original)
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

    func testRestoreLiveRoundStateLeavesClubUnselectedUntilAClubEventExists() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try fixturePackage()

        XCTAssertFalse(package.clubProfiles.isEmpty, "fixture must expose the old arbitrary first-club default")

        let snapshot = try store.restoreLiveRoundState(roundId: package.roundId, package: package)
        let holeState = try XCTUnwrap(snapshot.holeState(for: 1))

        XCTAssertEqual(holeState.selectedClub, "")
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
                payload: ["strokes": .number(5), "fairway": .string("left")]
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
        XCTAssertEqual(holeState.fairwayResult, "left")
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

    func testLiveProgressSurvivesStoreRecreation() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let package = try twoHoleFixturePackage()
        let store = OfflineStore(directoryURL: directory)
        var draft = LiveScoreDraft(
            hole: 1, par: 4, recordedShotCount: 2,
            currentScore: 4, currentPutts: 2, currentPenalty: 0
        )
        draft.startManualEntry()

        try store.saveActiveHole(roundId: package.roundId, hole: 2)
        try store.saveLiveScoreDraft(roundId: package.roundId, draft: draft)

        let reopened = OfflineStore(directoryURL: directory)
        XCTAssertEqual(try reopened.inProgressRoundId(), package.roundId)
        XCTAssertTrue(try reopened.hasRecordedEvents(roundId: package.roundId))
        XCTAssertEqual(
            try reopened.restoreLiveRoundState(roundId: package.roundId, package: package).activeHole,
            2
        )
        XCTAssertEqual(try reopened.loadLiveScoreDraft(roundId: package.roundId), draft)
    }

    func testEditingEarlierHoleDoesNotMoveLiveCursorBackward() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let package = try twoHoleFixturePackage()
        let store = OfflineStore(directoryURL: directory)
        try store.saveActiveHole(roundId: package.roundId, hole: 2)

        try store.appendEvent(
            LiveRoundEvent(
                eventId: "edit-hole-1",
                roundId: package.roundId,
                timestamp: "2026-07-29T00:00:00Z",
                hole: 1,
                kind: .score,
                payload: ["strokes": .number(5)]
            )
        )

        XCTAssertEqual(
            try store.restoreLiveRoundState(roundId: package.roundId, package: package).activeHole,
            2
        )
    }

    func testDiscardRoundClearsLiveProgress() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let package = try twoHoleFixturePackage()
        let store = OfflineStore(directoryURL: directory)
        let draft = LiveScoreDraft(
            hole: 1, par: 4, recordedShotCount: 1,
            currentScore: 4, currentPutts: 2, currentPenalty: 0
        )
        try store.saveRoundPackage(package)
        try store.saveActiveHole(roundId: package.roundId, hole: 2)
        try store.saveLiveScoreDraft(roundId: package.roundId, draft: draft)

        try store.discardRound(roundId: package.roundId)

        let reopened = OfflineStore(directoryURL: directory)
        XCTAssertNil(try reopened.loadLiveScoreDraft(roundId: package.roundId))
        XCTAssertEqual(
            try reopened.restoreLiveRoundState(roundId: package.roundId, package: package).activeHole,
            1
        )
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

    private func localFixturePackage() throws -> LiveRoundPackage {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let fixture = try String(contentsOf: url, encoding: .utf8)
            .replacingOccurrences(of: #""dataMode": "fixture""#, with: #""dataMode": "local""#)
        return try JSONDecoder().decode(LiveRoundPackage.self, from: Data(fixture.utf8))
    }

    private func replacingGeometryCoverage(
        in package: LiveRoundPackage,
        with geometryCoverage: GeometryCoverage,
        generatedAt: String
    ) -> LiveRoundPackage {
        LiveRoundPackage(
            schema: package.schema,
            roundId: package.roundId,
            dataMode: package.dataMode,
            sourceCoverage: package.sourceCoverage,
            missingData: package.missingData,
            playerProfile: package.playerProfile,
            course: package.course,
            holes: package.holes,
            nine: package.nine,
            coursePrep: package.coursePrep,
            geometryCoverage: geometryCoverage,
            readinessChecks: package.readinessChecks,
            caddieContextSeeds: package.caddieContextSeeds,
            weatherSnapshot: package.weatherSnapshot,
            clubProfiles: package.clubProfiles,
            caddieDecisionEndpoint: package.caddieDecisionEndpoint,
            offlinePackageStatus: package.offlinePackageStatus,
            eventCursor: package.eventCursor,
            recentHistory: package.recentHistory,
            cachedCaddieRules: package.cachedCaddieRules,
            generatedAt: generatedAt
        )
    }

    private func replacingCoursePrep(
        in package: LiveRoundPackage,
        geometryCoverage: String
    ) -> LiveRoundPackage {
        let preps = package.holes.map { hole in
            CoursePrepHole(
                hole: hole.number,
                par: hole.par,
                parSource: "test",
                blueYards: hole.yards ?? 0,
                routeLenM: 360,
                route: [[0, 0, 0], [0, 360, 360]],
                geometryCoverage: geometryCoverage,
                hazards: CoursePrepHazards(),
                map: CoursePrepMap(
                    image: "data:image/jpeg;base64,AQID",
                    overlay: CoursePrepOverlay(
                        w: 720,
                        h: 1120,
                        ppm: 1,
                        ln: 360,
                        route: [[360, 1000, 0], [360, 100, 360]]
                    )
                )
            )
        }
        return package.replacingCoursePrep(CoursePrepPackage(
            schema: "ai-caddie-course-prep-v1",
            globalId: package.course.globalId,
            holes: preps,
            missingData: nil
        ))
    }

    private func replacingHoles(
        in package: LiveRoundPackage,
        with holes: [Hole],
        generatedAt: String
    ) -> LiveRoundPackage {
        LiveRoundPackage(
            schema: package.schema,
            roundId: package.roundId,
            dataMode: package.dataMode,
            sourceCoverage: package.sourceCoverage,
            missingData: package.missingData,
            playerProfile: package.playerProfile,
            course: package.course,
            holes: holes,
            nine: package.nine,
            coursePrep: package.coursePrep,
            geometryCoverage: GeometryCoverage(
                state: package.geometryCoverage.state,
                readyHoles: min(package.geometryCoverage.readyHoles, holes.count),
                totalHoles: holes.count
            ),
            readinessChecks: package.readinessChecks,
            caddieContextSeeds: package.caddieContextSeeds,
            weatherSnapshot: package.weatherSnapshot,
            clubProfiles: package.clubProfiles,
            caddieDecisionEndpoint: package.caddieDecisionEndpoint,
            offlinePackageStatus: package.offlinePackageStatus,
            eventCursor: package.eventCursor,
            recentHistory: package.recentHistory,
            cachedCaddieRules: package.cachedCaddieRules,
            generatedAt: generatedAt
        )
    }

    private func twoHoleFixturePackage() throws -> LiveRoundPackage {
        let package = try fixturePackage()
        let first = try XCTUnwrap(package.holes.first)
        let second = Hole(
            number: 2,
            par: 3,
            yards: 165,
            geometryCoverage: .missing,
            sourceGlobalId: first.sourceGlobalId,
            sourceLocalHole: 2
        )
        return LiveRoundPackage(
            schema: package.schema,
            roundId: package.roundId,
            dataMode: package.dataMode,
            sourceCoverage: package.sourceCoverage,
            missingData: package.missingData,
            playerProfile: package.playerProfile,
            course: package.course,
            holes: [first, second],
            nine: package.nine,
            coursePrep: package.coursePrep,
            geometryCoverage: package.geometryCoverage,
            readinessChecks: package.readinessChecks,
            caddieContextSeeds: package.caddieContextSeeds,
            weatherSnapshot: package.weatherSnapshot,
            clubProfiles: package.clubProfiles,
            caddieDecisionEndpoint: package.caddieDecisionEndpoint,
            offlinePackageStatus: package.offlinePackageStatus,
            eventCursor: package.eventCursor,
            recentHistory: package.recentHistory,
            cachedCaddieRules: package.cachedCaddieRules,
            generatedAt: package.generatedAt
        )
    }

    private func directoryCreationParents(from anchor: URL, to target: URL) throws -> [URL] {
        let resolvedAnchor = anchor.standardizedFileURL.resolvingSymlinksInPath()
        let resolvedTarget = target.standardizedFileURL.resolvingSymlinksInPath()
        let anchorComponents = resolvedAnchor.pathComponents
        let targetComponents = resolvedTarget.pathComponents
        guard targetComponents.count >= anchorComponents.count,
              Array(targetComponents.prefix(anchorComponents.count)) == anchorComponents
        else {
            throw NSError(
                domain: "OfflineStoreTests.DirectoryContainment",
                code: 1,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "\(resolvedTarget.path) is outside trusted anchor \(resolvedAnchor.path)"
                ]
            )
        }

        var parents: [URL] = []
        var current = resolvedAnchor
        for component in targetComponents.dropFirst(anchorComponents.count) {
            parents.append(current)
            current.appendPathComponent(component, isDirectory: true)
        }
        return parents
    }
}
