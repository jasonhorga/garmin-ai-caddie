import XCTest
@testable import AICaddie

/// Device review (build 77): a 433 y Par 4 planned 一号木 214 → 三号木 175 → 九号铁 66 although only
/// 44 y were left after the 3-wood. The plan's carry is the club's full stock carry; the label must
/// name the shot actually played.
final class PlannedShotLabelTests: XCTestCase {
    func testFullLegKeepsClubAndCarry() {
        let label = PlannedShotLabel.resolve(clubName: "3W", carryM: 160, playedM: 160)
        XCTAssertEqual(label.yards, 175)
        XCTAssertNotEqual(label.club, "切杆")
    }

    func testShortFinishShowsPlayedDistanceAsPitch() {
        // 9-iron carries 60 m; the green is 40.3 m away.
        let label = PlannedShotLabel.resolve(clubName: "9I", carryM: 60, playedM: 40.3)
        XCTAssertEqual(label.club, "切杆")
        XCTAssertEqual(label.yards, 44)
    }

    func testSlightlyShortLegKeepsClubButShowsPlayedDistance() {
        let label = PlannedShotLabel.resolve(clubName: "7I", carryM: 140, playedM: 120)
        XCTAssertNotEqual(label.club, "切杆")
        XCTAssertEqual(label.yards, 131)
    }

    func testWithinToleranceKeepsCarry() {
        let label = PlannedShotLabel.resolve(clubName: "7I", carryM: 140, playedM: 137)
        XCTAssertEqual(label.yards, 153)
    }

    func testPlanWithoutCarryUsesPlayedDistance() {
        XCTAssertEqual(PlannedShotLabel.resolve(clubName: "PW", carryM: nil, playedM: 90).yards, 98)
        XCTAssertNil(PlannedShotLabel.resolve(clubName: "PW", carryM: nil, playedM: nil).yards)
    }
}
