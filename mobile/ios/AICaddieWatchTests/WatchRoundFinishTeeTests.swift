import Foundation
import XCTest
import AICaddieDomain
@testable import AICaddieWatch

@MainActor
final class WatchRoundFinishTeeTests: XCTestCase {
    /// Promise: standalone cached-course rounds upload their opening Tee without a phone or
    /// server package binding. Both immediate finish and disk-backed retry use the same wire field.
    func testStandaloneFinishUploadsOpeningTee() async throws {
        try await checkFinish(tee: "White", deferred: false)
    }

    func testDeferredFinishUploadsOpeningTeeAfterRelaunch() async throws {
        try await checkFinish(tee: "Red", deferred: true)
    }

    /// Promise: older Watch rounds with no saved Tee must not claim they were played from Blue.
    func testLegacyFinishDoesNotInventTee() async throws {
        try await checkFinish(tee: nil, deferred: true)
    }

    private func checkFinish(tee: String?, deferred: Bool) async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = WatchRoundStore(directoryURL: directory)
        var bodies: [Data] = []
        let client = WatchBackendClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            dataLoader: { request in
                XCTAssertEqual(request.httpMethod, "POST")
                XCTAssertEqual(request.url?.path, "/api/v2/mobile/rounds/standalone-round/finish")
                bodies.append(try XCTUnwrap(request.httpBody))
                return (Data("{}".utf8), HTTPURLResponse(
                    url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil, headerFields: nil
                )!)
            },
            retrySleep: { _ in XCTFail("successful finish must not retry") }
        )
        var eventNumber = 0
        let makeEventId = { eventNumber += 1; return "event-\(eventNumber)" }
        let finish: (String, WatchRoundFinishMetadata) async throws -> Void = { roundId, metadata in
            try await client.finishRound(roundId: roundId, metadata: metadata)
        }
        let model = WatchRoundModel(
            store: store, makeEventId: makeEventId, now: { "2026-08-09T00:00:00Z" },
            uploader: { events, _ in
                if deferred { throw URLError(.notConnectedToInternet) }
                return events.map(\.eventId)
            },
            finisher: finish
        )
        let rows = try XCTUnwrap(WatchCourseSelection.roundRows(loopKey: "31795:all"))
        let holes = rows.map { row in
            WatchRoundState(
                roundId: "standalone-round", hole: row.number, par: 4, distanceM: nil,
                selectedClub: nil, globalId: row.globalId, sourceLocalHole: row.sourceLocalHole,
                courseHoleNumber: row.courseHoleNumber, score: 0, putts: 0, penaltyCount: 0,
                caddieConfidence: "offline"
            )
        }
        model.seedRound(holes, courseName: "Fixture Links", courseGlobalId: 31795,
                        teeBox: tee, loopKey: "31795:all")
        XCTAssertNotNil(model.round)
        model.startScoringActiveHole()
        model.saveActiveHole()
        model.requestFinish()
        model.requestFinishConfirmation()
        await model.confirmFinish()
        XCTAssertNil(model.round)
        if deferred {
            XCTAssertTrue(bodies.isEmpty)
            XCTAssertEqual(store.loadDeferredFinishes().count, 1)
            let reopened = WatchRoundStore(directoryURL: directory)
            let relaunched = WatchRoundModel(
                store: reopened, now: { "2026-08-09T00:01:00Z" },
                uploader: { events, _ in events.map(\.eventId) }, finisher: finish
            )
            await relaunched.retryDeferredFinishes()
            XCTAssertTrue(reopened.loadDeferredFinishes().isEmpty)
            XCTAssertNil(relaunched.round)
        }
        XCTAssertEqual(bodies.count, 1)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(bodies.first)) as? [String: Any])
        let meta = try XCTUnwrap(body["meta"] as? [String: Any])
        XCTAssertEqual(meta["teeBox"] as? String, tee, "finish must retain the opening Tee, including its absence")
        if tee == nil { XCTAssertNil(meta["teeBox"]) }
        XCTAssertEqual(meta["holesCompleted"] as? Int, 1)
        XCTAssertEqual(meta["courseGlobalId"] as? Int, 31795)
    }
}
