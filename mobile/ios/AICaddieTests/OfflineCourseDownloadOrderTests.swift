@testable import AICaddie
import XCTest

final class OfflineCourseDownloadOrderTests: XCTestCase {
    private func holes(_ numbers: [Int], globalId: Int = 7, localOffset: Int = 0) -> [OfflineCourseDownloadOrder.Hole] {
        numbers.map { .init(number: $0, key: "\(globalId):\($0 + localOffset)") }
    }

    /// A back-nine start fetches hole 10 first, then 11…18, then the front nine it will play last.
    func testTheActiveHoleThenTheHolesAheadThenThosePlayed() {
        let round = holes(Array(1...18))
        let ranks = OfflineCourseDownloadOrder.ranks(roundHoles: round, activeHole: 10)
        XCTAssertEqual(ranks["7:10"], 0)
        XCTAssertEqual(ranks["7:18"], 8)
        XCTAssertEqual(ranks["7:1"], 9)
        XCTAssertEqual(ranks["7:9"], 17)
    }

    /// Relaunching mid-round on hole 7 starts at hole 7, not hole 1.
    func testARelaunchMidRoundStartsAtTheHoleBeingPlayed() {
        let ranks = OfflineCourseDownloadOrder.ranks(roundHoles: holes(Array(1...18)), activeHole: 7)
        let order = ranks.sorted { $0.value < $1.value }.map(\.key)
        XCTAssertEqual(Array(order.prefix(3)), ["7:7", "7:8", "7:9"])
        XCTAssertEqual(order.last, "7:6")
    }

    func testNoOrUnknownActiveHoleKeepsRoundOrder() {
        let round = holes(Array(1...9))
        for active in [nil, 42] as [Int?] {
            let ranks = OfflineCourseDownloadOrder.ranks(roundHoles: round, activeHole: active)
            XCTAssertEqual(ranks["7:1"], 0)
            XCTAssertEqual(ranks["7:9"], 8)
        }
    }

    /// The same nine played twice (后→后): each physical hole is ranked by its nearest visit.
    func testARepeatedLoopKeepsEachPhysicalHolesEarliestRank() {
        let round = holes(Array(1...9), localOffset: 9) + holes(Array(10...18), localOffset: 0)
        // Round holes 1…9 map to local 10…18, round holes 10…18 to local 10…18 again.
        let ranks = OfflineCourseDownloadOrder.ranks(roundHoles: round, activeHole: 12)
        XCTAssertEqual(ranks["7:12"], 0, "round hole 12 is local 12")
        XCTAssertEqual(ranks["7:18"], 6)
        XCTAssertEqual(ranks["7:10"], 7, "local 10 next comes up as round hole 1")
        XCTAssertEqual(ranks.count, 9)
    }

    func testAPersistedRowWithoutTheIntentFlagDecodesAsThePlayersOwn() throws {
        let row = PrepCourseDownloadRecord(
            course: MobileCourseOption(globalId: 7, name: "Old", holes: 18, teeBox: "blue"),
            isIntentPrefetch: true
        )
        let encoded = try JSONEncoder().encode(row)
        XCTAssertTrue(try JSONDecoder().decode(PrepCourseDownloadRecord.self, from: encoded).isIntentPrefetch)

        var legacy = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        legacy.removeValue(forKey: "isIntentPrefetch")
        let decoded = try JSONDecoder().decode(
            PrepCourseDownloadRecord.self,
            from: JSONSerialization.data(withJSONObject: legacy)
        )
        XCTAssertFalse(decoded.isIntentPrefetch)
        XCTAssertEqual(decoded.id, row.id)
    }
}
