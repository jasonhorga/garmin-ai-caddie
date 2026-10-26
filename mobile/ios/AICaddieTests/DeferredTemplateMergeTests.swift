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
        json["recentHistory"] = ["course": ["courseKey": "fixture", "roundCount": 0, "recentScores": [], "roundIds": []], "rounds": [], "holes": []]
        // A later map response changes par to 5 and has no personal projection (C91 / #426).
        var holes = try XCTUnwrap(json["holes"] as? [[String: Any]])
        holes[0]["par"] = 5
        json["holes"] = holes
        json["generatedAt"] = "2099-01-01T00:00:00Z"
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
            XCTAssertEqual(saved.eventCursor, original.eventCursor)
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
}
