// size: medium
// goals: I-21
//
// I-21: client timing diagnostics are reported with throttling, never disturb the business
// flow, and a failed diagnostics upload keeps its records for a later retransmission.
// Entry point: SyncClient business calls (fetchCoursePrep) with an upload-enabled
// ClientTimingStore; only the HTTP edge (URLProtocol) and the monotonic clock are faked.

import Foundation
import XCTest
@testable import AICaddie

private let timingGoalPath = "/api/v2/mobile/client-timing"
private let timingGoalPrepPayload = Data(
    #"{"schema":"ai-caddie-course-prep-v1","globalId":31870,"holeCount":0,"clubs":[],"holes":[]}"#.utf8
)

/// Injected monotonic clock; the store and the client read it, nothing waits on it.
private final class TimingGoalClock: @unchecked Sendable {
    private let lock = NSLock()
    private var value: TimeInterval

    init(_ value: TimeInterval) { self.value = value }

    func now() -> TimeInterval {
        lock.lock()
        defer { lock.unlock() }
        return value
    }

    func set(_ newValue: TimeInterval) {
        lock.lock()
        value = newValue
        lock.unlock()
    }
}

/// How the fake server answers the n-th (0-based) diagnostics upload.
private enum TimingGoalUploadReply {
    case status(Int)
    case transport(URLError.Code)
}

/// Fake server edge: answers business calls with a valid prep payload and records every
/// diagnostics upload as the list of request ids it carried.
private final class TimingGoalServer: @unchecked Sendable {
    private let lock = NSLock()
    private var uploadIds: [[String]] = []
    private var businessIds: [String] = []
    private var uploadExpectations: [Int: XCTestExpectation] = [:]
    private let reply: (Int) -> TimingGoalUploadReply

    init(reply: @escaping (Int) -> TimingGoalUploadReply) {
        self.reply = reply
    }

    func expectUpload(index: Int, _ expectation: XCTestExpectation) {
        lock.lock()
        uploadExpectations[index] = expectation
        lock.unlock()
    }

    var uploads: [[String]] {
        lock.lock()
        defer { lock.unlock() }
        return uploadIds
    }

    var businessRequestIds: [String] {
        lock.lock()
        defer { lock.unlock() }
        return businessIds
    }

    func handle(_ request: URLRequest) throws -> (HTTPURLResponse, Data) {
        let url = try XCTUnwrap(request.url)
        if url.path == timingGoalPath {
            let body = try CapturingURLProtocol.requestBodyData(from: request)
            let rows = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [[String: Any]])
            let ids = rows.compactMap { $0["request_id"] as? String }
            lock.lock()
            let index = uploadIds.count
            uploadIds.append(ids)
            let expectation = uploadExpectations[index]
            lock.unlock()
            expectation?.fulfill()
            switch reply(index) {
            case .status(let status):
                let response = try XCTUnwrap(HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil))
                return (response, Data(#"{"accepted":0,"rejected":0}"#.utf8))
            case .transport(let code):
                throw URLError(code)
            }
        }
        lock.lock()
        businessIds.append(request.value(forHTTPHeaderField: "X-AI-Caddie-Request-ID") ?? "")
        lock.unlock()
        let response = try XCTUnwrap(HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil))
        return (response, timingGoalPrepPayload)
    }
}

final class TimingGoalTests: XCTestCase {
    private func makeClient(
        server: TimingGoalServer,
        clock: TimingGoalClock
    ) throws -> (SyncClient, URLSession, CapturingURLProtocolScope) {
        let scope = CapturingURLProtocolScope(handler: { try server.handle($0) })
        let session = URLSession(configuration: scope.configuration())
        let store = ClientTimingStore(fileURL: nil, now: { clock.now() }, uploadsEnabled: true)
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session,
            retrySleep: { _ in },
            monotonicNow: { clock.now() },
            timingStore: store
        )
        return (client, session, scope)
    }

    /// Runs business calls until the fake server has seen `uploads` diagnostics uploads, with a
    /// hard cap so a broken uploader fails by assertion rather than hanging.
    private func callUntilUploads(
        _ client: SyncClient,
        server: TimingGoalServer,
        uploads: Int,
        cap: Int
    ) async throws -> Int {
        var calls = 0
        while server.uploads.count < uploads && calls < cap {
            let prep = try await client.fetchCoursePrep(globalId: 31870, render: false)
            XCTAssertEqual(prep.globalId, 31870)
            calls += 1
        }
        return calls
    }

    // goals: I-21 [main]
    func testFailedTimingUploadKeepsRecordsForRetransmission() async throws {
        let server = TimingGoalServer(reply: { index in
            index == 0 ? .status(503) : .status(200)
        })
        let clock = TimingGoalClock(100)
        let (client, session, scope) = try makeClient(server: server, clock: clock)
        defer {
            session.invalidateAndCancel()
            withExtendedLifetime(scope) {}
        }
        let firstUpload = expectation(description: "first diagnostics upload")
        let secondUpload = expectation(description: "retransmission upload")
        server.expectUpload(index: 0, firstUpload)
        server.expectUpload(index: 1, secondUpload)

        for _ in 0..<10 {
            let prep = try await client.fetchCoursePrep(globalId: 31870, render: false)
            XCTAssertEqual(prep.globalId, 31870, "business flow must succeed regardless of diagnostics")
        }
        await fulfillment(of: [firstUpload], timeout: 10)

        let more = try await callUntilUploads(client, server: server, uploads: 2, cap: 40)
        await fulfillment(of: [secondUpload], timeout: 10)

        let uploads = server.uploads
        XCTAssertGreaterThanOrEqual(uploads.count, 2)
        let first = Set(uploads[0])
        let second = Set(uploads[1])
        XCTAssertEqual(first.count, 10, "the throttle sends the first batch at ten records")
        XCTAssertTrue(
            first.isSubset(of: second),
            "records of a failed upload must be retransmitted, missing: \(first.subtracting(second).sorted())"
        )
        XCTAssertEqual(server.businessRequestIds.count, 10 + more, "diagnostics never add business requests")
        XCTAssertTrue(first.isSubset(of: Set(server.businessRequestIds)), "uploaded ids are the business request ids")
    }

    // goals: I-21
    func testTimingIsThrottledByCountAndInterval() async throws {
        let server = TimingGoalServer(reply: { _ in .status(200) })
        let clock = TimingGoalClock(100)
        let (client, session, scope) = try makeClient(server: server, clock: clock)
        defer {
            session.invalidateAndCancel()
            withExtendedLifetime(scope) {}
        }
        let firstUpload = expectation(description: "interval upload")
        server.expectUpload(index: 0, firstUpload)

        // Interval boundary: 59 s after the oldest record is not yet due, 60 s is.
        _ = try await client.fetchCoursePrep(globalId: 31870, render: false)
        _ = try await client.fetchCoursePrep(globalId: 31870, render: false)
        clock.set(159)
        _ = try await client.fetchCoursePrep(globalId: 31870, render: false)
        clock.set(160)
        _ = try await client.fetchCoursePrep(globalId: 31870, render: false)
        await fulfillment(of: [firstUpload], timeout: 10)

        let uploads = server.uploads
        XCTAssertEqual(uploads.first?.count, 4, "no upload before the 60 s window; the due upload carries all four records")
        XCTAssertEqual(Set(uploads.first ?? []), Set(server.businessRequestIds))
    }

    // goals: I-21
    func testCountThresholdSendsExactlyTenRecords() async throws {
        let server = TimingGoalServer(reply: { _ in .status(200) })
        let clock = TimingGoalClock(500)
        let (client, session, scope) = try makeClient(server: server, clock: clock)
        defer {
            session.invalidateAndCancel()
            withExtendedLifetime(scope) {}
        }
        let firstUpload = expectation(description: "threshold upload")
        server.expectUpload(index: 0, firstUpload)

        // Same instant for every call: only the count threshold (10) can trigger an upload, so
        // an upload started at nine records would carry nine ids.
        for _ in 0..<10 {
            _ = try await client.fetchCoursePrep(globalId: 31870, render: false)
        }
        await fulfillment(of: [firstUpload], timeout: 10)

        XCTAssertEqual(server.uploads.first?.count, 10)
        XCTAssertEqual(server.businessRequestIds.count, 10)
    }

    // goals: I-21
    func testRejectedTimingUploadIsDroppedAndBusinessUnaffected() async throws {
        let server = TimingGoalServer(reply: { index in
            switch index {
            case 0: return .status(422)
            case 1: return .transport(.notConnectedToInternet)
            default: return .status(200)
            }
        })
        let clock = TimingGoalClock(100)
        let (client, session, scope) = try makeClient(server: server, clock: clock)
        defer {
            session.invalidateAndCancel()
            withExtendedLifetime(scope) {}
        }
        let firstUpload = expectation(description: "rejected upload")
        let secondUpload = expectation(description: "next upload")
        server.expectUpload(index: 0, firstUpload)
        server.expectUpload(index: 1, secondUpload)

        for _ in 0..<10 {
            _ = try await client.fetchCoursePrep(globalId: 31870, render: false)
        }
        await fulfillment(of: [firstUpload], timeout: 10)
        let more = try await callUntilUploads(client, server: server, uploads: 2, cap: 40)
        await fulfillment(of: [secondUpload], timeout: 10)

        let uploads = server.uploads
        XCTAssertGreaterThanOrEqual(uploads.count, 2)
        XCTAssertTrue(
            Set(uploads[0]).isDisjoint(with: Set(uploads[1])),
            "an explicit 4xx rejection is final; those records are not resent"
        )
        XCTAssertGreaterThanOrEqual(more, 10, "a fresh batch needs ten new records")
        XCTAssertEqual(server.businessRequestIds.count, 10 + more, "a failing diagnostics endpoint never adds business requests")
    }
}
