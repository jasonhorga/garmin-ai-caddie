// size: medium
// goals: I-19
//
// I-19: uploaded events, the event log and watch summaries never carry the session token, the
// Apple identity token or the Garmin session cookie. Entry points: OfflineStore (the durable
// event log every record lands in), SyncClient.postEventBatch (the upload) and
// WatchEventBridge.makeWatchRoundStatePayload (the watch summary). Only HTTP is faked.

import Foundation
import XCTest
@testable import AICaddie

private let privacyGoalSessionToken = "sess-goal-token-4411"
private let privacyGoalAppleIdentity = "eyJ-apple-goal-identity"
private let privacyGoalGarminSession = "SESSIONID-goal-garmin-777"
private let privacyGoalCsrf = "csrf-goal-value-9"
private let privacyGoalSecrets = [
    privacyGoalSessionToken,
    privacyGoalAppleIdentity,
    privacyGoalGarminSession,
    privacyGoalCsrf,
]

/// Captures the single events upload the test performs.
private final class PrivacyGoalUploadCapture: @unchecked Sendable {
    private let lock = NSLock()
    private var bodies: [Data] = []
    private var authorizations: [String?] = []

    func record(body: Data, authorization: String?) {
        lock.lock()
        bodies.append(body)
        authorizations.append(authorization)
        lock.unlock()
    }

    var snapshot: (bodies: [Data], authorizations: [String?]) {
        lock.lock()
        defer { lock.unlock() }
        return (bodies, authorizations)
    }
}

final class PrivacyGoalTests: XCTestCase {
    private var directories: [URL] = []

    override func tearDown() {
        for directory in directories {
            try? FileManager.default.removeItem(at: directory)
        }
        directories = []
        super.tearDown()
    }

    private func makeStore() throws -> (OfflineStore, LiveRoundPackage, URL) {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("privacy-goal-\(UUID().uuidString)", isDirectory: true)
        directories.append(directory)
        let store = OfflineStore(directoryURL: directory)
        let package = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        try store.saveRoundPackage(package)
        return (store, package, directory)
    }

    /// Notes a player (or a pasted diagnostic) could put in an event: one per secret class,
    /// both at the top level and nested inside objects and arrays, plus an ordinary note.
    private func secretBearingEvents(roundId: String) -> [LiveRoundEvent] {
        let timestamp = "2026-07-29T05:00:00Z"
        return [
            LiveRoundEvent(
                eventId: "privacy-session", roundId: roundId, timestamp: timestamp,
                hole: 1, kind: .note,
                payload: ["text": .string("Authorization: Bearer \(privacyGoalSessionToken)")]
            ),
            LiveRoundEvent(
                eventId: "privacy-apple", roundId: roundId, timestamp: timestamp,
                hole: 1, kind: .note,
                payload: ["text": .string("apple identityToken: \(privacyGoalAppleIdentity)")]
            ),
            LiveRoundEvent(
                eventId: "privacy-nested", roundId: roundId, timestamp: timestamp,
                hole: 2, kind: .note,
                payload: [
                    "meta": .object([
                        "garmin": .string("garmin cookie=\(privacyGoalGarminSession)"),
                        "header": .string("connect-csrf-token: \(privacyGoalCsrf)"),
                    ]),
                    "trail": .array([
                        .string("bearer \(privacyGoalSessionToken)"),
                        .object(["sso": .string("access_token=\(privacyGoalAppleIdentity)")]),
                    ]),
                ]
            ),
            LiveRoundEvent(
                eventId: "privacy-plain", roundId: roundId, timestamp: timestamp,
                hole: 2, kind: .score,
                payload: ["strokes": .number(4), "fairway": .string("hit")]
            ),
        ]
    }

    private func assertNoSecrets(_ text: String, _ context: String, file: StaticString = #filePath, line: UInt = #line) {
        for secret in privacyGoalSecrets {
            XCTAssertFalse(text.contains(secret), "\(context) leaks \(secret)", file: file, line: line)
        }
    }

    // goals: I-19 [main]
    func testUploadedEventsCarryNoSessionAppleOrGarminSecrets() async throws {
        let (store, package, _) = try makeStore()
        try secretBearingEvents(roundId: package.roundId).forEach(store.appendEvent)
        let pending = try store.loadPendingEvents(roundId: package.roundId)
        XCTAssertEqual(pending.map(\.eventId), ["privacy-session", "privacy-apple", "privacy-nested", "privacy-plain"])

        let capture = PrivacyGoalUploadCapture()
        let scope = CapturingURLProtocolScope(handler: { request in
            let url = try XCTUnwrap(request.url)
            capture.record(
                body: try CapturingURLProtocol.requestBodyData(from: request),
                authorization: request.value(forHTTPHeaderField: "Authorization")
            )
            let reply = #"{"accepted":4,"duplicate":false,"acceptedEventIds":["privacy-session","privacy-apple","privacy-nested","privacy-plain"],"duplicateEventIds":[],"serverSequence":4}"#
            let response = try XCTUnwrap(HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil))
            return (response, Data(reply.utf8))
        })
        let session = URLSession(configuration: scope.configuration())
        defer {
            session.invalidateAndCancel()
            withExtendedLifetime(scope) {}
        }
        await MainActor.run {
            SessionStore.shared.save(AppSession(token: privacyGoalSessionToken, playerId: "p_privacy_goal"))
        }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session,
            retrySleep: { _ in }
        )

        let result: SyncResult
        do {
            result = try await client.postEventBatch(pending, roundId: package.roundId, idempotencyKey: "privacy-goal-key")
        } catch {
            await MainActor.run { SessionStore.shared.signOut() }
            throw error
        }
        await MainActor.run { SessionStore.shared.signOut() }

        XCTAssertEqual(result.accepted, 4)
        let captured = capture.snapshot
        XCTAssertEqual(captured.bodies.count, 1)
        // The session token authenticates the request header only; it is never event content.
        XCTAssertEqual(captured.authorizations.first ?? nil, "Bearer \(privacyGoalSessionToken)")
        let body = try XCTUnwrap(captured.bodies.first)
        assertNoSecrets(String(decoding: body, as: UTF8.self), "uploaded event batch")
        let batch = try JSONDecoder().decode(EventBatch.self, from: body)
        XCTAssertEqual(batch.events.map(\.eventId), pending.map(\.eventId), "redaction keeps every event")
        let plain = try XCTUnwrap(batch.events.first { $0.eventId == "privacy-plain" })
        XCTAssertEqual(plain.payload["strokes"], .number(4))
        XCTAssertEqual(plain.payload["fairway"], .string("hit"), "ordinary content is not redacted")
    }

    // goals: I-19
    func testLocalEventLogNeverStoresSecretsAndKeepsOrdinaryContent() throws {
        let (store, package, directory) = try makeStore()
        try secretBearingEvents(roundId: package.roundId).forEach(store.appendEvent)

        let log = directory.appendingPathComponent("events.jsonl")
        let raw = try String(contentsOf: log, encoding: .utf8)
        assertNoSecrets(raw, "events.jsonl on disk")

        let reloaded = try OfflineStore(directoryURL: directory).loadEvents()
        let reloadedText = String(decoding: try JSONEncoder().encode(reloaded), as: UTF8.self)
        assertNoSecrets(reloadedText, "reloaded event log")
        XCTAssertEqual(
            reloaded.filter { $0.kind != .syncMarker }.map(\.eventId),
            ["privacy-session", "privacy-apple", "privacy-nested", "privacy-plain"]
        )
        let session = try XCTUnwrap(reloaded.first { $0.eventId == "privacy-session" })
        guard case .string(let note)? = session.payload["text"] else {
            return XCTFail("the note survives as text")
        }
        XCTAssertTrue(note.contains("[REDACTED]"), "the secret is replaced, not silently dropped: \(note)")
    }

    // goals: I-19
    func testWatchSummaryRedactsSessionAppleAndGarminSecrets() throws {
        let bridge = WatchEventBridge()
        let package = try LiveRoundPackageFixture.package()
        let hole = try XCTUnwrap(package.holes.first)
        let cases: [(source: String, ref: String)] = [
            ("garmin cookie=\(privacyGoalGarminSession)", "identityToken=\(privacyGoalAppleIdentity)"),
            ("Authorization: Bearer \(privacyGoalSessionToken)", "csrf \(privacyGoalCsrf)"),
            ("bearer \(privacyGoalSessionToken)", "token=\(privacyGoalSessionToken)"),
        ]
        for (source, ref) in cases {
            let option = OfflineCaddieOption(
                optionId: "stock",
                label: "Center green",
                clubName: "8I",
                carryM: 142,
                riskScore: 1,
                source: source,
                sourceRefs: [ref]
            )
            let payload = bridge.makeWatchRoundStatePayload(
                package: package,
                hole: hole,
                score: 4,
                putts: 2,
                penaltyCount: 0,
                selectedClub: "8I",
                decision: nil,
                offlineOption: option
            )
            XCTAssertEqual(payload.evidenceSummary, "[redacted] / [redacted]", "source \(source)")
            let encoded = String(decoding: try JSONEncoder().encode(payload), as: UTF8.self)
            assertNoSecrets(encoded, "watch round-state payload")
        }

        // Ordinary provenance is still shown on the watch.
        let clean = OfflineCaddieOption(
            optionId: "stock",
            label: "Center green",
            clubName: "8I",
            carryM: 142,
            riskScore: 1,
            source: "offline_seed",
            sourceRefs: ["club_stats"]
        )
        let cleanPayload = bridge.makeWatchRoundStatePayload(
            package: package,
            hole: hole,
            score: 4,
            putts: 2,
            penaltyCount: 0,
            selectedClub: "8I",
            decision: nil,
            offlineOption: clean
        )
        XCTAssertEqual(cleanPayload.evidenceSummary, "offline_seed / club_stats")
    }
}
