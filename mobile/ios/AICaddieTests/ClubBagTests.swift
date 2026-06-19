import XCTest
@testable import AICaddie

/// The real Garmin bag (from `/club/player` + `/club/types`) resolves to the app's Chinese catalog
/// names: custom names win (Pw/Aw/50/54/58), else the authoritative clubTypeId map; retired/deleted
/// clubs drop out. This is the owner's actual 14-club bag.
final class ClubBagTests: XCTestCase {
    private func club(_ id: Int, _ typeId: Int, custom: String? = nil, typeName: String? = nil,
                      retired: Bool = false, deleted: Bool = false) -> ClubBagClub {
        ClubBagClub(id: id, clubTypeId: typeId, customName: custom, typeName: typeName,
                    retired: retired, deleted: deleted)
    }

    func testClubTypeIdMapIsAuthoritative() {
        // The Garmin scheme: Driver=1 … 9 Iron=18 … Putter=23 (NOT the old guessed Putter=18).
        XCTAssertEqual(garminClubTypeZh[1], "一号木")
        XCTAssertEqual(garminClubTypeZh[2], "三号木")
        XCTAssertEqual(garminClubTypeZh[6], "三号小鸡腿")
        XCTAssertEqual(garminClubTypeZh[14], "五号铁")
        XCTAssertEqual(garminClubTypeZh[18], "九号铁")
        XCTAssertEqual(garminClubTypeZh[19], "P 杆")
        XCTAssertEqual(garminClubTypeZh[20], "A 杆")
        XCTAssertEqual(garminClubTypeZh[23], "推杆")
    }

    func testResolvesOwnerRealBag() {
        // The owner's actual 14-club bag (5 custom-named wedges + standard clubs).
        let response = ClubBagResponse(found: true, clubs: [
            club(42684923, 1),
            club(42684924, 2),
            club(42684926, 6),
            club(42684927, 14),
            club(42684931, 15),
            club(42684932, 16),
            club(42684933, 17),
            club(42684934, 18),
            club(42684975, 18, custom: "Pw"),
            club(42684957, 19, custom: "Aw"),
            club(42684936, 20, custom: "50"),
            club(42684937, 21, custom: "54"),
            club(42684938, 22, custom: "58"),
            club(42684939, 23),
        ])
        let names = resolvedBagNames(response)
        let expected: Set<String> = [
            "一号木", "三号木", "三号小鸡腿", "五号铁", "六号铁", "七号铁", "八号铁", "九号铁",
            "P 杆", "A 杆", "50° 挖起杆", "54° 挖起杆", "58° 挖起杆", "推杆",
        ]
        XCTAssertEqual(names, expected)
        // Every resolved name is a real catalog entry (so it renders as a checkable row).
        XCTAssertTrue(names.allSatisfy { ClubCatalog.names.contains($0) })
    }

    func testCustomNameOverridesClubType() {
        // A type-18 (9 Iron) club the user renamed "Pw" shows as P 杆, not 九号铁.
        let response = ClubBagResponse(found: true, clubs: [club(1, 18, custom: "Pw")])
        XCTAssertEqual(resolvedBagNames(response), ["P 杆"])
    }

    func testExcludesRetiredAndDeleted() {
        let response = ClubBagResponse(found: true, clubs: [
            club(1, 1),                       // in use → 一号木
            club(2, 2, retired: true),        // retired → dropped
            club(3, 14, deleted: true),       // deleted → dropped
        ])
        XCTAssertEqual(resolvedBagNames(response), ["一号木"])
    }

    func testNewCatalogEntriesCoverFullGarminScheme() {
        // Catalog was extended so any of the 23 Garmin types maps to a checkable row.
        for typeId in 1...23 {
            if let zh = garminClubTypeZh[typeId] {
                XCTAssertTrue(ClubCatalog.names.contains(zh), "clubTypeId \(typeId) → \(zh) missing from catalog")
            }
        }
    }
}
