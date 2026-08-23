import XCTest
@testable import AICaddie

final class BackendConfigurationStoreTests: XCTestCase {
    func testNormalizedAPIBaseURLPreservesSafeHTTPSPathPrefix() {
        XCTAssertEqual(
            BackendConfigurationStore.normalizedAPIBaseURL(
                from: "https://caddie.example.test/aicaddie-candidate/"
            )?.absoluteString,
            "https://caddie.example.test/aicaddie-candidate"
        )
    }

    func testNormalizedAPIBaseURLRejectsAmbiguousOrAuthorityChangingValues() {
        for value in [
            "https://caddie.example.test/a/../candidate",
            "https://caddie.example.test/a//candidate",
            "https://user@caddie.example.test/candidate",
            "https://caddie.example.test/candidate?token=secret",
        ] {
            XCTAssertNil(BackendConfigurationStore.normalizedAPIBaseURL(from: value), value)
        }
    }
}
