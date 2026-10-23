import Foundation
import XCTest
@testable import AICaddie

/// 4.3: every slot, physical identity and display number must match the hand-written table.
/// Templates contain only synthetic input holes; no expected row is used to build them.
final class ProductLoopMapTests: XCTestCase {
    private struct Document: Decodable {
        let schemaVersion: Int
        let holeColumns: [String]
        let courses: [InputCourse]
        let cases: [Vector]
    }

    struct InputCourse: Decodable {
        let globalId: Int
        let holeCount: Int
        let venue: String
        let name: String
    }

    private struct Vector: Decodable {
        let id: String
        let loops: String
        let expectedLoopKey: String
        let expectedHoles: [[Int]]
    }

    func test_j4_3_offline_composition_matches_shared_hole_tables() throws {
        let document: Document = try ProductSharedVectors.read("loop_map")
        XCTAssertEqual(document.schemaVersion, 1)
        XCTAssertEqual(document.holeColumns, ["number", "sourceGlobalId", "sourceLocalHole", "courseHoleNumber"])
        XCTAssertFalse(document.cases.isEmpty)
        let templates = try Dictionary(uniqueKeysWithValues: document.courses.map {
            ($0.globalId, try Self.template($0))
        })
        for vector in document.cases {
            let entries = try XCTUnwrap(
                RoundLoopEntry.entries(loopKey: vector.loops.replacingOccurrences(of: ",", with: "+")),
                vector.id
            )
            let package = try XCTUnwrap(LiveRoundPackage.projecting(
                entries, templates: templates, roundId: "product-\(vector.id)"
            ), vector.id)
            XCTAssertEqual(package.loopKey, vector.expectedLoopKey, vector.id)
            XCTAssertEqual(rows(package), vector.expectedHoles, vector.id)
            XCTAssertNoThrow(try package.validatedRoundIdentity(), vector.id)

            // The same operation at the turn must also reproduce the independent table.
            if entries.count == 2 {
                let first = try XCTUnwrap(LiveRoundPackage.projecting(
                    [entries[0]], templates: templates, roundId: "turn-\(vector.id)"
                ), vector.id)
                let secondTemplate = try XCTUnwrap(templates[entries[1].globalId], vector.id)
                let composed = try XCTUnwrap(first.composingSecondLoop(
                    entries[1], from: secondTemplate, roundId: first.roundId
                ), vector.id)
                XCTAssertEqual(composed.loopKey, vector.expectedLoopKey, vector.id)
                XCTAssertEqual(rows(composed), vector.expectedHoles, vector.id)
            }
        }
    }

    private func rows(_ package: LiveRoundPackage) -> [[Int]] {
        package.holes.map { [$0.number, $0.sourceGlobalId, $0.sourceLocalHole, $0.courseHoleNumber] }
    }

    static func template(_ course: InputCourse) throws -> LiveRoundPackage {
        let loops: [[String: Any]] = course.holeCount == 18 ? [
            ["globalId": course.globalId, "half": "front", "roundStartHole": 1, "sourceStartHole": 1, "holeCount": 9],
            ["globalId": course.globalId, "half": "back", "roundStartHole": 10, "sourceStartHole": 10, "holeCount": 9],
        ] : [
            ["globalId": course.globalId, "half": "all", "roundStartHole": 1, "sourceStartHole": 1, "holeCount": 9],
        ]
        let key = course.holeCount == 18
            ? "\(course.globalId):front+\(course.globalId):back" : "\(course.globalId):all"
        let input: [String: Any] = [
            "schema": "ai-caddie-live-round-package-v2",
            "roundId": "template-\(course.globalId)", "dataMode": "fixture",
            "sourceCoverage": [
                "state": "ready", "dataMode": "fixture", "requestedRoundId": "template",
                "roundFound": false, "availableRoundCount": 0,
                "holeCount": course.holeCount, "clubProfileCount": 0,
            ],
            "missingData": [],
            "playerProfile": ["playerId": "synthetic", "displayName": "Synthetic", "handedness": "right"],
            "course": ["globalId": course.globalId, "name": course.name, "venueName": course.venue, "teeBox": "blue"],
            "holes": (1...course.holeCount).map { number in
                ["number": number, "par": 4, "geometryCoverage": "missing",
                 "sourceGlobalId": course.globalId, "sourceLocalHole": number, "courseHoleNumber": number] as [String: Any]
            },
            "roundLoops": loops, "loopKey": key,
            "geometryCoverage": ["state": "missing", "readyHoles": 0, "totalHoles": course.holeCount],
            "readinessChecks": [], "caddieContextSeeds": [],
            "weatherSnapshot": ["schema": "ai-caddie-weather-snapshot-v1", "state": "missing", "source": "missing", "confidence": "low", "missingData": []],
            "clubProfiles": [], "caddieDecisionEndpoint": "/api/v2/caddie/decision",
            "offlinePackageStatus": [
                "state": "ready", "preparedAt": "2026-10-01T00:00:00Z", "expiresAt": "2026-11-01T00:00:00Z",
                "cachePolicy": ["staleAfterHours": 24, "expiresAfterHours": 744],
            ],
            "eventCursor": ["serverSequence": 0, "pendingEventCount": 0],
            "recentHistory": [
                "course": ["courseKey": "synthetic", "roundCount": 0, "recentScores": [], "roundIds": []], "holes": [],
            ],
            "cachedCaddieRules": ["decisionContract": "ai-caddie-decision-v2", "offlineCapable": true, "requiredInputs": [], "degradeWhenMissing": []],
            "generatedAt": "2026-10-01T00:00:00Z",
        ]
        let result: LiveRoundPackage = try ProductSharedVectors.decode(input)
        return try result.validatedRoundIdentity()
    }
}
