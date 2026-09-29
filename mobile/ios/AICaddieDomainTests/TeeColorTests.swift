import XCTest
@testable import AICaddieDomain

/// The one shared tee-colour mapping used by the phone start screen and the Watch setup.
final class TeeColorTests: XCTestCase {
    func testKnownTeeKeysMapCaseInsensitivelyAndAcceptTheWatchPrefix() {
        XCTAssertEqual(TeeColor.forTee("blue"), .blueTee)
        XCTAssertEqual(TeeColor.forTee("Blue"), .blueTee)
        XCTAssertEqual(TeeColor.forTee(" WHITE "), .whiteTee)
        XCTAssertEqual(TeeColor.forTee("tee:red"), .redTee)
        XCTAssertEqual(TeeColor.forTee("Gold"), .goldTee)
        XCTAssertEqual(TeeColor.forTee("yellow"), .yellowTee)
        XCTAssertEqual(TeeColor.forTee("green"), .greenTee)
        XCTAssertEqual(TeeColor.forTee("silver"), .silverTee)
    }

    func testChampionshipAliasesShareTheBlackTee() {
        XCTAssertEqual(TeeColor.forTee("black"), .blackTee)
        XCTAssertEqual(TeeColor.forTee("championship"), .blackTee)
        XCTAssertEqual(TeeColor.forTee("Tips"), .blackTee)
    }

    func testUnknownTeesAreNeutralNeverAGuessedColour() {
        XCTAssertEqual(TeeColor.forTee("unknown"), .unknownTee)
        XCTAssertEqual(TeeColor.forTee(""), .unknownTee)
        XCTAssertEqual(TeeColor.forTee("Combo"), .unknownTee)
    }

    func testOnlyNearWhiteTeesNeedAnOutline() {
        XCTAssertTrue(TeeColor.whiteTee.isLight)
        XCTAssertFalse(TeeColor.blueTee.isLight)
        XCTAssertFalse(TeeColor.blackTee.isLight)
        XCTAssertFalse(TeeColor.yellowTee.isLight)
    }
}
