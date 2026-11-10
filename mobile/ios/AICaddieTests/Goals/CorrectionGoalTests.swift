// size: medium
// goals: I-15
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import AICaddie

/// I-15: in the round correction editor, adding, reordering or deleting strokes on one screen keeps
/// the shot numbers contiguous, and after submit the corrected hole takes effect immediately. A
/// failed submit must never present the local draft as applied.
@MainActor
final class CorrectionGoalTests: XCTestCase {
    private var scope: CapturingURLProtocolScope?

    override func tearDown() {
        scope = nil
        super.tearDown()
    }

    // MARK: - Draft operations keep numbers contiguous

    // goals: I-15
    func testAddingAStrokeKeepsShotNumbersContiguous() {
        let recorder = CorrectionRequestRecorder()
        let model = makeModel(recorder: recorder) { request in
            correctionResponse(request, status: 503)
        }

        model.enterEdit()
        let afterFirst = model.addShot(px: [45, 55], club: "5W", lie: "fairway", afterShotId: "shot-1")
        XCTAssertFalse(afterFirst.isEmpty, "a precise map must accept a new stroke")
        XCTAssertEqual(model.map.shots.map(\.id), ["shot-1", afterFirst, "shot-2", "shot-3", "putt-1"])
        assertContiguous(model)
        XCTAssertEqual(model.displayNumber(of: afterFirst), 2)
        XCTAssertEqual(model.displayNumber(of: "shot-3"), 4)

        // Nothing selected: the new full shot lands after the last full shot, before the putt.
        let appended = model.addShot(px: [52, 12], club: "PW", lie: "fairway")
        XCTAssertEqual(model.map.shots.map(\.id), ["shot-1", afterFirst, "shot-2", "shot-3", appended, "putt-1"])
        assertContiguous(model)
        XCTAssertEqual(model.fullShotCount, 5)
        XCTAssertEqual(model.displayNumber(of: appended), 5)
        XCTAssertNil(model.displayNumber(of: "putt-1"), "putts are counted, never numbered as full shots")
        XCTAssertTrue(model.hasUnsavedChanges)
        XCTAssertTrue(recorder.requests.isEmpty, "drafting must not write to the server")
    }

    // goals: I-15
    func testReorderingStrokesRenumbersInTheNewOrder() {
        let recorder = CorrectionRequestRecorder()
        let model = makeModel(recorder: recorder) { request in
            correctionResponse(request, status: 503)
        }

        model.enterEdit()
        XCTAssertTrue(model.canMoveShot("shot-3", by: -1))
        XCTAssertFalse(model.canMoveShot("shot-3", by: 1), "a full shot never swaps with a putt row")
        model.moveShot("shot-3", by: -1)

        XCTAssertEqual(model.map.shots.map(\.id), ["shot-1", "shot-3", "shot-2", "putt-1"])
        assertContiguous(model)
        XCTAssertEqual(model.displayNumber(of: "shot-3"), 2)
        XCTAssertEqual(model.displayNumber(of: "shot-2"), 3)
        // The moved stroke now starts where the first stroke ended.
        XCTAssertEqual(model.map.shots[1].start, [40, 65])

        // A full reorder through the list API also renumbers.
        model.reorder(["shot-2", "shot-1", "shot-3", "putt-1"])
        XCTAssertEqual(model.map.shots.map(\.id), ["shot-2", "shot-1", "shot-3", "putt-1"])
        assertContiguous(model)
        XCTAssertEqual(model.displayNumber(of: "shot-2"), 1)

        // A reorder that would move the putt row is refused and changes nothing.
        let before = model.map.shots
        model.reorder(["putt-1", "shot-1", "shot-3", "shot-2"])
        XCTAssertEqual(model.map.shots, before)
        XCTAssertTrue(recorder.requests.isEmpty)
    }

    // goals: I-15
    func testDeletingAMiddleStrokeClosesTheGap() {
        let recorder = CorrectionRequestRecorder()
        let model = makeModel(recorder: recorder) { request in
            correctionResponse(request, status: 503)
        }

        model.enterEdit()
        model.delete(shotId: "shot-2")

        XCTAssertEqual(model.map.shots.map(\.id), ["shot-1", "shot-3", "putt-1"])
        assertContiguous(model)
        XCTAssertEqual(model.displayNumber(of: "shot-3"), 2)
        XCTAssertEqual(model.fullShotCount, 2)
        // The stroke after the gap is re-chained to the previous landing.
        XCTAssertEqual(model.map.shots[1].start, [40, 65])
        XCTAssertTrue(model.hasUnsavedChanges)
        XCTAssertTrue(recorder.requests.isEmpty)
    }

    // goals: I-15
    func testDeletingTheLastFullStrokeKeepsTheRemainingNumbers() {
        let recorder = CorrectionRequestRecorder()
        let model = makeModel(recorder: recorder) { request in
            correctionResponse(request, status: 503)
        }

        model.enterEdit()
        model.delete(shotId: "shot-3")

        XCTAssertEqual(model.map.shots.map(\.id), ["shot-1", "shot-2", "putt-1"])
        assertContiguous(model)
        XCTAssertEqual(model.displayNumber(of: "shot-1"), 1)
        XCTAssertEqual(model.displayNumber(of: "shot-2"), 2)
        XCTAssertNil(model.displayNumber(of: "shot-3"))
        XCTAssertEqual(model.fullShotCount, 2)

        // Deleting down to the first stroke still leaves a contiguous 1-based list.
        model.delete(shotId: "shot-2")
        XCTAssertEqual(model.map.shots.map(\.id), ["shot-1", "putt-1"])
        assertContiguous(model)
        XCTAssertTrue(recorder.requests.isEmpty)
    }

    // MARK: - Submit

    // goals: I-15 [main]
    func testSubmittedCorrectionIsSentContiguousAndTakesEffectImmediately() async throws {
        let recorder = CorrectionRequestRecorder()
        let serverMap = #"""
        {"found":true,"hole":4,"par":4,"globalId":3881,"localHole":4,"geometryRevision":"geometry-r2",
         "map":{"overlay":{"w":100,"h":100,"ppm":1,"ln":100,"route":[[50,95,0],[50,50,50],[50,5,100]]}},
         "shots":[
          {"id":"shot-1","start":[50,95],"end":[40,65],"club":"Driver","lie":"tee","order":1},
          {"id":"s:server:2","start":[40,65],"end":[45,55],"club":"5W","lie":"fairway","order":2,"clubSource":"manual"},
          {"id":"shot-2","start":[45,55],"end":[50,20],"club":"7I","lie":"fairway","order":3},
          {"id":"putt-1","start":[50,20],"end":[50,18],"club":"Putter","lie":"green","shotType":"PUTT","order":4}
         ],
         "manualPenalty":0,"missingData":[]}
        """#
        let model = makeModel(recorder: recorder) { request in
            if request.httpMethod == "POST" {
                return correctionResponse(request, status: 201, body: #"{"stored":{}}"#)
            }
            if request.url?.path.hasSuffix("/holes/4/shotmap") == true {
                return correctionResponse(request, status: 200, body: serverMap)
            }
            return correctionResponse(request, status: 503)
        }

        model.enterEdit()
        model.delete(shotId: "shot-3")
        let added = model.addShot(px: [45, 55], club: "5W", lie: "fairway", afterShotId: "shot-1")
        XCTAssertEqual(model.map.shots.map(\.id), ["shot-1", added, "shot-2", "putt-1"])
        assertContiguous(model)

        let saved = await model.save()

        XCTAssertTrue(saved)
        let requests = recorder.requests
        XCTAssertEqual(requests.map(\.method), ["POST", "GET"], "one atomic write, then a refetch")
        let post = try XCTUnwrap(requests.first)
        XCTAssertEqual(post.path, "/api/v2/history/rounds/round-1/corrections")
        let body = try XCTUnwrap(try JSONSerialization.jsonObject(with: post.body) as? [String: Any])
        XCTAssertEqual(body["op"] as? String, "replaceHoleShots")
        XCTAssertEqual(body["hole"] as? Int, 4)
        XCTAssertEqual(body["geometryRevision"] as? String, "geometry-r1")
        XCTAssertNotNil(body["clientMutationId"] as? String)
        let sentShots = try XCTUnwrap(body["shots"] as? [[String: Any]])
        XCTAssertEqual(sentShots.compactMap { $0["id"] as? String }, ["shot-1", added, "shot-2", "putt-1"])
        XCTAssertEqual(sentShots.compactMap { $0["order"] as? Int }, [1, 2, 3, 4])
        XCTAssertEqual(sentShots[1]["club"] as? String, "5W")
        XCTAssertEqual(sentShots[2]["start"] as? [Int], [45, 55], "the next stroke starts at the added landing")

        // Effective immediately: the screen shows the server's corrected hole, not a stale draft.
        XCTAssertFalse(model.isEditing)
        XCTAssertFalse(model.hasUnsavedChanges)
        XCTAssertNil(model.saveError)
        XCTAssertEqual(model.map.geometryRevision, "geometry-r2")
        XCTAssertEqual(model.map.shots.map(\.id), ["shot-1", "s:server:2", "shot-2", "putt-1"])
        XCTAssertEqual(model.displayNumber(of: "s:server:2"), 2)
        XCTAssertEqual(model.displayNumber(of: "shot-2"), 3)

        // A new edit session starts from the applied result, not from the pre-submit hole.
        model.enterEdit()
        XCTAssertEqual(model.map.shots.map(\.id), ["shot-1", "s:server:2", "shot-2", "putt-1"])
        assertContiguous(model)
    }

    // goals: I-15
    func testFailedSubmitKeepsTheDraftAndDoesNotClaimItWasApplied() async throws {
        let recorder = CorrectionRequestRecorder()
        let model = makeModel(recorder: recorder) { request in
            correctionResponse(request, status: 500, body: #"{"detail":"boom"}"#)
        }
        let original = model.map

        model.enterEdit()
        model.delete(shotId: "shot-2")
        let draft = model.map

        let saved = await model.save()

        XCTAssertFalse(saved)
        XCTAssertEqual(recorder.requests.map(\.method), ["POST"], "no refetch after a rejected write")
        XCTAssertTrue(model.isEditing, "the editor stays open on the unsaved draft")
        XCTAssertFalse(model.isSaving)
        XCTAssertTrue(model.hasUnsavedChanges, "the change is still pending, not applied")
        XCTAssertNotNil(model.saveError)
        XCTAssertEqual(model.map, draft, "the draft survives for a retry")

        // Leaving the editor shows the server's last known hole: the failed change never took effect.
        model.cancelEdit()
        XCTAssertFalse(model.isEditing)
        XCTAssertEqual(model.map, original)
        XCTAssertEqual(model.map.shots.map(\.id), ["shot-1", "shot-2", "shot-3", "putt-1"])
    }

    // goals: I-15
    func testRetryAfterFailedSubmitReusesTheSameMutationAndThenApplies() async throws {
        let recorder = CorrectionRequestRecorder()
        let lock = NSLock()
        var postCount = 0
        let model = makeModel(recorder: recorder) { request in
            if request.httpMethod == "POST" {
                lock.lock()
                postCount += 1
                let attempt = postCount
                lock.unlock()
                return correctionResponse(request, status: attempt == 1 ? 502 : 201, body: #"{"stored":{}}"#)
            }
            // The refetch fails: the accepted draft is then the applied state.
            return correctionResponse(request, status: 404, body: "{}")
        }

        model.enterEdit()
        model.delete(shotId: "shot-1")
        let firstAttempt = await model.save()
        XCTAssertFalse(firstAttempt)
        XCTAssertTrue(model.isEditing)

        let secondAttempt = await model.save()
        XCTAssertTrue(secondAttempt)
        XCTAssertFalse(model.isEditing)
        XCTAssertNil(model.saveError)
        XCTAssertEqual(model.map.shots.map(\.id), ["shot-2", "shot-3", "putt-1"])
        XCTAssertEqual(model.displayNumber(of: "shot-2"), 1)

        let posts = recorder.requests.filter { $0.method == "POST" }
        XCTAssertEqual(posts.count, 2)
        let ids = try posts.map { post -> String? in
            let json = try JSONSerialization.jsonObject(with: post.body) as? [String: Any]
            return json?["clientMutationId"] as? String
        }
        XCTAssertNotNil(ids.first ?? nil)
        XCTAssertEqual(ids.first ?? nil, ids.last ?? nil, "a retry must be idempotent")
        let sent = try XCTUnwrap(try JSONSerialization.jsonObject(with: posts[1].body) as? [String: Any])
        let sentShots = try XCTUnwrap(sent["shots"] as? [[String: Any]])
        XCTAssertEqual(sentShots.compactMap { $0["order"] as? Int }, [1, 2, 3])

        // Re-entering edit starts from the applied hole.
        model.enterEdit()
        XCTAssertEqual(model.map.shots.map(\.id), ["shot-2", "shot-3", "putt-1"])
    }

    // goals: I-15
    func testPostRoundCorrectionSendsTheOperationAndSurfacesRejection() async throws {
        let recorder = CorrectionRequestRecorder()
        let lock = NSLock()
        var status = 201
        let scope = CapturingURLProtocolScope { request in
            recorder.record(request)
            lock.lock()
            let current = status
            lock.unlock()
            return correctionResponse(request, status: current, body: #"{"stored":{}}"#)
        }
        self.scope = scope
        let client = SyncClient(
            baseURL: URL(string: "https://example.test")!,
            session: URLSession(configuration: scope.configuration()),
            retrySleep: { _ in }
        )
        let shots = [
            RoundShot(shotId: "a", start: [50, 95], end: [40, 65], club: "Driver", lie: "tee", order: 1),
            RoundShot(shotId: "b", start: [40, 65], end: [50, 20], club: "7I", lie: "fairway", order: 2),
        ]
        let op = RoundCorrectionOp.replaceHoleShots(
            hole: 7, shots: shots, manualPenalty: 1, geometryRevision: "g-7",
            clientMutationId: "mutation-1", clientTime: "2026-11-10T08:00:00Z"
        )

        try await client.postRoundCorrection(roundRef: "round 9", op)

        let post = try XCTUnwrap(recorder.requests.first)
        XCTAssertEqual(post.method, "POST")
        XCTAssertEqual(post.path, "/api/v2/history/rounds/round 9/corrections")
        XCTAssertEqual(post.contentType, "application/json")
        let body = try XCTUnwrap(try JSONSerialization.jsonObject(with: post.body) as? [String: Any])
        XCTAssertEqual(body["op"] as? String, "replaceHoleShots")
        XCTAssertEqual(body["hole"] as? Int, 7)
        XCTAssertEqual(body["manualPenalty"] as? Int, 1)
        XCTAssertEqual(body["geometryRevision"] as? String, "g-7")
        XCTAssertEqual(body["clientMutationId"] as? String, "mutation-1")
        XCTAssertEqual(body["clientTime"] as? String, "2026-11-10T08:00:00Z")
        let sentShots = try XCTUnwrap(body["shots"] as? [[String: Any]])
        XCTAssertEqual(sentShots.compactMap { $0["id"] as? String }, ["a", "b"])
        XCTAssertEqual(sentShots.compactMap { $0["order"] as? Int }, [1, 2])

        lock.lock()
        status = 409
        lock.unlock()
        do {
            try await client.postRoundCorrection(roundRef: "round 9", op)
            XCTFail("a rejected correction must throw, never report success")
        } catch let SyncClientError.http(status: code, body: _) {
            XCTAssertEqual(code, 409)
        }
    }

    // MARK: - Fixture

    private func assertContiguous(
        _ model: RoundEditModel,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        let orders = model.map.shots.map(\.order)
        XCTAssertEqual(orders, Array(1...model.map.shots.count).map { Optional($0) }, "orders", file: file, line: line)
        let numbers = model.map.shots.filter(roundShotIsFullShot).compactMap { model.displayNumber(of: $0.id) }
        XCTAssertEqual(numbers, model.fullShotCount == 0 ? [] : Array(1...model.fullShotCount), "display numbers", file: file, line: line)
    }

    private func makeModel(
        recorder: CorrectionRequestRecorder,
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> RoundEditModel {
        let scope = CapturingURLProtocolScope { request in
            recorder.record(request)
            return try handler(request)
        }
        self.scope = scope
        let overlay = CoursePrepOverlay(
            w: 100, h: 100, ppm: 1, ln: 100,
            route: [[50, 95, 0], [50, 50, 50], [50, 5, 100]]
        )
        let shots = [
            RoundShot(shotId: "shot-1", start: [50, 95], end: [40, 65], club: "Driver", lie: "tee", endLie: "fairway", order: 1),
            RoundShot(shotId: "shot-2", start: [40, 65], end: [45, 40], club: "7I", lie: "fairway", endLie: "fairway", order: 2),
            RoundShot(shotId: "shot-3", start: [45, 40], end: [50, 20], club: "9I", lie: "fairway", endLie: "green", order: 3),
            RoundShot(shotId: "putt-1", start: [50, 20], end: [50, 18], club: "Putter", lie: "green", shotType: "PUTT", order: 4),
        ]
        return RoundEditModel(
            map: RoundHoleShotMap(
                found: true, hole: 4, par: 4, globalId: 3881, localHole: 4,
                geometryRevision: "geometry-r1",
                map: CoursePrepMap(image: nil, overlay: overlay),
                shots: shots
            ),
            sync: SyncClient(
                baseURL: URL(string: "https://example.test")!,
                session: URLSession(configuration: scope.configuration()),
                retrySleep: { _ in }
            ),
            roundRef: "round-1",
            now: { Date(timeIntervalSince1970: 1_800_000_000) }
        )
    }
}

private struct CorrectionCapturedRequest {
    let method: String
    let path: String
    let contentType: String?
    let body: Data
}

private final class CorrectionRequestRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var stored: [CorrectionCapturedRequest] = []

    var requests: [CorrectionCapturedRequest] {
        lock.lock()
        defer { lock.unlock() }
        return stored
    }

    func record(_ request: URLRequest) {
        let body = (try? CapturingURLProtocol.requestBodyData(from: request)) ?? Data()
        let captured = CorrectionCapturedRequest(
            method: request.httpMethod ?? "GET",
            path: request.url?.path ?? "",
            contentType: request.value(forHTTPHeaderField: "Content-Type"),
            body: body
        )
        lock.lock()
        stored.append(captured)
        lock.unlock()
    }
}

private func correctionResponse(_ request: URLRequest, status: Int, body: String = "") -> (HTTPURLResponse, Data) {
    (
        HTTPURLResponse(
            url: request.url!,
            statusCode: status,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!,
        Data(body.utf8)
    )
}
