import Foundation
@testable import AICaddie

/// Test-only views of `AICaddie/Fixtures/live_round_package.fixture.json`.
///
/// The shared fixture is a contract-valid v2 package: the front nine (`31795:front`) of the
/// fixture world's 18-hole course 31795 — round holes 1–9 are physical holes 1–9, each with its
/// own caddie seed and recent-history row. Unit tests that model something else derive it here,
/// at the JSON level, so every derivation stays a decodable package.
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

    /// Only round hole 1 (with its seed and history row) as a one-hole `G:all` test table — the
    /// shape older store / sync / prep tests were written against (one topo asset, one install
    /// row). iOS does not validate the loop table; the server never emits this shape.
    static func singleHole(dataMode: String? = nil) throws -> LiveRoundPackage {
        var root = try object(dataMode: dataMode)
        let globalId = try courseGlobalId(root)
        let roundId = root["roundId"] as? String ?? ""
        root["holes"] = try rows(root["holes"], key: "holes").filter { ($0["number"] as? Int) == 1 }
        root["caddieContextSeeds"] = try rows(root["caddieContextSeeds"], key: "caddieContextSeeds")
            .filter { ($0["hole"] as? Int) == 1 }
        if var history = root["recentHistory"] as? [String: Any] {
            history["holes"] = try rows(history["holes"], key: "recentHistory.holes")
                .filter { ($0["number"] as? Int) == 1 }
            root["recentHistory"] = history
        }
        if var coverage = root["sourceCoverage"] as? [String: Any] {
            coverage["holeCount"] = 1
            root["sourceCoverage"] = coverage
        }
        root["readinessChecks"] = try rows(root["readinessChecks"], key: "readinessChecks").map {
            (check: [String: Any]) -> [String: Any] in
            guard (check["label"] as? String) == "caddie_seeds" else { return check }
            var narrowed = check
            narrowed["ready"] = 1
            narrowed["total"] = 1
            narrowed["reason"] = "1/1 holes have cached caddie context seeds and offline options"
            narrowed["sourceRefs"] = ["\(roundId):1"]
            return narrowed
        }
        root["roundLoops"] = [loopRow(globalId: globalId, half: "all", holeCount: 1)]
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

    private static func rows(_ value: Any?, key: String) throws -> [[String: Any]] {
        guard let rows = value as? [[String: Any]] else { throw FixtureError.malformed(key) }
        return rows
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
