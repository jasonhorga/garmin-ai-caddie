import XCTest
@testable import AICaddie

@MainActor
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

    func testFixtureURLRejectsAPathPrefix() {
        XCTAssertNil(BackendConfigurationStore.normalizedAPIBaseURL(
            from: "http://127.0.0.1:9000/fixture",
            allowFixtureLoopback: true
        ))
    }

    func testFixtureResolutionNeverFallsBackToPersistedOrBundleValues() {
        let persisted = "https://production.example.test"
        let fixtureEnvironment = [
            "AI_CADDIE_FIXTURE_MODE": "1",
            "AI_CADDIE_DATA_MODE": "fixture",
            "AI_CADDIE_ADMIN_TOKEN": "masked-test-token",
        ]
        XCTAssertNil(LiveRoundAppModel.resolveAPIBaseURL(
            environment: fixtureEnvironment,
            persistedValue: persisted,
            bundleValue: persisted
        ))
        XCTAssertNil(LiveRoundAppModel.resolveAPIBaseURL(
            environment: fixtureEnvironment.merging(["AI_CADDIE_API_BASE_URL": "https://production.example.test"]) { _, new in new },
            persistedValue: persisted,
            bundleValue: persisted
        ))
        XCTAssertEqual(LiveRoundAppModel.resolveAPIBaseURL(
            environment: fixtureEnvironment.merging(["AI_CADDIE_API_BASE_URL": "http://127.0.0.1:9000"]) { _, new in new },
            persistedValue: persisted,
            bundleValue: persisted
        )?.absoluteString, "http://127.0.0.1:9000")
    }

    func testFixtureMarkerMismatchRejectsEvenWithFallbackValues() {
        let fallback = "https://production.example.test"
        for environment in [
            ["AI_CADDIE_FIXTURE_MODE": "1", "AI_CADDIE_DATA_MODE": "production", "AI_CADDIE_ADMIN_TOKEN": "token"],
            ["AI_CADDIE_FIXTURE_MODE": "0", "AI_CADDIE_DATA_MODE": "fixture", "AI_CADDIE_ADMIN_TOKEN": "token"],
            ["AI_CADDIE_FIXTURE_MODE": "1", "AI_CADDIE_DATA_MODE": "fixture"],
        ] {
            XCTAssertNil(LiveRoundAppModel.resolveAPIBaseURL(environment: environment, persistedValue: fallback, bundleValue: fallback))
        }
    }

    func testLiveResolutionKeepsHTTPSOnlyPolicy() {
        XCTAssertNotNil(LiveRoundAppModel.resolveAPIBaseURL(
            environment: ["AI_CADDIE_API_BASE_URL": "https://public.example.test"],
            persistedValue: nil,
            bundleValue: nil
        ))
        XCTAssertNil(LiveRoundAppModel.resolveAPIBaseURL(
            environment: ["AI_CADDIE_API_BASE_URL": "http://127.0.0.1:9000"],
            persistedValue: nil,
            bundleValue: nil
        ))
    }
}
