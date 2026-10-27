import Foundation
import XCTest
@testable import AICaddie

final class DeferredTemplateMergeTests: XCTestCase {
    func testDeferredPackageUpdatesMapsAndRetainsEveryPersonalField() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let full = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(full)) as? [String: Any])
        var coverage = try XCTUnwrap(json["sourceCoverage"] as? [String: Any])
        coverage["playerStatsWindow"] = "deferred"
        coverage["clubProfileCount"] = 0
        json["sourceCoverage"] = coverage
        json["clubProfiles"] = [] as [Any]
        json["caddieContextSeeds"] = [] as [Any]
        json["playerProfile"] = ["playerId": "player-1", "displayName": "Deferred", "handedness": "unknown"]
        json["recentHistory"] = ["course": ["courseKey": "fixture", "roundCount": 0, "recentScores": [Int](), "roundIds": [String]()] as [String: Any],
                                   "rounds": [[String: Any]](), "holes": [[String: Any]]()] as [String: Any]
        // A later map response changes par to 5 and has no personal projection (C91 / #426).
        var holes = try XCTUnwrap(json["holes"] as? [[String: Any]])
        holes[0]["par"] = 5
        json["holes"] = holes
        json["generatedAt"] = "2026-05-26T00:00:00Z"
        json["eventCursor"] = ["serverSequence": 9, "pendingEventCount": 0]
        json["weatherSnapshot"] = ["schema": "ai-caddie-weather-snapshot-v1", "state": "missing",
                                   "source": "deferred", "confidence": "low", "missingData": [[String: Any]]()] as [String: Any]
        json["cachedCaddieRules"] = ["decisionContract": "deferred", "offlineCapable": false,
                                     "requiredInputs": [String](), "degradeWhenMissing": [String]()] as [String: Any]
        json["caddieDecisionEndpoint"] = "/deferred"
        var missing = try XCTUnwrap(json["missingData"] as? [[String: Any]])
        missing.append(["label": "club_profiles", "reason": "personal enrichment deferred"])
        json["missingData"] = missing
        var checks = try XCTUnwrap(json["readinessChecks"] as? [[String: Any]])
        for index in checks.indices where (checks[index]["label"] as? String) == "club_profiles" {
            checks[index]["ready"] = 0
            checks[index]["state"] = "missing"
        }
        json["readinessChecks"] = checks
        let deferred = try JSONDecoder().decode(LiveRoundPackage.self, from: JSONSerialization.data(withJSONObject: json))
        try store.saveCourseTemplate(full)
        let original = try XCTUnwrap(store.loadCourseTemplate(globalId: 31795, teeBox: "blue"))

        // Both normal round writes and explicit template installs must preserve the personal half.
        for replace in [false, true] {
            if replace { try store.saveCourseTemplate(deferred, replacingExisting: true) }
            else { try store.saveRoundPackage(deferred) }
            let saved = try XCTUnwrap(store.loadCourseTemplate(globalId: 31795, teeBox: "blue"))
            XCTAssertEqual(saved.holes.first?.par, 5)
            XCTAssertEqual(saved.clubProfiles, original.clubProfiles)
            XCTAssertEqual(saved.caddieContextSeeds, original.caddieContextSeeds)
            XCTAssertEqual(saved.playerProfile, original.playerProfile)
            XCTAssertEqual(saved.recentHistory, original.recentHistory)
            XCTAssertEqual(saved.weatherSnapshot, original.weatherSnapshot)
            XCTAssertEqual(saved.cachedCaddieRules, original.cachedCaddieRules)
            XCTAssertEqual(saved.caddieDecisionEndpoint, original.caddieDecisionEndpoint)
            XCTAssertEqual(saved.eventCursor, deferred.eventCursor, "the cursor belongs to the new round")
            XCTAssertEqual(saved.missingData, original.missingData, "deferred club warnings do not invalidate retained clubs")
            XCTAssertEqual(saved.readinessChecks.sorted { $0.label < $1.label },
                           original.readinessChecks.sorted { $0.label < $1.label })
            XCTAssertEqual(saved.enrichmentState, original.enrichmentState)
            XCTAssertEqual(saved.sourceCoverage.clubProfileCount, original.sourceCoverage.clubProfileCount)
            XCTAssertEqual(saved.sourceCoverage.playerStatsWindow, original.sourceCoverage.playerStatsWindow)
        }
        let offline = try XCTUnwrap(store.loadCourseTemplate(globalId: 31795, teeBox: "blue"))
            .rebasedForOfflineStart(roundId: "next-offline", generatedAt: Date())
        XCTAssertFalse(offline.clubProfiles.isEmpty)
        XCTAssertEqual(Set(offline.caddieContextSeeds.map(\.hole)), Set(1...9))
        // The live map package must still ask for this round's fresh personal enrichment.
        XCTAssertEqual(try store.loadRoundPackage(roundId: full.roundId)?.sourceCoverage.playerStatsWindow, "deferred")
    }

    func testDeferredMapRefreshDropsSeedsOnlyForChangedGeometry() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let full = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(full)) as? [String: Any])
        var coverage = try XCTUnwrap(json["sourceCoverage"] as? [String: Any])
        coverage["playerStatsWindow"] = "deferred"
        json["sourceCoverage"] = coverage
        json["caddieContextSeeds"] = [] as [Any]
        let holes = try XCTUnwrap(json["holes"] as? [[String: Any]])
        json["holes"] = holes.enumerated().map { index, row in
            var copy = row
            if index == 0 { copy["geometryRevision"] = "changed-r2" }
            return copy
        }
        let maps = try JSONDecoder().decode(
            LiveRoundPackage.self,
            from: JSONSerialization.data(withJSONObject: json)
        )

        try store.saveCourseTemplate(full)
        try store.saveCourseTemplate(maps, replacingExisting: true)
        let saved = try XCTUnwrap(store.loadCourseTemplate(globalId: 31795, teeBox: "blue"))
        XCTAssertNil(saved.caddieContextSeeds.first(where: { $0.hole == 1 }))
        XCTAssertEqual(
            Set(saved.caddieContextSeeds.map(\.hole)),
            Set(2...9),
            "seeds remain usable where the geometry frame did not change"
        )
    }

    func testCompleteTemplateWinsWhenCoverageReadyCountIsStale() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let existing = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(existing)) as? [String: Any])
        json["generatedAt"] = "2099-01-01T00:00:00Z"
        json["geometryCoverage"] = [
            "state": "ready", "readyHoles": 0, "totalHoles": existing.holes.count,
        ] as [String: Any]
        let complete = try JSONDecoder().decode(
            LiveRoundPackage.self,
            from: JSONSerialization.data(withJSONObject: json)
        )
        XCTAssertTrue(complete.hasCompleteOfflineCoursePrep)

        try store.saveCourseTemplate(existing)
        try store.saveCourseTemplate(complete)
        let saved = try XCTUnwrap(store.loadCourseTemplate(globalId: 31795, teeBox: "blue"))
        XCTAssertEqual(saved.generatedAt, "2099-01-01T00:00:00Z")
    }
}
