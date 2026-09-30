import Foundation
@testable import AICaddie

/// Test-only views of `AICaddie/Fixtures/live_round_package.fixture.json`.
///
/// The shared fixture is a contract-valid v2 package: the front nine (`31795:front`) of the
/// fixture world's 18-hole course 31795 — round holes 1–9 are physical holes 1–9, each with its
/// own caddie seed and recent-history row. Unit tests that model something else derive it here,
/// at the JSON level, so every derivation stays a decodable package. Every derivation is also a
/// contract-valid v2 round identity (whole nine-hole loops): OfflineStore validates each package it
/// writes or reads, so a narrowed one- or two-hole table can no longer be stored.
enum LiveRoundPackageFixture {
    enum FixtureError: Error {
        case malformed(String)
    }

    static var url: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
    }

    /// The fixture as shipped (nine holes, `31795:front`). `dataMode` overrides both the package
    /// and its source coverage (e.g. "local" for tests that exercise the course-template store,
    /// which never retains a fixture-mode package).
    static func package(dataMode: String? = nil) throws -> LiveRoundPackage {
        try decode(try object(dataMode: dataMode))
    }

    /// The same nine holes presented as a standalone 9-hole loop (`G:all`, holeCount 9). Round
    /// numbers, physical holes and `courseHoleNumber` are unchanged (1–9); only the loop table
    /// says "a 9-hole loop", so the package is its own whole-course template.
    static func nineHoleLoop(dataMode: String? = nil) throws -> LiveRoundPackage {
        var root = try object(dataMode: dataMode)
        let globalId = try courseGlobalId(root)
        root["roundLoops"] = [loopRow(globalId: globalId, half: "all", holeCount: 9)]
        root["loopKey"] = "\(globalId):all"
        return try decode(root)
    }

    private static func object(dataMode: String?) throws -> [String: Any] {
        let data = try Data(contentsOf: url)
        guard var root = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw FixtureError.malformed("root")
        }
        if let dataMode {
            root["dataMode"] = dataMode
            if var coverage = root["sourceCoverage"] as? [String: Any] {
                coverage["dataMode"] = dataMode
                root["sourceCoverage"] = coverage
            }
        }
        return root
    }

    private static func courseGlobalId(_ root: [String: Any]) throws -> Int {
        guard let course = root["course"] as? [String: Any],
              let globalId = course["globalId"] as? Int else {
            throw FixtureError.malformed("course.globalId")
        }
        return globalId
    }

    private static func loopRow(globalId: Int, half: String, holeCount: Int) -> [String: Any] {
        [
            "globalId": globalId,
            "half": half,
            "roundStartHole": 1,
            "sourceStartHole": 1,
            "holeCount": holeCount,
        ]
    }

    private static func decode(_ root: [String: Any]) throws -> LiveRoundPackage {
        let data = try JSONSerialization.data(withJSONObject: root)
        return try JSONDecoder().decode(LiveRoundPackage.self, from: data)
    }
}
