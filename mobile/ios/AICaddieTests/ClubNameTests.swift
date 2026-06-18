import XCTest
@testable import AICaddie

/// zhClubName normalizes the messy real Garmin bag (Driver/3W/3号木杆/9I/50/PW/Pw/Aw/Putter/2I-Hybrid…)
/// to clear Chinese, collapsing duplicate spellings so the picker can dedup.
final class ClubNameTests: XCTestCase {
    func testWoodsAndDriver() {
        XCTAssertEqual(zhClubName("Driver"), "一号木")
        XCTAssertEqual(zhClubName("3W"), "三号木")
        XCTAssertEqual(zhClubName("3号木杆"), "三号木")        // same club as 3W → same name
        XCTAssertEqual(zhClubName("5W"), "五号木")
    }

    func testHybridIronWedge() {
        XCTAssertEqual(zhClubName("3号小鸡腿"), "三号小鸡腿")
        XCTAssertEqual(zhClubName("2I/Hybrid"), "二号小鸡腿")
        XCTAssertEqual(zhClubName("9I"), "九号铁")
        XCTAssertEqual(zhClubName("50"), "50° 挖起杆")
        XCTAssertEqual(zhClubName("58"), "58° 挖起杆")
    }

    func testLetterWedgesDedup() {
        XCTAssertEqual(zhClubName("PW"), "P 杆")
        XCTAssertEqual(zhClubName("Pw"), "P 杆")
        XCTAssertEqual(zhClubName("P"), "P 杆")
        XCTAssertEqual(zhClubName("GW"), "A 杆")
        XCTAssertEqual(zhClubName("Aw"), "A 杆")
        XCTAssertEqual(zhClubName("SW"), "S 杆")
        XCTAssertEqual(zhClubName("LW"), "L 杆")
        XCTAssertEqual(zhClubName("Putter"), "推杆")
    }

    func testIdempotentAndTeeOnly() {
        XCTAssertEqual(zhClubName("一号木"), "一号木")     // idempotent on its own output
        XCTAssertEqual(zhClubName("P 杆"), "P 杆")
        XCTAssertTrue(clubIsTeeOnly("一号木"))
        XCTAssertFalse(clubIsTeeOnly("五号铁"))
    }
}
