import XCTest
@testable import AICaddie

final class ProductWatchHandoffTests: XCTestCase {
    func test_j6_2_phone_snapshots_replace_hole_ranges_and_clear_absent_advice() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let bridge = WatchEventBridge(offlineStore: OfflineStore(directoryURL: directory), autoActivate: false)
        let package = try ProductInputs.package()
        let first = try XCTUnwrap(package.holes.first)
        let second = try XCTUnwrap(package.holes.first { $0.number == 2 })
        let option: [String: Any] = [
            "id": "stock", "clubName": "7I", "carry_m": 150,
            "dispersion": ["state": "modeled", "clubName": "7I", "carryP10_m": 140, "carryP90_m": 160, "sampleSize": 20],
        ]
        let advice: CaddieDecisionResponse = try ProductSharedVectors.decode([
            "schema": "ai-caddie-decision-v2", "decisionId": "synthetic-decision", "sourceRef": "product:profile",
            "evidenceRefs": ["product:profile"], "shotType": "tee", "phase": "tee",
            "context": ["source": "ios_live", "currentLocation": ["latitude": 0, "longitude": 0,
                "horizontalAccuracyM": 5, "capturedAt": "2026-10-23T00:00:00Z"]],
            "options": [option], "selectedOption": option, "selectedOptionId": "stock",
            "avoidZones": [], "forbiddenZones": [], "acceptableMiss": [:], "evidence": [],
            "confidence": ["level": "medium"], "missingData": [], "auditCriteria": [],
        ])
        let connected = bridge.makeWatchRoundStatePayload(package: package, hole: first, score: 4, putts: 2,
            penaltyCount: 0, selectedClub: nil, decision: advice, frontGreenM: 100, centerGreenM: 110, backGreenM: 120)
        XCTAssertEqual(connected.suggestedClub, "7I", "real previous recommendation exists before clearing")
        XCTAssertNotNil(connected.rootCaddieRecommendation)
        XCTAssertFalse(connected.caddieOptions.isEmpty)
        var revision = try XCTUnwrap(connected.snapshotRevision)
        // Hand-written transport facts. A fresh hole never inherits any missing previous field.
        let rows: [(String, Hole, Double?, Double?, Double?, Double?)] = [
            ("connected", first, 100, 110, 120, 115),
            ("no-live-facts", first, nil, nil, nil, nil),
            ("reconnected-new-hole", second, 200, 210, 220, 218),
        ]
        for (id, hole, front, middle, back, slope) in rows {
            let state = bridge.makeWatchRoundStatePayload(package: package, hole: hole, score: 4, putts: 2, penaltyCount: 0,
                selectedClub: nil, decision: nil, distanceToPinM: middle,
                frontGreenM: front, centerGreenM: middle, backGreenM: back,
                playsLikeDistanceM: slope, elevationDeltaM: slope == nil ? nil : 5)
            let bytes = try JSONEncoder().encode(state)
            let restored = try JSONDecoder().decode(WatchRoundStatePayload.self, from: bytes)
            XCTAssertGreaterThan(try XCTUnwrap(restored.snapshotRevision), revision, id + " newer replaces prior snapshot")
            revision = try XCTUnwrap(restored.snapshotRevision)
            XCTAssertEqual(restored.roundId, package.roundId, id)
            XCTAssertEqual(restored.hole, hole.number, id)
            XCTAssertEqual(restored.frontGreenM, front, id)
            XCTAssertEqual(restored.centerGreenM, middle, id)
            XCTAssertEqual(restored.backGreenM, back, id)
            XCTAssertEqual(restored.playsLikeDistanceM, slope, id)
            XCTAssertNil(restored.suggestedClub, id)
            XCTAssertNil(restored.rootCaddieRecommendation, id)
            XCTAssertTrue(restored.caddieOptions.isEmpty, id)
        }
    }
}
