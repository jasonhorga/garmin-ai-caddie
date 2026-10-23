import XCTest
@testable import AICaddieWatch

/// C16f product vectors for the Watch-facing parts of 4.5 and 5.1.
/// The expected rows below are hand calculated from the shared C16c vectors; they are
/// deliberately not produced by the objects under test.
final class WatchC16fSharedRulesTests: XCTestCase {
    func testWatchCaddiePlansKeepThreeDistinctRoutesAndMeasuredOffsets() {
        let options = [
            WatchCaddieOption(
                optionId: "safe", label: "safe",
                plan: [
                    WatchCaddiePlanStep(clubName: "9I", carryM: 100, routeOffsetM: 100, planIndex: 0),
                    WatchCaddiePlanStep(clubName: "9I", carryM: 100, routeOffsetM: 200, planIndex: 1),
                    WatchCaddiePlanStep(clubName: "9I", carryM: 100, routeOffsetM: 300, planIndex: 2),
                ], confidence: "offline", routeOffsetBasis: .tee
            ),
            WatchCaddieOption(
                optionId: "stock", label: "stock",
                plan: [
                    WatchCaddiePlanStep(clubName: "6I", carryM: 150, routeOffsetM: 150, planIndex: 0),
                    WatchCaddiePlanStep(clubName: "6I", carryM: 150, routeOffsetM: 300, planIndex: 1),
                ], confidence: "offline", routeOffsetBasis: .tee
            ),
            WatchCaddieOption(
                optionId: "attack", label: "attack",
                plan: [
                    WatchCaddiePlanStep(clubName: "3W", carryM: 200, routeOffsetM: 200, planIndex: 0),
                    WatchCaddiePlanStep(clubName: "9I", carryM: 100, routeOffsetM: 300, planIndex: 1),
                ], confidence: "offline", routeOffsetBasis: .tee
            ),
        ]
        let expected: [(String, [String], [Double], [Int])] = [
            ("safe", ["9I", "9I", "9I"], [100, 200, 300], [0, 1, 2]),
            ("stock", ["6I", "6I"], [150, 300], [0, 1]),
            ("attack", ["3W", "9I"], [200, 300], [0, 1]),
        ]

        for (option, row) in zip(options, expected) {
            XCTAssertEqual(option.id, row.0)
            XCTAssertEqual(option.plan?.map(\.clubName), row.1)
            XCTAssertEqual(option.plan?.compactMap(\.routeOffsetM), row.2)
            XCTAssertEqual(option.plan?.compactMap(\.planIndex), row.3)
        }
        XCTAssertEqual(options.map { $0.plan?.last?.routeOffsetM }, [300, 300, 300])
        XCTAssertNotEqual(options[0].plan?.map(\.clubName), options[1].plan?.map(\.clubName))
        XCTAssertNotEqual(options[1].plan?.map(\.clubName), options[2].plan?.map(\.clubName))
    }

    func testWatchDistanceBoundaryUsesYardsAndLeavesPlaysLikeMissingWhenFactsAreMissing() {
        XCTAssertEqual(WatchUnits.yards(100), 109)
        XCTAssertEqual(WatchUnits.yards(300), 328)
        XCTAssertEqual(WatchUnits.playsLikeMetres(distanceMetres: 150, elevationDeltaMetres: 6), 156)
        XCTAssertNil(WatchUnits.playsLikeMetres(distanceMetres: 150, elevationDeltaMetres: nil))
    }

    func testWatchLoopIdentityPreservesAllFourOrderedHalfStarts() {
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
