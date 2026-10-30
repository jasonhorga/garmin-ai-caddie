#if !SWIFT_PACKAGE && canImport(UIKit)
import Foundation
import UIKit
import XCTest
@testable import AICaddie

@MainActor
final class LiveMapFirstFrameTests: XCTestCase {
    /// J4.5-1: an installed precise map owns the first frame even before decode completes.
    func testKnownPreciseTopoNeverFallsBackToGarminBeforeDecode() throws {
        // Either availability signal reserves the precise map, with or without a ready Garmin.
        for (available, cached) in [(true, false), (false, true)] {
            for garminReady in [true, false] {
                let state = LiveMapDisplayState.resolveLive(.init(
                    coverage: "ready",
                    preciseTopoImageReady: false,
                    garminRaster: GarminRasterResponse(available: true, imageUrl: "/garmin.png"),
                    garminImageReady: garminReady,
                    garminImageFailed: false,
                    hasCachedPreciseTopo: cached,
                    preciseTopoAvailable: available
                ))
                try assertNeutralDecodeFrame(state)
            }
        }
    }

    private func assertNeutralDecodeFrame(
        _ state: LiveMapDisplayState,
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws {
        let prep = try ProductInputs.prep()
        let overlay = try XCTUnwrap(prep.resolvedMapOverlay)
        let projection = CoursePrepHoleImageProjection(
            available: true, widthPx: 300, heightPx: 400,
            refs: [
                CoursePrepProjectionRef(lat: 0, lon: 0, px: 100, py: 350),
                CoursePrepProjectionRef(lat: 0, lon: 0.001, px: 200, py: 350),
                CoursePrepProjectionRef(lat: 0.001, lon: 0, px: 100, py: 250),
            ]
        )
        XCTAssertNotEqual(state, .garminRaster, file: file, line: line)
        XCTAssertNotEqual(state, .waiting, "No preparation/spinner page during local decode", file: file, line: line)
        XCTAssertEqual(state, .factualPending, file: file, line: line)
        XCTAssertNil(LiveMapDisplaySelection.overlay(
            for: state, precise: overlay, preciseProjection: projection, garminProjection: projection
        ), "J4.5 no route/label/target/flag over the neutral frame", file: file, line: line)
        XCTAssertNil(LiveMapDisplaySelection.projection(
            for: state, precise: projection, garmin: projection
        ), file: file, line: line)
        XCTAssertNil(LiveMapDisplaySelection.mapFrameOverlay(
            for: state, overlay: overlay, garminProjection: projection
        ), file: file, line: line)
        XCTAssertNil(LiveMapDisplaySelection.gestureFrameOverlay(
            for: state, overlay: overlay, garminProjection: projection
        ), file: file, line: line)
    }

    /// J4.5-1: a local precise map without a prep route also gets a neutral decode frame.
    func testKnownPreciseTopoWithNoPrepRouteKeepsNeutralPendingFrame() throws {
        let inputs = LiveMapDisplayState.liveInputs(
            coverage: "ready",
            decodeFailed: false,
            resolvedLocalTopoURL: URL(fileURLWithPath: "/tmp/known-topo.png"),
            hasLiveTopoURL: true,
            hasEmbeddedTopoImage: false,
            preciseTopoImageReady: false,
            memoryCached: false,
            garminRaster: GarminRasterResponse(available: true, imageUrl: "/garmin.png"),
            garminImageReady: true,
            garminImageFailed: false,
            hasRoute: false
        )
        try assertNeutralDecodeFrame(LiveMapDisplayState.resolveLive(inputs))
    }

    /// J4.5-1/2: a failed local decode releases the neutral frame for the ready Garmin bitmap.
    func testFailedPreciseDecodeAllowsReadyGarminFallback() {
        let inputs = LiveMapDisplayState.liveInputs(
            coverage: "ready",
            decodeFailed: true,
            resolvedLocalTopoURL: URL(fileURLWithPath: "/tmp/broken-topo.png"),
            hasLiveTopoURL: true,
            hasEmbeddedTopoImage: false,
            preciseTopoImageReady: false,
            memoryCached: false,
            garminRaster: GarminRasterResponse(available: true, imageUrl: "/garmin.png"),
            garminImageReady: true,
            garminImageFailed: false
        )
        let state = LiveMapDisplayState.resolveLive(inputs)
        XCTAssertEqual(state, .garminRaster)
    }

    /// J4.5-1/4: local decode completion promotes to precise; failure without Garmin waits neutrally.
    func testLocalPreciseDecodeCompletionAndFailureWithoutGarmin() {
        for failed in [false, true] {
            let inputs = LiveMapDisplayState.liveInputs(
                coverage: "ready", decodeFailed: failed,
                resolvedLocalTopoURL: URL(fileURLWithPath: "/tmp/installed-topo.png"),
                hasLiveTopoURL: true, hasEmbeddedTopoImage: false,
                preciseTopoImageReady: !failed, memoryCached: false,
                garminRaster: nil, garminImageReady: false, garminImageFailed: false
            )
            XCTAssertEqual(LiveMapDisplayState.resolveLive(inputs), failed ? .waiting : .precise)
        }
    }

    func testNeighbourLookupUsesTheSameLocalURLThatPrefetchDecodes() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("live-map-first-frame-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let png = Data(base64Encoded:
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )!
        XCTAssertTrue(try store.saveCourseTopoImage(png, globalId: 42, localHole: 3, geometryRevision: "r1"))
        let url = LiveTopoAvailability.localTopoURL(
            store: store, globalId: 42, localHole: 3, geometryRevision: "r1"
        )
        XCTAssertTrue(url?.isFileURL == true)
        let loaded = await TopoHoleImageStore.ensureLoaded(url)
        XCTAssertTrue(loaded)
        XCTAssertTrue(TopoHoleImageStore.isMemoryCached(url))
    }
}
#endif
