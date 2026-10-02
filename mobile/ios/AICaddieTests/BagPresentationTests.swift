@testable import AICaddie
import XCTest

/// B5c 球包 distance ladder (README §9, `stats.html` 3).
final class BagPresentationTests: XCTestCase {
    private let profiles = [
        ClubProfile(clubName: "Driver", sampleSize: 86, medianM: 211, p10M: 187, p90M: 227),
        ClubProfile(clubName: "7I", sampleSize: 58, medianM: 137, p10M: 124, p90M: 146),
        ClubProfile(clubName: "8I", sampleSize: 51, medianM: 128, p10M: 116, p90M: 136),
        ClubProfile(clubName: "PW", sampleSize: 0, medianM: 105, p10M: 93, p90M: 113),
    ]

    func testRowsRunLongToShortWithTypedDistancesAndUnmeasuredClubsLast() {
        let rows = BagPresentation.rows(
            bag: ["一号木", "七号铁", "八号铁", "P 杆", "九号铁", "推杆"],
            profiles: profiles,
            manual: ["九号铁": 130, "八号铁": 0]
        )
        XCTAssertEqual(rows.map(\.name), ["一号木", "七号铁", "八号铁", "九号铁", "P 杆"],
                       "no putter; a typed 9 iron sits by its distance; a club with no samples is last")
        XCTAssertEqual(rows[0].median, 231)
        XCTAssertEqual([rows[0].p10, rows[0].p90], [205, 248])
        XCTAssertTrue(rows[3].isManual)
        XCTAssertFalse(rows[3].hasRange, "a typed distance alone draws no bar")
        XCTAssertFalse(rows[2].isManual, "a zero typed distance is no distance")
        XCTAssertNil(rows[4].median, "zero samples are not a distance")
    }

    func testGapsBetweenNeighboursFlagOverlapsAndHoles() {
        let rows = BagPresentation.rows(bag: ["一号木", "七号铁", "八号铁"], profiles: profiles, manual: [:])
        let gaps = zip(rows, rows.dropFirst()).compactMap { BagPresentation.gap($0, $1) }
        XCTAssertEqual(gaps.map(\.yards), [81, 10])
        XCTAssertEqual(gaps.map(\.isFlagged), [true, false])
        XCTAssertEqual(gaps[1].text, "差 10 码")
        XCTAssertTrue(BagPresentation.Gap(yards: 7).isFlagged)
        XCTAssertFalse(BagPresentation.Gap(yards: 8).isFlagged)
        XCTAssertFalse(BagPresentation.Gap(yards: 20).isFlagged)
        XCTAssertTrue(BagPresentation.Gap(yards: 21).isFlagged)
    }

    func testTheAxisCoversEveryBarInWholeTens() throws {
        let rows = BagPresentation.rows(bag: ["一号木", "八号铁"], profiles: profiles, manual: [:])
        let axis = try XCTUnwrap(BagPresentation.axis(rows))
        XCTAssertEqual(axis, 110...260)
        XCTAssertEqual(BagPresentation.ticks(axis), [150, 200, 250])
        XCTAssertNil(BagPresentation.axis([]))
    }

    func testTheEditorNamesOnlyWhatIsKnown() {
        let rows = BagPresentation.rows(bag: ["一号木", "P 杆"], profiles: profiles, manual: [:])
        XCTAssertEqual(BagPresentation.historyText(rows[0]), "历史 86 杆 · 中位 231 码 · 80% 在 205–248 码")
        XCTAssertEqual(BagPresentation.historyText(rows[1]), "还没有击球记录")
        XCTAssertEqual(BagPresentation.summary(rows), "2 支 · 条是 80% 的击球落在的范围，白线是中位数")
        XCTAssertFalse(BagPresentation.addable(bag: ["一号木"]).map(\.zhName).contains("一号木"))
        XCTAssertFalse(BagPresentation.addable(bag: []).map(\.zhName).contains("推杆"), "no invisible putter row")
    }

    func testAliasesOfOneClubUseTheStrongestSampleWhateverTheOrder() {
        let weak = ClubProfile(clubName: "Aw", sampleSize: 4, medianM: 70, p10M: 60, p90M: 78)
        let strong = ClubProfile(clubName: "GW", sampleSize: 31, medianM: 91, p10M: 80, p90M: 99)
        let sevenLegacy = ClubProfile(clubName: "7 Iron", sampleSize: 2, medianM: 120, p10M: 115, p90M: 125)
        let seven = ClubProfile(clubName: "7I", sampleSize: 58, medianM: 137, p10M: 124, p90M: 146)
        for profiles in [[weak, strong, sevenLegacy, seven], [strong, weak, seven, sevenLegacy]] {
            let rows = BagPresentation.rows(bag: ["A 杆", "七号铁"], profiles: profiles, manual: [:])
            let wedge = rows.first { $0.name == "A 杆" }
            XCTAssertEqual(wedge?.samples, 31)
            XCTAssertEqual(wedge?.historyMedian, 100)
            let iron = rows.first { $0.name == "七号铁" }
            XCTAssertEqual(iron?.samples, 58)
            XCTAssertEqual(iron?.historyMedian, 150)
        }
        // Equal samples: the earlier row, deterministically.
        let tie = [ClubProfile(clubName: "PW", sampleSize: 9, medianM: 100, p10M: 90, p90M: 110),
                   ClubProfile(clubName: "P", sampleSize: 9, medianM: 110, p10M: 100, p90M: 120)]
        XCTAssertEqual(BagPresentation.strongestProfile(for: "P 杆", in: tie)?.clubName, "PW")
    }
}
