#if !SWIFT_PACKAGE
import Combine
import Foundation
import XCTest
@testable import AICaddie

@MainActor
final class C33StartTests: XCTestCase {
    override func setUp() {
        super.setUp()
        URLProtocol.registerClass(C33URLProtocol.self)
    }
    override func tearDown() {
        URLProtocol.unregisterClass(C33URLProtocol.self)
        super.tearDown()
    }

    func testStartCancelsPreviousCourseAndSendsWithinOneSecond() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c33.example.test")!, session: session)
        let model = c33Model(store, client)
        let oldStarted = expectation(description: "old home package held")
        let oldCancelled = expectation(description: "old package cancelled")
        let startSent = expectation(description: "32850 start sent")
        let entered = expectation(description: "first hole entered")
        let package = try c33Package()
        let data = try JSONEncoder().encode(package)
        C33URLProtocol.onStart = { proto in
            if proto.request.url!.path.contains("/31796/package") { oldStarted.fulfill(); return }
            if proto.request.url!.path.contains("/32850/package") {
                startSent.fulfill(); proto.reply(200, data); return
            }
            proto.reply(404)
        }
        C33URLProtocol.onStop = { request in
            if request.url!.path.contains("/31796/package") { oldCancelled.fulfill() }
        }
        let old = Task { try? await client.fetchCoursePackage(
            globalId: 31796, roundId: "home-31796", teeBox: "blue",
            loops: [.init(globalId: 31796, half: "all")]
        ) }
        defer {
            old.cancel(); client.invalidateForTesting(); session.invalidateAndCancel()
            C33URLProtocol.onStart = nil; C33URLProtocol.onStop = nil
            try? FileManager.default.removeItem(at: directory)
        }
        await fulfillment(of: [oldStarted], timeout: 1)
        let subscription = model.$pendingLiveHole.compactMap { $0 }.first().sink { _ in entered.fulfill() }
        defer { subscription.cancel() }
        let start = Task { await model.prepareCourseRound(
            roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")]
        ) }
        defer { start.cancel() }
        // C33: old request is held indefinitely; Start must leave the phone within 1 s.
        await fulfillment(of: [startSent, oldCancelled, entered], timeout: 1)
        XCTAssertEqual(model.pendingLiveHole, 1)
    }

    func testDefaultStartBudgetIsThirtySecondsWithoutAutomaticRetry() async throws {
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c33-budget.example.test")!, session: session)
        var requests = 0
        let requestsLock = NSLock()
        C33URLProtocol.onStart = { proto in
            requestsLock.lock(); requests += 1; requestsLock.unlock()
            // The card gives one total 30 s budget; a 503 is an explicit failure for retry.
            XCTAssertEqual(proto.request.timeoutInterval, 30)
            proto.reply(503)
        }
        defer { client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.onStart = nil }
        do {
            _ = try await client.fetchCoursePackage(
                globalId: 32850, roundId: "c33-budget", teeBox: "blue",
                loops: [.init(globalId: 32850, half: "all")], foregroundStart: true
            )
            XCTFail("503 must fail the start")
        } catch SyncClientError.http(status: 503, body: _) { }
        XCTAssertEqual(requests, 1)
    }

    func testUserDownloadAndWatchStartSurviveForegroundStartCancellation() async throws {
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c33-kinds.example.test")!, session: session)
        let owner = UUID(); client.beginRoundStart(owner)
        let sent = expectation(description: "non-background requests sent")
        let requestLock = NSLock()
        var count = 0
        C33URLProtocol.onStart = { proto in
            let isExpectedPackage = proto.request.url?.path == "/api/v2/mobile/courses/32850/package"
            let roundID = URLComponents(url: proto.request.url!, resolvingAgainstBaseURL: false)?
                .queryItems?.first(where: { $0.name == "round_id" })?.value
            guard isExpectedPackage, (roundID == "download" || roundID == "watch") else {
                proto.reply(404)
                return
            }
            requestLock.lock()
            count += 1
            let firstRequest = count == 1
            requestLock.unlock()
            if firstRequest { sent.fulfill() }
            proto.reply(503)
        }
        defer { client.endRoundStart(owner); client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.onStart = nil }
        async let download = client.fetchCoursePackage(
            globalId: 32850, roundId: "download", teeBox: "blue",
            loops: [.init(globalId: 32850, half: "all")], requestKind: .userDownload
        )
        async let watch = client.fetchCoursePackage(
            globalId: 32850, roundId: "watch", teeBox: "blue",
            loops: [.init(globalId: 32850, half: "all")], requestKind: .watchStart
        )
        _ = try? await download
        _ = try? await watch
        await fulfillment(of: [sent], timeout: 1)
        XCTAssertGreaterThanOrEqual(count, 2)
    }

    func testUnresponsiveStartHasThirtySecondBudgetAndRetryableFailure() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let session = C33URLProtocol.session()
        let sent = expectation(description: "start request")
        let stopped = expectation(description: "timed out request cancelled")
        let failed = expectation(description: "spinner ended with failure")
        let client = SyncClient(
            baseURL: URL(string: "https://c33-timeout.example.test")!, session: session,
            roundStartTimeoutInterval: 0.05
        )
        let model = c33Model(OfflineStore(directoryURL: directory), client)
        C33URLProtocol.onStart = { proto in
            if proto.request.url!.path.contains("/32850/package") {
                // C33 specifies a 30 s total default, never 120 s per attempt.
                XCTAssertLessThanOrEqual(proto.request.timeoutInterval, 30)
                sent.fulfill() // Intentionally never reply.
            } else { proto.reply(404) }
        }
        C33URLProtocol.onStop = { _ in stopped.fulfill() }
        let subscription = model.$isPreparingRound.dropFirst().filter { !$0 }.first().sink { _ in failed.fulfill() }
        defer {
            subscription.cancel(); client.invalidateForTesting(); session.invalidateAndCancel()
            C33URLProtocol.onStart = nil; C33URLProtocol.onStop = nil
            try? FileManager.default.removeItem(at: directory)
        }
        let start = Task { await model.prepareCourseRound(
            roundId: "c33-timeout", teeBox: "blue", loops: [.init(globalId: 32850, half: "all")]
        ) }
        defer { start.cancel() }
        await fulfillment(of: [sent, stopped, failed], timeout: 1)
        XCTAssertFalse(model.isPreparingRound)
        XCTAssertNil(model.pendingLiveHole)
        XCTAssertNotNil(model.roundStartFailure)
        // A failed attempt releases preparation ownership, so the same round can be retried.
        let retryFailed = expectation(description: "retry finished")
        let retrySubscription = model.$isPreparingRound.dropFirst().filter { !$0 }.first().sink { _ in retryFailed.fulfill() }
        C33URLProtocol.onStart = { $0.reply(503) }
        C33URLProtocol.onStop = nil
        let retry = Task { await model.prepareCourseRound(
            roundId: "c33-timeout", teeBox: "blue", loops: [.init(globalId: 32850, half: "all")]
        ) }
        defer { retry.cancel(); retrySubscription.cancel() }
        await fulfillment(of: [retryFailed], timeout: 1)
        XCTAssertNotNil(model.roundStartFailure)
    }
}
#endif
