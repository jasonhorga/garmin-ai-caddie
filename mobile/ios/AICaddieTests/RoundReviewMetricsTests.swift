import XCTest
@testable import AICaddie

final class RoundReviewMetricsTests: XCTestCase {
    func testFairwayDenominatorExcludesUnknownAndMissingValues() {
        XCTAssertEqual(roundReviewFairwayOutcome("hit"), true)
        XCTAssertEqual(roundReviewFairwayOutcome("left"), false)
        XCTAssertNil(roundReviewFairwayOutcome("unknown"))
        XCTAssertNil(roundReviewFairwayOutcome("future-token"))
        XCTAssertNil(roundReviewFairwayOutcome(""))
        XCTAssertNil(roundReviewFairwayOutcome(nil))

        let counts = roundReviewFairwayCounts(["hit", "unknown", nil, "0"])
        XCTAssertEqual(counts.hit, 1)
        XCTAssertEqual(counts.recorded, 2)
    }

    func testFairwayLabelsDistinguishRecordedZeroFromUnknown() {
        XCTAssertEqual(roundReviewFairwayLabel("0"), "球道✗")
        XCTAssertEqual(roundReviewFairwayLabel("unknown"), "未记录")
        XCTAssertEqual(roundReviewFairwayLabel(nil), "未记录")
    }

    /// A 9-of-18 round: holes 1–9 scored, 10–18 blank in the backend scorecard.
    private func nineOfEighteen() throws -> [RoundDetailHole] {
        let rows = (1...18).map { hole -> String in
            hole <= 9
                ? #"{"hole":\#(hole),"localHole":\#(hole + 9),"par":4,"score":5,"putts":2}"#
                : #"{"hole":\#(hole),"localHole":\#(hole - 9),"par":4}"#
        }
        return try JSONDecoder().decode([RoundDetailHole].self, from: Data("[\(rows.joined(separator: ","))]".utf8))
    }

    func testPartialRoundKeepsEveryCourseHoleOnTheStripButOpensOnlyPlayedHoles() throws {
        let scorecard = try nineOfEighteen()
        let holes = RoundReviewHoles(scorecard.reversed())
        XCTAssertEqual(holes.strip, Array(1...18), "holes 10–18 stay on the strip")
        XCTAssertEqual(holes.played, Array(1...9), "only scored holes page and prefetch")
        XCTAssertTrue(holes.canOpen(1))
        XCTAssertTrue(holes.canOpen(9))
        XCTAssertFalse(holes.canOpen(10), "an unplayed hole never requests a shot map")
        XCTAssertFalse(holes.canOpen(18))

        let card = RoundReviewScorecard(scorecard)
        XCTAssertEqual(card.holes.map(\.number), Array(1...18), "round-hole keys stay in play order")
        XCTAssertEqual(card.holes.compactMap(\.displayNumber), Array(10...18) + Array(1...9),
                       "the card displays the physical back/front holes")
        XCTAssertEqual(card.nineLabels?.front, "后九")
        XCTAssertEqual(card.nineLabels?.back, "前九")
        XCTAssertEqual(Set(card.scores.keys), Set(1...9))
        XCTAssertTrue(card.canOpen(9))
        XCTAssertFalse(card.canOpen(10))
        XCTAssertEqual(card.strokes, 45)
    }

    func testTwoLoopCardUsesNeutralLabelsAndShareNamesWhenPhysicalHalvesAreUnknown() throws {
        let rows = (1...18).map { hole in
            #"{"hole":\#(hole),"localHole":\#((hole - 1) % 9 + 1),"par":4,"score":4}"#
        }
        let scorecard = try JSONDecoder().decode(
            [RoundDetailHole].self, from: Data("[\(rows.joined(separator: ","))]".utf8)
        )
        let card = RoundReviewScorecard(scorecard)
        XCTAssertNil(card.nineLabels, "two loops that both start at 1 have no front/back identity")
        let shared = RoundReviewContent.shareText(
            course: "Example",
            round: RoundDetailSummary(
                courseName: "Example", date: nil, score: 72, par: 72, toPar: 0,
                holesCompleted: 18, holesScored: 18, courseHoles: 18, confidence: nil
            ),
            card: card
        )
        XCTAssertTrue(shared.contains("第一环 36"))
        XCTAssertTrue(shared.contains("第二环 36"))
        XCTAssertFalse(shared.contains("OUT"))
        XCTAssertFalse(shared.contains("IN"))
    }

    func testUnscoredRoundPagesEveryHoleAndTheStripIsCappedAtEighteen() throws {
        let rows = (1...27).map { #"{"hole":\#($0),"par":4}"# }
        let scorecard = try JSONDecoder().decode([RoundDetailHole].self, from: Data("[\(rows.joined(separator: ","))]".utf8))
        let holes = RoundReviewHoles(scorecard + scorecard.prefix(2))
        XCTAssertEqual(holes.strip, Array(1...18), "duplicates collapse and the width is capped")
        XCTAssertEqual(holes.played, Array(1...18))
    }
}
