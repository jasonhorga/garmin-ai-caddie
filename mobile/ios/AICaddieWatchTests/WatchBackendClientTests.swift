import XCTest
@testable import AICaddieWatch

final class WatchBackendClientTests: XCTestCase {
    private func makeClient(adminToken: String? = nil) -> WatchBackendClient {
        WatchBackendClient(baseURL: URL(string: "https://caddie.example")!, adminToken: adminToken)
    }

    func testMapsWatchInputEventsToBackendEventsWithAppleWatchClientId() throws {
        let client = makeClient()

        let score = WatchInputEvent(
            eventId: "e1", roundId: "r1", hole: 3, kind: .score, value: "5",
            createdAt: "2026-06-20T00:00:00Z", fairwayResult: "LEFT"
        )
        let scoreDict = try client.backendEvent(from: score)
        XCTAssertEqual(scoreDict["kind"] as? String, "score")
        XCTAssertEqual(scoreDict["clientId"] as? String, "apple-watch")
        XCTAssertEqual(scoreDict["schema"] as? String, "ai-caddie-live-round-event-v1")
        XCTAssertEqual(scoreDict["hole"] as? Int, 3)
        XCTAssertEqual((scoreDict["payload"] as? [String: Any])?["strokes"] as? Int, 5)
        XCTAssertEqual((scoreDict["payload"] as? [String: Any])?["fairway"] as? String, "left")

        let club = WatchInputEvent(eventId: "e2", roundId: "r1", hole: 3, kind: .club, value: "7I", createdAt: "t", shotType: "approach", lie: "fairway")
        let clubDict = try client.backendEvent(from: club)
        XCTAssertEqual(clubDict["kind"] as? String, "club")
        let clubPayload = clubDict["payload"] as? [String: Any]
        XCTAssertEqual(clubPayload?["clubName"] as? String, "7I")
        XCTAssertEqual(clubPayload?["shotType"] as? String, "approach")
        XCTAssertEqual(clubPayload?["lie"] as? String, "fairway")

        // A distance input is recorded as a club event carrying the new to-pin distance.
        let distance = WatchInputEvent(eventId: "e3", roundId: "r1", hole: 3, kind: .distance, value: "142", createdAt: "t", contextClub: "8I")
        let distDict = try client.backendEvent(from: distance)
        XCTAssertEqual(distDict["kind"] as? String, "club")
        let distPayload = distDict["payload"] as? [String: Any]
        XCTAssertEqual(distPayload?["clubName"] as? String, "8I")
        XCTAssertEqual(distPayload?["distanceToPinM"] as? Double, 142)

        let location = WatchInputEvent(
            eventId: "e4", roundId: "r1", hole: 3, kind: .location,
            value: "40.0454995,116.5461531,5.0", createdAt: "t"
        )
        let locationDict = try client.backendEvent(from: location)
        XCTAssertEqual(locationDict["kind"] as? String, "location")
        let locationPayload = locationDict["payload"] as? [String: Any]
        XCTAssertEqual(locationPayload?["latitude"] as? Double, 40.0454995)
        XCTAssertEqual(locationPayload?["longitude"] as? Double, 116.5461531)
        XCTAssertEqual(locationPayload?["horizontalAccuracyM"] as? Double, 5)
    }

    func testEventBatchRequestCarriesHeadersAndMappedAppleWatchBatch() throws {
        let client = makeClient(adminToken: "secret")
        let event = WatchInputEvent(eventId: "e1", roundId: "r1", hole: 1, kind: .score, value: "4", createdAt: "t")
        let request = try client.makeEventBatchRequest([event], roundId: "r1", idempotencyKey: "batch-1")

        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "batch-1")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "secret")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
        XCTAssertTrue(request.url?.absoluteString.hasSuffix("/api/v2/mobile/rounds/r1/events") ?? false)

        let body = try XCTUnwrap(request.httpBody)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(json["roundId"] as? String, "r1")
        let events = json["events"] as? [[String: Any]]
        XCTAssertEqual(events?.count, 1)
        XCTAssertEqual(events?.first?["clientId"] as? String, "apple-watch")
        XCTAssertEqual(events?.first?["kind"] as? String, "score")
        XCTAssertEqual((events?.first?["payload"] as? [String: Any])?["strokes"] as? Int, 4)
    }

    func testEventBatchRequestOmitsAdminTokenHeaderWhenAbsent() throws {
        let request = try makeClient(adminToken: nil).makeEventBatchRequest(
            [WatchInputEvent(eventId: "e1", roundId: "r1", hole: 1, kind: .putt, value: "2", createdAt: "t")],
            roundId: "r1",
            idempotencyKey: "b"
        )
        XCTAssertNil(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"))
    }

    func testRoundFinishRequestCarriesReviewMetadata() throws {
        let metadata = WatchRoundFinishMetadata(
            courseName: "北京丽宫 · 前九",
            holePars: [4, 5],
            holesCompleted: 2,
            courseGlobalId: 12345
        )

        let request = try makeClient(adminToken: "secret").makeRoundFinishRequest(
            roundId: "round-1",
            metadata: metadata
        )

        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.url?.path, "/api/v2/mobile/rounds/round-1/finish")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "secret")
        let body = try XCTUnwrap(request.httpBody)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        let meta = try XCTUnwrap(json["meta"] as? [String: Any])
        XCTAssertEqual(meta["courseName"] as? String, "北京丽宫 · 前九")
        XCTAssertEqual(meta["holePars"] as? [Int], [4, 5])
        XCTAssertEqual(meta["holesCompleted"] as? Int, 2)
        XCTAssertEqual(meta["courseGlobalId"] as? Int, 12345)
    }

    func testEventBatchRequestPrefersBearerSessionTokenOverAdminToken() throws {
        // round-13 watch-auth: the phone forwards its live Apple session token; the watch authenticates
        // as the signed-in member/owner with a Bearer header (mirroring the phone's applyAICaddieAuth),
        // and does NOT also send the admin token alongside it.
        let client = WatchBackendClient(
            baseURL: URL(string: "https://caddie.example")!,
            adminToken: "admin-secret",
            sessionToken: "session-jwt"
        )
        let request = try client.makeEventBatchRequest(
            [WatchInputEvent(eventId: "e1", roundId: "r1", hole: 1, kind: .score, value: "4", createdAt: "t")],
            roundId: "r1",
            idempotencyKey: "b"
        )
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer session-jwt")
        XCTAssertNil(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"))
    }

    func testEventBatchRequestFallsBackToAdminTokenWhenSessionTokenExpired() throws {
        // An expired Bearer never authenticates (mirrors SessionStore.liveToken returning nil), so the
        // watch falls back to the admin token (the DEBUG/CI path) rather than sending a stale token.
        let client = WatchBackendClient(
            baseURL: URL(string: "https://caddie.example")!,
            adminToken: "admin-secret",
            sessionToken: "session-jwt",
            sessionTokenExpiresAt: Date().addingTimeInterval(-60)
        )
        let request = try client.makeEventBatchRequest(
            [WatchInputEvent(eventId: "e1", roundId: "r1", hole: 1, kind: .score, value: "4", createdAt: "t")],
            roundId: "r1",
            idempotencyKey: "b"
        )
        XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "admin-secret")
    }

    func testParseEventResultDecodesAcceptedAndSequence() throws {
        let client = makeClient()
        let data = try JSONSerialization.data(withJSONObject: [
            "accepted": 1,
            "duplicate": false,
            "acceptedEventIds": ["event-1"],
            "duplicateEventIds": ["event-0"],
            "serverSequence": 7,
        ])
        let result = client.parseEventResult(data)
        XCTAssertEqual(result.accepted, 1)
        XCTAssertFalse(result.duplicate)
        XCTAssertEqual(result.acceptedEventIds, ["event-1"])
        XCTAssertEqual(result.duplicateEventIds, ["event-0"])
        XCTAssertEqual(result.acknowledgedEventIds, ["event-1", "event-0"])
        XCTAssertEqual(result.serverSequence, 7)

        // Missing/garbled fields degrade to safe defaults rather than throwing.
        XCTAssertEqual(client.parseEventResult(Data()).acknowledgedEventIds, [])
        XCTAssertEqual(client.parseEventResult(Data()).serverSequence, 0)
    }

    func testCourseDownloadRequestsReuseExistingAuthenticatedMobileEndpoints() throws {
        let client = WatchBackendClient(
            baseURL: URL(string: "https://caddie.example")!,
            adminToken: "admin-secret",
            sessionToken: "member-session"
        )

        let options = try client.makeCourseOptionsRequest()
        XCTAssertEqual(options.url?.path, "/api/v2/mobile/courses/options")
        XCTAssertEqual(options.value(forHTTPHeaderField: "Authorization"), "Bearer member-session")

        let search = try client.makeCourseSearchRequest(name: "观澜湖")
        XCTAssertEqual(search.url?.path, "/api/v2/courses/search")
        XCTAssertEqual(
            URLComponents(url: try XCTUnwrap(search.url), resolvingAgainstBaseURL: false)?
                .queryItems?.first(where: { $0.name == "name" })?.value,
            "观澜湖"
        )
        XCTAssertEqual(search.value(forHTTPHeaderField: "Authorization"), "Bearer member-session")

        let tees = try client.makeCourseTeesRequest(globalId: 31870)
        XCTAssertEqual(tees.url?.path, "/api/v2/courses/31870/tees")
        XCTAssertEqual(tees.value(forHTTPHeaderField: "Authorization"), "Bearer member-session")

        let package = try client.makeCoursePackageRequest(
            globalId: 31669,
            roundId: "watch-round-1",
            teeBox: "White",
            backGlobalId: 31670,
            ensureGeometry: true
        )
        XCTAssertEqual(package.url?.path, "/api/v2/mobile/courses/31669/package")
        let packageQuery = try XCTUnwrap(URLComponents(url: try XCTUnwrap(package.url), resolvingAgainstBaseURL: false))
        XCTAssertEqual(packageQuery.queryItems?.first(where: { $0.name == "round_id" })?.value, "watch-round-1")
        XCTAssertEqual(packageQuery.queryItems?.first(where: { $0.name == "tee_box" })?.value, "White")
        XCTAssertEqual(packageQuery.queryItems?.first(where: { $0.name == "back_global_id" })?.value, "31670")
        XCTAssertEqual(packageQuery.queryItems?.first(where: { $0.name == "ensure_geometry" })?.value, "true")
        XCTAssertEqual(packageQuery.queryItems?.first(where: { $0.name == "client_id" })?.value, "apple-watch")

        let prep = try client.makeCoursePrepRequest(globalId: 31669, localHoles: [1, 2, 9])
        XCTAssertEqual(prep.url?.path, "/api/v2/courses/31669/prep")
        let prepQuery = try XCTUnwrap(URLComponents(url: try XCTUnwrap(prep.url), resolvingAgainstBaseURL: false))
        XCTAssertEqual(prepQuery.queryItems?.filter { $0.name == "holes" }.compactMap(\.value), ["1", "2", "9"])
        XCTAssertEqual(prepQuery.queryItems?.first(where: { $0.name == "render" })?.value, "true")
    }

    func testCoursePayloadsDecodeOnlyWatchStartFacts() throws {
        let client = makeClient()
        let options = try client.decodeCourseOptions(Data(
            #"{"schema":"ai-caddie-mobile-course-options-v1","dataMode":"real","total":1,"courses":[{"globalId":31669,"name":"北京丽宫","roundCount":4,"holes":18,"teeBox":"Blue","geometryCoverage":"ready","sourceRefs":[],"venueName":"北京丽宫","segmentLabel":null,"segmentHoles":18,"tees":["Blue","White"]}],"generatedAt":"2026-07-26T00:00:00Z"}"#.utf8
        ))
        XCTAssertEqual(options, [
            WatchCourseOption(
                globalId: 31669,
                name: "北京丽宫",
                holes: 18,
                teeBox: "Blue",
                venueName: "北京丽宫",
                segmentLabel: nil,
                segmentHoles: 18,
                tees: ["Blue", "White"],
                roundCount: 4
            )
        ])

        let package = try client.decodeCoursePackage(Data(
            #"{"schema":"ai-caddie-live-round-package-v1","roundId":"watch-round-1","course":{"globalId":31669,"name":"北京丽宫","teeBox":"Blue"},"holes":[{"number":1,"par":4,"yards":404,"geometryCoverage":"ready","sourceGlobalId":31669,"sourceLocalHole":1}],"ignored":{"large":"payload"}}"#.utf8
        ))
        XCTAssertEqual(package.roundId, "watch-round-1")
        XCTAssertEqual(package.course.name, "北京丽宫")
        XCTAssertEqual(package.holes.first?.yards, 404)
        XCTAssertEqual(package.holes.first?.sourceLocalHole, 1)

        let matches = try client.decodeCourseSearch(Data(
            #"{"schema":"ai-caddie-course-search-v1","query":"观澜湖","matches":[{"globalId":31870,"name":"Mission Hills ~ A","holes":9,"city":"深圳","province":"广东","ratio":0.92}]}"#.utf8
        ))
        XCTAssertEqual(matches, [
            WatchCourseSearchMatch(
                globalId: 31870,
                name: "Mission Hills ~ A",
                holes: 9,
                city: "深圳",
                province: "广东",
                ratio: 0.92
            )
        ])
        XCTAssertEqual(matches.first?.courseOption?.segmentLabel, "A")
        XCTAssertEqual(matches.first?.courseOption?.venueName, "Mission Hills")

        let incompleteMatches = try client.decodeCourseSearch(Data(
            #"{"schema":"ai-caddie-course-search-v1","query":"unknown","matches":[{"globalId":39999,"name":"Unclassified Course","holes":null,"city":null,"province":null,"ratio":0.5}]}"#.utf8
        ))
        XCTAssertEqual(incompleteMatches.count, 1)
        XCTAssertNil(incompleteMatches.first?.holes)
        XCTAssertNil(incompleteMatches.first?.courseOption)

        let tees = try client.decodeCourseTees(Data(
            #"{"schema":"ai-caddie-course-tees-v1","globalId":31870,"defaultTeeBox":"blue","tees":[{"teeBox":"blue","name":"Blue","set":2,"yards":6412,"holeCount":18,"default":true},{"teeBox":"white","name":"White","set":3,"yards":6020,"holeCount":18,"default":false}]}"#.utf8
        ))
        XCTAssertEqual(tees.map(\.teeBox), ["blue", "white"])
        XCTAssertEqual(tees.first?.yards, 6412)
        XCTAssertTrue(tees.first?.isDefault == true)
    }
}
