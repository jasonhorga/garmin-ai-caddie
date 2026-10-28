#if !SWIFT_PACKAGE
import Combine
import Foundation
import XCTest
@testable import AICaddie

// Every test owns a distinct host. C33URLProtocol is process-wide, so requests that earlier tests'
// models are still draining are answered 404 here and never drive this test's expectations.
//
// The CI simulator stalls at random for 1.5–14 s. Waits here are therefore generous and never the
// assertion: a held request is never answered, so a regression shows up as an event that does not
// happen within the wait, never as one that is only a little late.
@MainActor
final class C33StartTests: XCTestCase {
    /// Far below every default the product could fall back to (the 30 s start budget, the 120 s
    /// package timeout) and far above a simulator stall.
    private let eventWait: TimeInterval = 10

    override func setUp() {
        super.setUp()
        URLProtocol.registerClass(C33URLProtocol.self)
    }
    override func tearDown() {
        C33URLProtocol.setHandlers(onStart: nil)
        URLProtocol.unregisterClass(C33URLProtocol.self)
        super.tearDown()
    }

    func testStartCancelsPreviousCourseAndSendsWithoutWaitingForIt() async throws {
        let host = "c33.example.test"
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://\(host)")!, session: session)
        let model = c33Model(store, client)
        let oldStarted = expectation(description: "old home package held")
        let oldCancelled = expectation(description: "old package cancelled")
        let startSent = expectation(description: "32850 start sent")
        let entered = expectation(description: "first hole entered")
        let oldStartedOnce = C33FirstMatch(), oldCancelledOnce = C33FirstMatch(), startSentOnce = C33FirstMatch()
        let package = try c33Package()
        let data = try JSONEncoder().encode(package)
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            if proto.request.url!.path.contains("/31796/package") {
                if oldStartedOnce.claim() { oldStarted.fulfill() }
                return
            }
            if proto.request.url!.path.contains("/32850/package") {
                if startSentOnce.claim() { startSent.fulfill() }
                proto.reply(200, data); return
            }
            proto.reply(404)
        }, onStop: { request in
            guard request.url?.host == host, request.url!.path.contains("/31796/package") else { return }
            if oldCancelledOnce.claim() { oldCancelled.fulfill() }
        })
        let old = Task { try? await client.fetchCoursePackage(
            globalId: 31796, roundId: "home-31796", teeBox: "blue",
            loops: [.init(globalId: 31796, half: "all")]
        ) }
        defer {
            old.cancel(); client.invalidateForTesting(); session.invalidateAndCancel()
            C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await fulfillment(of: [oldStarted], timeout: eventWait)
        let subscription = model.$pendingLiveHole.compactMap { $0 }.first().sink { _ in entered.fulfill() }
        defer { subscription.cancel() }
        let start = Task { await model.prepareCourseRound(
            roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")]
        ) }
        defer { start.cancel() }
        // C33 "Start does not wait for the previous course", proved by order rather than by the clock:
        // the old request is never answered and would only end on its own 120 s timeout, so Start can
        // be sent and enter hole 1 within the wait only if it cancels the old request and does not
        // queue behind it.
        await fulfillment(of: [startSent, oldCancelled, entered], timeout: eventWait)
        XCTAssertEqual(model.pendingLiveHole, 1)
    }

    func testNewRoundStartCancelsAPreviousForegroundStart() async throws {
        let host = "c33-restart.example.test"
        let session = C33URLProtocol.session()
        // The default 30 s start budget is far longer than this test; only the next Start can
        // release the first request.
        let client = SyncClient(baseURL: URL(string: "https://\(host)")!, session: session)
        let sent = expectation(description: "first start held")
        let stopped = expectation(description: "first start cancelled by the next start")
        let sentOnce = C33FirstMatch(), stoppedOnce = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host, c33Query(proto.request, "round_id") == "first-start" else {
                proto.reply(404); return
            }
            if sentOnce.claim() { sent.fulfill() } // Intentionally never reply.
        }, onStop: { request in
            guard request.url?.host == host, c33Query(request, "round_id") == "first-start" else { return }
            if stoppedOnce.claim() { stopped.fulfill() }
        })
        let owner = UUID()
        defer {
            client.endRoundStart(owner); client.invalidateForTesting(); session.invalidateAndCancel()
            C33URLProtocol.setHandlers(onStart: nil)
        }
        let first = Task { try? await client.fetchCoursePackage(
            globalId: 32850, roundId: "first-start", teeBox: "blue",
            loops: [.init(globalId: 32850, half: "all")], foregroundStart: true
        ) }
        defer { first.cancel() }
        await fulfillment(of: [sent], timeout: eventWait)
        client.beginRoundStart(owner)
        // Left alone, the held request would only stop on the 30 s budget, three times this wait.
        await fulfillment(of: [stopped], timeout: eventWait)
    }

    func testDefaultStartBudgetIsThirtySecondsWithoutAutomaticRetry() async throws {
        let host = "c33-budget.example.test"
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://\(host)")!, session: session)
        var requests = 0
        let requestsLock = NSLock()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            requestsLock.lock(); requests += 1; requestsLock.unlock()
            // The card gives one total 30 s budget; a 503 is an explicit failure for retry.
            XCTAssertEqual(proto.request.timeoutInterval, 30)
            proto.reply(503)
        })
        defer { client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil) }
        do {
            _ = try await client.fetchCoursePackage(
                globalId: 32850, roundId: "c33-budget", teeBox: "blue",
                loops: [.init(globalId: 32850, half: "all")], foregroundStart: true
            )
            XCTFail("503 must fail the start")
        } catch SyncClientError.http(status: 503, body: _) { }
        requestsLock.lock(); let sentRequests = requests; requestsLock.unlock()
        XCTAssertEqual(sentRequests, 1)
    }

    func testForegroundRoundPackageFailsWithinTheStartBudget() async throws {
        let host = "c33-round-budget.example.test"
        let session = C33URLProtocol.session()
        let client = SyncClient(
            baseURL: URL(string: "https://\(host)")!, session: session,
            roundStartTimeoutInterval: 0.2
        )
        let sent = expectation(description: "round package request held")
        let sentOnce = C33FirstMatch()
        let timeoutLock = NSLock()
        var requestTimeout: TimeInterval?
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  proto.request.url!.path.hasSuffix("/rounds/c33-resume/package") else {
                proto.reply(404); return
            }
            timeoutLock.lock(); requestTimeout = proto.request.timeoutInterval; timeoutLock.unlock()
            if sentOnce.claim() { sent.fulfill() } // Intentionally never reply.
        })
        defer { client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil) }
        let failed = expectation(description: "resumed start failed within its budget")
        let resume = Task {
            do {
                _ = try await client.fetchRoundPackage(roundId: "c33-resume", foregroundStart: true)
                XCTFail("an unresponsive start must fail")
            } catch { }
            failed.fulfill()
        }
        defer { resume.cancel() }
        // Resuming a round by id is a foreground start too: the same short total budget applies. The
        // request is never answered, so only the injected 0.2 s budget can end it within the wait;
        // a 30 s deadline or a longer request timeout cannot.
        await fulfillment(of: [sent, failed], timeout: eventWait)
        timeoutLock.lock(); let timeout = requestTimeout; timeoutLock.unlock()
        XCTAssertLessThanOrEqual(try XCTUnwrap(timeout), 30)
    }

    func testUserDownloadAndWatchStartSurviveForegroundStartCancellation() async throws {
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c33-kinds.example.test")!, session: session)
        let owner = UUID(); client.beginRoundStart(owner)
        let sent = expectation(description: "non-background requests sent")
        let requestLock = NSLock()
        var count = 0
        C33URLProtocol.setHandlers(onStart: { proto in
            let isExpectedPackage = proto.request.url?.host == "c33-kinds.example.test"
                && proto.request.url?.path == "/api/v2/mobile/courses/32850/package"
            let roundID = c33Query(proto.request, "round_id")
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
        })
        defer { client.endRoundStart(owner); client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil) }
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
        await fulfillment(of: [sent], timeout: eventWait)
        requestLock.lock(); let sentRequests = count; requestLock.unlock()
        XCTAssertGreaterThanOrEqual(sentRequests, 2)
    }

    func testUnresponsiveStartHasThirtySecondBudgetAndRetryableFailure() async throws {
        let host = "c33-timeout.example.test"
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let session = C33URLProtocol.session()
        let sent = expectation(description: "start request")
        let stopped = expectation(description: "timed out request cancelled")
        let failed = expectation(description: "spinner ended with failure")
        let client = SyncClient(
            baseURL: URL(string: "https://\(host)")!, session: session,
            roundStartTimeoutInterval: 0.05
        )
        let model = c33Model(OfflineStore(directoryURL: directory), client)
        // Only the held start request drives `stopped`. Requests that complete normally (this
        // model's other 404s, or strays from earlier tests) also call stopLoading.
        let heldLock = NSLock()
        var heldURL: URL?
        let stoppedOnce = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  proto.request.url!.path.contains("/32850/package") else { proto.reply(404); return }
            // C33 specifies a 30 s total default, never 120 s per attempt.
            XCTAssertLessThanOrEqual(proto.request.timeoutInterval, 30)
            heldLock.lock()
            let first = heldURL == nil
            if first { heldURL = proto.request.url }
            heldLock.unlock()
            if first { sent.fulfill() } // Intentionally never reply.
        }, onStop: { request in
            heldLock.lock(); let held = heldURL; heldLock.unlock()
            guard let held, request.url == held else { return }
            if stoppedOnce.claim() { stopped.fulfill() }
        })
        let subscription = model.$isPreparingRound.dropFirst().filter { !$0 }.first().sink { _ in failed.fulfill() }
        defer {
            subscription.cancel(); client.invalidateForTesting(); session.invalidateAndCancel()
            C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        let start = Task { await model.prepareCourseRound(
            roundId: "c33-timeout", teeBox: "blue", loops: [.init(globalId: 32850, half: "all")]
        ) }
        defer { start.cancel() }
        // The 30 s budget itself is the `timeoutInterval` asserted on the request above. Here the
        // injected 0.05 s budget must end the never-answered request: without a total budget it would
        // hang for the 120 s package timeout, and a hard-coded 30 s would also miss this wait.
        await fulfillment(of: [sent, stopped, failed], timeout: eventWait)
        XCTAssertFalse(model.isPreparingRound)
        XCTAssertNil(model.pendingLiveHole)
        XCTAssertNotNil(model.roundStartFailure)
        // A failed attempt releases preparation ownership, so the same round can be retried.
        let retryFailed = expectation(description: "retry finished")
        let retrySubscription = model.$isPreparingRound.dropFirst().filter { !$0 }.first().sink { _ in retryFailed.fulfill() }
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            proto.reply(503)
        })
        let retry = Task { await model.prepareCourseRound(
            roundId: "c33-timeout", teeBox: "blue", loops: [.init(globalId: 32850, half: "all")]
        ) }
        defer { retry.cancel(); retrySubscription.cancel() }
        await fulfillment(of: [retryFailed], timeout: eventWait)
        XCTAssertNotNil(model.roundStartFailure)
    }

    func testRetryReusesTheSameCourseStartParameters() async throws {
        let host = "c114-retry.example.test"
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let package = try c33Package()
        let packageData = try JSONEncoder().encode(package)
        let session = C33URLProtocol.session()
        let client = SyncClient(
            baseURL: URL(string: "https://\(host)")!, session: session,
            roundStartTimeoutInterval: 0.05
        )
        let model = c33Model(OfflineStore(directoryURL: directory), client)
        let firstSent = expectation(description: "first package start")
        let lock = NSLock()
        var requests: [URLRequest] = []
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  proto.request.url?.path == "/api/v2/mobile/courses/\(package.course.globalId)/package" else {
                proto.reply(404); return
            }
            lock.lock(); requests.append(proto.request); let count = requests.count; lock.unlock()
            if count == 1 {
                firstSent.fulfill()
            } else {
                proto.reply(200, packageData)
            }
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel()
            C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        let loops = [RoundLoopEntry(globalId: package.course.globalId, half: "all")]
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: loops)
        await fulfillment(of: [firstSent], timeout: 5)
        XCTAssertEqual(model.roundStartFailure, .timedOut)

        await model.retryRoundStart()
        lock.lock(); let observed = requests; lock.unlock()
        XCTAssertEqual(observed.count, 2)
        for name in ["round_id", "tee_box", "loops", "captured_at"] {
            XCTAssertEqual(c33Query(observed[0], name), c33Query(observed[1], name), name)
        }
        XCTAssertNil(model.roundStartFailure)
    }
}
#endif
