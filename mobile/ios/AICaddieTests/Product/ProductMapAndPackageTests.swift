import CoreLocation
import XCTest
@testable import AICaddie
import AICaddieDomain

final class ProductMapAndPackageTests: XCTestCase {
    func test_j4_2_cached_package_lifecycle_and_revision_adoption() throws {
        // Prepared at midnight; stale at +24 h; expires at +48 h. Boundary instants are inclusive.
        let status: OfflinePackageStatus = try ProductSharedVectors.decode([
            "state": "ready", "preparedAt": "2026-10-01T00:00:00Z", "expiresAt": "2026-10-03T00:00:00Z",
            "cachePolicy": ["staleAfterHours": 24, "expiresAfterHours": 48],
        ])
        for (date, expected) in [
            ("2026-10-01T23:59:59Z", OfflinePackageCacheState.ready),
            ("2026-10-02T00:00:00Z", .stale), ("2026-10-03T00:00:00Z", .expired),
        ] {
            XCTAssertEqual(status.cacheState(now: try XCTUnwrap(ISO8601DateFormatter().date(from: date))), expected, date)
        }
        let job = PrepCourseDownloadRecord(course: ProductInputs.course(81001, venue: "Example", holes: 18),
            phase: .downloading, preparedHoles: 18, downloadedHoles: 7, totalHoles: 18,
            requiredGeometryRevisions: ["81001:8": "synthetic-r2"])
        let precise = try ProductInputs.prep()
        let partial = try ProductInputs.prep(coverage: "partial")
        XCTAssertTrue(CoursePrepHoleAdoptionPolicy.shouldAdopt(current: partial, incoming: precise), "new map replaces route")
        XCTAssertFalse(CoursePrepHoleAdoptionPolicy.shouldAdopt(current: precise, incoming: partial), "late partial cannot erase complete map")
        var input = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(partial)) as? [String: Any])
        input["geometryRevision"] = "synthetic-r2"
        let replacement: CoursePrepHole = try ProductSharedVectors.decode(input)
        XCTAssertTrue(CoursePrepHoleAdoptionPolicy.shouldAdopt(current: precise, incoming: replacement, authoritativeRevision: "synthetic-r2"))
        XCTAssertFalse(CoursePrepHoleAdoptionPolicy.shouldAdopt(current: replacement, incoming: precise, authoritativeRevision: "synthetic-r2"))
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        try store.savePrepCourseDownloads([job])
        let resumed = try XCTUnwrap(OfflineStore(directoryURL: directory).loadPrepCourseDownloads().first)
        XCTAssertEqual(resumed.phase, .downloading, "restart resumes unfinished job")
        XCTAssertEqual(resumed.downloadedHoles, 7, "seven finished maps retained")
        XCTAssertEqual(resumed.requiredGeometryRevisions, ["81001:8": "synthetic-r2"])
        var packageInput = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(ProductInputs.package())) as? [String: Any])
        packageInput["coursePrep"] = ["schema": "ai-caddie-course-prep-v1", "globalId": 81001,
            "holes": [try JSONSerialization.jsonObject(with: JSONEncoder().encode(precise))]]
        let package: LiveRoundPackage = try ProductSharedVectors.decode(packageInput)
        XCTAssertFalse(package.hasCompleteOfflineCoursePrep, "one prepared map is a partial package")
        var completeInput = packageInput
        let firstPrep = try XCTUnwrap((packageInput["coursePrep"] as? [String: Any])?["holes"] as? [[String: Any]]).first!
        completeInput["coursePrep"] = ["schema": "ai-caddie-course-prep-v1", "globalId": 81001,
            "holes": (1...18).map { number -> [String: Any] in var row = firstPrep; row["hole"] = number; return row }]
        let complete: LiveRoundPackage = try ProductSharedVectors.decode(completeInput)
        XCTAssertTrue(complete.hasCompleteOfflineCoursePrep, "all eighteen precise routes installed")
        try store.saveRoundPackage(package)
        // No client/network exists on the read path: a fresh store can recover the installed facts.
        let restored = try XCTUnwrap(OfflineStore(directoryURL: directory).loadRoundPackage(roundId: package.roundId))
        XCTAssertEqual(restored.holes.map(\.sourceLocalHole), Array(1...18), "unreachable server and restart")
        input = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(package)) as? [String: Any])
        XCTAssertEqual(restored.coursePrep?.holes.first?.map?.overlay.w, 300, "installed overlay survives no server")
        let files = try FileManager.default.subpathsOfDirectory(atPath: directory.path)
            .filter { $0.hasPrefix("packages/") && $0.hasSuffix(".json") }
        XCTAssertEqual(files.count, 1)
        let cached = directory.appendingPathComponent(try XCTUnwrap(files.first))
        try Data("{bad".utf8).write(to: cached)
        XCTAssertNil(try store.loadRoundPackage(roundId: package.roundId), "corrupt cache rejected")
        XCTAssertFalse(FileManager.default.fileExists(atPath: cached.path), "invalid package evicted for reacquisition")
        try store.saveRoundPackage(package)
        XCTAssertNotNil(try store.loadRoundPackage(roundId: package.roundId), "fresh package installs after corruption")
        for (name, key) in [("negative-id", "-1:front"), ("unknown-half", "81001:side"), ("three-loops", "81001:front+81001:back+81001:front")] {
            XCTAssertNil(RoundLoopEntry.entries(loopKey: key), name)
        }
        input["schema"] = "ai-caddie-live-round-package-v1"
        let old: LiveRoundPackage = try ProductSharedVectors.decode(input)
        XCTAssertThrowsError(try OfflineStore(directoryURL: directory).saveRoundPackage(old), "old package must be reacquired")
    }

    func test_j4_5_map_degradation_and_upgrade_preserve_physical_points() throws {
        let ready = try ProductInputs.prep()
        let partial = try ProductInputs.prep(coverage: "partial")
        let empty = try ProductInputs.prep(coverage: "missing", route: false)
        let rows: [(String, CoursePrepHole?, Bool, LiveMapDisplayState)] = [
            ("precise", ready, false, .precise), ("route-downloading", partial, true, .factualPending),
            ("offline-route", partial, false, .factual), ("no-route", empty, true, .waiting),
            ("no-hole", nil, false, .waiting),
        ]
        for (id, prep, pending, expected) in rows {
            XCTAssertEqual(LiveMapDisplayState.resolve(prep: prep, pending: pending), expected, id)
        }
        XCTAssertEqual(LiveMapDisplayState.resolvePrep(prep: ready, hasLocalTopo: true, isStale: false, downloadActive: false), .precise)
        XCTAssertEqual(LiveMapDisplayState.resolvePrep(prep: ready, hasLocalTopo: true, isStale: true, downloadActive: true), .factualPending)
        XCTAssertEqual(LiveMapDisplayState.resolvePrep(prep: partial, hasLocalTopo: false, isStale: false, downloadActive: false), .factual)
        XCTAssertEqual(LiveMapDisplayState.resolvePrep(prep: empty, hasLocalTopo: false, isStale: false, downloadActive: true), .waiting)
        let old = try XCTUnwrap(ready.map?.overlay)
        let new = try XCTUnwrap(ProductInputs.prep(scale: 2).map?.overlay)
        // Same physical station/lateral offset in a map with twice the pixels/metre.
        for (id, point, expected) in [
            ("target", CGPoint(x: 110, y: 200), CGPoint(x: 220, y: 400)),
            ("flag", CGPoint(x: 100, y: 50), CGPoint(x: 200, y: 100)),
        ] {
            let transferred = try XCTUnwrap(LiveMapCarryOver.transfer(point, from: old, to: new), id)
            XCTAssertEqual(transferred.x, expected.x, accuracy: 0.001, id)
            XCTAssertEqual(transferred.y, expected.y, accuracy: 0.001, id)
        }
        var session = PrepHoleMapSession()
        session.select(hole: 1)
        session.selectPlan(2, planCount: 3)
        session.viewport = HoleMapViewportState(zoomScale: 2.5, offset: CGSize(width: 35, height: -20))
        for state in ["route", "topo-arrived", "revision-replaced"] {
            session.adopt(holeNumbers: [1, 2], planCount: 3)
            XCTAssertEqual(session.holeNumber, 1, state)
            XCTAssertEqual(session.selectedPlanIndex, 2, state)
            XCTAssertEqual(session.viewport.zoomScale, 2.5, state)
            XCTAssertEqual(session.viewport.offset, CGSize(width: 35, height: -20), state)
        }
        func hazard(_ id: String, _ station: Double, kind: String = "water") -> LiveHazardDisplayItem {
            LiveHazardDisplayItem(id: id, kind: kind, label: "Example obstacle", frontYards: 110, backYards: 132,
                frontPx: [100, 250], backPx: [100, 230], outlinePx: [], frontRouteM: station, backRouteM: station + 20)
        }
        let before = [hazard("old", 100)]
        for (name, after, selected) in [
            ("same-physical-new-id", [hazard("new", 105)], Optional("new")),
            ("different-obstacle", [hazard("old", 130)], nil),
            ("different-kind", [hazard("old", 100, kind: "bunker")], nil),
        ] {
            XCTAssertEqual(LiveMapCarryOver.hazardSelection(current: "old", previous: before, next: after), selected, name)
        }
    }

    func test_j5_4_green_edges_and_live_position_ranges() throws {
        // At 1 px/m the rectangular green is 20m wide x 40m deep. The centred flag
        // is 20m from front/back and 10m from either side -> 22/22/11/11 yards.
        let rectangle: [[Double]] = [[0, 0], [20, 0], [20, 40], [0, 40]]
        // A centred notch removes the upper middle. Flag at (5,20), image-up axis:
        // first forward intersection y=10, not the distant top lobe y=0.
        let concave: [[Double]] = [[0, 0], [4, 0], [4, 10], [6, 10], [6, 0], [10, 0], [10, 40], [0, 40]]
        for (id, outline, flag, expected) in [
            ("rectangle", rectangle, [10.0, 20.0], [22, 22, 11, 11]),
            ("concave-notch", concave, [5.0, 20.0], [22, 11, 5, 5]),
            ("on-edge", rectangle, [0.0, 20.0], [22, 22, 0, 22]),
        ] {
            let edges = try XCTUnwrap(GreenEdgeDistances.resolve(flagPx: flag, outlinePx: outline,
                referencePx: nil, pixelsPerMetre: 1), id)
            XCTAssertEqual([edges.front.yards, edges.back.yards, edges.left.yards, edges.right.yards], expected, id)
        }
        // Great-circle distances on the equator: .001 degrees = 111.1949m = 121.604 yd.
        // After moving north by .001 degrees every F/M/B distance falls by 122 yards.
        let positions: [(String, Double, [Int])] = [
            ("tee", 0, [243, 365, 486]), ("after-tee", 0.001, [122, 243, 365]),
        ]
        for (id, latitude, expected) in positions {
            let actual = [0.002, 0.003, 0.004].map { GeoDistance.yards(from: latitude, 0, to: $0, 0) }
            XCTAssertEqual(actual, expected.map(Optional.some), id)
        }
        let clamped = try XCTUnwrap(LivePolygonGeometry.nearestPoint(CGPoint(x: 30, y: 20), on: rectangle.map { CGPoint(x: $0[0], y: $0[1]) }))
        XCTAssertEqual(clamped, CGPoint(x: 20, y: 20), "flag dragged beyond right edge attaches to boundary")
        XCTAssertNil(GeoDistance.yards(from: 0, 0, to: nil, nil))
        XCTAssertNil(GreenEdgeDistances.resolve(flagPx: [10, 20], outlinePx: [], referencePx: nil, pixelsPerMetre: 1))
    }

    func test_j5_5_saved_gps_and_accuracy_or_unknown_score_position() throws {
        for (id, accuracy) in [("accurate", 5.0), ("poor", 120.0)] {
            let event = LiveRoundEventBuilder(roundId: "synthetic", idFactory: { id }).makeLocationEvent(
                hole: 1, coordinate: CLLocationCoordinate2D(latitude: 0.001, longitude: 0.002), horizontalAccuracyM: accuracy)
            XCTAssertEqual(event.payload["latitude"], .number(0.001), id)
            XCTAssertEqual(event.payload["longitude"], .number(0.002), id)
            XCTAssertEqual(event.payload["horizontalAccuracyM"], .number(accuracy), id)
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: directory) }
            let store = OfflineStore(directoryURL: directory)
            try store.appendEvent(event)
            try store.appendEvent(LiveRoundEventBuilder(roundId: "synthetic").makeScoreEvent(hole: 1, strokes: 4))
            let restored = try XCTUnwrap(store.restoreLiveRoundState(roundId: "synthetic", package: ProductInputs.package()).holeState(for: 1))
            XCTAssertEqual(restored.score, 4, id + " score remains saveable")
            XCTAssertEqual(restored.horizontalAccuracyM, accuracy, id + " precision remains visible to the view")
            if accuracy == 5 {
                XCTAssertEqual(restored.latitude, 0.001, id)
                XCTAssertEqual(restored.longitude, 0.002, id)
            } else {
                XCTAssertNil(restored.latitude, id + " location must be unknown")
                XCTAssertNil(restored.longitude, id + " location must be unknown")
            }
        }
        // Scoring without a location still writes the same three score facts, and no invented GPS.
        for phoneShots in [0, 2] {
            let draft = LiveScoreDraft(hole: 1, par: 4, phoneShotCount: phoneShots)
            let events = LiveScoreSubmission.events(roundId: "synthetic", draft: draft, note: "", timestamp: "2026-10-23T00:00:00Z")
            XCTAssertEqual(events.map(\.kind), [.score, .putt, .penalty], "no GPS, shots=\(phoneShots)")
            XCTAssertTrue(events.allSatisfy { $0.payload["latitude"] == nil && $0.payload["longitude"] == nil })
        }
    }

    func test_j8_3_optional_sections_old_and_future_data_decode_without_losing_facts() throws {
        let rows: [(String, [String: Any], Int?, Bool)] = [
            ("old", ["hole": 1, "par": 4, "par_source": "synthetic", "blue_yards": 328, "route_len_m": 300, "steps": [], "cautions": [], "hazards": [:]], nil, false),
            ("new-unknown-fields", ["hole": 1, "par": 4, "par_source": "synthetic", "blue_yards": 328, "route_len_m": 300, "steps": [], "cautions": [], "hazards": [:], "teeYards": 300, "future": ["new": true]], 300, false),
            ("unknown-outline", ["hole": 1, "par": 4, "par_source": "synthetic", "blue_yards": 328, "route_len_m": 300, "steps": [], "cautions": [], "hazards": [:], "fairwayOutline": ["version": 999, "polygons": []]], nil, false),
        ]
        for (id, input, tee, hasOutline) in rows {
            let prep: CoursePrepHole = try ProductSharedVectors.decode(input)
            XCTAssertEqual(prep.hole, 1, id)
            XCTAssertEqual(prep.par, 4, id)
            XCTAssertEqual(prep.teeYards, tee, id)
            XCTAssertEqual(prep.fairwayOutline != nil, hasOutline, id)
            XCTAssertNil(prep.greenDistances, id)
        }
        // A broken optional analytics section must not erase the valid score summary.
        let stats: MobileStats = try ProductSharedVectors.decode([
            "summary": ["totalRounds": 3, "average18": 82], "scoring": "future-shape", "future": true,
        ])
        XCTAssertEqual(stats.summary?.totalRounds, 3)
        XCTAssertEqual(stats.summary?.average18, 82)
        XCTAssertNil(stats.scoring)
    }
}
