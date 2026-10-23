import Foundation
@testable import AICaddie

enum ProductInputs {
    static func package() throws -> LiveRoundPackage {
        try ProductLoopMapTests.template(.init(globalId: 81001, holeCount: 18, venue: "Example", name: "Example"))
    }

    static func prep(coverage: String = "ready", route: Bool = true, scale: Double = 1) throws -> CoursePrepHole {
        var input: [String: Any] = [
            "hole": 1, "par": 4, "par_source": "synthetic", "blue_yards": 328, "route_len_m": 300,
            "geometryCoverage": coverage, "geometryRevision": "synthetic-r1",
            "route": route ? [[100.0, 350.0], [100.0, 50.0]] : [],
            "steps": [], "cautions": [], "hazards": ["water_carry": [], "bunkers": [], "details": []],
        ]
        if route {
            input["map"] = ["overlay": [
                "w": Int(300 * scale), "h": Int(400 * scale), "ppm": scale, "ln": 300,
                "route": [[100 * scale, 350 * scale, 0], [100 * scale, 50 * scale, 300]],
            ]]
        }
        return try ProductSharedVectors.decode(input)
    }

    static func shotMap() throws -> RoundHoleShotMap {
        RoundHoleShotMap(
            found: true, hole: 1, par: 4, globalId: 81001, localHole: 1,
            geometryRevision: "synthetic-r1", mapKind: "prodgeometry", map: try prep().map,
            shots: [
                RoundShot(shotId: "s1", start: [100, 350], end: [100, 200], club: "7I", lie: "tee", endLie: "fairway", order: 1),
                RoundShot(shotId: "s2", start: [100, 200], end: [100, 50], club: "7I", lie: "fairway", endLie: "green", order: 2),
            ]
        )
    }

    static func course(_ id: Int, venue: String, holes: Int = 9, latitude: Double? = nil) -> MobileCourseOption {
        MobileCourseOption(globalId: id, name: venue, holes: holes, venueName: venue,
                           latitude: latitude, longitude: latitude == nil ? nil : 0)
    }

    static func card(_ id: String) throws -> HistoryRoundCard {
        try ProductSharedVectors.decode([
            "id": id, "courseName": "Example", "holesCompleted": 9, "score": 40, "par": 36,
            "scoreStrip": [["hole": 1, "score": 5, "par": 4, "toPar": 1]],
        ])
    }
}
