import XCTest
@testable import AICaddieWatch

/// README §8: choose one factual nine-hole loop at opening; decide the second at the turn.
@MainActor
final class WatchRoundOpeningOptionsTests: XCTestCase {
    private func loop(_ id: Int, _ label: String) -> WatchCourseOption {
        WatchCourseOption(
            globalId: id, name: "测试球场 ~ \(label)", holes: 27, teeBox: "Blue",
            venueName: "测试球场", segmentLabel: label, segmentHoles: 9
        )
    }

    func testLoopVenueOpeningOffersOnlyIndividualNines() {
        let a = loop(301, "A")
        let choices = WatchRoundSetupView.loopChoices(
            front: a, backOptions: [a, loop(302, "B"), loop(303, "C")],
            selectedPrimaryGlobalId: 302
        )

        // Three real loops => three start options, each covering exactly nine holes (README §8).
        XCTAssertEqual(choices.count, 3)
        XCTAssertEqual(choices.map(\.title), ["A 场", "B 场", "C 场"])
        XCTAssertEqual(choices.map(\.detail), ["9 洞", "9 洞", "9 洞"])
        XCTAssertEqual(choices.map(\.isSelected), [false, true, false])
        XCTAssertFalse(choices.contains { $0.id.hasPrefix("loop:full:") })
    }

    func testStandaloneNineDoesNotOfferFullEighteenAtOpening() {
        let a = loop(301, "A")
        let choices = WatchRoundSetupView.loopChoices(
            front: a, backOptions: [a], selectedPrimaryGlobalId: 301
        )

        // Repeating the same nine is a turn decision, so a lone loop has one opening option.
        XCTAssertEqual(choices.count, 1)
        XCTAssertEqual(choices.map(\.title), ["A 场"])
        XCTAssertEqual(choices.map(\.detail), ["9 洞"])
        XCTAssertEqual(choices.map(\.isSelected), [true])
    }

    func testOrdinaryEighteenKeepsItsTwoHalfOptions() {
        let course = WatchCourseOption(
            globalId: 400, name: "十八洞球场", holes: 18, segmentHoles: 18
        )
        let choices = WatchRoundSetupView.halfChoices(front: course, selectedHalf: "back")

        // B4b-2 §7: a non-loop 18-hole row retains physical 1–9 / 10–18, not A/B loop choices.
        XCTAssertEqual(choices.map(\.id), ["watch-setup-half-front", "watch-setup-half-back"])
        XCTAssertEqual(choices.map(\.title), ["前九", "后九"])
        XCTAssertEqual(choices.map(\.detail), ["第 1–9 洞", "第 10–18 洞"])
        XCTAssertEqual(choices.map(\.isSelected), [false, true])
        XCTAssertTrue(WatchRoundSetupView.halfChoices(front: loop(301, "A"), selectedHalf: "front").isEmpty)
    }

    func testEachOpeningLoopSubmitsOnlyItsOwnNine() {
        let loops = [loop(301, "A"), loop(302, "B"), loop(303, "C")]
        // Hand golden: one global id and nine holes, with no second-loop id in the start payload.
        let keys = ["301:all", "302:all", "303:all"]
        let titles = ["A 场", "B 场", "C 场"]
        for (index, first) in loops.enumerated() {
            let view = WatchRoundSetupView(front: first, courses: loops)
            XCTAssertEqual(view.initialStage, .holes)
            XCTAssertEqual(view.startSelection.front.globalId, first.globalId)
            XCTAssertNil(view.startSelection.back)
            XCTAssertEqual(view.startSelection.loopKey, keys[index])
            XCTAssertEqual(view.startSelection.loopsQuery, keys[index])
            XCTAssertEqual(view.startSelection.holeCount, 9)
            XCTAssertEqual(view.loopChoices.filter(\.isSelected).map(\.title), [titles[index]])
        }
    }
}
