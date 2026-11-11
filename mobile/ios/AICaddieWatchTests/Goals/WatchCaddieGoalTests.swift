// size: medium
// goals: W-04, W-10
import CoreLocation
import Foundation
import XCTest
import WatchConnectivity
import AICaddieDomain
import AICaddieCore
@testable import AICaddieWatch

@MainActor
final class WatchCaddieGoalTests: XCTestCase {
    private final class Session: NSObject, WatchSessioning {
        var isSessionActivated = true
        var isCounterpartReachable = true
        var receivedContext: [String: Any] = [:]
        var sentContext: [String: Any] = [:]
        func activateSession() {}
        func send(_ message: [String: Any], onReply: (([String: Any]) -> Void)?, onError: ((Error) -> Void)?) {}
        func queueUserInfo(_ userInfo: [String: Any]) {}
        func replaceContext(_ context: [String: Any]) throws { sentContext = context }
    }
    private func makeModel(now: @escaping () -> String = { "2026-06-20T00:00:00Z" }) -> WatchRoundModel {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        addTeardownBlock { try? FileManager.default.removeItem(at: directory) }
        let model = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory),
            now: now
        )
        model.seedRound([WatchRoundState(
            roundId: "r1", hole: 1, par: 4, distanceM: 400, selectedClub: nil,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )])
        return model
    }

    private func state(
        decisionId: String,
        revision: Int64,
        options: [WatchCaddieOption] = [],
        recommendation: WatchRootCaddieRecommendation? = nil
    ) -> WatchRoundState {
        WatchRoundState(
            roundId: "r1", hole: 1, par: 4, distanceM: 400,
            suggestedClub: recommendation?.clubName,
            selectedClub: nil, decisionId: decisionId,
            holeMap: WatchHoleMap(
                w: 100, h: 100, you: [10, 90], pin: [90, 10], layup: [50, 50],
                apex: [50, 50], greenCtrl: [70, 30], route: [[0, 0, 0], [100, 100, 400]]
            ),
            caddieOptions: options,
            rootCaddieRecommendation: recommendation,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "high",
            snapshotRevision: revision
        )
    }

    // goals: W-04 [main]
    /// The caddie detail keeps only the remaining route legs, while the root page opens only for a
    /// current, accurate fix and a coherent live recommendation.
    func testCaddiePagesShareRemainingPlanAndFailClosedOnUntrustedFix() throws {
        let model = makeModel()
        let option = WatchCaddieOption(
            optionId: "stock", label: "标准", clubName: "1W", carryM: 220,
            carryP10M: 205, carryP90M: 235, sampleSize: 20,
            plan: [
                WatchCaddiePlanStep(clubName: "1W", carryM: 220, routeOffsetM: 220),
                WatchCaddiePlanStep(clubName: "8I", carryM: 140, routeOffsetM: 360),
            ], confidence: "high", routeOffsetBasis: .tee, originShotEventIds: []
        )
        let recommendation = WatchRootCaddieRecommendation(
            decisionId: "d1", clubName: "1W", aimCarryM: 220, carryP10M: 205,
            carryP90M: 235, sampleSize: 20, confidence: "high", source: "live",
            mode: "automatic", generatedAt: "2026-06-20T00:00:00Z",
            validUntil: "2026-06-20T00:00:12Z", originLatitude: 40.0,
            originLongitude: 116.0, originAccuracyM: 5, maximumMovementM: 25,
            evidenceCount: 2
        )
        model.receivePhoneState(state(decisionId: "d1", revision: 1, options: [option], recommendation: recommendation))

        XCTAssertEqual(model.currentCaddieOptions(progressM: 230).first?.plan?.map(\.clubName), ["8I"])
        XCTAssertTrue(model.rootCaddieLayerAvailable(at: WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.0, longitude: 116.0),
            horizontalAccuracyM: 5, capturedAt: "2026-06-20T00:00:00Z"
        )))
        XCTAssertFalse(model.rootCaddieLayerAvailable(at: nil))
        XCTAssertFalse(model.rootCaddieLayerAvailable(at: WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.001, longitude: 116.0),
            horizontalAccuracyM: 5, capturedAt: "2026-06-20T00:00:00Z"
        )))
    }

    // goals: W-10 [main]
    /// Without another phone refresh, the live recommendation disappears at its expiry even with
    /// a fresh Watch fix. A stale or inaccurate fix also keeps it hidden inside the validity window.
    func testRecommendationExpiresWithoutAnotherPhoneRefresh() {
        var currentTime = "2026-06-20T00:00:00Z"
        let model = makeModel(now: { currentTime })
        let recommendation = WatchRootCaddieRecommendation(
            decisionId: "d1", clubName: "1W", aimCarryM: 220, carryP10M: 205,
            carryP90M: 235, sampleSize: 20, confidence: "high", source: "live",
            mode: "automatic", generatedAt: "2026-06-20T00:00:00Z",
            validUntil: "2026-06-20T00:00:12Z", originLatitude: 40.0,
            originLongitude: 116.0, originAccuracyM: 5, maximumMovementM: 25,
            evidenceCount: 2
        )
        model.receivePhoneState(state(decisionId: "d1", revision: 1, recommendation: recommendation))
        let cases: [(String, String, Double, Bool)] = [
            ("2026-06-20T00:00:11Z", "2026-06-20T00:00:11Z", 5, true),
            ("2026-06-20T00:00:12Z", "2026-06-20T00:00:12Z", 5, false),
            ("2026-06-20T00:00:13Z", "2026-06-20T00:00:13Z", 5, false),
            ("2026-06-20T00:00:11Z", "2026-06-19T23:59:55Z", 5, false),
            ("2026-06-20T00:00:11Z", "2026-06-20T00:00:11Z", 16, false),
        ]
        for (time, capturedAt, accuracy, expected) in cases {
            currentTime = time
            let fix = WatchLocationFix(
                coordinate: CLLocationCoordinate2D(latitude: 40.0, longitude: 116.0),
                horizontalAccuracyM: accuracy, capturedAt: capturedAt
            )
            XCTAssertEqual(model.rootCaddieLayerAvailable(at: fix), expected,
                           "now=\(time), capturedAt=\(capturedAt), accuracy=\(accuracy)")
        }
    }

    // goals: W-10
    /// A delayed phone snapshot cannot restore an older recommendation after a newer one arrived.
    func testOlderPhoneRecommendationIsIgnoredAfterARefresh() {
        let model = makeModel()
        let fresh = WatchCaddieOption(optionId: "fresh", label: "标准", clubName: "7I", plan: nil)
        let stale = WatchCaddieOption(optionId: "stale", label: "旧", clubName: "3W", plan: nil)
        let session = Session()
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let sync = WatchSyncClient(
            queueURL: directory.appendingPathComponent("events.json"),
            holeImageStore: WatchHoleImageStore(directoryURL: directory.appendingPathComponent("images")),
            courseStore: WatchCourseStore(directoryURL: directory.appendingPathComponent("courses")),
            session: session
        )
        let freshState = state(decisionId: "fresh", revision: 2, options: [fresh])
        let staleState = state(decisionId: "stale", revision: 1, options: [stale])
        let object: (WatchRoundState) throws -> [String: Any] = { value in
            try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(value)) as? [String: Any])
        }
        sync.session(WCSession.default, didReceiveMessage: ["state": try! object(freshState)])
        model.receivePhoneState(try! XCTUnwrap(sync.currentState))
        sync.session(WCSession.default, didReceiveUserInfo: ["state": try! object(staleState)])
        model.receivePhoneState(try! XCTUnwrap(sync.currentState))
        XCTAssertEqual(model.activeHoleState?.decisionId, "fresh")
        XCTAssertEqual(model.currentCaddieOptions(progressM: nil).map(\.optionId), ["fresh"])
    }
}
