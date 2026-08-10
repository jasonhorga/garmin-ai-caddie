import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import AICaddie

@MainActor
final class RoundEditModelTests: XCTestCase {
    override func tearDown() {
        CapturingURLProtocol.requestHandler = nil
        super.tearDown()
    }

    func testAllDraftOperationsStayLocalAndCancelRestoresTheWholeHole() async throws {
        let unexpectedRequest = expectation(description: "draft and cancel must make zero requests")
        unexpectedRequest.isInverted = true
        let model = makeModel { request in
            unexpectedRequest.fulfill()
            return Self.response(request, status: 500)
        }
        let baseline = model.map

        model.enterEdit()
        let added = model.addShot(
            px: [44.2, 48.8],
            club: "7I",
            lie: "fairway",
            afterShotId: "shot-1"
        )
        model.move(shotId: added, px: [47.7, 43.1])
        model.editClub(shotId: "shot-2", "九号铁")
        model.editLie(shotId: "shot-2", "bunker")
        model.reorder(["shot-2", "shot-1", added])
        model.delete(shotId: "shot-1")
        model.setPenalty(2)

        XCTAssertTrue(model.isEditing)
        XCTAssertTrue(model.hasUnsavedChanges)
        XCTAssertEqual(model.map.shots.map(\.id), ["shot-2", added])
        XCTAssertEqual(model.map.shots.map(\.order), [1, 2])
        XCTAssertEqual(model.map.shots[1].start, model.map.shots[0].end)
        XCTAssertEqual(model.map.manualPenalty, 2)

        model.cancelEdit()

        XCTAssertFalse(model.isEditing)
        XCTAssertFalse(model.hasUnsavedChanges)
        XCTAssertEqual(model.map, baseline)
        await fulfillment(of: [unexpectedRequest], timeout: 0.25)
    }

    func testSaveCommitsOneWholeHoleSnapshotAfterContinuousEditing() async throws {
        let posted = expectation(description: "one whole-hole snapshot POST")
        let unexpectedSecondPost = expectation(description: "must not split the save into multiple POSTs")
        unexpectedSecondPost.isInverted = true
        var postCount = 0
        var savedPayload: [String: Any] = [:]
        let model = makeModel { request in
            if request.httpMethod == "POST" {
                postCount += 1
                if postCount == 1 { posted.fulfill() } else { unexpectedSecondPost.fulfill() }
                let body = try CapturingURLProtocol.requestBodyData(from: request)
                savedPayload = try XCTUnwrap(
                    JSONSerialization.jsonObject(with: body) as? [String: Any]
                )
                return Self.response(request, status: 201, body: #"{"stored":{}}"#)
            }
            // Save may perform one read-only reconciliation. Deliberately fail it: an accepted POST
            // must still leave the locally approved snapshot as the visible read-only result.
            return Self.response(request, status: 503)
        }

        model.enterEdit()
        let third = model.addShot(px: [42, 52], afterShotId: "shot-2")
        let fourth = model.addShot(px: [55, 37], afterShotId: third)
        model.move(shotId: third, px: [46, 49])
        model.reorder(["shot-1", third, "shot-2", fourth])
        model.delete(shotId: "shot-2")
        model.setPenalty(1)

        let expectedIds = model.map.shots.map(\.id)
        let saved = await model.save()

        XCTAssertTrue(saved)
        XCTAssertFalse(model.isEditing)
        XCTAssertFalse(model.hasUnsavedChanges)
        XCTAssertEqual(model.map.shots.map(\.id), expectedIds)
        XCTAssertEqual(savedPayload["op"] as? String, "replaceHoleShots")
        XCTAssertEqual(savedPayload["hole"] as? Int, 4)
        XCTAssertEqual(savedPayload["manualPenalty"] as? Int, 1)
        XCTAssertEqual(savedPayload["geometryRevision"] as? String, "geometry-r1")
        XCTAssertFalse((savedPayload["clientMutationId"] as? String ?? "").isEmpty)
        let shots = try XCTUnwrap(savedPayload["shots"] as? [[String: Any]])
        XCTAssertEqual(shots.compactMap { $0["id"] as? String }, expectedIds)
        XCTAssertEqual(shots.compactMap { $0["order"] as? Int }, [1, 2, 3])
        await fulfillment(of: [posted, unexpectedSecondPost], timeout: 0.25)
    }

    func testFailedSaveKeepsDraftAndRetryReusesTheIdempotencyKey() async throws {
        let posts = expectation(description: "initial save plus retry")
        posts.expectedFulfillmentCount = 2
        var mutationIds: [String] = []
        var postCount = 0
        let model = makeModel { request in
            guard request.httpMethod == "POST" else {
                return Self.response(request, status: 503)
            }
            postCount += 1
            let data = try CapturingURLProtocol.requestBodyData(from: request)
            let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
            mutationIds.append(try XCTUnwrap(payload["clientMutationId"] as? String))
            posts.fulfill()
            return Self.response(request, status: postCount == 1 ? 503 : 201, body: #"{"stored":{}}"#)
        }

        model.enterEdit()
        model.move(shotId: "shot-1", px: [49, 61])
        let draftAfterMove = model.map

        let firstSave = await model.save()
        XCTAssertFalse(firstSave)
        XCTAssertTrue(model.isEditing)
        XCTAssertEqual(model.map, draftAfterMove)
        XCTAssertNotNil(model.saveError)

        let retrySave = await model.save()
        XCTAssertTrue(retrySave)
        XCTAssertFalse(model.isEditing)
        XCTAssertEqual(mutationIds.count, 2)
        XCTAssertEqual(mutationIds.first, mutationIds.last)
        await fulfillment(of: [posts], timeout: 2)
    }

    func testMaplessSaveUsesFactSnapshotAndNeverEncodesPixels() async throws {
        let posted = expectation(description: "one mapless fact snapshot POST")
        var savedPayload: [String: Any] = [:]
        let model = makeModel(includeMap: false, geometryRevision: nil) { request in
            if request.httpMethod == "POST" {
                let body = try CapturingURLProtocol.requestBodyData(from: request)
                savedPayload = try XCTUnwrap(
                    JSONSerialization.jsonObject(with: body) as? [String: Any]
                )
                posted.fulfill()
                return Self.response(request, status: 201, body: #"{"stored":{}}"#)
            }
            return Self.response(request, status: 503)
        }

        XCTAssertFalse(model.canEditPositions)
        model.enterEdit()
        model.move(shotId: "shot-1", px: [99, 99])
        XCTAssertFalse(model.hasUnsavedChanges, "mapless mode must reject position edits")
        model.reorder(["shot-2", "shot-1"])
        model.editClub(shotId: "shot-2", "九号铁")
        model.editLie(shotId: "shot-2", "bunker")
        model.delete(shotId: "shot-1")
        model.setPenalty(2)

        let saved = await model.save()

        XCTAssertTrue(saved)
        XCTAssertEqual(savedPayload["op"] as? String, "replaceHoleFacts")
        XCTAssertEqual(savedPayload["hole"] as? Int, 4)
        XCTAssertEqual(savedPayload["manualPenalty"] as? Int, 2)
        XCTAssertNil(savedPayload["geometryRevision"])
        let facts = try XCTUnwrap(savedPayload["shots"] as? [[String: Any]])
        XCTAssertEqual(facts.compactMap { $0["id"] as? String }, ["shot-2"])
        XCTAssertEqual(facts.first?["club"] as? String, "九号铁")
        XCTAssertEqual(facts.first?["lie"] as? String, "bunker")
        for fact in facts {
            XCTAssertNil(fact["start"])
            XCTAssertNil(fact["end"])
            XCTAssertNil(fact["order"])
            XCTAssertNil(fact["geometryRevision"])
        }
        await fulfillment(of: [posted], timeout: 2)
    }

    func testEmptyHoleCanAddSeveralNumberedShotsBeforeOneSave() async throws {
        let posted = expectation(description: "empty-hole snapshot")
        var payloadShots: [[String: Any]] = []
        let model = makeModel(shots: []) { request in
            if request.httpMethod == "POST" {
                let data = try CapturingURLProtocol.requestBodyData(from: request)
                let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
                payloadShots = try XCTUnwrap(payload["shots"] as? [[String: Any]])
                posted.fulfill()
                return Self.response(request, status: 201, body: #"{"stored":{}}"#)
            }
            return Self.response(request, status: 503)
        }

        model.enterEdit()
        let first = model.addShot(px: [31, 74])
        _ = model.addShot(px: [49, 43], afterShotId: first)

        XCTAssertEqual(model.map.shots.map(\.order), [1, 2])
        XCTAssertEqual(model.map.shots[0].start, [50, 95])
        XCTAssertEqual(model.map.shots[1].start, model.map.shots[0].end)
        let saved = await model.save()
        XCTAssertTrue(saved)
        XCTAssertEqual(payloadShots.compactMap { $0["order"] as? Int }, [1, 2])
        await fulfillment(of: [posted], timeout: 2)
    }

    private func makeModel(
        shots: [RoundShot]? = nil,
        includeMap: Bool = true,
        geometryRevision: String? = "geometry-r1",
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> RoundEditModel {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        CapturingURLProtocol.requestHandler = handler
        let courseMap = CoursePrepMap(
            image: "data:image/png;base64,AA==",
            overlay: CoursePrepOverlay(
                w: 100,
                h: 100,
                ppm: 1,
                ln: 100,
                route: [[50, 95, 0], [50, 50, 50], [50, 5, 100]]
            )
        )
        let defaultShots = [
            RoundShot(
                shotId: "shot-1",
                start: [50, 95],
                end: [40, 65],
                club: "Driver",
                lie: "teebox",
                endLie: "fairway",
                order: 1
            ),
            RoundShot(
                shotId: "shot-2",
                start: [40, 65],
                end: [50, 20],
                club: "7I",
                lie: "fairway",
                endLie: "green",
                order: 2
            ),
        ]
        return RoundEditModel(
            map: RoundHoleShotMap(
                found: true,
                hole: 4,
                par: 4,
                globalId: 3881,
                localHole: 4,
                geometryRevision: geometryRevision,
                map: includeMap ? courseMap : nil,
                shots: shots ?? defaultShots
            ),
            sync: SyncClient(
                baseURL: URL(string: "https://example.test")!,
                session: URLSession(configuration: configuration)
            ),
            roundRef: "round-1"
        )
    }

    nonisolated private static func response(
        _ request: URLRequest,
        status: Int,
        body: String = ""
    ) -> (HTTPURLResponse, Data) {
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
}
