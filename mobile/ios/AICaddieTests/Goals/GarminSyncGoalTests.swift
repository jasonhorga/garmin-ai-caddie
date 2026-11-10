// size: medium
// goals: I-16
import Combine
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import AICaddie

/// I-16: a Garmin pull can be started by hand (设置页「同步」) or automatically (launch/foreground),
/// and the status the app shows is the truth: 进行中 while the server job runs, 需重新认证 when the
/// Garmin login expired, 失败 (retryable, never "connected") when the pull failed.
/// The server is faked at the URLProtocol edge and the Garmin login lives in a throwaway keychain
/// item; the real LiveRoundAppModel entry points and the real SyncClient job monitor run.
@MainActor
final class GarminSyncGoalTests: XCTestCase {
    private var scopes: [CapturingURLProtocolScope] = []
    private var store: GarminSessionStore?
    private var cancellables = Set<AnyCancellable>()

    override func setUp() {
        super.setUp()
        SessionStore.shared.signOut()
        let base = FileManager.default.temporaryDirectory
            .appendingPathComponent("garmin-goal-\(UUID().uuidString)", isDirectory: true)
        RoundReviewDiskCache.rootOverride = base.appendingPathComponent("support", isDirectory: true)
        RoundReviewDiskCache.legacyRootOverride = base.appendingPathComponent("caches", isDirectory: true)
    }

    override func tearDown() {
        try? store?.deleteSession()
        store = nil
        cancellables.removeAll()
        scopes.removeAll()
        RoundReviewDiskCache.rootOverride = nil
        RoundReviewDiskCache.legacyRootOverride = nil
        super.tearDown()
    }

    // goals: I-16 [main]
    func testManualSyncShowsSyncingWhileTheJobRunsThenTheUpdatedResult() async throws {
        let store = try makeStore(verified: true)
        let server = GarminFakeServer()
        server.post = { garminRun(state: "queued", jobId: "job-manual") }
        server.jobStates = ["running", "ready"]
        server.status = { _ in garminStatus(state: "ready", newRoundCount: 2) }
        let model = makeModel(server: server, store: store)
        let log = watchStates(of: model, into: server)

        let outcome = await model.syncGarminDataOutcome()

        XCTAssertEqual(outcome, .completed)
        XCTAssertEqual(server.postURLs.count, 1)
        let post = try XCTUnwrap(server.postURLs.first)
        XCTAssertEqual(post.path, "/api/v2/sync/garmin")
        XCTAssertEqual(post.query, "with_shots=true")
        XCTAssertEqual(server.jobPolls, 2, "the queued job is followed until it is terminal")
        XCTAssertEqual(
            server.statesSeenDuringPolls, [.syncing, .syncing],
            "while the server job runs the page says 进行中, never the previous result"
        )
        XCTAssertEqual(GarminConnectionState.syncing.statusText, "Garmin 已连接，正在同步")
        XCTAssertEqual(log.states.last, .connectedUpdated)
        XCTAssertFalse(log.states.contains(.syncFailed))
        XCTAssertEqual(model.garminConnectionState, .connectedUpdated)
        XCTAssertEqual(model.garminSyncStatus, "Garmin 数据已更新")
        XCTAssertFalse(model.isGarminSyncing)
        XCTAssertNotNil(model.lastGarminSyncAt)
        XCTAssertEqual(server.statusReads, 1)
    }

    // goals: I-16
    func testExpiredGarminLoginSaysReconnectAndForgetsTheSavedLogin() async throws {
        let store = try makeStore(verified: true)
        let server = GarminFakeServer()
        server.post = { garminRun(state: "queued", jobId: "job-expired") }
        server.jobStates = ["reauth_required"]
        let model = makeModel(server: server, store: store)

        let succeeded = await model.syncGarminData()

        XCTAssertFalse(succeeded)
        XCTAssertEqual(model.garminConnectionState, .reauthRequired)
        XCTAssertEqual(model.garminSyncStatus, "Garmin 登录已过期，请重新连接")
        XCTAssertFalse(model.garminConnectionState.isVerified)
        XCTAssertNil(try store.loadSession(), "an expired Garmin login must not keep claiming 已连接")
        XCTAssertNil(model.lastGarminSyncAt)
        XCTAssertFalse(model.isGarminSyncing)
    }

    // goals: I-16
    func testPostThatSaysReauthRequiredIsNotReportedAsAGenericFailure() async throws {
        let store = try makeStore(verified: true)
        let server = GarminFakeServer()
        server.post = { garminRun(state: "error", jobId: "job-direct", reauthRequired: true) }
        let model = makeModel(server: server, store: store)

        let outcome = await model.syncGarminDataOutcome()

        XCTAssertEqual(outcome, .reauthRequired)
        XCTAssertEqual(model.garminConnectionState, .reauthRequired)
        XCTAssertNotEqual(model.garminConnectionState, .syncFailed)
        XCTAssertNil(try store.loadSession())
    }

    // goals: I-16
    func testFailedPullIsReportedAsRetryableFailureNotConnected() async throws {
        let store = try makeStore(verified: true)
        let server = GarminFakeServer()
        server.postStatus = 500
        let model = makeModel(server: server, store: store)

        let transportFailure = await model.syncGarminDataOutcome()

        XCTAssertEqual(transportFailure, .failed)
        XCTAssertEqual(model.garminConnectionState, .syncFailed)
        XCTAssertEqual(model.garminSyncStatus, "Garmin 已连接，本次同步失败；可重试")
        XCTAssertTrue(model.garminConnectionState.canRetrySavedSession)
        XCTAssertNil(model.lastGarminSyncAt, "a failed pull is never shown as 上次成功")
        XCTAssertNotNil(try store.loadSession(), "a plain failure keeps the login for a retry")

        server.postStatus = 200
        server.post = { garminRun(state: "queued", jobId: "job-error") }
        server.jobStates = ["error"]

        let jobFailure = await model.syncGarminDataOutcome()

        XCTAssertEqual(jobFailure, .failed)
        XCTAssertEqual(model.garminConnectionState, .syncFailed)
        XCTAssertNil(model.lastGarminSyncAt)
    }

    // goals: I-16
    func testFailedFirstPullOfANewLoginSaysNotYetVerified() async throws {
        let store = try makeStore(verified: false)
        let server = GarminFakeServer()
        server.postStatus = 503
        let model = makeModel(server: server, store: store)

        let succeeded = await model.syncGarminData()

        XCTAssertFalse(succeeded)
        XCTAssertEqual(model.garminConnectionState, .verificationFailed)
        XCTAssertEqual(model.garminSyncStatus, "Garmin 登录已保存，暂时无法验证；可重试")
        XCTAssertFalse(model.garminConnectionState.isVerified)
        XCTAssertNil(try XCTUnwrap(try store.loadSession()).verifiedAt)
    }

    // goals: I-16
    func testJobStillRunningAfterPollingIsReportedInProgressNotDone() async throws {
        let store = try makeStore(verified: true)
        let server = GarminFakeServer()
        server.post = { garminRun(state: "running", jobId: "job-long") }
        server.jobStates = []
        server.jobFallbackState = "running"
        let model = makeModel(server: server, store: store)

        let outcome = await model.syncGarminDataOutcome()

        XCTAssertEqual(outcome, .inProgress)
        XCTAssertEqual(model.garminConnectionState, .syncing)
        XCTAssertEqual(model.garminSyncStatus, "Garmin 已连接，正在同步")
        XCTAssertEqual(server.jobPolls, 60)
        XCTAssertNil(model.lastGarminSyncAt)

        server.post = { garminRun(state: "no_data", jobId: "job-stored", errorCode: "session_stored") }

        let stored = await model.syncGarminDataOutcome()

        XCTAssertEqual(stored, .inProgress, "a login that was only stored is not a finished pull")
        XCTAssertEqual(model.garminConnectionState, .awaitingVerification)
        XCTAssertEqual(model.garminSyncStatus, "Garmin 登录已保存，等待数据验证")
        XCTAssertNil(model.lastGarminSyncAt)
    }

    // goals: I-16
    func testAutoSyncDoesNothingWithoutASavedGarminLogin() async throws {
        let server = GarminFakeServer()
        server.post = { garminRun(state: "ready", jobId: "job-never") }

        let noStoreModel = makeModel(server: server, store: nil)
        await noStoreModel.autoSyncGarminIfNeeded()

        let emptyStore = GarminSessionStore(service: "goal-tests.garmin.\(UUID().uuidString)")
        self.store = emptyStore
        let emptyModel = makeModel(server: server, store: emptyStore)
        await emptyModel.autoSyncGarminIfNeeded()

        XCTAssertEqual(server.requestCount, 0)
        XCTAssertFalse(noStoreModel.isGarminSyncing)
        XCTAssertFalse(emptyModel.isGarminSyncing)
        XCTAssertEqual(emptyModel.garminConnectionState, .disconnected)
    }

    // goals: I-16
    func testAutoSyncPullsASavedLoginAndOnlyThenMarksItVerified() async throws {
        let store = try makeStore(verified: false)
        let server = GarminFakeServer()
        server.post = { garminRun(state: "ready", jobId: "job-auto") }
        server.status = { posted in
            posted ? garminStatus(state: "ready", newRoundCount: 0) : nil
        }
        let model = makeModel(server: server, store: store)
        let log = watchStates(of: model, into: server)

        await model.autoSyncGarminIfNeeded()

        XCTAssertEqual(server.postURLs.count, 1, "a saved but unverified login is pulled automatically")
        XCTAssertTrue(log.states.contains(.verifying))
        XCTAssertEqual(model.garminConnectionState, .connectedNoChanges)
        XCTAssertEqual(model.garminSyncStatus, "Garmin 已同步，暂无新球局")
        XCTAssertNotNil(try XCTUnwrap(try store.loadSession()).verifiedAt)
        XCTAssertNotNil(model.lastGarminSyncAt)

        await model.autoSyncGarminIfNeeded()

        XCTAssertEqual(server.postURLs.count, 1, "a login verified moments ago is not pulled again")
        XCTAssertEqual(model.garminConnectionState, .connectedNoChanges)
    }

    // goals: I-16
    func testAutoSyncReportsAnExpiredLoginInsteadOfAFailure() async throws {
        let store = try makeStore(verified: true)
        let server = GarminFakeServer()
        server.post = { garminRun(state: "reauth_required", jobId: "job-auto-expired", reauthRequired: true) }
        let model = makeModel(server: server, store: store)

        await model.autoSyncGarminIfNeeded()

        XCTAssertEqual(server.postURLs.count, 1)
        XCTAssertEqual(model.garminConnectionState, .reauthRequired)
        XCTAssertEqual(model.garminSyncStatus, "Garmin 登录已过期，请重新连接")
        XCTAssertNil(try store.loadSession())
    }

    private func makeStore(verified: Bool) throws -> GarminSessionStore {
        let store = GarminSessionStore(service: "goal-tests.garmin.\(UUID().uuidString)")
        self.store = store
        try store.saveSession(GarminSessionMaterial(
            webSessionHeader: "SESSION=goal",
            antiForgeryValue: "csrf-goal",
            storedAt: "2026-01-01T00:00:00Z",
            verifiedAt: verified ? "2026-01-01T00:05:00Z" : nil
        ))
        return store
    }

    private func makeModel(server: GarminFakeServer, store: GarminSessionStore?) -> LiveRoundAppModel {
        let scope = CapturingURLProtocolScope { request in try server.handle(request) }
        scopes.append(scope)
        let baseURL = URL(string: "https://example.test")!
        let client = SyncClient(
            baseURL: baseURL,
            adminToken: "admin-secret",
            session: URLSession(configuration: scope.configuration()),
            retrySleep: { _ in }
        )
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("garmin-goal-store-\(UUID().uuidString)", isDirectory: true)
        return LiveRoundAppModel(
            offlineStore: OfflineStore(directoryURL: directory),
            apiBaseURL: baseURL,
            adminToken: "admin-secret",
            watchBridge: nil,
            garminSessionStore: store,
            syncClient: client
        )
    }

    private func watchStates(of model: LiveRoundAppModel, into server: GarminFakeServer) -> GarminStateLog {
        let log = GarminStateLog()
        server.stateLog = log
        model.$garminConnectionState
            .sink { log.append($0) }
            .store(in: &cancellables)
        return log
    }
}

private final class GarminStateLog: @unchecked Sendable {
    private let lock = NSLock()
    private var stored: [GarminConnectionState] = []

    func append(_ state: GarminConnectionState) {
        lock.lock(); defer { lock.unlock() }
        stored.append(state)
    }

    var states: [GarminConnectionState] {
        lock.lock(); defer { lock.unlock() }
        return stored
    }
}

/// The Garmin side of the homeserver: one POST that enqueues a job, the job status URL it polls,
/// and the last-run summary. Anything else (post-sync course/bag/home refreshes) answers 404.
private final class GarminFakeServer: @unchecked Sendable {
    private let lock = NSLock()
    var post: () -> String = { garminRun(state: "ready", jobId: "job") }
    var postStatus = 200
    var jobStates: [String] = []
    var jobFallbackState = "ready"
    var status: (_ posted: Bool) -> String? = { _ in nil }
    var stateLog: GarminStateLog?
    private var postedURLs: [URL] = []
    private var polls = 0
    private var reads = 0
    private var requests = 0
    private var seenDuringPolls: [GarminConnectionState] = []

    var postURLs: [URL] { locked { postedURLs } }
    var jobPolls: Int { locked { polls } }
    var statusReads: Int { locked { reads } }
    var requestCount: Int { locked { requests } }
    var statesSeenDuringPolls: [GarminConnectionState] { locked { seenDuringPolls } }

    private func locked<T>(_ body: () -> T) -> T {
        lock.lock(); defer { lock.unlock() }
        return body()
    }

    func handle(_ request: URLRequest) throws -> (HTTPURLResponse, Data) {
        let url = try XCTUnwrap(request.url)
        lock.lock(); defer { lock.unlock() }
        requests += 1
        switch (request.httpMethod ?? "GET", url.path) {
        case ("POST", "/api/v2/sync/garmin"):
            postedURLs.append(url)
            guard postStatus == 200 else {
                return garminResponse(url, status: postStatus, body: #"{"detail":"server error"}"#)
            }
            return garminResponse(url, body: post())
        case ("GET", let path) where path.hasPrefix("/api/v2/sync/garmin/jobs/"):
            polls += 1
            if let last = stateLog?.states.last { seenDuringPolls.append(last) }
            let state = jobStates.isEmpty ? jobFallbackState : jobStates.removeFirst()
            let jobId = String(path.dropFirst("/api/v2/sync/garmin/jobs/".count))
            return garminResponse(url, body: garminRun(
                state: state,
                jobId: jobId,
                reauthRequired: state == "reauth_required"
            ))
        case ("GET", "/api/v2/sync/status"):
            guard let body = status(!postedURLs.isEmpty) else {
                return garminResponse(url, status: 404, body: #"{"detail":"none"}"#)
            }
            reads += 1
            return garminResponse(url, body: body)
        default:
            return garminResponse(url, status: 404, body: #"{"detail":"not in this fake"}"#)
        }
    }
}

private func garminResponse(_ url: URL, status: Int = 200, body: String) -> (HTTPURLResponse, Data) {
    (
        HTTPURLResponse(
            url: url,
            statusCode: status,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!,
        Data(body.utf8)
    )
}

private func garminRun(
    state: String,
    jobId: String,
    reauthRequired: Bool = false,
    errorCode: String? = nil
) -> String {
    let code = errorCode.map { "\"\($0)\"" } ?? (reauthRequired ? "\"reauth_required\"" : "null")
    return """
    {"schema":"ai-caddie-sync-run-v2","connector":"garmin_cn_web_session","state":"\(state)",\
    "jobId":"\(jobId)","statusUrl":"/api/v2/sync/garmin/jobs/\(jobId)",\
    "createdAt":"2026-08-20T12:30:00Z","updatedAt":"2026-08-20T12:30:01Z",\
    "startedAt":"2026-08-20T12:30:00Z","completedAt":null,"detail":"\(state)",\
    "reauthRequired":\(reauthRequired),"errorCode":\(code),"snapshot":null,"safeMeta":{}}
    """
}

/// The last-run summary is stamped "now" so it is never older than the saved login it verifies.
private func garminStatus(state: String, newRoundCount: Int) -> String {
    let now = ISO8601DateFormatter().string(from: Date())
    return """
    {"schema":"ai-caddie-sync-status-v2","lastRun":{"state":"\(state)","detail":"done",\
    "updatedAt":"\(now)","newRoundCount":\(newRoundCount)}}
    """
}
