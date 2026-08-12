import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import AICaddie

final class SyncClientTests: XCTestCase {
    func testEventBatchEncodesRoundIdAndEvents() throws {
        let event = LiveRoundEvent(
            eventId: "event-1",
            roundId: "round-1",
            timestamp: "2026-05-25T00:00:00Z",
            hole: 1,
            kind: .club,
            payload: ["clubName": .string("8I")]
        )

        let data = try JSONEncoder().encode(EventBatch(roundId: "round-1", events: [event]))
        let decoded = try JSONDecoder().decode(EventBatch.self, from: data)

        XCTAssertEqual(decoded.roundId, "round-1")
        XCTAssertEqual(decoded.events.first?.kind, .club)
    }

    func testSyncResultDecodesAcknowledgementMetadata() throws {
        let payload = """
        {
          "accepted": 2,
          "duplicate": false,
          "acceptedEventIds": ["event-1", "event-2"],
          "duplicateEventIds": ["event-0"],
          "serverSequence": 42
        }
        """.data(using: .utf8)!

        let result = try JSONDecoder().decode(SyncResult.self, from: payload)

        XCTAssertEqual(result.accepted, 2)
        XCTAssertFalse(result.duplicate)
        XCTAssertEqual(result.acceptedEventIds, ["event-1", "event-2"])
        XCTAssertEqual(result.duplicateEventIds, ["event-0"])
        XCTAssertEqual(result.serverSequence, 42)
    }

    func testSyncResultDecodesLegacyAcknowledgementWithoutMetadata() throws {
        let payload = """
        {
          "accepted": 1,
          "duplicate": true
        }
        """.data(using: .utf8)!

        let result = try JSONDecoder().decode(SyncResult.self, from: payload)

        XCTAssertEqual(result.accepted, 1)
        XCTAssertTrue(result.duplicate)
        XCTAssertEqual(result.acceptedEventIds, [])
        XCTAssertEqual(result.duplicateEventIds, [])
        XCTAssertEqual(result.serverSequence, 0)
    }

    func testFetchRoundPackageAttachesAdminTokenHeader() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let responseData = try Data(contentsOf: fixtureURL)
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/mobile/rounds/live-round-1/package")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "admin-secret")
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, responseData)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            adminToken: "admin-secret",
            session: session
        )

        let package = try await client.fetchRoundPackage(roundId: "live-round-1")

        XCTAssertEqual(package.roundId, "live-round-1")
    }

    func testFetchRoundPackageSendsCapturedAtQuery() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let responseData = try Data(contentsOf: fixtureURL)
        let capturedAt = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-05-25T09:15:00Z"))
        CapturingURLProtocol.requestHandler = { request in
            let queryItems = URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false)?.queryItems
            XCTAssertEqual(queryItems?.first { $0.name == "captured_at" }?.value, "2026-05-25T09:15:00Z")
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, responseData)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session
        )

        let package = try await client.fetchRoundPackage(roundId: "live-round-1", capturedAt: capturedAt)

        XCTAssertEqual(package.roundId, "live-round-1")
    }

    func testFetchCoursePrepRenderFalseSendsQueryItem() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = """
        {"schema":"ai-caddie-course-prep-v1","globalId":31870,"holeCount":0,"clubs":[],"holes":[]}
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/courses/31870/prep")
            let queryItems = URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false)?.queryItems
            XCTAssertEqual(queryItems?.first { $0.name == "render" }?.value, "false")
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session
        )

        let response = try await client.fetchCoursePrep(globalId: 31870, render: false)

        XCTAssertEqual(response.globalId, 31870)
    }

    func testFetchCourseGeometryCoverageUsesCheapSelectedHoleProbe() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = Data(
            #"{"schema":"ai-caddie-course-geometry-coverage-v1","globalId":31870,"coverage":"partial","readyHoles":1,"partialHoles":0,"totalHoles":2,"holes":[{"globalId":31870,"localHole":1,"coverage":"ready"},{"globalId":31870,"localHole":4,"coverage":"missing"}]}"#.utf8
        )
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/geometry/course/31870/coverage")
            let queryItems = URLComponents(
                url: try XCTUnwrap(request.url),
                resolvingAgainstBaseURL: false
            )?.queryItems
            XCTAssertEqual(
                queryItems?.filter { $0.name == "holes" }.compactMap(\.value),
                ["1", "4"]
            )
            XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
            return (
                HTTPURLResponse(
                    url: try XCTUnwrap(request.url),
                    statusCode: 200,
                    httpVersion: nil,
                    headerFields: ["Content-Type": "application/json"]
                )!,
                payload
            )
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session
        )

        let coverage = try await client.fetchCourseGeometryCoverage(
            globalId: 31870,
            holes: [1, 4]
        )

        XCTAssertEqual(coverage.readyHoles, 1)
        XCTAssertEqual(coverage.holes.first?.localHole, 1)
    }

    func testSearchCoursesFetchesMetadataWithoutPreparingAssets() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = Data(
            #"{"schema":"ai-caddie-course-search-v1","query":"Mission Hills","matches":[{"globalId":10283,"name":"Mission Hills · A","holes":9,"city":"深圳","province":"广东","ratio":0.98,"latitude":22.7401328,"longitude":114.0714097,"distanceKm":0.4},{"globalId":10284,"name":"Mission Hills · B","holes":null,"city":"深圳","province":"广东","ratio":0.94,"latitude":null,"longitude":null,"distanceKm":null}]}"#.utf8
        )
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/courses/search")
            let queryItems = URLComponents(
                url: try XCTUnwrap(request.url),
                resolvingAgainstBaseURL: false
            )?.queryItems
            XCTAssertEqual(queryItems?.first { $0.name == "name" }?.value, "Mission Hills")
            XCTAssertEqual(queryItems?.first { $0.name == "city" }?.value, "深圳")
            XCTAssertEqual(queryItems?.first { $0.name == "latitude" }?.value, "22.7401328")
            XCTAssertEqual(queryItems?.first { $0.name == "longitude" }?.value, "114.0714097")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "admin-secret")
            XCTAssertNil(queryItems?.first { $0.name == "ensure_geometry" })
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            adminToken: "admin-secret",
            session: session
        )

        let matches = try await client.searchCourses(
            name: "  Mission Hills  ",
            city: " 深圳 ",
            latitude: 22.7401328,
            longitude: 114.0714097
        )

        XCTAssertEqual(matches.map(\.globalId), [10283, 10284])
        XCTAssertEqual(matches[0].latitude, 22.7401328)
        XCTAssertEqual(matches[0].longitude, 114.0714097)
        XCTAssertNil(matches[1].latitude)
        XCTAssertNil(matches[1].longitude)
        XCTAssertEqual(matches[0].distanceKm, 0.4)
        XCTAssertEqual(matches[0].subtitle, "0.4 km · 深圳 · 广东 · 9 洞")
        XCTAssertNotNil(matches[0].courseOption)
        XCTAssertNil(matches[1].courseOption)
    }

    func testSearchCoursesRetriesTransientTLSHandshakeWithoutRelaxingCertificateErrors() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = Data(
            #"{"schema":"ai-caddie-course-search-v1","query":"北京丽宫","matches":[{"globalId":31793,"name":"北京丽宫体育公园高尔夫俱乐部","holes":18,"city":"北京","province":"北京","ratio":1.0,"latitude":40.0455,"longitude":116.5462,"distanceKm":null}]}"#.utf8
        )
        var attempts = 0
        CapturingURLProtocol.requestHandler = { request in
            attempts += 1
            XCTAssertEqual(request.timeoutInterval, SyncClient.nearbyDiscoveryTimeoutInterval)
            if attempts == 1 {
                throw URLError(.secureConnectionFailed)
            }
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session,
            retrySleep: { _ in }
        )

        let matches = try await client.searchCourses(name: "北京丽宫")

        XCTAssertEqual(matches.map(\.globalId), [31793])
        XCTAssertEqual(attempts, 2)
        XCTAssertTrue(SyncClient.isTransientCourseReleaseError(URLError(.secureConnectionFailed)))
        XCTAssertFalse(SyncClient.isTransientCourseReleaseError(URLError(.serverCertificateUntrusted)))
    }

    func testNearbyCoursesUsesProviderWideRadiusEndpoint() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = Data(
            #"{"schema":"ai-caddie-course-nearby-v1","radiusKm":50,"matches":[{"globalId":31669,"name":"Shenzhen Mission Hills ~ Els","holes":9,"city":"Shenzhen","province":"Guangdong","ratio":0,"latitude":22.7402,"longitude":114.0715,"distanceKm":0.0}]}"#.utf8
        )
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/courses/nearby")
            let queryItems = URLComponents(
                url: try XCTUnwrap(request.url),
                resolvingAgainstBaseURL: false
            )?.queryItems
            XCTAssertEqual(queryItems?.first { $0.name == "latitude" }?.value, "22.7401328")
            XCTAssertEqual(queryItems?.first { $0.name == "longitude" }?.value, "114.0714097")
            XCTAssertEqual(queryItems?.first { $0.name == "radius_km" }?.value, "50")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "admin-secret")
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            adminToken: "admin-secret",
            session: session
        )

        let matches = try await client.nearbyCourses(
            latitude: 22.7401328,
            longitude: 114.0714097,
            radiusKm: 50
        )

        XCTAssertEqual(matches.map(\.globalId), [31669])
        XCTAssertEqual(matches.first?.distanceKm, 0.0)
        XCTAssertNotNil(matches.first?.courseOption)
    }

    func testNearbyCoursesRetriesATransientFailureWithoutDelayingTheFallback() async throws {
        XCTAssertGreaterThanOrEqual(SyncClient.nearbyDiscoveryTimeoutInterval, 30)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = Data(
            #"{"schema":"ai-caddie-course-nearby-v1","radiusKm":50,"matches":[]}"#.utf8
        )
        var attempts = 0
        CapturingURLProtocol.requestHandler = { request in
            attempts += 1
            XCTAssertEqual(request.timeoutInterval, SyncClient.nearbyDiscoveryTimeoutInterval)
            if attempts == 1 {
                throw URLError(.networkConnectionLost)
            }
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session,
            retrySleep: { _ in }
        )

        let matches = try await client.nearbyCourses(latitude: 0, longitude: 0, radiusKm: 50)

        XCTAssertTrue(matches.isEmpty)
        XCTAssertEqual(attempts, 2)
    }

    func testFetchCoursePrepCanRequestSmallHoleBatch() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = """
        {"schema":"ai-caddie-course-prep-v1","globalId":31870,"holeCount":0,"clubs":[],"holes":[]}
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            let queryItems = URLComponents(
                url: try XCTUnwrap(request.url),
                resolvingAgainstBaseURL: false
            )?.queryItems
            XCTAssertEqual(queryItems?.filter { $0.name == "holes" }.compactMap(\.value), ["1", "2", "3"])
            XCTAssertEqual(queryItems?.first { $0.name == "render" }?.value, "false")
            XCTAssertEqual(request.timeoutInterval, 180)
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session
        )

        _ = try await client.fetchCoursePrep(globalId: 31870, holes: [1, 2, 3], render: false)
    }

    func testFetchHolePrepRequestsOneLightweightHole() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = Data(
            #"{"schema":"ai-caddie-course-prep-v1","globalId":3881,"holeCount":1,"clubs":[],"holes":[{"hole":4,"par":4,"par_source":"courseview","blue_yards":197,"route_len_m":180,"route":[],"steps":[],"cautions":[],"hazards":{"water_carry":[],"bunkers":[]}}]}"#.utf8
        )
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/courses/3881/prep")
            let queryItems = URLComponents(
                url: try XCTUnwrap(request.url),
                resolvingAgainstBaseURL: false
            )?.queryItems
            XCTAssertEqual(queryItems?.first { $0.name == "holes" }?.value, "4")
            XCTAssertEqual(queryItems?.first { $0.name == "render" }?.value, "false")
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session
        )

        let hole = try await client.fetchHolePrep(globalId: 3881, localHole: 4)

        XCTAssertEqual(hole?.hole, 4)
    }

    func testFetchCourseTeesRequestsReleaseMetadata() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = Data(
            #"{"schema":"ai-caddie-course-tees-v1","globalId":10283,"defaultTeeBox":"blue","tees":[{"teeBox":"blue","name":"Blue","set":1,"yards":6828,"holeCount":18,"default":true}]}"#.utf8
        )
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/courses/10283/tees")
            let queryItems = URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false)?.queryItems
            XCTAssertEqual(queryItems?.first { $0.name == "ensure_release" }?.value, "true")
            XCTAssertNil(queryItems?.first { $0.name == "ensure_geometry" })
            XCTAssertEqual(request.timeoutInterval, SyncClient.courseReleaseTimeoutInterval)
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            adminToken: "admin-secret",
            session: session
        )

        let response = try await client.fetchCourseTees(globalId: 10283)

        XCTAssertEqual(response.globalId, 10283)
        XCTAssertEqual(response.tees.first?.set, 1)
    }

    func testFetchCourseTeesRetriesOnlyTransientReleaseFailures() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = Data(
            #"{"schema":"ai-caddie-course-tees-v1","globalId":10283,"defaultTeeBox":"blue","tees":[{"teeBox":"blue","name":"Blue","set":1,"yards":6828,"holeCount":18,"default":true}]}"#.utf8
        )
        var attempts = 0
        CapturingURLProtocol.requestHandler = { request in
            attempts += 1
            if attempts == 1 {
                let response = HTTPURLResponse(
                    url: try XCTUnwrap(request.url),
                    statusCode: 503,
                    httpVersion: nil,
                    headerFields: nil
                )!
                return (response, Data("cooldown".utf8))
            }
            if attempts == 2 {
                throw URLError(.timedOut)
            }
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session,
            retrySleep: { _ in }
        )

        let response = try await client.fetchCourseTees(globalId: 10283)

        XCTAssertEqual(response.globalId, 10283)
        XCTAssertEqual(attempts, 3)
        XCTAssertTrue(SyncClient.isTransientCourseReleaseError(URLError(.timedOut)))
        XCTAssertTrue(SyncClient.isTransientCourseReleaseError(SyncClientError.http(status: 429, body: nil)))
        XCTAssertFalse(SyncClient.isTransientCourseReleaseError(URLError(.cancelled)))
        XCTAssertFalse(SyncClient.isTransientCourseReleaseError(SyncClientError.http(status: 401, body: nil)))
        XCTAssertEqual(SyncClient.courseReleaseRetryDelayNanoseconds(afterAttempt: 1), 500_000_000)
        XCTAssertEqual(SyncClient.courseReleaseRetryDelayNanoseconds(afterAttempt: 2), 1_000_000_000)
    }

    func testFetchRoundDetailRetriesTransientTLSHandshake() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = Data(#"{"roundRef":"17553539","found":true,"scorecard":[],"phaseSummary":[],"missingData":[]}"#.utf8)
        var attempts = 0
        CapturingURLProtocol.requestHandler = { request in
            attempts += 1
            XCTAssertEqual(request.url?.path, "/api/v2/history/rounds/17553539")
            if attempts == 1 {
                throw URLError(.secureConnectionFailed)
            }
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session,
            retrySleep: { _ in }
        )

        let detail = try await client.fetchRoundDetail(roundRef: "17553539")

        XCTAssertTrue(detail.found)
        XCTAssertEqual(detail.roundRef, "17553539")
        XCTAssertEqual(attempts, 2)
    }

    func testFetchRoundDetailRetriesTransientHTTPStatuses() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = Data(#"{"roundRef":"round-retry","found":true}"#.utf8)
        var attempts = 0
        CapturingURLProtocol.requestHandler = { request in
            attempts += 1
            let status = attempts == 1 ? 429 : attempts == 2 ? 503 : 200
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: status,
                httpVersion: nil,
                headerFields: status == 200 ? ["Content-Type": "application/json"] : nil
            )!
            return (response, status == 200 ? payload : Data("temporary".utf8))
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session,
            retrySleep: { _ in }
        )

        let detail = try await client.fetchRoundDetail(roundRef: "round-retry")

        XCTAssertTrue(detail.found)
        XCTAssertEqual(attempts, 3)
    }

    func testFetchRoundDetailDoesNotRetryNotFound() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        var attempts = 0
        CapturingURLProtocol.requestHandler = { request in
            attempts += 1
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 404,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, Data("missing".utf8))
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session,
            retrySleep: { _ in XCTFail("404 must not sleep or retry") }
        )

        do {
            _ = try await client.fetchRoundDetail(roundRef: "missing-round")
            XCTFail("Expected 404")
        } catch let error as SyncClientError {
            XCTAssertEqual(error, .http(status: 404, body: "missing"))
        }
        XCTAssertEqual(attempts, 1)
    }

    func testFetchCoursePackageWithGeometryAllowsLongFirstDownload() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let responseData = try Data(contentsOf: fixtureURL)
        CapturingURLProtocol.requestHandler = { request in
            let queryItems = URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false)?.queryItems
            XCTAssertEqual(queryItems?.first { $0.name == "ensure_geometry" }?.value, "true")
            XCTAssertEqual(request.timeoutInterval, 900)
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, responseData)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session
        )

        _ = try await client.fetchCoursePackage(
            globalId: 10283,
            roundId: "live-round-1",
            teeBox: "blue",
            ensureGeometry: true
        )
    }

    func testFetchCoursePackageCanQueueGeometryWithoutBlockingFirstOpen() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let responseData = try Data(contentsOf: fixtureURL)
        CapturingURLProtocol.requestHandler = { request in
            let queryItems = URLComponents(
                url: try XCTUnwrap(request.url),
                resolvingAgainstBaseURL: false
            )?.queryItems
            XCTAssertEqual(queryItems?.first { $0.name == "ensure_geometry" }?.value, "false")
            XCTAssertEqual(queryItems?.first { $0.name == "background_geometry" }?.value, "true")
            XCTAssertEqual(request.timeoutInterval, SyncClient.coursePackageTimeoutInterval)
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, responseData)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session
        )

        _ = try await client.fetchCoursePackage(
            globalId: 10283,
            roundId: "live-round-lightweight",
            teeBox: "blue",
            backgroundGeometry: true
        )
    }

    func testFetchColdCoursePackageRetriesTransientTimeout() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let responseData = try Data(contentsOf: fixtureURL)
        var attempts = 0
        CapturingURLProtocol.requestHandler = { request in
            attempts += 1
            XCTAssertEqual(request.timeoutInterval, SyncClient.coursePackageTimeoutInterval)
            if attempts == 1 {
                throw URLError(.timedOut)
            }
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, responseData)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session,
            retrySleep: { _ in }
        )

        _ = try await client.fetchCoursePackage(
            globalId: 10283,
            roundId: "live-round-cold-retry",
            teeBox: "blue",
            backgroundGeometry: true
        )

        XCTAssertEqual(attempts, 2)
    }

    func testFetchHomeCoursePackageCanSkipEventCursor() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let responseData = try Data(contentsOf: fixtureURL)
        CapturingURLProtocol.requestHandler = { request in
            let queryItems = URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false)?.queryItems
            XCTAssertEqual(queryItems?.first { $0.name == "include_event_cursor" }?.value, "false")
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, responseData)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session
        )

        _ = try await client.fetchCoursePackage(
            globalId: 10283,
            roundId: "home-10283",
            teeBox: "blue",
            includeEventCursor: false
        )
    }

    func testFetchEventReplayUsesClientCursorQuery() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = """
        {
          "schema": "ai-caddie-mobile-event-replay-v1",
          "roundId": "live-round-1",
          "clientId": "ios-test",
          "afterSequence": 1,
          "latestServerSequence": 2,
          "nextCursor": 2,
          "eventCount": 1,
          "hasMore": false,
          "events": [
            {
              "serverSequence": 2,
              "idempotencyKey": "batch-2",
              "event": {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": "club-1",
                "roundId": "live-round-1",
                "timestamp": "2026-05-25T00:00:00Z",
                "hole": 1,
                "kind": "club",
                "payload": {"clubName": "8I"}
              }
            }
          ]
        }
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/mobile/rounds/live-round-1/events/replay")
            let queryItems = URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false)?.queryItems
            XCTAssertEqual(queryItems?.first { $0.name == "client_id" }?.value, "ios-test")
            XCTAssertEqual(queryItems?.first { $0.name == "after_sequence" }?.value, "1")
            XCTAssertEqual(queryItems?.first { $0.name == "limit" }?.value, "25")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "admin-secret")
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            adminToken: "admin-secret",
            clientId: "ios-test",
            session: session
        )

        let replay = try await client.fetchEventReplay(roundId: "live-round-1", afterSequence: 1, limit: 25)

        XCTAssertEqual(replay.clientId, "ios-test")
        XCTAssertEqual(replay.events.first?.serverSequence, 2)
        XCTAssertEqual(replay.events.first?.event.eventId, "club-1")
    }

    func testAckEventCursorPostsClientSequence() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = """
        {
          "schema": "ai-caddie-mobile-event-ack-v1",
          "roundId": "live-round-1",
          "clientId": "ios-test",
          "ackedServerSequence": 2,
          "latestServerSequence": 2,
          "pendingEventCount": 0
        }
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/mobile/rounds/live-round-1/events/ack")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "admin-secret")
            let body = try Self.requestBodyData(from: request)
            let decoded = try JSONDecoder().decode(EventCursorAckRequest.self, from: body)
            XCTAssertEqual(decoded.clientId, "ios-test")
            XCTAssertEqual(decoded.serverSequence, 2)
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            adminToken: "admin-secret",
            clientId: "ios-test",
            session: session
        )

        let ack = try await client.ackEventCursor(roundId: "live-round-1", serverSequence: 2)

        XCTAssertEqual(ack.ackedServerSequence, 2)
        XCTAssertEqual(ack.pendingEventCount, 0)
    }

    func testNonSuccessResponseThrowsTypedErrorWithStatusAndBody() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        CapturingURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 500,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, Data(#"{"detail":"boom"}"#.utf8))
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session
        )

        do {
            _ = try await client.postEventBatch([], roundId: "round-1", idempotencyKey: "key-1")
            XCTFail("expected SyncClientError for a 500 response")
        } catch let error as SyncClientError {
            XCTAssertEqual(error, .http(status: 500, body: #"{"detail":"boom"}"#))
        }
    }

    private static func requestBodyData(from request: URLRequest) throws -> Data {
        if let body = request.httpBody {
            return body
        }
        guard let stream = request.httpBodyStream else {
            throw URLError(.zeroByteResource)
        }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 1024)
        while stream.hasBytesAvailable {
            let readCount = stream.read(&buffer, maxLength: buffer.count)
            if readCount < 0 {
                throw stream.streamError ?? URLError(.cannotDecodeContentData)
            }
            if readCount == 0 {
                break
            }
            data.append(buffer, count: readCount)
        }
        return data
    }
}

// CapturingURLProtocol moved to TestURLProtocol.swift (shared with AppleAuthClientTests).
