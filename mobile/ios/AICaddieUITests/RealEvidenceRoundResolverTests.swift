import XCTest

final class RealEvidenceRoundResolverTests: XCTestCase {
    func testLiveLaunchOmitsFixtureMarkersButPreservesNonLiveMarkers() {
        XCTAssertEqual(
            UITestBackendLaunchConfiguration.markers(fixtureMode: "0", dataMode: ""),
            [:]
        )
        XCTAssertEqual(
            UITestBackendLaunchConfiguration.markers(fixtureMode: nil, dataMode: nil),
            [:]
        )
        XCTAssertEqual(
            UITestBackendLaunchConfiguration.markers(fixtureMode: "1", dataMode: "fixture"),
            [
                "AI_CADDIE_FIXTURE_MODE": "1",
                "AI_CADDIE_DATA_MODE": "fixture",
            ]
        )
        // Do not normalize malformed values into live mode; the app must reject them fail-closed.
        XCTAssertEqual(
            UITestBackendLaunchConfiguration.markers(fixtureMode: "1", dataMode: "production"),
            [
                "AI_CADDIE_FIXTURE_MODE": "1",
                "AI_CADDIE_DATA_MODE": "production",
            ]
        )
    }

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
