#if !SWIFT_PACKAGE
import Foundation
import XCTest
@testable import AICaddie

@MainActor
final class C33PackageTests: XCTestCase {
    private func packageJSON() throws -> [String: Any] {
        let package = try c33Package()
        return try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(package)) as? [String: Any]
        )
    }

    private func decodePackage(_ json: [String: Any]) throws -> LiveRoundPackage {
        try JSONDecoder().decode(
            LiveRoundPackage.self,
            from: JSONSerialization.data(withJSONObject: json)
        ).validatedRoundIdentity()
    }

    private func replaceFirstHole(_ json: inout [String: Any], with fields: [String: Any]) throws {
        var holes = try XCTUnwrap(json["holes"] as? [[String: Any]])
        var first = try XCTUnwrap(holes.first)
        for (key, value) in fields { first[key] = value }
        holes[0] = first
        json["holes"] = holes
    }

    func testPackageHoleDecodesC33sFieldsAndKeepsOldPayloadCompatible() throws {
        let old = try decodePackage(packageJSON())
        let oldHole = try XCTUnwrap(old.holes.first)
        XCTAssertNil(oldHole.geometryState)
        XCTAssertNil(oldHole.retryAfterEpoch)
        XCTAssertNil(oldHole.garminRaster)
        XCTAssertNil(oldHole.topoAvailable)
        XCTAssertNil(oldHole.topoRevision)

        var json = try packageJSON()
        try replaceFirstHole(&json, with: [
            "geometryState": "pending",
            "retryAfterEpoch": 1_900_000_123.5,
            "garminRaster": [
                "imageUrl": "/api/v2/courses/32850/holes/1/garmin-raster.jpg",
                "metadataUrl": "/api/v2/courses/32850/holes/1/garmin-raster.json",
            ],
            "topoAvailable": true,
            "topoRevision": "topo-r1",
        ])
        let enriched = try decodePackage(json)
        let hole = try XCTUnwrap(enriched.holes.first)
        XCTAssertEqual(hole.geometryState, "pending")
        XCTAssertEqual(hole.retryAfterEpoch, 1_900_000_123.5)
        XCTAssertEqual(hole.garminRaster?.imageUrl, "/api/v2/courses/32850/holes/1/garmin-raster.jpg")
        XCTAssertEqual(hole.garminRaster?.metadataUrl, "/api/v2/courses/32850/holes/1/garmin-raster.json")
        XCTAssertEqual(hole.topoAvailable, true)
        XCTAssertEqual(hole.topoRevision, "topo-r1")
    }

    func testTopoAvailableRevisionCanDrawWithoutPrepReady() throws {
        var json = try packageJSON()
        try replaceFirstHole(&json, with: [
            "geometryCoverage": "missing",
            "geometryRevision": NSNull(),
            "topoAvailable": true,
            "topoRevision": "topo-r1",
        ])
        json["coursePrep"] = NSNull()
        let package = try decodePackage(json)
        let hole = try XCTUnwrap(package.holes.first)
        let url = LiveTopoAvailability.url(
            hole: hole,
            prep: nil,
            localURL: nil,
            baseURL: URL(string: "https://c33.example.test")!
        )
        XCTAssertNotNil(url)
        XCTAssertEqual(
            URLComponents(url: try XCTUnwrap(url), resolvingAgainstBaseURL: false)?
                .queryItems?.first(where: { $0.name == "r" })?.value,
            "topo-r1"
        )
    }

    func testPendingGeometryRetriesOnlyAfterServerDeadlineAndSameRound() throws {
        var json = try packageJSON()
        try replaceFirstHole(&json, with: [
            "geometryState": "pending",
            "retryAfterEpoch": 1_900_000_123.5,
        ])
        let package = try decodePackage(json)
        let hole = try XCTUnwrap(package.holes.first)
        XCTAssertFalse(PackageGeometryRetryPolicy.shouldRefresh(
            hole: hole,
            nowEpoch: 1_900_000_123,
            packageRoundId: package.roundId,
            activeRoundId: package.roundId
        ))
        XCTAssertTrue(PackageGeometryRetryPolicy.shouldRefresh(
            hole: hole,
            nowEpoch: 1_900_000_123.5,
            packageRoundId: package.roundId,
            activeRoundId: package.roundId
        ))
        XCTAssertFalse(PackageGeometryRetryPolicy.shouldRefresh(
            hole: hole,
            nowEpoch: 1_900_000_123.5,
            packageRoundId: package.roundId,
            activeRoundId: "another-round"
        ))
    }

    func testPendingPackageRefreshesAfterRetryDateOnTheActiveRound() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c33-package-retry.example.test")!, session: session)
        let model = c33Model(OfflineStore(directoryURL: directory), client)
        var pendingJSON = try packageJSON()
        pendingJSON["roundId"] = "c33-package-retry"
        try replaceFirstHole(&pendingJSON, with: [
            "geometryState": "pending",
            "retryAfterEpoch": Date().timeIntervalSince1970 - 1,
            "garminRaster": [
                "imageUrl": "/api/v2/courses/32850/holes/1/garmin-raster.jpg",
                "metadataUrl": "/api/v2/courses/32850/holes/1/garmin-raster.json",
            ],
        ])
        var readyJSON = try packageJSON()
        readyJSON["roundId"] = "c33-package-retry"
        try replaceFirstHole(&readyJSON, with: ["geometryState": "ready", "retryAfterEpoch": NSNull()])
        let pendingData = try JSONSerialization.data(withJSONObject: pendingJSON)
        let readyData = try JSONSerialization.data(withJSONObject: readyJSON)
        let retryRequest = expectation(description: "pending package is retried")
        let lock = NSLock()
        var packageRefreshes = 0
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.contains("/api/v2/mobile/courses/32850/package") {
                proto.reply(200, pendingData)
                return
            }
            if path.contains("/api/v2/mobile/rounds/") && path.hasSuffix("/package") {
                lock.lock(); packageRefreshes += 1; lock.unlock()
                retryRequest.fulfill()
                proto.reply(200, readyData)
                return
            }
            proto.reply(404)
        })
        defer {
            client.invalidateForTesting()
            session.invalidateAndCancel()
            C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        let start = Task {
            await model.prepareCourseRound(
                roundId: "c33-package-retry",
                teeBox: "blue",
                loops: [.init(globalId: 32850, half: "all")]
            )
        }
        await fulfillment(of: [retryRequest], timeout: 2)
        await start.value
        lock.lock(); let observed = packageRefreshes; lock.unlock()
        XCTAssertEqual(observed, 1)
    }

    func testDegradedSingleflightPackageNeverReplacesCachedCompletePackage() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        defer { try? FileManager.default.removeItem(at: directory) }
        let complete = try c33Package()
        try store.saveRoundPackage(complete)

        var json = try packageJSON()
        json["offlinePackageStatus"] = [
            "state": "degraded",
            "cacheable": false,
            "degradationReason": "singleflight_timeout",
            "preparedAt": "2026-01-01T00:00:00Z",
            "expiresAt": "2027-01-01T00:00:00Z",
            "cachePolicy": ["staleAfterHours": 24, "expiresAfterHours": 720],
        ]
        let degraded = try decodePackage(json)
        XCTAssertTrue(degraded.offlinePackageStatus.mustNotCache)
        let effective = try store.saveRoundPackage(degraded)
        XCTAssertEqual(effective, complete)
        XCTAssertEqual(try store.loadRoundPackage(roundId: complete.roundId), complete)

        let emptyDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let emptyStore = OfflineStore(directoryURL: emptyDirectory)
        defer { try? FileManager.default.removeItem(at: emptyDirectory) }
        _ = try emptyStore.saveRoundPackage(degraded)
        XCTAssertNil(try emptyStore.loadRoundPackage(roundId: degraded.roundId))
    }
}
#endif
