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

    func testFixtureLoopbackHTTPRequiresExplicitOptIn() {
        XCTAssertEqual(
            BackendConfigurationStore.normalizedAPIBaseURL(
                from: "http://127.0.0.1:9000",
                allowFixtureLoopback: true
            )?.absoluteString,
            "http://127.0.0.1:9000"
        )
        for value in [
            "http://127.0.0.1:8999",
            "http://127.0.0.2:9000",
            "http://127.0.0.1:9000/path?token=secret",
        ] {
            XCTAssertNil(
                BackendConfigurationStore.normalizedAPIBaseURL(
                    from: value,
                    allowFixtureLoopback: true
                ),
                value
            )
        }
        XCTAssertNil(BackendConfigurationStore.normalizedAPIBaseURL(from: "http://127.0.0.1:9000"))
        XCTAssertNotNil(BackendConfigurationStore.normalizedAPIBaseURL(from: "https://caddie.example.test"))
    }
}
