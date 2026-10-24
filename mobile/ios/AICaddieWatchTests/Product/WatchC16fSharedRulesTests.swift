import XCTest
@testable import AICaddieWatch

/// C16f product vectors for Watch 4.5 and the Watch side of 5.1.
final class WatchC16fSharedRulesTests: XCTestCase {
    func test_4_5_watch_map_degradation_rows() {
        let rows: [(String, WatchHoleRootPresentation)] = [
            ("precise geometry", .map),
            ("route-only while the package is pending", .mapPreparing),
            ("no geometry or distance", .scoreOnly),
        ]
        let actual: [WatchHoleRootPresentation] = [
            WatchHoleRootPresentation.resolve(hasQualifiedWristFix: false, hasGeometry: true, hasLiveCenterDistance: false),
            WatchHoleRootPresentation.resolve(hasQualifiedWristFix: false, hasGeometry: false, hasLiveCenterDistance: false, courseDataPending: true),
            WatchHoleRootPresentation.resolve(hasQualifiedWristFix: true, hasGeometry: false, hasLiveCenterDistance: false),
        ]
        for ((label, expected), result) in zip(rows, actual) {
            XCTAssertEqual(result, expected, label)
        }
    }

    func test_4_5_watch_map_upgrade_replaces_geometry_but_keeps_player_facts() {
        let baseMap = WatchHoleMap(w: 300, h: 200, you: [10, 20], pin: [250, 20], layup: [120, 20], apex: [80, 20], greenCtrl: [220, 20], route: [[10, 20, 0], [250, 20, 240]])
        let readyMap = WatchHoleMap(w: 600, h: 400, you: [20, 30], pin: [500, 30], layup: [250, 30], apex: [160, 30], greenCtrl: [450, 30], route: [[20, 30, 0], [500, 30, 240]])
        let base = WatchRoundState(
            roundId: "map-round", hole: 1, par: 4, distanceM: 180,
            targetNote: "落点右侧", targetLatitude: 40, targetLongitude: 116,
            targetKind: "layup", suggestedClub: "6I", selectedClub: "8I",
            holeMap: baseMap, geometryCoverage: "partial", score: 5, putts: 2,
            penaltyCount: 0, caddieConfidence: "medium"
        )
        let upgraded = WatchRoundState(
            roundId: "map-round", hole: 1, par: 4, distanceM: 170,
            suggestedClub: "7I", selectedClub: nil, holeMap: readyMap,
            geometryCoverage: "ready", geometryRevision: "release-2", score: 0,
            putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let result = base.applyingCourseMapUpgrade(upgraded)
        XCTAssertEqual(result.geometryCoverage, "ready")
        XCTAssertEqual(result.geometryRevision, "release-2")
        XCTAssertEqual(result.holeMap, readyMap)
        XCTAssertEqual(result.score, 5)
        XCTAssertEqual(result.putts, 2)
        XCTAssertEqual(result.selectedClub, "8I")
        XCTAssertEqual(result.targetNote, "落点右侧")
    }

    func test_5_1_watch_loop_identity_preserves_all_ordered_half_starts() {
        let course = WatchCourseOption(globalId: 81001, name: "Example Eighteen", holes: 18)
        let cases: [(String, String?, String, [Int], [Int])] = [
            ("front", nil, "81001:front", Array(1...9), Array(1...9)),
            ("back", nil, "81001:back", Array(10...18), Array(10...18)),
            ("front", "front", "81001:front+81001:front", Array(1...9) + Array(1...9), Array(1...9) + Array(1...9)),
            ("front", "back", "81001:front+81001:back", Array(1...9) + Array(10...18), Array(1...9) + Array(10...18)),
            ("back", "front", "81001:back+81001:front", Array(10...18) + Array(1...9), Array(10...18) + Array(1...9)),
            ("back", "back", "81001:back+81001:back", Array(10...18) + Array(10...18), Array(10...18) + Array(10...18)),
        ]

        for (first, second, key, physical, printed) in cases {
            let selection = WatchCourseSelection(
                front: course,
                teeBox: "blue",
                firstHalf: first,
                secondHalf: second
            )
            XCTAssertEqual(selection.loopKey, key)
            let rows = try! XCTUnwrap(WatchCourseSelection.roundRows(loopKey: key))
            XCTAssertEqual(rows.map(\.number), Array(1...rows.count))
            XCTAssertEqual(rows.map(\.sourceLocalHole), physical)
            XCTAssertEqual(rows.map(\.courseHoleNumber), printed)
        }

        let a = WatchCourseOption(globalId: 82001, name: "Example A", holes: 9, segmentHoles: 9)
        let b = WatchCourseOption(globalId: 82002, name: "Example B", holes: 9, segmentHoles: 9)
        let nine = WatchCourseSelection(front: a, back: b, teeBox: "white")
        XCTAssertEqual(nine.loopKey, "82001:all+82002:all")
        let nineRows = try! XCTUnwrap(WatchCourseSelection.roundRows(loopKey: nine.loopKey))
        XCTAssertEqual(nineRows.map(\.sourceLocalHole), Array(1...9) + Array(1...9))
        XCTAssertEqual(nineRows.map(\.courseHoleNumber), Array(1...18))
    }
}
