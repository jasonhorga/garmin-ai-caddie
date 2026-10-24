#if !SWIFT_PACKAGE && canImport(UIKit)
import Combine
import UIKit
import XCTest
@testable import AICaddie

@MainActor
final class C33DrawingTests: XCTestCase {
    func testPackageReadyTopoDoesNotWaitForPartialPrep() throws {
        let package = try c33Package()
        let hole = try XCTUnwrap(package.holes.first)
        let prep = try XCTUnwrap(package.coursePrep?.holes.first)
        XCTAssertEqual(hole.geometryCoverage, .ready)
        XCTAssertEqual(prep.geometryCoverage, "partial")
        // C33: the package's revision-bound topo is already usable while lightweight prep is partial.
        let url = LiveTopoAvailability.url(
            hole: hole, prep: prep, localURL: nil, baseURL: URL(string: "https://c33.example.test")!
        )
        XCTAssertNotNil(url)
        XCTAssertEqual(URLComponents(url: try XCTUnwrap(url), resolvingAgainstBaseURL: false)?
            .queryItems?.first(where: { $0.name == "r" })?.value, hole.geometryRevision)
        XCTAssertEqual(LiveMapDisplayState.resolveLive(.init(
            coverage: LiveTopoAvailability.coverage(hole: hole, prep: prep),
            preciseTopoImageReady: true, garminRaster: nil, garminImageFailed: true,
            hasCachedPreciseTopo: false
        )), .precise)
    }

    func testCachedTopoWinsEvenWithoutReadyCoverage() {
        // C33: an already downloaded bitmap is usable without waiting for prep readiness.
        XCTAssertEqual(LiveMapDisplayState.resolveLive(.init(
            coverage: "partial", preciseTopoImageReady: true, garminRaster: nil,
            garminImageFailed: true, hasCachedPreciseTopo: true
        )), .precise)
    }

    func testPartialPrepDrawsOverlayOnlyWhenTopoPixelFrameMatches() throws {
        let package = try c33Package()
        let hole = try XCTUnwrap(package.holes.first)
        let prep = try XCTUnwrap(package.coursePrep?.holes.first)
        // The fixture records identical 678x1060 projection/overlay dimensions and revision.
        XCTAssertTrue(LiveTopoAvailability.overlayCompatible(hole: hole, prep: prep))
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(prep)) as? [String: Any])
        object["geometryRevision"] = "different-revision"
        let mismatched = try JSONDecoder().decode(
            CoursePrepHole.self, from: JSONSerialization.data(withJSONObject: object)
        )
        XCTAssertFalse(LiveTopoAvailability.overlayCompatible(hole: hole, prep: mismatched))
    }

    func testGarminRasterKeepsOverlayAndTargetWhenPrepProjectionMissing() throws {
        let package = try c33Package()
        let hole = try XCTUnwrap(package.holes.first)
        let originalPrep = try XCTUnwrap(package.coursePrep?.holes.first)
        let originalProjection = try XCTUnwrap(originalPrep.holeImageProjection)
        let refs = try XCTUnwrap(originalProjection.refs)

        // A cold start can have the Garmin descriptor while lightweight prep has no precise
        // CourseView pixel frame yet. Build that payload shape without reaching into view state.
        var prepJSON = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(originalPrep)) as? [String: Any]
        )
        prepJSON.removeValue(forKey: "holeImageProjection")
        let prepWithoutProjection = try JSONDecoder().decode(
            CoursePrepHole.self,
            from: JSONSerialization.data(withJSONObject: prepJSON)
        )
        let garminProjection = CoursePrepHoleImageProjection(
            available: true, widthPx: 1242, heightPx: 1920, refs: refs
        )
        let garmin = GarminRasterResponse(
            available: true,
            imageUrl: "https://c33.example.test/garmin.jpg",
            projection: GarminRasterProjection(
                widthPx: 1242, heightPx: 1920, refs: refs
            )
        )
        let state = LiveMapDisplayState.resolveLive(.init(
            coverage: LiveTopoAvailability.coverage(hole: hole, prep: prepWithoutProjection),
            preciseTopoImageReady: false,
            garminRaster: garmin,
            garminImageFailed: false,
            hasCachedPreciseTopo: false
        ))
        XCTAssertEqual(state, .garminRaster)
        XCTAssertTrue(LiveTopoAvailability.overlayAllowed(
            displayState: state, hole: hole, prep: prepWithoutProjection
        ))
        XCTAssertEqual(
            LiveMapDisplaySelection.projection(
                for: state, precise: prepWithoutProjection.holeImageProjection,
                garmin: garminProjection
            ),
            garminProjection
        )
        let overlay = LiveMapDisplaySelection.overlay(
            for: state,
            precise: prepWithoutProjection.resolvedMapOverlay,
            preciseProjection: prepWithoutProjection.holeImageProjection,
            garminProjection: garminProjection
        )
        XCTAssertNotNil(overlay)
        XCTAssertNotNil(LiveMapDisplaySelection.validTargetPixel(
            CGPoint(x: 150, y: 210), in: overlay
        ))

        var mismatchedJSON = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(originalPrep)) as? [String: Any]
        )
        mismatchedJSON["geometryCoverage"] = "partial"
        mismatchedJSON["geometryRevision"] = "different-revision"
        let mismatched = try JSONDecoder().decode(
            CoursePrepHole.self,
            from: JSONSerialization.data(withJSONObject: mismatchedJSON)
        )
        XCTAssertFalse(LiveTopoAvailability.overlayAllowed(
            displayState: .precise, hole: hole, prep: mismatched
        ))
    }

    func testFourthGarminAttemptDisplaysImageAndBackoffStaysCapped() async throws {
        let url = URL(string: "https://c33.example.test/\(UUID().uuidString).jpg")!
        let image = UIGraphicsImageRenderer(size: CGSize(width: 20, height: 30)).image { _ in UIColor.green.setFill(); UIRectFill(CGRect(x: 0, y: 0, width: 20, height: 30)) }
        var now: UInt64 = 0
        var attempts = 0
        var delays: [UInt64] = []
        var states: [LiveMapDisplayState] = []
        let descriptor = GarminRasterResponse(available: true, imageUrl: url.absoluteString)
        let store = GarminRasterImageStore(
            nowNanoseconds: { now }, sleep: { delay in delays.append(delay); now += delay; await Task.yield(); try Task.checkCancellation() },
            loader: { _ in attempts += 1; return attempts == 4 ? image : nil }
        )
        let subscription = store.$isRetrying.sink { retrying in
            states.append(LiveMapDisplayState.resolveLive(.init(
                coverage: "partial", preciseTopoImageReady: false, garminRaster: descriptor,
                garminImageFailed: retrying, hasCachedPreciseTopo: false
            )))
        }
        defer { subscription.cancel(); GarminRasterImageStore.resetRetryCursors() }
        let finished = expectation(description: "fourth attempt settled")
        let load = Task { await store.load(url); finished.fulfill() }
        defer { load.cancel() }
        await fulfillment(of: [finished], timeout: 1)
        // C33 explicitly requires surviving the initial three failures and immediately displaying #4.
        XCTAssertEqual(attempts, 4)
        XCTAssertEqual(delays, [5_000_000_000, 15_000_000_000, 30_000_000_000])
        XCTAssertTrue(states.contains(.numericPlaceholder))
        XCTAssertEqual(states.last, .garminRaster)
        XCTAssertTrue(store.image === image)
        XCTAssertFalse(store.isRetrying)
        var cursor = GarminRasterRetryCursor()
        for _ in 0..<12 { cursor.recordFailure(at: 0) }
        XCTAssertEqual(cursor.nextPlan(nowNanoseconds: 0)?.delayNanoseconds, 60_000_000_000)
    }

    func testChangingHoleCancelsGarminRetry() async {
        var attempts = 0
        let waiting = expectation(description: "retry waiting")
        let store = GarminRasterImageStore(
            nowNanoseconds: { 0 }, sleep: { _ in
                waiting.fulfill(); try await Task.sleep(nanoseconds: 10_000_000_000)
            }, loader: { _ in attempts += 1; return nil }
        )
        let finished = expectation(description: "cancelled retry settled")
        let load = Task {
            await store.load(URL(string: "https://c33.example.test/cancel.jpg")!)
            finished.fulfill()
        }
        defer { load.cancel() }
        await fulfillment(of: [waiting], timeout: 1)
        load.cancel()
        await fulfillment(of: [finished], timeout: 1)
        XCTAssertEqual(attempts, 1)
        XCTAssertFalse(store.isRetrying)
    }

    func testGreenFailureUsesCachedTopoBeforeGarmin() async throws {
        let hole = try XCTUnwrap(c33Package().coursePrep?.holes.first)
        let topoURL = URL(string: "https://c33.example.test/\(UUID().uuidString)/topo.png")!
        let rasterURL = URL(string: "https://c33.example.test/\(UUID().uuidString)/raster.jpg")!
        let image = UIGraphicsImageRenderer(size: CGSize(width: 678, height: 1060)).image { _ in UIColor.green.setFill(); UIRectFill(CGRect(x: 0, y: 0, width: 678, height: 1060)) }
        TopoHoleImageStore.preload(image, for: topoURL)
        GarminRasterImageStore.preload(image, for: rasterURL)
        // A corrupt local green.png exercises the real decode-failure path without any network.
        let failedGreenURL = FileManager.default.temporaryDirectory.appendingPathComponent("c33-\(UUID().uuidString)-green.png")
        try Data("invalid png".utf8).write(to: failedGreenURL)
        defer { try? FileManager.default.removeItem(at: failedGreenURL) }
        let detailStore = TopoHoleImageStore()
        await detailStore.load(failedGreenURL)
        XCTAssertEqual(detailStore.failedURL, failedGreenURL)
        XCTAssertNil(detailStore.image)
        XCTAssertNil(hole.map?.image)
        let selection = GreenDetailImageResolver.resolve(
            hole: hole, detailImage: detailStore.image, topoURL: topoURL, garminURL: rasterURL,
            garminProjection: hole.holeImageProjection
        )
        XCTAssertEqual(selection.source, .topo)
        XCTAssertNotNil(selection.image)
        XCTAssertLessThan(selection.image!.size.height, 1060) // cropped green, not the full-hole thumbnail
    }

    func testGreenFailureWithoutTopoUsesGarminThenSchematic() throws {
        let hole = try XCTUnwrap(c33Package().coursePrep?.holes.first)
        let rasterURL = URL(string: "https://c33.example.test/\(UUID().uuidString)/raster.jpg")!
        let image = UIGraphicsImageRenderer(size: CGSize(width: 678, height: 1060)).image { _ in }
        GarminRasterImageStore.preload(image, for: rasterURL)
        // C33 fallback order: failed green + absent topo + cached Garmin must still draw a green.
        let selection = GreenDetailImageResolver.resolve(
            hole: hole, detailImage: nil, topoURL: nil, garminURL: rasterURL,
            garminProjection: hole.holeImageProjection
        )
        XCTAssertEqual(selection.source, .garmin)
        XCTAssertNotNil(selection.image)
        let visualOnly = GreenDetailImageResolver.resolve(
            hole: hole, detailImage: nil, topoURL: nil, garminURL: rasterURL, garminProjection: nil
        )
        XCTAssertEqual(visualOnly.source, .garmin)
        XCTAssertTrue(visualOnly.image === image)
        XCTAssertFalse(visualOnly.registered)
        let schematic = GreenDetailImageResolver.resolve(
            hole: hole, detailImage: nil, topoURL: nil, garminURL: nil, garminProjection: nil
        )
        XCTAssertEqual(schematic.source, .schematic)
        XCTAssertNotNil(schematic.image)
    }
}
#endif
