import XCTest

final class RealEvidenceRoundResolverTests: XCTestCase {
    func testBlankPreferredRoundReferenceFallsBackToRecentHistory() {
        XCTAssertNil(RealEvidenceRoundResolver.normalizedPreferredRoundRef(nil))
        XCTAssertNil(RealEvidenceRoundResolver.normalizedPreferredRoundRef(""))
        XCTAssertNil(RealEvidenceRoundResolver.normalizedPreferredRoundRef(" \n\t "))
        XCTAssertEqual(
            RealEvidenceRoundResolver.normalizedPreferredRoundRef(" 17603881 "),
            "17603881"
        )
    }
}
