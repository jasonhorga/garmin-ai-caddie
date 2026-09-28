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

    func testPreciseOverlayWithoutDuplicatedEmbeddedImageCanEditPositions() {
        let model = makeModel(includeEmbeddedImage: false) { request in
            Self.response(request, status: 503)
        }

        XCTAssertTrue(
            model.canEditPositions,
            "the revision-bound topo URL owns bitmap transfer; its precise overlay remains editable"
        )
        model.enterEdit()
        model.move(shotId: "shot-1", px: [63, 41])

        XCTAssertEqual(model.map.shots.first?.end, [63, 41])
        XCTAssertTrue(model.hasUnsavedChanges)
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

    // MARK: B3 同屏改杆

    func testTapAddGoesAfterTheSelectedShotAndGuessesTheClubFromTheDistance() {
        let model = makeModel(ppm: 0.5) { request in Self.response(request, status: 503) }
        model.enterEdit()
        model.selectedShotId = "shot-1"

        // shot-1 lands at [40, 65]; 65 px at 0.5 px/m is 130 m = 142 yd → 八号铁 (140).
        let added = model.addShot(px: [40, 0], afterShotId: model.selectedShotId)

        XCTAssertEqual(model.map.shots.map(\.id), ["shot-1", added, "shot-2"])
        XCTAssertEqual(model.map.shots.map(\.order), [1, 2, 3])
        XCTAssertEqual(model.map.shots[1].start, [40, 65])
        XCTAssertEqual(model.map.shots[2].start, [40, 0])
        XCTAssertEqual(model.map.shots[1].club, "八号铁")
        XCTAssertNil(model.map.shots[1].clubSource, "a guessed club is not a confirmed edit")
        XCTAssertEqual(model.yards(of: added), 142)
        XCTAssertEqual(model.selectedShotId, added)
    }

    func testClubGuessPicksTheNearestTypicalCarryAndListsItFirst() {
        XCTAssertEqual(RoundClubGuess.club(forYards: 228), "一号木")
        XCTAssertEqual(RoundClubGuess.club(forYards: 152), "七号铁")
        XCTAssertEqual(RoundClubGuess.club(forYards: 40), "LW")
        XCTAssertNil(RoundClubGuess.club(forYards: nil))
        let ordered = RoundClubGuess.orderedClubs(guess: "七号铁", current: "1W", clubs: ["一号木", "七号铁", "PW"])
        XCTAssertEqual(ordered.first, "七号铁")
        XCTAssertEqual(Set(ordered), ["一号木", "七号铁", "P 杆"])
    }

    func testOrderArrowsMoveOneShotOnePlaceAndRenumber() {
        let model = makeModel { request in Self.response(request, status: 503) }
        model.enterEdit()

        model.moveShot("shot-1", by: -1)
        XCTAssertFalse(model.hasUnsavedChanges, "the first shot cannot move earlier")

        model.moveShot("shot-1", by: 1)
        XCTAssertEqual(model.map.shots.map(\.id), ["shot-2", "shot-1"])
        XCTAssertEqual(model.map.shots.map(\.order), [1, 2])
        XCTAssertEqual(model.map.shots[0].start, [50, 95], "the new first shot starts at the tee")
        XCTAssertEqual(model.map.shots[1].start, model.map.shots[0].end)
        XCTAssertEqual(model.selectedShotId, "shot-1")
        XCTAssertTrue(model.hasUnsavedChanges)
    }

    func testDeletingRenumbersTheRemainingShots() {
        let model = makeModel { request in Self.response(request, status: 503) }
        model.enterEdit()
        model.selectedShotId = "shot-1"

        model.delete(shotId: "shot-1")

        XCTAssertEqual(model.map.shots.map(\.id), ["shot-2"])
        XCTAssertEqual(model.map.shots.map(\.order), [1])
        XCTAssertEqual(model.map.shots[0].start, [50, 95])
        XCTAssertNil(model.selectedShotId)
    }

    func testPuttsOnlySavePostsOnePuttCorrectionAndNoShotSnapshot() async throws {
        var paths: [String] = []
        var annotation: [String: Any] = [:]
        let model = makeModel(putts: 2, now: { Date(timeIntervalSince1970: 1_790_000_000) }) { request in
            if request.httpMethod == "POST" {
                paths.append(request.url?.path ?? "")
                let body = try CapturingURLProtocol.requestBodyData(from: request)
                annotation = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
                return Self.response(request, status: 201, body: #"{"schema":"ai-caddie-annotation-create-v1"}"#)
            }
            return Self.response(request, status: 503)
        }

        model.enterEdit()
        model.adjustPutts(by: 1)
        XCTAssertEqual(model.putts, 3)
        XCTAssertTrue(model.hasUnsavedChanges)
        let saved = await model.save()

        XCTAssertTrue(saved)
        XCTAssertEqual(paths, ["/api/v2/annotations"])
        XCTAssertEqual(annotation["targetType"] as? String, "hole")
        XCTAssertEqual(annotation["targetId"] as? String, "round-1:4")
        XCTAssertEqual(annotation["kind"] as? String, "putt_correction")
        let payload = try XCTUnwrap(annotation["payload"] as? [String: Any])
        XCTAssertEqual(payload["to"] as? Int, 3)
        XCTAssertEqual(payload["from"] as? Int, 2)
        XCTAssertFalse((annotation["clientMutationId"] as? String ?? "").isEmpty)
        XCTAssertEqual(annotation["clientTime"] as? String, "2026-09-21T14:13:20Z")
        XCTAssertEqual(model.putts, 3)
        XCTAssertFalse(model.hasUnsavedChanges)
    }

    func testPuttsAndPenaltyStayInBounds() {
        let model = makeModel(putts: nil) { request in Self.response(request, status: 503) }
        model.enterEdit()
        model.adjustPutts(by: -1)
        XCTAssertEqual(model.putts, 0, "an unrecorded count starts from zero")
        for _ in 0..<20 { model.adjustPutts(by: 1) }
        XCTAssertEqual(model.putts, RoundEditModel.maximumPutts)
        model.adjustPenalty(by: -1)
        XCTAssertEqual(model.map.manualPenalty, 0)
        model.adjustPenalty(by: 2)
        XCTAssertEqual(model.map.manualPenalty, 2)
        model.cancelEdit()
        XCTAssertNil(model.putts)
        XCTAssertEqual(model.map.manualPenalty, 0)
    }

    func testShotAndPuttSaveRetryReusesBothIdempotencyKeysAndSendsClientTime() async throws {
        var corrections: [[String: Any]] = []
        var annotations: [[String: Any]] = []
        var failAnnotation = true
        let model = makeModel(putts: 2, now: { Date(timeIntervalSince1970: 1_790_000_000) }) { request in
            guard request.httpMethod == "POST" else { return Self.response(request, status: 503) }
            let body = try CapturingURLProtocol.requestBodyData(from: request)
            let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
            if request.url?.path == "/api/v2/annotations" {
                annotations.append(json)
                if failAnnotation {
                    failAnnotation = false
                    return Self.response(request, status: 503)
                }
            } else {
                corrections.append(json)
            }
            return Self.response(request, status: 201, body: #"{"stored":{}}"#)
        }

        model.enterEdit()
        model.editClub(shotId: "shot-2", "八号铁")
        model.adjustPutts(by: -1)
        let first = await model.save()
        XCTAssertFalse(first)
        XCTAssertTrue(model.isEditing)
        let retry = await model.save()

        XCTAssertTrue(retry)
        XCTAssertEqual(corrections.count, 2)
        XCTAssertEqual(annotations.count, 2)
        XCTAssertEqual(corrections[0]["clientMutationId"] as? String, corrections[1]["clientMutationId"] as? String)
        XCTAssertEqual(annotations[0]["clientMutationId"] as? String, annotations[1]["clientMutationId"] as? String)
        XCTAssertEqual(corrections[0]["clientTime"] as? String, "2026-09-21T14:13:20Z")
        XCTAssertEqual(corrections[0]["op"] as? String, "replaceHoleShots")
    }

    private func makeModel(
        shots: [RoundShot]? = nil,
        includeMap: Bool = true,
        includeEmbeddedImage: Bool = true,
        geometryRevision: String? = "geometry-r1",
        ppm: Double = 1,
        putts: Int? = nil,
        now: @escaping () -> Date = Date.init,
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> RoundEditModel {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        CapturingURLProtocol.requestHandler = handler
        let courseMap = CoursePrepMap(
            image: includeEmbeddedImage ? "data:image/png;base64,AA==" : nil,
            overlay: CoursePrepOverlay(
                w: 100,
                h: 100,
                ppm: ppm,
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
            roundRef: "round-1",
            putts: putts,
            now: now
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
